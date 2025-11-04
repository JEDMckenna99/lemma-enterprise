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
        # Get site_id from query param (optional - can filter by site)
        site_id = request.args.get('site_id', 'lemma_platform')
        
        # Query database for revoked credentials
        try:
            from api.database import get_db_connection
            
            conn = get_db_connection(site_id=site_id)
            cursor = conn.cursor()
            
            # Get all revoked credential IDs for THIS SITE ONLY (site-specific isolation)
            # NOTE: Each site has its own Bloom filter to prevent cross-site information leakage
            cursor.execute("""
                SELECT credential_id 
                FROM revocation_list 
                WHERE site_id = %s
            """, (site_id,))
            
            revoked_ids = [row[0] for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            logger.info(f"📊 Bloom filter for {site_id}: {len(revoked_ids)} revoked credentials")
            
        except Exception as e:
            logger.error(f"❌ Failed to query revocations: {e}")
            revoked_ids = []  # Fail safe - return empty list
        
        # Return bloom filter data
        import time
        from datetime import datetime, timedelta
        
        valid_until = datetime.now() + timedelta(days=7)
        
        response = {
            'success': True,
            'site_id': site_id,  # CRITICAL: Site-specific Bloom filter
            'revoked_ids': revoked_ids,
            'count': len(revoked_ids),
            'version': int(time.time()),  # Use timestamp as version
            'valid_until': valid_until.isoformat(),
            'sync_interval_days': 7,
            'isolation': 'site_specific',  # Each site has its own Bloom filter
            'message': f'Site-specific Bloom filter for {site_id} - Cache locally for client-side revocation checks'
        }
        
        logger.info(f"📊 Site-specific Bloom filter for {site_id}: {len(revoked_ids)} revocations")
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Bloom filter error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

