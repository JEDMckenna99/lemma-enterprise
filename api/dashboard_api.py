"""
Dashboard API for Customer and Admin Management
"""

import os
import logging
import secrets
import time
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, render_template
from flask_cors import cross_origin
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Create dashboard blueprint
dashboard_bp = Blueprint('dashboard', __name__)

# ================================================================================
# CUSTOMER DASHBOARD ENDPOINTS
# ================================================================================

@dashboard_bp.route('/api/customer/profile', methods=['GET'])
@cross_origin()
def get_customer_profile():
    """Get customer profile information"""
    try:
        customer_id = session.get('customer_id')
        if not customer_id:
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401

        # Get customer from database
        from .customer_accounts import customer_manager
        customer = customer_manager.get_customer_by_id(customer_id)
        
        if not customer:
            return jsonify({
                'success': False,
                'error': 'Customer not found'
            }), 404

        return jsonify({
            'success': True,
            'customer': {
                'customer_id': customer.customer_id,
                'email': customer.email,
                'name': customer.name,
                'company': customer.company,
                'role': customer.role,
                'created_at': customer.created_at.isoformat() if customer.created_at else None,
                'last_login': customer.last_login.isoformat() if customer.last_login else None,
                'login_count': customer.login_count,
                'status': customer.status,
                'subscription_status': customer.subscription_status
            }
        })

    except Exception as e:
        logger.error(f"Get customer profile error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get profile'
        }), 500

# Duplicate endpoint removed - handled by customer_accounts.py
# @dashboard_bp.route('/api/customer/api-keys', methods=['GET'])
# @cross_origin()
def get_customer_api_keys_disabled():
    """Get customer API keys"""
    try:
        customer_id = session.get('customer_id')
        if not customer_id:
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401

        from .customer_accounts import customer_manager
        customer = customer_manager.get_customer_by_id(customer_id)
        
        if not customer:
            return jsonify({
                'success': False,
                'error': 'Customer not found'
            }), 404

        return jsonify({
            'success': True,
            'api_keys': customer.api_keys or []
        })

    except Exception as e:
        logger.error(f"Get API keys error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get API keys'
        }), 500

# Duplicate endpoint removed - handled by customer_accounts.py
# @dashboard_bp.route('/api/customer/api-keys', methods=['POST'])
@cross_origin()
def create_api_key():
    """Create new API key for customer"""
    try:
        customer_id = session.get('customer_id')
        if not customer_id:
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401

        data = request.get_json() or {}
        key_name = data.get('name', 'API Key')

        from .customer_accounts import customer_manager
        result = customer_manager.generate_api_key(customer_id, key_name)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Create API key error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to create API key'
        }), 500

# Duplicate endpoint removed - handled by customer_accounts.py  
# @dashboard_bp.route('/api/customer/api-keys/<key_id>', methods=['DELETE'])
@cross_origin()
def revoke_api_key(key_id):
    """Revoke customer API key"""
    try:
        customer_id = session.get('customer_id')
        if not customer_id:
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401

        from .customer_accounts import customer_manager
        result = customer_manager.revoke_api_key(customer_id, key_id)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Revoke API key error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to revoke API key'
        }), 500

@dashboard_bp.route('/api/customer/usage', methods=['GET'])
@cross_origin()
def get_customer_usage():
    """Get customer usage statistics"""
    try:
        customer_id = session.get('customer_id')
        if not customer_id:
            return jsonify({
                'success': False,
                'error': 'Not authenticated'
            }), 401

        # Mock usage data for now
        current_month = datetime.now().strftime('%Y-%m')
        
        usage_data = {
            'current_month': current_month,
            'federated_id_network': {
                'monthly_active_users': 1247,
                'new_verifications': 156,
                'total_verifications': 45623,
                'cost': 62.35  # $0.05 * 1247 MAU
            },
            'iam_system': {
                'monthly_active_users': 856,
                'permission_grants': 234,
                'access_verifications': 12890,
                'cost': 128.40  # $0.15 * 856 MAU
            },
            'total_cost': 190.75,
            'next_billing_date': (datetime.now() + timedelta(days=7)).isoformat()
        }

        return jsonify({
            'success': True,
            'usage': usage_data
        })

    except Exception as e:
        logger.error(f"Get usage error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get usage data'
        }), 500

# ================================================================================
# ADMIN DASHBOARD ENDPOINTS
# ================================================================================

@dashboard_bp.route('/api/admin/platform-stats', methods=['GET'])
@cross_origin()
def get_platform_stats():
    """Get platform-wide statistics (admin only)"""
    try:
        # Check admin permission lemma (in production, verify from wallet)
        user_role = session.get('user_role', 'customer')
        if user_role != 'admin':
            return jsonify({
                'success': False,
                'error': 'Admin access required'
            }), 403

        # Mock platform statistics
        stats = {
            'total_customers': 1247,
            'active_sites': 89,
            'total_verifications_today': 15623,
            'revenue_this_month': 15420.50,
            'federated_network': {
                'total_poh_lemmas': 45623,
                'cross_site_verifications': 234567,
                'network_nodes': 12
            },
            'iam_system': {
                'total_permission_lemmas': 12890,
                'active_iam_sites': 34,
                'permission_verifications': 89456
            },
            'performance': {
                'avg_verification_time_us': 2.38,
                'uptime_percentage': 99.97,
                'cache_hit_rate': 96.2
            }
        }

        return jsonify({
            'success': True,
            'stats': stats
        })

    except Exception as e:
        logger.error(f"Get platform stats error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get platform stats'
        }), 500

@dashboard_bp.route('/api/admin/customers', methods=['GET'])
@cross_origin()
def get_all_customers():
    """Get all customers (admin only)"""
    try:
        user_role = session.get('user_role', 'customer')
        if user_role != 'admin':
            return jsonify({
                'success': False,
                'error': 'Admin access required'
            }), 403

        from .customer_accounts import customer_manager
        customers = customer_manager.get_all_customers()

        return jsonify({
            'success': True,
            'customers': customers
        })

    except Exception as e:
        logger.error(f"Get customers error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get customers'
        }), 500

@dashboard_bp.route('/api/admin/sites', methods=['GET'])
@cross_origin()
def get_all_sites():
    """Get all registered sites (admin only)"""
    try:
        user_role = session.get('user_role', 'customer')
        if user_role != 'admin':
            return jsonify({
                'success': False,
                'error': 'Admin access required'
            }), 403

        # Mock site data
        sites = [
            {
                'site_id': 'site_abc123',
                'site_domain': 'example.com',
                'company_name': 'Example Corp',
                'service_type': 'both',
                'plan': 'professional',
                'status': 'active',
                'monthly_active_users': 1247,
                'created_at': '2024-01-15T10:00:00Z'
            },
            {
                'site_id': 'site_def456',
                'site_domain': 'testsite.org',
                'company_name': 'Test Organization',
                'service_type': 'iam',
                'plan': 'starter',
                'status': 'active',
                'monthly_active_users': 456,
                'created_at': '2024-02-01T14:30:00Z'
            }
        ]

        return jsonify({
            'success': True,
            'sites': sites
        })

    except Exception as e:
        logger.error(f"Get sites error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get sites'
        }), 500

@dashboard_bp.route('/api/admin/issue-admin-lemma', methods=['POST'])
@cross_origin()
def issue_admin_lemma_endpoint():
    """Issue admin permission lemma (admin only)"""
    try:
        # Verify admin credentials
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Basic '):
            return jsonify({
                'success': False,
                'error': 'Basic authentication required'
            }), 401

        import base64
        try:
            credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
            username, password = credentials.split(':', 1)
        except:
            return jsonify({
                'success': False,
                'error': 'Invalid authentication format'
            }), 401

        # Check admin credentials
        admin_user = os.getenv('LEMMA_ADMIN_USER', 'admin')
        admin_pass = os.getenv('LEMMA_ADMIN_PASS', 'defaultpass')

        if username != admin_user or password != admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin credentials'
            }), 401

        # Create admin permission lemma
        admin_did = f"did:lemma:admin:{username}"
        current_time = int(time.time())
        
        permission_lemma_data = {
            'id': f"admin_perm_{secrets.token_hex(16)}",
            'issuer': 'did:lemma:platform:lemma.id',
            'subject': admin_did,
            'packageType': 'permission',
            'issued_at': current_time,
            'expires_at': current_time + (365 * 24 * 60 * 60),  # 1 year for admin
            'claims': {
                'packageType': 'permission',
                'siteId': 'lemma.id',
                'permissionId': 'admin_access',
                'accountType': 'admin',
                'username': username,
                'networkShared': False,
                'grantedBy': 'did:lemma:platform:lemma.id',
                'grantedAt': current_time,
                'scope': ['platform_admin', 'customer_management', 'site_management', 'billing_access']
            },
            'proof': {
                'type': 'Ed25519Signature2020',
                'created': current_time,
                'verificationMethod': 'did:lemma:platform:lemma.id',
                'signatureValue': f"admin_sig_{secrets.token_hex(32)}"
            }
        }

        return jsonify({
            'success': True,
            'admin_did': admin_did,
            'permission_lemma': permission_lemma_data,
            'message': 'Admin permission lemma issued successfully'
        })

    except Exception as e:
        logger.error(f"Admin lemma issuance error: {e}")
        return jsonify({
            'success': False,
            'error': 'Admin lemma issuance failed'
        }), 500
