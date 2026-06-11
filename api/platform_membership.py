"""Registered lemma.id platform member helpers (not every isHuman PPID)."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set

from api.platform_owner import normalize_ppid

_PLATFORM_SITE_IDS = frozenset({"lemma.id", "lemma_platform"})
_PLATFORM_MEMBER_ROLES = frozenset(
    {"developer", "dev", "admin", "owner", "super_admin", "superadmin", "platform_admin"}
)
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


def _role_is_platform_member(role: Optional[str]) -> bool:
    return (role or "").strip().lower() in _PLATFORM_MEMBER_ROLES


def collect_registered_platform_ppids(
    *,
    site_id: str = "lemma.id",
    db=None,
    include_sites: Optional[Iterable[str]] = None,
) -> Set[str]:
    """
    PPIDs with intentional lemma.id platform entitlement.

    Includes active site admins and developer/admin customer records bound to a
    person-root PPID. Excludes orphan platform_user_sites rows from legacy login
    probes and uniform test PPIDs.
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
        from api.database import Customer, SiteAdmin

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

        for row in db.query(Customer).filter(Customer.customer_did.isnot(None)).all():
            ppid = normalize_ppid(row.customer_did)
            if not ppid or is_probe_ppid(ppid):
                continue
            role = (row.role or "").strip().lower()
            if _role_is_platform_member(role):
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
    from api.database import Customer, PlatformUser, PlatformUserSite, SiteAdmin

    pu = db.query(PlatformUser).filter(PlatformUser.user_did == ppid).first()
    membership = (
        db.query(PlatformUserSite)
        .filter(PlatformUserSite.user_did == ppid, PlatformUserSite.site_id == site_id)
        .order_by(PlatformUserSite.id.desc())
        .first()
    )
    customer = db.query(Customer).filter(Customer.customer_did == ppid).first()
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

    effective_role = "user"
    if site_admin:
        effective_role = (site_admin.admin_role or "admin").strip().lower()
    elif customer and _role_is_platform_member(customer.role):
        effective_role = (customer.role or "developer").strip().lower()
    elif membership and _role_is_platform_member(membership.role):
        effective_role = (membership.role or "developer").strip().lower()
    elif membership:
        effective_role = (membership.role or "user").strip().lower()

    if not site_admin and not (customer and _role_is_platform_member(customer.role)):
        if not _role_is_platform_member(effective_role):
            return None

    email = (pu.email if pu and pu.email else None) or (customer.email if customer else None)
    if site_admin and site_admin.admin_email:
        email = email or site_admin.admin_email

    display_name = (
        (pu.display_name if pu else None)
        or (customer.display_name if customer else None)
        or (customer.name if customer else None)
        or (email.split("@")[0] if email else ppid[:18])
    )

    account_status = (
        getattr(pu, "status", None) if pu and getattr(pu, "status", None) else None
    ) or (getattr(membership, "status", None) if membership else None) or "active"

    return {
        "id": pu.id if pu else (membership.id if membership else (getattr(customer, "customer_id", None) if customer else ppid)),
        "internal_identifier": ppid,
        "email": email,
        "display_name": display_name,
        "ppid": ppid,
        "type": "admin" if effective_role in {"admin", "owner", "super_admin", "superadmin"} else "developer",
        "role": effective_role,
        "site_id": site_id,
        "site_count": 1,
        "created_at": getattr(pu, "created_at", None) if pu else (membership.joined_at if membership else getattr(customer, "created_at", None)),
        "last_active": getattr(pu, "last_seen", None) if pu else (membership.joined_at if membership else None),
        "status": str(account_status).lower(),
        "membership_status": (getattr(membership, "status", None) if membership else "active") or "active",
        "joined_at": membership.joined_at if membership else getattr(customer, "created_at", None),
        "source": "site_admins" if site_admin else ("customers" if customer else "platform_user_sites"),
        "verification_level": getattr(pu, "verification_level", None) if pu else None,
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
