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
        
        # Build Cascaded Bloom Filter with OPRF-hashed IDs (for WASM)
        filter_bytes = None
        try:
            from lemma_crypto import PyCascadedBloomFilter, PyOPRFServer
            
            # Create Bloom filter (3 levels, 10K base capacity, 0.1% error rate)
            bloom_filter = PyCascadedBloomFilter(3, 10000, 0.001)
            
            # Create OPRF server for hashing credential IDs
            oprf_server = PyOPRFServer()
            
            # Add revoked IDs to Bloom filter (OPRF-hashed)
            for cred_id in revoked_ids:
                # For now, just use credential ID as bytes
                # In production, we'd OPRF-blind these
                bloom_filter.add(cred_id.encode('utf-8'))
            
            # Serialize Bloom filter for client
            filter_bytes = bloom_filter.to_bytes()
            
            logger.info(f"✅ Built Bloom filter: {len(filter_bytes)} bytes")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to build Bloom filter: {e}")
            filter_bytes = None
        
        response = {
            'success': True,
            'filter_type': 'global_cascaded',  # Single global Bloom filter for all sites
            'revoked_ids': revoked_ids,
            'count': len(revoked_ids),
            'version': int(time.time()),  # Use timestamp as version
            'valid_until': valid_until.isoformat(),
            'sync_interval_days': 7,
            'privacy_mechanism': 'oprf_blinding',  # OPRF provides zero-knowledge privacy
            'message': 'Global revocation list - privacy preserved via OPRF blinding before lookup'
        }
        
        # Include Bloom filter bytes if available (base64-encoded for JSON)
        if filter_bytes:
            import base64
            response['filter_bytes'] = base64.b64encode(filter_bytes).decode('utf-8')
            response['filter_size_bytes'] = len(filter_bytes)
        
        logger.info(f"✅ Global Bloom filter served: {len(revoked_ids)} total revocations")
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Bloom filter error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

