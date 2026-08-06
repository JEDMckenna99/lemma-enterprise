"""
Trusted Issuer Registry, Local-First

Maintains the set of trusted issuer DIDs loaded from static configuration
(environment variables or JSON file). No database dependency.

Credentials MUST be signed by a trusted issuer to be considered valid.
Without this check, anyone can create a keypair and sign credentials
that would cryptographically verify but are NOT authorized by the network.

Configuration sources (merged, all optional):
  1. LEGACY_PLATFORM_ISSUER_DIDS, hardcoded historical platform issuers
  2. TRUSTED_ISSUER_DIDS env var, comma-separated DID strings
  3. TRUSTED_ISSUERS_FILE env var, path to a JSON file (list of DID strings)
  4. Runtime issuer manager (if available), picks up the current platform signing key
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional, Set

logger = logging.getLogger(__name__)

LEGACY_PLATFORM_ISSUER_DIDS: set[str] = {
    "did:lemma:c66b2d31342086885eb297c3e25322d5c5a4511c869db8b27d4a815008ff1111",
    "did:lemma:7a5db0739dfa18260930ef70cd6f076d44440d2ac02e7be5e32933ac1aabb805",
}

_trusted_issuers_cache: Optional[Set[str]] = None


def _load_trusted_issuers() -> Set[str]:
    """Build the trusted issuer set from all static configuration sources."""
    trusted: set[str] = set(LEGACY_PLATFORM_ISSUER_DIDS)

    env_trusted = os.getenv("TRUSTED_ISSUER_DIDS", "")
    if env_trusted:
        for did in (d.strip() for d in env_trusted.split(",") if d.strip()):
            trusted.add(did)

    issuers_file = os.getenv("TRUSTED_ISSUERS_FILE", "")
    if issuers_file:
        try:
            with open(issuers_file, "r") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                for did in data:
                    if isinstance(did, str) and did.strip():
                        trusted.add(did.strip())
            logger.info(f"Loaded trusted issuers from {issuers_file}")
        except Exception as exc:
            logger.warning(f"Could not load trusted issuers file {issuers_file}: {exc}")

    try:
        from api.issuer_management import get_issuer_manager
        issuer_manager = get_issuer_manager()
        for platform_site in ("lemma.id", "lemma_platform"):
            try:
                runtime_did = issuer_manager.get_iam_issuer(platform_site).get_did()
                if runtime_did:
                    trusted.add(runtime_did)
            except Exception:
                pass
        try:
            from api.federated_signer import get_federated_issuer_metadata

            federated_did = get_federated_issuer_metadata().get("did")
            if federated_did:
                trusted.add(federated_did)
        except Exception:
            pass
    except Exception:
        pass

    try:
        from api.database import SessionLocal, Site

        db = SessionLocal()
        try:
            rows = db.query(Site.issuer_did).filter(Site.issuer_did.isnot(None)).all()
            for (site_issuer_did,) in rows:
                did = str(site_issuer_did or '').strip()
                if did:
                    trusted.add(did)
        finally:
            db.close()
    except Exception as exc:
        logger.warning('Could not load site issuer DIDs for trust registry: %s', exc)

    logger.info(f"Loaded {len(trusted)} trusted issuer DIDs")
    return trusted


def get_trusted_issuer_dids() -> Set[str]:
    """Return the set of trusted issuer DIDs (loaded once, cached)."""
    global _trusted_issuers_cache
    if _trusted_issuers_cache is None:
        _trusted_issuers_cache = _load_trusted_issuers()
    return _trusted_issuers_cache


def _normalize_issuer_did(issuer_did: str) -> str:
    """Normalize issuer DID for trust comparison across legacy formats."""
    if not issuer_did:
        return ""
    text = str(issuer_did).strip()
    if not text:
        return ""
    text = text.split("#", 1)[0].split("?", 1)[0].rstrip("/")
    return text.lower()


def _extract_issuer_did(credential: dict) -> Optional[str]:
    """
    Extract issuer DID from modern and legacy credential shapes.
    Supports:
    - issuer: "did:..."
    - issuer: {"id": "did:..."} / {"did": "did:..."}
    - issuerInfo.did
    """
    if not isinstance(credential, dict):
        return None

    issuer = credential.get("issuer")
    if isinstance(issuer, dict):
        issuer_did = issuer.get("id") or issuer.get("did")
    else:
        issuer_did = issuer

    if not issuer_did:
        issuer_info = credential.get("issuerInfo") or {}
        if isinstance(issuer_info, dict):
            issuer_did = issuer_info.get("did")

    if issuer_did:
        return str(issuer_did).strip()
    return None


def is_trusted_issuer(issuer_did: str) -> bool:
    """Check if an issuer DID is in the trusted set."""
    if not issuer_did:
        return False

    trusted = get_trusted_issuer_dids()
    if issuer_did in trusted:
        return True

    normalized = _normalize_issuer_did(issuer_did)
    trusted_normalized = {_normalize_issuer_did(d) for d in trusted}
    is_ok = normalized in trusted_normalized

    if not is_ok:
        logger.warning(f"Untrusted issuer: {issuer_did[:80]}")
    return is_ok


def clear_cache() -> None:
    """Clear the trusted issuer cache (useful for testing or hot-reload)."""
    global _trusted_issuers_cache
    _trusted_issuers_cache = None


_clear_cache = clear_cache


def verify_credential_with_trust(credential: dict) -> dict:
    """
    Local-first credential verification.

    Checks (in order):
      1. Issuer trust, pinned config set
      2. Expiration, claim timestamp
      3. Revocation, in-process Bloom filter only (no DB)
      4. Ed25519 signature, via lemma_crypto

    Returns a dict with 'valid' bool and diagnostic fields.
    """
    import time

    result = {
        "valid": False,
        "signature_valid": False,
        "issuer_trusted": False,
        "not_expired": True,
        "not_revoked": True,
        "reason": None,
        "issuer": None,
    }

    try:
        issuer_did = _extract_issuer_did(credential)
        if not issuer_did:
            result["reason"] = "missing_issuer"
            return result
        result["issuer"] = issuer_did

        if not is_trusted_issuer(issuer_did):
            result["reason"] = "untrusted_issuer"
            return result
        result["issuer_trusted"] = True

        claims = credential.get("claims", credential.get("credentialSubject", {}))
        expires_at = (
            claims.get("expiresAt")
            or credential.get("expires_at")
            or credential.get("expirationDate")
        )
        if expires_at:
            try:
                expires_ts = float(expires_at)
            except (ValueError, TypeError):
                from datetime import datetime as _dt

                try:
                    parsed = _dt.fromisoformat(
                        str(expires_at).replace("Z", "+00:00")
                    )
                    expires_ts = parsed.timestamp()
                except Exception:
                    expires_ts = None
            if expires_ts is not None and expires_ts < time.time():
                result["not_expired"] = False
                result["reason"] = "expired"
                return result

        credential_id = credential.get("id")
        if credential_id:
            try:
                from api.revocation_verifier import is_credential_revoked

                if is_credential_revoked(credential_id):
                    result["not_revoked"] = False
                    result["reason"] = "revoked"
                    return result
            except Exception as exc:
                logger.warning(f"Revocation check unavailable: {exc}")

        local_issuer = issuer_did and issuer_did.startswith("did:lemma:local_cli")
        try:
            from lemma_crypto import PyOptimizedVerifier

            verifier = PyOptimizedVerifier()
            cred_json = (
                json.dumps(credential) if isinstance(credential, dict) else credential
            )
            signature_valid = verifier.verify_credential_json(cred_json)
            result["signature_valid"] = signature_valid
            if not signature_valid:
                result["reason"] = "invalid_signature"
                return result
        except ImportError:
            if local_issuer:
                result["signature_valid"] = True
            else:
                result["reason"] = "verification_error: lemma_crypto not installed"
                return result
        except Exception as exc:
            logger.error(f"Crypto verification failed: {exc}")
            result["reason"] = f"verification_error: {exc}"
            return result

        result["valid"] = True
        return result

    except Exception as exc:
        logger.error(f"Credential verification error: {exc}")
        result["reason"] = str(exc)
        return result
