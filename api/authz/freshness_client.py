from __future__ import annotations

# pylint: disable=broad-exception-caught,global-statement

import json
import os
import threading
import time
from dataclasses import dataclass
from urllib import request as urllib_request


@dataclass
class FreshnessState:
    jwks_last_sync_epoch: float | None = None
    revocation_last_sync_epoch: float | None = None
    policy_last_sync_epoch: float | None = None
    revocation_cursor: int = 0
    policy_version: str | None = None


_STATE = FreshnessState()
_STATE_LOCK = threading.Lock()
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def get_freshness_state() -> FreshnessState:
    with _STATE_LOCK:
        return FreshnessState(
            jwks_last_sync_epoch=_STATE.jwks_last_sync_epoch,
            revocation_last_sync_epoch=_STATE.revocation_last_sync_epoch,
            policy_last_sync_epoch=_STATE.policy_last_sync_epoch,
            revocation_cursor=_STATE.revocation_cursor,
            policy_version=_STATE.policy_version,
        )


def _fetch_json(url: str, timeout_seconds: float) -> dict | None:
    req = urllib_request.Request(url, method="GET")
    with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:  # nosec B310
        payload = resp.read().decode("utf-8")
    data = json.loads(payload)
    return data if isinstance(data, dict) else None


def _poll_once(base_url: str, timeout_seconds: float) -> None:
    now = time.time()
    with _STATE_LOCK:
        cursor = _STATE.revocation_cursor
        policy_version = _STATE.policy_version or ""
    try:
        _fetch_json(f"{base_url}/api/authz/jwks", timeout_seconds=timeout_seconds)
        with _STATE_LOCK:
            _STATE.jwks_last_sync_epoch = now
    except Exception:
        pass

    try:
        rev = _fetch_json(
            f"{base_url}/api/authz/revocation/delta?since={cursor}",
            timeout_seconds=timeout_seconds,
        )
        if rev:
            with _STATE_LOCK:
                _STATE.revocation_last_sync_epoch = now
                _STATE.revocation_cursor = int(rev.get("next_cursor") or cursor)
    except Exception:
        pass

    try:
        snap = _fetch_json(
            f"{base_url}/api/authz/policy/snapshot?version={policy_version}",
            timeout_seconds=timeout_seconds,
        )
        if snap:
            policy = snap.get("policy") or {}
            with _STATE_LOCK:
                _STATE.policy_last_sync_epoch = now
                _STATE.policy_version = str(policy.get("policy_version") or policy_version or "")
    except Exception:
        pass


def start_background_freshness_client() -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True

    base_url = str(os.getenv("LEMMA_AUTHZ_CONTROL_PLANE_BASE_URL") or "https://lemma.id").rstrip("/")
    poll_seconds = max(5, int(str(os.getenv("LEMMA_AUTHZ_FRESHNESS_POLL_SECONDS") or "30")))
    timeout_seconds = max(1.0, float(str(os.getenv("LEMMA_AUTHZ_FRESHNESS_TIMEOUT_SECONDS") or "3")))

    def _worker() -> None:
        while True:
            _poll_once(base_url=base_url, timeout_seconds=timeout_seconds)
            time.sleep(poll_seconds)

    thread = threading.Thread(target=_worker, daemon=True, name="lemma-authz-freshness")
    thread.start()

