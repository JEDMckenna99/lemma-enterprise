"""
Canonical site hostname helpers for SDK siteId and isHuman site binding.
"""

from __future__ import annotations

from typing import Optional, Tuple

from api.ppid import canonicalize_rp_id


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
