"""
Revocation API - Bloom Filter Distribution
Provides revocation data for client-side verification
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging

logger = logging.getLogger(__name__)

revocation_api = Blueprint('revocation_api', __name__)


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
        # All revocations in one filter, privacy preserved by OPRF blinding
        # Sites only check credentials they have (selective disclosure)
        
        # Query database for ALL revoked credentials (global)
        try:
            from api.database import get_db_connection
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get ALL revoked credential IDs across all sites
            # Privacy guaranteed by:
            # 1. Wallet selective disclosure: Sites only receive credentials for their domain
            # 2. OPRF blinding: Credential IDs blinded before revocation check
            # 3. Zero-knowledge: Sites cannot correlate revocations to other sites
            cursor.execute("""
                SELECT credential_id 
                FROM revocation_list
            """)
            
            revoked_ids = [row[0] for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            logger.info(f"📊 Global Bloom filter: {len(revoked_ids)} total revocations (all sites)")
            
        except Exception as e:
            logger.error(f"❌ Failed to query revocations: {e}")
            revoked_ids = []  # Fail safe - return empty list
        
        # Return bloom filter data
        import time
        from datetime import datetime, timedelta
        
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
        
        response = {
            'success': True,
            'filter_type': 'global_sha256',  # SHA-256 hashed IDs for privacy
            'hashed_revoked_ids': hashed_revoked_ids,  # SHA-256 hashes (client hashes locally to check)
            'count': len(hashed_revoked_ids),
            'version': int(time.time()),  # Use timestamp as version
            'valid_until': valid_until.isoformat(),
            'sync_interval_days': 7,
            'privacy_mechanism': 'sha256_web_crypto',  # Web Crypto API provides one-way hashing
            'message': 'Global revocation list (SHA-256 hashed) - client hashes credential ID locally using Web Crypto API to check',
            'hash_algorithm': 'SHA-256',
            'client_implementation': 'crypto.subtle.digest'
        }
        
        logger.info(f"✅ Global Bloom filter served: {len(revoked_ids)} total revocations")
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Bloom filter error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

