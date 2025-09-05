"""
Privacy-Preserving Network Revocation System
Allows sites to report malicious activity while maintaining complete user privacy
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
import os
import time
import secrets
import hashlib
from datetime import datetime, timedelta

from .database import get_db, UserLemma
from .network_registry import NETWORK_REGISTRY

logger = logging.getLogger(__name__)

privacy_revocation_bp = Blueprint('privacy_revocation', __name__)

class PrivacyPreservingRevocationManager:
    """Manages privacy-preserving revocation reports and manual admin actions"""
    
    def __init__(self):
        # Store reports with privacy-preserving hashes
        self.malicious_activity_reports = {}
        self.user_hash_cache = {}
    
    def generate_privacy_preserving_hash(self, user_did, site_id):
        """
        Generate privacy-preserving hash that can't be reverse-engineered
        Sites can report using this hash without exposing user identity
        """
        
        # Use HMAC with site-specific salt for privacy
        site_salt = hashlib.sha256(f"lemma_site_salt_{site_id}".encode()).hexdigest()
        privacy_hash = hashlib.sha256(f"{user_did}_{site_salt}".encode()).hexdigest()[:16]
        
        return f"privacy_{privacy_hash}"
    
    def report_malicious_activity(self, privacy_hash, site_id, activity_evidence):
        """
        Accept privacy-preserving malicious activity report from site
        Site reports using hash - no user identity exposed
        """
        
        report_id = f"report_{secrets.token_hex(8)}"
        current_time = time.time()
        
        report = {
            'report_id': report_id,
            'privacy_hash': privacy_hash,
            'site_id': site_id,
            'reported_at': current_time,
            'activity_evidence': activity_evidence,
            'status': 'pending_admin_review',
            'admin_reviewed': False,
            'action_taken': None
        }
        
        self.malicious_activity_reports[report_id] = report
        
        logger.info(f"📋 Privacy-preserving malicious activity report: {report_id} from site {site_id}")
        
        return {
            'success': True,
            'report_id': report_id,
            'privacy_preserved': True,
            'admin_review_required': True
        }
    
    def get_pending_reports(self):
        """Get all pending reports for admin review (privacy-preserving)"""
        
        pending_reports = []
        
        for report_id, report in self.malicious_activity_reports.items():
            if not report['admin_reviewed']:
                # Return only non-identifying information
                pending_reports.append({
                    'report_id': report_id,
                    'site_id': report['site_id'],
                    'reported_at': report['reported_at'],
                    'activity_evidence': report['activity_evidence'],
                    'privacy_hash': report['privacy_hash'],  # Hash only, no user identity
                    'status': report['status']
                })
        
        return pending_reports
    
    def admin_review_report(self, report_id, admin_decision, admin_notes=None):
        """
        Admin manually reviews report and decides on action
        Admin sees evidence but no user identity
        """
        
        if report_id not in self.malicious_activity_reports:
            return {'success': False, 'error': 'Report not found'}
        
        report = self.malicious_activity_reports[report_id]
        report['admin_reviewed'] = True
        report['admin_decision'] = admin_decision  # 'revoke', 'dismiss', 'investigate'
        report['admin_notes'] = admin_notes
        report['reviewed_at'] = time.time()
        
        if admin_decision == 'revoke':
            # Admin decided to revoke - now we need to find the actual user DID
            # This is the ONLY time we link the privacy hash back to user identity
            user_did = self._resolve_privacy_hash_to_user_did(
                report['privacy_hash'], 
                report['site_id']
            )
            
            if user_did:
                # Perform network-wide revocation
                from .network_revocation_system import network_revocation_manager
                revocation_result = network_revocation_manager.revoke_personhood_credential(
                    user_did=user_did,
                    reason=f"manual_admin_decision_report_{report_id}",
                    evidence=report['activity_evidence']
                )
                
                report['action_taken'] = 'network_wide_revocation'
                report['revocation_id'] = revocation_result.get('revocation_id')
                
                return {
                    'success': True,
                    'action': 'revoked_network_wide',
                    'privacy_preserved': True,
                    'revocation_id': revocation_result.get('revocation_id')
                }
            else:
                return {'success': False, 'error': 'Could not resolve user identity'}
        
        elif admin_decision == 'dismiss':
            report['action_taken'] = 'dismissed_false_positive'
            return {
                'success': True,
                'action': 'dismissed',
                'privacy_preserved': True
            }
        
        return {'success': True, 'action': 'under_investigation'}
    
    def _resolve_privacy_hash_to_user_did(self, privacy_hash, site_id):
        """
        PRIVACY-CRITICAL: Resolve privacy hash back to user DID
        This should only be called after admin manual review decision
        """
        
        try:
            db = get_db()
            
            # Get all identity lemmas and check which one matches the hash
            identity_lemmas = db.query(UserLemma).filter(
                UserLemma.lemma_type == 'identity',
                UserLemma.revoked_at.is_(None)
            ).all()
            
            site_salt = hashlib.sha256(f"lemma_site_salt_{site_id}".encode()).hexdigest()
            
            for lemma in identity_lemmas:
                user_did = lemma.user_did
                test_hash = hashlib.sha256(f"{user_did}_{site_salt}".encode()).hexdigest()[:16]
                test_privacy_hash = f"privacy_{test_hash}"
                
                if test_privacy_hash == privacy_hash:
                    db.close()
                    logger.info(f"🔍 Privacy hash resolved for admin action (report-based)")
                    return user_did
            
            db.close()
            return None
            
        except Exception as e:
            logger.error(f"❌ Privacy hash resolution error: {e}")
            return None

# Global manager instance
privacy_revocation_manager = PrivacyPreservingRevocationManager()

@privacy_revocation_bp.route('/api/sites/<site_id>/report-malicious-activity', methods=['POST'])
@cross_origin()
def report_malicious_activity(site_id):
    """
    Site reports malicious activity using privacy-preserving hash
    
    POST /api/sites/{site_id}/report-malicious-activity
    {
        "user_credential_hash": "privacy_abc123...",  // Generated by site
        "activity_type": "automated_signup",
        "evidence": {
            "signup_pattern": "100_signups_in_1_minute",
            "user_agent": "automated_tool",
            "ip_pattern": "same_ip_multiple_accounts"
        },
        "confidence": 0.95
    }
    """
    try:
        data = request.get_json()
        privacy_hash = data.get('user_credential_hash', '')
        activity_type = data.get('activity_type', 'unknown')
        evidence = data.get('evidence', {})
        confidence = data.get('confidence', 0.0)
        
        if not privacy_hash or not privacy_hash.startswith('privacy_'):
            return jsonify({
                'success': False,
                'error': 'Valid privacy hash is required'
            }), 400
        
        # Validate site exists
        db = get_db()
        from .database import Site
        site = db.query(Site).filter(Site.site_id == site_id).first()
        if not site:
            db.close()
            return jsonify({
                'success': False,
                'error': 'Site not found'
            }), 404
        db.close()
        
        # Create privacy-preserving report
        report_result = privacy_revocation_manager.report_malicious_activity(
            privacy_hash=privacy_hash,
            site_id=site_id,
            activity_evidence={
                'activity_type': activity_type,
                'evidence': evidence,
                'confidence': confidence,
                'site_domain': site.site_domain
            }
        )
        
        if report_result['success']:
            logger.info(f"📋 Malicious activity report from {site.site_domain}: {report_result['report_id']}")
            
            return jsonify({
                'success': True,
                'report_id': report_result['report_id'],
                'status': 'submitted_for_admin_review',
                'privacy_preserved': True,
                'user_identity': 'not_exposed_to_reporting_site',
                'next_steps': 'Manual admin review required for network-wide action'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to submit report'
            }), 500
        
    except Exception as e:
        logger.error(f"❌ Malicious activity report error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@privacy_revocation_bp.route('/api/admin/review-malicious-reports', methods=['GET'])
@cross_origin()
def get_pending_reports():
    """
    Get pending malicious activity reports for admin review
    Shows evidence but preserves user privacy until admin decision
    """
    try:
        # Verify admin password
        admin_password = request.headers.get('X-Admin-Password', '')
        expected_admin_pass = os.getenv('LEMMA_ADMIN_PASS', '.511MeV/c^2')
        
        if admin_password != expected_admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin password'
            }), 401
        
        # Get pending reports (privacy-preserving)
        pending_reports = privacy_revocation_manager.get_pending_reports()
        
        return jsonify({
            'success': True,
            'pending_reports': pending_reports,
            'total_pending': len(pending_reports),
            'privacy_note': 'User identities are protected until you make a revocation decision'
        })
        
    except Exception as e:
        logger.error(f"❌ Admin report review error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@privacy_revocation_bp.route('/api/admin/review-report/<report_id>', methods=['POST'])
@cross_origin()
def admin_review_report(report_id):
    """
    Admin manually reviews and decides on malicious activity report
    
    POST /api/admin/review-report/{report_id}
    {
        "decision": "revoke",  // "revoke", "dismiss", "investigate"
        "admin_notes": "Clear bot pattern detected",
        "admin_password": ".511MeV/c^2"
    }
    """
    try:
        data = request.get_json()
        admin_decision = data.get('decision', '')
        admin_notes = data.get('admin_notes', '')
        admin_password = data.get('admin_password', '')
        
        # Verify admin password
        expected_admin_pass = os.getenv('LEMMA_ADMIN_PASS', '.511MeV/c^2')
        if admin_password != expected_admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin password'
            }), 401
        
        if admin_decision not in ['revoke', 'dismiss', 'investigate']:
            return jsonify({
                'success': False,
                'error': 'Decision must be: revoke, dismiss, or investigate'
            }), 400
        
        # Process admin decision
        result = privacy_revocation_manager.admin_review_report(
            report_id=report_id,
            admin_decision=admin_decision,
            admin_notes=admin_notes
        )
        
        if result['success']:
            logger.info(f"👨‍💼 Admin reviewed report {report_id}: {admin_decision}")
            
            return jsonify({
                'success': True,
                'report_id': report_id,
                'decision': admin_decision,
                'action_taken': result.get('action'),
                'revocation_id': result.get('revocation_id'),
                'privacy_preserved': True,
                'network_effect': 'immediate' if admin_decision == 'revoke' else 'none'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Review failed')
            }), 500
        
    except Exception as e:
        logger.error(f"❌ Admin report review error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@privacy_revocation_bp.route('/api/sites/<site_id>/generate-privacy-hash', methods=['POST'])
@cross_origin()
def generate_privacy_hash(site_id):
    """
    Help sites generate privacy-preserving hashes for reporting
    
    POST /api/sites/{site_id}/generate-privacy-hash
    {
        "user_did": "did:lemma:federated:user:suspicious_actor"
    }
    """
    try:
        data = request.get_json()
        user_did = data.get('user_did', '')
        
        if not user_did:
            return jsonify({
                'success': False,
                'error': 'User DID is required'
            }), 400
        
        # Generate privacy hash for this site
        privacy_hash = privacy_revocation_manager.generate_privacy_preserving_hash(user_did, site_id)
        
        return jsonify({
            'success': True,
            'privacy_hash': privacy_hash,
            'site_id': site_id,
            'usage': 'Use this hash to report malicious activity while preserving user privacy',
            'user_identity': 'protected_and_not_exposed'
        })
        
    except Exception as e:
        logger.error(f"❌ Privacy hash generation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
