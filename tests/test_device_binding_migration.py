"""Tests for device-binding migration controls (PoP signatures, enforce env, reissue 2FA)."""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-unit-tests")


@pytest.mark.unit
def test_pop_signature_required_rejects_unsigned(monkeypatch):
    from api.authz.replay import validate_pop_replay

    monkeypatch.setenv("LEMMA_POP_SIGNATURE_REQUIRED", "1")
    headers = {
        "X-Lemma-Proof": json.dumps({"proof_id": "p1"}),
        "X-Lemma-PoP": json.dumps(
            {
                "nonce": "n1",
                "proof_id": "p1",
                "iat": 1,
                "exp": 9999999999,
                "method": "GET",
                "path": "/api/test",
                "body_hash": "",
                "aud": "lemma.id",
            }
        ),
    }
    decision = validate_pop_replay(
        headers=headers,
        method="GET",
        path="/api/test",
        required=True,
    )
    assert decision.valid is False
    assert decision.reason == "missing_signature"


@pytest.mark.unit
def test_mode_policy_agent_bypass_disabled_when_enforced(monkeypatch):
    from api.authz.mode_policy import evaluate_mode_policy

    monkeypatch.setenv("LEMMA_ENFORCE_PROOF_REQUIRED", "1")
    decision = evaluate_mode_policy(
        expected_mode="proof_required",
        headers={"X-Agent-Token": "lm_agent_test"},
    )
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_PROOF_REQUIRED"


@pytest.mark.unit
def test_reissue_requires_second_factor_when_other_devices_exist(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from flask import Flask

    from api import ishuman as ishuman_mod
    from api.database import IsHumanVerification, WalletSigningKey
    from api.wallet_authn import register_wallet_signing_key
    from api.wallet_keys import register_self_signature

    monkeypatch.setattr("api.database.SessionLocal", fake_ishuman_db_session_factory.session_local)
    monkeypatch.setattr(ishuman_mod, "_require_wallet_assertion", lambda body, field_names: (None, body.get("wallet_id")))
    monkeypatch.setattr("api.rate_limiter.check_rate_limit", lambda *args, **kwargs: True)
    monkeypatch.setattr(ishuman_mod, "_issue_ishuman_credential", lambda *args, **kwargs: {"id": "ishuman_master_new"})
    monkeypatch.setattr(ishuman_mod, "_master_credential_ttl_seconds", lambda *args, **kwargs: 3600)
    monkeypatch.setattr("api.bloom_snapshot.invalidate_bloom_filter_cache", lambda: None)

    wallet_id = "wallet_reissue_2fa"
    for device_id in ("legacy", "dev_other"):
        pubkey_b64, sig_b64 = register_self_signature(wallet_id, "ab" * 32 if device_id == "legacy" else "cd" * 32)
        assert register_wallet_signing_key(
            wallet_id=wallet_id,
            device_id=device_id,
            pubkey_b64=pubkey_b64,
            signature_b64=sig_b64,
        ).ok

    db = fake_ishuman_db_session_factory.session_local()
    db.add(
        IsHumanVerification(
            wallet_id=wallet_id,
            status="verified",
            ppid="did:lemma:ppid_test",
            credential_id="ishuman_master_old",
        )
    )
    db.commit()
    db.close()

    app = Flask(__name__)
    app.register_blueprint(ishuman_mod.ishuman_bp)
    client = app.test_client()
    resp = client.post(
        "/api/ishuman/reissue-master",
        json={
            "wallet_id": wallet_id,
            "device_id": "legacy",
            "wallet_assertion": {"nonce": "n", "signature": "s", "device_id": "legacy"},
        },
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "second_factor_required"
