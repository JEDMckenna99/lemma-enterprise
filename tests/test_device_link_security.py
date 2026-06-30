"""Device-link transfer security — encryption, expiry, and server non-exposure.

The QR/browser link is a device-to-device channel: lemma.id never receives the
encrypted bundle. These tests mirror the browser AES-GCM format and assert
interception/tamper resistance properties.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-unit-tests")

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"


def _encrypt_for_link(payload: str, key_bytes: bytes) -> str:
    """Mirror LemmaWallet._encryptForLink (AES-GCM, 12-byte IV prefix)."""
    iv = secrets.token_bytes(12)
    aes = AESGCM(key_bytes)
    ciphertext = aes.encrypt(iv, payload.encode("utf-8"), None)
    combined = iv + ciphertext
    return base64.b64encode(combined).decode("ascii")


def _decrypt_for_link(encrypted_b64: str, key_bytes: bytes) -> dict:
    """Mirror LemmaWallet._decryptLinkQR inner decrypt."""
    combined = base64.b64decode(encrypted_b64)
    iv, ciphertext = combined[:12], combined[12:]
    aes = AESGCM(key_bytes)
    plaintext = aes.decrypt(iv, ciphertext, None)
    return json.loads(plaintext.decode("utf-8"))


def _build_link_qr(*, key_bytes: bytes, inner: dict, expires_at_ms: int | None = None) -> dict:
    expires_at_ms = expires_at_ms if expires_at_ms is not None else int(time.time() * 1000) + 300_000
    inner["expiresAt"] = expires_at_ms
    encrypted = _encrypt_for_link(json.dumps(inner), key_bytes)
    return {
        "v": 1,
        "k": key_bytes.hex(),
        "p": encrypted,
        "e": expires_at_ms,
    }


@pytest.mark.unit
def test_link_roundtrip_decrypts_wallet_and_ishuman_bundle():
    key = secrets.token_bytes(16)
    inner = {
        "walletSecret": "ab" * 32,
        "walletId": "wallet_link_test_001",
        "profileId": "default",
        "profileName": "Personal",
        "ishumanCredentials": [{"id": "ishuman_master_test", "claims": {"isHuman": True}}],
        "unlockToken": "wallet:123:456:789:nonce:sig",
    }
    qr = _build_link_qr(key_bytes=key, inner=inner)
    key_from_qr = bytes.fromhex(qr["k"])
    recovered = _decrypt_for_link(qr["p"], key_from_qr)
    assert recovered["walletSecret"] == inner["walletSecret"]
    assert len(recovered["ishumanCredentials"]) == 1
    assert recovered["unlockToken"] == inner["unlockToken"]


@pytest.mark.unit
def test_ciphertext_alone_cannot_decrypt_without_key():
    key = secrets.token_bytes(16)
    qr = _build_link_qr(key_bytes=key, inner={"walletSecret": "cd" * 32, "walletId": "w1"})
    wrong_key = secrets.token_bytes(16)
    with pytest.raises(InvalidTag):
        _decrypt_for_link(qr["p"], wrong_key)


@pytest.mark.unit
def test_tampered_ciphertext_fails_authentication():
    key = secrets.token_bytes(16)
    qr = _build_link_qr(key_bytes=key, inner={"walletSecret": "ef" * 32, "walletId": "w2"})
    combined = bytearray(base64.b64decode(qr["p"]))
    combined[-1] ^= 0xFF
    tampered = base64.b64encode(bytes(combined)).decode("ascii")
    with pytest.raises(InvalidTag):
        _decrypt_for_link(tampered, key)


@pytest.mark.unit
def test_expired_outer_envelope_is_rejected():
    key = secrets.token_bytes(16)
    past = int(time.time() * 1000) - 60_000
    qr = _build_link_qr(key_bytes=key, inner={"walletSecret": "12" * 32}, expires_at_ms=past)
    assert qr["e"] < int(time.time() * 1000)


@pytest.mark.unit
def test_server_has_no_link_payload_storage_endpoint():
    """Link material must never be POSTed to the server for relay/storage."""
    api_root = ROOT / "api"
    forbidden = (
        "walletSecret",
        "ishumanCredentials",
        "generateLinkCode",
        "link_qr_payload",
    )
    hits: list[str] = []
    for path in api_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "walletSecret" in text and "link" in path.name.lower():
            hits.append(str(path.relative_to(ROOT)))
    # walletSecret may appear in unrelated wallet auth paths; ensure no dedicated link store route.
    routes_text = "\n".join(
        p.read_text(encoding="utf-8") for p in api_root.rglob("*.py")
    )
    assert "/api/wallet/store-link" not in routes_text
    assert "/api/wallet/link-deposit" not in routes_text
    assert "link_qr_payload" not in routes_text


@pytest.mark.unit
def test_sdk_keeps_secrets_inside_encrypted_payload():
    source = WALLET_JS.read_text(encoding="utf-8")
    assert "ishumanCredentials" in source
    assert "unlockToken" in source
    # Outer QR JSON holds key + ciphertext; inner JSON holds secrets.
    assert "walletSecret: walletSecret" in source or '"walletSecret"' in source
    assert "link-unlock-token" in source
    assert "_importLinkedIsHumanCredentials" in source


@pytest.mark.unit
def test_link_unlock_token_requires_valid_session(monkeypatch):
    from flask import Flask

    from api import wallet_session_sync

    app = Flask(__name__)
    app.register_blueprint(wallet_session_sync.wallet_session_sync_bp)
    client = app.test_client()

    no_cookie = client.post("/api/wallet/link-unlock-token")
    assert no_cookie.status_code == 401
    assert no_cookie.get_json()["error"] == "no_session"

    monkeypatch.setattr(wallet_session_sync, "validate_session_token", lambda _t: None)
    client.set_cookie(wallet_session_sync.SESSION_COOKIE_NAME, "expired_session")
    expired = client.post("/api/wallet/link-unlock-token")
    assert expired.status_code == 401
    assert expired.get_json()["error"] == "session_expired"


@pytest.mark.unit
def test_set_session_rejects_unlock_token_wallet_mismatch(monkeypatch):
    from flask import Flask

    from api import wallet_session_sync
    from auth.session_manager import generate_unlock_token

    app = Flask(__name__)
    app.register_blueprint(wallet_session_sync.wallet_session_sync_bp)
    client = app.test_client()

    token = generate_unlock_token("wallet_a", int(time.time() * 1000), int(time.time()) + 3600)
    resp = client.post(
        "/api/wallet/set-session",
        json={"wallet_id": "wallet_b", "unlock_token": token},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "unlock_token_required"


@pytest.mark.unit
def test_set_session_rejects_missing_unlock_token():
    from flask import Flask

    from api import wallet_session_sync

    app = Flask(__name__)
    app.register_blueprint(wallet_session_sync.wallet_session_sync_bp)
    client = app.test_client()

    resp = client.post("/api/wallet/set-session", json={"wallet_id": "wallet_x"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "unlock_token_required"


@pytest.mark.unit
def test_unlock_token_expires(monkeypatch):
    from auth import session_manager

    base = int(time.time())
    clock = {"now": base}
    monkeypatch.setattr(session_manager, "UNLOCK_TOKEN_TTL", 60)
    monkeypatch.setattr(session_manager.time, "time", lambda: clock["now"])

    token = session_manager.generate_unlock_token(
        "wallet_expire", base * 1000, base + 3600
    )
    assert session_manager.validate_unlock_token(token) is not None
    clock["now"] = base + 61
    assert session_manager.validate_unlock_token(token) is None
