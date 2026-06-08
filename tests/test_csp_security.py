from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_PY = ROOT / "app.py"

EXPECTED_SCRIPT_ORIGINS = [
    "https://cdn.jsdelivr.net/npm/",
    "https://unpkg.com/",
    "https://static.cloudflareinsights.com",
    "https://challenges.cloudflare.com",
    "https://js.stripe.com",
]


@pytest.fixture(name="app_source")
def fixture_app_source() -> str:
    return APP_PY.read_text(encoding="utf-8")


@pytest.mark.unit
def test_csp_script_src_disallows_unsafe_inline_and_eval(app_source):
    csp_start = app_source.index('csp = (')
    csp_block = app_source[csp_start:csp_start + 3500]
    assert "'unsafe-inline'" not in csp_block.split("script-src", 1)[1].split("style-src", 1)[0]
    assert "'unsafe-eval'" not in csp_block.split("script-src", 1)[1].split("style-src", 1)[0]


@pytest.mark.unit
def test_csp_lists_expected_third_party_script_origins(app_source):
    for origin in EXPECTED_SCRIPT_ORIGINS:
        assert origin in app_source
        assert f"CSP-ALLOW:" in app_source


@pytest.mark.unit
def test_csp_includes_report_uri(app_source):
    assert "report-uri /api/security/csp-report" in app_source
    assert "/api/security/csp-report" in app_source


@pytest.mark.unit
def test_csp_report_endpoint_exists(app_source):
    assert "def csp_report():" in app_source
