"""
Revocation API - Bloom Filter Distribution
Provides revocation data for client-side verification
"""

from flask import Blueprint, request, jsonify, Response
from flask_cors import cross_origin
import logging
import os
import base64
import hashlib
import time
from datetime import datetime, timedelta
import math

logger = logging.getLogger(__name__)

revocation_api = Blueprint('revocation_api', __name__)


def _bloom_etag(sequence_number: int) -> str:
    return f'"bloom-seq-{int(sequence_number)}"'


def _bloom_cache_control(ttl_seconds: int) -> str:
    # Allow shared caches / CDN; clients revalidate via ETag when stale.
    ttl = max(0, int(ttl_seconds))
    swr = max(ttl, int(os.getenv("LEMMA_REVOCATION_FILTER_SWR_SECONDS", "300")))
    return f"public, max-age={ttl}, stale-while-revalidate={swr}"


def _attach_bloom_cache_headers(response, *, sequence_number: int, ttl_seconds: int):
    response.headers["ETag"] = _bloom_etag(sequence_number)
    response.headers["Cache-Control"] = _bloom_cache_control(ttl_seconds)
    response.headers["Vary"] = "Accept-Encoding"
    return response


def _bloom_not_modified(sequence_number: int, ttl_seconds: int):
    resp = Response(status=304)
    return _attach_bloom_cache_headers(
        resp, sequence_number=sequence_number, ttl_seconds=ttl_seconds
    )


@revocation_api.route('/api/issuer/trust-list', methods=['GET'])
@cross_origin()
def get_issuer_trust_list():
    """Return signed issuer trust-list for local verifier trust decisions."""
    try:
        from api.issuer_trust_list import build_signed_trust_list

        payload = build_signed_trust_list()
        return jsonify({"success": True, "trust_list": payload}), 200
    except Exception as exc:
        logger.error("Issuer trust-list error: %s", exc)
        return jsonify({"success": False, "error": "trust_list_unavailable"}), 500


@revocation_api.route('/api/v1/revocation/list', methods=['GET'])
@cross_origin()
def get_revocation_list():
    """
    Simple revocation list for client-side caching
    Returns plain credential IDs (for direct lookup)
    """
    try:
        from api.database import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COALESCE(credential_id, lemma_id) as credential_id
            FROM revocation_list
        """)
        
        revoked_ids = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'revocations': revoked_ids,
            'count': len(revoked_ids),
            'timestamp': int(time.time() * 1000),
            'ttl_ms': 3600000  # 1 hour cache
        }), 200

    except Exception as e:
        logger.error(f"Revocation list error: {e}")
        return jsonify({
            'success': False,
            'error': 'revocation_unavailable',
        }), 503

_BLOOM_CACHE = {
    "built_at": 0.0,
    "count": None,
    "sequence": None,
    "payload": None,
}

def _bloom_params(capacity: int, false_positive_rate: float) -> tuple[int, int]:
    """
    Return (m_bits, k_hashes) for a Bloom filter.
    """
    ln2 = math.log(2.0)
    m = int(math.ceil(-(capacity * math.log(false_positive_rate)) / (ln2 * ln2)))
    k = int(max(1, math.ceil((m / max(1, capacity)) * ln2)))
    return m, k

def _bloom_set_bit(bitset: bytearray, idx: int) -> None:
    bitset[idx >> 3] |= (1 << (idx & 7))

def _build_bloom_bitset_sha256_dh32le(items: list[str], capacity: int, false_positive_rate: float) -> tuple[bytes, int, int]:
    """
    Build a Bloom filter bitset where each item is hashed with SHA-256,
    then indices are generated via double-hashing over two 32-bit LE words:
      h1 = u32_le(digest[0:4])
      h2 = u32_le(digest[4:8]) (forced non-zero)
      idx_i = (h1 + i*h2) % m_bits
    """
    m_bits, k = _bloom_params(capacity, false_positive_rate)
    bitset = bytearray((m_bits + 7) // 8)

    for s in items:
        digest = hashlib.sha256(s.encode("utf-8")).digest()
        h1 = int.from_bytes(digest[0:4], "little", signed=False)
        h2 = int.from_bytes(digest[4:8], "little", signed=False) or 0x5BD1E995
        for i in range(k):
            idx = (h1 + i * h2) % m_bits
            _bloom_set_bit(bitset, idx)

    return bytes(bitset), m_bits, k


@revocation_api.route('/api/revocation/bloom-filter', methods=['GET'])
@cross_origin()
def get_bloom_filter():
    """
    Get bloom filter of revoked credential IDs for client-side checking
    
    This allows client-side verification without revealing which
    credentials are being checked (privacy-preserving)
    
    Response includes:
    - revoked_ids: Array of revoked credential IDs
    - version: Bloom filter version (monotonic)
    - valid_until: Timestamp when filter expires (7 days)
    """
    try:
        # GLOBAL BLOOM FILTER APPROACH
        # All revocations in one filter
        # Sites only check credentials they have (selective disclosure)

        from api.bloom_snapshot import (
            fetch_revocation_sequence_number,
            sign_bloom_snapshot,
            verify_snapshot_matches_payload,
        )
        from api.issuer_trust_list import build_signed_trust_list

        try:
            sequence_number = fetch_revocation_sequence_number()
        except Exception as exc:
            logger.error("Bloom sequence lookup failed: %s", exc)
            return jsonify({"success": False, "error": "revocation_unavailable"}), 503
        cache_ttl_seconds = int(os.getenv("LEMMA_REVOCATION_FILTER_CACHE_TTL_SECONDS", "60"))
        etag = _bloom_etag(sequence_number)

        # Cheap path: matching ETag → 304 without scanning revocation_list.
        if_none_match = (request.headers.get("If-None-Match") or "").strip()
        if if_none_match and etag in if_none_match:
            return _bloom_not_modified(sequence_number, cache_ttl_seconds)

        now_ts = time.time()
        if (
            _BLOOM_CACHE["payload"] is not None
            and _BLOOM_CACHE["sequence"] == sequence_number
            and (now_ts - _BLOOM_CACHE["built_at"]) < cache_ttl_seconds
        ):
            resp = jsonify(_BLOOM_CACHE["payload"])
            return _attach_bloom_cache_headers(
                resp, sequence_number=sequence_number, ttl_seconds=cache_ttl_seconds
            ), 200

        # Query database for ALL revoked credentials AND PPIDs (global)
        from api.database import get_db_connection

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Get ALL revoked credential IDs across all sites
            cursor.execute("""
                SELECT COALESCE(credential_id, lemma_id) as credential_id
                FROM revocation_list
            """)

            revoked_ids = [row[0] for row in cursor.fetchall()]

            # Include site-scoped user PPIDs too. Site bans store the PPID in
            # credential_id/lemma_id (picked up above) AND ppid; keeping this
            # query unfiltered avoids missing a ban key shape on unban/rebuild.
            cursor.execute("""
                SELECT DISTINCT ppid
                FROM revocation_list
                WHERE ppid IS NOT NULL
                  AND revocation_type = 'user'
            """)

            revoked_ppids = [row[0] for row in cursor.fetchall()]

            cursor.execute("""
                SELECT DISTINCT wallet_id
                FROM revocation_list
                WHERE wallet_id IS NOT NULL AND revocation_type = 'wallet'
            """)

            revoked_wallets = [row[0] for row in cursor.fetchall()]

            all_revoked = revoked_ids + revoked_ppids + revoked_wallets

            cursor.close()
            conn.close()

            logger.info(
                "Global Bloom filter: %s creds + %s PPIDs + %s wallets = %s total",
                len(revoked_ids),
                len(revoked_ppids),
                len(revoked_wallets),
                len(all_revoked),
            )

            revoked_ids = all_revoked

        except Exception as e:
            logger.error("Failed to query revocations: %s", e)
            return jsonify({"success": False, "error": "revocation_unavailable"}), 503

        valid_until = datetime.now() + timedelta(days=7)

        hashed_revoked_ids = []
        try:
            for cred_id in revoked_ids:
                cred_id_str = cred_id if isinstance(cred_id, str) else cred_id.decode("utf-8")
                hash_digest = hashlib.sha256(cred_id_str.encode("utf-8")).hexdigest()
                hashed_revoked_ids.append(hash_digest)

            logger.info("Hashed %s revoked IDs with SHA-256", len(hashed_revoked_ids))

        except Exception as e:
            logger.error("Failed to hash revoked IDs: %s", e, exc_info=True)
            return jsonify({"success": False, "error": "bloom_hash_failed"}), 500

        # Build a REAL Bloom filter payload (compact bitset) for scalable distribution
        bloom_enabled = os.getenv("LEMMA_ENABLE_BLOOM_REVOCATION", "1") != "0"
        bloom_filter_b64 = None
        bloom_meta = None
        if bloom_enabled:
            try:
                target_capacity = int(os.getenv("LEMMA_BLOOM_TARGET_CAPACITY", "100000"))
                error_rate = float(os.getenv("LEMMA_BLOOM_FALSE_POSITIVE_RATE", "0.000001"))  # 1e-6

                capacity = max(target_capacity, max(1, len(revoked_ids)))
                revoked_id_strs = [
                    (cid if isinstance(cid, str) else cid.decode("utf-8"))
                    for cid in revoked_ids
                ]

                bloom_bytes, m_bits, k_hashes = _build_bloom_bitset_sha256_dh32le(
                    revoked_id_strs,
                    capacity=capacity,
                    false_positive_rate=error_rate,
                )

                bloom_filter_b64 = base64.b64encode(bloom_bytes).decode("ascii")
                bloom_meta = {
                    "format": "bloom_v1",
                    "encoding": "base64",
                    "m_bits": m_bits,
                    "k_hashes": k_hashes,
                    "capacity": capacity,
                    "false_positive_rate": error_rate,
                    "size_bytes": len(bloom_bytes),
                    "item_format": "credential_id_utf8",
                    "hash": "sha256_dh32le",
                }
            except Exception as e:
                # Non-fatal: keep serving hashed set even if bloom generation fails.
                logger.warning(f"⚠️ Bloom filter generation failed, serving hashed set only: {e}", exc_info=True)

        snapshot = sign_bloom_snapshot(
            hashed_revoked_ids=hashed_revoked_ids,
            sequence_number=sequence_number,
            generated_at=datetime.utcnow(),
        )
        trust_list = build_signed_trust_list()
        ok_payload, payload_reason = verify_snapshot_matches_payload(
            snapshot,
            hashed_revoked_ids=hashed_revoked_ids,
        )
        if not ok_payload:
            logger.error("Bloom snapshot self-check failed: %s", payload_reason)
            return jsonify({"success": False, "error": "bloom_snapshot_build_failed"}), 500

        response = {
            'success': True,
            # Backwards-compatible payload (exact membership, no false positives)
            'filter_type': 'global_sha256',  # SHA-256 hashed IDs for privacy
            'hashed_revoked_ids': hashed_revoked_ids,  # SHA-256 hex hashes (client hashes locally to check)
            'count': len(hashed_revoked_ids),
            'version': sequence_number,
            'generated_at': snapshot.get('generated_at'),
            'sequence_number': sequence_number,
            'valid_until': snapshot.get('valid_until') or valid_until.isoformat(),
            'sync_interval_days': 7,
            'privacy_mechanism': 'sha256_web_crypto',  # Web Crypto API provides one-way hashing
            'message': 'Global revocation list (SHA-256 hashed) - client hashes credential ID locally using Web Crypto API to check',
            'hash_algorithm': 'SHA-256',
            'client_implementation': 'crypto.subtle.digest',
            # Phase 3 signed envelope
            'snapshot': snapshot,
            'issuer_did': snapshot.get('issuer_did'),
            'issuer_pubkey': snapshot.get('issuer_pubkey'),
            'signature': snapshot.get('signature'),
            'content_hash': snapshot.get('content_hash'),
            'algorithm': snapshot.get('algorithm'),
            'max_bloom_staleness_seconds': snapshot.get('max_staleness_seconds'),
            # Phase 7 signed issuer trust list (for multi-issuer verification + rotation)
            'trust_list': trust_list,
            # New Bloom payload (compact, false positives possible)
            'bloom_filter': bloom_meta,
            'filter_bytes': bloom_filter_b64,
        }
        
        logger.info(f"✅ Global Bloom filter served: {len(revoked_ids)} total revocations")

        _BLOOM_CACHE["built_at"] = now_ts
        _BLOOM_CACHE["count"] = len(revoked_ids)
        _BLOOM_CACHE["sequence"] = sequence_number
        _BLOOM_CACHE["payload"] = response

        resp = jsonify(response)
        return _attach_bloom_cache_headers(
            resp, sequence_number=sequence_number, ttl_seconds=cache_ttl_seconds
        ), 200
        
    except Exception as e:
        logger.error(f"Bloom filter error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

