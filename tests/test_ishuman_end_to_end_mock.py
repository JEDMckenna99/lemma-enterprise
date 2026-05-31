"""End-to-end isHuman flow with a MOCK identity (no Stripe IDV).

This exercises the *real* production code paths -- person-root derivation,
Ed25519 credential issuance + browser-canonical signature verification,
per-site pairwise PPIDs, Phase 1.1 seed envelopes, Phase 4 device transfer,
and Phase 3 root rotation -- swapping only:

  * Stripe Identity  -> ``material_from_test_fixture`` (placeholder document)
  * KMS-backed issuer -> a fixed dev seed loaded into the SAME
    ``PyMinimalIssuer`` class production uses.

It is intentionally hermetic: it builds its own temp SQLite engine so it does
not depend on (or pollute) the shared in-memory test DB. Skips cleanly when the
native ``lemma_crypto`` engine is not installed in the environment.
"""
from __future__ import annotations

import hashlib

import pytest

pytestmark = pytest.mark.integration

# Fixed 32-byte dev issuer seed (NOT a production key).
_DEV_ISSUER_SEED = b"e2e-dev-issuer-seed-0123456789!!"


@pytest.fixture
def real_db_session(tmp_path, monkeypatch):
    """A SQLAlchemy session bound to an isolated temp-file SQLite engine."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from api.database import Base

    db_path = tmp_path / "e2e.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    try:
        Base.metadata.create_all(engine)
    except Exception:  # pragma: no cover - some models may use PG-only types
        from api.database import (
            IsHumanVerification, LemmaPerson, LemmaDocumentRoot,
            LemmaWalletBinding, Site,
        )
        Base.metadata.create_all(
            engine,
            tables=[
                IsHumanVerification.__table__, LemmaPerson.__table__,
                LemmaDocumentRoot.__table__, LemmaWalletBinding.__table__,
                Site.__table__,
            ],
        )
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def dev_issuer(monkeypatch):
    """Inject a deterministic local issuer in place of the KMS-backed one."""
    lemma_crypto = pytest.importorskip("lemma_crypto")
    issuer = lemma_crypto.PyMinimalIssuer.from_seed(list(_DEV_ISSUER_SEED))
    monkeypatch.setattr("api.ishuman._get_ishuman_issuer", lambda: issuer)
    return issuer


def _verify_browser_sig(credential: dict) -> None:
    """Verify a credential exactly as the JS verifier / /verify endpoint does."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from api.ishuman import _browser_canonical_message

    pub = bytes.fromhex(credential["issuerInfo"]["publicKey"])
    sig = bytes.fromhex(credential["proof"]["signatureValueWeb"])
    digest = hashlib.sha256(_browser_canonical_message(credential)).digest()
    Ed25519PublicKey.from_public_bytes(pub).verify(sig, digest)


def test_full_mock_idv_to_verified_credential(real_db_session, dev_issuer, monkeypatch):
    monkeypatch.setenv("LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS", "true")
    monkeypatch.setenv("LEMMA_IDENTITY_ROOT_PEPPER_V2", "P" * 43)
    monkeypatch.setenv("LEMMA_PERSON_ROOT_SALT_V2", "Q" * 43)

    from api.identity_person import (
        material_from_test_fixture,
        resolve_or_create_person_from_material,
    )
    from api.ppid import derive_ppid_from_person_root_hash
    from api.ishuman import _issue_ishuman_credential, _derive_ppid_for_site

    db = real_db_session
    wallet_id = "wallet_e2e_demo_001"

    # 1. Mock IDV -> real person root (no Stripe).
    material = material_from_test_fixture(
        stripe_session_id="vs_e2e_mock_001", document_number="E2E-DEMO-001"
    )
    resolved = resolve_or_create_person_from_material(db, material=material, wallet_id=wallet_id)
    db.commit()
    assert len(resolved.person_root_hash) == 64

    # 2. Master credential issued with real Ed25519 + verifies.
    master_ppid = derive_ppid_from_person_root_hash(resolved.person_root_hash, "lemma.id")
    assert master_ppid.startswith("did:lemma:ppid_")
    master_cred = _issue_ishuman_credential(master_ppid, wallet_id, ppid_derivation="person_root_v1")
    assert master_cred.get("id")
    _verify_browser_sig(master_cred)  # raises if invalid

    # 2b. Tampered credential is rejected.
    tampered = dict(master_cred)
    tampered["claims"] = {**master_cred["claims"], "isHuman": False}
    with pytest.raises(Exception):
        _verify_browser_sig(tampered)

    # 3. Same document -> same person_root (recovery / continuity).
    resolved_dup = resolve_or_create_person_from_material(
        db,
        material=material_from_test_fixture(
            stripe_session_id="vs_e2e_mock_dup", document_number="E2E-DEMO-001"
        ),
        wallet_id="wallet_other_device",
    )
    db.commit()
    assert resolved_dup.person_root_hash == resolved.person_root_hash

    # 4. Per-site PPIDs: deterministic + pairwise unlinkable.
    site_a = _derive_ppid_for_site(rp_id="tickets-demo.lemma.id", lemma_person_id=resolved.person_id, db=db)
    site_b = _derive_ppid_for_site(rp_id="trials-demo.lemma.id", lemma_person_id=resolved.person_id, db=db)
    site_a_again = _derive_ppid_for_site(rp_id="tickets-demo.lemma.id", lemma_person_id=resolved.person_id, db=db)
    assert site_a == site_a_again
    assert len({master_ppid, site_a, site_b}) == 3

    site_cred = _issue_ishuman_credential(
        site_a, wallet_id, site_id="site_demo_tickets", ppid_derivation="person_root_v1"
    )
    _verify_browser_sig(site_cred)

    # 5. Phase 1.1 seed envelopes: seal/open round-trip + client/server PPID parity.
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from api.seed_envelope import (
        derive_wallet_local_seed, derive_person_root_proxy, seal_envelope, open_envelope,
    )
    from api.identity_roots import derive_ppid_from_person_root_bytes

    person_root = bytes.fromhex(resolved.person_root_hash)
    enc_priv = X25519PrivateKey.generate()
    enc_pub = enc_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    wls = derive_wallet_local_seed(person_root, wallet_id)
    proxy = derive_person_root_proxy(person_root)
    opened_seed = open_envelope(enc_priv.private_bytes_raw(), seal_envelope(enc_pub, wls))
    opened_proxy = open_envelope(enc_priv.private_bytes_raw(), seal_envelope(enc_pub, proxy))
    assert opened_seed == wls
    assert derive_ppid_from_person_root_bytes(opened_proxy, "tickets-demo.lemma.id") == site_a

    # 6. Phase 4 device transfer: old device reseals to a new device key.
    new_priv = X25519PrivateKey.generate()
    new_pub = new_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    resealed = seal_envelope(new_pub, opened_seed)
    assert open_envelope(new_priv.private_bytes_raw(), resealed) == wls

    # 7. Phase 3 root rotation: same document under V2 yields a different root.
    from api.identity_roots import document_root_hash_from_material, derive_person_root_hash

    doc_v2 = document_root_hash_from_material(material, "V2")
    pr_v2 = derive_person_root_hash(doc_v2, "V2")
    assert doc_v2 != resolved.document_root_hash
    assert pr_v2 != resolved.person_root_hash
