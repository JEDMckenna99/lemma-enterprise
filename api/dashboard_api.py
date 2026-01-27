"""
Dashboard API for Customer and Admin Management

Authentication uses lemma-based credentials:
- Admin endpoints: Require admin permission lemma (via @require_site_admin)
- Customer endpoints: Require customer permission lemma (via @require_customer_auth)
- API key fallback for programmatic access
"""

import os
import logging
import secrets
import time
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, g
from flask_cors import cross_origin
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Create dashboard blueprint
dashboard_bp = Blueprint('dashboard', __name__)

# Import usage tracking
from .usage_tracking import get_usage_summary, get_monthly_active_users, track_active_user

# Import auth decorators
from auth.decorators import require_site_admin, require_api_key, require_wallet_ppid, require_customer_or_admin

# ================================================================================
# CUSTOMER DASHBOARD ENDPOINTS
# ================================================================================

@dashboard_bp.route('/api/customer/profile', methods=['GET'])
@cross_origin()
@require_wallet_ppid
def get_customer_profile():
    """Get customer profile information
    
    Requires: Authenticated wallet (X-Lemma-PPID header) or API key
    """
    try:
        # Auth verified by @require_wallet_ppid decorator
        # g.ppid contains the user's PPID
        
        # Get customer from database using PPID
        from .customer_accounts import customer_manager
        customer = customer_manager.get_customer_by_ppid(g.ppid) if hasattr(g, 'ppid') and g.ppid else None
        
        # Fallback to API key lookup
        if not customer and hasattr(g, 'api_key'):
            customer = customer_manager.get_customer_by_api_key(g.api_key)
        
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


@dashboard_bp.route('/api/customer/usage', methods=['GET'])
@cross_origin()
@require_customer_or_admin
def get_customer_usage():
    """
    Get usage statistics and billing information for customer's site
    
    Requires: Authenticated wallet (PPID), admin credential, or API key
    Returns: MAU count, current tier, pricing, and historical data
    """
    try:
        # Get site_id based on auth type
        site_id = request.args.get('site_id')
        
        if not site_id:
            # Try to get from customer account using PPID
            if hasattr(g, 'ppid') and g.ppid:
                from .customer_accounts import customer_manager
                customer = customer_manager.get_customer_by_ppid(g.ppid)
                if customer:
                    site_id = customer.customer_id
            
            # Default fallback
            if not site_id:
                site_id = 'lemma_platform'
        
        # Get comprehensive usage summary
        usage = get_usage_summary(site_id)
        
        return jsonify({
            'success': True,
            'usage': usage
        })
        
    except Exception as e:
        logger.error(f"Get customer usage error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Legacy session-based endpoints removed - now handled by customer_accounts.py
# with proper credential-based authentication

# ================================================================================
# ADMIN DASHBOARD ENDPOINTS
# ================================================================================

@dashboard_bp.route('/api/admin/platform-stats', methods=['GET'])
@cross_origin()
@require_site_admin
def get_platform_stats():
    """Get platform-wide statistics (admin only)
    
    Requires: Admin permission lemma via X-Credential-ID + X-Permission-ID headers
    Or: Valid API key via X-API-Key header
    """
    try:
        # Admin auth verified by @require_site_admin decorator
        # g.is_admin, g.admin_email, g.permission_id are set by decorator

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
@require_site_admin
def get_all_customers():
    """Get all customers (admin only)
    
    Requires: Admin permission lemma or API key
    """
    try:
        # Admin auth verified by @require_site_admin decorator

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
@require_site_admin
def get_all_sites():
    """Get all registered sites (admin only)
    
    Requires: Admin permission lemma or API key
    """
    try:
        # Admin auth verified by @require_site_admin decorator

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
    """Issue admin permission lemma - BOOTSTRAP ENDPOINT
    
    This is the initial bootstrap endpoint for creating the first admin lemma.
    Uses Basic Auth with LEMMA_ADMIN_USER/LEMMA_ADMIN_PASS env vars.
    
    Once you have an admin lemma, use @require_site_admin protected endpoints.
    
    Request: Basic Auth with admin credentials
    Response: Admin permission lemma to store in wallet
    """
    try:
        # Bootstrap auth: Basic Auth with env var credentials
        # This is intentionally simple - it's only used to create the FIRST admin lemma
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Basic '):
            return jsonify({
                'success': False,
                'error': 'Basic authentication required (Bootstrap endpoint)'
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

        # Check admin credentials from environment
        admin_user = os.getenv('LEMMA_ADMIN_USER')
        admin_pass = os.getenv('LEMMA_ADMIN_PASS')
        
        if not admin_user or not admin_pass:
            return jsonify({
                'success': False,
                'error': 'Admin credentials not configured (LEMMA_ADMIN_USER/LEMMA_ADMIN_PASS)'
            }), 500

        if username != admin_user or password != admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin credentials'
            }), 401

        # Create admin permission lemma using REAL Ed25519 signing
        from api.real_iam_manager import get_or_create_site_manager
        from api.ppid import derive_ppid_did
        
        site_id = 'lemma_platform'
        site_domain = 'lemma.id'
        
        # Get or create the platform IAM manager (with Ed25519 keypair)
        manager = get_or_create_site_manager(site_id, site_domain)
        if not manager:
            return jsonify({
                'success': False,
                'error': 'Failed to initialize platform IAM manager'
            }), 500
        
        # Ensure admin permission type exists
        if 'admin_access' not in manager.permissions:
            manager.add_permission({
                'permission_id': 'admin_access',
                'display_name': 'Platform Administrator',
                'scope': ['platform_admin', 'customer_management', 'site_management', 'billing_access'],
                'conditions': [],
                'priority': 100
            })
        
        # Derive admin DID from username
        admin_did = derive_ppid_did(username, site_domain)
        
        # Issue permission lemma with REAL Ed25519 signature
        permission_lemma = manager.issue_permission_lemma(
            admin_did,
            'admin_access',
            expiry_days=365,  # 1 year for admin
            custom_claims={
                'siteId': 'lemma.id',
                'accountType': 'admin',
                'permissionId': 'admin_access',
                'username': username,
                'networkShared': False,
                'scope': ['platform_admin', 'customer_management', 'site_management', 'billing_access']
            }
        )
        
        # Add W3C type field for credential classification
        permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
        permission_lemma['packageType'] = 'permission'
        
        # Ensure claims has packageType for wallet filtering
        if 'credentialSubject' in permission_lemma:
            permission_lemma['credentialSubject']['packageType'] = 'permission'
        if 'claims' in permission_lemma:
            permission_lemma['claims']['packageType'] = 'permission'

        return jsonify({
            'success': True,
            'admin_did': admin_did,
            'issuer_did': manager.issuer_did,
            'permission_lemma': permission_lemma,
            'message': 'Admin permission lemma issued with Ed25519 signature. Store in your wallet.'
        })

    except Exception as e:
        logger.error(f"Admin lemma issuance error: {e}")
        return jsonify({
            'success': False,
            'error': 'Admin lemma issuance failed'
        }), 500
