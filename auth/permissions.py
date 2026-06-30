"""
Canonical permission and scope helpers for Lemma auth.
"""

from typing import Iterable

# Canonical scopes used by agent/session authorization
CANONICAL_SCOPES = {"read", "write", "admin", "developer", "test"}

# Legacy aliases mapped to canonical values
SCOPE_ALIASES = {
    "super_admin": "admin",
    "superadmin": "admin",
    "site_admin": "admin",
    "admin_access": "admin",
    "dev": "developer",
}

# Credential permission ids accepted as admin-equivalent
ADMIN_PERMISSION_IDS = {
    "admin",
    "admin_access",
    "super_admin",
    "superadmin",
    "site_admin",
}


def normalize_scope(scope: str) -> str:
    if not scope:
        return ""
    value = scope.strip().lower()
    return SCOPE_ALIASES.get(value, value)


def normalize_scopes(scopes: Iterable[str]) -> list[str]:
    normalized = []
    for scope in scopes or []:
        norm = normalize_scope(scope)
        if norm and norm in CANONICAL_SCOPES and norm not in normalized:
            normalized.append(norm)
    return normalized


def is_admin_permission(permission_id: str) -> bool:
    """Return True only for explicitly recognized admin permission ids.

    SECURITY: This must never use a substring match such as ``"admin" in value``
    because that treats ``"non_admin"``, ``"badmin"``, ``"readonly_admin_viewer"``
    and any other attacker-influenced string containing "admin" as admin, which
    is a direct privilege-escalation primitive. We match against an explicit
    allowlist, tolerating only a canonical trailing ``_access`` suffix (e.g.
    ``"super_admin_access"`` -> ``"super_admin"``).
    """
    if not permission_id:
        return False
    value = permission_id.strip().lower()
    if value in ADMIN_PERMISSION_IDS:
        return True
    if value.endswith("_access"):
        base = value[: -len("_access")]
        if base in ADMIN_PERMISSION_IDS:
            return True
    return False
