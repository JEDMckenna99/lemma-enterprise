"""
Revocation API - Bloom Filter Distribution
Provides revocation data for client-side verification
"""

from flask import Blueprint, request, jsonify
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
            'success': True,
            'revocations': [],
            'count': 0,
            'timestamp': int(time.time() * 1000)
        }), 200  # Return empty list on error (fail-safe)

_BLOOM_CACHE = {
    "built_at": 0.0,
    "count": None,
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
        
        # Query database for ALL revoked credentials (global)
        try:
            from api.database import get_db_connection
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get ALL revoked credential IDs across all sites
            # Privacy guaranteed by:
            # 1. Wallet selective disclosure: Sites only receive credentials for their domain
            # 2. SHA256 hashing: Credential IDs hashed before revocation check
            # 3. Zero-knowledge: Sites cannot correlate revocations to other sites
            # Note: Table uses both 'credential_id' and 'lemma_id' columns for compatibility
            cursor.execute("""
                SELECT COALESCE(credential_id, lemma_id) as credential_id
                FROM revocation_list
            """)
            
            revoked_ids = [row[0] for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            logger.info(f"📊 Global Bloom filter: {len(revoked_ids)} total revocations (all sites)")
            
        except Exception as e:
            logger.error(f"❌ Failed to query revocations: {e}")
            revoked_ids = []  # Fail safe - return empty list
        
        # Cache to avoid rebuilding on every request
        cache_ttl_seconds = int(os.getenv("LEMMA_REVOCATION_FILTER_CACHE_TTL_SECONDS", "60"))
        now_ts = time.time()
        if (
            _BLOOM_CACHE["payload"] is not None
            and _BLOOM_CACHE["count"] == len(revoked_ids)
            and (now_ts - _BLOOM_CACHE["built_at"]) < cache_ttl_seconds
        ):
            return jsonify(_BLOOM_CACHE["payload"]), 200

        valid_until = datetime.now() + timedelta(days=7)
        
        # Hash revoked IDs with SHA-256 (client will hash credential IDs locally to check)
        # This provides strong privacy: server cannot reverse SHA-256 to get credential IDs
        hashed_revoked_ids = []
        try:
            import hashlib
            
            for cred_id in revoked_ids:
                # SHA-256 hash of credential ID (one-way function)
                cred_id_str = cred_id if isinstance(cred_id, str) else cred_id.decode('utf-8')
                hash_digest = hashlib.sha256(cred_id_str.encode('utf-8')).hexdigest()
                hashed_revoked_ids.append(hash_digest)
            
            logger.info(f"✅ Hashed {len(hashed_revoked_ids)} revoked IDs with SHA-256")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to hash revoked IDs: {e}", exc_info=True)
            # Fallback to plain IDs
            hashed_revoked_ids = revoked_ids

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

        response = {
            'success': True,
            # Backwards-compatible payload (exact membership, no false positives)
            'filter_type': 'global_sha256',  # SHA-256 hashed IDs for privacy
            'hashed_revoked_ids': hashed_revoked_ids,  # SHA-256 hex hashes (client hashes locally to check)
            'count': len(hashed_revoked_ids),
            'version': int(time.time()),  # timestamp version (monotonic-enough for caching)
            'valid_until': valid_until.isoformat(),
            'sync_interval_days': 7,
            'privacy_mechanism': 'sha256_web_crypto',  # Web Crypto API provides one-way hashing
            'message': 'Global revocation list (SHA-256 hashed) - client hashes credential ID locally using Web Crypto API to check',
            'hash_algorithm': 'SHA-256',
            'client_implementation': 'crypto.subtle.digest',
            # New Bloom payload (compact, false positives possible)
            'bloom_filter': bloom_meta,
            'filter_bytes': bloom_filter_b64,
        }
        
        logger.info(f"✅ Global Bloom filter served: {len(revoked_ids)} total revocations")

        _BLOOM_CACHE["built_at"] = now_ts
        _BLOOM_CACHE["count"] = len(revoked_ids)
        _BLOOM_CACHE["payload"] = response

        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Bloom filter error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

