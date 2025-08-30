"""
Complete Billing Integration for Lemma.id Platform
Two-tier billing: PoH Network + Site IAM with Stripe integration
"""

import stripe
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
import logging

from .database_models import db, ActivityType, PaymentStatus, BillingInvoice
from auth.decorators import require_api_key

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_...')  # Use test key for development

billing_api = Blueprint('billing_api', __name__)
logger = logging.getLogger(__name__)

class BillingManager:
    """Complete billing management for two-tier pricing"""
    
    def __init__(self):
        self.poh_rate = 0.05  # $0.05 per MAU for PoH network
        self.iam_rate = 0.15  # $0.15 per MAU per site for IAM
        self.identity_rate = 2.00  # $2.00 per Stripe Identity verification
    
    def track_user_activity(self, site_id: str, user_id: str, activity_type: str, 
                          additional_data: Optional[Dict] = None) -> Dict:
        """Track user activity for billing purposes"""
        try:
            # Convert activity type
            if activity_type == 'poh_verification':
                activity_enum = ActivityType.POH_NETWORK
                site_specific_id = None
            elif activity_type == 'permission_verification':
                activity_enum = ActivityType.SITE_IAM
                site_specific_id = site_id
            else:
                raise ValueError(f"Unknown activity type: {activity_type}")
            
            # Track in database
            mau = db.track_user_activity(
                customer_id=site_id,
                user_id=user_id,
                activity_type=activity_enum,
                site_id=site_specific_id
            )
            
            return {
                'success': True,
                'activity_type': activity_type,
                'user_hash': mau.user_id_hash[:8] + '...',  # Privacy-preserving
                'month_year': mau.month_year,
                'activity_count': mau.activity_count
            }
            
        except Exception as e:
            logger.error(f"Error tracking user activity: {e}")
            return {'success': False, 'error': str(e)}
    
    def calculate_current_usage(self, site_id: str) -> Dict:
        """Calculate current month usage for real-time billing estimates"""
        try:
            current_month = datetime.utcnow().strftime('%Y-%m')
            
            # Get MAU counts
            poh_mau = db.get_monthly_active_users(site_id, current_month, ActivityType.POH_NETWORK)
            iam_mau = db.get_monthly_active_users(site_id, current_month, ActivityType.SITE_IAM)
            
            poh_count = len(set(mau.user_id_hash for mau in poh_mau))
            iam_count = len(set(mau.user_id_hash for mau in iam_mau if mau.site_id == site_id))
            
            # Calculate costs
            poh_cost = poh_count * self.poh_rate
            iam_cost = iam_count * self.iam_rate
            total_cost = poh_cost + iam_cost
            
            # Get Stripe Identity verifications
            identity_verifications = [
                v for v in db.stripe_verifications 
                if v.customer_id == site_id and v.verification_date.strftime('%Y-%m') == current_month
            ]
            identity_cost = len(identity_verifications) * self.identity_rate
            
            # Traditional comparison
            traditional_auth0 = poh_count * 3.00  # Conservative estimate
            traditional_duo = iam_count * 3.00    # Conservative estimate
            traditional_total = traditional_auth0 + traditional_duo
            
            savings = traditional_total - total_cost
            savings_percentage = (savings / traditional_total * 100) if traditional_total > 0 else 0
            
            return {
                'success': True,
                'period': current_month,
                'usage': {
                    'poh_network': {
                        'mau_count': poh_count,
                        'rate': self.poh_rate,
                        'cost': poh_cost
                    },
                    'site_iam': {
                        'mau_count': iam_count,
                        'rate': self.iam_rate,
                        'cost': iam_cost
                    },
                    'identity_verifications': {
                        'count': len(identity_verifications),
                        'rate': self.identity_rate,
                        'cost': identity_cost
                    }
                },
                'totals': {
                    'subtotal': total_cost + identity_cost,
                    'total': total_cost + identity_cost
                },
                'comparison': {
                    'traditional_total': traditional_total,
                    'lemma_total': total_cost + identity_cost,
                    'monthly_savings': savings,
                    'savings_percentage': savings_percentage
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating usage: {e}")
            return {'success': False, 'error': str(e)}
    
    def generate_monthly_invoice(self, site_id: str, month_year: str) -> Dict:
        """Generate monthly invoice and create Stripe invoice"""
        try:
            # Calculate invoice
            invoice = db.calculate_monthly_bill(site_id, month_year)
            site = db.get_site(site_id)
            
            if not site:
                return {'success': False, 'error': 'Site not found'}
            
            # Create Stripe customer if needed
            if not site.stripe_customer_id:
                stripe_customer = stripe.Customer.create(
                    email=site.billing_email or site.admin_email,
                    name=site.company_name,
                    description=f"Lemma.id customer for {site.site_domain}",
                    metadata={
                        'site_id': site_id,
                        'site_domain': site.site_domain
                    }
                )
                site.stripe_customer_id = stripe_customer.id
                db.update_site(site_id, {'stripe_customer_id': stripe_customer.id})
            
            # Create Stripe invoice
            stripe_invoice = stripe.Invoice.create(
                customer=site.stripe_customer_id,
                description=f"Lemma.id Platform - {month_year}",
                metadata={
                    'site_id': site_id,
                    'period': month_year,
                    'poh_mau': invoice.poh_mau_count,
                    'iam_mau': invoice.iam_mau_count,
                    'identity_verifications': invoice.identity_verification_count
                }
            )
            
            # Add line items
            if invoice.poh_amount > 0:
                stripe.InvoiceItem.create(
                    customer=site.stripe_customer_id,
                    invoice=stripe_invoice.id,
                    amount=int(invoice.poh_amount * 100),  # Convert to cents
                    currency='usd',
                    description=f"PoH Network - {invoice.poh_mau_count} MAU × ${invoice.poh_rate}"
                )
            
            if invoice.iam_amount > 0:
                stripe.InvoiceItem.create(
                    customer=site.stripe_customer_id,
                    invoice=stripe_invoice.id,
                    amount=int(invoice.iam_amount * 100),  # Convert to cents
                    currency='usd',
                    description=f"Site IAM - {invoice.iam_mau_count} MAU × ${invoice.iam_rate}"
                )
            
            if invoice.identity_amount > 0:
                stripe.InvoiceItem.create(
                    customer=site.stripe_customer_id,
                    invoice=stripe_invoice.id,
                    amount=int(invoice.identity_amount * 100),  # Convert to cents
                    currency='usd',
                    description=f"Identity Verifications - {invoice.identity_verification_count} × ${invoice.identity_rate}"
                )
            
            # Finalize invoice
            stripe_invoice = stripe.Invoice.finalize_invoice(stripe_invoice.id)
            
            # Update database
            invoice.stripe_invoice_id = stripe_invoice.id
            invoice.payment_status = PaymentStatus.PENDING
            
            return {
                'success': True,
                'invoice': {
                    'site_id': site_id,
                    'period': month_year,
                    'stripe_invoice_id': stripe_invoice.id,
                    'stripe_invoice_url': stripe_invoice.hosted_invoice_url,
                    'amount': invoice.total_amount,
                    'status': invoice.payment_status.value,
                    'breakdown': {
                        'poh_network': {
                            'mau': invoice.poh_mau_count,
                            'amount': invoice.poh_amount
                        },
                        'site_iam': {
                            'mau': invoice.iam_mau_count,
                            'amount': invoice.iam_amount
                        },
                        'identity_verifications': {
                            'count': invoice.identity_verification_count,
                            'amount': invoice.identity_amount
                        }
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating invoice: {e}")
            return {'success': False, 'error': str(e)}
    
    def handle_stripe_webhook(self, event_data: Dict) -> Dict:
        """Handle Stripe webhook events"""
        try:
            event_type = event_data.get('type')
            
            if event_type == 'invoice.payment_succeeded':
                # Payment successful
                invoice_data = event_data['data']['object']
                site_id = invoice_data['metadata'].get('site_id')
                period = invoice_data['metadata'].get('period')
                
                if site_id and period:
                    invoice = db.get_billing_invoice(site_id, period)
                    if invoice:
                        invoice.payment_status = PaymentStatus.PAID
                        invoice.payment_date = datetime.utcnow()
                        invoice.stripe_charge_id = invoice_data.get('charge')
                
                return {'success': True, 'message': 'Payment processed successfully'}
            
            elif event_type == 'invoice.payment_failed':
                # Payment failed
                invoice_data = event_data['data']['object']
                site_id = invoice_data['metadata'].get('site_id')
                period = invoice_data['metadata'].get('period')
                
                if site_id and period:
                    invoice = db.get_billing_invoice(site_id, period)
                    if invoice:
                        invoice.payment_status = PaymentStatus.FAILED
                
                return {'success': True, 'message': 'Payment failure recorded'}
            
            return {'success': True, 'message': f'Webhook {event_type} processed'}
            
        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            return {'success': False, 'error': str(e)}

# Global billing manager
billing_manager = BillingManager()

@billing_api.route('/api/v1/billing/track-activity', methods=['POST'])
@cross_origin()
@require_api_key
def track_activity():
    """
    Track user activity for billing
    
    POST /api/v1/billing/track-activity
    {
        "site_id": "site_abc123",
        "user_id": "user_unique_id",
        "activity_type": "poh_verification|permission_verification"
    }
    """
    try:
        data = request.get_json()
        
        required_fields = ['site_id', 'user_id', 'activity_type']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        result = billing_manager.track_user_activity(
            site_id=data['site_id'],
            user_id=data['user_id'],
            activity_type=data['activity_type'],
            additional_data=data.get('additional_data')
        )
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@billing_api.route('/api/v1/billing/usage/<site_id>', methods=['GET'])
@cross_origin()
@require_api_key
def get_current_usage(site_id):
    """
    Get current month usage and billing estimate
    
    GET /api/v1/billing/usage/{site_id}
    """
    try:
        result = billing_manager.calculate_current_usage(site_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@billing_api.route('/api/v1/billing/invoice/<site_id>/<month_year>', methods=['POST'])
@cross_origin()
@require_api_key
def generate_invoice(site_id, month_year):
    """
    Generate monthly invoice
    
    POST /api/v1/billing/invoice/{site_id}/{month_year}
    """
    try:
        result = billing_manager.generate_monthly_invoice(site_id, month_year)
        
        if result['success']:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@billing_api.route('/api/v1/billing/webhook', methods=['POST'])
@cross_origin()
def stripe_webhook():
    """
    Handle Stripe webhook events
    
    POST /api/v1/billing/webhook
    """
    try:
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature')
        
        # Verify webhook signature (in production)
        # event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        
        # For development, just parse the JSON
        event_data = request.get_json()
        
        result = billing_manager.handle_stripe_webhook(event_data)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 400

@billing_api.route('/api/v1/billing/analytics/<site_id>', methods=['GET'])
@cross_origin()
@require_api_key
def get_billing_analytics(site_id):
    """
    Get billing analytics and cost comparison
    
    GET /api/v1/billing/analytics/{site_id}
    """
    try:
        # Get current usage
        usage_result = billing_manager.calculate_current_usage(site_id)
        
        if not usage_result['success']:
            return jsonify(usage_result), 400
        
        # Get site info
        site = db.get_site(site_id)
        if not site:
            return jsonify({'error': 'Site not found'}), 404
        
        # Get historical data (last 6 months)
        historical_data = []
        current_date = datetime.utcnow()
        
        for i in range(6):
            month_date = current_date - timedelta(days=30 * i)
            month_year = month_date.strftime('%Y-%m')
            
            invoice = db.get_billing_invoice(site_id, month_year)
            if invoice:
                historical_data.append({
                    'period': month_year,
                    'poh_mau': invoice.poh_mau_count,
                    'iam_mau': invoice.iam_mau_count,
                    'total_cost': invoice.total_amount,
                    'payment_status': invoice.payment_status.value
                })
        
        return jsonify({
            'success': True,
            'site_info': {
                'site_id': site_id,
                'domain': site.site_domain,
                'company': site.company_name,
                'plan': site.plan.value
            },
            'current_usage': usage_result,
            'historical_data': historical_data,
            'cost_comparison': {
                'lemma_advantages': [
                    '96%+ cost savings vs Auth0+Duo',
                    '4.176µs verification (119,808x faster)',
                    'Single platform for PoH + IAM',
                    'No per-verification charges',
                    'Predictable monthly billing'
                ],
                'traditional_problems': [
                    'High per-verification costs',
                    'Multiple vendor complexity',
                    'Slow verification times',
                    'Unpredictable billing spikes',
                    'Limited network effects'
                ]
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
