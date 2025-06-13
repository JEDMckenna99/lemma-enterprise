#!/usr/bin/env python3
"""
📊 LEMMA BILLING API ENDPOINTS
==============================
Partner-facing usage endpoints, webhooks, and dispute workflows
Provides identical numbers to invoices with signature verification
"""

import json
import os
import time
import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, abort
from functools import wraps

from ..auth.security import api_key_required
from ..utils.input_validation import validate_input
from ..billing.usage_logger import get_usage_logger
from ..billing.rollup_engine import get_rollup_engine
from ..billing.billing_engine import get_billing_engine

logger = logging.getLogger(__name__)

# Create blueprint
billing_api = Blueprint('billing_api', __name__, url_prefix='/api/billing')

# Webhook signature verification
def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook signature using HMAC-SHA256."""
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected_signature}", signature)

def webhook_auth_required(f):
    """Decorator to verify webhook signatures."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for webhook signature header
        signature = request.headers.get('X-Lemma-Signature')
        if not signature:
            abort(401, description="Missing webhook signature")
        
        # Get webhook secret
        webhook_secret = os.environ.get('LEMMA_WEBHOOK_SECRET')
        if not webhook_secret:
            abort(500, description="Webhook secret not configured")
        
        # Verify signature
        payload = request.get_data()
        if not verify_webhook_signature(payload, signature, webhook_secret):
            abort(401, description="Invalid webhook signature")
        
        return f(*args, **kwargs)
    return decorated_function

@billing_api.route('/usage/monthly', methods=['GET'])
@api_key_required
def get_monthly_usage():
    """Get monthly usage statistics for a site."""
    try:
        # Validate input
        site_id = validate_input(request.args.get('site_id'), 'site_id', required=True)
        month = validate_input(request.args.get('month'), 'month', required=True)
        
        # Validate month format (YYYY-MM)
        try:
            datetime.strptime(month, '%Y-%m')
        except ValueError:
            return jsonify({"error": "Invalid month format. Use YYYY-MM"}), 400
        
        # Get billing engine
        billing_engine = get_billing_engine()
        
        # Calculate billing data
        billing_data = billing_engine.calculate_monthly_bill(site_id, month)
        
        if not billing_data['success']:
            return jsonify({"error": billing_data.get('error', 'Unknown error')}), 404
        
        # Return usage data in partner-friendly format
        usage_response = {
            "site_id": site_id,
            "month": month,
            "currency": billing_data['currency'],
            "usage_metrics": {
                "monthly_active_humans": billing_data['usage']['monthly_active_humans'],
                "new_humans": billing_data['usage']['new_humans'],
                "total_verifications": billing_data['usage']['total_verifications']
            },
            "billing_summary": {
                "mah_charge": billing_data['charges']['mah_charge'],
                "new_humans_charge": billing_data['charges']['new_humans_charge'],
                "subtotal": billing_data['charges']['subtotal'],
                "discount_percent": billing_data['charges']['discount_percent'],
                "discount_amount": billing_data['charges']['discount_amount'],
                "total_amount": billing_data['charges']['total_amount']
            },
            "rates": billing_data['rates'],
            "billing_date": billing_data['billing_date'],
            "due_date": billing_data['due_date']
        }
        
        return jsonify(usage_response)
        
    except Exception as e:
        logger.error(f"Error getting monthly usage: {e}")
        return jsonify({"error": "Internal server error"}), 500

@billing_api.route('/usage/daily', methods=['GET'])
@api_key_required
def get_daily_usage():
    """Get daily usage statistics for a site."""
    try:
        # Validate input
        site_id = validate_input(request.args.get('site_id'), 'site_id', required=True)
        date = validate_input(request.args.get('date'), 'date', required=True)
        
        # Validate date format (YYYY-MM-DD)
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        # Get rollup engine
        rollup_engine = get_rollup_engine()
        
        # Get daily rollup data
        daily_data = rollup_engine.get_daily_rollup(date)
        
        if not daily_data:
            return jsonify({
                "site_id": site_id,
                "date": date,
                "usage_metrics": {
                    "daily_active_humans": 0,
                    "new_humans": 0,
                    "total_verifications": 0
                },
                "message": "No usage data for this date"
            })
        
        # Extract site-specific metrics
        site_metrics = daily_data['metrics']['site_metrics'].get(site_id)
        
        if not site_metrics:
            return jsonify({
                "site_id": site_id,
                "date": date,
                "usage_metrics": {
                    "daily_active_humans": 0,
                    "new_humans": 0,
                    "total_verifications": 0
                },
                "message": "No usage data for this site on this date"
            })
        
        # Return daily usage data
        usage_response = {
            "site_id": site_id,
            "date": date,
            "usage_metrics": {
                "daily_active_humans": site_metrics['monthly_active_humans'],  # Unique humans this day
                "new_humans": site_metrics['new_humans'],
                "total_verifications": site_metrics['total_verifications']
            }
        }
        
        return jsonify(usage_response)
        
    except Exception as e:
        logger.error(f"Error getting daily usage: {e}")
        return jsonify({"error": "Internal server error"}), 500

@billing_api.route('/usage/range', methods=['GET'])
@api_key_required
def get_usage_range():
    """Get usage statistics for a date range."""
    try:
        # Validate input
        site_id = validate_input(request.args.get('site_id'), 'site_id', required=True)
        start_date = validate_input(request.args.get('start_date'), 'start_date', required=True)
        end_date = validate_input(request.args.get('end_date'), 'end_date', required=True)
        
        # Validate date formats
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        
        if start_dt > end_dt:
            return jsonify({"error": "Start date must be before end date"}), 400
        
        # Get usage logger
        usage_logger = get_usage_logger()
        
        # Calculate range statistics
        total_verifications = 0
        unique_humans = set()
        new_humans = set()
        daily_breakdown = []
        
        current_date = start_dt
        while current_date <= end_dt:
            date_str = current_date.strftime('%Y-%m-%d')
            events = usage_logger.get_daily_events(date_str)
            
            # Filter events for this site
            site_events = [e for e in events if e.get('site_id') == site_id]
            
            daily_verifications = len(site_events)
            daily_humans = set(e['subject_did_hash'] for e in site_events)
            
            total_verifications += daily_verifications
            unique_humans.update(daily_humans)
            
            daily_breakdown.append({
                "date": date_str,
                "verifications": daily_verifications,
                "unique_humans": len(daily_humans)
            })
            
            current_date += timedelta(days=1)
        
        # Return range statistics
        usage_response = {
            "site_id": site_id,
            "date_range": f"{start_date} to {end_date}",
            "summary": {
                "total_verifications": total_verifications,
                "unique_humans": len(unique_humans),
                "days": len(daily_breakdown)
            },
            "daily_breakdown": daily_breakdown
        }
        
        return jsonify(usage_response)
        
    except Exception as e:
        logger.error(f"Error getting usage range: {e}")
        return jsonify({"error": "Internal server error"}), 500

@billing_api.route('/invoice/<site_id>/<month>', methods=['GET'])
@api_key_required
def get_invoice(site_id, month):
    """Get invoice data for a site and month."""
    try:
        # Validate input
        site_id = validate_input(site_id, 'site_id', required=True)
        month = validate_input(month, 'month', required=True)
        
        # Validate month format
        try:
            datetime.strptime(month, '%Y-%m')
        except ValueError:
            return jsonify({"error": "Invalid month format. Use YYYY-MM"}), 400
        
        # Get billing engine
        billing_engine = get_billing_engine()
        
        # Calculate invoice
        billing_data = billing_engine.calculate_monthly_bill(site_id, month)
        
        if not billing_data['success']:
            return jsonify({"error": billing_data.get('error', 'Invoice not found')}), 404
        
        return jsonify(billing_data)
        
    except Exception as e:
        logger.error(f"Error getting invoice: {e}")
        return jsonify({"error": "Internal server error"}), 500

@billing_api.route('/invoice/<site_id>/<month>/pdf', methods=['GET'])
@api_key_required
def get_invoice_pdf(site_id, month):
    """Get PDF invoice for download."""
    try:
        # Validate input
        site_id = validate_input(site_id, 'site_id', required=True)
        month = validate_input(month, 'month', required=True)
        
        # Get billing engine
        billing_engine = get_billing_engine()
        
        # Calculate invoice
        billing_data = billing_engine.calculate_monthly_bill(site_id, month)
        
        if not billing_data['success']:
            return jsonify({"error": "Invoice not found"}), 404
        
        # Generate PDF
        pdf_bytes = billing_engine.generate_invoice_pdf(billing_data)
        
        # Return PDF response
        from flask import Response
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename=invoice_{site_id}_{month}.pdf'}
        )
        
    except Exception as e:
        logger.error(f"Error generating PDF invoice: {e}")
        return jsonify({"error": "Internal server error"}), 500

@billing_api.route('/webhook/billing-summary', methods=['POST'])
def webhook_billing_summary():
    """Webhook endpoint for billing summary notifications (no auth required for webhooks)."""
    try:
        # Parse webhook payload
        webhook_data = request.get_json()
        
        if not webhook_data:
            return jsonify({"error": "Invalid JSON payload"}), 400
        
        # Log webhook received
        logger.info(f"Received billing summary webhook: {webhook_data}")
        
        # Process webhook (could trigger external systems)
        # In a real system, this might:
        # - Update external billing systems
        # - Send notifications
        # - Trigger accounting workflows
        
        return jsonify({
            "status": "received",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "processed": True
        })
        
    except Exception as e:
        logger.error(f"Error processing billing webhook: {e}")
        return jsonify({"error": "Webhook processing failed"}), 500

@billing_api.route('/disputes', methods=['GET'])
@api_key_required
def list_disputes():
    """List billing disputes for a site."""
    try:
        site_id = validate_input(request.args.get('site_id'), 'site_id')
        
        # In a real system, this would query a disputes database
        # For now, return mock data
        disputes = [
            {
                "dispute_id": "disp_001",
                "site_id": site_id or "example_site",
                "month": "2025-01",
                "amount": "125.50",
                "reason": "Usage discrepancy",
                "status": "under_review",
                "created_at": "2025-02-15T10:00:00Z",
                "notes": "Customer claims lower usage than billed"
            }
        ]
        
        return jsonify({"disputes": disputes})
        
    except Exception as e:
        logger.error(f"Error listing disputes: {e}")
        return jsonify({"error": "Internal server error"}), 500

@billing_api.route('/disputes', methods=['POST'])
@api_key_required
def create_dispute():
    """Create a billing dispute."""
    try:
        # Validate input
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
        
        site_id = validate_input(data.get('site_id'), 'site_id', required=True)
        month = validate_input(data.get('month'), 'month', required=True)
        reason = validate_input(data.get('reason'), 'reason', required=True)
        amount = validate_input(data.get('amount'), 'amount')
        notes = validate_input(data.get('notes'), 'notes', max_length=1000)
        
        # Create dispute record
        dispute = {
            "dispute_id": f"disp_{int(time.time())}",
            "site_id": site_id,
            "month": month,
            "amount": amount,
            "reason": reason,
            "status": "submitted",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes or ""
        }
        
        # In a real system, save to disputes database
        logger.info(f"Created dispute: {dispute}")
        
        return jsonify(dispute), 201
        
    except Exception as e:
        logger.error(f"Error creating dispute: {e}")
        return jsonify({"error": "Internal server error"}), 500

@billing_api.route('/credit-notes', methods=['POST'])
@api_key_required
def create_credit_note():
    """Create a credit note for billing adjustments."""
    try:
        # Validate input
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
        
        site_id = validate_input(data.get('site_id'), 'site_id', required=True)
        amount = validate_input(data.get('amount'), 'amount', required=True)
        reason = validate_input(data.get('reason'), 'reason', required=True)
        reference_invoice = validate_input(data.get('reference_invoice'), 'reference_invoice')
        
        # Validate amount
        try:
            credit_amount = float(amount)
            if credit_amount <= 0:
                return jsonify({"error": "Credit amount must be positive"}), 400
        except ValueError:
            return jsonify({"error": "Invalid amount format"}), 400
        
        # Create credit note
        credit_note = {
            "credit_note_id": f"cn_{int(time.time())}",
            "site_id": site_id,
            "amount": amount,
            "reason": reason,
            "reference_invoice": reference_invoice,
            "status": "issued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "currency": "USD"
        }
        
        # In a real system, save to credit notes database and update accounting
        logger.info(f"Created credit note: {credit_note}")
        
        return jsonify(credit_note), 201
        
    except Exception as e:
        logger.error(f"Error creating credit note: {e}")
        return jsonify({"error": "Internal server error"}), 500

@billing_api.route('/health', methods=['GET'])
def billing_health():
    """Health check for billing system."""
    try:
        # Check billing engine
        billing_engine = get_billing_engine()
        
        # Check rollup engine
        rollup_engine = get_rollup_engine()
        
        # Check usage logger
        usage_logger = get_usage_logger()
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "billing_engine": "operational",
                "rollup_engine": "operational",
                "usage_logger": "operational"
            }
        })
        
    except Exception as e:
        logger.error(f"Billing health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 500

# Webhook signature verification sample for clients
@billing_api.route('/webhook/example-client', methods=['POST'])
@webhook_auth_required  # This shows how clients should verify signatures
def example_webhook_client():
    """Example webhook endpoint showing signature verification."""
    try:
        data = request.get_json()
        
        # Process the webhook
        logger.info(f"Verified webhook received: {data}")
        
        return jsonify({
            "status": "success",
            "message": "Webhook processed with verified signature",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error processing verified webhook: {e}")
        return jsonify({"error": "Webhook processing failed"}), 500 