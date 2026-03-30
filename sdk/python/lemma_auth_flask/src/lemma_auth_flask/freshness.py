from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import request as urllib_request
from urllib.parse import quote


@dataclass
class FreshnessState:
    jwks_last_sync_epoch: float | None = None
    revocation_last_sync_epoch: float | None = None
    policy_last_sync_epoch: float | None = None
    revocation_cursor: int = 0
    policy_version: str | None = None


def _fetch_json(url: str, timeout_seconds: float = 3.0) -> dict | None:
    req = urllib_request.Request(url, method="GET")
    with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
        payload = resp.read().decode("utf-8")
    data = json.loads(payload)
    return data if isinstance(data, dict) else None


class FreshnessClient:
    def __init__(
        self,
        base_url: str = "https://lemma.id",
        timeout_seconds: float = 3.0,
        fail_closed: bool = True,
        max_staleness_seconds: float = 30.0,
        root_type: str = "passkey_root",
    ):
        self.base_url = str(base_url).rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.fail_closed = bool(fail_closed)
        self.max_staleness_seconds = float(max_staleness_seconds)
        self.root_type = str(root_type or "passkey_root")
        self.state = FreshnessState()

    def poll_once(self) -> FreshnessState:
        import time

        now = time.time()
        jwks = _fetch_json(f"{self.base_url}/api/authz/jwks", timeout_seconds=self.timeout_seconds)
        rev = _fetch_json(
            f"{self.base_url}/api/authz/revocation/delta?since={self.state.revocation_cursor}",
            timeout_seconds=self.timeout_seconds,
        )
        policy = _fetch_json(
            f"{self.base_url}/api/authz/policy/snapshot?version={quote(self.state.policy_version or '')}",
            timeout_seconds=self.timeout_seconds,
        )
        if jwks:
            self.state.jwks_last_sync_epoch = now
        if rev:
            self.state.revocation_last_sync_epoch = now
            self.state.revocation_cursor = int(rev.get("next_cursor") or self.state.revocation_cursor)
        if policy:
            self.state.policy_last_sync_epoch = now
            current = policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
            self.state.policy_version = str(current.get("policy_version") or self.state.policy_version or "")
        return self.state

    def assert_fresh_or_raise(self) -> FreshnessState:
        import time

        min_sync = min(
            self.state.jwks_last_sync_epoch or 0,
            self.state.revocation_last_sync_epoch or 0,
            self.state.policy_last_sync_epoch or 0,
        )
        stale = (not min_sync) or ((time.time() - min_sync) > self.max_staleness_seconds)
        if self.fail_closed and stale:
            raise RuntimeError(f"lemma_freshness_stale:{self.root_type}")
        return self.state

