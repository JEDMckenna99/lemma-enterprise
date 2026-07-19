"""Contract tests for human-auth authority-changing operations."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_authority_operations import validate_contract


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "docs" / "api" / "AUTHORITY_OPERATIONS_V1.json"


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _operation(operation_id: str) -> dict:
    return next(
        operation
        for operation in _contract()["operations"]
        if operation["operation_id"] == operation_id
    )


def test_authority_operation_contract_is_complete():
    assert validate_contract(_contract()) == []


def test_wallet_id_only_session_paths_are_closed():
    init_first = _operation("wallet.session.init_first")
    assert init_first["current_auth"] == ["retired_http_410"]
    assert init_first["compliance"] == "compliant"

    signal_unlock = _operation("wallet.session.signal_unlock")
    assert "existing_webauthn_session" in signal_unlock["required_auth"]
    assert "authorized_wallet_assertion" in signal_unlock["required_auth"]
    assert "csrf_token" in signal_unlock["required_auth"]
    assert signal_unlock["compliance"] == "compliant"

    webauthn_unlock = _operation("wallet.session.webauthn_unlock")
    assert "verified_webauthn_assertion" in webauthn_unlock["required_auth"]
    assert webauthn_unlock["compliance"] == "compliant"


def test_signing_key_enrollment_requires_existing_authority():
    operation = _operation("wallet.device.register_signing_key")
    assert operation["compliance"] == "compliant"
    assert "webauthn_first_device_or_existing_device_transfer_or_verified_recovery" in operation["required_auth"]

    enroll = _operation("wallet.device.enroll_webauthn")
    assert enroll["compliance"] == "compliant"
    assert "webauthn_registration_ceremony" in enroll["required_auth"]

    revoke = _operation("wallet.device.revoke")
    assert "fresh_webauthn_for_cross_device_revoke" in revoke["required_auth"]

    device_list = _operation("wallet.device.list")
    assert device_list["compliance"] == "compliant"
    assert "authorized_wallet_assertion" in device_list["required_auth"]

    recovery = _operation("wallet.device.lost_device_recovery")
    assert recovery["compliance"] == "compliant"
    assert "verified_idv_session" in recovery["required_auth"]
    assert "webauthn_registration_ceremony" in recovery["required_auth"]


def test_site_proof_requires_assurance_and_canonical_site_binding():
    operation = _operation("identity.site_proof.derive")
    assert "required_assurance" in operation["required_auth"]
    assert operation["site_binding"] == "canonical_hostname"


def test_site_registration_requires_domain_ownership():
    operation = _operation("tenant.site.register")
    assert operation["compliance"] == "compliant"
    assert "domain_ownership_proof" in operation["required_auth"]
    assert "existing_owner_conflict_check" in operation["required_auth"]


def test_billing_webhook_requires_transactional_idempotency():
    operation = _operation("billing.stripe_webhook")
    assert "transactional_event_idempotency" in operation["required_auth"]
    assert operation["compliance"] == "gap"


def test_recovery_completion_requires_human_and_replacement_passkey_proofs():
    operation = _operation("recovery.complete")
    assert "verified_human_recovery" in operation["required_auth"]
    assert "replacement_passkey_proof" in operation["required_auth"]
    assert "atomically_consumed_recovery_token" in operation["required_auth"]
