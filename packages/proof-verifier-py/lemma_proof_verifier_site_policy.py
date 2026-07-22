"""Site-scoped block/doubt enforcement helpers for relying-site backends."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class SiteDecision:
    blocked: bool = False
    doubt_required: bool = False
    reason: Optional[str] = None
    doubt_reason: Optional[str] = None


class SitePolicyStore(Protocol):
    def check(self, ppid: str) -> tuple[bool, SiteDecision, str]:
        """Return (available, decision, error_reason)."""


class InMemorySitePolicyStore:
    """Local mirror for tests and demos."""

    def __init__(
        self,
        *,
        blocked: Optional[set[str]] = None,
        doubted: Optional[set[str]] = None,
    ) -> None:
        self.blocked = set(blocked or ())
        self.doubted = set(doubted or ())

    def check(self, ppid: str) -> tuple[bool, SiteDecision, str]:
        ppid = str(ppid or "").strip()
        if not ppid:
            return True, SiteDecision(), "ppid_missing"
        if ppid in self.blocked:
            return True, SiteDecision(blocked=True, reason="site_block"), "ok"
        if ppid in self.doubted:
            return True, SiteDecision(doubt_required=True, doubt_reason="site_doubt"), "ok"
        return True, SiteDecision(), "ok"


class LemmaCheckPolicyStore:
    """Server-only store backed by GET /api/ishuman/check."""

    def __init__(
        self,
        *,
        site_id: str,
        api_key: str,
        lemma_origin: str = "https://lemma.id",
        cache_ttl_seconds: int = 30,
        timeout_seconds: int = 5,
        fail_closed: bool = True,
    ) -> None:
        self.site_id = site_id
        self.api_key = api_key
        self.lemma_origin = lemma_origin.rstrip("/")
        self.cache_ttl_seconds = max(1, int(cache_ttl_seconds))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.fail_closed = fail_closed
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, SiteDecision]] = {}

    def check(self, ppid: str) -> tuple[bool, SiteDecision, str]:
        ppid = str(ppid or "").strip()
        if not ppid:
            return False, SiteDecision(), "ppid_missing"
        now = time.time()
        with self._lock:
            cached = self._cache.get(ppid)
            if cached and now - cached[0] <= self.cache_ttl_seconds:
                return True, cached[1], "ok"
        url = (
            f"{self.lemma_origin}/api/ishuman/check"
            f"?ppid={urllib.parse.quote(ppid)}&site_id={urllib.parse.quote(self.site_id)}"
        )
        req = urllib.request.Request(
            url,
            headers={"X-API-Key": self.api_key},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:  # noqa: S310
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if self.fail_closed:
                return False, SiteDecision(), "site_policy_unavailable"
            return True, SiteDecision(), "site_policy_unavailable"
        if not payload.get("success"):
            if self.fail_closed:
                return False, SiteDecision(), "site_policy_unavailable"
            return True, SiteDecision(), "site_policy_unavailable"
        decision = SiteDecision(
            blocked=bool(payload.get("blocked")),
            doubt_required=bool(payload.get("doubt_required")),
            reason=payload.get("reason"),
            doubt_reason=payload.get("doubt_reason"),
        )
        with self._lock:
            self._cache[ppid] = (now, decision)
        return True, decision, "ok"


def enforce_site_policy(
    *,
    ppid: str,
    policy_store: Optional[SitePolicyStore],
    legacy_ppid: Optional[str] = None,
    require_policy: bool = True,
) -> tuple[bool, str, Optional[SiteDecision]]:
    """Fail-closed site-policy gate for server middleware."""
    if policy_store is None:
        if require_policy:
            return False, "site_policy_not_configured", None
        return True, "ok", None

    for candidate in (ppid, legacy_ppid):
        if not candidate:
            continue
        available, decision, err = policy_store.check(candidate)
        if not available:
            return False, err, None
        if decision.blocked:
            return False, "site_blocked", decision
        if decision.doubt_required:
            return False, "doubt_required", decision
    return True, "ok", None
