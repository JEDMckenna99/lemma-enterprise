from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from app import build_content_security_policy, resolve_csp_profile

PROFILE_SCRIPT_ORIGINS = {
    "strict": [],
    "unlock_idv": [
        "https://challenges.cloudflare.com",
        "https://js.stripe.com",
    ],
    "link_qr": [
        "https://challenges.cloudflare.com",
        "https://js.stripe.com",
        "https://unpkg.com/",
    ],
}


@pytest.mark.unit
@pytest.mark.parametrize("profile,origin", [
    ("strict", "https://js.stripe.com"),
    ("strict", "https://unpkg.com/"),
    ("strict", "https://cdn.jsdelivr.net/npm/"),
    ("strict", "https://static.cloudflareinsights.com"),
])
def test_strict_profile_excludes_third_party_script_origins(profile, origin):
    csp = build_content_security_policy("testnonce", profile)
    script_src = csp.split("script-src ", 1)[1].split("; ", 1)[0]
    assert origin not in script_src
    assert "'self'" in script_src
    assert "'nonce-testnonce'" in script_src


@pytest.mark.unit
@pytest.mark.parametrize("profile", ["unlock_idv", "link_qr"])
def test_unlock_and_link_profiles_allow_stripe_and_turnstile(profile):
    csp = build_content_security_policy("nonce123", profile)
    script_src = csp.split("script-src ", 1)[1].split("; ", 1)[0]
    for origin in PROFILE_SCRIPT_ORIGINS[profile]:
        assert origin in script_src


@pytest.mark.unit
def test_link_qr_profile_allows_unpkg_only_on_link_routes():
    link_csp = build_content_security_policy("nonce123", "link_qr")
    unlock_csp = build_content_security_policy("nonce123", "unlock_idv")
    assert "https://unpkg.com/" in link_csp
    assert "https://unpkg.com/" not in unlock_csp


@pytest.mark.unit
def test_csp_disallows_unsafe_inline_and_eval_in_script_src():
    csp = build_content_security_policy("nonce123", "link_qr")
    script_src = csp.split("script-src ", 1)[1].split("; ", 1)[0]
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src


@pytest.mark.unit
def test_csp_includes_report_uri():
    csp = build_content_security_policy("nonce123", "strict")
    assert "report-uri /api/security/csp-report" in csp


@pytest.mark.unit
@pytest.mark.parametrize("path,expected", [
    ("/", "strict"),
    ("/dashboard", "strict"),
    ("/unlock", "unlock_idv"),
    ("/wallet/unlock", "unlock_idv"),
    ("/wallet/popup", "unlock_idv"),
    ("/wallet/ishuman-idv", "unlock_idv"),
    ("/link", "link_qr"),
    ("/wallet/link", "link_qr"),
])
def test_resolve_csp_profile_for_routes(path, expected):
    assert resolve_csp_profile(path) == expected


@pytest.mark.unit
def test_csp_report_endpoint_exists():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def csp_report():" in app_source
    assert "build_content_security_policy" in app_source


@pytest.mark.unit
def test_csp_report_endpoint_accepts_violation_payload():
    from app import create_app

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/security/csp-report",
        json={
            "csp-report": {
                "violated-directive": "script-src",
                "blocked-uri": "https://evil.example.invalid",
                "document-uri": "https://lemma.id/",
            }
        },
        content_type="application/csp-report",
    )
    assert response.status_code == 204


@pytest.mark.unit
def test_csp_response_headers_differ_by_route():
    from app import create_app

    app = create_app()
    client = app.test_client()

    home = client.get("/")
    unlock = client.get("/unlock")
    link = client.get("/link")

    home_csp = home.headers.get("Content-Security-Policy", "")
    unlock_csp = unlock.headers.get("Content-Security-Policy", "")
    link_csp = link.headers.get("Content-Security-Policy", "")

    assert "https://js.stripe.com" not in home_csp
    assert "https://js.stripe.com" in unlock_csp
    assert "https://unpkg.com/" in link_csp
    assert "https://unpkg.com/" not in home_csp
