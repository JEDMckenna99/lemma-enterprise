"""
Stripe manager for Lemma.id platform
"""

import stripe
import os
import logging

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