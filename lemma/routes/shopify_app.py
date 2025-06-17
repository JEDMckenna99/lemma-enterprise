"""
Shopify App Integration Routes for Lemma Enterprise
Provides Shopify app endpoints integrated with the main Flask application
"""

import os
import json
import logging
from flask import Blueprint, render_template, jsonify, request, send_from_directory
import requests

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
shopify_bp = Blueprint('shopify', __name__, url_prefix='/shopify')

# Configuration
LEMMA_BASE_URL = os.environ.get('LEMMA_BASE_URL', 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com')

@shopify_bp.route('/health')
def health_check():
    """Health check endpoint for Shopify app"""
    return jsonify({
        "status": "ok",
        "service": "lemma-shopify-app",
        "version": "1.0.0",
        "timestamp": "2025-01-08T12:00:00Z"
    })

@shopify_bp.route('/dashboard')
def merchant_dashboard():
    """Merchant dashboard for Shopify app"""
    return render_template('shopify_dashboard.html')

@shopify_bp.route('/install')
def install_app():
    """Shopify app installation page"""
    return jsonify({
        "message": "Welcome to Lemma Human Verification for Shopify",
        "status": "ready_for_installation",
        "setup_url": f"{LEMMA_BASE_URL}/shopify/dashboard"
    })

@shopify_bp.route('/api/stats')
def get_stats():
    """API endpoint to get merchant verification statistics"""
    try:
        # Mock data for demonstration - in production this would come from database
        stats = {
            "verified_customers": 127,
            "blocked_bots": 45,
            "monthly_cost": "$12.50",
            "success_rate": "96.5%",
            "last_updated": "2025-01-08T12:00:00Z"
        }
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({"error": str(e)}), 500

@shopify_bp.route('/api/lemma-status')
def lemma_status():
    """Check Lemma service status"""
    try:
        # Check Lemma API health
        response = requests.get(f"{LEMMA_BASE_URL}/api/health", timeout=5)
        if response.status_code == 200:
            return jsonify({
                "status": "connected",
                "lemma_service": "operational",
                "response_time": "< 500ms"
            })
        else:
            return jsonify({
                "status": "error",
                "lemma_service": "unavailable",
                "error": f"HTTP {response.status_code}"
            }), 503
    except requests.RequestException as e:
        logger.error(f"Error checking Lemma status: {e}")
        return jsonify({
            "status": "error",
            "lemma_service": "unavailable",
            "error": str(e)
        }), 503

@shopify_bp.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    """Manage merchant settings"""
    if request.method == 'GET':
        # Return current settings
        settings = {
            "verification_enabled": True,
            "verification_mode": "standard",
            "block_suspicious": True,
            "store_name": "Demo Store"
        }
        return jsonify(settings)
    
    elif request.method == 'POST':
        # Update settings
        try:
            data = request.json
            # In production, save to database
            logger.info(f"Settings updated: {data}")
            return jsonify({
                "status": "success",
                "message": "Settings updated successfully"
            })
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return jsonify({"error": str(e)}), 500

@shopify_bp.route('/webhook/customer-created', methods=['POST'])
def webhook_customer_created():
    """Webhook handler for new customer registration"""
    try:
        data = request.json
        logger.info(f"New customer webhook received: {data.get('id', 'unknown')}")
        
        # In production, this would:
        # 1. Validate the webhook signature
        # 2. Check if customer needs verification
        # 3. Trigger verification flow if needed
        
        return jsonify({
            "status": "received",
            "action": "verification_check_scheduled"
        })
    except Exception as e:
        logger.error(f"Error processing customer webhook: {e}")
        return jsonify({"error": str(e)}), 500

@shopify_bp.route('/webhook/order-created', methods=['POST'])
def webhook_order_created():
    """Webhook handler for new orders"""
    try:
        data = request.json
        logger.info(f"New order webhook received: {data.get('id', 'unknown')}")
        
        # In production, this would:
        # 1. Validate the webhook signature
        # 2. Check customer verification status
        # 3. Apply fraud protection rules
        
        return jsonify({
            "status": "received",
            "action": "order_processed"
        })
    except Exception as e:
        logger.error(f"Error processing order webhook: {e}")
        return jsonify({"error": str(e)}), 500

@shopify_bp.route('/verify-widget')
def verification_widget():
    """Serve the verification widget for Shopify checkout"""
    return jsonify({
        "widget_url": f"{LEMMA_BASE_URL}/static/js/lemma-shield-widget.js",
        "api_endpoint": f"{LEMMA_BASE_URL}/api/shield/challenge",
        "instructions": "Include this widget in your checkout flow"
    })

@shopify_bp.route('/api/test-verification', methods=['POST'])
def test_verification():
    """Test verification endpoint for debugging"""
    try:
        # Forward to Lemma verification API
        response = requests.post(
            f"{LEMMA_BASE_URL}/api/generate-challenge",
            json=request.json,
            timeout=10
        )
        
        if response.status_code == 200:
            return jsonify({
                "status": "success",
                "verification": "completed",
                "challenge": response.json()
            })
        else:
            return jsonify({
                "status": "error",
                "error": f"Verification failed: HTTP {response.status_code}"
            }), 400
            
    except Exception as e:
        logger.error(f"Error in test verification: {e}")
        return jsonify({"error": str(e)}), 500 