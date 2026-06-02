from __future__ import annotations

import pytest


@pytest.mark.unit
def test_round_trip_encrypts_and_decrypts():
    from api.column_crypto import decrypt_column, encrypt_column, is_encrypted, reset_key_cache

    reset_key_cache()
    plaintext = "ab" * 32  # 64-hex person_root_hash
    enc = encrypt_column(plaintext)

    assert enc != plaintext
    assert is_encrypted(enc)
    assert enc.startswith("lc1:")
    assert decrypt_column(enc) == plaintext


@pytest.mark.unit
def test_randomized_ciphertext_each_call():
    from api.column_crypto import encrypt_column, reset_key_cache

    reset_key_cache()
    value = "cd" * 32
    assert encrypt_column(value) != encrypt_column(value)


@pytest.mark.unit
def test_legacy_plaintext_passthrough_on_read():
    from api.column_crypto import decrypt_column

    legacy = "ff" * 32
    assert decrypt_column(legacy) == legacy


@pytest.mark.unit
def test_none_and_double_encrypt_are_safe():
    from api.column_crypto import decrypt_column, encrypt_column, reset_key_cache

    reset_key_cache()
    assert encrypt_column(None) is None
    assert decrypt_column(None) is None

    enc = encrypt_column("11" * 32)
    assert encrypt_column(enc) == enc  # idempotent


@pytest.mark.unit
def test_no_key_degrades_to_plaintext(monkeypatch):
    import api.column_crypto as cc

    monkeypatch.setattr(cc, "_column_key", lambda: b"")
    value = "22" * 32
    assert cc.encrypt_column(value) == value
    assert cc.decrypt_column(value) == value


@pytest.mark.unit
def test_person_root_hash_stored_encrypted_and_readable(
    fake_ishuman_db_session_factory,
):
    """End-to-end: resolve stores an encrypted person_root_hash; load decrypts it."""
    from api.column_crypto import is_encrypted, reset_key_cache
    from api.database import LemmaPerson
    from api.identity_person import (
        load_person_root_bytes,
        material_from_test_fixture,
        resolve_or_create_person_from_material,
    )

    reset_key_cache()
    db = fake_ishuman_db_session_factory
    session = db.session_local()
    material = material_from_test_fixture(document_number="COLCRYPTO_001")
    resolved = resolve_or_create_person_from_material(
        session, material=material, wallet_id="wallet_colcrypto_1"
    )

    stored = db.store.data[LemmaPerson.__name__][-1]
    assert is_encrypted(stored.person_root_hash)
    assert stored.person_root_hash != resolved.person_root_hash

    recovered = load_person_root_bytes(session, resolved.person_id)
    assert recovered == bytes.fromhex(resolved.person_root_hash)
