import json
import os
import sys
import base64

from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.authz.mode_policy import evaluate_mode_policy  # noqa: E402
from api.authz.replay import validate_pop_replay  # noqa: E402
from api.authz.verifier import evaluate_proof_native  # noqa: E402
from api.authz_control_plane import authz_control_bp  # noqa: E402


def test_mode_policy_proof_required_blocks_without_proof(monkeypatch):
    monkeypatch.setenv("LEMMA_ENFORCE_PROOF_REQUIRED", "1")
    decision = evaluate_mode_policy(expected_mode="proof_required", headers={})
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_PROOF_REQUIRED"


def test_mode_policy_allows_when_proof_present(monkeypatch):
    monkeypatch.setenv("LEMMA_ENFORCE_PROOF_REQUIRED", "1")
    decision = evaluate_mode_policy(expected_mode="proof_required", headers={"X-Lemma-Proof": "{}"})
    assert decision.allowed is True
    assert decision.effective_mode in {"proof_required", "compat_proof_wrapped"}


def test_mode_policy_proof_required_blocks_without_proof_even_when_env_off(monkeypatch):
    monkeypatch.delenv("LEMMA_ENFORCE_PROOF_REQUIRED", raising=False)
    decision = evaluate_mode_policy(expected_mode="proof_required", headers={})
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_PROOF_REQUIRED"


def test_mode_policy_compat_bearer_expires_at_sunset():
    decision = evaluate_mode_policy(
        expected_mode="compat_bearer",
        headers={},
        compat_sunset_utc="2000-01-01T00:00:00Z",
    )
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_COMPAT_MODE_EXPIRED"


def test_mode_policy_sunset_accepts_modern_credential_but_rejects_agent_bearer():
    modern = evaluate_mode_policy(
        expected_mode="compat_bearer",
        headers={"X-Lemma-Credential": "credential"},
        compat_sunset_utc="2000-01-01T00:00:00Z",
    )
    legacy = evaluate_mode_policy(
        expected_mode="compat_bearer",
        headers={"X-Agent-Token": "lm_agent_legacy"},
        compat_sunset_utc="2000-01-01T00:00:00Z",
    )

    assert modern.allowed is True
    assert modern.effective_mode == "credential_required"
    assert legacy.allowed is False
    assert legacy.reason_code == "AUTH_COMPAT_MODE_EXPIRED"


def test_replay_contract_detects_nonce_reuse():
    used = set()

    def writer(key: str, _ttl: int) -> bool:
        if key in used:
            return False
        used.add(key)
        return True

    pop_payload = {
        "nonce": "abc",
        "proof_id": "prf_1",
        "iat": 0,
        "exp": 9999999999,
        "method": "GET",
        "path": "/api/developer/sites",
        "body_hash": "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855",
    }
    headers = {"X-Lemma-PoP": json.dumps(pop_payload)}
    first = validate_pop_replay(
        headers=headers,
        method="GET",
        path="/api/developer/sites",
        body_bytes=b"",
        required=True,
        nonce_writer=writer,
    )
    second = validate_pop_replay(
        headers=headers,
        method="GET",
        path="/api/developer/sites",
        body_bytes=b"",
        required=True,
        nonce_writer=writer,
    )
    assert first.valid is True
    assert second.valid is False
    assert second.code == "AUTH_REPLAY_DETECTED"


def test_replay_contract_accepts_valid_ed25519_signature():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        return

    used = set()

    def writer(key: str, _ttl: int) -> bool:
        if key in used:
            return False
        used.add(key)
        return True

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_b64 = base64.urlsafe_b64encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("utf-8").rstrip("=")
    payload = {
        "nonce": "sig-ok-1",
        "proof_id": "dpf_sig_ok_1",
        "agent_key_id": "agent-key-1",
        "iat": 0,
        "exp": 9999999999,
        "method": "GET",
        "path": "/api/developer/sites",
        "body_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "aud": "lemma.id",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sig = private_key.sign(canonical)
    payload["sig"] = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    headers = {
        "X-Lemma-PoP": json.dumps(payload),
        "X-Lemma-Proof": json.dumps(
            {
                "delegated_proof": {"agent_key_id": "agent-key-1", "agent_public_key": public_b64},
                "proof_id": "dpf_sig_ok_1",
            }
        ),
    }
    decision = validate_pop_replay(
        headers=headers,
        method="GET",
        path="/api/developer/sites",
        body_bytes=b"",
        required=True,
        nonce_writer=writer,
        require_signature=True,
    )
    assert decision.valid is True


def test_replay_contract_denies_invalid_ed25519_signature():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        return

    used = set()

    def writer(key: str, _ttl: int) -> bool:
        if key in used:
            return False
        used.add(key)
        return True

    private_key = Ed25519PrivateKey.generate()
    other_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_b64 = base64.urlsafe_b64encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("utf-8").rstrip("=")
    payload = {
        "nonce": "sig-bad-1",
        "proof_id": "dpf_sig_bad_1",
        "agent_key_id": "agent-key-1",
        "iat": 0,
        "exp": 9999999999,
        "method": "GET",
        "path": "/api/developer/sites",
        "body_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "aud": "lemma.id",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload["sig"] = base64.urlsafe_b64encode(other_key.sign(canonical)).decode("utf-8").rstrip("=")
    headers = {
        "X-Lemma-PoP": json.dumps(payload),
        "X-Lemma-Proof": json.dumps(
            {
                "delegated_proof": {"agent_key_id": "agent-key-1", "agent_public_key": public_b64},
                "proof_id": "dpf_sig_bad_1",
            }
        ),
    }
    decision = validate_pop_replay(
        headers=headers,
        method="GET",
        path="/api/developer/sites",
        body_bytes=b"",
        required=True,
        nonce_writer=writer,
        require_signature=True,
    )
    assert decision.valid is False
    assert decision.code == "AUTH_PROOF_OF_POSSESSION_FAILED"


def test_replay_contract_denies_missing_signature_when_required():
    pop_payload = {
        "nonce": "sig-missing-1",
        "proof_id": "dpf_sig_missing_1",
        "agent_key_id": "agent-key-1",
        "iat": 0,
        "exp": 9999999999,
        "method": "GET",
        "path": "/api/developer/sites",
        "body_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }
    headers = {"X-Lemma-PoP": json.dumps(pop_payload)}
    decision = validate_pop_replay(
        headers=headers,
        method="GET",
        path="/api/developer/sites",
        body_bytes=b"",
        required=True,
        require_signature=True,
    )
    assert decision.valid is False
    assert decision.reason == "missing_signature"


def test_proof_verifier_requires_scope():
    payload = {
        "proof_id": "p1",
        "root_grant_id": "r1",
        "scope": ["read"],
        "aud": "lemma.id",
        "issued_at": 0,
        "expires_at": 9999999999,
        "version": "v2",
    }
    decision = evaluate_proof_native(
        headers={"X-Lemma-Proof": json.dumps(payload)},
        method="GET",
        path="/api/developer/sites",
        required_scope="admin",
        base_url="https://lemma.id",
    )
    assert decision.allowed is False


def test_proof_verifier_accepts_valid_chain(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )
    payload = {
        "version": "authz_profile_v2",
        "policy_version": "authz_profile_v2",
        "root_proof": {
            "proof_id": "root_1",
            "root_grant_id": "rgr_1",
            "subject_ppid": "did:lemma:ppid_abc",
            "scope": ["read", "admin"],
            "aud": "lemma.id",
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_abc",
        },
        "delegated_proof": {
            "proof_id": "dpf_1",
            "parent_proof_id": "root_1",
            "root_grant_id": "rgr_1",
            "acting_for_ppid": "did:lemma:ppid_abc",
            "agent_key_id": "agent_1",
            "scope": ["read"],
            "aud": "lemma.id",
            "delegation_depth": 1,
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_abc",
        },
        "proof_id": "dpf_1",
        "root_grant_id": "rgr_1",
    }
    decision = evaluate_proof_native(
        headers={"X-Lemma-Proof": json.dumps(payload)},
        method="GET",
        path="/api/developer/sites",
        required_scope="read",
        base_url="https://lemma.id",
    )
    assert decision.allowed is True
    assert decision.reason_code == "OK"


def test_proof_verifier_accepts_multi_hop_chain(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )
    root = {
        "proof_id": "root_1",
        "root_grant_id": "rgr_1",
        "subject_ppid": "did:lemma:ppid_abc",
        "scope": ["read", "write"],
        "aud": "lemma.id",
        "delegation_depth": 0,
        "issued_at": 10,
        "expires_at": 9999999999,
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_abc",
    }
    parent = {
        "proof_id": "dpf_parent_1",
        "parent_proof_id": "root_1",
        "root_grant_id": "rgr_1",
        "acting_for_ppid": "did:lemma:ppid_abc",
        "scope": ["read", "write"],
        "aud": "lemma.id",
        "delegation_depth": 1,
        "issued_at": 20,
        "expires_at": 9999999990,
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_abc",
    }
    child = {
        "proof_id": "dpf_child_1",
        "parent_proof_id": "dpf_parent_1",
        "root_grant_id": "rgr_1",
        "acting_for_ppid": "did:lemma:ppid_abc",
        "scope": ["read"],
        "aud": "lemma.id",
        "delegation_depth": 2,
        "issued_at": 30,
        "expires_at": 9999999980,
        "issuer": "did:web:lemma.id",
        "subject": "did:lemma:ppid_abc",
        "ancestor_ids": ["dpf_child_1", "dpf_parent_1", "root_1", "rgr_1"],
    }
    payload = {
        "version": "authz_profile_v2",
        "policy_version": "authz_profile_v2",
        "proof_id": "dpf_child_1",
        "root_grant_id": "rgr_1",
        "proof_chain": [root, parent, child],
        "root_proof": root,
        "delegated_proof": child,
    }
    decision = evaluate_proof_native(
        headers={"X-Lemma-Proof": json.dumps(payload)},
        method="GET",
        path="/api/developer/sites",
        required_scope="read",
        base_url="https://lemma.id",
    )
    assert decision.allowed is True
    assert decision.reason_code == "OK"


def test_proof_verifier_denies_revoked_ancestor_in_chain(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )
    payload = {
        "version": "authz_profile_v2",
        "proof_id": "dpf_child_1",
        "root_grant_id": "rgr_1",
        "proof_chain": [
            {
                "proof_id": "root_1",
                "root_grant_id": "rgr_1",
                "scope": ["read"],
                "aud": "lemma.id",
                "delegation_depth": 0,
                "issued_at": 0,
                "expires_at": 9999999999,
                "issuer": "did:web:lemma.id",
                "subject": "did:lemma:ppid_abc",
            },
            {
                "proof_id": "dpf_child_1",
                "parent_proof_id": "root_1",
                "root_grant_id": "rgr_1",
                "acting_for_ppid": "did:lemma:ppid_abc",
                "scope": ["read"],
                "aud": "lemma.id",
                "delegation_depth": 1,
                "issued_at": 1,
                "expires_at": 9999999998,
                "issuer": "did:web:lemma.id",
                "subject": "did:lemma:ppid_abc",
                "ancestor_ids": ["dpf_child_1", "root_1", "rgr_1"],
            },
        ],
    }
    decision = evaluate_proof_native(
        headers={"X-Lemma-Proof": json.dumps(payload)},
        method="GET",
        path="/api/developer/sites",
        required_scope="read",
        base_url="https://lemma.id",
        revoked_proof_ids={"root_1"},
    )
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_CHAIN_BROKEN"


def test_proof_verifier_denies_broken_parent(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )
    payload = {
        "version": "authz_profile_v2",
        "root_proof": {
            "proof_id": "root_1",
            "root_grant_id": "rgr_1",
            "scope": ["read"],
            "aud": "lemma.id",
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_abc",
        },
        "delegated_proof": {
            "proof_id": "dpf_1",
            "parent_proof_id": "wrong_parent",
            "root_grant_id": "rgr_1",
            "acting_for_ppid": "did:lemma:ppid_abc",
            "agent_key_id": "agent_1",
            "scope": ["read"],
            "aud": "lemma.id",
            "delegation_depth": 1,
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_abc",
        },
    }
    decision = evaluate_proof_native(
        headers={"X-Lemma-Proof": json.dumps(payload)},
        method="GET",
        path="/api/developer/sites",
        required_scope="read",
        base_url="https://lemma.id",
    )
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_CHAIN_BROKEN"


def test_proof_verifier_denies_unknown_critical_key(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )
    payload = {
        "version": "authz_profile_v2",
        "critical_unexpected": "x",
        "root_proof": {
            "proof_id": "root_1",
            "root_grant_id": "rgr_1",
            "scope": ["read"],
            "aud": "lemma.id",
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_abc",
        },
        "delegated_proof": {
            "proof_id": "dpf_1",
            "parent_proof_id": "root_1",
            "root_grant_id": "rgr_1",
            "acting_for_ppid": "did:lemma:ppid_abc",
            "agent_key_id": "agent_1",
            "scope": ["read"],
            "aud": "lemma.id",
            "delegation_depth": 1,
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_abc",
        },
    }
    decision = evaluate_proof_native(
        headers={"X-Lemma-Proof": json.dumps(payload)},
        method="GET",
        path="/api/developer/sites",
        required_scope="read",
        base_url="https://lemma.id",
    )
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_CHAIN_BROKEN"


def test_proof_verifier_denies_revoked_root(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )
    payload = {
        "version": "authz_profile_v2",
        "proof_id": "dpf_1",
        "root_grant_id": "rgr_1",
        "root_proof": {
            "proof_id": "root_1",
            "root_grant_id": "rgr_1",
            "scope": ["read"],
            "aud": "lemma.id",
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_abc",
        },
        "delegated_proof": {
            "proof_id": "dpf_1",
            "parent_proof_id": "root_1",
            "root_grant_id": "rgr_1",
            "acting_for_ppid": "did:lemma:ppid_abc",
            "agent_key_id": "agent_1",
            "scope": ["read"],
            "aud": "lemma.id",
            "delegation_depth": 1,
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_abc",
        },
    }
    decision = evaluate_proof_native(
        headers={"X-Lemma-Proof": json.dumps(payload)},
        method="GET",
        path="/api/developer/sites",
        required_scope="read",
        base_url="https://lemma.id",
        revoked_root_grant_ids={"rgr_1"},
    )
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_CHAIN_BROKEN"


def test_proof_verifier_denies_ppid_continuity_break(monkeypatch):
    monkeypatch.setattr(
        "api.trusted_issuers.verify_credential_with_trust",
        lambda _cred: {"valid": True},
    )
    payload = {
        "version": "authz_profile_v2",
        "proof_id": "dpf_1",
        "root_grant_id": "rgr_1",
        "root_proof": {
            "proof_id": "root_1",
            "root_grant_id": "rgr_1",
            "subject_ppid": "did:lemma:ppid_root",
            "scope": ["read"],
            "aud": "lemma.id",
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_root",
        },
        "delegated_proof": {
            "proof_id": "dpf_1",
            "parent_proof_id": "root_1",
            "root_grant_id": "rgr_1",
            "acting_for_ppid": "did:lemma:ppid_other",
            "agent_key_id": "agent_1",
            "scope": ["read"],
            "aud": "lemma.id",
            "delegation_depth": 1,
            "issued_at": 0,
            "expires_at": 9999999999,
            "issuer": "did:web:lemma.id",
            "subject": "did:lemma:ppid_other",
        },
    }
    decision = evaluate_proof_native(
        headers={"X-Lemma-Proof": json.dumps(payload)},
        method="GET",
        path="/api/developer/sites",
        required_scope="read",
        base_url="https://lemma.id",
    )
    assert decision.allowed is False
    assert decision.reason_code == "AUTH_CHAIN_BROKEN"


def test_authz_control_plane_endpoints():
    app = Flask(__name__)
    app.register_blueprint(authz_control_bp)
    with app.test_client() as client:
        jwks = client.get("/api/authz/jwks")
        assert jwks.status_code == 200
        snapshot = client.get("/api/authz/policy/snapshot")
        assert snapshot.status_code == 200
        payload = snapshot.get_json()
        assert payload["success"] is True
        assert "policy_version" in payload["policy"]
        delta = client.get("/api/authz/revocation/delta")
        assert delta.status_code == 200
        delta_payload = delta.get_json()
        assert delta_payload["success"] is True
        if delta_payload.get("changes"):
            first = delta_payload["changes"][0]
            assert "proof_id" in first
            assert "root_grant_id" in first
