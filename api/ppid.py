"""
PPID (Pairwise Pseudonymous Identifier) utilities
=================================================

Implements pairwise subject identifiers for Lemma credentials:

    subject = did:lemma:ppid_<HMAC(master_user_secret, rp_id)>

WALLET-FIRST APPROACH:
- The master_user_secret is derived from the wallet's secret (stored in wallet)
- OR from the passkey credential_id (for server-side derivation)
- Each relying party (site) gets a DIFFERENT subject (pairwise unlinkability)
- The SAME user at the SAME site gets the SAME subject (account continuity)

PRIVACY PROPERTIES:
- Site A sees: did:lemma:ppid_abc123...
- Site B sees: did:lemma:ppid_def456...  
- Sites CANNOT correlate these are the same user
"""

from __future__ import annotations

import hashlib
import hmac
import os
from urllib.parse import urlparse


def _get_root_ppid_key() -> bytes:
    """
    Root secret used to derive per-user master secrets.
    In production, this MUST be set to a high-entropy secret (32+ bytes).
    """
    try:
        from .config import get_ppid_root_key
        return get_ppid_root_key().encode("utf-8")
    except Exception:
        # Fallback for standalone usage or testing
        key = os.environ.get("LEMMA_PPID_ROOT_KEY")
        if key and len(key) >= 32:
            return key.encode("utf-8")
        # Development fallback only (NOT for production)
        return b"lemma_dev_ppid_root_key_change_me_32bytes_min"


def canonicalize_rp_id(rp_id: str) -> str:
    """
    Canonicalize relying party identifier.
    Accepts domain or URL. Returns a stable lowercase host string.
    Aligns with client ``canonicalizeSiteDomain`` (strip www, port, path).
    """
    rp_id = (rp_id or "").strip().lower()
    if not rp_id:
        return "unknown"

    # If a URL is passed, normalize to hostname
    if "://" in rp_id:
        parsed = urlparse(rp_id)
        if parsed.hostname:
            rp_id = parsed.hostname.lower()
        else:
            rp_id = rp_id.split("://", 1)[-1]

    # Strip path if someone passed "example.com/path"
    host = rp_id.split("/")[0]
    # Strip port
    if ":" in host and not host.startswith("["):
        host = host.rsplit(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown"


# =============================================================================
# WALLET-FIRST: Derive from wallet secret or passkey
# =============================================================================

def derive_master_secret_from_wallet_secret(wallet_secret: str) -> bytes:
    """
    Derive master_user_secret from wallet-held secret.
    
    The wallet generates a random secret on creation and stores it encrypted.
    This secret is the root of all PPID derivations for that wallet.
    
    Args:
        wallet_secret: The wallet's master secret (hex string, 32+ bytes)
    """
    root_key = _get_root_ppid_key()
    secret_bytes = bytes.fromhex(wallet_secret) if len(wallet_secret) == 64 else wallet_secret.encode()
    return hmac.new(root_key, secret_bytes, hashlib.sha256).digest()


def derive_master_secret_from_passkey(passkey_credential_id: str) -> bytes:
    """
    Derive master_user_secret from passkey credential ID.
    
    Used for server-side PPID derivation when wallet secret is not available.
    The passkey credential_id is stable per device/passkey.
    
    Args:
        passkey_credential_id: Base64-encoded WebAuthn credential ID
    """
    root_key = _get_root_ppid_key()
    return hmac.new(root_key, passkey_credential_id.encode("utf-8"), hashlib.sha256).digest()


def derive_ppid_from_person_root(person_root: bytes, rp_id: str) -> str:
    """Derive site PPID from stable Lemma person root (post Stripe IDV)."""
    from api.identity_roots import derive_ppid_from_person_root_bytes

    return derive_ppid_from_person_root_bytes(person_root, rp_id)


def derive_ppid_from_person_root_hash(person_root_hash_hex: str, rp_id: str) -> str:
    """Derive PPID from stored person_root_hash (64 hex chars)."""
    return derive_ppid_from_person_root(bytes.fromhex(person_root_hash_hex), rp_id)


def derive_ppid_from_wallet_secret(wallet_secret: str, rp_id: str) -> str:
    """
    Derive PPID for a user at a relying party using wallet secret.
    
    Legacy wallet-first authentication (pre person-root isHuman).
    
    Args:
        wallet_secret: The wallet's master secret
        rp_id: Site domain/identifier
        
    Returns:
        Pairwise subject DID: did:lemma:ppid_<hash>
    """
    rp = canonicalize_rp_id(rp_id)
    master = derive_master_secret_from_wallet_secret(wallet_secret)
    ppid = hmac.new(master, rp.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"did:lemma:ppid_{ppid}"


def derive_ppid_from_passkey(passkey_credential_id: str, rp_id: str) -> str:
    """
    Derive PPID for a user at a relying party using passkey credential ID.
    
    Used when server needs to derive PPID without wallet secret.
    
    Args:
        passkey_credential_id: WebAuthn credential ID
        rp_id: Site domain/identifier
        
    Returns:
        Pairwise subject DID: did:lemma:ppid_<hash>
    """
    rp = canonicalize_rp_id(rp_id)
    master = derive_master_secret_from_passkey(passkey_credential_id)
    ppid = hmac.new(master, rp.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"did:lemma:ppid_{ppid}"


# =============================================================================
# LEGACY: Email-based derivation (for backwards compatibility)
# =============================================================================

def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def derive_master_user_secret_from_email(email: str) -> bytes:
    """
    LEGACY: Derive master_user_secret from email.
    
    Used for backwards compatibility with email-based flows.
    For new wallet-first flows, use derive_master_secret_from_wallet_secret().
    """
    email_norm = normalize_email(email)
    root_key = _get_root_ppid_key()
    return hmac.new(root_key, email_norm.encode("utf-8"), hashlib.sha256).digest()


def derive_ppid_did(email: str, rp_id: str) -> str:
    """
    LEGACY: Derive PPID from email (backwards compatibility).
    
    For new wallet-first flows, use derive_ppid_from_wallet_secret().
    """
    rp = canonicalize_rp_id(rp_id)
    master = derive_master_user_secret_from_email(email)
    ppid = hmac.new(master, rp.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"did:lemma:ppid_{ppid}"


