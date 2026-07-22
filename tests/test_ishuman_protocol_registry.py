"""Contract tests for the isHuman protocol registry and migration policy."""

from __future__ import annotations

from scripts.check_ishuman_protocol_registry import load_registry, validate_registry


def test_protocol_registry_matches_docs_and_source_constants():
    assert validate_registry(load_registry()) == []


def test_protocol_registry_fails_closed_on_unknown_versions():
    registry = load_registry()
    assert registry["unknown_version_policy"] == "fail_closed"


def test_protocol_registry_covers_all_human_auth_artifact_classes():
    registry = load_registry()
    artifact_ids = {artifact["artifact_id"] for artifact in registry["artifacts"]}
    assert {
        "ishuman_credential",
        "presentation_envelope",
        "site_session_presentation",
        "action_stamp",
        "ppid_convergence",
        "bloom_snapshot",
        "issuer_trust_list",
        "fresh_passkey_attestation",
        "document_root",
        "person_root",
        "site_ppid",
    } <= artifact_ids


def test_implicit_legacy_formats_are_not_misrepresented_as_explicit_versions():
    registry = load_registry()
    by_id = {artifact["artifact_id"]: artifact for artifact in registry["artifacts"]}
    expected = {
        # Credential shape is now explicit v2 with retained legacy v1 verify path.
        "ishuman_credential": "explicit_with_legacy_v1",
        "wallet_assertion": "implicit_legacy",
        "wallet_master_secret": "implicit_legacy",
        "presentation_envelope": "implicit_legacy",
    }
    for artifact_id, status in expected.items():
        assert by_id[artifact_id]["status"] == status
        assert by_id[artifact_id]["status"] != "explicit"
