"""
Stripe Checkout API for Lemma Shield Subscriptions
Handles subscription creation and payment processing
"""

import os
import logging
from flask import Blueprint, request, jsonify, session, redirect, url_for
from typing import Dict, Any

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
        'price_id': 'price_1RtBQFDIouMeOMabSXK43jDW',  # One-time price for now, will update to recurring
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
        'price_id': 'price_1RtBQGDIouMeOMabRGaVYg0A',  # One-time price for now, will update to recurring
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
        'price_id': 'price_1RtBQGDIouMeOMab4DsImBZ3',  # One-time price for now, will update to recurring
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

@stripe_checkout_bp.route('/api/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """
    Create a Stripe Checkout session for subscription
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
        price_id = data.get('priceId')
        
        if not plan_type or plan_type not in SUBSCRIPTION_PLANS:
            return jsonify({
                'success': False,
                'error': 'invalid_plan',
                'message': 'Invalid subscription plan specified'
            }), 400
        
        plan_config = SUBSCRIPTION_PLANS[plan_type]
        
        # Create Stripe Checkout Session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': plan_config['price_id'],
                'quantity': 1,
            }],
            mode='payment',  # Will change to 'subscription' once we have recurring prices
            success_url=request.host_url + 'subscription/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.host_url + 'pricing?canceled=true',
            metadata={
                'plan_type': plan_type,
                'plan_name': plan_config['name']
            }
        )
        
        logger.info(f"✅ Created Stripe Checkout session {checkout_session.id} for {plan_type} plan")
        
        return jsonify({
            'success': True,
            'url': checkout_session.url,
            'session_id': checkout_session.id
        })
        
    except stripe.error.StripeError as e:
        logger.error(f"❌ Stripe error creating checkout session: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'stripe_error',
            'message': 'Payment processing error. Please try again.'
        }), 500
    except Exception as e:
        logger.error(f"❌ Error creating checkout session: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'internal_error',
            'message': 'Internal server error. Please try again.'
        }), 500

@stripe_checkout_bp.route('/subscription/success')
def subscription_success():
    """
    Handle successful subscription payment
    """
    session_id = request.args.get('session_id')
    
    if not session_id:
        return redirect(url_for('main.pricing'))
    
    try:
        if STRIPE_AVAILABLE:
            # Retrieve the checkout session to get details
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            plan_type = checkout_session.metadata.get('plan_type', 'unknown')
            plan_name = checkout_session.metadata.get('plan_name', 'Lemma Shield')
            
            logger.info(f"✅ Successful subscription payment for {plan_type} plan (session: {session_id})")
            
            # Store subscription info in session for now
            session['subscription'] = {
                'plan_type': plan_type,
                'plan_name': plan_name,
                'session_id': session_id,
                'status': 'active'
            }
        
        return redirect(url_for('main.dashboard') + '?subscription=success')
        
    except Exception as e:
        logger.error(f"❌ Error processing subscription success: {str(e)}")
        return redirect(url_for('main.pricing') + '?error=processing')

@stripe_checkout_bp.route('/api/subscription/status')
def get_subscription_status():
    """
    Get current user's subscription status
    """
    subscription = session.get('subscription')
    
    if not subscription:
        return jsonify({
            'success': True,
            'subscription': None,
            'message': 'No active subscription'
        })
    
    return jsonify({
        'success': True,
        'subscription': subscription
    })

def get_plan_config(plan_type: str) -> Dict[str, Any]:
    """Get configuration for a specific plan"""
    return SUBSCRIPTION_PLANS.get(plan_type, {})