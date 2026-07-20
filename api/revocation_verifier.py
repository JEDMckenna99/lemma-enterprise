"""
Canonical revocation verification, Bloom filter only.

All runtime revocation checks route through this module.
Verification uses the in-process Bloom filter populated by
api.revocation_sync (Redis pub/sub from the revocation_list table).

No database query is made at verification time.
"""

from __future__ import annotations

from typing import Literal, Optional
import logging

logger = logging.getLogger(__name__)

RevocationStatus = Literal["ok", "revoked", "unavailable"]

_revocation_sync_ready = False


def mark_revocation_sync_ready() -> None:
    global _revocation_sync_ready
    _revocation_sync_ready = True


def revocation_service_ready() -> tuple[bool, str]:
    """Return whether the in-process Bloom verifier finished initial sync."""
    if not _revocation_sync_ready:
        return False, "bloom_verifier_not_initialized"
    try:
        from api.permission_verification import get_global_verifier

        verifier = get_global_verifier()
        if not verifier:
            return False, "bloom_verifier_missing"
        return True, "ok"
    except Exception as exc:
        logger.warning("Revocation readiness check failed: %s", exc)
        return False, "bloom_verifier_unavailable"


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
