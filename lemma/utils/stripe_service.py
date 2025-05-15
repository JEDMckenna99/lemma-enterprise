"""
Stripe Identity integration for the Lemma Human Verification System.
Provides utilities for identity verification through Stripe.
"""
import os
import logging
import stripe
from typing import Dict, Any, Optional
from flask import current_app, url_for

# Set up logging
logger = logging.getLogger(__name__)

def init_stripe():
    """Initialize the Stripe API client."""
    stripe_api_key = os.environ.get('STRIPE_API_KEY') or current_app.config.get('STRIPE_API_KEY')
    if not stripe_api_key:
        logger.warning("Stripe API key not found in environment or configuration")
        return False
    
    stripe.api_key = stripe_api_key
    return True

def create_verification_session(user_id: str, return_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a Stripe Identity verification session.
    
    Args:
        user_id: The ID of the user to verify
        return_url: Optional URL to redirect to after verification
        
    Returns:
        Dict: The created verification session
    """
    try:
        # Initialize Stripe if not already initialized
        if not getattr(stripe, 'api_key', None):
            if not init_stripe():
                return {"error": "Stripe API key not configured"}
        
        # Use the provided return URL or generate one
        if not return_url:
            # Generate a return URL if not provided (needs to be in a request context)
            try:
                return_url = url_for('main.verification_callback', user_id=user_id, _external=True)
            except RuntimeError:
                # Not in a request context, use a placeholder
                return_url = f"/verification-callback?user_id={user_id}"
        
        # Create the verification session with Stripe
        verification_session = stripe.identity.VerificationSession.create(
            type="document",
            metadata={
                "user_id": user_id,
                "service": "lemma"
            },
            options={
                "document": {
                    "allowed_types": ["driving_license", "id_card", "passport"],
                    "require_id_number": True,
                    "require_matching_selfie": True
                }
            },
            return_url=return_url
        )
        
        logger.info(f"Created Stripe verification session for user {user_id}: {verification_session.id}")
        return verification_session
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating verification session: {str(e)}")
        return {"error": str(e)}
    
    except Exception as e:
        logger.error(f"Error creating verification session: {str(e)}")
        return {"error": str(e)}

def check_verification_status(session_id: str) -> Dict[str, Any]:
    """
    Check the status of a verification session.
    
    Args:
        session_id: The ID of the verification session
        
    Returns:
        Dict: The status of the verification session
    """
    try:
        # Initialize Stripe if not already initialized
        if not getattr(stripe, 'api_key', None):
            if not init_stripe():
                return {"error": "Stripe API key not configured"}
        
        # Retrieve the verification session
        verification_session = stripe.identity.VerificationSession.retrieve(session_id)
        
        # Get the verification report if available
        verification_report = None
        if verification_session.status == "verified" and verification_session.last_verification_report:
            verification_report = stripe.identity.VerificationReport.retrieve(
                verification_session.last_verification_report
            )
        
        return {
            "id": verification_session.id,
            "status": verification_session.status,
            "user_id": verification_session.metadata.get("user_id"),
            "verified": verification_session.status == "verified",
            "report": verification_report
        }
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error checking verification status: {str(e)}")
        return {"error": str(e)}
    
    except Exception as e:
        logger.error(f"Error checking verification status: {str(e)}")
        return {"error": str(e)}

def get_verification_client_secret(session_id: str) -> str:
    """
    Get the client secret for a verification session.
    
    Args:
        session_id: The ID of the verification session
        
    Returns:
        str: The client secret
    """
    try:
        # Initialize Stripe if not already initialized
        if not getattr(stripe, 'api_key', None):
            if not init_stripe():
                return ""
        
        # Retrieve the verification session
        verification_session = stripe.identity.VerificationSession.retrieve(session_id)
        return verification_session.client_secret
    
    except Exception as e:
        logger.error(f"Error getting verification client secret: {str(e)}")
        return "" 