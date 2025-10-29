"""
Test Credential Endpoint
For testing client-side verification matches server-side issuance
"""

from flask import Blueprint, jsonify, request
from flask_cors import cross_origin
import json
import logging

logger = logging.getLogger(__name__)

test_credential_bp = Blueprint('test_credential', __name__)

try:
    from lemma_crypto import PyMinimalIssuer
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    logger.warning("⚠️ Rust crypto not available for test endpoint")

@test_credential_bp.route('/api/test/issue-credential', methods=['POST', 'OPTIONS'])
@cross_origin()
def issue_test_credential():
    """
    Issue a test credential for verifying client-side signature verification
    
    This endpoint is ONLY for testing that JavaScript message construction
    matches the Rust server's message construction.
    
    DO NOT use in production!
    """
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        if not RUST_AVAILABLE:
            return jsonify({
                'error': 'Rust crypto engine not available'
            }), 500
        
        data = request.get_json() or {}
        
        subject = data.get('subject', 'did:lemma:test_user')
        permission = data.get('permission', 'test_permission')
        
        # Build claims
        claims = data.get('claims', {})
        claims['permission'] = permission
        
        # Create test issuer (this creates a fresh keypair for testing)
        issuer = PyMinimalIssuer.new()
        
        # Convert claims to string dict for Rust
        claims_str = {k: str(v) for k, v in claims.items()}
        
        # Issue credential (uses default 365 day expiry from Rust)
        credential_json = issuer.issue_credential(subject, claims_str)
        credential = json.loads(credential_json)
        
        # Extract public key for client-side verification
        issuer_did = issuer.get_did()
        public_key_hex = issuer.get_public_key_hex()
        
        logger.info(f"✅ Issued test credential: {credential['id']}")
        logger.info(f"🔐 Issuer DID: {issuer_did}")
        logger.info(f"🔑 Public Key: {public_key_hex}")
        
        # Return both credential and issuer's public key for verification
        return jsonify({
            'credential': credential,
            'issuer_did': issuer_did,
            'public_key': public_key_hex
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Test credential issue failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e)
        }), 500

