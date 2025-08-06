"""
Usage-Based Billing System for Lemma Shield
Handles per-user pricing: $0.10/user/month + $2 setup fee

This implements a simplified usage-based billing system using Stripe's
existing capabilities until we can upgrade to use the newer Meter API.
"""

import os
import logging
import stripe
from flask import Blueprint, request, jsonify
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Set up Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_51QJDkbP8RRlCYD4t8GWdrvJOlE6bZRnSqJ8Xzx8mKJHdVE3I8eOhCvMXZjNGq0gJNvJKFGP9t8QXzlW8NNQ6M2kN00XBuMjIuM')

# Create blueprint
usage_billing_bp = Blueprint('usage_billing', __name__)

# Configuration for per-user billing
PRICING_CONFIG = {
    'per_user_monthly_cost': 0.10,  # $0.10 per user per month
    'setup_fee_per_user': 2.00,     # $2.00 one-time setup fee
    'currency': 'usd'
}

# Use the products we created earlier, but we'll need to create proper recurring prices
STRIPE_PRODUCTS = {
    'per_user_service': 'prod_SosqPFh2y10U2l',  # Per-user service product
    'setup_fee': 'prod_SosqiMvANHprJ6'          # Setup fee product
}

class UsageBillingManager:
    """Manages usage-based billing for Lemma Shield"""
    
    def __init__(self):
        self.per_user_cost = PRICING_CONFIG['per_user_monthly_cost']
        self.setup_fee = PRICING_CONFIG['setup_fee_per_user']
        self.currency = PRICING_CONFIG['currency']
    
    def create_customer_subscription(self, customer_email: str, customer_name: str, 
                                   initial_user_count: int = 0) -> Dict[str, Any]:
        """
        Create a new customer and subscription for usage-based billing
        
        Args:
            customer_email: Customer's email address
            customer_name: Customer's name
            initial_user_count: Initial number of users (for setup fee calculation)
            
        Returns:
            Dictionary with customer and subscription information
        """
        try:
            # Create Stripe customer
            customer = stripe.Customer.create(
                email=customer_email,
                name=customer_name,
                metadata={
                    'service': 'lemma_shield',
                    'billing_model': 'per_user'
                }
            )
            
            # For now, we'll create a basic subscription structure
            # This will need to be enhanced when we implement proper metered billing
            subscription_data = {
                'customer_id': customer.id,
                'customer_email': customer_email,
                'customer_name': customer_name,
                'billing_model': 'per_user',
                'per_user_rate': self.per_user_cost,
                'setup_fee_rate': self.setup_fee,
                'created_at': datetime.utcnow().isoformat(),
                'status': 'active'
            }
            
            # Calculate initial setup fee if users provided
            if initial_user_count > 0:
                setup_fee_total = initial_user_count * self.setup_fee
                setup_invoice = self.create_setup_fee_invoice(customer.id, initial_user_count, setup_fee_total)
                subscription_data['initial_setup_invoice'] = setup_invoice.id
            
            logger.info(f"Created customer {customer.id} with usage-based billing")
            return {
                'success': True,
                'customer': customer,
                'subscription_data': subscription_data
            }
            
        except Exception as e:
            logger.error(f"Failed to create customer subscription: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_setup_fee_invoice(self, customer_id: str, user_count: int, total_amount: float) -> stripe.Invoice:
        """Create an invoice for setup fees"""
        try:
            # Create invoice for setup fees
            invoice = stripe.Invoice.create(
                customer=customer_id,
                currency=self.currency,
                description=f"Lemma Shield setup fee for {user_count} users",
                metadata={
                    'type': 'setup_fee',
                    'user_count': str(user_count),
                    'per_user_fee': str(self.setup_fee)
                }
            )
            
            # Add invoice item for setup fees
            stripe.InvoiceItem.create(
                customer=customer_id,
                invoice=invoice.id,
                amount=int(total_amount * 100),  # Convert to cents
                currency=self.currency,
                description=f"Setup fee for {user_count} new users @ ${self.setup_fee} each"
            )
            
            # Finalize the invoice
            invoice = stripe.Invoice.finalize_invoice(invoice.id)
            
            return invoice
            
        except Exception as e:
            logger.error(f"Failed to create setup fee invoice: {e}")
            raise
    
    def calculate_monthly_cost(self, user_count: int) -> Dict[str, float]:
        """Calculate monthly cost for given user count"""
        monthly_cost = user_count * self.per_user_cost
        return {
            'user_count': user_count,
            'per_user_rate': self.per_user_cost,
            'monthly_total': monthly_cost,
            'currency': self.currency
        }
    
    def create_monthly_usage_invoice(self, customer_id: str, user_count: int, 
                                   billing_period_start: datetime, billing_period_end: datetime) -> stripe.Invoice:
        """Create monthly invoice for usage-based billing"""
        try:
            monthly_total = user_count * self.per_user_cost
            
            invoice = stripe.Invoice.create(
                customer=customer_id,
                currency=self.currency,
                description=f"Lemma Shield monthly usage: {billing_period_start.strftime('%B %Y')}",
                metadata={
                    'type': 'monthly_usage',
                    'user_count': str(user_count),
                    'billing_period_start': billing_period_start.isoformat(),
                    'billing_period_end': billing_period_end.isoformat(),
                    'per_user_rate': str(self.per_user_cost)
                }
            )
            
            # Add invoice item for monthly usage
            stripe.InvoiceItem.create(
                customer=customer_id,
                invoice=invoice.id,
                amount=int(monthly_total * 100),  # Convert to cents
                currency=self.currency,
                description=f"Monthly usage: {user_count} users @ ${self.per_user_cost} each"
            )
            
            # Finalize the invoice
            invoice = stripe.Invoice.finalize_invoice(invoice.id)
            
            return invoice
            
        except Exception as e:
            logger.error(f"Failed to create monthly usage invoice: {e}")
            raise

# Initialize billing manager
billing_manager = UsageBillingManager()

@usage_billing_bp.route('/api/billing/estimate', methods=['POST'])
def estimate_cost():
    """Estimate monthly cost for given user count"""
    try:
        data = request.get_json()
        user_count = data.get('user_count', 0)
        
        if not isinstance(user_count, int) or user_count < 0:
            return jsonify({'error': 'Invalid user_count'}), 400
        
        cost_breakdown = billing_manager.calculate_monthly_cost(user_count)
        setup_fee_total = user_count * billing_manager.setup_fee
        
        return jsonify({
            'success': True,
            'cost_breakdown': cost_breakdown,
            'setup_fee_total': setup_fee_total,
            'setup_fee_per_user': billing_manager.setup_fee
        })
        
    except Exception as e:
        logger.error(f"Cost estimation error: {e}")
        return jsonify({'error': 'Failed to estimate cost'}), 500

@usage_billing_bp.route('/api/billing/create-customer', methods=['POST'])
def create_customer():
    """Create a new customer with usage-based billing"""
    try:
        data = request.get_json()
        email = data.get('email')
        name = data.get('name')
        initial_users = data.get('initial_users', 0)
        
        if not email or not name:
            return jsonify({'error': 'Email and name are required'}), 400
        
        result = billing_manager.create_customer_subscription(email, name, initial_users)
        
        if result['success']:
            return jsonify({
                'success': True,
                'customer_id': result['customer'].id,
                'subscription_data': result['subscription_data']
            })
        else:
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        logger.error(f"Customer creation error: {e}")
        return jsonify({'error': 'Failed to create customer'}), 500

# Export the blueprint
__all__ = ['usage_billing_bp', 'billing_manager']