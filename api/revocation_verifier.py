"""
Canonical revocation verification, Bloom filter only.

All runtime revocation checks route through this module.
Verification uses the in-process Bloom filter populated by
api.revocation_sync (Redis pub/sub from the revocation_list table).

No database query is made at verification time.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
import logging
import os
import time

logger = logging.getLogger(__name__)

RevocationStatus = Literal["ok", "revoked", "unavailable"]

_revocation_sync_ready = False
_revocation_last_sync_epoch: float | None = None


def _revocation_freshness_max_seconds() -> int:
    raw = os.getenv("LEMMA_REVOCATION_FRESHNESS_MAX_SECONDS", "86400").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 86400


def mark_revocation_sync_ready() -> None:
    global _revocation_sync_ready, _revocation_last_sync_epoch
    _revocation_sync_ready = True
    _revocation_last_sync_epoch = time.time()


def revocation_service_ready() -> tuple[bool, str]:
    """Return whether the in-process Bloom verifier finished initial sync."""
    ready, detail = revocation_freshness_status()
    if ready:
        return True, "ok"
    return False, str(detail.get("reason") or "bloom_verifier_unavailable")


def revocation_freshness_status() -> tuple[bool, dict[str, Any]]:
    """Return bloom initialization and freshness for readiness probes."""
    max_age = _revocation_freshness_max_seconds()
    if not _revocation_sync_ready:
        return False, {
            "ok": False,
            "reason": "bloom_verifier_not_initialized",
            "max_age_seconds": max_age,
        }
    try:
        from api.permission_verification import get_global_verifier

        verifier = get_global_verifier()
        if not verifier:
            return False, {
                "ok": False,
                "reason": "bloom_verifier_missing",
                "max_age_seconds": max_age,
            }
    except Exception as exc:
        logger.warning("Revocation readiness check failed: %s", exc)
        return False, {
            "ok": False,
            "reason": "bloom_verifier_unavailable",
            "error": str(exc),
            "max_age_seconds": max_age,
        }

    age_seconds = None
    if _revocation_last_sync_epoch is not None:
        age_seconds = max(0.0, time.time() - _revocation_last_sync_epoch)
    if age_seconds is not None and age_seconds > max_age:
        return False, {
            "ok": False,
            "reason": "bloom_snapshot_stale",
            "age_seconds": round(age_seconds, 1),
            "max_age_seconds": max_age,
        }
    return True, {
        "ok": True,
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "max_age_seconds": max_age,
    }


def revocation_candidates(credential: dict) -> list[str]:
    """Identifiers checked against the global revocation bloom (matches Browser SDK)."""
    claims = credential.get("claims") or credential.get("credentialSubject") or {}
    out: list[str] = []
    credential_id = str(credential.get("id") or "").strip()
    if credential_id:
        out.append(credential_id)
    subject = str(credential.get("subject") or "").strip()
    if subject:
        out.append(subject)
    wallet_id = str(claims.get("walletId") or claims.get("wallet_id") or "").strip()
    if wallet_id:
        out.append(wallet_id)
    return out


def check_revocation_candidate(candidate: Optional[str]) -> RevocationStatus:
    """Tri-state revocation lookup for a single identifier."""
    if not candidate:
        return "ok"
    if not _revocation_sync_ready:
        return "unavailable"
    try:
        from api.permission_verification import get_global_verifier

        verifier = get_global_verifier()
        if not verifier:
            return "unavailable"
        if verifier.is_revoked(str(candidate)):
            return "revoked"
        return "ok"
    except Exception as exc:
        logger.warning("Bloom revocation check unavailable for %s: %s", candidate, exc)
        return "unavailable"


def check_credential_revocation(credential: dict) -> RevocationStatus:
    """Check credential id, subject/PPID, and wallet id against the Bloom verifier."""
    worst: RevocationStatus = "ok"
    for candidate in revocation_candidates(credential):
        status = check_revocation_candidate(candidate)
        if status == "revoked":
            return "revoked"
        if status == "unavailable":
            worst = "unavailable"
    return worst


def is_credential_revoked(credential_id: Optional[str]) -> bool:
    """Return True only when definitively revoked (backward-compatible boolean API)."""
    return check_revocation_candidate(credential_id) == "revoked"
