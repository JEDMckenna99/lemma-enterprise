"""Wave 4 security containment regression tests."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import socket
import sys
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("SESSION_SECRET", "containment-wave4-session-secret")
os.environ.setdefault("LEMMA_ACCESS_TOKEN_SECRET", "containment-wave4-access-token-secret")

PPID = (
    "did:lemma:ppid_abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
)
ISSUER_A = "did:lemma:issuer:platform"
ISSUER_B = "did:lemma:issuer:federated-other"


def _load_py_sdk():
    pytest.importorskip("cryptography")
    name = "lemma_proof_verifier_wave4"
    if name in sys.modules:
        return sys.modules[name]
    path = REPO_ROOT / "packages" / "proof-verifier-py" / "lemma_proof_verifier.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _sign_digest(seed: bytes, digest: bytes) -> str:
    return Ed25519PrivateKey.from_private_bytes(seed).sign(digest).hex()


def _pubkey_hex(seed: bytes) -> str:
    return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw().hex()


def test_fresh_passkey_rejects_foreign_trusted_issuer_key():
    mod = _load_py_sdk()
    seed_a = b"a" * 32
    seed_b = b"b" * 32
    now = int(time.time())
    artifact = {
        "schema": mod.FRESH_PASSKEY_SCHEMA,
        "issuer": ISSUER_A,
        "attestation_id": "fpa_test",
        "site_id": "app.example.com",
        "credential_id": "cred_1",
        "subject": PPID,
        "action_commitment": "aa" * 32,
        "issued_at_unix": now,
        "expires_at_unix": now + 60,
    }
    digest = hashlib.sha256(
        mod.build_fresh_passkey_canonical_message(artifact, include_issuer=True)
    ).digest()
    # Signed by issuer B's key while claiming issuer A.
    artifact["proof"] = {"signatureValueWeb": _sign_digest(seed_b, digest)}

    TrustedIssuer = mod.TrustedIssuer
    trusted = {
        ISSUER_A: TrustedIssuer(did=ISSUER_A, pubkeys_hex={_pubkey_hex(seed_a)}),
        ISSUER_B: TrustedIssuer(did=ISSUER_B, pubkeys_hex={_pubkey_hex(seed_b)}),
    }
    ok, reason = mod.verify_fresh_passkey_attestation(
        artifact,
        site_id="app.example.com",
        credential_id="cred_1",
        subject=PPID,
        action_commitment="aa" * 32,
        trusted_issuers=trusted,
    )
    assert ok is False
    assert reason == "fresh_passkey_invalid_signature"

    # Correct issuer key accepts.
    artifact["proof"] = {"signatureValueWeb": _sign_digest(seed_a, digest)}
    ok, reason = mod.verify_fresh_passkey_attestation(
        artifact,
        site_id="app.example.com",
        credential_id="cred_1",
        subject=PPID,
        action_commitment="aa" * 32,
        trusted_issuers=trusted,
        expected_issuer_did=ISSUER_A,
    )
    assert ok is True
    assert reason == "valid"


def test_fresh_passkey_rejects_issuer_mismatch_with_credential():
    mod = _load_py_sdk()
    seed_a = b"c" * 32
    now = int(time.time())
    artifact = {
        "schema": mod.FRESH_PASSKEY_SCHEMA,
        "issuer": ISSUER_B,
        "attestation_id": "fpa_test2",
        "site_id": "app.example.com",
        "credential_id": "cred_1",
        "subject": PPID,
        "action_commitment": "bb" * 32,
        "issued_at_unix": now,
        "expires_at_unix": now + 60,
    }
    digest = hashlib.sha256(
        mod.build_fresh_passkey_canonical_message(artifact, include_issuer=True)
    ).digest()
    artifact["proof"] = {"signatureValueWeb": _sign_digest(seed_a, digest)}
    trusted = {
        ISSUER_B: mod.TrustedIssuer(did=ISSUER_B, pubkeys_hex={_pubkey_hex(seed_a)}),
    }
    ok, reason = mod.verify_fresh_passkey_attestation(
        artifact,
        site_id="app.example.com",
        credential_id="cred_1",
        subject=PPID,
        action_commitment="bb" * 32,
        trusted_issuers=trusted,
        expected_issuer_did=ISSUER_A,
    )
    assert ok is False
    assert reason == "fresh_passkey_issuer_mismatch"


def test_convergence_rejects_foreign_trusted_issuer_key():
    mod = _load_py_sdk()
    seed_a = b"d" * 32
    seed_b = b"e" * 32
    now = int(time.time())
    artifact = {
        "schema": mod.CONVERGENCE_SCHEMA,
        "issuer": ISSUER_A,
        "convergence_id": "conv_1",
        "site_id": "app.example.com",
        "legacy_ppid": PPID.replace("abcdef", "000000"),
        "canonical_ppid": PPID,
        "nonce": "n1",
        "issued_at_unix": now,
        "expires_at_unix": now + 3600,
    }
    digest = hashlib.sha256(
        mod.build_convergence_canonical_message(artifact, include_issuer=True)
    ).digest()
    artifact["proof"] = {"signatureValueWeb": _sign_digest(seed_b, digest)}
    trusted = {
        ISSUER_A: mod.TrustedIssuer(did=ISSUER_A, pubkeys_hex={_pubkey_hex(seed_a)}),
        ISSUER_B: mod.TrustedIssuer(did=ISSUER_B, pubkeys_hex={_pubkey_hex(seed_b)}),
    }
    ok, reason = mod.verify_ppid_convergence_artifact(
        artifact,
        site_id="app.example.com",
        canonical_ppid=PPID,
        trusted_issuers=trusted,
    )
    assert ok is False
    assert reason == "convergence_invalid_signature"

    artifact["proof"] = {"signatureValueWeb": _sign_digest(seed_a, digest)}
    ok, reason = mod.verify_ppid_convergence_artifact(
        artifact,
        site_id="app.example.com",
        canonical_ppid=PPID,
        trusted_issuers=trusted,
        expected_issuer_did=ISSUER_A,
    )
    assert ok is True


def test_fresh_passkey_subject_binding_requires_site_for_site_ppid(monkeypatch):
    from api import fresh_passkey_attestation as fpa

    monkeypatch.setattr(
        fpa,
        "lookup_wallet_passkey_identity",
        lambda _cid: ("wallet_abc", "device_1"),
    )

    ok, reason = fpa.validate_fresh_passkey_identity_binding(
        passkey_credential_id="cred_b64",
        wallet_id="wallet_abc",
        subject=PPID,
        site_id="",
    )
    # Without site_id, site-PPID subjects cannot be resolved via master lookup.
    assert ok is False
    assert reason in {"site_id_required_for_subject_bind", "subject_binding_failed", "subject_ppid_mismatch"}


def test_fresh_passkey_subject_binding_matches_passkey_derived_ppid(monkeypatch):
    from api import fresh_passkey_attestation as fpa
    from api.ppid import derive_ppid_from_passkey

    monkeypatch.setattr(
        fpa,
        "lookup_wallet_passkey_identity",
        lambda _cid: ("wallet_abc", "device_1"),
    )

    class _Db:
        def close(self):
            return None

    monkeypatch.setattr("api.database.SessionLocal", lambda: _Db())
    monkeypatch.setattr("api.ishuman.resolve_wallet_id_for_ppid", lambda _db, _ppid: None)

    def _boom(**_kwargs):
        raise RuntimeError("no person root")

    monkeypatch.setattr("api.ishuman._derive_ppid_for_site", _boom)

    expected = derive_ppid_from_passkey("cred_b64", "app.example.com")
    ok, reason = fpa.validate_fresh_passkey_identity_binding(
        passkey_credential_id="cred_b64",
        wallet_id="wallet_abc",
        subject=expected,
        site_id="app.example.com",
    )
    assert ok is True
    assert reason == "ok"

    ok, reason = fpa.validate_fresh_passkey_identity_binding(
        passkey_credential_id="cred_b64",
        wallet_id="wallet_abc",
        subject=PPID,
        site_id="app.example.com",
    )
    assert ok is False
    assert reason == "subject_ppid_mismatch"


def test_mode_policy_critical_staged_enforce(monkeypatch):
    from api.authz.mode_policy import evaluate_mode_policy

    monkeypatch.delenv("LEMMA_ENFORCE_PROOF_REQUIRED", raising=False)
    monkeypatch.delenv("LEMMA_ENFORCE_PROOF_REQUIRED_CRITICAL", raising=False)
    headers = {"X-Agent-Token": "lm_agent_testtoken"}

    bypass = evaluate_mode_policy(
        expected_mode="proof_required",
        headers=headers,
        risk_tier="critical",
    )
    assert bypass.allowed is True
    assert bypass.agent_proof_bypass is True
    assert bypass.reason_code == "AUTH_PROOF_BYPASS_AGENT_COMPAT"

    monkeypatch.setenv("LEMMA_ENFORCE_PROOF_REQUIRED_CRITICAL", "1")
    denied = evaluate_mode_policy(
        expected_mode="proof_required",
        headers=headers,
        risk_tier="critical",
    )
    assert denied.allowed is False
    assert denied.reason_code == "AUTH_PROOF_REQUIRED"

    # High-tier still allows agent compat when only critical gate is on.
    high_ok = evaluate_mode_policy(
        expected_mode="proof_required",
        headers=headers,
        risk_tier="high",
    )
    assert high_ok.allowed is True
    assert high_ok.agent_proof_bypass is True

    monkeypatch.setenv("LEMMA_ENFORCE_PROOF_REQUIRED", "1")
    global_denied = evaluate_mode_policy(
        expected_mode="proof_required",
        headers=headers,
        risk_tier="high",
    )
    assert global_denied.allowed is False
    assert global_denied.reason_code == "AUTH_PROOF_REQUIRED"


def test_resolve_safe_outbound_pins_public_ip(monkeypatch):
    from api import url_safety

    monkeypatch.setattr(
        url_safety.socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ],
    )
    target, reason = url_safety.resolve_safe_outbound_target(
        "https://example.com/.well-known/lemma-verification.txt"
    )
    assert reason == "ok"
    assert target is not None
    assert target.pinned_ip == "93.184.216.34"
    assert target.hostname == "example.com"
    assert target.path.endswith("/.well-known/lemma-verification.txt")


def test_fetch_safe_outbound_uses_pinned_socket(monkeypatch):
    from api import url_safety

    monkeypatch.setattr(
        url_safety.socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ],
    )

    connected = {}

    class _Sock:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    def _create_connection(address, timeout=None):
        connected["address"] = address
        connected["timeout"] = timeout
        return _Sock()

    monkeypatch.setattr(url_safety.socket, "create_connection", _create_connection)

    class _Ctx:
        def wrap_socket(self, sock, server_hostname=None):
            connected["sni"] = server_hostname
            return sock

    monkeypatch.setattr(url_safety.ssl, "create_default_context", lambda: _Ctx())

    class _Resp:
        status = 200

        def read(self, _n):
            return b"lemma-token-value"

    class _Conn:
        def __init__(self, *a, **k):
            self.sock = None
            self.headers = None

        def request(self, method, path, headers=None):
            connected["method"] = method
            connected["path"] = path
            connected["host_header"] = (headers or {}).get("Host")

        def getresponse(self):
            return _Resp()

        def close(self):
            return None

    monkeypatch.setattr(url_safety.http.client, "HTTPSConnection", _Conn)

    ok, reason, body = url_safety.fetch_safe_outbound_text(
        "https://example.com/.well-known/lemma-verification.txt",
        timeout=5.0,
    )
    assert ok is True
    assert reason == "ok"
    assert "lemma-token-value" in (body or "")
    assert connected["address"] == ("93.184.216.34", 443)
    assert connected["sni"] == "example.com"
    assert connected["host_header"] == "example.com"


def test_verify_well_known_uses_pinned_fetch(monkeypatch):
    from api import issuer_registry

    monkeypatch.setattr(
        "api.url_safety.fetch_safe_outbound_text",
        lambda url, **k: (True, "ok", "prefix lemma-verify-token suffix"),
    )
    assert issuer_registry.verify_well_known("example.com", "lemma-verify-token") is True

    monkeypatch.setattr(
        "api.url_safety.fetch_safe_outbound_text",
        lambda url, **k: (False, "private_or_reserved_ip", None),
    )
    assert issuer_registry.verify_well_known("evil.internal", "lemma-verify-token") is False


def test_api_canonical_fresh_passkey_includes_issuer():
    from api.fresh_passkey_attestation import build_fresh_passkey_canonical_message

    msg = build_fresh_passkey_canonical_message(
        {
            "schema": "fresh_passkey_attestation.v1",
            "issuer": ISSUER_A,
            "site_id": "app.example.com",
            "credential_id": "c1",
            "subject": PPID,
            "action_commitment": "aa" * 32,
            "attestation_id": "fpa_1",
            "issued_at_unix": 1700000000,
            "expires_at_unix": 1700000120,
        },
        include_issuer=True,
    ).decode("utf-8")
    lines = msg.split("\n")
    assert lines[0] == "lemma:fresh-passkey-attestation:v1"
    assert lines[1] == "fresh_passkey_attestation.v1"
    assert lines[2] == ISSUER_A
