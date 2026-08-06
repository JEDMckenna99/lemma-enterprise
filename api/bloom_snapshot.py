"""
Signed Bloom revocation snapshot helpers (Phase 3).

Canonical signing format is shared with static/js/ishuman-verifier.js.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from api.wallet_keys import b64url_encode, sign_message, verify_message

logger = logging.getLogger(__name__)

BLOOM_SNAPSHOT_PREFIX = "lemma:bloom-snapshot:v1"
DEFAULT_BLOOM_STALENESS_SECONDS = int(os.getenv("LEMMA_BLOOM_MAX_STALENESS_SECONDS", "900"))
DEFAULT_BLOOM_VALID_DAYS = int(os.getenv("LEMMA_BLOOM_VALID_DAYS", "7"))


def compute_content_hash(hashed_revoked_ids: list[str], count: int) -> str:
    """Deterministic hash over revocation membership payload."""
    body = {
        "count": int(count),
        "hashed_revoked_ids": list(hashed_revoked_ids),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_signature_message(
    *,
    sequence_number: int,
    content_hash_hex: str,
    generated_at_unix: int,
    valid_until_unix: int,
) -> bytes:
    lines = [
        BLOOM_SNAPSHOT_PREFIX,
        str(int(sequence_number)),
        str(content_hash_hex or "").strip(),
        str(int(generated_at_unix)),
        str(int(valid_until_unix)),
    ]
    return "\n".join(lines).encode("utf-8")


def _issuer_signing_material() -> tuple[Ed25519PrivateKey, Ed25519PublicKey, str]:
    """Load federated network issuer Ed25519 key material (local signing process only)."""
    from api.federated_signer import get_federated_signer

    signer = get_federated_signer()
    if not signer.has_local_seed():
        raise RuntimeError("issuer signing material requires local federated seed")
    return signer.signing_material()


def sign_bloom_snapshot(
    *,
    hashed_revoked_ids: list[str],
    sequence_number: int,
    generated_at: Optional[datetime] = None,
    valid_days: int = DEFAULT_BLOOM_VALID_DAYS,
) -> dict[str, Any]:
    """Build signed snapshot envelope for /api/revocation/bloom-filter."""
    if generated_at is not None:
        generated_unix = int(calendar.timegm(generated_at.timetuple()))
    else:
        generated_unix = int(time.time())
    valid_until_unix = generated_unix + (valid_days * 86400)
    generated = datetime.utcfromtimestamp(generated_unix)
    valid_until = datetime.utcfromtimestamp(valid_until_unix)
    count = len(hashed_revoked_ids)
    content_hash = compute_content_hash(hashed_revoked_ids, count)

    message = build_signature_message(
        sequence_number=sequence_number,
        content_hash_hex=content_hash,
        generated_at_unix=generated_unix,
        valid_until_unix=valid_until_unix,
    )
    from api.federated_signer import get_federated_signer

    signer = get_federated_signer()
    signature_b64 = signer.sign_b64url(message)
    pubkey_hex = signer.get_public_key_hex()
    issuer_did = signer.get_did()

    return {
        "sequence_number": int(sequence_number),
        "generated_at": generated.isoformat() + "Z",
        "generated_at_unix": generated_unix,
        "valid_until": valid_until.isoformat() + "Z",
        "valid_until_unix": valid_until_unix,
        "content_hash": content_hash,
        "count": count,
        "issuer_did": issuer_did,
        "issuer_pubkey": pubkey_hex,
        "signature": signature_b64,
        "algorithm": "Ed25519-SHA256",
        "max_staleness_seconds": DEFAULT_BLOOM_STALENESS_SECONDS,
    }


def verify_bloom_snapshot(snapshot: dict[str, Any], *, now_unix: Optional[int] = None) -> tuple[bool, str]:
    """Verify snapshot signature and freshness."""
    if not isinstance(snapshot, dict):
        return False, "snapshot_missing"

    required = (
        "sequence_number",
        "generated_at_unix",
        "valid_until_unix",
        "content_hash",
        "issuer_pubkey",
        "signature",
        "count",
    )
    for key in required:
        if snapshot.get(key) in (None, ""):
            return False, f"snapshot_{key}_missing"

    now = int(now_unix if now_unix is not None else time.time())
    generated_at = int(snapshot["generated_at_unix"])
    valid_until = int(snapshot["valid_until_unix"])
    if now < generated_at:
        return False, "snapshot_not_yet_valid"
    if now > valid_until:
        return False, "snapshot_expired"

    max_stale = int(snapshot.get("max_staleness_seconds") or DEFAULT_BLOOM_STALENESS_SECONDS)
    if now - generated_at > max_stale:
        return False, "snapshot_stale"

    try:
        pubkey_bytes = bytes.fromhex(str(snapshot["issuer_pubkey"]))
        public_key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        sig = _decode_signature(str(snapshot["signature"]))
    except Exception:
        return False, "snapshot_malformed"

    message = build_signature_message(
        sequence_number=int(snapshot["sequence_number"]),
        content_hash_hex=str(snapshot["content_hash"]),
        generated_at_unix=generated_at,
        valid_until_unix=valid_until,
    )
    if not verify_message(public_key, message, sig):
        return False, "snapshot_invalid_signature"

    return True, "ok"


def verify_snapshot_matches_payload(
    snapshot: dict[str, Any],
    *,
    hashed_revoked_ids: list[str],
) -> tuple[bool, str]:
    """Ensure snapshot content_hash matches hashed_revoked_ids in response."""
    expected = compute_content_hash(hashed_revoked_ids, len(hashed_revoked_ids))
    if str(snapshot.get("content_hash") or "") != expected:
        return False, "snapshot_content_hash_mismatch"
    if snapshot.get("count") is None:
        return False, "snapshot_count_missing"
    if int(snapshot["count"]) != len(hashed_revoked_ids):
        return False, "snapshot_count_mismatch"
    return True, "ok"


def _decode_signature(value: str) -> bytes:
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty signature")
    if len(text) == 128 and all(c in "0123456789abcdef" for c in text.lower()):
        return bytes.fromhex(text)
    from api.wallet_keys import b64url_decode

    return b64url_decode(text)


def fetch_revocation_sequence_number() -> int:
    """Bloom cache-busting sequence for revocation_list.

    ``MAX(id)`` alone does **not** change when a row is deleted. Site Unban
    deletes the PPID's revocation row, but dynos could keep serving a cached
    bloom (same sequence / ETag) that still contained the banned PPID — so
    Verify kept failing and the demo looked stuck banned.

    Mix in ``COUNT(*)`` (and a checksum of ids) so inserts **and** deletes
    change the sequence on every dyno.
    """
    from api.database import get_dbapi_connection

    conn = get_dbapi_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT COALESCE(MAX(id), 0) AS max_id,
                   COUNT(*) AS row_count,
                   COALESCE(SUM(id), 0) AS id_sum
            FROM revocation_list
            """
        )
        row = cursor.fetchone() or (0, 0, 0)
        max_id = int(row[0] or 0)
        row_count = int(row[1] or 0)
        id_sum = int(row[2] or 0)
        # Keep in signed 63-bit space for JSON / JS consumers.
        return ((max_id * 1_000_003) + row_count + (id_sum & 0xFFFF)) & 0x7FFFFFFFFFFFFFFF
    finally:
        cursor.close()
        conn.close()


def invalidate_bloom_filter_cache() -> None:
    """Clear in-process bloom HTTP cache (call after revocation writes)."""
    try:
        from api import revocation_api as rev_api

        rev_api._BLOOM_CACHE["built_at"] = 0.0
        rev_api._BLOOM_CACHE["count"] = None
        rev_api._BLOOM_CACHE["payload"] = None
        rev_api._BLOOM_CACHE["sequence"] = None
    except Exception:
        pass
