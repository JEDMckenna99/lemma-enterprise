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
    for artifact_id in (
        "ishuman_credential",
        "wallet_assertion",
        "wallet_master_secret",
        "presentation_envelope",
    ):
        assert by_id[artifact_id]["status"] == "implicit_legacy"
