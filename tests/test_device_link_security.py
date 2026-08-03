"""Device-link transfer security, person-root bundles and relay validation."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest

os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-unit-tests")

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"


@pytest.mark.unit
def test_legacy_generate_link_code_removed_from_sdk():
    source = WALLET_JS.read_text(encoding="utf-8")
    assert "generateLinkCode" not in source
    assert "linkDevice(" not in source
    assert "_decryptLinkQR" not in source


@pytest.mark.unit
def test_pull_send_uses_person_root_seeds_only():
    source = WALLET_JS.read_text(encoding="utf-8")
    assert "sealed_wallet_seed" in source
    assert "sealed_person_root_proxy" in source
    assert "sendLinkDepositFromScan" in source
    idx = source.index("async sendLinkDepositFromScan")
    chunk = source[idx:idx + 4000]
    assert "walletSecret: profile.secret" not in chunk
    assert "walletLocalSeed" in chunk


@pytest.mark.unit
def test_push_transfer_uses_offer_register_not_secret_in_url():
    source = WALLET_JS.read_text(encoding="utf-8")
    assert "async beginLinkPush" in source
    assert "async acceptLinkPushOffer" in source
    assert "async confirmLinkPushDeposit" in source
    idx = source.index("async beginLinkPush")
    end = source.index("async getLinkPushStatus", idx)
    chunk = source[idx:end]
    assert "mode: 'push'" in chunk or 'mode: "push"' in chunk
    assert "walletSecret" not in chunk
    assert "confirm_code" in chunk or "confirmCode" in chunk
    # Offer creation should not force a second passkey when already unlocked.
    assert "_requireFreshPasskeyAuth" not in chunk


@pytest.mark.unit
def test_link_completion_defers_signing_key_when_enrollment_grant_pending():
    source = WALLET_JS.read_text(encoding="utf-8")
    idx = source.index("async _completeLinkFromPayload")
    chunk = source[idx:idx + 8000]
    assert "if (!this._pendingEnrollmentGrant)" in chunk
    assert "_registerSigningKeyIfNeeded" in chunk
    assert "device-enroll needs" in chunk or "enrollment grant" in chunk.lower()


@pytest.mark.unit
def test_server_has_no_legacy_link_store_route():
    api_root = ROOT / "api"
    routes_text = "\n".join(p.read_text(encoding="utf-8") for p in api_root.rglob("*.py"))
    assert "/api/wallet/store-link" not in routes_text
    assert "/api/wallet/link-deposit" not in routes_text


@pytest.mark.unit
def test_link_receive_accepts_person_root_bundle(monkeypatch):
    from flask import Flask

    from api import ishuman as ishuman_mod

    app = Flask(__name__)
    app.register_blueprint(ishuman_mod.ishuman_bp)
    store = {}

    monkeypatch.setattr("auth.redis_store.store", lambda key, value, ttl_seconds=300: store.update({key: value}) or True)
    monkeypatch.setattr("auth.redis_store.get", lambda key: store.get(key))
    monkeypatch.setattr("auth.redis_store.delete", lambda key: bool(store.pop(key, None)))
    monkeypatch.setattr(
        ishuman_mod,
        "_require_wallet_assertion",
        lambda body, field_names: (None, body.get("wallet_id")),
    )

    client = app.test_client()
    deposit = client.post(
        "/api/wallet/link-receive",
        json={
            "action": "deposit",
            "wallet_id": "wallet_a",
            "transfer_id": "linkrecv_" + secrets.token_hex(8),
            "recv_pubkey": "AQIDBAUGBwgJCgsMDQ4PEA==",
            "bundle": {
                "sealed_wallet_seed": "c2VlZA==",
                "sealed_person_root_proxy": "cHJveHk=",
            },
            "wallet_assertion": {"nonce": "n", "signature": "s"},
        },
    )
    assert deposit.status_code == 200
    assert deposit.get_json()["success"] is True
