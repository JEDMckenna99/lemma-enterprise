"""
MAU (Monthly Active Users) API Endpoints
Provides REST API for MAU tracking, analytics, and billing integration
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from typing import Dict, Any, Optional

from api.mau_tracker import mau_tracker, track_user_activity, get_monthly_billing_data, get_customer_analytics

logger = logging.getLogger(__name__)

# Create blueprint
mau_api_bp = Blueprint('mau_api', __name__)

@mau_api_bp.route('/api/mau/track', methods=['POST'])
def track_user():
    """
    Track user activity for MAU calculation
    
    Expected payload:
    {
        "customer_id": "cus_stripe_customer_id",
        "user_id": "user@example.com",
        "timestamp": "2024-01-15T10:30:00Z" (optional)
    }
    """
    try:
        data = request.get_json()
        
        customer_id = data.get('customer_id')
        user_id = data.get('user_id')
        timestamp_str = data.get('timestamp')
        
        if not customer_id or not user_id:
            return jsonify({'error': 'customer_id and user_id are required'}), 400
        
        # Parse timestamp if provided
        timestamp = None
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', ''))
            except ValueError:
                return jsonify({'error': 'Invalid timestamp format. Use ISO format.'}), 400
        
        # Track the user activity
        result = track_user_activity(customer_id, user_id, timestamp)
        
        return jsonify({
            'success': True,
            'tracking_result': result
        })
        
    except Exception as e:
        logger.error(f"Error tracking user activity: {e}")
        return jsonify({'error': 'Failed to track user activity'}), 500

@mau_api_bp.route('/api/mau/billing/<customer_id>', methods=['GET'])
def get_billing_data(customer_id):
    """
    Get MAU billing data for a customer
    
    Query parameters:
    - month: YYYY-MM format (optional, defaults to current month)
    """
    try:
        month = request.args.get('month')
        
        billing_data = get_monthly_billing_data(customer_id, month)
        
        return jsonify({
            'success': True,
            'billing_data': billing_data
        })
        
    except Exception as e:
        logger.error(f"Error getting billing data: {e}")
        return jsonify({'error': 'Failed to get billing data'}), 500

@mau_api_bp.route('/api/mau/analytics/<customer_id>', methods=['GET'])
def get_analytics(customer_id):
    """
    Get comprehensive MAU analytics for a customer
    
    Query parameters:
    - days: Number of days to include in analytics (default: 30)
    """
    try:
        days = int(request.args.get('days', 30))
        
        if days < 1 or days > 365:
            return jsonify({'error': 'Days must be between 1 and 365'}), 400
        
        analytics = get_customer_analytics(customer_id, days)
        
        return jsonify({
            'success': True,
            'analytics': analytics
        })
        
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        return jsonify({'error': 'Failed to get analytics'}), 500

@mau_api_bp.route('/api/mau/rolling/<customer_id>', methods=['GET'])
def get_rolling_mau(customer_id):
    """
    Get rolling 30-day MAU for a customer
    
    Query parameters:
    - date: Reference date in YYYY-MM-DD format (optional, defaults to today)
    """
    try:
        date_str = request.args.get('date')
        
        reference_date = datetime.utcnow()
        if date_str:
            try:
                reference_date = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400
        
        rolling_data = mau_tracker.get_rolling_mau(customer_id, reference_date)
        
        return jsonify({
            'success': True,
            'rolling_mau': rolling_data
        })
        
    except Exception as e:
        logger.error(f"Error getting rolling MAU: {e}")
        return jsonify({'error': 'Failed to get rolling MAU'}), 500

@mau_api_bp.route('/api/mau/export/<customer_id>', methods=['GET'])
def export_billing_data(customer_id):
    """
    Export billing data for Stripe integration
    
    Query parameters:
    - month: YYYY-MM format (required)
    """
    try:
        month = request.args.get('month')
        
        if not month:
            return jsonify({'error': 'month parameter is required (YYYY-MM format)'}), 400
        
        # Validate month format
        try:
            datetime.strptime(month, '%Y-%m')
        except ValueError:
            return jsonify({'error': 'Invalid month format. Use YYYY-MM.'}), 400
        
        export_data = mau_tracker.export_billing_data(customer_id, month)
        
        return jsonify({
            'success': True,
            'export_data': export_data
        })
        
    except Exception as e:
        logger.error(f"Error exporting billing data: {e}")
        return jsonify({'error': 'Failed to export billing data'}), 500

@mau_api_bp.route('/api/mau/health', methods=['GET'])
def health_check():
    """Health check endpoint for MAU tracking system"""
    try:
        # Get some basic stats
        current_time = datetime.utcnow()
        
        return jsonify({
            'success': True,
            'service': 'MAU Tracking API',
            'status': 'healthy',
            'timestamp': current_time.isoformat(),
            'version': '1.0.0'
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'error': 'Health check failed'}), 500

# Batch tracking endpoint for high-volume scenarios
@mau_api_bp.route('/api/mau/track/batch', methods=['POST'])
def track_users_batch():
    """
    Track multiple user activities in batch for MAU calculation
    
    Expected payload:
    {
        "customer_id": "cus_stripe_customer_id",
        "users": [
            {"user_id": "user1@example.com", "timestamp": "2024-01-15T10:30:00Z"},
            {"user_id": "user2@example.com", "timestamp": "2024-01-15T10:31:00Z"},
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        
        customer_id = data.get('customer_id')
        users = data.get('users', [])
        
        if not customer_id:
            return jsonify({'error': 'customer_id is required'}), 400
        
        if not users or not isinstance(users, list):
            return jsonify({'error': 'users array is required'}), 400
        
        if len(users) > 1000:  # Limit batch size
            return jsonify({'error': 'Batch size cannot exceed 1000 users'}), 400
        
        results = []
        errors = []
        
        for i, user_data in enumerate(users):
            try:
                user_id = user_data.get('user_id')
                timestamp_str = user_data.get('timestamp')
                
                if not user_id:
                    errors.append(f"User {i}: user_id is required")
                    continue
                
                # Parse timestamp if provided
                timestamp = None
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', ''))
                
                # Track the user activity
                result = track_user_activity(customer_id, user_id, timestamp)
                results.append(result)
                
            except Exception as e:
                errors.append(f"User {i}: {str(e)}")
        
        return jsonify({
            'success': True,
            'processed': len(results),
            'errors': len(errors),
            'results': results,
            'error_details': errors if errors else None
        })
        
    except Exception as e:
        logger.error(f"Error in batch tracking: {e}")
        return jsonify({'error': 'Failed to process batch tracking'}), 500

# Export the blueprint
__all__ = ['mau_api_bp']