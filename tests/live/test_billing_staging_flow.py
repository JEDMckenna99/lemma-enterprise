"""Live billing guardrail checks against staging (unauth fail-closed)."""

from __future__ import annotations

import pytest

requests = pytest.importorskip("requests")

from tests.live.live_test_helpers import get_json, post_json, require_platform_staging_env  # noqa: E402

pytestmark = pytest.mark.live_platform


def test_live_staging_billing_unauthenticated_guardrails():
    base = require_platform_staging_env()
    session = requests.Session()

    status, _ = get_json(session, base, "/api/billing/usage/cus_smoke_nonexistent")
    assert status in (401, 403, 404), f"usage read should deny unauthenticated callers, got {status}"

    status, _ = get_json(session, base, "/api/billing/account-status")
    assert status in (401, 403), f"account-status should deny unauthenticated callers, got {status}"

    status, _ = post_json(session, base, "/api/billing/usage-checkout", {})
    assert status in (400, 401, 403), f"usage-checkout should deny unauthenticated callers, got {status}"

    status, _ = post_json(session, base, "/api/billing/create-checkout", {})
    assert status in (400, 401, 403), f"create-checkout should deny unauthenticated callers, got {status}"
