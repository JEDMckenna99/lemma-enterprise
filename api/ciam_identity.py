"""
Proof-native CIAM identity model helpers.

Maps canonical CIAM concepts onto existing lemma.id tables without changing
the hostname-private PPID default. See docs/architecture/CIAM_IDENTITY_MODEL.md.
"""

from __future__ import annotations

from typing import Optional

# Canonical concept names (documentation + code share vocabulary).
CONCEPT_TENANT = "tenant"
CONCEPT_PLATFORM_SUBJECT = "platform_subject"
CONCEPT_APPLICATION = "application"
CONCEPT_APP_SUBJECT = "app_subject"
CONCEPT_APP_MEMBERSHIP = "app_membership"

# External account key for relying sites.
APP_SUBJECT_KEY = "user_ppid"

# Alias table statuses (schema reserved; no public write API in Phase 1).
ALIAS_STATUS_RESERVED = "reserved"
ALIAS_STATUS_ACTIVE = "active"
ALIAS_STATUS_REVOKED = "revoked"


def normalize_app_subject_ppid(raw_ppid: Optional[str]) -> str:
    """Normalize a site directory subject identifier."""
    return (raw_ppid or "").strip()


def app_subject_key_for_site(site_id: str, user_ppid: str) -> tuple[str, str]:
    """Return the composite directory key (site_id, user_ppid)."""
    return (site_id.strip(), normalize_app_subject_ppid(user_ppid))


def is_active_directory_status(status: Optional[str]) -> bool:
    """True when a site directory row should be treated as login-eligible."""
    normalized = (status or "active").strip().lower()
    return normalized not in {"suspended", "banned", "deleted"}


def runtime_site_binding(site_domain: str) -> str:
    """Runtime siteId / hostname binding used by SDK and presentations."""
    return (site_domain or "").strip().lower()
