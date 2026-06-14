"""
Canonical site-bound PPID revocation for isHuman and IAM.

Tier-1 enforcement:
- SiteBlock (site-scoped deny list)
- RevocationList with revocation_type='user' and raw site-bound PPID
- Bloom sync via revocation_sync (raw PPID as the revocation key)

Also exports `clear_amnesty_eligible_wallet_revocations`, the helper called
from both the production Stripe Identity webhook and the demo test-mode IDV
endpoint to lift revocations after a wallet owner has re-proved identity.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

LEMMA_TYPE_ISHUMAN = "ishuman"


def clear_amnesty_eligible_wallet_revocations(
    db,
    *,
    wallet_id: str,
    new_master_credential_id: str = "",
    reason: str = "fresh_idv_reset",
) -> dict:
    """Clear amnesty-eligible revocation state for a wallet.

    Called after a wallet owner has re-proved identity by either:
      * completing a fresh Stripe Identity check (production), or
      * signing a wallet_assertion proving wallet ownership (demo recovery)

    Policy:
      * Per-credential revocations for old credentials owned by this wallet
        are cleared (the new master supersedes them).
      * Site-scoped PPID blocks (`revocation_type='user'` with a `site_id`)
        are cleared and the matching SiteBlock rows deactivated. The site
        remains free to re-block the PPID immediately if its anti-abuse
        policy still requires it; the network does not litigate that.
      * Wallet-level kill rows (`revocation_type='wallet'`) for THIS wallet
        are cleared -- EXCEPT rows marked `is_amnesty_eligible=False`, which are
        governance-approved coordinated-fraud kills that survive re-IDV and stay
        sticky until the network explicitly reinstates the subject. The same
        carve-out applies to site blocks and user/credential revocations below.

    Cross-device recovery: site PPIDs are derived from the deterministic
    person-root, so the *same* site PPID can be blocked on a prior device's
    wallet yet re-derived identically on a new wallet after recovery. We resolve
    the LemmaPerson for the re-verifying wallet and gather every wallet bound to
    that person, so the site-scoped clears below cover blocks placed against any
    of the person's devices -- not just the wallet that happens to complete this
    IDV. Wallet-level kill clearing stays scoped to THIS wallet (a kill on an old
    device's wallet_id cannot block a freshly recovered wallet anyway).

    Returns a counts dict for the caller to surface in logs / responses.
    """
    from api.database import (
        RevocationList,
        SiteBlock,
        DerivedCredential,
        IsHumanVerification,
        LemmaWalletBinding,
    )

    # Resolve the person and every wallet bound to them so site-scoped amnesty
    # spans devices (deterministic person-root PPIDs are identical across the
    # person's wallets). Falls back to the single wallet when no binding exists.
    person_id = None
    wallet_ids = {wallet_id} if wallet_id else set()
    binding = (
        db.query(LemmaWalletBinding).filter_by(wallet_id=wallet_id).first()
        if wallet_id
        else None
    )
    if binding and binding.lemma_person_id:
        person_id = binding.lemma_person_id
        for sibling in (
            db.query(LemmaWalletBinding)
            .filter_by(lemma_person_id=person_id)
            .all()
        ):
            if sibling.wallet_id:
                wallet_ids.add(sibling.wallet_id)

    logger.info(
        "[amnesty-reset] start wallet_id=%s person_id=%s person_wallets=%d new_master=%s reason=%s",
        wallet_id,
        person_id,
        len(wallet_ids),
        (new_master_credential_id or "")[:30],
        reason,
    )

    derived_rows = (
        db.query(DerivedCredential)
        .filter(DerivedCredential.wallet_id.in_(wallet_ids))
        .all()
        if wallet_ids
        else []
    )
    derived_ppids = sorted({row.derived_ppid for row in derived_rows if row.derived_ppid})
    derived_cred_ids = sorted({
        row.derived_credential_id for row in derived_rows if row.derived_credential_id
    })
    logger.info(
        "[amnesty-reset] derived_credentials=%d ppids=%d",
        len(derived_rows), len(derived_ppids),
    )

    masters = db.query(IsHumanVerification).filter_by(wallet_id=wallet_id).all()
    stale_master_cred_ids = sorted({
        m.credential_id for m in masters
        if m.credential_id and m.credential_id != new_master_credential_id
    })

    # Mark prior masters as 'superseded' so the new master is the only
    # status='verified' row and derive-site-proof picks it up unambiguously.
    superseded_masters = 0
    for old_master in masters:
        if (
            old_master.credential_id
            and old_master.credential_id != new_master_credential_id
            and old_master.status in ("revoked", "verified")
        ):
            old_master.status = "superseded"
            superseded_masters += 1

    # Governance carve-out (gap #2): rows marked is_amnesty_eligible=False are
    # coordinated-fraud kills approved by Lemma.id governance. A fresh IDV must
    # NOT lift them; they stay sticky until the network explicitly reinstates the
    # subject. `.isnot(False)` keeps legacy rows (TRUE / NULL) eligible.
    cleared_entries = 0
    rl_query = db.query(RevocationList)
    cleared_entries += rl_query.filter(
        RevocationList.wallet_id == wallet_id,
        RevocationList.revocation_type == "wallet",
        RevocationList.is_amnesty_eligible.isnot(False),
    ).delete(synchronize_session=False)
    if stale_master_cred_ids:
        cleared_entries += rl_query.filter(
            RevocationList.credential_id.in_(stale_master_cred_ids),
            RevocationList.revocation_type == "credential",
            RevocationList.is_amnesty_eligible.isnot(False),
        ).delete(synchronize_session=False)
    if derived_cred_ids:
        cleared_entries += rl_query.filter(
            RevocationList.credential_id.in_(derived_cred_ids),
            RevocationList.revocation_type == "credential",
            RevocationList.is_amnesty_eligible.isnot(False),
        ).delete(synchronize_session=False)
    if derived_ppids:
        cleared_entries += rl_query.filter(
            RevocationList.ppid.in_(derived_ppids),
            RevocationList.revocation_type == "user",
            RevocationList.is_amnesty_eligible.isnot(False),
        ).delete(synchronize_session=False)

    site_blocks_cleared = 0
    if derived_ppids:
        site_blocks_cleared = db.query(SiteBlock).filter(
            SiteBlock.ppid.in_(derived_ppids),
            SiteBlock.is_active == True,  # noqa: E712
            SiteBlock.is_amnesty_eligible.isnot(False),
        ).update({"is_active": False}, synchronize_session=False)

    derived_reactivated = 0
    if derived_cred_ids:
        derived_reactivated = db.query(DerivedCredential).filter(
            DerivedCredential.derived_credential_id.in_(derived_cred_ids),
            DerivedCredential.is_active == False,  # noqa: E712
        ).update({"is_active": True, "revoked_at": None}, synchronize_session=False)

    db.commit()

    try:
        from api.bloom_snapshot import invalidate_bloom_filter_cache
        invalidate_bloom_filter_cache()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bloom cache invalidation failed: %s", exc)

    try:
        from api.revocation_sync import get_event_bus
        bus = get_event_bus()
        if hasattr(bus, "publish_revocation_clear"):
            bus.publish_revocation_clear(wallet_id, reason=reason)
    except Exception:
        pass

    summary = {
        "wallet_id": wallet_id,
        "person_id": person_id,
        "person_wallets": len(wallet_ids),
        "cleared_revocation_entries": int(cleared_entries),
        "cleared_site_blocks": int(site_blocks_cleared),
        "reactivated_derived_credentials": int(derived_reactivated),
        "superseded_master_records": int(superseded_masters),
        "derived_ppids_cleared": derived_ppids,
        "reason": reason,
    }
    logger.info(
        "[amnesty-reset] done wallet_id=%s rev=%d site_blocks=%d reactivated=%d superseded=%d",
        wallet_id,
        summary["cleared_revocation_entries"],
        summary["cleared_site_blocks"],
        summary["reactivated_derived_credentials"],
        summary["superseded_master_records"],
    )
    return summary


def effective_revocation_keys(
    *,
    lemma_id: Optional[str] = None,
    credential_id: Optional[str] = None,
    ppid: Optional[str] = None,
    wallet_id: Optional[str] = None,
) -> list[str]:
    """Identifiers to add to the in-process Bloom verifier / public bloom API."""
    keys: list[str] = []
    for value in (lemma_id, credential_id, ppid, wallet_id):
        if value and value not in keys:
            keys.append(str(value))
    return keys


def keys_for_revocation_row(row: Any) -> list[str]:
    return effective_revocation_keys(
        lemma_id=getattr(row, "lemma_id", None),
        credential_id=getattr(row, "credential_id", None),
        ppid=getattr(row, "ppid", None),
        wallet_id=getattr(row, "wallet_id", None),
    )


def resolve_site_by_domain(db, target_site: str) -> Any | None:
    """Resolve a registered Site row from a normalized hostname / rp_id."""
    from api.database import Site
    from api.site_hostname import try_canonicalize_site_hostname

    domain, err = try_canonicalize_site_hostname(target_site)
    if err or not domain:
        return None

    site = db.query(Site).filter_by(site_domain=domain).first()
    if site:
        return site

    for candidate in db.query(Site).all():
        candidate_domain, candidate_err = try_canonicalize_site_hostname(
            getattr(candidate, "site_domain", "")
        )
        if not candidate_err and candidate_domain == domain:
            return candidate
    return None


def is_site_ppid_blocked(db, *, site_id: str, ppid: str) -> bool:
    from api.database import SiteBlock

    if not site_id or not ppid:
        return False
    block = (
        db.query(SiteBlock)
        .filter_by(site_id=site_id, ppid=ppid, is_active=True)
        .first()
    )
    return block is not None


def revoke_site_bound_ppid(
    db,
    *,
    site_id: str,
    ppid: str,
    reason: str = "",
    revoked_by: str = "api",
    site_domain: Optional[str] = None,
    blocked_by: Optional[str] = None,
    evidence_url: Optional[str] = None,
    network_revocation_requested: bool = False,
    network_revocation_status: Optional[str] = None,
    amnesty_eligible: bool = True,
    skip_bloom_sync: bool = False,
    commit: bool = True,
) -> dict:
    """
    Canonical tier-1 site revocation for a site-bound PPID.

    Writes SiteBlock + RevocationList (user scope) and publishes Bloom sync
    using the raw PPID so server and client verifiers agree.

    ``amnesty_eligible=False`` marks this as a governance-approved coordinated-
    fraud kill: a subsequent fresh IDV will NOT lift it (see
    clear_amnesty_eligible_wallet_revocations). Setting it False is sticky --
    re-revoking an existing eligible block with amnesty_eligible=False escalates
    it, but an ordinary site re-block never silently downgrades a governance kill
    back to eligible.
    """
    from api.database import SiteBlock, RevocationList

    ppid = (ppid or "").strip()
    if not ppid:
        raise ValueError("ppid required")
    if not site_id:
        raise ValueError("site_id required")

    block = (
        db.query(SiteBlock)
        .filter_by(site_id=site_id, ppid=ppid)
        .first()
    )
    block_created = False
    if not block:
        block = SiteBlock(
            site_id=site_id,
            ppid=ppid,
            reason=reason,
            blocked_by=blocked_by or revoked_by,
            evidence_url=evidence_url,
            network_revocation_requested=network_revocation_requested,
            network_revocation_status=network_revocation_status,
            is_amnesty_eligible=amnesty_eligible,
        )
        db.add(block)
        block_created = True
    elif not block.is_active:
        block.is_active = True
        block_created = True
        if not amnesty_eligible:
            block.is_amnesty_eligible = False
    else:
        if reason:
            block.reason = reason
        if evidence_url:
            block.evidence_url = evidence_url
        if network_revocation_requested:
            block.network_revocation_requested = True
        if network_revocation_status:
            block.network_revocation_status = network_revocation_status
        # Escalation only: a governance kill (False) is sticky and never
        # downgraded back to eligible by an ordinary re-block.
        if not amnesty_eligible:
            block.is_amnesty_eligible = False

    existing_revoke = (
        db.query(RevocationList)
        .filter_by(ppid=ppid, site_id=site_id, revocation_type="user")
        .first()
    )
    revocation_created = False
    if not existing_revoke:
        db.add(
            RevocationList(
                lemma_id=ppid,
                credential_id=ppid,
                ppid=ppid,
                site_id=site_id,
                lemma_type=LEMMA_TYPE_ISHUMAN,
                revocation_type="user",
                revoked_by=revoked_by,
                reason=reason or "site_ppid_revocation",
                revoked_at=datetime.utcnow(),
                is_amnesty_eligible=amnesty_eligible,
            )
        )
        revocation_created = True
    elif not amnesty_eligible and existing_revoke.is_amnesty_eligible is not False:
        # Escalate an existing eligible user-scope revocation to a sticky kill.
        existing_revoke.is_amnesty_eligible = False

    if commit:
        db.commit()
        try:
            from api.bloom_snapshot import invalidate_bloom_filter_cache

            invalidate_bloom_filter_cache()
        except Exception:
            pass

    event_published = False
    if commit and not skip_bloom_sync:
        try:
            from api.revocation_sync import trigger_revocation_sync

            event_published = bool(
                trigger_revocation_sync(
                    ppid,
                    credential_type=LEMMA_TYPE_ISHUMAN,
                    site_id=site_id,
                )
            )
        except Exception as exc:
            logger.warning("Site PPID revocation sync failed: %s", exc)

    return {
        "site_id": site_id,
        "site_domain": site_domain,
        "ppid": ppid,
        "block_id": getattr(block, "id", None),
        "block_created": block_created,
        "revocation_created": revocation_created,
        "event_published": event_published,
    }


def clear_site_bound_ppid(
    db,
    *,
    site_id: str,
    ppid: str,
    cleared_by: str = "api",
    commit: bool = True,
) -> dict:
    """Reverse a tier-1 site block for a site-bound PPID (the inverse of
    ``revoke_site_bound_ppid``).

    Deactivates the ``SiteBlock`` row AND removes the canonical user-scope
    ``RevocationList`` entry so server + client verifiers stop rejecting the
    PPID once the Bloom is rebuilt. Governance-approved coordinated-fraud kills
    (``is_amnesty_eligible=False``) are deliberately left in place — an ordinary
    site unblock must not lift a network kill. The return dict reports whether
    anything was actually lifted vs. blocked by a governance kill.
    """
    from api.database import SiteBlock, RevocationList

    ppid = (ppid or "").strip()
    if not ppid:
        raise ValueError("ppid required")
    if not site_id:
        raise ValueError("site_id required")

    # Governance carve-out: never lift a sticky kill via a site unblock.
    governance_kill = (
        db.query(SiteBlock)
        .filter(
            SiteBlock.site_id == site_id,
            SiteBlock.ppid == ppid,
            SiteBlock.is_active == True,  # noqa: E712
            SiteBlock.is_amnesty_eligible.is_(False),
        )
        .first()
    )
    if governance_kill is not None:
        return {
            "site_id": site_id,
            "ppid": ppid,
            "lifted": False,
            "reason": "governance_kill_not_amnesty_eligible",
            "blocks_deactivated": 0,
            "revocations_cleared": 0,
        }

    blocks_deactivated = (
        db.query(SiteBlock)
        .filter(
            SiteBlock.site_id == site_id,
            SiteBlock.ppid == ppid,
            SiteBlock.is_active == True,  # noqa: E712
            SiteBlock.is_amnesty_eligible.isnot(False),
        )
        .update({"is_active": False}, synchronize_session=False)
    )

    revocations_cleared = (
        db.query(RevocationList)
        .filter(
            RevocationList.ppid == ppid,
            RevocationList.site_id == site_id,
            RevocationList.revocation_type == "user",
            RevocationList.is_amnesty_eligible.isnot(False),
        )
        .delete(synchronize_session=False)
    )

    if commit:
        db.commit()
        try:
            from api.bloom_snapshot import invalidate_bloom_filter_cache

            invalidate_bloom_filter_cache()
        except Exception:
            pass
        try:
            from api.revocation_sync import get_event_bus

            bus = get_event_bus()
            if hasattr(bus, "publish_revocation_clear"):
                bus.publish_revocation_clear(ppid, reason="site_unblock")
        except Exception:
            pass

    logger.info(
        "Site unblock: site=%s ppid=%s blocks=%d revocations=%d by=%s",
        site_id, ppid[:40], blocks_deactivated, revocations_cleared, cleared_by,
    )
    return {
        "site_id": site_id,
        "ppid": ppid,
        "lifted": bool(blocks_deactivated or revocations_cleared),
        "reason": "ok",
        "blocks_deactivated": int(blocks_deactivated),
        "revocations_cleared": int(revocations_cleared),
    }


def sync_revocation_row_to_bloom(row: Any) -> int:
    """Add all effective keys for a revocation row to the global Bloom verifier."""
    from api.permission_verification import get_global_verifier, sync_single_revocation

    added = 0
    for key in keys_for_revocation_row(row):
        if sync_single_revocation(key):
            added += 1
    verifier = get_global_verifier()
    if verifier is None and added == 0:
        return 0
    return added
