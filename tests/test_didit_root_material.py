"""Unit tests for didit IDV decision -> document-root material mapping.

Covers the fragile field normalization (alpha-3 country, human-readable
document type) and the fail-closed behavior on missing/invalid fields.
"""

from __future__ import annotations

import pytest

from api.identity_roots import (
    IdentityRootMaterialError,
    extract_root_material_from_didit_decision,
    map_didit_country,
    map_didit_document_type,
    validate_didit_workflow_id,
)

PROOF_OF_HUMANITY_WORKFLOW_ID = "668fbf42-cfb7-4774-9ecd-564c297d4a07"


def _approved_poh_decision(**idv_overrides) -> dict:
    idv = {
        "status": "Approved",
        "document_type": "Passport",
        "document_number": "x 12-345 678",
        "date_of_birth": "1985-03-12",
        "issuing_state": "USA",
        **idv_overrides,
    }
    return {
        "id_verifications": [idv],
        "liveness_checks": [{"status": "Approved", "method": "passive"}],
        "face_matches": [{"status": "Approved", "score": 95}],
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "alpha3,alpha2",
    [("ESP", "ES"), ("USA", "US"), ("GBR", "GB"), ("DEU", "DE"), ("JPN", "JP")],
)
def test_country_alpha3_to_alpha2(alpha3, alpha2):
    assert map_didit_country(alpha3) == alpha2


@pytest.mark.unit
def test_country_passthrough_alpha2():
    assert map_didit_country("es") == "ES"


@pytest.mark.unit
def test_country_unknown_fails_closed():
    with pytest.raises(IdentityRootMaterialError):
        map_didit_country("ZZZ")


@pytest.mark.unit
@pytest.mark.parametrize(
    "label,expected",
    [
        ("Identity Card", "id_card"),
        ("Passport", "passport"),
        ("Driver's License", "driving_license"),
        ("Driving Licence", "driving_license"),
        ("National ID", "id_card"),
    ],
)
def test_document_type_mapping(label, expected):
    assert map_didit_document_type(label) == expected


@pytest.mark.unit
def test_document_type_unsupported_fails_closed():
    with pytest.raises(IdentityRootMaterialError):
        map_didit_document_type("Residence Permit")


@pytest.mark.unit
def test_extract_picks_approved_entry_and_normalizes():
    decision = _approved_poh_decision()
    decision["id_verifications"] = [
        {"status": "Declined", "document_type": "Passport"},
        decision["id_verifications"][0],
    ]
    material = extract_root_material_from_didit_decision(decision)
    assert material.country == "US"
    assert material.document_type == "passport"
    # The extractor preserves the raw document number; normalization (strip
    # spaces/hyphens, uppercase) happens later in build_document_root_claims.
    assert material.document_number == "x 12-345 678"
    assert material.date_of_birth == "1985-03-12"
    assert material.document_expiration_date is None
    assert material.stripe_session_id is None


@pytest.mark.unit
def test_extract_reads_document_expiration_date():
    decision = _approved_poh_decision(expiration_date="2031-06-02")
    material = extract_root_material_from_didit_decision(decision)
    assert material.document_expiration_date == "2031-06-02"


@pytest.mark.unit
def test_extract_ignores_invalid_document_expiration_date():
    decision = _approved_poh_decision(expiration_date="not-a-date")
    material = extract_root_material_from_didit_decision(decision)
    assert material.document_expiration_date is None


@pytest.mark.unit
def test_extract_no_approved_entry_fails_closed():
    decision = _approved_poh_decision()
    decision["id_verifications"] = [{"status": "Declined"}]
    with pytest.raises(IdentityRootMaterialError):
        extract_root_material_from_didit_decision(decision)


@pytest.mark.unit
def test_extract_missing_id_verifications_fails_closed():
    with pytest.raises(IdentityRootMaterialError):
        extract_root_material_from_didit_decision({})


@pytest.mark.unit
def test_extract_missing_document_number_fails_closed():
    decision = _approved_poh_decision(document_number="")
    with pytest.raises(IdentityRootMaterialError):
        extract_root_material_from_didit_decision(decision)


@pytest.mark.unit
def test_extract_bad_dob_fails_closed():
    decision = _approved_poh_decision(date_of_birth="12/03/1985")
    with pytest.raises(IdentityRootMaterialError):
        extract_root_material_from_didit_decision(decision)


@pytest.mark.unit
def test_extract_missing_liveness_fails_closed():
    decision = _approved_poh_decision()
    decision["liveness_checks"] = []
    with pytest.raises(IdentityRootMaterialError, match="liveness"):
        extract_root_material_from_didit_decision(decision)


@pytest.mark.unit
def test_extract_declined_liveness_fails_closed():
    decision = _approved_poh_decision()
    decision["liveness_checks"] = [{"status": "Declined"}]
    with pytest.raises(IdentityRootMaterialError, match="liveness"):
        extract_root_material_from_didit_decision(decision)


@pytest.mark.unit
def test_extract_missing_face_match_fails_closed():
    decision = _approved_poh_decision()
    decision.pop("face_matches")
    with pytest.raises(IdentityRootMaterialError, match="face_match"):
        extract_root_material_from_didit_decision(decision)


@pytest.mark.unit
def test_extract_declined_face_match_fails_closed():
    decision = _approved_poh_decision()
    decision["face_matches"] = [{"status": "Declined"}]
    with pytest.raises(IdentityRootMaterialError, match="face_match"):
        extract_root_material_from_didit_decision(decision)


@pytest.mark.unit
def test_validate_workflow_id_matches_config(monkeypatch):
    monkeypatch.setattr(
        "api.config.get_didit_workflow_id",
        lambda: PROOF_OF_HUMANITY_WORKFLOW_ID,
    )
    validate_didit_workflow_id(PROOF_OF_HUMANITY_WORKFLOW_ID)


@pytest.mark.unit
def test_validate_workflow_id_mismatch_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "api.config.get_didit_workflow_id",
        lambda: PROOF_OF_HUMANITY_WORKFLOW_ID,
    )
    with pytest.raises(IdentityRootMaterialError, match="workflow_id mismatch"):
        validate_didit_workflow_id("wrong-workflow-id")
