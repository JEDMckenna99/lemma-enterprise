"""
Admin API Blueprint for Lemma Platform
=====================================

Provides administrative functionality for managing the Lemma platform including:
- User management (CRUD operations on FIL users)
- Business analytics and metrics
- Network monitoring and health
- System configuration
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from auth.decorators import require_admin, require_authenticated, get_current_user
from api.customer_accounts import customer_manager

logger = logging.getLogger(__name__)

# Create admin blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ============================================================================
# ADMIN DASHBOARD ROUTES
# ============================================================================

@admin_bp.route('/')
@require_admin()
def admin_dashboard():
    """Main admin dashboard"""
    try:
        # Get system overview metrics
        metrics = get_system_metrics()
        
        return render_template('admin/dashboard.html', 
                             metrics=metrics,
                             user_info=get_current_user())
    except Exception as e:
        logger.error(f"Admin dashboard error: {e}")
        return redirect(url_for('index'))

@admin_bp.route('/users')
@require_admin()
def admin_users():
    """User management interface"""
    try:
        # Get all users with pagination
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '')
        
        users = get_all_users(page=page, search=search)
        
        return render_template('admin/users.html',
                             users=users,
                             user_info=get_current_user())
    except Exception as e:
        logger.error(f"Admin users page error: {e}")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/analytics')
@require_admin()
def admin_analytics():
    """Business analytics dashboard"""
    try:
        analytics_data = get_business_analytics()
        
        return render_template('admin/analytics.html',
                             analytics=analytics_data,
                             user_info=get_current_user())
    except Exception as e:
        logger.error(f"Admin analytics page error: {e}")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/network')
@require_admin()
def admin_network():
    """Network monitoring dashboard"""
    try:
        network_data = get_network_status()
        
        return render_template('admin/network.html',
                             network=network_data,
                             user_info=get_current_user())
    except Exception as e:
        logger.error(f"Admin network page error: {e}")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/revocation')
@require_admin()
def admin_revocation():
    """Revocation management dashboard"""
    try:
        revocation_data = get_revocation_status()
        
        return render_template('admin/revocation.html',
                             revocation=revocation_data,
                             user_info=get_current_user())
    except Exception as e:
        logger.error(f"Admin revocation page error: {e}")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/system')
@require_admin()
def admin_system():
    """System configuration dashboard"""
    try:
        system_data = get_system_config()
        
        return render_template('admin/system.html',
                             system=system_data,
                             user_info=get_current_user())
    except Exception as e:
        logger.error(f"Admin system page error: {e}")
        return redirect(url_for('admin.admin_dashboard'))

# ============================================================================
# ADMIN API ENDPOINTS
# ============================================================================

@admin_bp.route('/api/users', methods=['GET'])
@require_admin(redirect_to_login=False)
def api_get_users():
    """Get users with filtering and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        role = request.args.get('role', '')
        
        users_data = get_all_users(
            page=page, 
            per_page=per_page, 
            search=search,
            status_filter=status,
            role_filter=role
        )
        
        return jsonify({
            'success': True,
            'users': users_data['users'],
            'pagination': users_data['pagination'],
            'total_count': users_data['total_count']
        })
        
    except Exception as e:
        logger.error(f"API get users error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve users'
        }), 500

@admin_bp.route('/api/users/<customer_id>', methods=['GET'])
@require_admin(redirect_to_login=False)
def api_get_user_details(customer_id):
    """Get detailed user information"""
    try:
        customer = customer_manager.get_customer(customer_id)
        if not customer:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Get additional user metrics
        user_metrics = get_user_metrics(customer_id)
        
        from dataclasses import asdict
        user_data = asdict(customer)
        user_data['metrics'] = user_metrics
        
        return jsonify({
            'success': True,
            'user': user_data
        })
        
    except Exception as e:
        logger.error(f"API get user details error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve user details'
        }), 500

@admin_bp.route('/api/users/<customer_id>', methods=['PUT'])
@require_admin(redirect_to_login=False)
def api_update_user(customer_id):
    """Update user account"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        customer = customer_manager.get_customer(customer_id)
        if not customer:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Update allowed fields
        if 'status' in data:
            customer.status = data['status']
        if 'role' in data:
            customer.role = data['role']
        if 'permissions' in data:
            customer.permissions = data['permissions']
        
        # Log admin action
        log_admin_action('user_updated', {
            'target_user': customer_id,
            'changes': data
        })
        
        return jsonify({
            'success': True,
            'message': 'User updated successfully'
        })
        
    except Exception as e:
        logger.error(f"API update user error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to update user'
        }), 500

@admin_bp.route('/api/analytics', methods=['GET'])
@require_admin(redirect_to_login=False)
def api_get_analytics():
    """Get business analytics data"""
    try:
        timeframe = request.args.get('timeframe', '30d')  # 7d, 30d, 90d, 1y
        analytics_data = get_business_analytics(timeframe=timeframe)
        
        return jsonify({
            'success': True,
            'analytics': analytics_data
        })
        
    except Exception as e:
        logger.error(f"API get analytics error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve analytics'
        }), 500

@admin_bp.route('/api/network', methods=['GET'])
@require_admin(redirect_to_login=False)
def api_get_network_status():
    """Get network monitoring data"""
    try:
        network_data = get_network_status()
        
        return jsonify({
            'success': True,
            'network': network_data
        })
        
    except Exception as e:
        logger.error(f"API get network status error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve network status'
        }), 500

# ============================================================================
# ADMIN HELPER FUNCTIONS
# ============================================================================

def get_system_metrics() -> Dict[str, Any]:
    """Get system overview metrics"""
    try:
        total_users = len(customer_manager.customers)
        active_users = len([c for c in customer_manager.customers.values() if c.status == 'active'])
        admin_users = len([c for c in customer_manager.customers.values() if c.role == 'admin'])
        
        # Calculate revenue (mock data for now)
        total_revenue = sum(
            sum(usage.values()) * 0.10 
            for customer in customer_manager.customers.values() 
            for usage in [customer.monthly_usage]
        )
        
        # Get current month usage
        current_month = datetime.now().strftime('%Y-%m')
        monthly_active_users = sum(
            customer.monthly_usage.get(current_month, 0)
            for customer in customer_manager.customers.values()
        )
        
        return {
            'total_users': total_users,
            'active_users': active_users,
            'admin_users': admin_users,
            'monthly_active_users': monthly_active_users,
            'total_revenue': round(total_revenue, 2),
            'api_keys_total': sum(len(c.api_keys) for c in customer_manager.customers.values()),
            'last_updated': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        return {
            'total_users': 0,
            'active_users': 0,
            'admin_users': 0,
            'monthly_active_users': 0,
            'total_revenue': 0.0,
            'api_keys_total': 0,
            'last_updated': datetime.now().isoformat()
        }

def get_all_users(page: int = 1, per_page: int = 50, search: str = '', 
                  status_filter: str = '', role_filter: str = '') -> Dict[str, Any]:
    """Get all users with filtering and pagination"""
    try:
        all_customers = list(customer_manager.customers.values())
        
        # Apply filters
        if search:
            search_lower = search.lower()
            all_customers = [
                c for c in all_customers 
                if (search_lower in c.email.lower() or 
                    search_lower in c.name.lower() or 
                    search_lower in c.company.lower())
            ]
        
        if status_filter:
            all_customers = [c for c in all_customers if c.status == status_filter]
        
        if role_filter:
            all_customers = [c for c in all_customers if c.role == role_filter]
        
        # Sort by creation date (newest first)
        all_customers.sort(key=lambda x: x.created_at, reverse=True)
        
        # Pagination
        total_count = len(all_customers)
        start = (page - 1) * per_page
        end = start + per_page
        customers_page = all_customers[start:end]
        
        # Convert to dict format
        from dataclasses import asdict
        users_data = []
        for customer in customers_page:
            user_data = asdict(customer)
            # Add computed fields
            user_data['total_usage'] = sum(customer.monthly_usage.values())
            user_data['active_api_keys'] = len([k for k in customer.api_keys if k['status'] == 'active'])
            users_data.append(user_data)
        
        return {
            'users': users_data,
            'total_count': total_count,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_pages': (total_count + per_page - 1) // per_page,
                'has_next': end < total_count,
                'has_prev': page > 1
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return {
            'users': [],
            'total_count': 0,
            'pagination': {
                'page': 1,
                'per_page': per_page,
                'total_pages': 0,
                'has_next': False,
                'has_prev': False
            }
        }

def get_user_metrics(customer_id: str) -> Dict[str, Any]:
    """Get detailed metrics for a specific user"""
    try:
        customer = customer_manager.get_customer(customer_id)
        if not customer:
            return {}
        
        # Calculate usage metrics
        total_usage = sum(customer.monthly_usage.values())
        current_month = datetime.now().strftime('%Y-%m')
        current_month_usage = customer.monthly_usage.get(current_month, 0)
        
        # API key metrics
        active_keys = len([k for k in customer.api_keys if k['status'] == 'active'])
        total_api_calls = sum(k.get('usage_count', 0) for k in customer.api_keys)
        
        return {
            'total_usage': total_usage,
            'current_month_usage': current_month_usage,
            'active_api_keys': active_keys,
            'total_api_keys': len(customer.api_keys),
            'total_api_calls': total_api_calls,
            'estimated_monthly_bill': current_month_usage * 0.10,
            'account_age_days': (datetime.now() - customer.created_at).days if customer.created_at else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting user metrics: {e}")
        return {}

def get_business_analytics(timeframe: str = '30d') -> Dict[str, Any]:
    """Get business analytics data"""
    try:
        # Mock analytics data - in production, this would query actual analytics
        return {
            'revenue': {
                'total': 15420.50,
                'monthly_recurring': 8750.00,
                'growth_rate': 12.5
            },
            'users': {
                'total': len(customer_manager.customers),
                'active': len([c for c in customer_manager.customers.values() if c.status == 'active']),
                'new_this_month': 25,
                'churn_rate': 2.1
            },
            'api_usage': {
                'total_calls': 1250000,
                'average_per_user': 15625,
                'peak_daily': 45000
            },
            'timeframe': timeframe,
            'last_updated': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting business analytics: {e}")
        return {}

def get_network_status() -> Dict[str, Any]:
    """Get network monitoring data"""
    try:
        # Mock network data - in production, this would query actual network metrics
        return {
            'active_sites': 1250,
            'total_verifications': 2500000,
            'network_health': 99.8,
            'average_response_time': 4.2,
            'revocation_events': 15,
            'top_domains': [
                {'domain': 'example.com', 'verifications': 125000},
                {'domain': 'test.org', 'verifications': 98000},
                {'domain': 'demo.net', 'verifications': 87000}
            ],
            'last_updated': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting network status: {e}")
        return {}

def get_revocation_status() -> Dict[str, Any]:
    """Get revocation monitoring data"""
    try:
        # Mock revocation data
        return {
            'total_revocations': 150,
            'pending_revocations': 5,
            'revocation_rate': 0.006,  # 0.6%
            'recent_revocations': [
                {
                    'id': 'rev_123',
                    'customer_id': 'cus_abc123',
                    'reason': 'API key compromised',
                    'timestamp': datetime.now().isoformat()
                }
            ],
            'last_updated': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting revocation status: {e}")
        return {}

def get_system_config() -> Dict[str, Any]:
    """Get system configuration data"""
    try:
        return {
            'version': '3.0.0',
            'environment': 'production',
            'maintenance_mode': False,
            'rate_limits': {
                'api_calls_per_minute': 1000,
                'registrations_per_hour': 100
            },
            'features': {
                'stripe_billing': True,
                'qr_generation': True,
                'admin_dashboard': True
            },
            'last_updated': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting system config: {e}")
        return {}

def log_admin_action(action_type: str, details: Dict[str, Any]):
    """Log admin actions for audit trail"""
    try:
        admin_id = session.get('customer_id')
        logger.info(f"Admin action: {action_type}", extra={
            'admin_id': admin_id,
            'action_type': action_type,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
        
        # In production, store this in a dedicated admin actions table
        
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

# Export the blueprint
__all__ = ['admin_bp']
