"""Public marketing pages lead with enforcement (IDV-backed / document uniqueness).

Free passkey continuity / local verify is the on-ramp; human proofs are the headline claim.
Honest-copy invariants (passkey tier is not Sybil resistance, document uniqueness
not biometric unique-human, no revocation overclaims) must survive any repositioning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(name="public_client")
def fixture_public_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.mark.integration
def test_homepage_leads_with_enforcement(public_client):
    resp = public_client.get("/home")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # Enforcement is the headline; hero leads with the consequence claim.
    assert "they stay banned" in body
    assert "One account per verified document" in body
    assert "document uniqueness" in body.lower()
    # Free passkey continuity remains the on-ramp, present via component + code sample.
    assert "lemma.id proof layer" in body
    assert "lemma-signin" in body
    assert "Passkey for continuity" in body
    assert "local verify" in body.lower()
    assert "requiredAssurance" in body
    assert "/demo/how-it-works?lane=builder" in body
    # Honest step-up framing stays: passkey tier alone is not Sybil resistance.
    assert "anyone can create another lemma.id" in body
    assert "Revoke everywhere" not in body
    assert "Network revocation" not in body
    # Do not ship absolute unique-human overclaims on the homepage.
    assert "One account per verified human" not in body
    assert "one verified human per account" not in body.lower()


@pytest.mark.integration
def test_trust_page_distinguishes_passkey_and_human_proofs(public_client):
    resp = public_client.get("/trust")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Enforcement-grade assurance" in body
    assert "passkey" in body.lower()
    assert "human proofs" in body.lower()
    assert "returning lemma.id" in body.lower() or "lemma.id continuity" in body.lower()
    assert "document uniqueness" in body.lower()
    assert "distinct documents can still mint distinct persons" in body.lower()
    assert "one verified human" not in body.lower()


@pytest.mark.integration
def test_pricing_page_leads_with_free_local_verify(public_client):
    resp = public_client.get("/pricing")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Local verify is free" in body
    assert "no card required" in body
    assert "Free forever, not a trial" in body
    assert "human proof" in body.lower()
    assert "identity check is included" in body or "no separate IDV charge" in body


@pytest.mark.integration
def test_trust_page_answers_objections_with_evidence(public_client):
    resp = public_client.get("/trust")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "The objections, answered directly" in body
    assert "Is this a biometric database?" in body
    assert "status.lemma.id" in body
    # Pending assurance work is disclosed, never implied complete.
    assert "not yet complete" in body


@pytest.mark.integration
def test_ticketing_page_links_live_presale_demo(public_client):
    resp = public_client.get("/ticketing")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "?tour=presale" in body
    assert "/docs/demo/PRESALE_DEMO_SCRIPT.md" in body
    assert "Multi-document farming" in body


@pytest.mark.integration
def test_docs_split_continuity_first(public_client):
    """/docs leads with proof continuity; step-up material lives at /docs/human-proofs."""
    docs = public_client.get("/docs")
    body = docs.get_data(as_text=True)
    assert docs.status_code == 200
    assert "Proof continuity for your site" in body
    assert "lemma-signin" in body
    assert "requiredAssurance" in body
    # Step-up sections must not render on the continuity page.
    assert "Global Bloom revocation" not in body
    assert "What you configure vs what lemma.id runs" not in body

    step_up = public_client.get("/docs/human-proofs")
    sbody = step_up.get_data(as_text=True)
    assert step_up.status_code == 200
    assert "Human proofs" in sbody
    assert "requiredAssurance: 'ishuman'" in sbody
    assert "Global Bloom revocation" in sbody
    assert "Uniqueness bound" in sbody
    assert "per verified government document" in sbody
    assert "not biometric unique-human" in sbody

    legacy = public_client.get("/docs/ishuman", follow_redirects=True)
    assert legacy.status_code == 200
    assert legacy.request.path == "/docs/human-proofs"


@pytest.mark.unit
def test_index_template_ties_rotation_resistance_to_ishuman():
    index = (ROOT / "templates" / "modern" / "index.html").read_text(encoding="utf-8")
    assert "does not stop someone from making another" in index
    assert "anyone can create another lemma.id" in index
    assert "One account per verified document" in index
    assert "Distinct documents can still mint distinct persons" in index
    assert "US or Canadian" in index


@pytest.mark.unit
def test_terms_page_avoids_absolute_zero_knowledge_claim():
    terms = (ROOT / "templates" / "legal" / "terms.html").read_text(encoding="utf-8")
    assert "Zero-Knowledge Verification" not in terms
    assert "Local Return-Visit Verification" in terms
    assert "without per-request calls to Lemma" in terms
    assert "Browser Wallet" not in terms
    assert "99.5% uptime" not in terms
    assert "Professional:" not in terms
    assert "Didit" in terms
    assert "not biometric unique-human" in terms


@pytest.mark.unit
def test_privacy_page_matches_current_data_model():
    privacy = (ROOT / "templates" / "legal" / "privacy.html").read_text(encoding="utf-8")
    assert "Didit" in privacy
    assert "IndexedDB" in privacy
    assert "lemma_wallet_session" in privacy
    assert "unlinkable across sites" not in privacy
    assert "Professional:" not in privacy
    assert "7 years (compliance requirement)" not in privacy
    assert "we do not sell personal information" in privacy.lower()
    assert "not biometric unique-human" in privacy
    assert "Zero-Knowledge" not in privacy


@pytest.mark.unit
def test_docs_page_clarifies_human_vs_assurance():
    docs = (ROOT / "templates" / "docs" / "ishuman.html").read_text(encoding="utf-8")
    assert "human</code> vs <code>assurance" in docs
    assert "requiredAssurance: 'ishuman'" in docs or "requiredAssurance: &apos;ishuman&apos;" in docs
    assert "passkey success does not mean IDV-backed humanness" in docs
    assert "per verified government document" in docs


@pytest.mark.unit
def test_llms_and_public_guides_avoid_absolute_unique_human():
    llms = (ROOT / "llms.txt").read_text(encoding="utf-8")
    assert "document uniqueness" in llms.lower() or "per verified document" in llms.lower()
    assert "not biometric unique-human" in llms
    assert "one verified human per account" not in llms.lower()

    continuity = (ROOT / "docs" / "integration" / "CONTINUITY_AND_ABUSE.md").read_text(
        encoding="utf-8"
    )
    assert "Uniqueness (honest bound)" in continuity
    assert "not biometric" in continuity
    assert "unique-human" in continuity

    bounds = (ROOT / "docs" / "security" / "HUMAN_UNIQUENESS_BOUNDS.md").read_text(
        encoding="utf-8"
    )
    assert "one verified government document attestation" in bounds
    assert "Claim that is false" in bounds


@pytest.mark.unit
def test_public_source_links_use_lemma_proof_repo():
    """HN and docs must not 404 on the private enterprise repo."""
    paths = (
        ROOT / "docs" / "integration" / "SIGN_IN_TRUST_AND_RECOVERY.md",
        ROOT / "oss" / "specs" / "SIGN_IN_TRUST_AND_RECOVERY.md",
        ROOT / "docs" / "launch" / "SHOW_HN_SIGN_IN_WITH_LEMMA.md",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "lemma-enterprise/tree" not in text, path
        assert "github.com/JEDMckenna99/lemma-proof" in text, path
