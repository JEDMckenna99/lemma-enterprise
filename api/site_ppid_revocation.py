"""
Canonical site-bound PPID revocation for isHuman and IAM.

Tier-1 enforcement:
- SiteBlock (site-scoped deny list)
- RevocationList with revocation_type='user' and raw site-bound PPID
- Bloom sync via revocation_sync (raw PPID as the revocation key)

Also exports `clear_amnesty_eligible_wallet_revocations`, the legacy-named helper called
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
    """Clear only wallet/master compromise state after fresh IDV.

    SiteBlock rows and site-scoped user revocations are deliberate site policy
    and are never cleared here. Temporary site doubts clear later, only for the
    requesting site and matching PPID, after successful site-proof issuance.
    """
    from api.database import IsHumanVerification, RevocationList

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
        "cleared_revocation_entries": int(cleared_entries),
        "cleared_site_blocks": 0,
        "reactivated_derived_credentials": 0,
        "superseded_master_records": int(superseded_masters),
        "derived_ppids_cleared": [],
        "reason": reason,
    }
    logger.info(
        "[amnesty-reset] done wallet_id=%s rev=%d site_blocks=%d reactivated=%d superseded=%d",
        wallet_id,
        summary["cleared_revocation_entries"],
        summary["cleared_site_blocks"],
        0,
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
    PPID once the Bloom is rebuilt. This authenticated site operation is the
    only path that removes a site decision.
    """
    from api.database import SiteBlock, RevocationList

    ppid = (ppid or "").strip()
    if not ppid:
        raise ValueError("ppid required")
    if not site_id:
        raise ValueError("site_id required")

    blocks_deactivated = (
        db.query(SiteBlock)
        .filter(
            SiteBlock.site_id == site_id,
            SiteBlock.ppid == ppid,
            SiteBlock.is_active == True,  # noqa: E712
        )
        .update({"is_active": False}, synchronize_session=False)
    )

    revocations_cleared = (
        db.query(RevocationList)
        .filter(
            RevocationList.ppid == ppid,
            RevocationList.site_id == site_id,
            RevocationList.revocation_type == "user",
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
