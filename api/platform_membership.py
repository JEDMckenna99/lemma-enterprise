"""Registered lemma.id platform member helpers (not every isHuman PPID)."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set

from api.platform_account import is_platform_member_account_type, normalize_account_type
from api.platform_owner import normalize_ppid

_PLATFORM_SITE_IDS = frozenset({"lemma.id", "lemma_platform"})
_PPID_HEX_RE = re.compile(r"^did:lemma:ppid_([0-9a-f]{64})$")
# Security probes / unit tests use uniform hex runs (aaaa..., bbbb..., etc.).
_PROBE_HEX_RUNS = frozenset(ch * 64 for ch in "0123456789abcdef")


def is_platform_site(site_id: Optional[str]) -> bool:
    return (site_id or "").strip().lower() in _PLATFORM_SITE_IDS


def is_probe_ppid(ppid: Optional[str]) -> bool:
    """Detect synthetic PPIDs used by probes/tests, not real person-root identities."""
    normalized = normalize_ppid(ppid)
    if not normalized:
        return True
    match = _PPID_HEX_RE.match(normalized)
    if not match:
        return True
    return match.group(1) in _PROBE_HEX_RUNS


def collect_registered_platform_ppids(
    *,
    site_id: str = "lemma.id",
    db=None,
    include_sites: Optional[Iterable[str]] = None,
) -> Set[str]:
    """
    PPIDs with intentional lemma.id platform entitlement.

    Source of truth: platform_users.account_type + active site_admins.
    """
    close_db = False
    if db is None:
        from api.database import get_db

        db = get_db()
        close_db = True

    site_keys = {site_id.strip().lower()}
    if include_sites:
        site_keys.update(s.strip().lower() for s in include_sites if s)

    registered: Set[str] = set()
    try:
        from api.database import PlatformUser, SiteAdmin

        for key in site_keys:
            for row in (
                db.query(SiteAdmin)
                .filter(
                    SiteAdmin.site_id == key,
                    SiteAdmin.is_active == True,  # noqa: E712
                )
                .all()
            ):
                ppid = normalize_ppid(row.admin_did)
                if ppid and not is_probe_ppid(ppid):
                    registered.add(ppid)

        for row in db.query(PlatformUser).filter(PlatformUser.user_did.isnot(None)).all():
            ppid = normalize_ppid(row.user_did)
            if not ppid or is_probe_ppid(ppid):
                continue
            if is_platform_member_account_type(row.account_type):
                registered.add(ppid)
    finally:
        if close_db and db is not None:
            db.close()

    return registered


def has_registered_platform_membership(ppid: Optional[str], site_id: str = "lemma.id", db=None) -> bool:
    normalized = normalize_ppid(ppid)
    if not normalized or is_probe_ppid(normalized):
        return False
    return normalized in collect_registered_platform_ppids(site_id=site_id, db=db)


def build_platform_user_row(
    *,
    ppid: str,
    site_id: str,
    db,
) -> Optional[Dict[str, Any]]:
    """Build admin user list row for a registered platform PPID."""
    from api.database import PlatformUser, PlatformUserSite, SiteAdmin

    account = db.query(PlatformUser).filter(PlatformUser.user_did == ppid).first()
    membership = (
        db.query(PlatformUserSite)
        .filter(PlatformUserSite.user_did == ppid, PlatformUserSite.site_id == site_id)
        .order_by(PlatformUserSite.id.desc())
        .first()
    )
    site_admin = (
        db.query(SiteAdmin)
        .filter(
            SiteAdmin.site_id == site_id,
            SiteAdmin.admin_did == ppid,
            SiteAdmin.is_active == True,  # noqa: E712
        )
        .order_by(SiteAdmin.id.desc())
        .first()
    )

    effective_role = normalize_account_type(account.account_type if account else "customer")
    if site_admin:
        effective_role = normalize_account_type(site_admin.admin_role or "admin")
    elif membership and is_platform_member_account_type(membership.role):
        effective_role = normalize_account_type(membership.role)

    if not site_admin and not is_platform_member_account_type(effective_role):
        return None

    email = (account.email if account else None)
    if site_admin and site_admin.admin_email:
        email = email or site_admin.admin_email

    display_name = (
        getattr(account, "display_name", None)
        or getattr(account, "name", None)
        or getattr(account, "company", None)
        or (email.split("@")[0] if email else ppid[:18])
    )

    account_status = (
        getattr(account, "status", None) if account and getattr(account, "status", None) else None
    ) or (getattr(membership, "status", None) if membership else None) or "active"

    return {
        "id": getattr(account, "id", None) if account else (getattr(membership, "id", None) if membership else ppid),
        "internal_identifier": ppid,
        "email": email,
        "display_name": display_name,
        "ppid": ppid,
        "type": "admin" if effective_role in {"admin", "owner", "super_admin", "superadmin"} else "developer",
        "role": effective_role,
        "account_type": effective_role,
        "site_id": site_id,
        "site_count": 1,
        "billing_customer_id": getattr(account, "billing_customer_id", None) if account else None,
        "created_at": getattr(account, "created_at", None) if account else (membership.joined_at if membership else None),
        "last_active": getattr(account, "last_seen", None) if account else (membership.joined_at if membership else None),
        "status": str(account_status).lower(),
        "membership_status": (getattr(membership, "status", None) if membership else "active") or "active",
        "joined_at": membership.joined_at if membership else getattr(account, "created_at", None),
        "source": "site_admins" if site_admin else "platform_accounts",
        "verification_level": getattr(account, "verification_level", None) if account else None,
    }


def list_registered_platform_user_rows(
    *,
    site_id: str = "lemma.id",
    db=None,
) -> List[Dict[str, Any]]:
    close_db = False
    if db is None:
        from api.database import get_db

        db = get_db()
        close_db = True

    rows: List[Dict[str, Any]] = []
    try:
        for ppid in sorted(collect_registered_platform_ppids(site_id=site_id, db=db)):
            row = build_platform_user_row(ppid=ppid, site_id=site_id, db=db)
            if row:
                rows.append(row)
    finally:
        if close_db and db is not None:
            db.close()
    return rows
