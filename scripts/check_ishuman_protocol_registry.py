#!/usr/bin/env python3
"""Validate the isHuman protocol registry against docs and source constants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "docs" / "protocol" / "ISHUMAN_PROTOCOL_VERSIONS.json"
READABLE_PATH = REPO_ROOT / "docs" / "protocol" / "ISHUMAN_PROTOCOL_VERSIONS.md"
CANONICAL_PATH = REPO_ROOT / "docs" / "cryptographic" / "CANONICAL_MESSAGES.md"
MIGRATION_PATH = REPO_ROOT / "docs" / "protocol" / "ISHUMAN_PROTOCOL_MIGRATION_POLICY.md"

REQUIRED_ARTIFACTS = {
    "site_ppid",
    "document_root",
    "person_root",
    "ishuman_credential",
    "site_session_presentation",
    "wallet_assertion",
    "wallet_master_secret",
    "bloom_snapshot",
    "issuer_trust_list",
    "ppid_convergence",
    "action_commitment",
    "fresh_passkey_attestation",
    "action_stamp",
    "presentation_envelope",
}
REQUIRED_FIELDS = {
    "artifact_id",
    "version",
    "wire_marker",
    "marker_type",
    "status",
    "canonical_section",
    "migration_class",
    "source_assertions",
}
MIGRATION_CLASSES = {
    "derived_identifier",
    "root_material",
    "signed_artifact",
    "signed_envelope",
    "composite_envelope",
}


def load_registry() -> dict[str, Any]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("protocol registry must be a JSON object")
    return payload


def validate_registry(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    canonical = CANONICAL_PATH.read_text(encoding="utf-8")
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    readable = READABLE_PATH.read_text(encoding="utf-8")

    if payload.get("unknown_version_policy") != "fail_closed":
        errors.append("unknown_version_policy must be fail_closed")
    if payload.get("migration_policy") != MIGRATION_PATH.relative_to(REPO_ROOT).as_posix():
        errors.append("migration_policy path does not match the canonical policy")
    if payload.get("canonical_messages") != CANONICAL_PATH.relative_to(REPO_ROOT).as_posix():
        errors.append("canonical_messages path does not match the canonical specification")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return errors + ["artifacts must be a non-empty list"]

    seen: set[str] = set()
    for index, artifact in enumerate(artifacts):
        label = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{label} must be an object")
            continue

        artifact_id = str(artifact.get("artifact_id") or "")
        missing = sorted(REQUIRED_FIELDS - set(artifact))
        if missing:
            errors.append(f"{artifact_id or label} missing fields: {', '.join(missing)}")
        if not artifact_id:
            errors.append(f"{label} has an empty artifact_id")
            continue
        if artifact_id in seen:
            errors.append(f"duplicate artifact_id: {artifact_id}")
        seen.add(artifact_id)

        for field in ("version", "wire_marker", "marker_type", "status", "canonical_section"):
            if not str(artifact.get(field) or "").strip():
                errors.append(f"{artifact_id} has empty {field}")

        if artifact.get("migration_class") not in MIGRATION_CLASSES:
            errors.append(f"{artifact_id} has invalid migration_class")

        section = str(artifact.get("canonical_section") or "")
        if section and section not in canonical:
            errors.append(f"{artifact_id} canonical section missing: {section}")
        if f"`{artifact_id}`" not in migration:
            errors.append(f"{artifact_id} is not covered by the migration policy")

        assertions = artifact.get("source_assertions")
        if not isinstance(assertions, list) or not assertions:
            errors.append(f"{artifact_id} requires source_assertions")
            continue
        for assertion in assertions:
            if not isinstance(assertion, dict):
                errors.append(f"{artifact_id} has a non-object source assertion")
                continue
            rel_path = str(assertion.get("path") or "")
            expected = str(assertion.get("contains") or "")
            source_path = REPO_ROOT / rel_path
            if not rel_path or not expected:
                errors.append(f"{artifact_id} has an incomplete source assertion")
            elif not source_path.is_file():
                errors.append(f"{artifact_id} source path missing: {rel_path}")
            elif expected not in source_path.read_text(encoding="utf-8"):
                errors.append(f"{artifact_id} source marker drifted: {rel_path}: {expected}")

        marker = str(artifact.get("wire_marker") or "")
        if marker and marker not in readable:
            errors.append(f"{artifact_id} wire marker missing from readable registry")

    missing_artifacts = sorted(REQUIRED_ARTIFACTS - seen)
    extra_artifacts = sorted(seen - REQUIRED_ARTIFACTS)
    if missing_artifacts:
        errors.append(f"registry missing artifacts: {', '.join(missing_artifacts)}")
    if extra_artifacts:
        errors.append(f"unreviewed registry artifacts: {', '.join(extra_artifacts)}")

    return errors


def main() -> int:
    payload = load_registry()
    errors = validate_registry(payload)
    if errors:
        print("isHuman protocol registry failed:")
        for error in errors:
            print(f" - {error}")
        return 1
    print(
        "isHuman protocol registry passed: "
        f"{len(payload['artifacts'])} artifacts in {payload['current_epoch']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
