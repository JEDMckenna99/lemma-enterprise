"""Live platform/admin read-only checks against staging."""

from __future__ import annotations

import pytest

requests = pytest.importorskip("requests")

from tests.live.live_test_helpers import get_json, post_json, require_platform_staging_env  # noqa: E402

pytestmark = pytest.mark.live_platform

FAKE_PPID = "did:lemma:ppid_" + ("c" * 64)


def test_live_staging_platform_health_and_admin_guards():
    base = require_platform_staging_env()
    session = requests.Session()

    status, data = get_json(session, base, "/api/health")
    assert status == 200, data
    assert data.get("status") == "ok", data

    status, data = get_json(session, base, "/api/health/check")
    assert status in (200, 206, 503), data
    assert "status" in data, data

    status, _ = get_json(session, base, "/admin/bootstrap")
    assert status == 200, f"/admin/bootstrap expected 200, got {status}"

    status, data = get_json(session, base, "/api/admin/platform-stats")
    assert status in (401, 403), data
    if status == 401:
        assert data.get("error") == "auth_required", data

    for path in ("/login", "/register", "/docs"):
        status, _ = get_json(session, base, path)
        assert status == 200, f"{path} expected 200, got {status}"

    for path in ("/sdk/ishuman-verifier.js", "/static/js/lemma-wallet.js"):
        status, _ = get_json(session, base, path)
        assert status == 200, f"{path} expected 200, got {status}"

    status, _ = get_json(session, base, "/docs/operations/INTERNAL_COGS_ESTIMATE.md")
    assert status in (403, 404), f"internal docs should be blocked, got {status}"

    status, data = post_json(
        session,
        base,
        "/api/v1/iam/admin/platform-bootstrap/status",
        {"ppid": FAKE_PPID, "wallet_id": "wallet_probe_nonexistent"},
    )
    assert status == 200 and data.get("success") is True, data
