"""
Signed issuer trust-list envelope (Phase 7).

This module provides a deterministic, signed issuer trust-list that the
browser verifier can validate locally to enforce multi-issuer trust and key
rotation without adding extra network calls beyond bloom sync.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime
from typing import Any

from api.wallet_keys import b64url_encode, sign_message, verify_message

logger = logging.getLogger(__name__)

TRUST_LIST_PREFIX = "lemma:issuer-trust-list:v1"
DEFAULT_TRUST_LIST_VALID_SECONDS = int(os.getenv("LEMMA_TRUST_LIST_VALID_SECONDS", "86400"))


def _did_pubkey_hex(issuer_did: str) -> str:
    text = str(issuer_did or "").strip()
    if not text.startswith("did:lemma:"):
        return ""
    suffix = text.replace("did:lemma:", "", 1).lower()
    return suffix if len(suffix) == 64 and all(c in "0123456789abcdef" for c in suffix) else ""


def _normalize_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    did = str(raw.get("did") or raw.get("issuer_did") or "").strip()
    pubkey = str(raw.get("pubkey") or raw.get("public_key_hex") or _did_pubkey_hex(did)).strip().lower()
    if not did or len(pubkey) != 64:
        return None

    key_id = str(raw.get("key_id") or f"{did}#{pubkey[:12]}").strip()
    status = str(raw.get("status") or "active").strip().lower()
    if status not in {"active", "retiring"}:
        status = "active"

    now = int(time.time())
    valid_from = int(raw.get("valid_from_unix") or now - 300)
    valid_until = int(raw.get("valid_until_unix") or (now + DEFAULT_TRUST_LIST_VALID_SECONDS))
    priority = int(raw.get("priority") or 0)

    return {
        "did": did,
        "pubkey": pubkey,
        "key_id": key_id,
        "status": status,
        "valid_from_unix": valid_from,
        "valid_until_unix": valid_until,
        "priority": priority,
    }


def _load_rotation_entries() -> list[dict[str, Any]]:
    raw_json = (os.getenv("LEMMA_TRUST_ROTATION_KEYS_JSON") or "").strip()
    if not raw_json:
        return []

    try:
        data = json.loads(raw_json)
    except Exception as exc:
        logger.warning("Invalid LEMMA_TRUST_ROTATION_KEYS_JSON: %s", exc)
        return []

    if not isinstance(data, list):
        logger.warning("LEMMA_TRUST_ROTATION_KEYS_JSON must be a list")
        return []

    entries: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        entry = _normalize_entry(row)
        if entry:
            entries.append(entry)
    return entries


def _load_default_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    # Legacy static trusted DIDs.
    try:
        from api.trusted_issuers import LEGACY_PLATFORM_ISSUER_DIDS

        for did in sorted(LEGACY_PLATFORM_ISSUER_DIDS):
            entry = _normalize_entry({"did": did, "status": "retiring", "priority": -10})
            if entry:
                entries.append(entry)
    except Exception:
        pass

    # Runtime federated issuer is authoritative signer for revocation artifacts.
    try:
        from api.federated_signer import get_federated_issuer_metadata

        meta = get_federated_issuer_metadata()
        entry = _normalize_entry(
            {
                "did": meta["did"],
                "public_key_hex": meta["pubkey_hex"],
                "key_id": "federated-current",
                "status": "active",
                "priority": 100,
            }
        )
        if entry:
            entries.append(entry)
    except Exception as exc:
        logger.warning("Unable to load federated issuer for trust list: %s", exc)

    # Optional additional trusted issuers from env.
    env_issuers = (os.getenv("TRUSTED_ISSUER_DIDS") or "").strip()
    if env_issuers:
        for did in [d.strip() for d in env_issuers.split(",") if d.strip()]:
            entry = _normalize_entry({"did": did})
            if entry:
                entries.append(entry)

    # Optional explicit rotation config.
    entries.extend(_load_rotation_entries())

    # De-dup by (did, pubkey), keeping highest-priority entry.
    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in entries:
        key = (row["did"], row["pubkey"])
        prev = dedup.get(key)
        if prev is None or int(row["priority"]) > int(prev.get("priority") or 0):
            dedup[key] = row

    out = list(dedup.values())
    out.sort(key=lambda item: (item["did"], -int(item.get("priority") or 0), item["key_id"]))
    return out


def compute_trust_list_content_hash(entries: list[dict[str, Any]]) -> str:
    canonical_entries = [
        {
            "did": str(item["did"]),
            "pubkey": str(item["pubkey"]).lower(),
            "key_id": str(item["key_id"]),
            "status": str(item["status"]),
            "valid_from_unix": int(item["valid_from_unix"]),
            "valid_until_unix": int(item["valid_until_unix"]),
            "priority": int(item.get("priority") or 0),
        }
        for item in entries
    ]
    canonical = json.dumps(canonical_entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_trust_list_signature_message(
    *, version: int, content_hash: str, generated_at_unix: int, valid_until_unix: int
) -> bytes:
    return "\n".join(
        [
            TRUST_LIST_PREFIX,
            str(int(version)),
            str(content_hash or "").strip(),
            str(int(generated_at_unix)),
            str(int(valid_until_unix)),
        ]
    ).encode("utf-8")


def build_signed_trust_list(*, generated_at_unix: int | None = None) -> dict[str, Any]:
    from api.bloom_snapshot import _issuer_signing_material
    from api.federated_signer import get_federated_signer, use_remote_federated_signer

    entries = _load_default_entries()
    if not entries:
        raise RuntimeError("trust_list_empty")

    now = int(generated_at_unix or time.time())
    valid_until = now + DEFAULT_TRUST_LIST_VALID_SECONDS
    version = 1
    content_hash = compute_trust_list_content_hash(entries)

    message = build_trust_list_signature_message(
        version=version,
        content_hash=content_hash,
        generated_at_unix=now,
        valid_until_unix=valid_until,
    )
    if use_remote_federated_signer():
        signer = get_federated_signer()
        signature = signer.sign_b64url(message)
        signer_did = signer.get_did()
        signer_pubkey = signer.get_public_key_hex()
    else:
        private_key, public_key, signer_did = _issuer_signing_material()
        signature = b64url_encode(sign_message(private_key, message))
        signer_pubkey = public_key.public_bytes_raw().hex()

    return {
        "version": version,
        "generated_at": datetime.utcfromtimestamp(now).isoformat() + "Z",
        "generated_at_unix": now,
        "valid_until_unix": valid_until,
        "content_hash": content_hash,
        "signer_did": signer_did,
        "signer_pubkey": signer_pubkey,
        "signature": signature,
        "issuers": entries,
        "algorithm": "Ed25519-SHA256",
    }


def verify_signed_trust_list(payload: dict[str, Any], *, now_unix: int | None = None) -> tuple[bool, str]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from api.bloom_snapshot import _decode_signature
    from api.network_roots import signer_pubkey_is_pinned

    if not isinstance(payload, dict):
        return False, "trust_list_missing"

    for key in (
        "version",
        "generated_at_unix",
        "valid_until_unix",
        "content_hash",
        "signer_pubkey",
        "signature",
        "issuers",
    ):
        if payload.get(key) in (None, ""):
            return False, f"trust_list_{key}_missing"

    if not signer_pubkey_is_pinned(str(payload["signer_pubkey"])):
        return False, "trust_list_signer_not_pinned"

    # Clock-skew tolerance (seconds). Mirrors the browser verifier
    # (ishuman-verifier.js TIME_SKEW_SECONDS = 300): client/server clocks
    # routinely drift, so a freshly-signed list whose generated_at_unix is a few
    # seconds ahead of the verifier's clock must not be rejected. 300 s is the
    # conventional window for signed time bounds in identity / OAuth specs.
    _TIME_SKEW_SECONDS = 300
    now = int(now_unix if now_unix is not None else time.time())
    if now + _TIME_SKEW_SECONDS < int(payload["generated_at_unix"]):
        return False, "trust_list_not_yet_valid"
    if now - _TIME_SKEW_SECONDS > int(payload["valid_until_unix"]):
        return False, "trust_list_expired"

    if not isinstance(payload.get("issuers"), list) or not payload["issuers"]:
        return False, "trust_list_issuers_missing"

    normalized: list[dict[str, Any]] = []
    for row in payload["issuers"]:
        if not isinstance(row, dict):
            return False, "trust_list_issuer_malformed"
        entry = _normalize_entry(row)
        if not entry:
            return False, "trust_list_issuer_invalid"
        normalized.append(entry)

    expected_hash = compute_trust_list_content_hash(normalized)
    if expected_hash != str(payload["content_hash"]):
        return False, "trust_list_content_hash_mismatch"

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(str(payload["signer_pubkey"])))
        signature = _decode_signature(str(payload["signature"]))
    except Exception:
        return False, "trust_list_malformed"

    message = build_trust_list_signature_message(
        version=int(payload["version"]),
        content_hash=str(payload["content_hash"]),
        generated_at_unix=int(payload["generated_at_unix"]),
        valid_until_unix=int(payload["valid_until_unix"]),
    )
    if not verify_message(public_key, message, signature):
        return False, "trust_list_invalid_signature"

    return True, "ok"
