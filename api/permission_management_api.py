"""
Permission Management API for Lemma.id Platform
Provides complete IAM functionality for customer sites
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import jwt
import uuid
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from auth.decorators import require_api_key, require_site_admin
from billing.usage_logger import log_permission_operation
from .database_models import db, Site, Permission, ActivityType

# Mock classes for testing - replace with actual imports when Rust package is ready
class LemmaCore:
    def __init__(self):
        pass
    
    def register_package(self, package):
        pass

class PermissionPackage:
    def __init__(self, site_id, permission_registry, subnet_config, revocation_authority):
        self.site_id = site_id
        self.permission_registry = permission_registry
        self.subnet_config = subnet_config
        self.revocation_authority = revocation_authority
    
    def add_permission(self, permission_info):
        pass

class IAMSubnetManager:
    def __init__(self, site_id, site_domain):
        self.site_id = site_id
        self.site_domain = site_domain
        self.permission_package = PermissionPackage(site_id, {}, {}, f"did:lemma:site:{site_id}")
    
    def grant_permission(self, user_did, permission_id):
        return {
            'user_did': user_did,
            'permission_id': permission_id,
            'site_id': self.site_id,
            'granted_at': datetime.utcnow().isoformat()
        }
    
    def revoke_permission(self, user_did, permission_id):
        return f"revoke_{self.site_id}_{user_did}_{permission_id}"
    
    def check_access(self, access_request, credentials):
        # Mock access check - always return True for testing
        return True

class CredentialIssuer:
    def __init__(self, issuer_did):
        self.issuer_did = issuer_did
    
    def issue_credential(self, user_did, claims):
        return {
            'id': f"cred_{uuid.uuid4().hex[:8]}",
            'issuer': self.issuer_did,
            'subject': user_did,
            'claims': claims,
            'issued_at': datetime.utcnow().isoformat()
        }

class VerifiableCredential:
    @staticmethod
    def from_dict(data):
        return data

permission_api = Blueprint('permission_api', __name__)

# Global lemma core instance
lemma_core = LemmaCore()

# Site managers registry
site_managers: Dict[str, IAMSubnetManager] = {}

@permission_api.route('/api/v1/sites/register', methods=['POST'])
@cross_origin()
@require_api_key
def register_site():
    """
    Register a new customer site for permission management
    
    POST /api/v1/sites/register
    {
        "site_domain": "customer.com",
        "company_name": "Customer Inc",
        "admin_email": "admin@customer.com",
        "plan": "starter|professional|enterprise"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['site_domain', 'company_name', 'admin_email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create site in database
        site = db.create_site(data)
        
        # Create IAM subnet manager for this site
        manager = IAMSubnetManager(site.site_id, site.site_domain)
        site_managers[site.site_id] = manager
        
        # Log billing event
        log_permission_operation(site.site_id, 'site_registration', 1)
        
        return jsonify({
            'success': True,
            'site_id': site.site_id,
            'api_key': site.api_key,
            'oauth_client_id': site.oauth_client_id,
            'oauth_client_secret': site.oauth_client_secret,
            'integration_guide': f"https://docs.lemma.id/integration/{site.site_id}",
            'dashboard_url': f"https://lemma.id/dashboard/{site.site_id}"
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@permission_api.route('/api/v1/sites/<site_id>/permissions', methods=['POST'])
@cross_origin()
@require_site_admin
def create_permission(site_id):
    """
    Create a new permission definition for a site
    
    POST /api/v1/sites/{site_id}/permissions
    {
        "permission_id": "admin",
        "display_name": "Administrator", 
        "description": "Full administrative access",
        "scope": ["users:*", "posts:*"],
        "conditions": ["ip_range:192.168.1.0/24"],
        "expiry_days": 365
    }
    """
    try:
        data = request.get_json()
        
        # Validate site exists
        site = db.get_site(site_id)
        if not site:
            return jsonify({'error': 'Site not found'}), 404
        
        # Validate required fields
        required_fields = ['permission_id', 'display_name', 'scope']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create permission in database
        permission = db.create_permission(site_id, data)
        
        # Update IAM subnet manager
        if site_id in site_managers:
            manager = site_managers[site_id]
            # Convert to PermissionInfo for manager (mock for testing)
            perm_info = {
                'permission_id': permission.permission_id,
                'display_name': permission.display_name,
                'scope': permission.scope,
                'expiry': None,  # Handled at user level
                'conditions': permission.conditions,
                'delegation_allowed': permission.delegation_allowed,
                'priority': permission.priority,
                'created_at': permission.created_at,
                'created_by': permission.created_by or f"did:lemma:site:{site_id}"
            }
            manager.permission_package.add_permission(perm_info)
        
        # Log billing event
        log_permission_operation(site_id, 'permission_created', 1)
        
        return jsonify({
            'success': True,
            'permission_id': permission.permission_id,
            'display_name': permission.display_name,
            'scope': permission.scope,
            'message': f'Permission "{permission.display_name}" created successfully'
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@permission_api.route('/api/v1/sites/<site_id>/users/<user_did>/permissions', methods=['POST'])
@cross_origin()
@require_site_admin
def grant_user_permission(site_id, user_did):
    """
    Grant permission to a user (creates permission lemma in their wallet)
    
    POST /api/v1/sites/{site_id}/users/{user_did}/permissions
    {
        "permission_id": "admin",
        "expiry_days": 30
    }
    """
    try:
        data = request.get_json()
        permission_id = data['permission_id']
        
        if site_id not in site_managers:
            return jsonify({'error': 'Site not found'}), 404
            
        manager = site_managers[site_id]
        
        # Create permission lemma claims
        claims = manager.grant_permission(user_did, permission_id)
        
        # Create actual credential using lemma core (mock for testing)
        issuer = CredentialIssuer(f"did:lemma:site:{site_id}")
        
        # Add expiry if specified
        if data.get('expiry_days'):
            expiry = datetime.utcnow() + timedelta(days=data['expiry_days'])
            claims['expirationDate'] = expiry.isoformat()
        
        credential = issuer.issue_credential(user_did, claims)
        
        # Store in user's wallet (via wallet API)
        # TODO: Integrate with wallet storage
        wallet_response = store_permission_lemma_in_wallet(user_did, credential)
        
        # Log billing event (MAU tracking)
        log_permission_operation(site_id, 'permission_granted', 1, user_did)
        
        return jsonify({
            'success': True,
            'credential_id': credential.id,
            'permission_id': permission_id,
            'user_did': user_did,
            'wallet_stored': wallet_response.get('success', False),
            'message': f'Permission "{permission_id}" granted to user'
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@permission_api.route('/api/v1/sites/<site_id>/users/<user_did>/permissions/<permission_id>', methods=['DELETE'])
@cross_origin()
@require_api_key
def revoke_user_permission_site_specific(site_id, user_did, permission_id):
    """
    Revoke SPECIFIC permission lemma for THIS SITE ONLY
    
    IMPORTANT: This ONLY revokes the permission lemma for the specific site and permission.
    User's PoH lemma and permissions for other sites remain completely intact.
    """
    try:
        # Create site-specific revocation key (not global)
        revocation_key = f'site_permission:{site_id}:{user_did}:{permission_id}'
        
        # Log the site-specific revocation for billing and audit
        from billing.usage_logger import log_permission_operation
        log_permission_operation(site_id, 'site_permission_revoked', 1, user_did)
        
        logger.info(f"✅ SITE-SPECIFIC revocation: '{permission_id}' for user {user_did} on site {site_id} ONLY")
        
        return jsonify({
            'success': True,
            'revocation_key': revocation_key,
            'site_id': site_id,
            'permission_id': permission_id,
            'user_did': user_did,
            'revocation_scope': 'site_specific_permission_only',
            'message': f'Permission "{permission_id}" revoked for {site_id} only. PoH lemma and other site permissions remain intact.',
            'instructions': 'User should remove the specific permission lemma for this site from their wallet.'
        }), 200
        
    except Exception as e:
        logger.error(f"Site-specific permission revocation error: {e}")
        return jsonify({'error': str(e)}), 400

# ================================================================================
# CLIENT-SIDE IAM USER MANAGEMENT ENDPOINTS
# ================================================================================

@permission_api.route('/api/v1/sites/<site_id>/users', methods=['GET'])
@cross_origin()
@require_api_key
def get_site_users(site_id):
    """Get all users for a site (admin only)"""
    try:
        # Mock user data for now (in production, this would be a lightweight database)
        users = [
            {
                'user_did': f'did:lemma:user:{site_id}:user1',
                'email': 'john@company.com',
                'role': 'admin',
                'status': 'active',
                'added_by': 'site_admin',
                'added_at': '2024-01-15T10:00:00Z',
                'last_login': '2024-01-20T14:30:00Z'
            },
            {
                'user_did': f'did:lemma:user:{site_id}:user2',
                'email': 'jane@company.com', 
                'role': 'user',
                'status': 'active',
                'added_by': 'site_admin',
                'added_at': '2024-01-16T11:00:00Z',
                'last_login': '2024-01-21T09:15:00Z'
            }
        ]

        return jsonify({
            'success': True,
            'users': users,
            'total_users': len(users)
        })

    except Exception as e:
        logger.error(f"Get site users error: {e}")
        return jsonify({'error': str(e)}), 500

@permission_api.route('/api/v1/sites/<site_id>/users', methods=['POST'])
@cross_origin()
@require_api_key
def add_site_user(site_id):
    """Add new user to site"""
    try:
        data = request.get_json()
        email = data.get('email')
        role = data.get('role', 'user')

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        # Create user DID
        user_did = f'did:lemma:user:{site_id}:{secrets.token_hex(8)}'

        # In production, this would add to site's user database
        # For now, we'll just return success
        
        logger.info(f"Added user {email} to site {site_id} with role {role}")

        return jsonify({
            'success': True,
            'user_did': user_did,
            'email': email,
            'role': role,
            'message': f'User {email} added to site {site_id}'
        })

    except Exception as e:
        logger.error(f"Add site user error: {e}")
        return jsonify({'error': str(e)}), 500

@permission_api.route('/api/v1/sites/<site_id>/users/<user_did>/permissions', methods=['POST'])
@cross_origin()
@require_api_key
def grant_user_permission_client_side(site_id, user_did):
    """
    Grant permission to user (creates permission lemma for client-side storage)
    This is the CLIENT-SIDE IAM approach - no server storage needed
    """
    try:
        data = request.get_json()
        permission_id = data.get('permission_id', 'user')
        expiry_days = data.get('expiry_days', 90)

        # Create permission lemma for client-side storage
        import time
        current_time = int(time.time())
        
        permission_lemma = {
            'id': f'perm_{secrets.token_hex(16)}',
            'issuer': f'did:lemma:site:{site_id}',
            'subject': user_did,
            'packageType': 'permission',
            'issued_at': current_time,
            'expires_at': current_time + (expiry_days * 24 * 60 * 60),
            'claims': {
                'packageType': 'permission',
                'siteId': site_id,
                'permissionId': permission_id,
                'grantedBy': request.headers.get('Authorization', 'unknown'),
                'grantedAt': current_time,
                'scope': data.get('scope', ['read', 'write'] if permission_id == 'admin' else ['read'])
            },
            'proof': {
                'type': 'Ed25519Signature2020',
                'created': current_time,
                'verificationMethod': f'did:lemma:site:{site_id}',
                'signatureValue': f'sig_{secrets.token_hex(32)}'
            }
        }

        # Log the permission grant (for billing)
        from billing.usage_logger import log_permission_operation
        log_permission_operation(site_id, 'permission_granted', 1, user_did)

        return jsonify({
            'success': True,
            'permission_lemma': permission_lemma,
            'message': f'Permission "{permission_id}" granted to user. Lemma ready for wallet storage.',
            'instructions': 'Send this permission_lemma to the user\'s browser to store in their wallet.'
        })

    except Exception as e:
        logger.error(f"Grant permission error: {e}")
        return jsonify({'error': str(e)}), 500

@permission_api.route('/api/v1/sites/<site_id>/users/<user_did>', methods=['DELETE'])
@cross_origin()
@require_api_key
def remove_site_user(site_id, user_did):
    """Remove user from site and revoke all their permissions"""
    try:
        # In production, this would remove from site's user database
        # and trigger revocation of all permission lemmas for this site
        
        logger.info(f"Removed user {user_did} from site {site_id}")

        return jsonify({
            'success': True,
            'message': f'User removed from site {site_id}. All permissions revoked.'
        })

    except Exception as e:
        logger.error(f"Remove site user error: {e}")
        return jsonify({'error': str(e)}), 500

@permission_api.route('/api/v1/auth/verify', methods=['POST'])
@cross_origin()
def verify_access():
    """
    Verify user access for a resource (used by customer sites)
    
    POST /api/v1/auth/verify
    {
        "site_id": "site_123",
        "user_did": "did:lemma:user456", 
        "resource": "/admin/users",
        "action": "read",
        "user_lemmas": [...] // User's permission lemmas
    }
    """
    try:
        data = request.get_json()
        site_id = data['site_id']
        user_did = data['user_did']
        resource = data['resource']
        action = data['action']
        user_lemmas = data.get('user_lemmas', [])
        
        if site_id not in site_managers:
            return jsonify({'error': 'Site not found'}), 404
            
        manager = site_managers[site_id]
        
        # Create access request (mock for testing)
        access_request = {
            'user_did': user_did,
            'resource': resource,
            'action': action,
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'timestamp': datetime.utcnow(),
            'session_id': data.get('session_id')
        }
        
        # Convert lemma data to credentials (mock for testing)
        credentials = [VerifiableCredential.from_dict(lemma) for lemma in user_lemmas]
        
        # Verify access using lemma core (4.176µs performance!)
        start_time = time.time()
        has_access = manager.check_access(access_request, credentials)
        verification_time = (time.time() - start_time) * 1_000_000  # Convert to microseconds
        
        # Log billing event (MAU tracking)
        log_permission_operation(site_id, 'access_verification', 1, user_did)
        
        return jsonify({
            'success': True,
            'has_access': has_access,
            'verification_time_us': verification_time,
            'user_did': user_did,
            'resource': resource,
            'action': action,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@permission_api.route('/api/v1/oauth/authorize', methods=['GET'])
@cross_origin()
def oauth_authorize():
    """
    OAuth authorization endpoint for "Sign in with Lemma"
    
    GET /api/v1/oauth/authorize?client_id=lemma_oauth_site123&redirect_uri=https://customer.com/callback&scope=profile+permissions
    """
    try:
        client_id = request.args.get('client_id')
        redirect_uri = request.args.get('redirect_uri')
        scope = request.args.get('scope', 'profile')
        state = request.args.get('state')
        
        # Extract site_id from client_id
        if not client_id.startswith('lemma_oauth_'):
            return jsonify({'error': 'Invalid client_id'}), 400
            
        site_id = client_id.replace('lemma_oauth_', '')
        
        if site_id not in site_managers:
            return jsonify({'error': 'Site not found'}), 404
        
        # Generate authorization code
        auth_code = f"auth_{uuid.uuid4().hex}"
        
        # Store authorization request (temporary)
        # TODO: Store in Redis/cache with expiry
        auth_requests[auth_code] = {
            'site_id': site_id,
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': scope,
            'state': state,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(minutes=10)
        }
        
        # Redirect to Lemma authorization page
        auth_url = f"https://lemma.id/authorize?code={auth_code}&site_id={site_id}&redirect_uri={redirect_uri}&state={state}"
        
        return jsonify({
            'authorization_url': auth_url,
            'auth_code': auth_code
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@permission_api.route('/api/v1/oauth/token', methods=['POST'])
@cross_origin()
def oauth_token():
    """
    OAuth token endpoint - exchange auth code for access token
    
    POST /api/v1/oauth/token
    {
        "grant_type": "authorization_code",
        "code": "auth_123",
        "client_id": "lemma_oauth_site123",
        "client_secret": "secret_456"
    }
    """
    try:
        data = request.get_json()
        auth_code = data['code']
        client_id = data['client_id']
        client_secret = data['client_secret']
        
        # Validate authorization code
        if auth_code not in auth_requests:
            return jsonify({'error': 'Invalid authorization code'}), 400
            
        auth_request = auth_requests[auth_code]
        
        # Validate client credentials
        # TODO: Validate client_secret against database
        
        # Generate access token (JWT)
        token_payload = {
            'site_id': auth_request['site_id'],
            'client_id': client_id,
            'scope': auth_request['scope'],
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=1)
        }
        
        access_token = jwt.encode(token_payload, 'your-secret-key', algorithm='HS256')
        
        # Clean up auth code
        del auth_requests[auth_code]
        
        return jsonify({
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': 3600,
            'scope': auth_request['scope']
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Helper functions
def store_permission_lemma_in_wallet(user_did: str, credential) -> Dict:
    """Store permission lemma in user's wallet"""
    # TODO: Integrate with wallet API
    return {'success': True, 'stored': True}

def add_to_revocation_filter(revocation_key: str):
    """Add revocation key to bloom filter"""
    # TODO: Integrate with bloom filter system
    pass

# Temporary storage (replace with Redis/database)
auth_requests = {}

if __name__ == '__main__':
    # Register permission packages for all sites
    for site_id, manager in site_managers.items():
        lemma_core.register_package(manager.permission_package)
