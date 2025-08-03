"""
Stripe Manager - Salvaged from Old Build
========================================
Handles Stripe Identity verification for high-assurance human verification.
Enhanced for lemma-rebuild with simplified integration.
"""

import os
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Import Stripe (optional dependency)
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    logger.warning("Stripe library not available - Identity verification disabled")

@dataclass
class StripeConfig:
    """Stripe configuration"""
    secret_key: str
    publishable_key: str
    webhook_secret: str
    api_version: str = "2023-10-16"

class StripeManager:
    """
    SALVAGED: Stripe Identity verification manager
    Handles Stripe Identity sessions for high-assurance human verification
    """
    
    def __init__(self, config: Optional[StripeConfig] = None):
        self.config = config or self._load_config()
        self.initialized = False
        
        if STRIPE_AVAILABLE and self.config.secret_key:
            try:
                stripe.api_key = self.config.secret_key
                stripe.api_version = self.config.api_version
                self.initialized = True
                logger.info("✅ Stripe manager initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Stripe: {e}")
        else:
            logger.warning("⚠️ Stripe not configured - Identity verification unavailable")
    
    def _load_config(self) -> StripeConfig:
        """Load Stripe configuration from environment"""
        return StripeConfig(
            secret_key=os.getenv('STRIPE_SECRET_KEY', ''),
            publishable_key=os.getenv('STRIPE_PUBLISHABLE_KEY', ''),
            webhook_secret=os.getenv('STRIPE_WEBHOOK_SECRET', ''),
            api_version=os.getenv('STRIPE_API_VERSION', '2023-10-16')
        )
    
    def create_identity_verification_session(
        self, 
        user_id: str, 
        return_url: str,
        inline_mode: bool = True
    ) -> Dict[str, Any]:
        """
        SALVAGED: Create Stripe Identity verification session
        Creates a new identity verification session for inline or redirect flow
        """
        if not self.initialized:
            return {
                'success': False,
                'error': 'stripe_not_initialized',
                'message': 'Stripe Identity verification not available'
            }
        
        try:
            # Create identity verification session
            session = stripe.identity.VerificationSession.create(
                type='document',
                metadata={
                    'user_id': user_id,
                    'created_by': 'lemma_bot_shield',
                    'inline_mode': str(inline_mode),
                    'created_at': str(int(time.time()))
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
            
            logger.info(f"✅ Created Stripe Identity session {session.id} for user {user_id}")
            
            return {
                'success': True,
                'session_id': session.id,
                'client_secret': session.client_secret,
                'url': session.url,
                'status': session.status,
                'user_id': user_id,
                'inline_mode': inline_mode,
                'created_at': time.time()
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"❌ Stripe Identity session creation failed: {e}")
            return {
                'success': False,
                'error': 'stripe_api_error',
                'message': f'Failed to create identity verification session: {str(e)}',
                'details': {
                    'error_type': type(e).__name__,
                    'error_code': getattr(e, 'code', None),
                    'error_param': getattr(e, 'param', None)
                }
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error creating Stripe Identity session: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': f'Unexpected error: {str(e)}'
            }
    
    def get_identity_verification_session(self, session_id: str) -> Dict[str, Any]:
        """
        SALVAGED: Get Stripe Identity verification session status
        Retrieves the current status of a verification session
        """
        if not self.initialized:
            return {
                'success': False,
                'error': 'stripe_not_initialized',
                'message': 'Stripe Identity verification not available'
            }
        
        try:
            session = stripe.identity.VerificationSession.retrieve(session_id)
            
            # Extract verification details
            verification_data = {
                'session_id': session.id,
                'status': session.status,
                'created': session.created,
                'user_id': session.metadata.get('user_id'),
                'inline_mode': session.metadata.get('inline_mode') == 'true'
            }
            
            # Add verification report if available
            if session.last_verification_report:
                report = session.last_verification_report
                
                # Handle case where report is just a string ID vs full object
                if isinstance(report, str):
                    # If it's just an ID string, retrieve the full report
                    try:
                        report = stripe.identity.VerificationReport.retrieve(report)
                    except Exception as e:
                        logger.warning(f"⚠️ Could not retrieve verification report {report}: {e}")
                        report = None
                
                if report and hasattr(report, 'id'):
                    verification_data['verification_report'] = {
                        'id': report.id,
                        'type': getattr(report, 'type', 'unknown'),
                        'status': getattr(report, 'status', 'unknown'),
                        'created': getattr(report, 'created', None)
                    }
                    
                    # Add document details if available
                    if hasattr(report, 'document') and report.document:
                        verification_data['document'] = {
                            'status': getattr(report.document, 'status', 'unknown'),
                            'type': getattr(report.document, 'type', 'unknown')
                        }
            
            logger.info(f"✅ Retrieved Stripe Identity session {session_id} with status {session.status}")
            
            return {
                'success': True,
                'status': session.status,
                'verification_data': verification_data
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"❌ Failed to retrieve Stripe Identity session {session_id}: {e}")
            return {
                'success': False,
                'error': 'stripe_api_error',
                'message': f'Failed to retrieve verification session: {str(e)}'
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error retrieving Stripe Identity session: {e}")
            return {
                'success': False,
                'error': 'unexpected_error',
                'message': f'Unexpected error: {str(e)}'
            }
    
    def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        SALVAGED: Handle Stripe webhook events
        Processes Stripe webhook events for identity verification
        """
        if not self.initialized or not self.config.webhook_secret:
            return {
                'success': False,
                'error': 'webhook_not_configured',
                'message': 'Stripe webhook handling not configured'
            }
        
        try:
            # Verify webhook signature
            event = stripe.Webhook.construct_event(
                payload, 
                signature, 
                self.config.webhook_secret
            )
            
            logger.info(f"📨 Received Stripe webhook event: {event['type']}")
            
            # Handle identity verification events
            if event['type'] == 'identity.verification_session.verified':
                return self._handle_verification_completed(event['data']['object'])
            elif event['type'] == 'identity.verification_session.requires_input':
                return self._handle_verification_requires_input(event['data']['object'])
            elif event['type'] == 'identity.verification_session.processing':
                return self._handle_verification_processing(event['data']['object'])
            else:
                logger.info(f"ℹ️ Unhandled webhook event type: {event['type']}")
                return {
                    'success': True,
                    'message': f'Event {event["type"]} received but not handled'
                }
            
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"❌ Stripe webhook signature verification failed: {e}")
            return {
                'success': False,
                'error': 'invalid_signature',
                'message': 'Webhook signature verification failed'
            }
        except Exception as e:
            logger.error(f"❌ Webhook handling error: {e}")
            return {
                'success': False,
                'error': 'webhook_error',
                'message': f'Webhook handling failed: {str(e)}'
            }
    
    def _handle_verification_completed(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle completed verification"""
        session_id = session_data['id']
        user_id = session_data['metadata'].get('user_id')
        
        logger.info(f"✅ Identity verification completed for session {session_id}, user {user_id}")
        
        # TODO: Store verification result in your database
        # TODO: Create verified credential for user
        # TODO: Send notification to user
        
        return {
            'success': True,
            'event_type': 'verification_completed',
            'session_id': session_id,
            'user_id': user_id
        }
    
    def _handle_verification_requires_input(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle verification that requires additional input"""
        session_id = session_data['id']
        user_id = session_data['metadata'].get('user_id')
        
        logger.info(f"⚠️ Identity verification requires input for session {session_id}, user {user_id}")
        
        return {
            'success': True,
            'event_type': 'verification_requires_input',
            'session_id': session_id,
            'user_id': user_id
        }
    
    def _handle_verification_processing(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle verification in processing state"""
        session_id = session_data['id']
        user_id = session_data['metadata'].get('user_id')
        
        logger.info(f"🔄 Identity verification processing for session {session_id}, user {user_id}")
        
        return {
            'success': True,
            'event_type': 'verification_processing',
            'session_id': session_id,
            'user_id': user_id
        }
    
    def is_available(self) -> bool:
        """Check if Stripe Identity verification is available"""
        return self.initialized and STRIPE_AVAILABLE
    
    def get_publishable_key(self) -> Optional[str]:
        """Get Stripe publishable key for client-side integration"""
        return self.config.publishable_key if self.initialized else None

# Global instance
_stripe_manager = None

def get_stripe_manager() -> StripeManager:
    """Get global Stripe manager instance"""
    global _stripe_manager
    if _stripe_manager is None:
        _stripe_manager = StripeManager()
    return _stripe_manager

def init_stripe(config: Optional[StripeConfig] = None):
    """Initialize Stripe manager"""
    global _stripe_manager
    _stripe_manager = StripeManager(config)
    
    if _stripe_manager.is_available():
        logger.info("✅ Stripe Identity verification available")
    else:
        logger.warning("⚠️ Stripe Identity verification not available")

# Utility functions
def create_customer_for_billing(email: str, name: str = None) -> Dict[str, Any]:
    """
    SALVAGED: Create Stripe customer for billing
    Creates a Stripe customer for billing purposes
    """
    stripe_manager = get_stripe_manager()
    
    if not stripe_manager.is_available():
        return {
            'success': False,
            'error': 'stripe_not_available',
            'message': 'Stripe not configured'
        }
    
    try:
        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata={
                'created_by': 'lemma_bot_shield',
                'created_at': str(int(time.time()))
            }
        )
        
        logger.info(f"✅ Created Stripe customer {customer.id} for {email}")
        
        return {
            'success': True,
            'customer_id': customer.id,
            'email': email,
            'name': name
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"❌ Failed to create Stripe customer: {e}")
        return {
            'success': False,
            'error': 'stripe_api_error',
            'message': f'Failed to create customer: {str(e)}'
        }

def get_verification_pricing() -> Dict[str, Any]:
    """
    Get pricing information for identity verification
    """
    return {
        'stripe_identity': {
            'price_per_verification': 2.00,  # $2.00 per verification
            'currency': 'usd',
            'description': 'High-assurance identity verification via Stripe Identity'
        },
        'network_membership': {
            'price_per_user_per_month': 0.10,  # $0.10 per user per month
            'currency': 'usd',
            'description': 'Ongoing network membership after verification'
        }
    } 