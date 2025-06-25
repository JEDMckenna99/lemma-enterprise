"""
Lemma Enterprise - Stripe Manager
Handles all Stripe operations for network-effect pricing model.
"""

import os
import stripe
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from flask import current_app

logger = logging.getLogger(__name__)

class LemmaStripeManager:
    """
    Manages all Stripe operations for Lemma billing.
    Implements network-effect pricing with dynamic subscription management.
    """
    
    def __init__(self):
        """Initialize Stripe manager with API keys."""
        self.stripe_secret_key = os.getenv('STRIPE_SECRET_KEY')
        self.stripe_publishable_key = os.getenv('STRIPE_PUBLISHABLE_KEY')
        self.stripe_webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        
        if not self.stripe_secret_key:
            logger.warning("STRIPE_SECRET_KEY not set - Stripe functionality disabled")
            self.enabled = False
            return
            
        stripe.api_key = self.stripe_secret_key
        self.enabled = True
        logger.info("Stripe manager initialized successfully")
    
    def is_enabled(self) -> bool:
        """Check if Stripe integration is enabled."""
        return self.enabled
    
    def create_stripe_customer(self, customer_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new Stripe customer for Lemma billing.
        
        Args:
            customer_data: Customer information from onboarding
            
        Returns:
            Dict with Stripe customer details or None if failed
        """
        if not self.enabled:
            logger.warning("Stripe not enabled - cannot create customer")
            return None
            
        try:
            stripe_customer = stripe.Customer.create(
                email=customer_data.get('email'),
                name=customer_data.get('company') or customer_data.get('email'),
                description=f"Lemma Customer - {customer_data.get('domain')}",
                metadata={
                    'lemma_customer_id': customer_data.get('customer_id'),
                    'domain': customer_data.get('domain'),
                    'created_via': 'lemma_onboarding'
                }
            )
            
            logger.info(f"Created Stripe customer {stripe_customer.id} for {customer_data.get('email')}")
            
            return {
                'stripe_customer_id': stripe_customer.id,
                'stripe_created_at': datetime.fromtimestamp(stripe_customer.created).isoformat(),
                'billing_email': stripe_customer.email
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating Stripe customer: {e}")
            return None
    
    def create_subscription(self, customer_id: str, network_pricing: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a subscription for network-effect pricing.
        
        Args:
            customer_id: Stripe customer ID
            network_pricing: Current network pricing information
            
        Returns:
            Dict with subscription details or None if failed
        """
        if not self.enabled:
            return None
            
        try:
            # Create price for current network rate
            current_rate = network_pricing.get('current_rate', 0.10)
            price = self.create_stripe_price_for_rate(current_rate)
            
            if not price:
                logger.error("Failed to create price for subscription")
                return None
            
            # Create subscription
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{'price': price['id']}],
                billing_cycle_anchor=None,  # Start immediately
                description=f"Lemma Verification Service - ${current_rate}/user/month",
                metadata={
                    'lemma_service': 'network_verification',
                    'network_rate': str(current_rate),
                    'network_sites': str(network_pricing.get('network_sites', 0)),
                    'tier': network_pricing.get('tier', {}).get('name', 'starter')
                }
            )
            
            logger.info(f"Created subscription {subscription.id} for customer {customer_id}")
            
            return {
                'stripe_subscription_id': subscription.id,
                'stripe_price_id': price['id'],
                'current_rate': current_rate,
                'status': subscription.status,
                'created_at': datetime.fromtimestamp(subscription.created).isoformat(),
                'current_period_start': datetime.fromtimestamp(subscription.current_period_start).isoformat(),
                'current_period_end': datetime.fromtimestamp(subscription.current_period_end).isoformat()
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create subscription: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating subscription: {e}")
            return None
    
    def create_stripe_price_for_rate(self, rate: float) -> Optional[Dict[str, Any]]:
        """
        Create a Stripe price for a specific network rate.
        
        Args:
            rate: Monthly rate per user (e.g., 0.10 for $0.10)
            
        Returns:
            Dict with price details or None if failed
        """
        if not self.enabled:
            return None
            
        try:
            # Convert rate to cents
            unit_amount = int(rate * 100)
            
            price = stripe.Price.create(
                unit_amount=unit_amount,
                currency='usd',
                recurring={'interval': 'month'},
                product_data={
                    'name': 'Lemma Network Verification Service',
                    'description': f'Monthly verification service at ${rate:.3f} per user'
                },
                metadata={
                    'lemma_service': 'network_verification',
                    'rate': str(rate),
                    'version': '2.3.0'
                }
            )
            
            logger.info(f"Created Stripe price {price.id} for rate ${rate}")
            
            return {
                'id': price.id,
                'rate': rate,
                'unit_amount': unit_amount,
                'currency': price.currency
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe price: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating Stripe price: {e}")
            return None
    
    def update_subscription_pricing(self, customer_id: str, subscription_id: str, new_rate: float) -> bool:
        """
        Update subscription pricing for network rate changes.
        
        Args:
            customer_id: Stripe customer ID
            subscription_id: Stripe subscription ID
            new_rate: New monthly rate per user
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
            
        try:
            # Create new price for the new rate
            new_price = self.create_stripe_price_for_rate(new_rate)
            if not new_price:
                return False
            
            # Get current subscription
            subscription = stripe.Subscription.retrieve(subscription_id)
            
            # Update subscription with new price
            updated_subscription = stripe.Subscription.modify(
                subscription_id,
                items=[{
                    'id': subscription.items.data[0].id,
                    'price': new_price['id']
                }],
                proration_behavior='create_prorations',
                metadata={
                    **subscription.metadata,
                    'network_rate': str(new_rate),
                    'rate_updated_at': datetime.now().isoformat()
                }
            )
            
            logger.info(f"Updated subscription {subscription_id} to rate ${new_rate}")
            return True
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to update subscription pricing: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating subscription: {e}")
            return False
    
    def charge_verification_fee(self, customer_id: str, user_count: int, amount_override: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Charge one-time verification fee for new users.
        
        Args:
            customer_id: Stripe customer ID
            user_count: Number of users being verified
            amount_override: Override amount (for testing/adjustments)
            
        Returns:
            Dict with charge details or None if failed
        """
        if not self.enabled:
            return None
            
        try:
            # Calculate charge amount
            verification_fee = amount_override or 2.00  # $2.00 per user
            total_amount = verification_fee * user_count
            amount_cents = int(total_amount * 100)
            
            charge = stripe.Charge.create(
                amount=amount_cents,
                currency='usd',
                customer=customer_id,
                description=f"Lemma Network Verification - {user_count} user(s) @ ${verification_fee:.2f} each",
                metadata={
                    'lemma_service': 'verification_fee',
                    'user_count': str(user_count),
                    'fee_per_user': str(verification_fee),
                    'charged_at': datetime.now().isoformat()
                }
            )
            
            logger.info(f"Charged ${total_amount:.2f} verification fee for {user_count} users to customer {customer_id}")
            
            return {
                'charge_id': charge.id,
                'amount': total_amount,
                'user_count': user_count,
                'fee_per_user': verification_fee,
                'status': charge.status,
                'created_at': datetime.fromtimestamp(charge.created).isoformat()
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to charge verification fee: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error charging verification fee: {e}")
            return None
    
    def get_customer_billing_summary(self, customer_id: str) -> Dict[str, Any]:
        """
        Get comprehensive billing summary for a customer.
        
        Args:
            customer_id: Stripe customer ID
            
        Returns:
            Dict with billing summary information
        """
        if not self.enabled:
            return {'enabled': False, 'message': 'Stripe not configured'}
            
        try:
            # Get customer
            customer = stripe.Customer.retrieve(customer_id)
            
            # Get subscriptions
            subscriptions = stripe.Subscription.list(customer=customer_id, limit=10)
            
            # Get recent charges
            charges = stripe.Charge.list(customer=customer_id, limit=10)
            
            # Get upcoming invoice
            try:
                upcoming_invoice = stripe.Invoice.upcoming(customer=customer_id)
            except stripe.error.InvalidRequestError:
                upcoming_invoice = None
            
            # Calculate totals
            total_charges = sum(charge.amount for charge in charges.data) / 100
            verification_charges = sum(
                charge.amount for charge in charges.data 
                if charge.metadata.get('lemma_service') == 'verification_fee'
            ) / 100
            
            return {
                'enabled': True,
                'customer': {
                    'id': customer.id,
                    'email': customer.email,
                    'created': datetime.fromtimestamp(customer.created).isoformat()
                },
                'subscriptions': [{
                    'id': sub.id,
                    'status': sub.status,
                    'current_period_start': datetime.fromtimestamp(sub.current_period_start).isoformat(),
                    'current_period_end': datetime.fromtimestamp(sub.current_period_end).isoformat(),
                    'metadata': sub.metadata
                } for sub in subscriptions.data],
                'billing_totals': {
                    'total_charges': total_charges,
                    'verification_charges': verification_charges,
                    'subscription_charges': total_charges - verification_charges
                },
                'upcoming_invoice': {
                    'amount_due': upcoming_invoice.amount_due / 100 if upcoming_invoice else 0,
                    'period_start': datetime.fromtimestamp(upcoming_invoice.period_start).isoformat() if upcoming_invoice else None,
                    'period_end': datetime.fromtimestamp(upcoming_invoice.period_end).isoformat() if upcoming_invoice else None
                } if upcoming_invoice else None,
                'last_updated': datetime.now().isoformat()
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to get billing summary: {e}")
            return {'enabled': True, 'error': str(e)}
        except Exception as e:
            logger.error(f"Unexpected error getting billing summary: {e}")
            return {'enabled': True, 'error': str(e)}
    
    def cancel_subscription(self, subscription_id: str) -> bool:
        """Cancel a customer subscription."""
        if not self.enabled:
            return False
            
        try:
            stripe.Subscription.delete(subscription_id)
            logger.info(f"Cancelled subscription {subscription_id}")
            return True
        except stripe.error.StripeError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            return False
    
    def reactivate_subscription(self, customer_id: str, network_pricing: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Reactivate a subscription for a customer."""
        if not self.enabled:
            return None
            
        # This is essentially creating a new subscription
        return self.create_subscription(customer_id, network_pricing)
    
    def create_payment_intent(self, customer_id: str, amount: float, description: str, metadata: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Create a payment intent for one-time charges.
        
        Args:
            customer_id: Stripe customer ID
            amount: Amount in dollars
            description: Payment description
            metadata: Additional metadata
            
        Returns:
            Dict with payment intent details or None if failed
        """
        if not self.enabled:
            return None
            
        try:
            payment_intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Convert to cents
                currency='usd',
                customer=customer_id,
                description=description,
                metadata=metadata or {},
                automatic_payment_methods={'enabled': True}
            )
            
            return {
                'id': payment_intent.id,
                'client_secret': payment_intent.client_secret,
                'amount': amount,
                'status': payment_intent.status
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create payment intent: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating payment intent: {e}")
            return None
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Stripe webhook signature.
        
        Args:
            payload: Raw request payload
            signature: Stripe signature header
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.enabled or not self.stripe_webhook_secret:
            return False
            
        try:
            stripe.Webhook.construct_event(
                payload, signature, self.stripe_webhook_secret
            )
            return True
        except (stripe.error.SignatureVerificationError, ValueError):
            return False
    
    def create_identity_verification_session(self, customer_id: str, user_id: str, customer_domain: str, return_url: str) -> Optional[Dict[str, Any]]:
        """
        Create a Stripe Identity verification session for human verification.
        
        Args:
            customer_id: Stripe customer ID
            user_id: Lemma user ID
            customer_domain: Customer's domain for context
            return_url: URL to redirect to after verification
            
        Returns:
            Dict with verification session details or None if failed
        """
        if not self.enabled:
            return None
            
        try:
            verification_session = stripe.identity.VerificationSession.create(
                type='document',
                metadata={
                    'lemma_user_id': user_id,
                    'lemma_customer_id': customer_id,
                    'domain': customer_domain,
                    'service': 'lemma_human_verification'
                },
                options={
                    'document': {
                        'allowed_types': ['driving_license', 'passport', 'id_card'],
                        'require_id_number': True,
                        'require_live_capture': True,
                        'require_matching_selfie': True
                    }
                },
                return_url=return_url
            )
            
            logger.info(f"Created Identity verification session {verification_session.id} for user {user_id}")
            
            return {
                'verification_session_id': verification_session.id,
                'client_secret': verification_session.client_secret,
                'url': verification_session.url,
                'status': verification_session.status,
                'user_id': user_id,
                'created_at': datetime.fromtimestamp(verification_session.created).isoformat()
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Identity verification session: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating Identity verification session: {e}")
            return None
    
    def get_identity_verification_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get details of an Identity verification session.
        
        Args:
            session_id: Verification session ID
            
        Returns:
            Dict with session details or None if failed
        """
        if not self.enabled:
            return None
            
        try:
            verification_session = stripe.identity.VerificationSession.retrieve(session_id)
            
            return {
                'verification_session_id': verification_session.id,
                'status': verification_session.status,
                'type': verification_session.type,
                'created': datetime.fromtimestamp(verification_session.created).isoformat(),
                'metadata': verification_session.metadata,
                'last_error': verification_session.last_error,
                'verified_outputs': verification_session.verified_outputs,
                'url': verification_session.url
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve Identity verification session: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving Identity verification session: {e}")
            return None

# Global instance
_stripe_manager = None

def get_stripe_manager() -> LemmaStripeManager:
    """Get global Stripe manager instance."""
    global _stripe_manager
    if _stripe_manager is None:
        _stripe_manager = LemmaStripeManager()
    return _stripe_manager 