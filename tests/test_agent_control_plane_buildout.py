from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from api.authz.verifier import evaluate_proof_native
from api.authz_control_plane import _revocation_shape_fields


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_workload_root_allows_non_ppid_continuity(monkeypatch):
    now = datetime.now(timezone.utc)
    root_proof = {
        "proof_id": "prf_root",
        "root_type": "workload_root",
        "root_grant_id": "wkr_root_1",
        "subject_ppid": "did:lemma:ppid_human_a",
        "scope": ["read"],
        "issued_at": _iso(now - timedelta(minutes=1)),
        "expires_at": _iso(now + timedelta(minutes=10)),
    }
    delegated_proof = {
        "proof_id": "dpf_1",
        "parent_proof_id": "prf_root",
        "root_type": "workload_root",
        "root_grant_id": "wkr_root_1",
        "acting_for_ppid": "did:lemma:ppid_workload_service",
        "scope": ["read"],
        "delegation_depth": 1,
        "issued_at": _iso(now - timedelta(minutes=1)),
        "expires_at": _iso(now + timedelta(minutes=10)),
    }
    payload = {
        "policy_version": "authz_profile_v2",
        "root_type": "workload_root",
        "proof_id": "dpf_1",
        "root_grant_id": "wkr_root_1",
        "proof_chain": [root_proof, delegated_proof],
        "delegated_proof": delegated_proof,
        "root_proof": root_proof,
        "scope": ["read"],
    }
    monkeypatch.setattr("api.authz.verifier._decode_proof", lambda _raw: payload)
    monkeypatch.setattr("api.authz.verifier._validate_chain_signatures", lambda *_args, **_kwargs: True)
    decision = evaluate_proof_native(headers={"X-Lemma-Proof": "x"}, method="GET", path="/api/test", required_scope="read")
    assert decision.allowed is True


def test_revocation_shape_marks_workload_roots():
    shape = _revocation_shape_fields("wkr_abc123", None)
    assert shape["subject_type"] == "workload_root"
    assert shape["root_type"] == "workload_root"
    assert shape["root_grant_id"] == "wkr_abc123"


