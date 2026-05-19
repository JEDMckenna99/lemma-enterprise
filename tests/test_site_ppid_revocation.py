from __future__ import annotations

from datetime import datetime, timedelta

import pytest


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
        json={
            "master_credential_id": "ishuman_master_block_001",
            "wallet_id": "wallet_test_001",
            "wallet_secret": "ab" * 32,
            "target_site": "example.com",
        },
    )

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "site_ppid_blocked"


@pytest.mark.unit
def test_derive_site_proof_denies_master_credential_bloom_revocation(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
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
        json={
            "master_credential_id": "ishuman_master_bloom_001",
            "wallet_id": "wallet_test_001",
            "wallet_secret": "ab" * 32,
            "target_site": "example.com",
        },
    )

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "master_credential_revoked"


@pytest.mark.unit
def test_derive_site_proof_denies_site_ppid_bloom_revocation(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
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
        json={
            "master_credential_id": "ishuman_master_ppid_bloom_001",
            "wallet_id": "wallet_test_001",
            "wallet_secret": "ab" * 32,
            "target_site": "example.com",
        },
    )

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "site_ppid_revoked"


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
