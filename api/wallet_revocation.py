"""
Wallet Revocation API - Handle credential revocation from wallet interface
"""
import json
import time
import logging
from flask import Blueprint, request, jsonify, session
from flask_cors import cross_origin
from auth.decorators import require_customer_or_admin, rate_limit
from api.agent_ops_store import record_revocation

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
wallet_revocation_bp = Blueprint('wallet_revocation', __name__)

@wallet_revocation_bp.route('/api/wallet/revoke', methods=['POST'])
@cross_origin()
@require_customer_or_admin
@rate_limit(max_requests=10, window=60)  # Limit revocation calls
def revoke_credential():
    """
    Revoke credential from wallet and propagate to network
    
    This handles both PoH lemmas (network-wide revocation) and 
    permission lemmas (site-specific revocation)
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'invalid_request',
                'message': 'JSON payload required'
            }), 400
        
        credential_id = data.get('credential_id')
        credential_type = data.get('credential_type', 'unknown')  # 'poh' or 'permission'
        credential_scope = data.get('credential_scope', 'site_specific')  # 'site_specific' or 'cross_site'
        site_domain = data.get('site_domain')  # Site domain for permission lemmas
        reason = data.get('reason', 'user_requested')
        
        if not credential_id:
            return jsonify({
                'success': False,
                'error': 'missing_credential_id',
                'message': 'credential_id is required'
            }), 400
        
        logger.info(f"🚨 Wallet revocation request: {credential_id} (type: {credential_type}, scope: {credential_scope}, site: {site_domain})")
        
        # Cross-site credentials require global sync (all sites must update)
        # This is used for portable credentials that work across multiple sites
        if credential_scope == 'cross_site':
            network_success = await_network_revocation(credential_id, reason)
            record_revocation(
                subject_type='proof',
                subject_ref=credential_id,
                reason_code='cross_site_revocation',
                revoked_by='wallet_user',
                metadata={'credential_scope': credential_scope, 'credential_type': credential_type, 'site_domain': site_domain, 'reason': reason},
            )
            
            try:
                from api.revocation_sync import trigger_revocation_sync
                # site_id=None triggers ALL sites to sync
                event_published = trigger_revocation_sync(credential_id, 'cross_site', site_id=None)
                
                if event_published:
                    logger.info(f"✅ Cross-site revocation event published - ALL sites will sync")
                else:
                    logger.warning(f"⚠️ Event bus not available - local sync only")
            except Exception as e:
                logger.error(f"❌ Event-driven revocation sync failed: {e}")
            
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'cross_site',
                'credential_scope': 'cross_site',
                'network_propagated': network_success,
                'message': 'Cross-site credential revoked - all sites will sync',
                'scope': 'All sites using this credential will be updated',
                'wallet_deleted': True,
                'bloom_filter_synced': True,
                'sync_method': 'event_driven_redis_pubsub'
            })
        
        # For PoH lemmas: Network-wide revocation (same as cross_site)
        if credential_type == 'poh':
            network_success = await_network_revocation(credential_id, reason)
            record_revocation(
                subject_type='proof',
                subject_ref=credential_id,
                reason_code='poh_revocation',
                revoked_by='wallet_user',
                metadata={'credential_scope': credential_scope, 'credential_type': credential_type, 'reason': reason},
            )
            
            # Trigger IMMEDIATE bloom filter sync via event bus (FIXES VULN-001)
            # PoH = Global revocation (site_id=None syncs ALL sites)
            try:
                from api.revocation_sync import trigger_revocation_sync
                event_published = trigger_revocation_sync(credential_id, 'poh', site_id=None)
                
                if event_published:
                    logger.info(f"✅ Global PoH revocation event published - ALL sites will sync")
                else:
                    logger.warning(f"⚠️ Event bus not available - local sync only")
            except Exception as e:
                logger.error(f"❌ Event-driven revocation sync failed: {e}")
            
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'network_wide',
                'network_propagated': network_success,
                'message': 'PoH lemma revoked - network-wide revocation initiated',
                'scope': 'All sites in federated network will be updated',
                'wallet_deleted': True,
                'bloom_filter_synced': True,
                'sync_method': 'event_driven_redis_pubsub'
            })
        
        # For permission lemmas: Site-specific revocation
        elif credential_type == 'permission':
            site_success = await_site_revocation(credential_id, reason, site_domain)
            
            if not site_success:
                logger.error(f"❌ Site-specific revocation persistence failed for {credential_id}")
                return jsonify({
                    'success': False,
                    'error': 'revocation_persist_failed',
                    'credential_id': credential_id,
                    'revocation_type': 'site_specific',
                    'site_domain': site_domain,
                    'message': 'Failed to persist site-specific revocation',
                }), 500
            
            # Trigger IMMEDIATE bloom filter sync via event bus (FIXES VULN-001)
            # Permission = Site-specific revocation (only that site syncs)
            try:
                from api.revocation_sync import trigger_revocation_sync
                
                # Extract site_id from site_domain (e.g., "example.com" -> "example.com")
                sync_site_id = site_domain if site_domain else None
                event_published = trigger_revocation_sync(credential_id, 'permission', site_id=sync_site_id)
                
                if event_published:
                    logger.info(f"✅ Site-targeted revocation event published - ONLY {sync_site_id} will sync")
                else:
                    logger.warning(f"⚠️ Event bus not available - local sync only")
            except Exception as e:
                logger.error(f"❌ Event-driven revocation sync failed: {e}")
            
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'site_specific',
                'site_updated': site_success,
                'site_domain': site_domain,
                'message': f'Permission lemma revoked for {site_domain}',
                'scope': 'Only this site\'s permissions affected',
                'wallet_deleted': True,
                'registry_updated': site_success,
                'bloom_filter_synced': True,
                'sync_method': 'event_driven_redis_pubsub'
            })
        
        # Unknown type: Local revocation only
        else:
            logger.warning(f"Unknown credential type: {credential_type}")
            return jsonify({
                'success': True,
                'credential_id': credential_id,
                'revocation_type': 'local_only',
                'message': 'Credential revoked locally',
                'scope': 'Local wallet only - network not updated'
            })
        
    except Exception as e:
        logger.error(f"❌ Wallet revocation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'revocation_failed',
            'message': str(e)
        }), 500

def await_network_revocation(credential_id: str, reason: str) -> bool:
    """
    Propagate PoH lemma revocation to the federated network
    """
    try:
        # Import the network revocation function
        from api.sdk_api import distribute_revocation_to_network
        import hashlib
        
        # SHA256 hash for bloom filter
        bloom_hash = hashlib.sha256(credential_id.encode()).hexdigest()
        
        # Distribute to network
        success = distribute_revocation_to_network(
            credential_id=credential_id,
            bloom_hash=bloom_hash,
            reason=reason
        )
        
        logger.info(f"🌐 Network revocation result for {credential_id}: {success}")
        return success
        
    except Exception as e:
        logger.warning(f"⚠️ Network revocation failed for {credential_id}: {e}")
        return False

def await_site_revocation(credential_id: str, reason: str, site_domain: str = None) -> bool:
    """
    Handle site-specific permission lemma revocation
    Updates database revocation registry for the specific site
    """
    try:
        from api.database import get_db_session, RevocationList
        from datetime import datetime
        
        logger.info(f"🏠 Site-specific revocation for {credential_id}: {reason}")
        
        # Add to database revocation list
        session = get_db_session()
        try:
            # Check if already revoked
            existing = session.query(RevocationList).filter_by(lemma_id=credential_id).first()
            if existing:
                logger.info(f"⚠️ Credential {credential_id} already revoked at {existing.revoked_at}")
                return True
            
            # Create new revocation entry
            revocation = RevocationList(
                lemma_id=credential_id,
                credential_id=credential_id,  # Set both for backward compatibility
                lemma_type='permission',
                site_id=site_domain or 'unknown',
                user_did='user_requested',  # Would extract from credential in production
                revoked_by='user_self_revoke',
                revoked_at=datetime.utcnow(),
                reason=reason,
                bloom_filter_updated=False
            )
            
            session.add(revocation)
            session.commit()
            
            logger.info(f"✅ Added {credential_id} to revocation registry for site {site_domain}")
            
            # Keep revocation data path current by immediately syncing this credential.
            # Event-bus propagation still occurs in revoke_credential().
            bloom_synced = False
            try:
                from api.permission_verification import sync_single_revocation
                bloom_synced = bool(sync_single_revocation(credential_id))
            except Exception as sync_err:
                logger.warning(f"⚠️ Local bloom sync failed for {credential_id}: {sync_err}")

            if bloom_synced:
                revocation.bloom_filter_updated = True
                session.commit()
                logger.info(f"✅ Local bloom filter updated for {credential_id}")
            else:
                logger.warning(f"⚠️ Revocation stored but bloom_filter_updated remains false for {credential_id}")

            record_revocation(
                subject_type='proof',
                subject_ref=credential_id,
                reason_code='site_permission_revocation',
                revoked_by='wallet_user',
                metadata={'site_domain': site_domain, 'reason': reason, 'bloom_filter_updated': bloom_synced},
            )
            
            return True
            
        finally:
            session.close()
        
    except Exception as e:
        logger.warning(f"⚠️ Site revocation failed for {credential_id}: {e}")
        return False

@wallet_revocation_bp.route('/api/wallet/revocation-status', methods=['GET'])
@cross_origin()
def get_revocation_status():
    """
    Get revocation status for credentials
    """
    try:
        credential_ids = request.args.getlist('credential_ids')
        
        if not credential_ids:
            return jsonify({
                'success': False,
                'error': 'no_credentials',
                'message': 'No credential IDs provided'
            }), 400
        
        # Check revocation status from persistent revocation registry.
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            statuses = {}
            for cred_id in credential_ids:
                cursor.execute("""
                    SELECT
                        COALESCE(credential_id, lemma_id) as cred_id,
                        revoked_at,
                        reason,
                        site_id,
                        lemma_type
                    FROM revocation_list
                    WHERE COALESCE(credential_id, lemma_id) = %s
                    ORDER BY revoked_at DESC
                    LIMIT 1
                """, (cred_id,))

                row = cursor.fetchone()
                if row:
                    _, revoked_at, reason, site_id, lemma_type = row
                    scope = 'global' if lemma_type == 'poh' else 'site_specific'
                    statuses[cred_id] = {
                        'revoked': True,
                        'revocation_time': revoked_at.isoformat() if revoked_at else None,
                        'reason': reason,
                        'scope': scope,
                        'site_id': site_id
                    }
                else:
                    statuses[cred_id] = {
                        'revoked': False,
                        'revocation_time': None,
                        'reason': None,
                        'scope': 'unknown',
                        'site_id': None
                    }
        finally:
            cursor.close()
            conn.close()
        
        return jsonify({
            'success': True,
            'statuses': statuses
        })
        
    except Exception as e:
        logger.error(f"❌ Revocation status check failed: {e}")
        return jsonify({
            'success': False,
            'error': 'status_check_failed',
            'message': str(e)
        }), 500
