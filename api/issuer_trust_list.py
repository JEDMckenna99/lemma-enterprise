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
        from api.issuer_management import get_issuer_manager

        issuer = get_issuer_manager().get_federated_issuer()
        entry = _normalize_entry(
            {
                "did": issuer.get_did(),
                "public_key_hex": issuer.get_public_key_hex(),
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

    entries = _load_default_entries()
    if not entries:
        raise RuntimeError("trust_list_empty")

    now = int(generated_at_unix or time.time())
    valid_until = now + DEFAULT_TRUST_LIST_VALID_SECONDS
    version = 1
    content_hash = compute_trust_list_content_hash(entries)

    private_key, public_key, signer_did = _issuer_signing_material()
    message = build_trust_list_signature_message(
        version=version,
        content_hash=content_hash,
        generated_at_unix=now,
        valid_until_unix=valid_until,
    )
    signature = b64url_encode(sign_message(private_key, message))

    return {
        "version": version,
        "generated_at": datetime.utcfromtimestamp(now).isoformat() + "Z",
        "generated_at_unix": now,
        "valid_until_unix": valid_until,
        "content_hash": content_hash,
        "signer_did": signer_did,
        "signer_pubkey": public_key.public_bytes_raw().hex(),
        "signature": signature,
        "issuers": entries,
        "algorithm": "Ed25519-SHA256",
    }


def verify_signed_trust_list(payload: dict[str, Any], *, now_unix: int | None = None) -> tuple[bool, str]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from api.bloom_snapshot import _decode_signature

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

    now = int(now_unix if now_unix is not None else time.time())
    if now < int(payload["generated_at_unix"]):
        return False, "trust_list_not_yet_valid"
    if now > int(payload["valid_until_unix"]):
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
