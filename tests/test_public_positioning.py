"""Public marketing pages lead with enforcement (one account per verified human).

Free Sign in with lemma.id is the on-ramp; human proofs are the headline claim.
Honest-copy invariants (passkey tier is not Sybil resistance, no revocation
overclaims) must survive any repositioning.
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
    assert "One account per verified human" in body
    # Free sign-in remains the on-ramp, present and named.
    assert "Sign in with lemma.id" in body
    assert "Passwordless login" in body
    assert "No user data to store" in body
    assert "lemma-signin" in body
    assert "requiredAssurance: 'passkey'" in body
    # Honest step-up framing stays: passkey tier alone is not Sybil resistance.
    assert "anyone can create another lemma.id" in body
    assert "Revoke everywhere" not in body
    assert "Network revocation" not in body


@pytest.mark.integration
def test_trust_page_distinguishes_passkey_and_human_proofs(public_client):
    resp = public_client.get("/trust")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Enforcement-grade assurance" in body
    assert "passkey" in body.lower()
    assert "human proofs" in body.lower()
    assert "returning lemma.id" in body.lower() or "lemma.id continuity" in body.lower()


@pytest.mark.integration
def test_pricing_page_leads_with_free_sign_in(public_client):
    resp = public_client.get("/pricing")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Sign-in is free" in body
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


@pytest.mark.integration
def test_docs_split_sign_in_first(public_client):
    """/docs is login-only; step-up material lives at /docs/human-proofs."""
    docs = public_client.get("/docs")
    body = docs.get_data(as_text=True)
    assert docs.status_code == 200
    assert "Sign in with lemma.id" in body
    assert "lemma-signin" in body
    assert "requiredAssurance: 'passkey'" in body
    # Step-up sections must not render on the sign-in page.
    assert "Global Bloom revocation" not in body
    assert "What you configure vs what lemma.id runs" not in body

    step_up = public_client.get("/docs/human-proofs")
    sbody = step_up.get_data(as_text=True)
    assert step_up.status_code == 200
    assert "Human proofs" in sbody
    assert "requiredAssurance: 'ishuman'" in sbody
    assert "Global Bloom revocation" in sbody

    legacy = public_client.get("/docs/ishuman", follow_redirects=True)
    assert legacy.status_code == 200
    assert legacy.request.path == "/docs/human-proofs"


@pytest.mark.unit
def test_index_template_ties_rotation_resistance_to_ishuman():
    index = (ROOT / "templates" / "modern" / "index.html").read_text(encoding="utf-8")
    assert "doesn't stop someone from making another" in index
    assert "anyone can create another lemma.id" in index


@pytest.mark.unit
def test_terms_page_avoids_absolute_zero_knowledge_claim():
    terms = (ROOT / "templates" / "legal" / "terms.html").read_text(encoding="utf-8")
    assert "Zero-Knowledge Verification" not in terms
    assert "Local Return-Visit Verification" in terms
    assert "without per-request calls to Lemma" in terms


@pytest.mark.unit
def test_docs_page_clarifies_human_vs_assurance():
    docs = (ROOT / "templates" / "docs" / "ishuman.html").read_text(encoding="utf-8")
    assert "human</code> vs <code>assurance" in docs
    assert "requiredAssurance: 'ishuman'" in docs or "requiredAssurance: &apos;ishuman&apos;" in docs
    assert "passkey success does not mean IDV-backed humanness" in docs
