"""
Stripe Checkout API for Lemma Shield Subscriptions
Handles subscription creation and payment processing

Uses PPID-based customer lookup for subscription management.
"""

import os
import logging
from flask import Blueprint, request, jsonify, redirect, url_for, g
from typing import Dict, Any
from auth.decorators import require_wallet_ppid, require_customer_or_admin

logger = logging.getLogger(__name__)

# Import Stripe
try:
    import stripe
    STRIPE_AVAILABLE = True
    # Use the working API key from the environment or hardcoded for now
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_51QJDkbP8RRlCYD4t8GWdrvJOlE6bZRnSqJ8Xzx8mKJHdVE3I8eOhCvMXZjNGq0gJNvJKFGP9t8QXzlW8NNQ6M2kN00XBuMjIuM')
except ImportError:
    STRIPE_AVAILABLE = False
    logger.error("Stripe library not available")

# Create blueprint
stripe_checkout_bp = Blueprint('stripe_checkout', __name__)

# Plan configuration with correct price IDs
SUBSCRIPTION_PLANS = {
    'starter': {
        'name': 'Lemma Shield - Starter',
        'price_id': 'price_1RtBQFDIouMeOMabSXK43jDW',
        'amount': 2900,  # $29/month
        'description': 'Perfect for small to medium websites',
        'features': [
            'Up to 10,000 verifications/month',
            'Microsecond-level performance', 
            '99.9% offline operation',
            'Cross-site network effects',
            'Email support'
        ]
    },
    'professional': {
        'name': 'Lemma Shield - Professional',
        'price_id': 'price_1RtBQGDIouMeOMabRGaVYg0A',
        'amount': 9900,  # $99/month
        'description': 'Advanced features for growing businesses',
        'features': [
            'Up to 100,000 verifications/month',
            'Priority support',
            'Advanced analytics dashboard', 
            'Custom integration assistance',
            'SLA: 99.9% uptime guarantee'
        ]
    },
    'enterprise': {
        'name': 'Lemma Shield - Enterprise',
        'price_id': 'price_1RtBQGDIouMeOMab4DsImBZ3',
        'amount': 49900,  # $499/month
        'description': 'Full-scale enterprise protection',
        'features': [
            'Unlimited verifications',
            'White-label options',
            'Dedicated support team',
            'Custom implementations',
            'SLA: 99.99% uptime + 4hr response'
        ]
    }
}

# Cache for payment links (more reliable than checkout sessions)
PAYMENT_LINKS_CACHE = {}

@stripe_checkout_bp.route('/api/create-checkout-session', methods=['POST'])
@require_customer_or_admin
def create_checkout_session():
    """
    Create a Stripe Payment Link for subscription (more reliable than checkout sessions)
    """
    if not STRIPE_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'stripe_not_available',
            'message': 'Stripe integration not available'
        }), 500

    try:
        data = request.get_json()
        plan_type = data.get('planType')
        
        if not plan_type or plan_type not in SUBSCRIPTION_PLANS:
            return jsonify({
                'success': False,
                'error': 'invalid_plan',
                'message': 'Invalid subscription plan specified'
            }), 400
        
        plan_config = SUBSCRIPTION_PLANS[plan_type]
        
        # Use cached payment link if available
        if plan_type in PAYMENT_LINKS_CACHE:
            cached = PAYMENT_LINKS_CACHE[plan_type]
            logger.info(f"✅ Using cached Payment Link for {plan_type} plan")
            return jsonify({
                'success': True,
                'url': cached['url'],
                'payment_link_id': cached['id']
            })
        
        # Create Stripe Payment Link (more reliable than checkout sessions)
        payment_link = stripe.PaymentLink.create(
            line_items=[{
                'price': plan_config['price_id'],
                'quantity': 1,
            }],
            after_completion={
                'type': 'redirect',
                'redirect': {
                    'url': request.host_url + 'subscription/success?plan=' + plan_type
                }
            },
            metadata={
                'plan_type': plan_type,
                'plan_name': plan_config['name']
            }
        )
        
        # Cache the payment link
        PAYMENT_LINKS_CACHE[plan_type] = {
            'id': payment_link.id,
            'url': payment_link.url
        }
        
        logger.info(f"✅ Created Stripe Payment Link {payment_link.id} for {plan_type} plan")
        
        return jsonify({
            'success': True,
            'url': payment_link.url,
            'payment_link_id': payment_link.id
        })
        
    except stripe.error.StripeError as e:
        logger.error(f"❌ Stripe error creating payment link: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'stripe_error',
            'message': 'Payment processing error. Please try again.'
        }), 500
    except Exception as e:
        logger.error(f"❌ Error creating payment link: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'internal_error',
            'message': 'Internal server error. Please try again.'
        }), 500

@stripe_checkout_bp.route('/subscription/success')
def subscription_success():
    """
    Handle successful subscription payment.
    Uses Stripe webhook to associate with customer PPID for persistence.
    """
    plan_type = request.args.get('plan')
    
    if not plan_type:
        return redirect(url_for('main.pricing'))
    
    try:
        plan_name = SUBSCRIPTION_PLANS.get(plan_type, {}).get('name', 'Lemma Shield')
        logger.info(f"✅ User completed subscription flow for {plan_type} plan")
        
        # Note: Subscription is associated with customer via Stripe webhook
        # The webhook will use customer email/metadata to link to PPID
        
        return redirect(url_for('main.dashboard') + '?subscription=success')
        
    except Exception as e:
        logger.error(f"❌ Error processing subscription success: {str(e)}")
        return redirect(url_for('main.pricing') + '?error=processing')


@stripe_checkout_bp.route('/api/subscription/status')
@require_wallet_ppid
def get_subscription_status():
    """
    Get current user's subscription status.
    Requires wallet authentication (via verified X-Lemma-Credential header).
    """
    ppid = getattr(g, 'ppid', None)
    
    if not ppid:
        return jsonify({
            'success': True,
            'subscription': None,
            'message': 'No PPID provided'
        })
    
    # Look up subscription by PPID in database
    try:
        from .customer_accounts import customer_manager
        customer = customer_manager.get_customer_by_did(ppid)
        
        if customer and hasattr(customer, 'subscription_plan'):
            return jsonify({
                'success': True,
                'subscription': {
                    'plan_type': customer.subscription_plan,
                    'status': 'active'
                }
            })
    except Exception as e:
        logger.warning(f"Could not look up subscription for PPID: {e}")
    
    return jsonify({
        'success': True,
        'subscription': None,
        'message': 'No active subscription'
    })


def get_plan_config(plan_type: str) -> Dict[str, Any]:
    """Get configuration for a specific plan"""
    return SUBSCRIPTION_PLANS.get(plan_type, {})