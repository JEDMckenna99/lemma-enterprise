"""
Lemma Enterprise - Billing Routes
Handles Stripe integration, billing management, and payment processing.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for, current_app
from functools import wraps
import secrets

from lemma.billing.stripe_manager import get_stripe_manager
from lemma.routes.onboarding import customer_required, get_customer_data, save_customer_data, calculate_network_pricing
from lemma.core.credential_service import get_credential_service

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')
logger = logging.getLogger(__name__)

def enhanced_customer_required(f):
    """Enhanced decorator that also checks for Stripe customer setup."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'customer_id' not in session:
            flash('Please complete onboarding first.', 'warning')
            return redirect(url_for('onboarding.start'))
        
        # Check if customer has billing data
        customer_data = get_customer_data(session['customer_id'])
        if not customer_data:
            flash('Customer data not found. Please start over.', 'error')
            return redirect(url_for('onboarding.start'))
        
        return f(*args, **kwargs)
    return decorated_function

@billing_bp.route('/status')
@enhanced_customer_required
def billing_status():
    """Get billing status for the current customer."""
    try:
        stripe_manager = get_stripe_manager()
        customer_data = get_customer_data(session['customer_id'])
        
        if not stripe_manager.is_enabled():
            return jsonify({
                'success': False,
                'error': 'Billing not configured',
                'message': 'Stripe integration is not enabled'
            }), 503
        
        # Get Stripe customer ID
        stripe_customer_id = customer_data.get('stripe_customer_id')
        
        if not stripe_customer_id:
            return jsonify({
                'success': True,
                'billing_status': 'not_setup',
                'message': 'Billing not yet configured for this customer',
                'setup_required': True
            })
        
        # Get billing summary from Stripe
        billing_summary = stripe_manager.get_customer_billing_summary(stripe_customer_id)
        
        return jsonify({
            'success': True,
            'billing_status': 'active',
            'customer_data': {
                'customer_id': session['customer_id'],
                'domain': customer_data.get('domain'),
                'email': customer_data.get('email')
            },
            'stripe_data': billing_summary,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting billing status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@billing_bp.route('/setup', methods=['POST'])
@enhanced_customer_required
def setup_billing():
    """Set up billing for a customer."""
    try:
        stripe_manager = get_stripe_manager()
        customer_data = get_customer_data(session['customer_id'])
        
        if not stripe_manager.is_enabled():
            return jsonify({
                'success': False,
                'error': 'Billing not configured'
            }), 503
        
        # Check if already set up
        if customer_data.get('stripe_customer_id'):
            return jsonify({
                'success': True,
                'message': 'Billing already set up',
                'stripe_customer_id': customer_data['stripe_customer_id']
            })
        
        # Create Stripe customer
        stripe_customer_data = stripe_manager.create_stripe_customer(customer_data)
        
        if not stripe_customer_data:
            return jsonify({
                'success': False,
                'error': 'Failed to create Stripe customer'
            }), 500
        
        # Update customer data with Stripe information
        customer_data.update({
            'stripe_customer_id': stripe_customer_data['stripe_customer_id'],
            'billing_email': stripe_customer_data['billing_email'],
            'billing_setup_at': datetime.now().isoformat(),
            'billing_status': 'active'
        })
        
        save_customer_data(session['customer_id'], customer_data)
        
        # Create initial subscription with current network pricing
        network_pricing = calculate_network_pricing()
        subscription_data = stripe_manager.create_subscription(
            stripe_customer_data['stripe_customer_id'], 
            network_pricing
        )
        
        if subscription_data:
            customer_data.update({
                'stripe_subscription_id': subscription_data['stripe_subscription_id'],
                'current_rate': subscription_data['current_rate'],
                'subscription_status': subscription_data['status']
            })
            save_customer_data(session['customer_id'], customer_data)
        
        return jsonify({
            'success': True,
            'message': 'Billing setup completed successfully',
            'stripe_customer_id': stripe_customer_data['stripe_customer_id'],
            'subscription_data': subscription_data
        })
        
    except Exception as e:
        logger.error(f"Error setting up billing: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@billing_bp.route('/payment-methods')
@enhanced_customer_required
def payment_methods():
    """Manage payment methods."""
    customer_data = get_customer_data(session['customer_id'])
    stripe_manager = get_stripe_manager()
    
    # Get billing summary if Stripe is configured
    billing_summary = None
    if stripe_manager.is_enabled() and customer_data.get('stripe_customer_id'):
        billing_summary = stripe_manager.get_customer_billing_summary(customer_data['stripe_customer_id'])
    
    return render_template('billing/payment_methods.html', 
                         customer=customer_data,
                         billing_summary=billing_summary,
                         stripe_enabled=stripe_manager.is_enabled())

@billing_bp.route('/invoices')
@enhanced_customer_required
def invoices():
    """View invoice history."""
    customer_data = get_customer_data(session['customer_id'])
    stripe_manager = get_stripe_manager()
    
    # Get billing summary and invoice history
    billing_data = None
    if stripe_manager.is_enabled() and customer_data.get('stripe_customer_id'):
        billing_data = stripe_manager.get_customer_billing_summary(customer_data['stripe_customer_id'])
    
    return render_template('billing/invoices.html',
                         customer=customer_data,
                         billing_data=billing_data,
                         stripe_enabled=stripe_manager.is_enabled())

@billing_bp.route('/portal')
@enhanced_customer_required
def billing_portal():
    """Redirect to Stripe customer portal."""
    try:
        customer_data = get_customer_data(session['customer_id'])
        stripe_customer_id = customer_data.get('stripe_customer_id')
        
        if not stripe_customer_id:
            flash('Billing not set up. Please set up billing first.', 'warning')
            return redirect(url_for('billing.payment_methods'))
        
        # For now, redirect to a billing management page
        # In production, you would create a Stripe billing portal session
        flash('Billing portal integration coming soon.', 'info')
        return redirect(url_for('billing.payment_methods'))
        
    except Exception as e:
        logger.error(f"Error accessing billing portal: {e}")
        flash('Error accessing billing portal.', 'error')
        return redirect(url_for('onboarding.dashboard'))

@billing_bp.route('/verify-payment', methods=['POST'])
@enhanced_customer_required
def verify_payment():
    """Process verification payments."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        user_count = data.get('user_count', 1)
        payment_intent_id = data.get('payment_intent_id')
        
        if user_count <= 0:
            return jsonify({'success': False, 'error': 'Invalid user count'}), 400
        
        stripe_manager = get_stripe_manager()
        customer_data = get_customer_data(session['customer_id'])
        stripe_customer_id = customer_data.get('stripe_customer_id')
        
        if not stripe_customer_id:
            return jsonify({'success': False, 'error': 'Billing not set up'}), 400
        
        # Charge verification fee
        charge_result = stripe_manager.charge_verification_fee(stripe_customer_id, user_count)
        
        if not charge_result:
            return jsonify({'success': False, 'error': 'Payment failed'}), 500
        
        # Log the billing event
        save_billing_event(session['customer_id'], {
            'type': 'verification_charge',
            'amount': charge_result['amount'],
            'user_count': user_count,
            'charge_id': charge_result['charge_id'],
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify({
            'success': True,
            'charge_result': charge_result,
            'message': f'Successfully charged ${charge_result["amount"]:.2f} for {user_count} user verification(s)'
        })
        
    except Exception as e:
        logger.error(f"Error processing verification payment: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@billing_bp.route('/create-payment-intent', methods=['POST'])
@enhanced_customer_required
def create_payment_intent():
    """Create a payment intent for verification fees."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        user_count = data.get('user_count', 1)
        
        if user_count <= 0:
            return jsonify({'success': False, 'error': 'Invalid user count'}), 400
        
        stripe_manager = get_stripe_manager()
        customer_data = get_customer_data(session['customer_id'])
        stripe_customer_id = customer_data.get('stripe_customer_id')
        
        if not stripe_customer_id:
            return jsonify({'success': False, 'error': 'Billing not set up'}), 400
        
        # Calculate amount
        verification_fee = 2.00  # $2.00 per user
        total_amount = verification_fee * user_count
        
        # Create payment intent
        payment_intent = stripe_manager.create_payment_intent(
            stripe_customer_id,
            total_amount,
            f"Lemma Network Verification - {user_count} user(s)",
            {
                'lemma_customer_id': session['customer_id'],
                'user_count': str(user_count),
                'domain': customer_data.get('domain', '')
            }
        )
        
        if not payment_intent:
            return jsonify({'success': False, 'error': 'Failed to create payment intent'}), 500
        
        return jsonify({
            'success': True,
            'payment_intent': payment_intent,
            'amount': total_amount,
            'user_count': user_count
        })
        
    except Exception as e:
        logger.error(f"Error creating payment intent: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@billing_bp.route('/create-identity-verification', methods=['POST'])
@enhanced_customer_required
def create_identity_verification():
    """Create a Stripe Identity verification session for human verification."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        user_id = data.get('user_id')
        return_url = data.get('return_url')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID is required'}), 400
        
        if not return_url:
            return_url = request.url_root.rstrip('/') + '/billing/identity-complete'
        
        stripe_manager = get_stripe_manager()
        customer_data = get_customer_data(session['customer_id'])
        stripe_customer_id = customer_data.get('stripe_customer_id')
        
        if not stripe_customer_id:
            return jsonify({'success': False, 'error': 'Billing not set up'}), 400
        
        # Create Identity verification session
        verification_session = stripe_manager.create_identity_verification_session(
            stripe_customer_id,
            user_id,
            customer_data.get('domain', ''),
            return_url
        )
        
        if not verification_session:
            return jsonify({'success': False, 'error': 'Failed to create verification session'}), 500
        
        # Log the verification session creation
        save_billing_event(session['customer_id'], {
            'type': 'identity_verification_created',
            'user_id': user_id,
            'verification_session_id': verification_session['verification_session_id'],
            'domain': customer_data.get('domain', ''),
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify({
            'success': True,
            'verification_session': verification_session,
            'message': 'Identity verification session created successfully'
        })
        
    except Exception as e:
        logger.error(f"Error creating identity verification session: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@billing_bp.route('/identity-verification/<session_id>/status', methods=['GET'])
@enhanced_customer_required
def get_identity_verification_status(session_id):
    """Get the status of an Identity verification session."""
    try:
        stripe_manager = get_stripe_manager()
        
        if not stripe_manager.is_enabled():
            return jsonify({
                'success': False,
                'error': 'Identity verification not available'
            }), 503
        
        # Get verification session details
        verification_session = stripe_manager.get_identity_verification_session(session_id)
        
        if not verification_session:
            return jsonify({'success': False, 'error': 'Verification session not found'}), 404
        
        return jsonify({
            'success': True,
            'verification_session': verification_session,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting identity verification status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@billing_bp.route('/identity-complete')
def identity_verification_complete():
    """Handle completion of Identity verification (return URL)."""
    try:
        # This is where users land after completing Identity verification
        # You can customize this page to show verification status or redirect appropriately
        
        verification_session_id = request.args.get('verification_session')
        
        if verification_session_id:
            # Log the completion
            logger.info(f"Identity verification completed for session {verification_session_id}")
            
            # You could check the verification status here and show appropriate messaging
            return render_template('billing/identity_complete.html', 
                                 session_id=verification_session_id)
        else:
            return render_template('billing/identity_complete.html')
            
    except Exception as e:
        logger.error(f"Error handling identity verification completion: {e}")
        return render_template('billing/identity_complete.html', 
                             error="An error occurred during verification")

@billing_bp.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks."""
    try:
        payload = request.get_data()
        signature = request.headers.get('Stripe-Signature')
        
        stripe_manager = get_stripe_manager()
        
        if not stripe_manager.verify_webhook_signature(payload, signature):
            logger.warning("Invalid Stripe webhook signature")
            return jsonify({'error': 'Invalid signature'}), 400
        
        # Parse event
        event = json.loads(payload)
        event_type = event['type']
        
        logger.info(f"Received Stripe webhook: {event_type}")
        
        # Handle different event types
        if event_type == 'payment_intent.succeeded':
            handle_payment_succeeded(event)
        elif event_type == 'payment_intent.payment_failed':
            handle_payment_failed(event)
        elif event_type == 'customer.subscription.updated':
            handle_subscription_updated(event)
        elif event_type == 'customer.subscription.deleted':
            handle_subscription_deleted(event)
        elif event_type == 'invoice.payment_succeeded':
            handle_invoice_payment_succeeded(event)
        elif event_type == 'invoice.payment_failed':
            handle_invoice_payment_failed(event)
        # Identity verification events
        elif event_type == 'identity.verification_session.verified':
            handle_identity_verified(event)
        elif event_type == 'identity.verification_session.requires_input':
            handle_identity_requires_input(event)
        elif event_type == 'identity.verification_session.canceled':
            handle_identity_canceled(event)
        elif event_type == 'identity.verification_session.processing':
            handle_identity_processing(event)
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Error handling Stripe webhook: {e}")
        return jsonify({'error': str(e)}), 500

def handle_payment_succeeded(event):
    """Handle successful payment events."""
    try:
        payment_intent = event['data']['object']
        customer_id = payment_intent.get('customer')
        metadata = payment_intent.get('metadata', {})
        lemma_customer_id = metadata.get('lemma_customer_id')
        
        if lemma_customer_id:
            save_billing_event(lemma_customer_id, {
                'type': 'payment_succeeded',
                'stripe_payment_intent_id': payment_intent['id'],
                'amount': payment_intent['amount'] / 100,  # Convert from cents
                'user_count': metadata.get('user_count', '1'),
                'timestamp': datetime.now().isoformat()
            })
            
        logger.info(f"Payment succeeded for customer {customer_id}: ${payment_intent['amount']/100:.2f}")
        
    except Exception as e:
        logger.error(f"Error handling payment succeeded: {e}")

def handle_payment_failed(event):
    """Handle failed payment events."""
    try:
        payment_intent = event['data']['object']
        customer_id = payment_intent.get('customer')
        metadata = payment_intent.get('metadata', {})
        lemma_customer_id = metadata.get('lemma_customer_id')
        
        if lemma_customer_id:
            save_billing_event(lemma_customer_id, {
                'type': 'payment_failed',
                'stripe_payment_intent_id': payment_intent['id'],
                'amount': payment_intent['amount'] / 100,
                'failure_reason': payment_intent.get('last_payment_error', {}).get('message', 'Unknown'),
                'timestamp': datetime.now().isoformat()
            })
            
        logger.warning(f"Payment failed for customer {customer_id}: ${payment_intent['amount']/100:.2f}")
        
    except Exception as e:
        logger.error(f"Error handling payment failed: {e}")

def handle_subscription_updated(event):
    """Handle subscription update events."""
    try:
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        
        # Find Lemma customer by Stripe customer ID
        lemma_customer_id = find_lemma_customer_by_stripe_id(customer_id)
        
        if lemma_customer_id:
            customer_data = get_customer_data(lemma_customer_id)
            if customer_data:
                customer_data.update({
                    'subscription_status': subscription['status'],
                    'current_period_start': datetime.fromtimestamp(subscription['current_period_start']).isoformat(),
                    'current_period_end': datetime.fromtimestamp(subscription['current_period_end']).isoformat(),
                    'subscription_updated_at': datetime.now().isoformat()
                })
                save_customer_data(lemma_customer_id, customer_data)
        
        logger.info(f"Subscription updated for customer {customer_id}")
        
    except Exception as e:
        logger.error(f"Error handling subscription updated: {e}")

def handle_subscription_deleted(event):
    """Handle subscription deletion events."""
    try:
        subscription = event['data']['object']
        customer_id = subscription.get('customer')
        
        # Find Lemma customer by Stripe customer ID
        lemma_customer_id = find_lemma_customer_by_stripe_id(customer_id)
        
        if lemma_customer_id:
            customer_data = get_customer_data(lemma_customer_id)
            if customer_data:
                customer_data.update({
                    'subscription_status': 'canceled',
                    'subscription_canceled_at': datetime.now().isoformat()
                })
                save_customer_data(lemma_customer_id, customer_data)
        
        logger.info(f"Subscription canceled for customer {customer_id}")
        
    except Exception as e:
        logger.error(f"Error handling subscription deleted: {e}")

def handle_invoice_payment_succeeded(event):
    """Handle successful invoice payments."""
    try:
        invoice = event['data']['object']
        customer_id = invoice.get('customer')
        
        logger.info(f"Invoice payment succeeded for customer {customer_id}: ${invoice['amount_paid']/100:.2f}")
        
    except Exception as e:
        logger.error(f"Error handling invoice payment succeeded: {e}")

def handle_invoice_payment_failed(event):
    """Handle failed invoice payments."""
    try:
        invoice = event['data']['object']
        customer_id = invoice.get('customer')
        
        logger.warning(f"Invoice payment failed for customer {customer_id}: ${invoice['amount_due']/100:.2f}")
        
    except Exception as e:
        logger.error(f"Error handling invoice payment failed: {e}")

def handle_identity_verified(event):
    """Handle successful identity verification and charge verification fee."""
    try:
        verification_session = event['data']['object']
        customer_id = verification_session.get('customer')
        metadata = verification_session.get('metadata', {})
        
        # Extract Lemma-specific metadata
        lemma_customer_id = metadata.get('lemma_customer_id')
        lemma_user_id = metadata.get('lemma_user_id') 
        domain = metadata.get('domain')
        
        logger.info(f"Identity verified for Stripe customer {customer_id}, Lemma customer {lemma_customer_id}")
        
        if lemma_customer_id and customer_id:
            # Automatically charge verification fee
            stripe_manager = get_stripe_manager()
            charge_result = stripe_manager.charge_verification_fee(customer_id, 1)
            
            if charge_result:
                # Log successful verification and charge
                save_billing_event(lemma_customer_id, {
                    'type': 'identity_verified_and_charged',
                    'lemma_user_id': lemma_user_id,
                    'stripe_customer_id': customer_id,
                    'verification_session_id': verification_session['id'],
                    'charge_id': charge_result['charge_id'],
                    'amount': charge_result['amount'],
                    'fee_per_user': charge_result['fee_per_user'],
                    'domain': domain,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.info(f"Successfully charged ${charge_result['amount']:.2f} verification fee for user {lemma_user_id}")
                
                # Automatically issue Lemma credential for verified human
                try:
                    credential_service = get_credential_service()
                    if credential_service:
                        # Issue the credential for the verified user
                        credential = credential_service.issue_credential(lemma_user_id)
                        
                        # Log successful credential issuance
                        save_billing_event(lemma_customer_id, {
                            'type': 'credential_issued',
                            'lemma_user_id': lemma_user_id,
                            'credential_id': credential['id'],
                            'issued_at': credential['issuanceDate'],
                            'verification_session_id': verification_session['id'],
                            'domain': domain,
                            'timestamp': datetime.now().isoformat()
                        })
                        
                        logger.info(f"Successfully issued Lemma credential {credential['id']} for verified user {lemma_user_id}")
                        
                        # Update the original billing event to include credential info
                        save_billing_event(lemma_customer_id, {
                            'type': 'verification_complete',
                            'lemma_user_id': lemma_user_id,
                            'stripe_customer_id': customer_id,
                            'verification_session_id': verification_session['id'],
                            'charge_id': charge_result['charge_id'],
                            'credential_id': credential['id'],
                            'amount_charged': charge_result['amount'],
                            'status': 'complete',
                            'message': 'Human verification complete - fee charged and credential issued',
                            'domain': domain,
                            'timestamp': datetime.now().isoformat()
                        })
                        
                    else:
                        logger.error("Credential service not available - verification fee charged but credential not issued")
                        save_billing_event(lemma_customer_id, {
                            'type': 'credential_issuance_failed',
                            'lemma_user_id': lemma_user_id,
                            'error': 'Credential service not available',
                            'verification_session_id': verification_session['id'],
                            'charge_id': charge_result['charge_id'],
                            'timestamp': datetime.now().isoformat()
                        })
                        
                except Exception as credential_error:
                    logger.error(f"Failed to issue credential for verified user {lemma_user_id}: {credential_error}")
                    save_billing_event(lemma_customer_id, {
                        'type': 'credential_issuance_failed',
                        'lemma_user_id': lemma_user_id,
                        'error': str(credential_error),
                        'verification_session_id': verification_session['id'],
                        'charge_id': charge_result['charge_id'],
                        'timestamp': datetime.now().isoformat()
                    })
            else:
                # Log verification without charge (billing setup issue)
                save_billing_event(lemma_customer_id, {
                    'type': 'identity_verified_charge_failed',
                    'lemma_user_id': lemma_user_id,
                    'stripe_customer_id': customer_id,
                    'verification_session_id': verification_session['id'],
                    'error': 'Failed to charge verification fee',
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.warning(f"Identity verified but failed to charge verification fee for user {lemma_user_id}")
        else:
            # Log verification event without billing integration
            save_billing_event('unknown', {
                'type': 'identity_verified_no_customer_mapping',
                'stripe_customer_id': customer_id,
                'verification_session_id': verification_session['id'],
                'metadata': metadata,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.warning(f"Identity verified but no Lemma customer mapping found for Stripe customer {customer_id}")
            
    except Exception as e:
        logger.error(f"Error handling identity verified: {e}")
        # Log the error event
        try:
            save_billing_event('error', {
                'type': 'identity_verified_error',
                'error': str(e),
                'event_id': event.get('id'),
                'timestamp': datetime.now().isoformat()
            })
        except:
            pass

def handle_identity_requires_input(event):
    """Handle identity verification requiring additional input."""
    try:
        verification_session = event['data']['object']
        customer_id = verification_session.get('customer')
        metadata = verification_session.get('metadata', {})
        
        # Extract Lemma-specific metadata
        lemma_customer_id = metadata.get('lemma_customer_id')
        lemma_user_id = metadata.get('lemma_user_id')
        domain = metadata.get('domain')
        
        logger.info(f"Identity verification requires input for user {lemma_user_id} from domain {domain}")
        
        if lemma_customer_id:
            save_billing_event(lemma_customer_id, {
                'type': 'identity_requires_input',
                'lemma_user_id': lemma_user_id,
                'stripe_customer_id': customer_id,
                'verification_session_id': verification_session['id'],
                'status': verification_session['status'],
                'domain': domain,
                'last_error': verification_session.get('last_error'),
                'timestamp': datetime.now().isoformat()
            })
            
            # TODO: Notify user about additional requirements
            # This could trigger an email or dashboard notification
            # Example: notify_user_additional_input_required(lemma_user_id, verification_session)
            
        logger.info(f"Identity verification requires additional input for customer {customer_id}")
        
    except Exception as e:
        logger.error(f"Error handling identity requires input: {e}")

def handle_identity_canceled(event):
    """Handle canceled identity verification."""
    try:
        verification_session = event['data']['object']
        customer_id = verification_session.get('customer')
        metadata = verification_session.get('metadata', {})
        
        # Extract Lemma-specific metadata
        lemma_customer_id = metadata.get('lemma_customer_id')
        lemma_user_id = metadata.get('lemma_user_id')
        domain = metadata.get('domain')
        
        logger.info(f"Identity verification canceled for user {lemma_user_id} from domain {domain}")
        
        if lemma_customer_id:
            save_billing_event(lemma_customer_id, {
                'type': 'identity_verification_canceled',
                'lemma_user_id': lemma_user_id,
                'stripe_customer_id': customer_id,
                'verification_session_id': verification_session['id'],
                'status': verification_session['status'],
                'domain': domain,
                'cancellation_reason': verification_session.get('last_error', {}).get('reason'),
                'timestamp': datetime.now().isoformat()
            })
            
            # TODO: Handle cancellation cleanup
            # This might involve cleaning up any temporary data or notifying the user
            # Example: handle_verification_cancellation(lemma_user_id, lemma_customer_id)
            
        logger.warning(f"Identity verification canceled for customer {customer_id}")
        
    except Exception as e:
        logger.error(f"Error handling identity canceled: {e}")

def handle_identity_processing(event):
    """Handle identity verification in processing state."""
    try:
        verification_session = event['data']['object']
        customer_id = verification_session.get('customer')
        metadata = verification_session.get('metadata', {})
        
        # Extract Lemma-specific metadata
        lemma_customer_id = metadata.get('lemma_customer_id')
        lemma_user_id = metadata.get('lemma_user_id')
        domain = metadata.get('domain')
        
        logger.info(f"Identity verification processing for user {lemma_user_id} from domain {domain}")
        
        if lemma_customer_id:
            save_billing_event(lemma_customer_id, {
                'type': 'identity_processing',
                'lemma_user_id': lemma_user_id,
                'stripe_customer_id': customer_id,
                'verification_session_id': verification_session['id'],
                'status': verification_session['status'],
                'domain': domain,
                'timestamp': datetime.now().isoformat()
            })
            
            # TODO: Update user status to "processing"
            # This could update the user's verification status in your system
            # Example: update_user_verification_status(lemma_user_id, 'processing')
            
        logger.info(f"Identity verification processing for customer {customer_id}")
        
    except Exception as e:
        logger.error(f"Error handling identity processing: {e}")

def save_billing_event(customer_id: str, event_data: dict):
    """Save billing event to customer's billing history."""
    try:
        billing_dir = os.path.join(current_app.config['STORAGE_DIR'], 'billing')
        os.makedirs(billing_dir, exist_ok=True)
        
        billing_file = os.path.join(billing_dir, f'{customer_id}_billing.json')
        
        # Load existing billing data
        if os.path.exists(billing_file):
            with open(billing_file, 'r') as f:
                billing_data = json.load(f)
        else:
            billing_data = {
                'customer_id': customer_id,
                'events': [],
                'created_at': datetime.now().isoformat()
            }
        
        # Add new event
        billing_data['events'].append(event_data)
        billing_data['last_updated'] = datetime.now().isoformat()
        
        # Save updated data
        with open(billing_file, 'w') as f:
            json.dump(billing_data, f, indent=2)
            
    except Exception as e:
        logger.error(f"Error saving billing event: {e}")

def find_lemma_customer_by_stripe_id(stripe_customer_id: str) -> Optional[str]:
    """Find Lemma customer ID by Stripe customer ID."""
    try:
        customers_dir = os.path.join(current_app.config['STORAGE_DIR'], 'customers')
        
        if not os.path.exists(customers_dir):
            return None
        
        for customer_file in os.listdir(customers_dir):
            if customer_file.endswith('.json'):
                try:
                    with open(os.path.join(customers_dir, customer_file), 'r') as f:
                        customer_data = json.load(f)
                        if customer_data.get('stripe_customer_id') == stripe_customer_id:
                            return customer_data.get('customer_id')
                except Exception as e:
                    logger.warning(f"Error reading customer file {customer_file}: {e}")
        
        return None
        
    except Exception as e:
        logger.error(f"Error finding customer by Stripe ID: {e}")
        return None

@billing_bp.route('/test-credential-issuance', methods=['POST'])
@enhanced_customer_required  
def test_credential_issuance():
    """Test endpoint to verify credential issuance integration (development only)."""
    try:
        data = request.get_json()
        if not data or not data.get('user_id'):
            return jsonify({'success': False, 'error': 'user_id required'}), 400
        
        user_id = data['user_id']
        
        # Test the credential service integration
        credential_service = get_credential_service()
        if not credential_service:
            return jsonify({
                'success': False, 
                'error': 'Credential service not available'
            }), 503
        
        # Issue a test credential
        credential = credential_service.issue_credential(user_id)
        
        # Log the test event
        save_billing_event(session['customer_id'], {
            'type': 'test_credential_issued',
            'user_id': user_id,
            'credential_id': credential['id'],
            'test_mode': True,
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify({
            'success': True,
            'message': 'Credential issuance test successful',
            'credential_id': credential['id'],
            'issued_at': credential['issuanceDate'],
            'user_id': user_id,
            'integration_status': 'working'
        })
        
    except Exception as e:
        logger.error(f"Test credential issuance failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'integration_status': 'failed'
        }), 500 