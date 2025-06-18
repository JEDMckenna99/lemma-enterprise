"""
🧪 LEMMA SANDBOX ENVIRONMENT
===========================
Test KYC Issuer and Fake Revocation Events for Development
Provides safe testing environment without real verification
"""

import os
import json
import uuid
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from flask import Blueprint, request, jsonify, current_app
import logging

from ..core.credential_service import get_credential_service
from ..auth.security import api_key_required
from ..utils.input_validation import validate_input, ValidationError

logger = logging.getLogger(__name__)

sandbox_bp = Blueprint('sandbox', __name__, url_prefix='/api/sandbox')

# ============================================================================
# SANDBOX CONFIGURATION
# ============================================================================

SANDBOX_ENABLED = os.environ.get('LEMMA_SANDBOX_ENABLED', 'true').lower() == 'true'
SANDBOX_KYC_ISSUER = "did:lemma:sandbox-kyc"
SANDBOX_DOMAIN = "sandbox.lemma.network"

# Test user profiles for sandbox
SANDBOX_TEST_PROFILES = [
    {
        "user_id": "test_user_alice",
        "name": "Alice Developer",
        "description": "Test user for basic verification flows",
        "verification_status": "verified",
        "issued_at": "2025-01-01T00:00:00Z"
    },
    {
        "user_id": "test_user_bob", 
        "name": "Bob Tester",
        "description": "Test user for edge cases and error handling",
        "verification_status": "verified",
        "issued_at": "2025-01-15T12:00:00Z"
    },
    {
        "user_id": "test_user_charlie",
        "name": "Charlie QA",
        "description": "Test user for automated testing",
        "verification_status": "verified", 
        "issued_at": "2025-02-01T08:30:00Z"
    },
    {
        "user_id": "test_user_revoked",
        "name": "Revoked User",
        "description": "Test user with revoked credential for testing revocation flow",
        "verification_status": "revoked",
        "issued_at": "2025-01-01T00:00:00Z",
        "revoked_at": "2025-01-15T10:00:00Z",
        "revocation_reason": "Testing revocation workflow"
    }
]

# Fake revocation events for testing
SANDBOX_REVOCATION_EVENTS = [
    {
        "credential_id": "cred_sandbox_001",
        "user_id": "test_user_revoked",
        "revoked_at": "2025-01-15T10:00:00Z",
        "reason": "Testing revocation workflow",
        "issuer": SANDBOX_KYC_ISSUER,
        "event_type": "manual_revocation"
    },
    {
        "credential_id": "cred_sandbox_002", 
        "user_id": "test_user_expired",
        "revoked_at": "2025-01-20T15:30:00Z",
        "reason": "Credential expired",
        "issuer": SANDBOX_KYC_ISSUER,
        "event_type": "expiration"
    },
    {
        "credential_id": "cred_sandbox_003",
        "user_id": "test_user_compliance",
        "revoked_at": "2025-01-25T09:15:00Z", 
        "reason": "Compliance policy violation",
        "issuer": SANDBOX_KYC_ISSUER,
        "event_type": "compliance_revocation"
    }
]

# ============================================================================
# SANDBOX MIDDLEWARE
# ============================================================================

def require_sandbox_enabled(f):
    """Decorator to ensure sandbox is enabled."""
    def decorated_function(*args, **kwargs):
        if not SANDBOX_ENABLED:
            return jsonify({
                'success': False,
                'error': 'Sandbox environment is disabled',
                'hint': 'Set LEMMA_SANDBOX_ENABLED=true to enable sandbox features'
            }), 403
        return f(*args, **kwargs)
    
    decorated_function.__name__ = f.__name__
    return decorated_function

# ============================================================================
# SANDBOX ENDPOINTS
# ============================================================================

@sandbox_bp.route('/status', methods=['GET'])
def sandbox_status():
    """Get sandbox environment status and configuration."""
    return jsonify({
        'success': True,
        'data': {
            'sandbox_enabled': SANDBOX_ENABLED,
            'environment': 'sandbox',
            'kyc_issuer': SANDBOX_KYC_ISSUER,
            'domain': SANDBOX_DOMAIN,
            'test_profiles_count': len(SANDBOX_TEST_PROFILES),
            'revocation_events_count': len(SANDBOX_REVOCATION_EVENTS),
            'capabilities': [
                'test_credential_issuance',
                'fake_kyc_verification', 
                'revocation_simulation',
                'edge_case_testing'
            ],
            'warning': 'This is a sandbox environment. Credentials are for testing only.'
        }
    })

@sandbox_bp.route('/credentials', methods=['GET'])
@require_sandbox_enabled
def list_test_credentials():
    """Get list of available test credentials."""
    try:
        # Generate test credentials for each profile
        test_credentials = []
        
        for profile in SANDBOX_TEST_PROFILES:
            if profile['verification_status'] != 'revoked':
                credential = _generate_test_credential(profile)
                test_credentials.append({
                    'user_id': profile['user_id'],
                    'credential': credential,
                    'description': profile['description'],
                    'issued_at': profile['issued_at']
                })
        
        return jsonify({
            'success': True,
            'data': {
                'test_credentials': test_credentials,
                'count': len(test_credentials),
                'note': 'These credentials are for testing only and will not work in production'
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list test credentials: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate test credentials'
        }), 500

@sandbox_bp.route('/credentials/issue', methods=['POST'])
@require_sandbox_enabled
def issue_test_credential():
    """Issue a new test credential for sandbox testing."""
    try:
        data = request.get_json()
        user_id = validate_input(data.get('user_id'), 'user_id')
        
        # Allow custom user IDs or use test profile
        if not user_id:
            user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        
        # Create custom profile or use existing
        profile = next((p for p in SANDBOX_TEST_PROFILES if p['user_id'] == user_id), None)
        if not profile:
            profile = {
                'user_id': user_id,
                'name': f"Test User {user_id}",
                'description': "Custom test user for sandbox testing",
                'verification_status': 'verified',
                'issued_at': datetime.now(timezone.utc).isoformat()
            }
        
        credential = _generate_test_credential(profile)
        
        return jsonify({
            'success': True,
            'data': {
                'credential': credential,
                'user_id': user_id,
                'sandbox_note': 'This is a test credential for development only'
            }
        })
        
    except ValidationError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to issue test credential: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to issue test credential'
        }), 500

@sandbox_bp.route('/kyc/verify', methods=['POST'])
@require_sandbox_enabled  
def sandbox_kyc_verification():
    """Simulate KYC verification process for testing."""
    try:
        data = request.get_json()
        user_id = validate_input(data.get('user_id'), 'user_id')
        verification_type = data.get('verification_type', 'standard')
        
        # Simulate different verification outcomes
        verification_scenarios = {
            'standard': {'success': True, 'result': 'verified'},
            'failure': {'success': False, 'result': 'failed', 'reason': 'Document verification failed'},
            'pending': {'success': True, 'result': 'pending', 'reason': 'Manual review required'},
            'expired': {'success': False, 'result': 'expired', 'reason': 'Document expired'},
            'fraud': {'success': False, 'result': 'fraud_detected', 'reason': 'Potential fraud detected'}
        }
        
        scenario = verification_scenarios.get(verification_type, verification_scenarios['standard'])
        
        # Simulate processing delay
        import time
        time.sleep(0.5)  # Simulate API call delay
        
        response_data = {
            'verification_id': f"kyc_sandbox_{uuid.uuid4().hex[:12]}",
            'user_id': user_id,
            'status': scenario['result'],
            'verified_at': datetime.now(timezone.utc).isoformat(),
            'issuer': SANDBOX_KYC_ISSUER,
            'sandbox_scenario': verification_type
        }
        
        if 'reason' in scenario:
            response_data['reason'] = scenario['reason']
            
        return jsonify({
            'success': scenario['success'],
            'data': response_data
        })
        
    except ValidationError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Sandbox KYC verification failed: {e}")
        return jsonify({
            'success': False,
            'error': 'KYC verification simulation failed'
        }), 500

@sandbox_bp.route('/revocation/events', methods=['GET'])
@require_sandbox_enabled
def get_revocation_events():
    """Get fake revocation events for testing revocation handling."""
    try:
        # Add some random recent events for testing
        recent_events = []
        for i in range(3):
            import secrets
            event_time = datetime.now(timezone.utc) - timedelta(hours=secrets.randbelow(72) + 1)
            recent_events.append({
                'credential_id': f"cred_sandbox_recent_{i+1}",
                'user_id': f"test_user_recent_{i+1}",
                'revoked_at': event_time.isoformat(),
                'reason': secrets.choice(['Testing', 'Simulation', 'Development']),
                'issuer': SANDBOX_KYC_ISSUER,
                'event_type': 'sandbox_simulation'
            })
        
        all_events = SANDBOX_REVOCATION_EVENTS + recent_events
        
        return jsonify({
            'success': True,
            'data': {
                'revocation_events': all_events,
                'count': len(all_events),
                'note': 'These are simulated revocation events for testing only'
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get revocation events: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve revocation events'
        }), 500

@sandbox_bp.route('/revocation/simulate', methods=['POST'])
@require_sandbox_enabled
def simulate_revocation():
    """Simulate credential revocation for testing."""
    try:
        data = request.get_json()
        credential_id = validate_input(data.get('credential_id'), 'string')
        reason = data.get('reason', 'Testing revocation flow')
        
        # Create simulated revocation event
        revocation_event = {
            'credential_id': credential_id,
            'revoked_at': datetime.now(timezone.utc).isoformat(),
            'reason': reason,
            'issuer': SANDBOX_KYC_ISSUER,
            'event_type': 'sandbox_simulation',
            'simulation_id': str(uuid.uuid4())
        }
        
        return jsonify({
            'success': True,
            'data': {
                'revocation_event': revocation_event,
                'message': 'Revocation simulated successfully',
                'note': 'This is a simulated revocation for testing only'
            }
        })
        
    except ValidationError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to simulate revocation: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to simulate revocation'
        }), 500

@sandbox_bp.route('/test-scenarios', methods=['GET'])
@require_sandbox_enabled
def get_test_scenarios():
    """Get comprehensive test scenarios for different use cases."""
    scenarios = {
        'basic_verification': {
            'description': 'Basic human verification flow',
            'steps': [
                'Generate challenge using /api/generate-challenge',
                'Get test credential from /api/sandbox/credentials',
                'Verify using /api/verify-human'
            ],
            'expected_result': 'Successful verification'
        },
        'revocation_testing': {
            'description': 'Test revocation detection and handling',
            'steps': [
                'Get revoked credential (test_user_revoked)',
                'Attempt verification',
                'Handle revocation error appropriately'
            ],
            'expected_result': 'Verification fails with revocation error'
        },
        'kyc_simulation': {
            'description': 'Test different KYC verification outcomes',
            'steps': [
                'Call /api/sandbox/kyc/verify with different verification_type values',
                'Handle success, failure, pending, and fraud scenarios',
                'Test appropriate error handling for each case'
            ],
            'expected_result': 'Different outcomes based on scenario type'
        },
        'edge_cases': {
            'description': 'Test edge cases and error conditions',
            'steps': [
                'Test with malformed credentials',
                'Test with expired challenges',
                'Test with invalid domain bindings',
                'Test rate limiting behavior'
            ],
            'expected_result': 'Appropriate error responses for each edge case'
        }
    }
    
    return jsonify({
        'success': True,
        'data': {
            'test_scenarios': scenarios,
            'sandbox_endpoints': [
                '/api/sandbox/status',
                '/api/sandbox/credentials',
                '/api/sandbox/credentials/issue',
                '/api/sandbox/kyc/verify',
                '/api/sandbox/revocation/events',
                '/api/sandbox/revocation/simulate'
            ]
        }
    })

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _generate_test_credential(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a test credential for sandbox use."""
    try:
        credential_service = get_credential_service()
        
        # Create test credential with sandbox issuer
        credential_data = {
            'user_id': profile['user_id'],
            'issuer_did': SANDBOX_KYC_ISSUER,
            'verification_method': 'sandbox',
            'issued_at': profile['issued_at'],
            'expires_at': (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
            'sandbox': True
        }
        
        # Generate the credential (this will use sandbox keys)
        credential = credential_service.issue_credential(
            profile['user_id'],
            credential_data
        )
        
        # Add sandbox-specific metadata
        credential['sandbox_profile'] = profile['name']
        credential['sandbox_description'] = profile['description']
        credential['sandbox_warning'] = 'This credential is for testing only'
        
        return credential
        
    except Exception as e:
        logger.error(f"Failed to generate test credential: {e}")
        raise Exception("Test credential generation failed")

def _is_sandbox_request() -> bool:
    """Check if the current request is from sandbox environment."""
    return (
        request.headers.get('X-Lemma-Environment') == 'sandbox' or
        'sandbox' in request.headers.get('User-Agent', '').lower() or
        request.headers.get('X-Sandbox-Mode') == 'true'
    )

# ============================================================================
# SANDBOX INITIALIZATION
# ============================================================================

def init_sandbox():
    """Initialize sandbox environment if enabled."""
    if SANDBOX_ENABLED:
        logger.info("🧪 Sandbox environment initialized")
        logger.info(f"Sandbox KYC Issuer: {SANDBOX_KYC_ISSUER}")
        logger.info(f"Test profiles available: {len(SANDBOX_TEST_PROFILES)}")
        logger.info(f"Revocation events available: {len(SANDBOX_REVOCATION_EVENTS)}")
    else:
        logger.info("Sandbox environment disabled")

# Initialize on module import
init_sandbox() 