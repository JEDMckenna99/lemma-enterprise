"""Tests for site-scoped PPID migration after document refresh."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.unit
def test_pin_pending_merge_metadata_sets_person_id():
    from api.ppid_migration import pin_pending_merge_metadata

    binding = SimpleNamespace(wallet_id="wallet_a", lemma_person_id="person_old")
    db = SimpleNamespace(
        query=lambda model: SimpleNamespace(
            filter_by=lambda **kwargs: SimpleNamespace(
                first=lambda: binding if kwargs.get("wallet_id") == "wallet_a" else None
            )
        )
    )
    meta = pin_pending_merge_metadata(db, wallet_id="wallet_a", metadata={"return_url": "https://x"})
    assert meta["pending_merge_from_person_id"] == "person_old"
    assert "merge_pinned_at_unix" in meta


@pytest.mark.unit
def test_wallet_merge_allowed_when_pinned(monkeypatch):
    from api.identity_person import material_from_test_fixture, resolve_or_create_person_from_material

    binding = SimpleNamespace(
        wallet_id="wallet_a",
        lemma_person_id="person_old",
        updated_at=None,
    )
    added = []

    class FakeQuery:
        def __init__(self, model):
            self.model = model
            self._kwargs = {}

        def filter_by(self, **kwargs):
            self._kwargs = kwargs
            return self

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            name = getattr(self.model, "__tablename__", str(self.model))
            if name == "lemma_document_roots":
                return None
            if name == "lemma_wallet_bindings" and self._kwargs.get("wallet_id") == "wallet_a":
                return binding
            return None

    db = SimpleNamespace(query=lambda model: FakeQuery(model), add=lambda obj: added.append(obj))

    monkeypatch.setattr("api.column_crypto.encrypt_column", lambda value: value)

    resolved = resolve_or_create_person_from_material(
        db,
        material=material_from_test_fixture(document_number="NEW_DOC_001"),
        wallet_id="wallet_a",
        provider="didit",
        allow_wallet_person_merge=True,
        merge_from_person_id="person_old",
    )
    assert resolved.merged_from_person_id == "person_old"
    assert binding.lemma_person_id == resolved.person_id


@pytest.mark.unit
def test_wallet_merge_still_fails_without_pin(monkeypatch):
    from api.identity_person import (
        WalletPersonBindingConflictError,
        material_from_test_fixture,
        resolve_or_create_person_from_material,
    )

    binding = SimpleNamespace(wallet_id="wallet_a", lemma_person_id="person_old")
    db = SimpleNamespace(
        query=lambda model: SimpleNamespace(
            filter_by=lambda **kwargs: SimpleNamespace(
                first=lambda: (
                    binding if kwargs.get("wallet_id") == "wallet_a" else None
                )
            ),
            filter=lambda *args, **kwargs: SimpleNamespace(first=lambda: None),
            order_by=lambda *args, **kwargs: SimpleNamespace(first=lambda: None),
        ),
        add=lambda obj: None,
    )
    monkeypatch.setattr("api.column_crypto.encrypt_column", lambda value: value)
    with pytest.raises(WalletPersonBindingConflictError):
        resolve_or_create_person_from_material(
            db,
            material=material_from_test_fixture(document_number="NEW_DOC_002"),
            wallet_id="wallet_a",
            provider="didit",
        )


@pytest.mark.unit
def test_migration_canonical_message_is_stable():
    from api.ppid_migration import PPID_MIGRATION_TYPE, build_migration_canonical_message

    payload = {
        "type": PPID_MIGRATION_TYPE,
        "mergeId": "merge_abc",
        "siteId": "example.com",
        "legacyPpid": "did:lemma:ppid_old",
        "currentPpid": "did:lemma:ppid_new",
        "walletId": "wallet_x",
        "nonce": "nonce_y",
        "issuedAt": 1710000000,
        "expiresAt": 1710003600,
    }
    msg = build_migration_canonical_message(payload)
    assert msg.startswith(b"lemma:ppid-migration:v1\n")
    assert b"example.com" in msg


@pytest.mark.unit
def test_verify_ppid_migration_signature_roundtrip(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from api.ppid_migration import (
        PPID_MIGRATION_TYPE,
        sign_ppid_migration_payload,
        verify_ppid_migration_signature,
    )

    sk = Ed25519PrivateKey.generate()
    pk_hex = sk.public_key().public_bytes_raw().hex()

    class FakeIssuer:
        def signing_key_bytes(self):
            return sk.private_bytes_raw()

        def get_did(self):
            return "did:lemma:issuer_test"

        def get_public_key_hex(self):
            return pk_hex

    monkeypatch.setattr("api.ishuman._get_ishuman_issuer", lambda: FakeIssuer())

    payload = {
        "type": PPID_MIGRATION_TYPE,
        "mergeId": "merge_test",
        "siteId": "app.example.com",
        "legacyPpid": "did:lemma:ppid_a",
        "currentPpid": "did:lemma:ppid_b",
        "walletId": "wallet_test",
        "nonce": "n1",
        "issuedAt": 1710000000,
        "expiresAt": 1710003600,
    }
    signed = sign_ppid_migration_payload(payload)
    assert verify_ppid_migration_signature(signed, pk_hex) is True
    tampered = {**signed, "legacyPpid": "did:lemma:ppid_evil"}
    assert verify_ppid_migration_signature(tampered, pk_hex) is False


@pytest.mark.unit
def test_confirm_ppid_migration_endpoint(ishuman_client, monkeypatch):
    fake_site = SimpleNamespace(site_id="site_test", site_domain="legacy.example.com", admin_email="ops@test")
    monkeypatch.setattr("api.ishuman._require_site_api_key", lambda: fake_site)
    monkeypatch.setattr("api.rate_limiter.check_rate_limit", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "api.ppid_migration.confirm_ppid_migration_for_site",
        lambda db, **kwargs: {
            "approved": True,
            "merge_id": "merge_test_1",
            "migration_id": "mig_test_1",
        },
    )

    resp = ishuman_client.post(
        "/api/ishuman/confirm-ppid-migration",
        headers={"X-API-Key": "lm_legacy_direct_key", "Content-Type": "application/json"},
        json={
            "legacy_ppid": "did:lemma:ppid_" + ("a" * 64),
            "current_ppid": "did:lemma:ppid_" + ("b" * 64),
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["approved"] is True
    assert data["merge_id"] == "merge_test_1"


@pytest.mark.unit
def test_confirm_ppid_migration_requires_api_key(ishuman_client):
    resp = ishuman_client.post(
        "/api/ishuman/confirm-ppid-migration",
        json={
            "legacy_ppid": "did:lemma:ppid_" + ("a" * 64),
            "current_ppid": "did:lemma:ppid_" + ("b" * 64),
        },
    )
    assert resp.status_code == 401


@pytest.mark.unit
def test_confirm_ppid_migration_rejects_unapproved_pair(monkeypatch):
    from api.ppid_migration import confirm_ppid_migration_for_site

    db = SimpleNamespace(
        query=lambda model: SimpleNamespace(
            filter_by=lambda **kwargs: SimpleNamespace(
                filter=lambda *a, **k: SimpleNamespace(
                    order_by=lambda *a, **k: SimpleNamespace(first=lambda: None)
                ),
                order_by=lambda *a, **k: SimpleNamespace(first=lambda: None),
                first=lambda: None,
            ),
            filter=lambda *a, **k: SimpleNamespace(
                order_by=lambda *a, **k: SimpleNamespace(limit=lambda n: SimpleNamespace(all=lambda: []))
            ),
        )
    )
    result = confirm_ppid_migration_for_site(
        db,
        target_site="example.com",
        legacy_ppid="did:lemma:ppid_" + ("a" * 64),
        current_ppid="did:lemma:ppid_" + ("b" * 64),
    )
    assert result["approved"] is False
