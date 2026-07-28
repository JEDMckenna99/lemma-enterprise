"""Rate limits for POST /api/ishuman/derive-site-proof."""

from __future__ import annotations

import pytest

from tests.wallet_test_helpers import SITE_SIGNING_PUBKEY_B64

NO_MASTER_ASSERTION_FIELDS = ["target_site", "site_signing_pubkey", "issue_mode"]


def _patch_issuance(monkeypatch):
    monkeypatch.setattr(
        "api.ishuman._derive_ppid_for_site",
        lambda **_kwargs: "did:lemma:ppid_rate_limit_test",
    )
    monkeypatch.setattr(
        "api.ishuman._issue_ishuman_credential",
        lambda ppid, wallet_id=None, site_id=None, **kwargs: {
            "id": "ishuman_site_rate_limit_001",
            "subject": ppid,
            "wallet_id": wallet_id,
            "claims": {"isHuman": True, "siteId": site_id or "example.com"},
            "issuer": "did:lemma:test",
        },
    )


def _derive_body(wallet_id: str = "wallet_rate_limit_001", target_site: str = "example.com"):
    return {
        "wallet_id": wallet_id,
        "wallet_secret": "ab" * 32,
        "target_site": target_site,
        "site_signing_pubkey": SITE_SIGNING_PUBKEY_B64,
    }


@pytest.mark.unit
def test_derive_site_proof_under_wallet_limit_succeeds(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api import rate_limiter

    monkeypatch.setattr(rate_limiter, "REDIS_AVAILABLE", False)
    monkeypatch.setenv("LEMMA_API_RATE_LIMIT_DEGRADED_MODE", "memory")

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_rl_ok",
            wallet_id="wallet_rate_limit_001",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issuance(monkeypatch)

    resp = ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(_derive_body(), NO_MASTER_ASSERTION_FIELDS),
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["success"] is True


@pytest.mark.unit
def test_derive_site_proof_wallet_rate_limit_returns_429(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api import rate_limiter

    monkeypatch.setattr(rate_limiter, "REDIS_AVAILABLE", False)
    monkeypatch.setenv("LEMMA_API_RATE_LIMIT_DEGRADED_MODE", "memory")

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_rl_block",
            wallet_id="wallet_rate_limit_block",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issuance(monkeypatch)

    statuses = []
    for _ in range(11):
        resp = ishuman_client.post(
            "/api/ishuman/derive-site-proof",
            json=attach_wallet_assertion(
                _derive_body(wallet_id="wallet_rate_limit_block"),
                NO_MASTER_ASSERTION_FIELDS,
            ),
        )
        statuses.append(resp.status_code)

    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
    assert ishuman_client.post(
        "/api/ishuman/derive-site-proof",
        json=attach_wallet_assertion(
            _derive_body(wallet_id="wallet_rate_limit_block"),
                NO_MASTER_ASSERTION_FIELDS,
        ),
    ).get_json()["error"] == "derive_site_proof_rate_limited"


@pytest.mark.unit
def test_derive_site_proof_rate_limit_fail_open_when_redis_down(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    from api import rate_limiter

    monkeypatch.setattr(rate_limiter, "REDIS_AVAILABLE", False)
    monkeypatch.setenv("LEMMA_API_RATE_LIMIT_DEGRADED_MODE", "fail_open")

    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_rl_failopen",
            wallet_id="wallet_rate_limit_failopen",
            status="verified",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)
    _patch_issuance(monkeypatch)

    statuses = []
    for _ in range(12):
        resp = ishuman_client.post(
            "/api/ishuman/derive-site-proof",
            json=attach_wallet_assertion(
                _derive_body(wallet_id="wallet_rate_limit_failopen"),
                NO_MASTER_ASSERTION_FIELDS,
            ),
        )
        statuses.append(resp.status_code)

    assert all(status == 200 for status in statuses)
