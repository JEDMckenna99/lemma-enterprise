"""
Usage logging for billing and MAU tracking
"""

import hashlib
import hmac
from datetime import datetime
from typing import Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Secret key for HMAC (should be from config in production)
import os

def _get_billing_hmac_secret():
    """Get billing HMAC secret from environment"""
    from api.config import get_billing_hmac_secret
    return get_billing_hmac_secret()

def log_permission_operation(site_id: str, operation_type: str, count: int = 1, user_did: Optional[str] = None):
    """
    Log permission operation for billing tracking
    
    Args:
        site_id: Site identifier
        operation_type: Type of operation (site_registration, permission_granted, access_verification, etc.)
        count: Number of operations (default 1)
        user_did: User DID for MAU tracking (optional)
    """
    try:
        timestamp = datetime.utcnow()
        
        # Create privacy-preserving user hash for MAU tracking
        user_hash = None
        if user_did:
            # Use HMAC-SHA256 for privacy-preserving user identification
            user_hash = hmac.new(
                _get_billing_hmac_secret().encode(),
                f"{site_id}:{user_did}".encode(),
                hashlib.sha256
            ).hexdigest()[:16]  # First 16 chars for storage efficiency
        
        # Log the operation
        log_entry = {
            'timestamp': timestamp.isoformat(),
            'site_id': site_id,
            'operation_type': operation_type,
            'count': count,
            'user_hash': user_hash
        }
        
        logger.info(f"Billing operation logged: {log_entry}")
        
        # TODO: Store in database for actual billing
        # For now, just log to console for testing
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to log billing operation: {str(e)}")
        return False

def log_poh_verification(site_id: str, user_did: str, verification_result: bool):
    """
    Log PoH verification for MAU tracking (Federated Identity Network)
    
    Args:
        site_id: Site identifier
        user_did: User DID
        verification_result: Whether PoH verification succeeded
    """
    operation_type = 'poh_verification_success' if verification_result else 'poh_verification_failed'
    return log_permission_operation(site_id, operation_type, 1, user_did)

def log_iam_access(site_id: str, user_did: str, resource: str, access_granted: bool):
    """
    Log IAM access attempt for MAU tracking (Permission Lemmas)
    
    Args:
        site_id: Site identifier
        user_did: User DID
        resource: Resource being accessed
        access_granted: Whether access was granted
    """
    operation_type = 'iam_access_granted' if access_granted else 'iam_access_denied'
    return log_permission_operation(site_id, operation_type, 1, user_did)

def get_monthly_usage(site_id: str, year: int, month: int):
    """
    Get monthly usage statistics for a site
    
    Args:
        site_id: Site identifier
        year: Year (e.g., 2024)
        month: Month (1-12)
    
    Returns:
        Dict with usage statistics
    """
    # TODO: Query database for actual usage
    # For now, return mock data for testing
    return {
        'site_id': site_id,
        'year': year,
        'month': month,
        'poh_mau': 1247,  # Monthly Active Users for PoH
        'iam_mau': 856,   # Monthly Active Users for IAM
        'total_operations': 45623,
        'poh_cost': 62.35,  # $0.05 * 1247 MAU
        'iam_cost': 128.40, # $0.15 * 856 MAU
        'total_cost': 190.75
    }

def calculate_billing_amount(poh_mau: int, iam_mau: int):
    """
    Calculate billing amount based on MAU
    
    Args:
        poh_mau: Monthly Active Users for PoH/anti-bot
        iam_mau: Monthly Active Users for IAM/permissions
    
    Returns:
        Dict with billing breakdown
    """
    poh_rate = 0.05  # $0.05 per MAU for PoH
    iam_rate = 0.15  # $0.15 per MAU for IAM
    
    poh_cost = poh_mau * poh_rate
    iam_cost = iam_mau * iam_rate
    total_cost = poh_cost + iam_cost
    
    return {
        'poh_mau': poh_mau,
        'iam_mau': iam_mau,
        'poh_rate': poh_rate,
        'iam_rate': iam_rate,
        'poh_cost': round(poh_cost, 2),
        'iam_cost': round(iam_cost, 2),
        'total_cost': round(total_cost, 2),
        'savings_vs_auth0_duo': round(max(0, (poh_mau + iam_mau) * 2.0 - total_cost), 2)  # Estimated Auth0+Duo cost
    }