"""
Domain ownership verification for site registration and transfers.

Reuses DNS TXT and /.well-known verification patterns from issuer registry.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_VERIFICATION_TTL_MINUTES = 60


def mint_domain_verification_token(domain: str) -> str:
    """Create a one-time verification token for a canonical hostname."""
    canonical = (domain or "").strip().lower()
    seed = f"{canonical}:{secrets.token_urlsafe(24)}:{datetime.utcnow().isoformat()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def get_verification_instructions(domain: str, token: str) -> Dict[str, Any]:
    """Return DNS and well-known verification instructions."""
    from api.issuer_registry import get_verification_instructions

    return get_verification_instructions(domain, token)


def verify_domain_ownership(
    domain: str,
    token: str,
    method: str = "well-known",
) -> bool:
    """Verify domain ownership via DNS TXT or /.well-known file."""
    canonical = (domain or "").strip().lower()
    expected = (token or "").strip()
    if not canonical or not expected:
        return False

    normalized_method = (method or "well-known").strip().lower()
    from api.issuer_registry import verify_dns, verify_well_known

    if normalized_method == "dns":
        return bool(verify_dns(canonical, expected))
    return bool(verify_well_known(canonical, expected))


def store_domain_verification_challenge(
    db,
    *,
    domain: str,
    token: str,
    customer_id: str,
    actor_ppid: str,
    purpose: str = "site_registration",
) -> None:
    """Persist a pending verification challenge (best-effort when table exists)."""
    try:
        from api.database import DomainVerificationChallenge

        expires_at = datetime.utcnow() + timedelta(minutes=_VERIFICATION_TTL_MINUTES)
        row = DomainVerificationChallenge(
            domain=domain,
            token=token,
            customer_id=customer_id,
            actor_ppid=actor_ppid,
            purpose=purpose,
            expires_at=expires_at,
            verified=False,
        )
        db.add(row)
        db.commit()
    except Exception as exc:
        logger.debug("Could not persist domain verification challenge: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


def consume_verified_domain_proof(
    domain: str,
    token: str,
    method: str,
) -> bool:
    """Verify domain proof for registration/transfer."""
    return verify_domain_ownership(domain, token, method)
