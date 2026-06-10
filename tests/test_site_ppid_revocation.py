from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.wallet_test_helpers import DERIVE_ASSERTION_FIELDS, SITE_SIGNING_PUBKEY_B64


def _seed_site(db_factory, *, site_id="site_test_001", domain="example.com", api_key="test_api_key"):
    from api.database import Site

    site = Site(
        site_id=site_id,
        site_domain=domain,
        company_name="Test Site",
        admin_email="admin@example.com",
        api_key=api_key,
        oauth_client_id="oauth_test",
        oauth_client_secret="secret_test",
    )
    db_factory.store.data[Site.__name__].append(site)
    return site


@pytest.mark.unit
def test_revoke_site_bound_ppid_writes_block_and_revocation_list(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import RevocationList, SiteBlock
    from api.site_ppid_revocation import revoke_site_bound_ppid

    db = fake_ishuman_db_session_factory
    session = db.session_local()
    monkeypatch.setattr(
        "api.revocation_sync.trigger_revocation_sync",
        lambda credential_id, credential_type="unknown", site_id=None: True,
    )

    result = revoke_site_bound_ppid(
        session,
        site_id="site_test_001",
        ppid="did:lemma:ppid_revoke_001",
        reason="bot activity",
        revoked_by="test",
    )

    assert result["block_created"] is True
    assert result["revocation_created"] is True
    assert len(db.store.data[SiteBlock.__name__]) == 1
    assert len(db.store.data[RevocationList.__name__]) == 1
    revoke_row = db.store.data[RevocationList.__name__][0]
    assert revoke_row.ppid == "did:lemma:ppid_revoke_001"
    assert revoke_row.site_id == "site_test_001"
    assert revoke_row.revocation_type == "user"
    assert revoke_row.lemma_id == "did:lemma:ppid_revoke_001"


@pytest.mark.unit
def test_site_block_api_writes_canonical_revocation(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import RevocationList, SiteBlock

    db = fake_ishuman_db_session_factory
    _seed_site(db)
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.revocation_sync.trigger_revocation_sync",
        lambda credential_id, credential_type="unknown", site_id=None: True,
    )

    resp = ishuman_client.post(
        "/api/ishuman/site-block",
        json={"ppid": "did:lemma:ppid_site_block_001", "reason": "automated signup"},
        headers={"X-API-Key": "test_api_key"},
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert len(db.store.data[SiteBlock.__name__]) == 1
    assert len(db.store.data[RevocationList.__name__]) == 1
    assert db.store.data[RevocationList.__name__][0].ppid == "did:lemma:ppid_site_block_001"


@pytest.mark.unit
def test_derive_site_proof_denies_active_site_block(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import SiteBlock

    db = fake_ishuman_db_session_factory
    site = _seed_site(db)
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_block_001",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    db.store.data[SiteBlock.__name__].append(
        SiteBlock(
            site_id=site.site_id,
            ppid="did:lemma:ppid_blocked_site",
            reason="site block",
            blocked_by="admin@example.com",
            is_active=True,
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_blocked_site",
    )
    monkeypatch.setattr("api.revocation_verifier.is_credential_revoked", lambda _cid: False)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_block_001",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "site_ppid_blocked"


@pytest.mark.unit
def test_derive_site_proof_denies_master_credential_bloom_revocation(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    _seed_site(db)
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_bloom_001",
            wallet_id="wallet_test_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_ok",
    )

    def _is_revoked(credential_id):
        return credential_id == "ishuman_master_bloom_001"

    monkeypatch.setattr("api.revocation_verifier.is_credential_revoked", _is_revoked)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_bloom_001",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "master_credential_revoked"


@pytest.mark.unit
def test_derive_site_proof_denies_site_ppid_bloom_revocation(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory
    _seed_site(db)
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_ppid_bloom_001",
            wallet_id="wallet_test_001",
            status="verified",
            expires_at=datetime.utcnow() + timedelta(days=10),
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_site_revoked",
    )

    def _is_revoked(credential_id):
        return credential_id == "did:lemma:ppid_site_revoked"

    monkeypatch.setattr("api.revocation_verifier.is_credential_revoked", _is_revoked)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            {
                "master_credential_id": "ishuman_master_ppid_bloom_001",
                "wallet_id": "wallet_test_001",
                "wallet_secret": "ab" * 32,
                "target_site": "example.com",
                "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
            },
            DERIVE_ASSERTION_FIELDS,
        ),
    )

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "site_ppid_revoked"


@pytest.mark.unit
def test_network_revoke_disabled_by_default(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/network-revoke",
        json={"ppid": "did:lemma:ppid_demo"},
        headers={"X-API-Key": "test-site-key"},
    )
    payload = resp.get_json()

    assert resp.status_code == 503
    assert payload["error"] == "network_revocation_disabled"


@pytest.mark.unit
def test_approve_network_revocation_publishes_ishuman_events_without_reason_kwarg(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    make_derived_credential,
    monkeypatch,
):
    from api.database import DerivedCredential, IsHumanVerification, RevocationList
    from api.authz_engine import AuthzPrincipal

    monkeypatch.setenv("LEMMA_ISHUMAN_NETWORK_REVOCATION_ENABLED", "1")
    db = fake_ishuman_db_session_factory
    db.store.data[IsHumanVerification.__name__].append(
        make_ishuman_verification(
            credential_id="ishuman_master_revoke_001",
            wallet_id="wallet_revoke_001",
            status="verified",
            ppid="did:lemma:ppid_master_revoke",
        )
    )
    db.store.data[DerivedCredential.__name__].append(
        make_derived_credential(
            master_credential_id="ishuman_master_revoke_001",
            derived_credential_id="ishuman_site_revoke_001",
            wallet_id="wallet_revoke_001",
            target_site="example.com",
            derived_ppid="did:lemma:ppid_site_revoke",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr(
        "api.authz_engine.extract_user_lemma_principal",
        lambda _headers: (
            AuthzPrincipal(
                principal_type="user_lemma",
                auth_method="lemma_header",
                ppid="did:lemma:ppid_admin",
                credential_id="admin_cred_001",
                permission_id="admin_access",
                scope=["admin"],
                site_binding="lemma.id",
            ),
            None,
        ),
    )

    published = []

    class FakeBus:
        def publish_revocation(self, credential_id, credential_type="unknown", site_id=None):
            published.append(
                {
                    "credential_id": credential_id,
                    "credential_type": credential_type,
                    "site_id": site_id,
                }
            )
            return True

    monkeypatch.setattr("api.revocation_sync.get_event_bus", lambda: FakeBus())

    resp = ishuman_client.post(
        "/api/ishuman/approve-revocation",
        json={
            "wallet_id": "wallet_revoke_001",
            "reason": "confirmed automation",
        },
        headers={"X-Lemma-Credential": "{}"},
    )
    payload = resp.get_json()

    assert resp.status_code == 200
    assert payload["success"] is True
    assert payload["total_revoked"] == 3
    assert {event["credential_id"] for event in published} == {
        "wallet_revoke_001",
        "ishuman_master_revoke_001",
        "ishuman_site_revoke_001",
    }
    assert all(event["credential_type"] == "ishuman" for event in published)
    assert len(db.store.data[RevocationList.__name__]) == 3


@pytest.mark.unit
def test_revoke_site_bound_ppid_reactivates_inactive_site_block(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import SiteBlock
    from api.site_ppid_revocation import revoke_site_bound_ppid

    db = fake_ishuman_db_session_factory
    session = db.session_local()
    inactive = SiteBlock(
        site_id="site_test_001",
        ppid="did:lemma:ppid_reactivate_001",
        reason="old",
        blocked_by="test",
        is_active=False,
    )
    db.store.data[SiteBlock.__name__].append(inactive)
    monkeypatch.setattr(
        "api.revocation_sync.trigger_revocation_sync",
        lambda credential_id, credential_type="unknown", site_id=None: True,
    )

    result = revoke_site_bound_ppid(
        session,
        site_id="site_test_001",
        ppid="did:lemma:ppid_reactivate_001",
        reason="reactivated",
        revoked_by="test",
    )

    assert result["block_created"] is True
    assert len(db.store.data[SiteBlock.__name__]) == 1
    assert db.store.data[SiteBlock.__name__][0].is_active is True


@pytest.mark.unit
def test_check_ppid_reports_site_ppid_revoked_from_revocation_list(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import RevocationList

    db = fake_ishuman_db_session_factory
    ppid = "did:lemma:ppid_revoke_check_001"
    db.store.data[RevocationList.__name__].append(
        RevocationList(
            lemma_id=ppid,
            credential_id=ppid,
            ppid=ppid,
            site_id="site_test_001",
            lemma_type="ishuman",
            revocation_type="user",
            revoked_by="test",
            reason="test",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr("api.revocation_verifier.is_credential_revoked", lambda _cid: False)

    resp = ishuman_client.get(
        f"/api/ishuman/check?ppid={ppid}&site_id=site_test_001",
    )
    payload = resp.get_json()
    assert resp.status_code == 200
    assert payload["blocked"] is True
    assert payload["reason"] == "site_ppid_revoked"


@pytest.mark.unit
def test_sync_revocations_to_bloom_includes_ppid_and_wallet_keys(
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    from api.database import RevocationList
    from api.permission_verification import sync_revocations_to_bloom

    db = fake_ishuman_db_session_factory
    db.store.data[RevocationList.__name__].extend(
        [
            RevocationList(
                lemma_id="cred_abc",
                credential_id="cred_abc",
                lemma_type="ishuman",
                revocation_type="credential",
                revoked_by="test",
                reason="credential revoke",
            ),
            RevocationList(
                lemma_id="did:lemma:ppid_wallet_keys",
                credential_id="did:lemma:ppid_wallet_keys",
                ppid="did:lemma:ppid_wallet_keys",
                site_id="site_test_001",
                lemma_type="ishuman",
                revocation_type="user",
                revoked_by="test",
                reason="user revoke",
            ),
            RevocationList(
                lemma_id="wallet_kill_001",
                wallet_id="wallet_kill_001",
                lemma_type="ishuman",
                revocation_type="wallet",
                revoked_by="test",
                reason="wallet revoke",
            ),
        ]
    )

    revoked_keys: list[str] = []

    class _Verifier:
        def revoke_credential(self, key):
            revoked_keys.append(key)

    monkeypatch.setattr("api.permission_verification._global_verifier", _Verifier())
    monkeypatch.setattr("api.database.get_db", lambda: db.session_local())

    sync_revocations_to_bloom()

    assert "cred_abc" in revoked_keys
    assert "did:lemma:ppid_wallet_keys" in revoked_keys
    assert "wallet_kill_001" in revoked_keys
