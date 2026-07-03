"""Live one-PPID assurance flow on staging.

Requires:
  LEMMA_STAGING_BASE_URL
  LEMMA_STAGING_DEMO_TEST_TOKEN
  Staging flags: LEMMA_ONE_PPID_ASSURANCE_MODEL=1, LEMMA_PASSKEY_ASSURANCE_ENABLED=1
"""
from __future__ import annotations

import hashlib
import os
import secrets

import pytest

requests = pytest.importorskip("requests")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

from api.ishuman import _browser_canonical_message  # noqa: E402
from api.wallet_keys import b64url_encode, build_wallet_assertion, register_self_signature  # noqa: E402

pytestmark = pytest.mark.live


def _require_env() -> tuple[str, str]:
    base = os.getenv("LEMMA_STAGING_BASE_URL")
    token = os.getenv("LEMMA_STAGING_DEMO_TEST_TOKEN")
    if not base or not token:
        pytest.skip("requires LEMMA_STAGING_BASE_URL and LEMMA_STAGING_DEMO_TEST_TOKEN")
    return base.rstrip("/"), token


def _verify_browser_sig(credential: dict) -> None:
    pub = bytes.fromhex(credential["issuerInfo"]["publicKey"])
    sig = bytes.fromhex(credential["proof"]["signatureValueWeb"])
    digest = hashlib.sha256(_browser_canonical_message(credential)).digest()
    Ed25519PublicKey.from_public_bytes(pub).verify(sig, digest)


def _challenge(session, base: str, wallet_id: str) -> str:
    return session.post(f"{base}/api/wallet/challenge", json={"wallet_id": wallet_id}).json()["nonce"]


def _derive_passkey_site_proof(session, base: str, wallet_id: str, wallet_secret: str, target_site: str, site_pub_b64: str):
    fields = ["target_site", "site_signing_pubkey", "issue_mode"]
    fvals = {
        "target_site": target_site,
        "site_signing_pubkey": site_pub_b64,
        "issue_mode": "site_proof",
    }
    assertion = build_wallet_assertion(
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        field_names=fields,
        field_values=fvals,
        nonce_b64=_challenge(session, base, wallet_id),
    )
    return session.post(
        f"{base}/api/ishuman/derive-site-proof",
        json={
            **fvals,
            "wallet_id": wallet_id,
            "wallet_assertion": {"nonce": assertion.nonce, "signature": assertion.signature},
        },
    )


def test_live_staging_passkey_then_ishuman_same_ppid():
    base, token = _require_env()
    wallet_id = "wallet_one_ppid_" + secrets.token_hex(5)
    wallet_secret = "cd" * 32
    target_site = f"one-ppid-e2e-{secrets.token_hex(4)}.example.com"
    session = requests.Session()

    pub_b64, sig_b64 = register_self_signature(wallet_id, wallet_secret)
    reg = session.post(
        f"{base}/api/wallet/register-signing-key",
        json={"wallet_id": wallet_id, "pubkey": pub_b64, "signature": sig_b64},
    )
    assert reg.ok and reg.json().get("success"), reg.text

    site_priv = Ed25519PrivateKey.generate()
    site_pub_b64 = b64url_encode(site_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

    passkey_resp = _derive_passkey_site_proof(session, base, wallet_id, wallet_secret, target_site, site_pub_b64)
    payload = passkey_resp.json()
    assert passkey_resp.ok and payload.get("success"), payload
    passkey_cred = payload["credential"]
    _verify_browser_sig(passkey_cred)
    passkey_ppid = passkey_cred["subject"]
    passkey_claims = passkey_cred.get("claims") or {}
    assert passkey_claims.get("assurance") == "passkey"
    assert passkey_claims.get("isHuman") in (False, "false", None)
    assert passkey_claims.get("ppidDerivation") == "person_root_v1"

    return_url = f"{base}/demo/ishuman"
    start_assertion = build_wallet_assertion(
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        field_names=["return_url"],
        field_values={"return_url": return_url},
        nonce_b64=_challenge(session, base, wallet_id),
    )
    idv = session.post(
        f"{base}/api/demo/ishuman/verify-once-test-mode",
        headers={"X-Demo-Test-Token": token},
        json={
            "wallet_id": wallet_id,
            "wallet_secret": wallet_secret,
            "return_url": return_url,
            "wallet_assertion": {"nonce": start_assertion.nonce, "signature": start_assertion.signature},
        },
    )
    assert idv.ok and idv.json().get("success"), idv.text
    master = idv.json()
    _verify_browser_sig(master["credential"])

    fields = ["master_credential_id", "target_site", "site_signing_pubkey", "issue_mode"]
    fvals = {
        "master_credential_id": master["credential_id"],
        "target_site": target_site,
        "site_signing_pubkey": site_pub_b64,
        "issue_mode": "site_proof",
    }
    assertion = build_wallet_assertion(
        wallet_id=wallet_id,
        wallet_secret=wallet_secret,
        field_names=fields,
        field_values=fvals,
        nonce_b64=_challenge(session, base, wallet_id),
    )
    ishuman_resp = session.post(
        f"{base}/api/ishuman/derive-site-proof",
        json={
            **fvals,
            "wallet_id": wallet_id,
            "wallet_assertion": {"nonce": assertion.nonce, "signature": assertion.signature},
        },
    )
    ishuman_payload = ishuman_resp.json()
    assert ishuman_resp.ok and ishuman_payload.get("success"), ishuman_payload
    ishuman_cred = ishuman_payload["credential"]
    _verify_browser_sig(ishuman_cred)
    ishuman_claims = ishuman_cred.get("claims") or {}
    assert ishuman_claims.get("assurance") in ("ishuman", None)
    assert ishuman_claims.get("isHuman") in (True, "true")
    assert ishuman_cred["subject"] == passkey_ppid
