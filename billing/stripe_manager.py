"""
Stripe manager for Lemma.id platform
"""

import stripe
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def init_stripe():
    """
    Initialize Stripe with API key
    """
    try:
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_placeholder')
        logger.info("✅ Stripe initialized")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Stripe initialization failed: {e}")
        return False

class StripeManager:
    """
    Manages Stripe Identity verification sessions for federated identity network
    """
    
    def __init__(self):
        """Initialize Stripe manager"""
        self.initialized = False
        try:
            # Get Stripe secret key from environment
            stripe_key = os.getenv('STRIPE_SECRET_KEY')
            
            if stripe_key and stripe_key != 'sk_test_placeholder' and not stripe_key.startswith('sk_test_'):
                stripe.api_key = stripe_key
                self.initialized = True
                logger.info("✅ Stripe Identity manager initialized with live key")
            elif stripe_key and stripe_key.startswith('sk_test_'):
                stripe.api_key = stripe_key
                self.initialized = True
                logger.info("✅ Stripe Identity manager initialized with test key")
            else:
                logger.warning("⚠️ No valid Stripe key found - using demo mode")
                self.initialized = False
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Stripe manager: {e}")
            self.initialized = False
    
    def create_identity_verification_session(self, user_id: str, return_url: str, inline_mode: bool = False) -> Dict[str, Any]:
        """
        Create a Stripe Identity verification session
        
        Args:
            user_id: Unique user identifier
            return_url: URL to redirect after verification
            inline_mode: Whether to use inline mode (not supported in this implementation)
            
        Returns:
            Dict with session details or error
        """
        if not self.initialized:
            return {
                'success': False,
                'error': 'stripe_not_configured',
                'message': 'Stripe Identity not properly configured'
            }
        
        try:
            # Create Stripe Identity verification session
            session = stripe.identity.VerificationSession.create(
                type='document',
                metadata={
                    'user_id': user_id,
                    'lemma_verification': 'true',
                    'federated_identity': 'true'
                },
                return_url=return_url,
                options={
                    'document': {
                        'allowed_types': ['driving_license', 'passport', 'id_card'],
                        'require_id_number': True,
                        'require_live_capture': True,
                        'require_matching_selfie': True,
                    }
                }
            )
            
            logger.info(f"✅ Created Stripe Identity session: {session.id}")
            
            return {
                'success': True,
                'session_id': session.id,
                'client_secret': session.client_secret,
                'url': session.url,
                'status': session.status
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"❌ Stripe Identity session creation failed: {e}")
            return {
                'success': False,
                'error': 'stripe_session_failed',
                'message': str(e)
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error creating Stripe session: {e}")
            return {
                'success': False,
                'error': 'session_creation_failed',
                'message': str(e)
            }
    
    def get_identity_verification_session(self, session_id: str) -> Dict[str, Any]:
        """
        Get the status of a Stripe Identity verification session
        
        Args:
            session_id: Stripe session ID
            
        Returns:
            Dict with session status and verification results
        """
        if not self.initialized:
            return {
                'success': False,
                'error': 'stripe_not_configured',
                'message': 'Stripe Identity not properly configured'
            }
        
        try:
            # Retrieve the verification session
            session = stripe.identity.VerificationSession.retrieve(session_id)
            
            logger.info(f"📋 Retrieved Stripe Identity session {session_id}: status={session.status}")
            
            # Extract verification results
            verification_result = {
                'success': True,
                'session_id': session.id,
                'status': session.status,
                'verified': session.status == 'verified',
                'created': session.created,
                'metadata': session.metadata
            }
            
            # Add verification details if available
            if hasattr(session, 'verified_outputs') and session.verified_outputs:
                try:
                    verification_result['verified_outputs'] = {
                        'id_number': getattr(session.verified_outputs, 'id_number', None),
                        'dob': getattr(session.verified_outputs, 'dob', None),
                        'name': getattr(session.verified_outputs, 'name', None),
                        'address': getattr(session.verified_outputs, 'address', None)
                    }
                except AttributeError as e:
                    logger.warning(f"⚠️ Could not access verified_outputs: {e}")
                    verification_result['verified_outputs'] = None
            
            # Add document checks if available
            if hasattr(session, 'last_verification_report') and session.last_verification_report:
                try:
                    report = session.last_verification_report
                    document = getattr(report, 'document', {}) or {}
                    selfie = getattr(report, 'selfie', {}) or {}
                    verification_result['document_checks'] = {
                        'document_type': document.get('type') if isinstance(document, dict) else None,
                        'document_check': document.get('status') == 'verified' if isinstance(document, dict) else False,
                        'selfie_check': selfie.get('status') == 'verified' if isinstance(selfie, dict) else False
                    }
                except (AttributeError, TypeError) as e:
                    logger.warning(f"⚠️ Could not access verification report: {e}")
                    verification_result['document_checks'] = None
            
            return verification_result
            
        except stripe.error.StripeError as e:
            logger.error(f"❌ Failed to retrieve Stripe Identity session {session_id}: {e}")
            return {
                'success': False,
                'error': 'stripe_retrieval_failed',
                'message': str(e)
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error retrieving Stripe session: {e}")
            return {
                'success': False,
                'error': 'session_retrieval_failed',
                'message': str(e)
            }

    def _stripe_api_key_for_identity_sensitive(self) -> Optional[str]:
        """Prefer restricted Identity key for DOB / document number fields."""
        restricted = os.getenv('STRIPE_IDENTITY_RESTRICTED_KEY') or os.getenv('STRIPE_RESTRICTED_KEY')
        if restricted and restricted.startswith('rk_'):
            return restricted
        stripe_key = os.getenv('STRIPE_SECRET_KEY')
        if stripe_key and stripe_key not in ('sk_test_placeholder',):
            return stripe_key
        return None

    def retrieve_identity_root_material(self, session_id: str):
        """
        Retrieve a verified VerificationSession with fields required for document-root v1.

        Returns the Stripe VerificationSession object or None on failure.
        """
        api_key = self._stripe_api_key_for_identity_sensitive()
        if not api_key:
            logger.error("No Stripe API key for identity root material retrieval")
            return None

        expand = [
            'verified_outputs.dob',
            'verified_outputs.id_number',
            'last_verification_report',
            'last_verification_report.document.number',
        ]
        try:
            session = stripe.identity.VerificationSession.retrieve(
                session_id,
                expand=expand,
                api_key=api_key,
            )
            logger.info(
                "Retrieved identity root material for %s status=%s",
                session_id,
                getattr(session, 'status', None),
            )
            return session
        except stripe.error.StripeError as e:
            logger.error("Failed to retrieve identity root material for %s: %s", session_id, e)
            return None
        except Exception as e:
            logger.error("Unexpected error retrieving identity root material: %s", e)
            return None