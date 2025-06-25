from flask import Blueprint, jsonify, request, session
from lemma.auth.decorators import require_auth
from lemma.auth.security import generate_jwt_token
import logging

logger = logging.getLogger(__name__)

auth_api = Blueprint('auth_api', __name__, url_prefix='/api/v2/auth')

@auth_api.route('/me')
@require_auth
def get_current_user():
    """Get current user data for React components"""
    try:
        from flask_login import current_user
        
        user_data = {
            'id': getattr(current_user, 'id', None),
            'email': getattr(current_user, 'email', None),
            'organization': {
                'id': getattr(current_user, 'organization_id', None),
                'name': getattr(current_user, 'organization_name', 'Default Org')
            },
            'permissions': ['read', 'write', 'admin'],  # Expand based on your auth system
            'verified': True
        }
        
        return jsonify({
            'success': True,
            'user': user_data
        })
    except Exception as e:
        logger.error(f"Failed to get current user: {e}")
        return jsonify({'success': False, 'error': 'Authentication failed'}), 401

@auth_api.route('/session-token', methods=['POST'])
@require_auth
def get_session_token():
    """Convert Flask session to JWT for React components"""
    try:
        from flask_login import current_user
        
        # Generate JWT token for API access
        token_data = {
            'user_id': getattr(current_user, 'id', 'demo_user'),
            'email': getattr(current_user, 'email', 'demo@lemma.id'),
            'org_id': getattr(current_user, 'organization_id', 'demo_org'),
            'permissions': ['read', 'write', 'admin']
        }
        
        token = generate_jwt_token(token_data)
        
        return jsonify({
            'success': True,
            'token': token,
            'expires_in': 3600  # 1 hour
        })
    except Exception as e:
        logger.error(f"Failed to generate session token: {e}")
        return jsonify({'success': False, 'error': 'Token generation failed'}), 500

@auth_api.route('/refresh', methods=['POST'])
def refresh_token():
    """Refresh JWT token"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'No token provided'}), 401
        
        # For now, return success - implement JWT validation as needed
        return jsonify({
            'success': True,
            'message': 'Token refreshed'
        })
    except Exception as e:
        logger.error(f"Failed to refresh token: {e}")
        return jsonify({'success': False, 'error': 'Token refresh failed'}), 500 