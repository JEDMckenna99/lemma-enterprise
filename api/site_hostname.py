"""
Canonical site hostname helpers for SDK siteId and isHuman site binding.
"""

from __future__ import annotations

from typing import Optional, Tuple

from api.ppid import canonicalize_rp_id


PLATFORM_SITE_CANONICAL = "lemma.id"
PLATFORM_SITE_ALIASES = frozenset(
    {
        "lemma.id",
        "lemma_platform",
        "lemma-platform",
        "www.lemma.id",
    }
)


class SiteHostnameError(ValueError):
    """Raised when a hostname cannot be canonicalized for site binding."""


def canonicalize_site_hostname(value: Optional[str]) -> str:
    """
    Normalize integrator hostname input to the SDK siteId / PPID rp_id form.

    Rejects empty, unknown, and internal site_* identifiers passed as domains.
    """
    raw = (value or "").strip()
    if not raw:
        raise SiteHostnameError("hostname_required")

    if raw.lower().startswith("site_"):
        raise SiteHostnameError("internal_site_id_not_allowed")

    canonical = canonicalize_rp_id(raw)
    if not canonical or canonical == "unknown":
        raise SiteHostnameError("invalid_hostname")
    return canonical


def try_canonicalize_site_hostname(value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (canonical_hostname, error_code)."""
    try:
        return canonicalize_site_hostname(value), None
    except SiteHostnameError as exc:
        return None, str(exc)


def normalize_runtime_site_binding(value: Optional[str]) -> Optional[str]:
    """
    Normalize runtime credential/request site binding.

    - Empty values return None (sparse site fields are optional metadata).
    - Internal ``site_*`` identifiers are rejected as runtime binding keys.
    - Platform aliases map to ``lemma.id``.
    - Other values canonicalize to hostname form (lowercase, no www/port/path).
    """
    raw = (value or "").strip()
    if not raw:
        return None

    lowered = raw.lower()
    if lowered.startswith("site_"):
        return None

    host = lowered.split("/")[0].split(":")[0]
    if host.startswith("www."):
        host = host[4:]

    if host in PLATFORM_SITE_ALIASES:
        return PLATFORM_SITE_CANONICAL

    canonical = canonicalize_rp_id(raw)
    if not canonical or canonical == "unknown":
        return host or None
    return canonical


def try_normalize_runtime_site_binding(value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (normalized_runtime_binding, error_code)."""
    normalized = normalize_runtime_site_binding(value)
    if normalized is not None:
        return normalized, None
    raw = (value or "").strip()
    if not raw:
        return None, None
    if raw.lower().startswith("site_"):
        return None, "internal_site_id_not_allowed"
    return None, None
