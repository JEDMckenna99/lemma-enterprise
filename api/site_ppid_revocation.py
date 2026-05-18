"""
Canonical site-bound PPID revocation for isHuman and IAM.

Tier-1 enforcement:
- SiteBlock (site-scoped deny list)
- RevocationList with revocation_type='user' and raw site-bound PPID
- Bloom sync via revocation_sync (raw PPID as the revocation key)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

LEMMA_TYPE_ISHUMAN = "ishuman"


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
    from api.ppid import canonicalize_rp_id

    domain = canonicalize_rp_id(target_site)
    if not domain or domain == "unknown":
        return None

    site = db.query(Site).filter_by(site_domain=domain).first()
    if site:
        return site

    for candidate in db.query(Site).all():
        if canonicalize_rp_id(getattr(candidate, "site_domain", "")) == domain:
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
    skip_bloom_sync: bool = False,
    commit: bool = True,
) -> dict:
    """
    Canonical tier-1 site revocation for a site-bound PPID.

    Writes SiteBlock + RevocationList (user scope) and publishes Bloom sync
    using the raw PPID so server and client verifiers agree.
    """
    from api.database import SiteBlock, RevocationList

    ppid = (ppid or "").strip()
    if not ppid:
        raise ValueError("ppid required")
    if not site_id:
        raise ValueError("site_id required")

    block = (
        db.query(SiteBlock)
        .filter_by(site_id=site_id, ppid=ppid, is_active=True)
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
        )
        db.add(block)
        block_created = True
    else:
        if reason:
            block.reason = reason
        if evidence_url:
            block.evidence_url = evidence_url
        if network_revocation_requested:
            block.network_revocation_requested = True
        if network_revocation_status:
            block.network_revocation_status = network_revocation_status

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
            )
        )
        revocation_created = True

    if commit:
        db.commit()

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
