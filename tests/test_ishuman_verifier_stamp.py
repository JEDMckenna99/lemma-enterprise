"""Pins the SDK helpers that let a relying site attach the verified identity
to its own logs (getPPID / getVerification / stamp).

These are source-pattern assertions against the browser SDK (consistent with the
other ishuman-verifier tests) plus a check that the served SDK version is bumped
in lockstep across the file, the Flask route header, and the demo cache-bust.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "static" / "js" / "ishuman-verifier.js"
APP_PATH = ROOT / "app.py"
DEMO_PATH = ROOT / "templates" / "demo" / "ishuman.html"
DOCS_PATH = ROOT / "templates" / "docs" / "ishuman.html"


@pytest.fixture(name="verifier_source")
def fixture_verifier_source() -> str:
    return VERIFIER_PATH.read_text(encoding="utf-8")


@pytest.mark.browser
def test_sdk_exposes_get_ppid(verifier_source):
    assert "async getPPID(options = {})" in verifier_source
    # Never opens a popup by default.
    assert "this.verify({ autoProvision: false, ...options })" in verifier_source
    assert "return result.human ? result.ppid : null;" in verifier_source


@pytest.mark.browser
def test_sdk_exposes_get_verification_stamp(verifier_source):
    assert "async getVerification(options = {})" in verifier_source
    # Compact stamp fields the site logs.
    for field in (
        "verified:",
        "ppid:",
        "reason:",
        "siteId:",
        "verifiedAt:",
        "expiresAt,",
        "credentialId:",
    ):
        assert field in verifier_source, f"stamp field {field!r} missing"
    # Optional cryptographic proof only when explicitly requested.
    assert "if (options.includeProof) {" in verifier_source
    assert "stamp.proof = result.presentation || null;" in verifier_source
    # VC-first: bare credential is the recommended durable evidence.
    assert "} else if (options.includeCredential) {" in verifier_source
    assert "stamp.credential = result.credential || null;" in verifier_source


@pytest.mark.browser
def test_sdk_exposes_stamp_merge_helper(verifier_source):
    assert "async stamp(payload = {}, options = {})" in verifier_source
    # Configurable merge key, defaults to 'lemma', and does not mutate input.
    assert "const key = options.key || 'lemma';" in verifier_source
    assert "return { ...payload, [key]: verification };" in verifier_source


@pytest.mark.browser
def test_sdk_version_bumped_in_lockstep():
    from api.sdk_versions import ISHUMAN_VERIFIER_SDK_VERSION

    verifier = VERIFIER_PATH.read_text(encoding="utf-8")
    app = APP_PATH.read_text(encoding="utf-8")
    demo = DEMO_PATH.read_text(encoding="utf-8")
    relying = (ROOT / "demo-sites" / "relying_site_app.py").read_text(encoding="utf-8")
    version = ISHUMAN_VERIFIER_SDK_VERSION
    assert f"@version {version}" in verifier
    assert "ISHUMAN_VERIFIER_SDK_VERSION" in app
    assert f"ishuman_verifier_sdk_version" in demo
    assert f"ISHUMAN_VERIFIER_SDK_VERSION" in relying


def test_docs_document_stamp_pattern():
    docs = DOCS_PATH.read_text(encoding="utf-8")
    assert "Attach the verification to your own logs" in docs
    assert "getVerification" in docs
    assert "ih.stamp(" in docs
    # Reinforces the data-stays-with-you positioning.
    assert "lemma.id stores none of it" in docs
    # VC-first guidance present.
    assert "includeCredential" in docs
