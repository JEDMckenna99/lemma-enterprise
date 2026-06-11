"""Canonical lemma.id managed sites for admin dashboard."""

from __future__ import annotations

from typing import Iterable, List, Optional, Set

# Platform + isHuman demo sites shown on admin Sites tab.
MANAGED_SITE_IDS: Set[str] = frozenset(
    {
        "lemma.id",
        "site_demo_tickets",
        "site_demo_trials",
        "site_demo_trails",  # alias if provisioned under this id
    }
)

_DEMO_SITE_IDS: Set[str] = frozenset(
    {
        "site_demo_tickets",
        "site_demo_trials",
        "site_demo_trails",
    }
)


def normalize_site_id(site_id: Optional[str]) -> str:
    return (site_id or "").strip().lower()


def is_managed_platform_site(site_id: Optional[str]) -> bool:
    return normalize_site_id(site_id) in MANAGED_SITE_IDS


def is_demo_site(site_id: Optional[str]) -> bool:
    return normalize_site_id(site_id) in _DEMO_SITE_IDS


def filter_managed_sites(sites: Iterable[dict]) -> List[dict]:
    """Keep only managed platform/demo sites for admin views."""
    kept: List[dict] = []
    seen: Set[str] = set()
    for row in sites:
        site_id = normalize_site_id(row.get("site_id"))
        if not site_id or site_id not in MANAGED_SITE_IDS or site_id in seen:
            continue
        seen.add(site_id)
        kept.append(row)
    kept.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return kept
