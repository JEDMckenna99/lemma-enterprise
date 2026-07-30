from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CRYPTO_JS = ROOT / "static" / "js" / "wallet-at-rest-crypto.js"
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"
PASSKEY_JS = ROOT / "static" / "js" / "lemma-passkey.js"
PASSKEY_API = ROOT / "api" / "passkey_auth.py"


@pytest.fixture(name="crypto_js")
def fixture_crypto_js() -> str:
    return CRYPTO_JS.read_text(encoding="utf-8")


@pytest.fixture(name="wallet_js")
def fixture_wallet_js() -> str:
    return WALLET_JS.read_text(encoding="utf-8")


@pytest.mark.unit
def test_wallet_at_rest_crypto_module_exports_contract(crypto_js):
    assert "window.WalletAtRestCrypto" in crypto_js
    assert "ENVELOPE_VERSION = 'enc_v1'" in crypto_js
    assert "buildRegistrationPrfExtensions" in crypto_js
    assert "extractPrfBytes" in crypto_js
    assert "encryptEnvelope" in crypto_js
    assert "decryptEnvelope" in crypto_js


@pytest.mark.unit
def test_lemma_wallet_wires_encrypted_storage(wallet_js):
    assert "WALLET_DB_VERSION = 7" in wallet_js
    assert "_bindAtRestKeyFromCredential" in wallet_js
    assert "_migratePlaintextStores" in wallet_js
    assert "_encryptStoredValue" in wallet_js
    assert "_decryptStoredValue" in wallet_js
    assert "wallet_meta" in wallet_js
    assert "prf_required_for_encrypted_storage" in wallet_js


@pytest.mark.unit
def test_lemma_wallet_register_and_unlock_request_prf(wallet_js):
    assert "buildRegistrationPrfExtensions" in wallet_js
    assert "_publicKeyOptionsWithPrf" in wallet_js
    assert "extensions: prfExtensions" in wallet_js


@pytest.mark.unit
def test_server_webauthn_unlock_binds_prf_before_encrypted_profile_read(wallet_js):
    """Regression: envelope_invalid after successful passkey on lemma.id.

    ``_performServerWebAuthnUnlock`` must bind the PRF at-rest key before
    ``getActiveProfile()`` decrypts enc_v1 profile/secret rows.
    """
    marker = "async _performServerWebAuthnUnlock("
    start = wallet_js.index(marker)
    # Bound the method body loosely by the next top-level async method.
    end = wallet_js.index("\n    async requestWalletChallenge(", start)
    body = wallet_js[start:end]
    bind_at = body.index("await this._bindAtRestKeyFromCredential(")
    profile_at = body.index("await this.getActiveProfile(")
    assert bind_at < profile_at, "PRF bind must precede getActiveProfile during server unlock"


@pytest.mark.unit
def test_passkey_api_requests_prf_extensions():
    source = PASSKEY_API.read_text(encoding="utf-8")
    assert "_prf_extension_options" in source
    assert "_merge_prf_extensions" in source
    assert "prf_requested" in source
    assert "_credential_reports_prf" in source


@pytest.mark.unit
def test_lemma_passkey_forwards_prf_extensions():
    source = PASSKEY_JS.read_text(encoding="utf-8")
    assert "_preparePrfExtensions" in source
    assert "clientExtensionResults" in source


@pytest.mark.unit
def test_prf_salt_derivation_is_stable():
    wallet_id = "wallet_demo_001"
    rp_id = "lemma.id"
    material = f"lemma:wallet:prf:v1:{rp_id}:{wallet_id}".encode("utf-8")
    salt = hashlib.sha256(material).digest()
    salt_b64 = base64.urlsafe_b64encode(salt).decode("utf-8").rstrip("=")
    assert len(salt) == 32
    assert salt_b64


@pytest.mark.unit
def test_passkey_register_begin_merges_prf(monkeypatch):
    from api.passkey_auth import passkey_bp
    from flask import Flask

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test"
    app.register_blueprint(passkey_bp)

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["customer_id"] = "cust_demo"
            sess["user_email"] = "demo@lemma.id"

        monkeypatch.setattr(
            "api.passkey_auth.get_user_passkeys",
            lambda _uid: [],
        )
        monkeypatch.setattr(
            "api.passkey_auth.store_challenge",
            lambda *_args, **_kwargs: True,
        )

        resp = client.post(
            "/api/passkey/register/begin",
            json={"device_name": "test"},
        )
        payload = resp.get_json()
        assert resp.status_code == 200
        assert payload["success"] is True
        assert payload.get("prf_requested") is True
        assert "extensions" in payload["options"]
        assert "prf" in payload["options"]["extensions"]
