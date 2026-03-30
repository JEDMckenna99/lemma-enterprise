"""
Canonical revocation verification — Bloom filter only.

All runtime revocation checks route through this module.
Verification uses the in-process Bloom filter populated by
api.revocation_sync (Redis pub/sub from the revocation_list table).

No database query is made at verification time.
"""

from __future__ import annotations

from typing import Optional
import logging

logger = logging.getLogger(__name__)


def is_credential_revoked(credential_id: Optional[str]) -> bool:
    """
    Check whether a credential has been revoked using the in-process
    Bloom filter (populated via revocation_sync pub/sub).

    Returns False (not revoked) if the Bloom verifier is not yet
    initialized — this is a documented fail-open choice so that
    startup ordering does not block all requests.
    """
    if not credential_id:
        return False

    try:
        from api.permission_verification import get_global_verifier

        verifier = get_global_verifier()
        if verifier and verifier.is_revoked(credential_id):
            return True
    except Exception as exc:
        logger.debug(f"Bloom revocation check unavailable for {credential_id}: {exc}")

    return False
