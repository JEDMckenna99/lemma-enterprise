"""Offline test helpers for integrator CI — no lemma.id or WebAuthn required.

Example::

    from lemma_proof_verifier_testing import (
        create_offline_test_context,
        mint_test_presentation,
    )

    issuer = mint_test_issuer()
    presentation = mint_test_presentation(
        site_id="localhost",
        ppid="did:lemma:ppid_test_user",
        assurance="passkey",
        issuer=issuer,
    )
    ctx = create_offline_test_context(
        site_id="localhost",
        issuer_did=issuer["did"],
        issuer_pubkey_hex=issuer["pubkey_hex"],
        required_assurance="passkey",
    )
    result = ctx.verify(presentation)
    assert result.ok

Set ``TRUSTED_ISSUER_DIDS`` to the returned issuer DID when exercising server
paths that read the env allowlist (see AGENTS.md).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lemma_proof_verifier import TrustedIssuer, VerificationContext, browser_canonical_message

# Fixed dev seed — NOT a production key (matches tests/test_ishuman_end_to_end_mock.py).
DEFAULT_DEV_ISSUER_SEED = b"e2e-dev-issuer-seed-0123456789!!"


def mint_test_issuer(seed: bytes = DEFAULT_DEV_ISSUER_SEED) -> dict[str, str]:
    """Return {did, pubkey_hex, private_key} for a deterministic test issuer."""
    digest = hashlib.sha256(seed).digest()
    private_key = Ed25519PrivateKey.from_private_bytes(digest)
    pubkey_hex = private_key.public_key().public_bytes_raw().hex()
    did = f"did:lemma:test:{pubkey_hex[:16]}"
    return {"did": did, "pubkey_hex": pubkey_hex, "private_key": private_key}


def _sign_credential(credential: dict, private_key: Ed25519PrivateKey) -> str:
    message = browser_canonical_message(credential)
    digest = hashlib.sha256(message).digest()
    return private_key.sign(digest).hex()


def mint_test_credential(
    *,
    site_id: str,
    ppid: str,
    assurance: str = "passkey",
    issuer: Optional[dict[str, Any]] = None,
    credential_id: Optional[str] = None,
) -> dict:
    """Mint a signed site credential for offline verifier tests."""
    issuer = issuer or mint_test_issuer()
    now = int(time.time())
    cred_id = credential_id or f"ishuman_test_{secrets.token_hex(8)}"
    claims = {
        "assurance": assurance,
        "siteId": site_id,
        "issuedAt": str(now),
        "expiresAt": str(now + 86400 * 30),
        "packageType": "identity",
        "verificationMethod": "passkey" if assurance == "passkey" else "stripe_identity",
    }
    if assurance == "ishuman":
        claims["isHuman"] = True
    body = {
        "id": cred_id,
        "issuer": issuer["did"],
        "subject": ppid,
        "claims": claims,
        "credentialSubject": dict(claims),
    }
    signature_hex = _sign_credential(body, issuer["private_key"])
    credential = {
        **body,
        "issuerInfo": {"did": issuer["did"], "publicKey": issuer["pubkey_hex"]},
        "proof": {
            "type": "Ed25519Signature2020",
            "verificationMethod": issuer["did"],
            "signatureValueWeb": signature_hex,
        },
    }
    return credential


def mint_test_presentation(
    *,
    site_id: str,
    ppid: str,
    assurance: str = "passkey",
    issuer: Optional[dict[str, Any]] = None,
) -> dict:
    """Return a minimal presentation bundle suitable for ``VerificationContext.verify``."""
    credential = mint_test_credential(
        site_id=site_id,
        ppid=ppid,
        assurance=assurance,
        issuer=issuer,
    )
    return {
        "siteId": site_id,
        "credential": credential,
    }


class OfflineTestVerificationContext(VerificationContext):
    """VerificationContext that trusts one issuer and skips lemma.id HTTP fetches."""

    def __init__(
        self,
        *,
        trusted_issuer_did: str,
        trusted_pubkey_hex: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._offline_issuer_did = trusted_issuer_did.strip()
        self._offline_pubkey_hex = trusted_pubkey_hex.strip().lower()

    def _fetch_signed_bundle(self):
        from lemma_proof_verifier import _Snapshot

        now = time.time()
        issuers = {
            self._offline_issuer_did: TrustedIssuer(
                did=self._offline_issuer_did,
                pubkeys_hex={self._offline_pubkey_hex},
            )
        }
        return _Snapshot(
            sequence_number=1,
            revoked_hash_set=set(),
            valid_until_unix=int(now) + 86400,
            fetched_at_unix=now,
            max_staleness_seconds=86400,
            issuers=issuers,
        )


def create_offline_test_context(
    *,
    site_id: str,
    issuer_did: str,
    issuer_pubkey_hex: str,
    required_assurance: str = "passkey",
) -> OfflineTestVerificationContext:
    """Build a verifier that never contacts lemma.id."""
    return OfflineTestVerificationContext(
        site_id=site_id,
        trusted_issuer_did=issuer_did,
        trusted_pubkey_hex=issuer_pubkey_hex,
        required_assurance=required_assurance,
    )
