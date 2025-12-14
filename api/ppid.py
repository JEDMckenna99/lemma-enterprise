"""
PPID (Pairwise Pseudonymous Identifier) utilities
=================================================

Implements pairwise subject identifiers for Lemma credentials:

    subject = did:lemma:ppid_<HMAC(master_user_secret, rp_id)>

For the current IAM/email rollout (pre-PoH), we derive `master_user_secret`
deterministically from email + a server-side root key so that:
- The same user gets a stable master secret across devices
- Each relying party (rp_id) gets a different subject (pairwise)

Later, PoH can replace `derive_master_user_secret_from_email()` with RID-based
derivation (or wallet-held master secrets) without changing the PPID format.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from urllib.parse import urlparse


def _get_root_ppid_key() -> bytes:
    """
    Root secret used to derive per-user master secrets.

    In production, set `LEMMA_PPID_ROOT_KEY` to a high-entropy secret (32+ bytes),
    stored in your platform secret manager (e.g., Heroku config vars / KMS).
    """
    key = os.environ.get("LEMMA_PPID_ROOT_KEY")
    if key and len(key) >= 32:
        return key.encode("utf-8")
    # Development fallback only (NOT for production)
    return b"lemma_dev_ppid_root_key_change_me_32bytes_min"


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def canonicalize_rp_id(rp_id: str) -> str:
    """
    Canonicalize relying party identifier.

    Accepts domain or URL. Returns a stable lowercase host string.
    """
    rp_id = (rp_id or "").strip().lower()
    if not rp_id:
        return "unknown"

    # If a URL is passed, normalize to hostname
    if "://" in rp_id:
        parsed = urlparse(rp_id)
        if parsed.hostname:
            return parsed.hostname.lower()

    # Strip path if someone passed "example.com/path"
    return rp_id.split("/")[0]


def derive_master_user_secret_from_email(email: str) -> bytes:
    """
    Deterministically derive a per-user master secret from email.
    master_user_secret = HMAC(root_key, normalize(email))
    """
    email_norm = normalize_email(email)
    root_key = _get_root_ppid_key()
    return hmac.new(root_key, email_norm.encode("utf-8"), hashlib.sha256).digest()


def derive_ppid_did(email: str, rp_id: str) -> str:
    """
    Derive pairwise subject DID for a user at a relying party.
    """
    rp = canonicalize_rp_id(rp_id)
    master = derive_master_user_secret_from_email(email)
    ppid = hmac.new(master, rp.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"did:lemma:ppid_{ppid}"


