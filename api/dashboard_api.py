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
        
        # Get admin DID - prefer wallet-derived PPID if provided
        # This allows credentials to be issued to the wallet's actual PPID
        admin_did = request.headers.get('X-Lemma-PPID')
        
        if not admin_did or not admin_did.startswith('did:lemma:ppid_'):
            # Check request body for PPID
            data = request.get_json() or {}
            admin_did = data.get('user_ppid')
        
        if not admin_did or not admin_did.startswith('did:lemma:ppid_'):
            # Fall back to username-based derivation (legacy)
            logger.warning(f"No wallet PPID provided, falling back to username-derived DID")
            admin_did = derive_ppid_did(username, site_domain)
        else:
            logger.info(f"Using wallet-derived PPID: {admin_did[:50]}...")
        
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


@dashboard_bp.route('/api/admin/issue-admin-credential', methods=['POST'])
@cross_origin()
def issue_admin_credential():
    """
    Issue admin credential following the standard wallet-based pattern.
    
    This is the CORRECT flow matching developer self-issue:
    1. User has wallet (unlocked via passkey authentication)
    2. Client derives PPID: wallet.derivePPID('lemma.id')
    3. Client calls this endpoint with PPID + API key
    4. Server verifies API key authorization
    5. Server issues admin credential to wallet PPID
    6. Credential stored in wallet
    
    POST /api/admin/issue-admin-credential
    Headers:
        X-Lemma-PPID: did:lemma:ppid_xxx (from wallet.derivePPID('lemma.id'))
        X-API-Key: lemma_xxx (platform API key for authorization)
        OR Authorization: Bearer lemma_xxx
    Body:
        {
            "email": "jedmckenna@lemma.id",  // For auditing
            "permission_level": "admin_access"  // Optional, defaults to admin_access
        }
    
    Returns:
        - permission_lemma: Signed credential bound to wallet PPID
        - user_did: The PPID the credential was issued to
        - issuer_did: Platform issuer DID
    """
    try:
        # 1. REQUIRE wallet-derived PPID
        ppid = request.headers.get('X-Lemma-PPID')
        
        if not ppid or not ppid.startswith('did:lemma:ppid_'):
            return jsonify({
                'success': False,
                'error': 'X-Lemma-PPID header required',
                'message': 'Derive PPID from unlocked wallet: await wallet.derivePPID("lemma.id")'
            }), 400
        
        # 2. REQUIRE API key authorization (proves they have platform access)
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                api_key = auth_header.replace('Bearer ', '').strip()
        
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key required for authorization',
                'message': 'Provide X-API-Key header or Authorization: Bearer <key>'
            }), 401
        
        # 3. Verify API key is valid for platform admin
        from api.customer_accounts import customer_manager
        
        # Check platform API key first
        platform_key = os.getenv('LEMMA_API_KEY', os.getenv('LEMMA_PLATFORM_API_KEY'))
        is_platform_admin = platform_key and api_key == platform_key
        
        if not is_platform_admin:
            # Check if customer API key with admin role
            customer = customer_manager.get_customer_by_api_key(api_key)
            if not customer or customer.role != 'admin':
                return jsonify({
                    'success': False,
                    'error': 'Not authorized for admin credential issuance',
                    'message': 'API key must be platform admin key or admin-role customer key'
                }), 403
        
        data = request.get_json() or {}
        email = data.get('email', 'admin@lemma.id')
        permission_level = data.get('permission_level', 'admin_access')
        
        # 4. Issue credential to wallet PPID
        from api.real_iam_manager import get_or_create_site_manager
        import time
        
        site_id = 'lemma_platform'
        site_domain = 'lemma.id'
        
        manager = get_or_create_site_manager(site_id, site_domain)
        if not manager:
            return jsonify({
                'success': False,
                'error': 'Failed to initialize platform IAM manager'
            }), 500
        
        # Ensure admin permission type exists
        if permission_level not in manager.permissions:
            manager.add_permission({
                'permission_id': permission_level,
                'display_name': 'Platform Administrator',
                'scope': ['platform_admin', 'customer_management', 'site_management', 'billing_access'],
                'conditions': [],
                'priority': 100
            })
        
        start_time = time.perf_counter()
        
        # Issue permission lemma to the wallet's PPID
        permission_lemma = manager.issue_permission_lemma(
            ppid,  # Wallet-derived PPID - the credential subject
            permission_level,
            expiry_days=365,
            custom_claims={
                'siteId': 'lemma.id',
                'siteDomain': 'lemma.id',
                'accountType': 'admin',
                'permissionId': permission_level,
                'email': email,
                'networkShared': False,
                'scope': ['platform_admin', 'customer_management', 'site_management', 'billing_access'],
                'issuedVia': 'wallet_authenticated_issuance'
            }
        )
        
        issue_time_us = (time.perf_counter() - start_time) * 1_000_000
        
        # Add W3C type field for credential classification
        permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
        permission_lemma['packageType'] = 'permission'
        
        if 'credentialSubject' in permission_lemma:
            permission_lemma['credentialSubject']['packageType'] = 'permission'
            permission_lemma['credentialSubject']['siteId'] = 'lemma.id'
            permission_lemma['credentialSubject']['siteDomain'] = 'lemma.id'
        if 'claims' in permission_lemma:
            permission_lemma['claims']['packageType'] = 'permission'
            permission_lemma['claims']['siteId'] = 'lemma.id'
            permission_lemma['claims']['siteDomain'] = 'lemma.id'
        
        logger.info(f"✅ Issued admin credential to wallet PPID")
        logger.info(f"   PPID: {ppid[:50]}...")
        logger.info(f"   Email: {email}")
        logger.info(f"   Issue time: {issue_time_us:.2f}µs")
        
        return jsonify({
            'success': True,
            'user_did': ppid,
            'issuer_did': manager.issuer_did,
            'permission_lemma': permission_lemma,
            'credential_id': permission_lemma.get('id'),
            'issue_time_us': issue_time_us,
            'message': 'Admin credential issued to your wallet PPID. Store in your wallet.'
        })
        
    except Exception as e:
        logger.error(f"Admin credential issuance error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Legacy endpoint - kept for backwards compatibility
@dashboard_bp.route('/api/admin/reissue-with-ppid', methods=['POST'])
@cross_origin()
def reissue_admin_with_ppid():
    """Legacy endpoint - redirects to new issue-admin-credential"""
    return issue_admin_credential()


# ================================================================================
# ADMIN USER MANAGEMENT ENDPOINTS
# ================================================================================

@dashboard_bp.route('/api/admin/users', methods=['GET'])
@cross_origin()
@require_site_admin
def get_admin_users():
    """Get all platform users (admin only)"""
    try:
        database_url = os.environ.get('DATABASE_URL')
        users = []
        
        if database_url:
            import psycopg2
            conn = psycopg2.connect(database_url)
            cur = conn.cursor()
            
            cur.execute("""
                SELECT DISTINCT admin_email, site_domain, created_at, status
                FROM registered_sites 
                WHERE admin_email IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 100
            """)
            
            for row in cur.fetchall():
                users.append({
                    'email': row[0],
                    'site': row[1],
                    'created_at': row[2].isoformat() if row[2] else None,
                    'status': row[3] or 'active',
                    'type': 'developer'
                })
            
            cur.close()
            conn.close()
        else:
            users = [
                {'email': 'dev@example.com', 'site': 'example.com', 'created_at': '2025-01-15T10:00:00Z', 'status': 'active', 'type': 'developer'},
            ]
        
        return jsonify({
            'success': True,
            'users': users,
            'total': len(users)
        })
        
    except Exception as e:
        logger.error(f"Get admin users error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/api/admin/user-stats', methods=['GET'])
@cross_origin()
@require_site_admin
def get_admin_user_stats():
    """Get user statistics (admin only)"""
    try:
        database_url = os.environ.get('DATABASE_URL')
        
        if database_url:
            import psycopg2
            conn = psycopg2.connect(database_url)
            cur = conn.cursor()
            
            # Query customers table
            cur.execute("SELECT COUNT(*) FROM customers WHERE status = 'active' OR status IS NULL")
            total_users = cur.fetchone()[0] or 0
            
            # Count sites from customers.sites JSON column (estimate based on customers with sites)
            cur.execute("SELECT COUNT(*) FROM customers WHERE sites IS NOT NULL AND sites::text != '[]'")
            active_sites = cur.fetchone()[0] or 0
            
            cur.execute("""
                SELECT COUNT(*) FROM customers 
                WHERE created_at > NOW() - INTERVAL '7 days'
            """)
            new_this_week = cur.fetchone()[0] or 0
            
            cur.close()
            conn.close()
            
            stats = {
                'total_users': total_users,
                'active_sites': active_sites,
                'new_this_week': new_this_week,
                'growth_rate': round((new_this_week / max(total_users, 1)) * 100, 1)
            }
        else:
            stats = {
                'total_users': 156,
                'active_sites': 89,
                'new_this_week': 12,
                'growth_rate': 7.7
            }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Get user stats error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/api/admin/recent-activity', methods=['GET'])
@cross_origin()
@require_site_admin
def get_admin_recent_activity():
    """Get recent platform activity (admin only)"""
    try:
        database_url = os.environ.get('DATABASE_URL')
        activities = []
        
        if database_url:
            import psycopg2
            conn = psycopg2.connect(database_url)
            cur = conn.cursor()
            
            # Get recent customer registrations
            cur.execute("""
                SELECT email, name, customer_did, created_at
                FROM customers 
                WHERE created_at IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 10
            """)
            
            for row in cur.fetchall():
                activities.append({
                    'user': row[0] or row[2][:30] or 'Unknown',
                    'action': 'Registered account',
                    'target': row[1] or 'Wallet User',
                    'timestamp': row[3].isoformat() if row[3] else None,
                    'type': 'account_registered'
                })
            
            # Also get recent agent credentials issued
            cur.execute("""
                SELECT authorized_by_email, agent_name, issued_at
                FROM agent_credentials
                WHERE issued_at IS NOT NULL
                ORDER BY issued_at DESC
                LIMIT 5
            """)
            
            for row in cur.fetchall():
                activities.append({
                    'user': row[0] or 'Unknown',
                    'action': 'Issued agent credential',
                    'target': row[1],
                    'timestamp': row[2].isoformat() if row[2] else None,
                    'type': 'agent_credential_issued'
                })
            
            cur.close()
            conn.close()
            
            # Sort all activities by timestamp
            activities.sort(key=lambda x: x['timestamp'] or '', reverse=True)
            activities = activities[:10]  # Keep only 10 most recent
        else:
            from datetime import datetime
            now = datetime.utcnow()
            activities = [
                {'user': 'dev@example.com', 'action': 'Registered account', 'target': 'Example Corp', 'timestamp': now.isoformat(), 'type': 'account_registered'},
            ]
        
        return jsonify({
            'success': True,
            'activities': activities
        })
        
    except Exception as e:
        logger.error(f"Get recent activity error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@dashboard_bp.route('/api/health/detailed', methods=['GET'])
@cross_origin()
def get_detailed_health():
    """Get detailed system health status for admin dashboard"""
    try:
        services = []
        
        # API Server (always healthy if this endpoint responds)
        services.append({
            'name': 'API Server',
            'status': 'healthy',
            'message': 'Operational'
        })
        
        # Database
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            try:
                import psycopg2
                conn = psycopg2.connect(database_url, connect_timeout=5)
                conn.close()
                services.append({
                    'name': 'Database',
                    'status': 'healthy',
                    'message': 'Connected'
                })
            except Exception as e:
                services.append({
                    'name': 'Database',
                    'status': 'unhealthy',
                    'message': str(e)[:50]
                })
        else:
            services.append({
                'name': 'Database',
                'status': 'warning',
                'message': 'Not configured'
            })
        
        # Redis (optional)
        redis_url = os.environ.get('REDIS_URL')
        if redis_url:
            try:
                import redis
                r = redis.from_url(redis_url, socket_timeout=5)
                r.ping()
                services.append({
                    'name': 'Redis Cache',
                    'status': 'healthy',
                    'message': 'Connected'
                })
            except Exception as e:
                services.append({
                    'name': 'Redis Cache',
                    'status': 'unhealthy', 
                    'message': str(e)[:50]
                })
        else:
            services.append({
                'name': 'Redis Cache',
                'status': 'warning',
                'message': 'Not configured'
            })
        
        # Crypto Engine
        try:
            from lemma_crypto import PyMinimalIssuer
            issuer = PyMinimalIssuer()
            services.append({
                'name': 'Crypto Engine',
                'status': 'healthy',
                'message': 'Ed25519 ready'
            })
        except Exception as e:
            services.append({
                'name': 'Crypto Engine',
                'status': 'unhealthy',
                'message': str(e)[:50]
            })
        
        # Overall status
        unhealthy_count = sum(1 for s in services if s['status'] == 'unhealthy')
        overall = 'healthy' if unhealthy_count == 0 else 'degraded' if unhealthy_count < 3 else 'unhealthy'
        
        return jsonify({
            'success': True,
            'status': overall,
            'services': services,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f'Get detailed health error: {e}')
        return jsonify({
            'success': False,
            'status': 'error',
            'error': str(e)
        }), 500