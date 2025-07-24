"""
Lemma Shield - Real Implementation
==================================
Simple shield that checks: "Does this user have a valid lemma credential?"

Three flows:
1. SHIELD CHECK: Check for valid lemma credential in user's wallet
2. VERIFICATION: Get credential via Stripe Identity verification  
3. REVOCATION: Handle expired/compromised credentials

Usage:
    @lemma_shield_required
    def protected_page():
        return render_template('protected.html')
"""

import os
import time
import json
import logging
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template
from functools import wraps
from typing import Dict, List, Optional, Any

# Define logger FIRST before any usage
logger = logging.getLogger(__name__)

# Import Rust engine with proper Python bindings
try:
    from lemma_crypto import PyLemmaCore, PyVerificationResult
    RUST_ENGINE_AVAILABLE = True
    logger.info("✅ Rust engine imports successful")
except ImportError:
    RUST_ENGINE_AVAILABLE = False
    logger.warning("⚠️ Rust engine not available, using Python fallback")

# Import optimized engine if available
try:
    from .optimized_shield import get_optimized_engine
    OPTIMIZED_ENGINE_AVAILABLE = True
    logger.info("✅ Optimized engine integration enabled")
except ImportError:
    OPTIMIZED_ENGINE_AVAILABLE = False
    logger.warning("⚠️ Optimized engine not available, using fallback")

# Create blueprint
lemma_shield_bp = Blueprint('lemma_shield', __name__)

# Global Rust engine instance
rust_engine = None

def initialize_shield():
    """Initialize the Lemma Shield with Rust engine"""
    global rust_engine, RUST_ENGINE_AVAILABLE
    
    if not RUST_ENGINE_AVAILABLE:
        logger.error("❌ Rust engine not available - shield cannot function")
        return False
        
    if rust_engine is None:
        try:
            rust_engine = PyLemmaCore()
            rust_engine.register_identity_package()
            logger.info("✅ Lemma Shield initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize Lemma Shield: {e}")
            RUST_ENGINE_AVAILABLE = False
            return False
    
    return True

# Initialize on module load
initialize_shield()

# ============================================================================
# SHIELD CHECK FLOW: Check for valid lemma credential
# ============================================================================

def has_valid_lemma_credential(user_id: str = None) -> Dict[str, Any]:
    """
    SHIELD CHECK FLOW: Check if user has valid lemma credential
    
    Returns:
        {
            'has_credential': bool,
            'credential': dict or None,
            'reason': str,
            'verification_time_ns': int
        }
    """
    start_time = time.time_ns()
    
    # Check if Rust engine is available - use fallback if not
    if not RUST_ENGINE_AVAILABLE or not rust_engine:
        logger.warning("Rust engine not available, using Python fallback mode")
        # Python fallback mode - simplified credential check
        stored_credential = session.get('lemma_credential')
        if stored_credential:
            return {
                'has_credential': True,
                'credential': stored_credential,
                'reason': 'python_fallback_found',
                'verification_time_ns': time.time_ns() - start_time,
                'fallback_mode': True
            }
        else:
            return {
                'has_credential': False,
                'credential': None,
                'reason': 'python_fallback_no_credential',
                'verification_time_ns': time.time_ns() - start_time,
                'fallback_mode': True
            }
    
    # 1. Check session for stored credential
    stored_credential = session.get('lemma_credential')
    if not stored_credential:
        return {
            'has_credential': False,
            'credential': None,
            'reason': 'no_credential_in_session',
            'verification_time_ns': time.time_ns() - start_time
        }
    
    # 2. Verify credential with Rust engine
    try:
        credential_json = json.dumps(stored_credential)
        result = rust_engine.verify_credential(credential_json)
        
        verification_time = time.time_ns() - start_time
        
        if result.get('verified', False):
            # Valid credential found
            return {
                'has_credential': True,
                'credential': stored_credential,
                'reason': 'valid_credential_verified',
                'verification_time_ns': verification_time,
                'confidence': result.get('confidence', 0.95),
                'offline': result.get('offline', True)
            }
        else:
            # Invalid credential
            return {
                'has_credential': False,
                'credential': stored_credential,
                'reason': 'credential_verification_failed',
                'verification_time_ns': verification_time,
                'error': result.get('error', 'Unknown verification error')
            }
    
    except Exception as e:
        logger.error(f"Credential verification error: {e}")
        return {
            'has_credential': False,
            'credential': stored_credential,
            'reason': 'verification_error',
            'verification_time_ns': time.time_ns() - start_time,
            'error': str(e)
        }

# ============================================================================
# VERIFICATION FLOW: Get credential via Stripe Identity
# ============================================================================

def create_lemma_credential(user_id: str, stripe_session_id: str) -> Dict[str, Any]:
    """
    Create a lemma credential after successful Stripe Identity verification
    """
    return {
        'id': f"lemma_credential_{user_id}_{int(time.time())}",
        'type': 'VerifiedHuman',
        'issuer': 'did:lemma:stripe_identity',
        'subject': f'did:lemma:user:{user_id}',
        'issuedAt': int(time.time()),
        'expiresAt': int(time.time()) + (86400 * 30),  # 30 days
        'claims': {
            'isHuman': True,
            'verificationMethod': 'stripe_identity',
            'verificationLevel': 'high_assurance',
            'verifiedAt': int(time.time())
        },
        'proof': {
            'type': 'StripeIdentityProof',
            'sessionId': stripe_session_id,
            'verifiedAt': int(time.time())
        }
    }

# ============================================================================
# SHIELD DECORATOR: Protect routes with lemma credential check
# ============================================================================

def lemma_shield_required(f):
    """
    Decorator to protect routes with Lemma Shield
    
    Usage:
        @app.route('/protected')
        @lemma_shield_required
        def protected_page():
            return render_template('protected.html')
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # SHIELD CHECK FLOW
        check_result = has_valid_lemma_credential()
        
        if check_result['has_credential']:
            # ✅ Valid credential - allow access
            logger.info(f"✅ Shield check passed - valid credential found")
            return f(*args, **kwargs)
        else:
            # ❌ No valid credential - redirect to verification
            logger.info(f"❌ Shield check failed: {check_result['reason']}")
            
            # Store the original URL they were trying to access
            session['return_url'] = request.url
            
            # Redirect to verification flow
            return redirect(url_for('lemma_shield.start_verification'))
    
    return decorated_function

# ============================================================================
# API ENDPOINTS
# ============================================================================

@lemma_shield_bp.route('/lemma/start-verification')
def start_verification():
    """
    VERIFICATION FLOW: Start Stripe Identity verification
    """
    try:
        # Generate user ID if not exists
        user_id = session.get('user_id')
        if not user_id:
            user_id = f"user_{int(time.time())}_{os.urandom(4).hex()}"
            session['user_id'] = user_id
        
        # Import Stripe manager
        try:
            from billing.stripe_manager import StripeManager
            stripe_manager = StripeManager()
        except ImportError:
            logger.error("Stripe manager not available")
            return jsonify({
                'success': False,
                'error': 'stripe_not_configured',
                'message': 'Stripe Identity verification not available'
            }), 503
        
        # Create verification session
        return_url = url_for('lemma_shield.verification_complete', _external=True)
        
        session_result = stripe_manager.create_identity_verification_session(
            user_id=user_id,
            return_url=return_url
        )
        
        if session_result.get('success'):
            # Store session info
            session['stripe_session_id'] = session_result['session_id']
            session['verification_started'] = time.time()
            
            # Redirect to Stripe Identity
            return redirect(session_result['url'])
        else:
            return jsonify({
                'success': False,
                'error': 'stripe_session_failed',
                'message': 'Failed to start verification'
            }), 500
    
    except Exception as e:
        logger.error(f"Verification start error: {e}")
        return jsonify({
            'success': False,
            'error': 'verification_error',
            'message': 'Failed to start verification'
        }), 500

@lemma_shield_bp.route('/lemma/verification-complete')
def verification_complete():
    """
    VERIFICATION FLOW: Handle completed Stripe Identity verification
    """
    try:
        user_id = session.get('user_id')
        stripe_session_id = session.get('stripe_session_id')
        
        if not user_id or not stripe_session_id:
            return jsonify({
                'success': False,
                'error': 'missing_session_data',
                'message': 'Verification session not found'
            }), 400
        
        # Check verification status with Stripe
        try:
            from billing.stripe_manager import StripeManager
            stripe_manager = StripeManager()
            
            verification_result = stripe_manager.get_identity_verification_session(stripe_session_id)
            
            if verification_result.get('success') and verification_result.get('status') == 'verified':
                # ✅ Verification successful - create lemma credential
                credential = create_lemma_credential(user_id, stripe_session_id)
                
                # Store credential in session (user's "wallet")
                session['lemma_credential'] = credential
                session['verified_at'] = time.time()
                
                logger.info(f"✅ Lemma credential created for user {user_id}")
                
                # Redirect back to original page
                return_url = session.pop('return_url', '/')
                return redirect(return_url)
                
            else:
                # ❌ Verification failed
                status = verification_result.get('status', 'unknown')
                logger.warning(f"❌ Stripe verification failed: {status}")
                
                return render_template('verification_failed.html', 
                                     status=status, 
                                     error=verification_result.get('error'))
        
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'stripe_not_configured',
                'message': 'Stripe verification not available'
            }), 503
    
    except Exception as e:
        logger.error(f"Verification completion error: {e}")
        return jsonify({
            'success': False,
            'error': 'verification_error',
            'message': 'Failed to complete verification'
        }), 500

@lemma_shield_bp.route('/lemma/check-credential')
def check_credential():
    """
    API endpoint to check if user has valid lemma credential
    """
    try:
        user_id = session.get('user_id')
        result = has_valid_lemma_credential(user_id)
        
        return jsonify({
            'success': True,
            'has_credential': result['has_credential'],
            'reason': result['reason'],
            'verification_time_ns': result['verification_time_ns'],
            'verification_time_us': round(result['verification_time_ns'] / 1000, 2),
            'user_id': user_id
        })
    
    except Exception as e:
        logger.error(f"Credential check error: {e}")
        return jsonify({
            'success': False,
            'error': 'check_failed',
            'message': 'Failed to check credential'
        }), 500

@lemma_shield_bp.route('/lemma/revoke-credential', methods=['POST'])
def revoke_credential():
    """
    REVOCATION FLOW: Revoke user's lemma credential
    """
    try:
        # Clear credential from session
        session.pop('lemma_credential', None)
        session.pop('verified_at', None)
        
        logger.info("🚫 Lemma credential revoked")
        
        return jsonify({
            'success': True,
            'message': 'Credential revoked successfully'
        })
    
    except Exception as e:
        logger.error(f"Revocation error: {e}")
        return jsonify({
            'success': False,
            'error': 'revocation_failed',
            'message': 'Failed to revoke credential'
        }), 500

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_shield_status():
    """Get current shield status"""
    return {
        'shield_enabled': True,  # Enable shield even without Rust (fallback mode)
        'rust_engine_available': RUST_ENGINE_AVAILABLE,
        'engine_initialized': rust_engine is not None,
        'version': '1.0.0'
    }

def protect_page_with_shield(page_route):
    """
    Helper function to protect a page with Lemma Shield
    
    Usage:
        @app.route('/protected')
        def protected_page():
            return protect_page_with_shield(lambda: render_template('protected.html'))
    """
    check_result = has_valid_lemma_credential()
    
    if check_result['has_credential']:
        return page_route()
    else:
        session['return_url'] = request.url
        return redirect(url_for('lemma_shield.start_verification')) 