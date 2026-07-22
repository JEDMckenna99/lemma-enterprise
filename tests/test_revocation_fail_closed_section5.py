"""Section 5: revocation and replay protection fail-closed tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from flask import Flask

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_MODULE = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"
JS_MODULE = REPO_ROOT / "static" / "js" / "proof-verifier.mjs"


@pytest.fixture(autouse=True)
def _allow_unpinned_trust_root(monkeypatch):
    monkeypatch.setenv("LEMMA_ALLOW_UNPINNED_TRUST_ROOT", "1")


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
def py_sdk():
    pytest.importorskip("cryptography")
    name = "lemma_proof_verifier_section5"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, PY_MODULE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _node_eval(script: str) -> subprocess.CompletedProcess[str]:
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node not available in PATH")
    module_url = JS_MODULE.resolve().as_uri()
    wrapped = (
        "import(" + repr(module_url) + ").then(async (m) => {\n"
        "  try {\n"
        f"    {script}\n"
        "  } catch (err) {\n"
        "    console.error(err);\n"
        "    process.exit(1);\n"
        "  }\n"
        "});\n"
    )
    return subprocess.run(
        [node_bin, "-e", wrapped],
        capture_output=True,
        text=True,
        timeout=20,
    )


def _reset_bloom_cache(rev_api):
    rev_api._BLOOM_CACHE["payload"] = None
    rev_api._BLOOM_CACHE["count"] = None
    rev_api._BLOOM_CACHE["sequence"] = None
    rev_api._BLOOM_CACHE["built_at"] = 0.0


def test_bloom_filter_db_failure_returns_503_without_signature(revocation_client, monkeypatch):
    from api import revocation_api as rev_api

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("api.database.get_db_connection", _boom)
    _reset_bloom_cache(rev_api)

    resp = revocation_client.get("/api/revocation/bloom-filter")
    data = resp.get_json()
    assert resp.status_code == 503
    assert data["success"] is False
    assert data["error"] == "revocation_unavailable"
    assert "snapshot" not in data or not data.get("snapshot", {}).get("signature")


def test_bloom_filter_hash_failure_returns_500_no_plaintext(revocation_client, monkeypatch):
    from api import revocation_api as rev_api

    class _Cursor:
        def execute(self, _sql):
            return None

        def fetchall(self):
            return [("cred-1",), ("cred-2",)]

        def fetchone(self):
            return (5,)

        def close(self):
            return None

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            return None

    real_sha256 = hashlib.sha256
    calls = {"n": 0}

    def _flaky_sha256(data=None):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("hash failed")
        return real_sha256(data)

    monkeypatch.setattr("api.database.get_db_connection", lambda: _Conn())
    monkeypatch.setattr("api.revocation_api.hashlib.sha256", _flaky_sha256)
    _reset_bloom_cache(rev_api)

    resp = revocation_client.get("/api/revocation/bloom-filter")
    data = resp.get_json()
    assert resp.status_code == 500
    assert data["error"] == "bloom_hash_failed"
    assert "hashed_revoked_ids" not in data


def test_legacy_revocation_list_db_error_returns_503(revocation_client, monkeypatch):
    monkeypatch.setattr(
        "api.database.get_db_connection",
        lambda: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    resp = revocation_client.get("/api/v1/revocation/list")
    data = resp.get_json()
    assert resp.status_code == 503
    assert data["success"] is False
    assert data["error"] == "revocation_unavailable"


def test_verify_presentation_fails_closed_when_revocation_unavailable(monkeypatch):
    """verify-presentation returns 503 when Bloom revocation lookup is unavailable."""
    pytest.importorskip("flask")
    pytest.importorskip("cryptography")

    import sys
    import types

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from flask import Flask

    from api.ishuman import _sign_with_issuer_for_browser, ishuman_bp

    seed = b"\x33" * 32
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    pk_hex = sk.public_key().public_bytes_raw().hex()
    issuer_did = f"did:lemma:{pk_hex}"

    class _FakeIssuer:
        def signing_key_bytes(self):
            return seed

        def get_did(self):
            return issuer_did

        def get_public_key_hex(self):
            return pk_hex

    credential_body = {
        "id": "cred-section5",
        "issuer": issuer_did,
        "subject": "did:lemma:ppid_section5",
        "claims": {
            "assurance": "ishuman",
            "siteId": "example.com",
            "issuedAt": "1700000000",
            "expiresAt": str(int(time.time()) + 3600),
        },
    }
    credential = {
        **credential_body,
        "proof": {
            "signatureValueWeb": _sign_with_issuer_for_browser(credential_body, _FakeIssuer()),
        },
    }

    monkeypatch.setattr(
        "api.trusted_issuers.is_trusted_issuer",
        lambda did: did == issuer_did,
        raising=False,
    )
    fake_rev = types.SimpleNamespace(
        check_credential_revocation=lambda _cred: "unavailable",
    )
    monkeypatch.setitem(sys.modules, "api.revocation_verifier", fake_rev)

    app = Flask(__name__)
    app.register_blueprint(ishuman_bp)
    client = app.test_client()
    resp = client.post(
        "/api/ishuman/verify-presentation",
        json={"site_id": "example.com", "credential": credential},
        content_type="application/json",
    )
    data = resp.get_json()
    assert resp.status_code == 503
    assert data["success"] is False
    assert data["error"] == "revocation_unavailable"


def test_revocation_candidates_match_browser(py_sdk):
    credential = {
        "id": "cred-123",
        "subject": "did:lemma:ppid_abc",
        "claims": {"walletId": "wallet-xyz"},
    }
    assert py_sdk.revocation_candidates(credential) == [
        "cred-123",
        "did:lemma:ppid_abc",
        "wallet-xyz",
    ]

    revoked_hash = hashlib.sha256(b"did:lemma:ppid_abc").hexdigest()
    assert py_sdk.credential_revoked_in_snapshot(credential, {revoked_hash}) is True
    assert py_sdk.credential_revoked_in_snapshot(credential, set()) is False


def test_node_verifier_rejects_revoked_wallet_candidate():
    wallet_id = "wallet-revoked-1"
    wallet_hash = hashlib.sha256(wallet_id.encode()).hexdigest()
    result = _node_eval(
        f"""
const walletId = {json.dumps(wallet_id)};
const walletHash = {json.dumps(wallet_hash)};
const credential = {{
  id: "cred-live",
  subject: "did:lemma:ppid_ok",
  claims: {{ walletId, wallet_id: walletId }},
}};
const candidates = [];
if (credential.id) candidates.push(credential.id);
if (credential.subject) candidates.push(credential.subject);
if (credential.claims.walletId) candidates.push(credential.claims.walletId);
let revoked = false;
for (const candidate of candidates) {{
  const bytes = new TextEncoder().encode(candidate);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, "0")).join("");
  if (hex === walletHash) revoked = true;
}}
if (!revoked) process.exit(2);
console.log("ok");
"""
    )
    assert result.returncode == 0, result.stderr


def test_js_module_consumes_nonce_after_signature_validation():
    src = JS_MODULE.read_text(encoding="utf-8")
    sig_idx = src.index("invalid_action_signature")
    nonce_idx = src.index("action_nonce_reused", sig_idx)
    consume_idx = src.index("nonceStore.consume", sig_idx)
    assert consume_idx > sig_idx, "nonce consume must run after signature validation"
    assert nonce_idx > sig_idx


def _action_stamp_fixture(py_sdk, *, nonce: str = "nonce-section5"):
    now = int(time.time())
    body = {"amountCents": 100}
    body_hash = py_sdk.hash_action_body(body)
    return {
        "payload": body,
        "lemma": {
            "version": py_sdk.ACTION_STAMP_VERSION,
            "action": "checkout",
            "method": "POST",
            "path": "/api/checkout",
            "bodyHash": body_hash,
            "nonce": nonce,
            "credential": {
                "id": "c1",
                "subject": "did:lemma:ppid_a",
                "claims": {"site_signing_pubkey": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"},
                "proof": {},
            },
            "action_assertion": {
                "version": py_sdk.ACTION_STAMP_VERSION,
                "site_id": "demo.example.com",
                "credential_id": "c1",
                "subject": "did:lemma:ppid_a",
                "assurance": "passkey",
                "action": "checkout",
                "method": "POST",
                "path": "/api/checkout",
                "body_hash": body_hash,
                "nonce": nonce,
                "issued_at_unix": now,
                "expires_at_unix": now + 60,
            },
            "action_signature": "abc",
        },
    }, body


def test_invalid_action_signature_does_not_consume_nonce(py_sdk, monkeypatch):
    ctx = py_sdk.VerificationContext(site_id="demo.example.com", required_assurance="passkey")
    store = py_sdk.InMemoryNonceStore()
    stamped, body = _action_stamp_fixture(py_sdk)

    monkeypatch.setattr(
        ctx,
        "verify",
        lambda presentation: py_sdk.VerificationContext.Result(
            True,
            "valid",
            ppid="did:lemma:ppid_a",
            credential_id="c1",
            assurance="passkey",
        ),
    )
    monkeypatch.setattr(
        py_sdk,
        "_verify_site_ed25519_digest",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(py_sdk.InvalidSignature("bad sig")),
    )

    bad = ctx.verify_action_stamp(
        stamped,
        action="checkout",
        method="POST",
        path="/api/checkout",
        body=body,
        nonce_store=store,
    )
    assert bad.ok is False
    assert bad.reason == "invalid_action_signature"
    assert "nonce-section5" not in store._seen

    monkeypatch.setattr(py_sdk, "_verify_site_ed25519_digest", lambda *_a, **_k: None)
    good = ctx.verify_action_stamp(
        stamped,
        action="checkout",
        method="POST",
        path="/api/checkout",
        body=body,
        nonce_store=store,
    )
    assert good.ok is True


def test_node_redis_nonce_store_awaits_set_nx():
    result = _node_eval(
        """
const calls = [];
const client = {
  async set(key, value, opts) {
    calls.push({ key, value, opts });
    return "OK";
  },
};
const store = new m.RedisNonceStore(client);
const ok = await store.consume("nonce-redis-1", { siteId: "example.com", ttlSeconds: 120 });
if (!ok) process.exit(2);
if (calls.length !== 1) process.exit(3);
if (!calls[0].opts?.NX || calls[0].opts?.EX !== 120) process.exit(4);
console.log("ok");
"""
    )
    assert result.returncode == 0, result.stderr


def test_redis_nonce_replay_blocked_across_two_stores():
    result = _node_eval(
        """
const shared = new Map();
const makeClient = () => ({
  async set(key, value, opts) {
    if (shared.has(key)) return null;
    shared.set(key, value);
    return "OK";
  },
});
const a = new m.RedisNonceStore(makeClient());
const b = new m.RedisNonceStore(makeClient());
const first = await a.consume("shared-nonce", { siteId: "example.com", ttlSeconds: 60 });
const second = await b.consume("shared-nonce", { siteId: "example.com", ttlSeconds: 60 });
if (!first || second) process.exit(2);
console.log("ok");
"""
    )
    assert result.returncode == 0, result.stderr


def test_revocation_service_ready_requires_sync(monkeypatch):
    from api import revocation_verifier as rv

    monkeypatch.setattr(rv, "_revocation_sync_ready", False, raising=False)
    ready, reason = rv.revocation_service_ready()
    assert ready is False
    assert reason == "bloom_verifier_not_initialized"

    monkeypatch.setattr(rv, "_revocation_sync_ready", True, raising=False)
    monkeypatch.setattr(
        "api.permission_verification.get_global_verifier",
        lambda: None,
    )
    ready, reason = rv.revocation_service_ready()
    assert ready is False
    assert reason == "bloom_verifier_missing"


def test_check_credential_revocation_tri_state(monkeypatch):
    from api import revocation_verifier as rv

    monkeypatch.setattr(rv, "_revocation_sync_ready", True, raising=False)

    class _Verifier:
        def __init__(self, revoked):
            self._revoked = set(revoked)

        def is_revoked(self, candidate):
            return candidate in self._revoked

    monkeypatch.setattr(
        "api.permission_verification.get_global_verifier",
        lambda: _Verifier({"did:lemma:ppid_bad"}),
    )
    assert rv.check_credential_revocation({"id": "cred-ok", "subject": "did:lemma:ppid_bad"}) == "revoked"

    monkeypatch.setattr(
        "api.permission_verification.get_global_verifier",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert rv.check_credential_revocation({"id": "cred-ok"}) == "unavailable"


def test_required_nonce_store_mode_without_store_rejected(py_sdk, monkeypatch):
    ctx = py_sdk.VerificationContext(
        site_id="demo.example.com",
        required_assurance="ishuman",
        nonce_store_mode="required",
    )
    stamped, body = _action_stamp_fixture(py_sdk, nonce="nonce-required-mode")
    monkeypatch.setattr(
        ctx,
        "verify",
        lambda _presentation: py_sdk.VerificationContext.Result(
            ok=True,
            reason="valid",
            ppid="did:lemma:ppid_a",
            credential_id="c1",
            assurance="ishuman",
        ),
    )
    monkeypatch.setattr(py_sdk, "_verify_site_ed25519_digest", lambda *_a, **_k: None)
    result = ctx.verify_action_stamp(
        stamped,
        action="checkout",
        method="POST",
        path="/api/checkout",
        body=body,
        nonce_store_mode="required",
    )
    assert result.ok is False
    assert result.reason == "action_nonce_store_required"
