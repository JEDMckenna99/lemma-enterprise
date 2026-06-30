"""Phase 1.3 — /api/ishuman/reissue-master.

A verified wallet can re-fetch a freshly signed master credential without a new
IDV. The old master id is revoked (lands in the Bloom snapshot source), the new
credential keeps the same PPID, unverified wallets get 404, and the endpoint is
rate-limited per wallet per day.
"""

from __future__ import annotations

import pytest


def _patch_issue(monkeypatch, new_id="ishuman_master_reissued_001"):
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": new_id,
            "subject": ppid,
            "wallet_id": wallet_id,
            "claims": {"isHuman": True, "siteId": site_id or "lemma.id"},
            "issuer": "did:lemma:test",
        },
    )


@pytest.mark.unit
def test_verified_wallet_can_reissue_with_new_id_same_ppid(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api.database import IsHumanVerification, RevocationList

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_old_001",
            wallet_id="wallet_test_001",
            ppid="did:lemma:ppid_stable_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issue(monkeypatch)

    resp = ishuman_client.post(
        "/api/ishuman/reissue-master",
        json=attach_wallet_assertion(
            {"wallet_id": "wallet_test_001", "wallet_secret": "ab" * 32},
            ["wallet_id"],
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["success"] is True
    assert payload["credential"]["id"] == "ishuman_master_reissued_001"
    assert payload["old_credential_id"] == "ishuman_master_old_001"
    # New id, same PPID.
    assert payload["credential"]["subject"] == "did:lemma:ppid_stable_001"
    row = db.store.data[IsHumanVerification.__name__][0]
    assert row.credential_id == "ishuman_master_reissued_001"
    assert row.metadata_json["reissued_from"] == "ishuman_master_old_001"
    # Old id revoked (lands in Bloom snapshot source).
    revocations = db.store.data[RevocationList.__name__]
    assert any(r.credential_id == "ishuman_master_old_001" for r in revocations)


@pytest.mark.unit
def test_unverified_wallet_reissue_returns_404(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
    attach_wallet_assertion,
):
    db = fake_ishuman_db_session_factory  # no verified rows
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issue(monkeypatch)

    resp = ishuman_client.post(
        "/api/ishuman/reissue-master",
        json=attach_wallet_assertion(
            {"wallet_id": "wallet_unverified_404", "wallet_secret": "ab" * 32},
            ["wallet_id"],
        ),
    )

    payload = resp.get_json()
    assert resp.status_code == 404, payload
    assert payload["error"] == "wallet_not_verified"


@pytest.mark.unit
def test_reissue_requires_wallet_assertion(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issue(monkeypatch)

    resp = ishuman_client.post(
        "/api/ishuman/reissue-master",
        json={"wallet_id": "wallet_test_001"},
    )
    payload = resp.get_json()
    assert resp.status_code == 403, payload
    assert payload["error"].startswith("wallet_assertion")


@pytest.mark.unit
def test_reissue_is_rate_limited_per_wallet(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api import rate_limiter

    # Force deterministic in-process limiting regardless of local Redis.
    monkeypatch.setattr(rate_limiter, "REDIS_AVAILABLE", False)
    monkeypatch.setenv("LEMMA_ISHUMAN_REISSUE_LIMIT_PER_DAY", "2")
    monkeypatch.setenv("LEMMA_API_RATE_LIMIT_DEGRADED_MODE", "memory")

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_rl_001",
            wallet_id="wallet_ratelimit_xyz",
            ppid="did:lemma:ppid_rl",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issue(monkeypatch)

    statuses = []
    for _ in range(3):
        resp = ishuman_client.post(
            "/api/ishuman/reissue-master",
            json=attach_wallet_assertion(
                {"wallet_id": "wallet_ratelimit_xyz", "wallet_secret": "ab" * 32},
                ["wallet_id"],
            ),
        )
        statuses.append(resp.status_code)

    assert statuses[0] == 200
    assert statuses[1] == 200
    assert statuses[2] == 429


@pytest.mark.unit
def test_reissue_master_for_platform_owner_includes_admin_access(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    owner_ppid = "did:lemma:ppid_platform_owner_001"

    def _issue_owner_master(ppid, wallet_id=None, site_id=None, **kwargs):
        return {
            "id": "ishuman_master_owner_reissued",
            "subject": ppid,
            "issuer": "did:lemma:testissuer",
            "claims": {
                "isHuman": True,
                "siteId": "lemma.id",
                "permissionId": "admin_access",
            },
            "credentialSubject": {
                "isHuman": True,
                "siteId": "lemma.id",
                "permissionId": "admin_access",
            },
            "proof": {"signatureValueWeb": "ab" * 64},
        }

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_owner_old",
            wallet_id="wallet_owner_001",
            ppid=owner_ppid,
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    monkeypatch.setattr("api.ishuman._issue_ishuman_credential", _issue_owner_master)
    monkeypatch.setattr("api.platform_owner.is_platform_owner_ppid", lambda ppid: ppid == owner_ppid)

    resp = ishuman_client.post(
        "/api/ishuman/reissue-master",
        json=attach_wallet_assertion(
            {"wallet_id": "wallet_owner_001", "wallet_secret": "ab" * 32},
            ["wallet_id"],
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    claims = payload["credential"].get("claims") or payload["credential"].get("credentialSubject") or {}
    assert claims.get("permissionId") == "admin_access"
    assert payload["credential"]["proof"].get("signatureValueWeb")
    assert payload["credential"]["subject"] == owner_ppid
