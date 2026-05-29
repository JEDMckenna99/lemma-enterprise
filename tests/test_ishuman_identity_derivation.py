"""Phase 1.1 — person-root seed derivation + sealed envelopes.

Invariants:
  * same person_root + same wallet_id -> same wallet_local_seed (deterministic)
  * different wallet_id, same person_root -> different wallet_local_seed (isolation)
  * server seal -> client open round-trips to the exact seed bytes
  * client PPID from person_root_proxy == server PPID from person_root
"""

from __future__ import annotations

import pytest

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from api.seed_envelope import (
    derive_person_root_proxy,
    derive_wallet_local_seed,
    open_envelope,
    seal_envelope,
)


def _x25519_keypair():
    priv = X25519PrivateKey.generate()
    priv_raw = priv.private_bytes_raw() if hasattr(priv, "private_bytes_raw") else None
    pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv, priv_raw, pub_raw


@pytest.mark.unit
def test_wallet_local_seed_is_deterministic():
    person_root = bytes.fromhex("11" * 32)
    a = derive_wallet_local_seed(person_root, "wallet_abc")
    b = derive_wallet_local_seed(person_root, "wallet_abc")
    assert a == b
    assert len(a) == 32


@pytest.mark.unit
def test_wallet_local_seed_is_isolated_per_wallet():
    person_root = bytes.fromhex("11" * 32)
    a = derive_wallet_local_seed(person_root, "wallet_one")
    b = derive_wallet_local_seed(person_root, "wallet_two")
    assert a != b  # cross-wallet isolation


@pytest.mark.unit
def test_seed_envelope_round_trips():
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    priv = X25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_raw = priv.private_bytes_raw()

    person_root = bytes.fromhex("22" * 32)
    seed = derive_wallet_local_seed(person_root, "wallet_round_trip")

    blob = seal_envelope(pub, seed)
    assert blob[0] == 1  # version byte
    opened = open_envelope(priv_raw, blob)
    assert opened == seed

    # Tampering with the ciphertext must fail the AEAD check.
    tampered = bytearray(blob)
    tampered[-1] ^= 0x01
    with pytest.raises(Exception):
        open_envelope(priv_raw, bytes(tampered))


@pytest.mark.unit
def test_client_proxy_ppid_matches_server_person_root_ppid():
    from api.identity_roots import derive_ppid_from_person_root_bytes

    person_root = bytes.fromhex("33" * 32)
    site = "example.com"

    # Server computes the PPID directly from person_root.
    server_ppid = derive_ppid_from_person_root_bytes(person_root, site)

    # The wallet receives person_root_proxy (sealed) and computes the same PPID.
    proxy = derive_person_root_proxy(person_root)
    client_ppid = derive_ppid_from_person_root_bytes(proxy, site)

    assert client_ppid == server_ppid


@pytest.mark.integration
def test_seed_envelope_endpoint_returns_envelopes_when_enabled(
    ishuman_client,
    fake_ishuman_db_session_factory,
    make_ishuman_verification,
    monkeypatch,
    attach_wallet_assertion,
):
    monkeypatch.setenv("LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS", "true")
    db = fake_ishuman_db_session_factory
    db.store.data["IsHumanVerification"].append(
        make_ishuman_verification(
            credential_id="ishuman_master_seed_env",
            wallet_id="wallet_test_001",
            status="verified",
            wallet_seed_envelope=b"\x01sealed-seed-bytes",
            person_root_proxy_envelope=b"\x01sealed-proxy-bytes",
            seed_version="v1",
        )
    )
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    resp = ishuman_client.post(
        "/api/ishuman/seed-envelope",
        json=attach_wallet_assertion(
            {"wallet_id": "wallet_test_001", "wallet_secret": "ab" * 32},
            ["wallet_id"],
        ),
    )
    payload = resp.get_json()
    assert resp.status_code == 200, payload
    assert payload["success"] is True
    assert payload["seed_version"] == "v1"
    assert payload["wallet_seed_envelope"]
    assert payload["person_root_proxy_envelope"]


@pytest.mark.integration
def test_seed_envelope_endpoint_404_when_flag_disabled(
    ishuman_client,
    fake_ishuman_db_session_factory,
    monkeypatch,
):
    monkeypatch.delenv("LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS", raising=False)
    db = fake_ishuman_db_session_factory
    monkeypatch.setattr("api.database.SessionLocal", db.session_local)

    resp = ishuman_client.post(
        "/api/ishuman/seed-envelope",
        json={"wallet_id": "wallet_test_001"},
    )
    payload = resp.get_json()
    assert resp.status_code == 404, payload
    assert payload["error"] == "seed_envelopes_disabled"
