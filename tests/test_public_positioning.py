"""Public marketing pages lead with human proofs; lemma.id is the platform layer."""

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
def test_homepage_leads_with_human_proofs(public_client):
    resp = public_client.get("/home")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Human proofs for abuse-resistant accounts" in body
    assert "Stop the same abuser" in body
    assert "Passkey continuity" in body
    assert "not Sybil-resistant by itself" in body
    assert "requiredAssurance: 'ishuman'" in body
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
    assert "same returning wallet" in body.lower() or "returning wallet" in body.lower()


@pytest.mark.integration
def test_pricing_page_mentions_human_proof_enforcement(public_client):
    resp = public_client.get("/pricing")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "human-proof-backed enforcement" in body or "human proofs + lemma.id" in body
    assert "without IDV up front" in body or "no IDV up front" in body


@pytest.mark.unit
def test_index_template_ties_rotation_resistance_to_ishuman():
    index = (ROOT / "templates" / "modern" / "index.html").read_text(encoding="utf-8")
    assert "With human proofs required, swapping email, SIM, device, or IP no longer gives an abuser a clean slate" in index
    assert "not Sybil-resistant by itself" in index


@pytest.mark.unit
def test_docs_page_clarifies_human_vs_assurance():
    docs = (ROOT / "templates" / "docs" / "ishuman.html").read_text(encoding="utf-8")
    assert "human</code> vs <code>assurance" in docs
    assert "requiredAssurance: 'ishuman'" in docs or "requiredAssurance: &apos;ishuman&apos;" in docs
    assert "passkey success does not mean IDV-backed humanness" in docs
