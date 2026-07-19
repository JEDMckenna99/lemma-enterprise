"""Live end-to-end isHuman flow against a STAGING deployment, using the demo
test-mode IDV rail (no Stripe document) but the real deployed server, DB, KMS
issuer, and person-root derivation.

Exercises over HTTP: register signing key -> mock IDV (issues a real master
credential) -> wallet challenge -> derive per-site proof -> verify both
credentials' Ed25519 signatures locally -> confirm deterministic re-derive.

Requires (skips otherwise):
  * LEMMA_STAGING_BASE_URL          e.g. https://lemma-staging-xxxx.herokuapp.com
  * LEMMA_STAGING_DEMO_TEST_TOKEN   matches LEMMA_ISHUMAN_DEMO_TEST_TOKEN on the app

The target app must run with ENVIRONMENT=staging (so _demo_enabled() is true),
LEMMA_ISHUMAN_DEMO_ALLOW_TEST_VERIFY=true, and a Stripe sk_test_ key.
"""
from __future__ import annotations

import hashlib
import os
import secrets

import pytest

requests = pytest.importorskip("requests")

from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

from api.ishuman import _browser_canonical_message  # noqa: E402
from api.wallet_keys import (  # noqa: E402
    b64url_encode,
    build_wallet_assertion,
)
from tests.live.live_test_helpers import (  # noqa: E402
    require_staging_env,
    wallet_challenge,
)

pytestmark = pytest.mark.live


def _verify_browser_sig(credential: dict) -> None:
    pub = bytes.fromhex(credential["issuerInfo"]["publicKey"])
    sig = bytes.fromhex(credential["proof"]["signatureValueWeb"])
    digest = hashlib.sha256(_browser_canonical_message(credential)).digest()
    Ed25519PublicKey.from_public_bytes(pub).verify(sig, digest)


def test_live_staging_mock_idv_end_to_end():
    base, token = require_staging_env()
    wallet_id = "wallet_live_e2e_" + secrets.token_hex(5)
    wallet_secret = "ab" * 32
    s = requests.Session()

    # 1. Register the wallet signing key via staging test enrollment grant.
    from tests.live.live_test_helpers import register_wallet_signing_key

    register_wallet_signing_key(s, base, wallet_id, wallet_secret)

    # 2. Mock IDV -> real master credential (start-verification needs a START assertion).
    return_url = f"{base}/demo/ishuman"
    start_assertion = build_wallet_assertion(
        wallet_id=wallet_id, wallet_secret=wallet_secret,
        field_names=["return_url"], field_values={"return_url": return_url},
        nonce_b64=wallet_challenge(s, base, wallet_id),
    )
    idv = s.post(f"{base}/api/demo/ishuman/verify-once-test-mode",
                 headers={"X-Demo-Test-Token": token},
                 json={"wallet_id": wallet_id, "wallet_secret": wallet_secret,
                       "return_url": return_url,
                       "wallet_assertion": {"nonce": start_assertion.nonce,
                                            "signature": start_assertion.signature}})
    assert idv.ok and idv.json().get("success"), idv.text
    master = idv.json()
    master_id = master["credential_id"]
    master_ppid = master["ppid"]
    _verify_browser_sig(master["credential"])

    # 3. Server reflects a verified master.
    status = s.get(f"{base}/api/demo/ishuman/status", params={"wallet_id": wallet_id}).json()
    assert (status.get("master") or {}).get("status") == "verified"

    # 4. Derive a per-site proof via the real derive endpoint (wallet-assertion auth).
    site_priv = Ed25519PrivateKey.generate()
    site_pub_b64 = b64url_encode(
        site_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    )
    target_site = "tickets-demo.lemma.id"
    fields = ["master_credential_id", "target_site", "site_signing_pubkey", "issue_mode"]
    fvals = {"master_credential_id": master_id, "target_site": target_site,
             "site_signing_pubkey": site_pub_b64, "issue_mode": "site_proof"}

    def _derive():
        assertion = build_wallet_assertion(
            wallet_id=wallet_id, wallet_secret=wallet_secret,
            field_names=fields, field_values=fvals, nonce_b64=wallet_challenge(s, base, wallet_id),
        )
        return s.post(f"{base}/api/ishuman/derive-site-proof",
                      json={**fvals, "wallet_id": wallet_id,
                            "wallet_assertion": {"nonce": assertion.nonce,
                                                 "signature": assertion.signature}})

    d1 = _derive()
    assert d1.ok and d1.json().get("success"), d1.text
    site_cred = d1.json()["credential"]
    _verify_browser_sig(site_cred)
    site_ppid = site_cred["subject"]
    assert site_ppid and site_ppid != master_ppid  # pairwise unlinkable

    # 5. Re-derive is deterministic.
    d2 = _derive()
    assert d2.ok and d2.json()["credential"]["subject"] == site_ppid
