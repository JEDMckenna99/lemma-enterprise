"""Device-link transfer security, person-root bundles and relay validation."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest

os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-unit-tests")

ROOT = Path(__file__).resolve().parents[1]
WALLET_JS = ROOT / "static" / "js" / "lemma-wallet.js"


@pytest.mark.unit
def test_legacy_generate_link_code_removed_from_sdk():
    source = WALLET_JS.read_text(encoding="utf-8")
    assert "generateLinkCode" not in source
    assert "linkDevice(" not in source
    assert "_decryptLinkQR" not in source


@pytest.mark.unit
def test_pull_send_uses_person_root_seeds_only():
    source = WALLET_JS.read_text(encoding="utf-8")
    assert "sealed_wallet_seed" in source
    assert "sealed_person_root_proxy" in source
    assert "sendLinkDepositFromScan" in source
    idx = source.index("async sendLinkDepositFromScan")
    chunk = source[idx:idx + 4000]
    assert "walletSecret: profile.secret" not in chunk
    assert "walletLocalSeed" in chunk


@pytest.mark.unit
def test_push_transfer_uses_offer_register_not_secret_in_url():
    source = WALLET_JS.read_text(encoding="utf-8")
    assert "async beginLinkPush" in source
    assert "async acceptLinkPushOffer" in source
    assert "async confirmLinkPushDeposit" in source
    idx = source.index("async beginLinkPush")
    end = source.index("async getLinkPushStatus", idx)
    chunk = source[idx:end]
    assert "mode: 'push'" in chunk or 'mode: "push"' in chunk
    assert "walletSecret" not in chunk
    assert "confirm_code" in chunk or "confirmCode" in chunk
    # Offer creation should not force a second passkey when already unlocked.
    assert "_requireFreshPasskeyAuth" not in chunk


@pytest.mark.unit
def test_link_completion_defers_signing_key_when_enrollment_grant_pending():
    source = WALLET_JS.read_text(encoding="utf-8")
    idx = source.index("async _completeLinkFromPayload")
    chunk = source[idx:idx + 8000]
    assert "if (!this._pendingEnrollmentGrant)" in chunk
    assert "_registerSigningKeyIfNeeded" in chunk
    assert "device-enroll needs" in chunk or "enrollment grant" in chunk.lower()


@pytest.mark.unit
def test_device_link_exports_only_valid_ishuman_credentials():
    source = WALLET_JS.read_text(encoding="utf-8")
    assert "async exportIsHumanCredentialsForTransfer" in source
    assert "async _selectValidCredentialsForTransfer" in source
    assert "_dedupeCredentialsForTransfer" in source
    assert "_verifyIsHumanCredentialBrowser" in source

    pull_idx = source.index("async sendLinkDepositFromScan")
    pull_chunk = source[pull_idx:pull_idx + 4500]
    assert "exportIsHumanCredentialsForTransfer" in pull_chunk
    assert "exportIsHumanCredentialsForBridge" not in pull_chunk

    push_idx = source.index("async confirmLinkPushDeposit")
    push_chunk = source[push_idx:push_idx + 5500]
    assert "exportIsHumanCredentialsForTransfer" in push_chunk
    assert "exportIsHumanCredentialsForBridge" not in push_chunk

    import_idx = source.index("async _importLinkedIsHumanCredentials")
    import_chunk = source[import_idx:import_idx + 2500]
    assert "_selectValidCredentialsForTransfer" in import_chunk
    assert "forImport: true" in import_chunk


@pytest.mark.unit
def test_seed_transfer_finalizes_person_root_ppid_and_platform_role():
    source = WALLET_JS.read_text(encoding="utf-8")
    assert "async _derivePPIDFromPersonRootProxy" in source
    assert "lemma.id/site-ppid/v1" in source
    assert "async finalizeIdentityAfterSeedTransfer" in source
    assert "async _restorePlatformAccessForCurrentPpid" in source
    assert "async ensurePersonRootSeedsLoaded" in source

    derive_idx = source.index("async derivePPID(siteId)")
    derive_chunk = source[derive_idx:derive_idx + 4500]
    assert "_derivePPIDFromPersonRootProxy" in derive_chunk
    # Person-root must win over minting a divergent wallet_secret PPID.
    assert derive_chunk.index("_derivePPIDFromPersonRootProxy") < derive_chunk.index("getWalletSecret()")

    enroll_idx = source.index("async ensureDeviceEnrollmentAfterSeedTransfer")
    enroll_end = source.index("async finalizeIdentityAfterSeedTransfer", enroll_idx)
    enroll_chunk = source[enroll_idx:enroll_end]
    assert "reissueMasterCredential" not in enroll_chunk

    finalize_idx = source.index("async finalizeIdentityAfterSeedTransfer")
    finalize_chunk = source[finalize_idx:finalize_idx + 2800]
    assert "reissueMasterCredential" in finalize_chunk
    assert "_restorePlatformAccessForCurrentPpid" in finalize_chunk
    assert "_persistPersonRootSeedsAtRest" in finalize_chunk

    persist_idx = source.index("async _persistPersonRootSeedsAtRest")
    persist_chunk = source[persist_idx:persist_idx + 900]
    assert "id: 'person_root_seeds'" in persist_chunk
    # Must write via _put so the whole record is PRF-encrypted (old helper no-op'd).
    assert "await this._put('secrets'" in persist_chunk
    assert "mod?.encryptStoredValue" not in persist_chunk

    unlock_idx = source.index("async unlock(options = {})")
    unlock_chunk = source[unlock_idx:unlock_idx + 12000]
    assert "ensurePersonRootSeedsLoaded" in unlock_chunk

    link_html = (ROOT / "templates" / "wallet_link.html").read_text(encoding="utf-8")
    assert "finalizeIdentityAfterSeedTransfer" in link_html
    manager = (ROOT / "templates" / "wallet_simple.html").read_text(encoding="utf-8")
    assert "resolveCanonicalManagerPpid" in manager


@pytest.mark.unit
def test_client_person_root_proxy_ppid_message_matches_server():
    """Guard the domain-separator string used by wallet derivePPID."""
    from api.identity_roots import SITE_PPID_MSG_PREFIX, derive_ppid_from_person_root_bytes

    person_root = bytes.fromhex("33" * 32)
    site = "lemma.id"
    expected = derive_ppid_from_person_root_bytes(person_root, site)
    # Mirror the client message construction exactly.
    import hashlib
    import hmac

    client_hash = hmac.new(
        person_root,
        f"{SITE_PPID_MSG_PREFIX}{site}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert expected == f"did:lemma:ppid_{client_hash}"
    source = WALLET_JS.read_text(encoding="utf-8")
    assert f"`{SITE_PPID_MSG_PREFIX}${{site}}`" in source or f'"{SITE_PPID_MSG_PREFIX}"' in source


@pytest.mark.unit
def test_server_has_no_legacy_link_store_route():
    api_root = ROOT / "api"
    routes_text = "\n".join(p.read_text(encoding="utf-8") for p in api_root.rglob("*.py"))
    assert "/api/wallet/store-link" not in routes_text
    assert "/api/wallet/link-deposit" not in routes_text


@pytest.mark.unit
def test_link_receive_accepts_person_root_bundle(monkeypatch):
    from flask import Flask

    from api import ishuman as ishuman_mod

    app = Flask(__name__)
    app.register_blueprint(ishuman_mod.ishuman_bp)
    store = {}

    monkeypatch.setattr("auth.redis_store.store", lambda key, value, ttl_seconds=300: store.update({key: value}) or True)
    monkeypatch.setattr("auth.redis_store.get", lambda key: store.get(key))
    monkeypatch.setattr("auth.redis_store.delete", lambda key: bool(store.pop(key, None)))
    monkeypatch.setattr(
        ishuman_mod,
        "_require_wallet_assertion",
        lambda body, field_names: (None, body.get("wallet_id")),
    )

    client = app.test_client()
    deposit = client.post(
        "/api/wallet/link-receive",
        json={
            "action": "deposit",
            "wallet_id": "wallet_a",
            "transfer_id": "linkrecv_" + secrets.token_hex(8),
            "recv_pubkey": "AQIDBAUGBwgJCgsMDQ4PEA==",
            "bundle": {
                "sealed_wallet_seed": "c2VlZA==",
                "sealed_person_root_proxy": "cHJveHk=",
            },
            "wallet_assertion": {"nonce": "n", "signature": "s"},
        },
    )
    assert deposit.status_code == 200
    assert deposit.get_json()["success"] is True
