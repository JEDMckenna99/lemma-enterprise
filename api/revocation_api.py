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
        site_id = request.args.get('site_id')
        
        # For now, return empty set (no revocations yet)
        # In production, query database for revoked credentials
        revoked_ids = []
        
        # TODO: Get from database
        # from api.database import RevocationList
        # revocations = RevocationList.query.filter_by(site_id=site_id).all()
        # revoked_ids = [r.credential_id for r in revocations]
        
        # Return bloom filter data
        import time
        from datetime import datetime, timedelta
        
        valid_until = datetime.now() + timedelta(days=7)
        
        response = {
            'success': True,
            'revoked_ids': revoked_ids,
            'count': len(revoked_ids),
            'version': int(time.time()),  # Use timestamp as version
            'valid_until': valid_until.isoformat(),
            'sync_interval_days': 7,
            'message': 'Cache this locally for client-side revocation checks'
        }
        
        logger.info(f"Bloom filter requested: {len(revoked_ids)} revocations")
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Bloom filter error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

