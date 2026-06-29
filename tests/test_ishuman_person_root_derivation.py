from __future__ import annotations

import pytest

from tests.wallet_test_helpers import DERIVE_ASSERTION_FIELDS, SITE_SIGNING_PUBKEY_B64


@pytest.mark.unit
def test_derive_site_proof_uses_person_root_ppid(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import IsHumanVerification, LemmaPerson
    from api.identity_person import material_from_test_fixture, resolve_or_create_person_from_material
    from api.ppid import derive_ppid_from_person_root_hash

    db = fake_ishuman_db_session_factory
    session = db.session_local()
    material = material_from_test_fixture(document_number="DERIVE_SITE_001")
    resolved = resolve_or_create_person_from_material(session, material=material, wallet_id="wallet_test_001")
    expected_site_ppid = derive_ppid_from_person_root_hash(resolved.person_root_hash, "example.com")

    db.store.data[IsHumanVerification.__name__].append(
        make_ishuman_verification(
            credential_id="ishuman_master_person_root_1",
            wallet_id="wallet_test_001",
            lemma_person_id=resolved.person_id,
            document_root_hash=resolved.document_root_hash,
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    issued = []

    def _issue(ppid, wallet_id=None, site_id=None, **kwargs):
        issued.append(ppid)
        return {
            "id": "ishuman_site_person_root_001",
            "subject": ppid,
            "claims": {"isHuman": True, "siteId": site_id, "ppidDerivation": kwargs.get("ppid_derivation")},
        }

    monkeypatch.setattr("api.ishuman._issue_ishuman_credential", _issue)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_person_root_1",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "Example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["success"] is True
    assert issued[0] == expected_site_ppid
    assert db.store.data["DerivedCredential"] == []
