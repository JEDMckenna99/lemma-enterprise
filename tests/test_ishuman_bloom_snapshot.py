from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import pytest
from flask import Flask

from api.wallet_keys import derive_wallet_signing_keypair, pubkey_to_b64url, sign_message


@pytest.fixture(name="revocation_test_app")
def fixture_revocation_test_app():
    from api.revocation_api import revocation_api

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(revocation_api)
    return app


@pytest.fixture(name="revocation_client")
def fixture_revocation_client(revocation_test_app):
    with revocation_test_app.test_client() as client:
        yield client


@pytest.fixture
def bloom_signing_keypair():
    _priv, pub = derive_wallet_signing_keypair("cd" * 32)
    return _priv, pub


@pytest.fixture(autouse=True)
def patch_bloom_issuer_signing(monkeypatch, bloom_signing_keypair):
    """Avoid KMS/federated issuer dependency in unit tests."""
    private_key, public_key = bloom_signing_keypair

    def _material():
        return private_key, public_key, "did:lemma:" + ("a" * 64)

    monkeypatch.setattr("api.bloom_snapshot._issuer_signing_material", _material)


@pytest.mark.unit
def test_compute_content_hash_is_stable():
    from api.bloom_snapshot import compute_content_hash

    ids = ["abc", "def"]
    assert compute_content_hash(ids, 2) == compute_content_hash(ids, 2)
    assert compute_content_hash(ids, 2) != compute_content_hash(["abc"], 1)


@pytest.mark.unit
def test_sign_and_verify_bloom_snapshot_round_trip():
    from api.bloom_snapshot import sign_bloom_snapshot, verify_bloom_snapshot, verify_snapshot_matches_payload

    hashed = ["aa" * 32, "bb" * 32]
    snapshot = sign_bloom_snapshot(hashed_revoked_ids=hashed, sequence_number=42)

    ok, reason = verify_bloom_snapshot(snapshot)
    assert ok, reason
    ok_payload, payload_reason = verify_snapshot_matches_payload(snapshot, hashed_revoked_ids=hashed)
    assert ok_payload, payload_reason
    assert snapshot["sequence_number"] == 42


@pytest.mark.unit
def test_verify_bloom_snapshot_rejects_tampered_signature(bloom_signing_keypair):
    from api.bloom_snapshot import sign_bloom_snapshot, verify_bloom_snapshot

    snapshot = sign_bloom_snapshot(hashed_revoked_ids=["cc" * 32], sequence_number=7)
    snapshot["signature"] = "A" * 86

    ok, reason = verify_bloom_snapshot(snapshot)
    assert not ok
    assert reason == "snapshot_invalid_signature"


@pytest.mark.unit
def test_verify_bloom_snapshot_rejects_stale_snapshot():
    from api.bloom_snapshot import sign_bloom_snapshot, verify_bloom_snapshot

    old = datetime.utcnow() - timedelta(hours=2)
    snapshot = sign_bloom_snapshot(
        hashed_revoked_ids=["dd" * 32],
        sequence_number=3,
        generated_at=old,
    )

    ok, reason = verify_bloom_snapshot(snapshot, now_unix=int(time.time()))
    assert not ok
    assert reason == "snapshot_stale"


@pytest.mark.unit
def test_bloom_filter_endpoint_returns_signed_snapshot(revocation_client, monkeypatch):
    from api import revocation_api as rev_api

    class _Cursor:
        def execute(self, _sql):
            return None

        def fetchall(self):
            return []

        def fetchone(self):
            return (99,)

        def close(self):
            return None

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            return None

    monkeypatch.setattr("api.database.get_db_connection", lambda: _Conn())
    rev_api._BLOOM_CACHE["payload"] = None
    rev_api._BLOOM_CACHE["count"] = None
    rev_api._BLOOM_CACHE["sequence"] = None
    rev_api._BLOOM_CACHE["built_at"] = 0.0

    resp = revocation_client.get("/api/revocation/bloom-filter")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["success"] is True
    assert data["snapshot"]["signature"]
    assert data["sequence_number"] == 99
    from api.bloom_snapshot import verify_bloom_snapshot, verify_snapshot_matches_payload

    ok, reason = verify_bloom_snapshot(data["snapshot"])
    assert ok, reason
    ok_payload, payload_reason = verify_snapshot_matches_payload(
        data["snapshot"],
        hashed_revoked_ids=data["hashed_revoked_ids"],
    )
    assert ok_payload, payload_reason


@pytest.mark.unit
def test_ishuman_verifier_requires_bloom_snapshot_checks():
    sdk_path = __file__.replace("tests\\test_ishuman_bloom_snapshot.py", "static\\js\\ishuman-verifier.js")
    sdk_path = sdk_path.replace("\\", "/")
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "static", "js", "ishuman-verifier.js")
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()

    assert "verifyBloomSnapshot" in content
    assert "revocation_data_untrusted" in content
    assert "snapshot_invalid_signature" in content
    assert "snapshot_stale" in content
    assert "BLOOM_SNAPSHOT_PREFIX" in content
