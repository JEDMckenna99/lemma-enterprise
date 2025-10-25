"""
Usage Tracking for Lemma IAM
Tracks MAU (Monthly Active Users) and determines billing tier
"""

import os
import redis
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
import hashlib

logger = logging.getLogger(__name__)

# Initialize Redis for MAU tracking
try:
    REDIS_URL = os.getenv('REDIS_URL')
    if REDIS_URL:
        redis_client = redis.from_url(REDIS_URL)
        redis_client.ping()
        REDIS_AVAILABLE = True
        logger.info("✅ Usage tracking initialized with Redis")
    else:
        REDIS_AVAILABLE = False
        logger.warning("⚠️ REDIS_URL not set - usage tracking disabled")
except Exception as e:
    REDIS_AVAILABLE = False
    logger.error(f"❌ Redis connection failed for usage tracking: {e}")


def track_active_user(site_id: str, user_email: str):
    """
    Track an active user for MAU calculation
    
    Args:
        site_id: Site identifier
        user_email: User's email address
    """
    if not REDIS_AVAILABLE:
        return
    
    try:
        # Generate unique user ID (hash email for privacy)
        user_hash = hashlib.sha256(user_email.encode()).hexdigest()[:16]
        
        # Get current month key
        month_key = datetime.now().strftime('%Y-%m')
        mau_key = f'mau:{site_id}:{month_key}'
        
        # Add user to set (automatically deduplicates)
        redis_client.sadd(mau_key, user_hash)
        
        # Set expiry to 90 days (keep 3 months of data)
        redis_client.expire(mau_key, 90 * 24 * 60 * 60)
        
        logger.debug(f"Tracked active user for site {site_id}")
        
    except Exception as e:
        logger.error(f"Failed to track active user: {e}")


def get_monthly_active_users(site_id: str, month: Optional[str] = None) -> int:
    """
    Get MAU count for a site
    
    Args:
        site_id: Site identifier
        month: Month in format YYYY-MM (default: current month)
    
    Returns:
        Number of monthly active users
    """
    if not REDIS_AVAILABLE:
        return 0
    
    try:
        if not month:
            month = datetime.now().strftime('%Y-%m')
        
        mau_key = f'mau:{site_id}:{month}'
        count = redis_client.scard(mau_key)
        
        return count
        
    except Exception as e:
        logger.error(f"Failed to get MAU: {e}")
        return 0


def get_tier_for_mau(mau: int) -> Dict[str, any]:
    """
    Determine billing tier based on MAU count
    
    Args:
        mau: Monthly active users
    
    Returns:
        Tier information including name, price, limits
    """
    if mau < 1000:
        return {
            'tier': 'free',
            'name': 'Free',
            'monthly_price': 0,
            'annual_price': 0,
            'mau_limit': 1000,
            'features': [
                'Up to 1,000 MAU',
                'Unlimited sites',
                'Email authentication',
                'Ed25519 + OPRF crypto',
                '30-day audit logs',
                'Community support'
            ]
        }
    elif mau < 5000:
        return {
            'tier': 'starter',
            'name': 'Starter',
            'monthly_price': 5,
            'annual_price': 60,
            'mau_limit': 5000,
            'features': [
                '1,000 - 5,000 MAU',
                'Everything in Free',
                '90-day audit logs',
                'Email support',
                'Client-side verification',
                'Offline capability'
            ]
        }
    elif mau < 100000:
        # Growth tier: $0.023/MAU
        monthly_price = round(mau * 0.023, 2)
        annual_price = round(monthly_price * 12, 2)
        
        return {
            'tier': 'growth',
            'name': 'Growth',
            'monthly_price': monthly_price,
            'annual_price': annual_price,
            'mau_limit': 100000,
            'per_mau_price': 0.023,
            'features': [
                f'{mau:,} MAU',
                'Everything in Starter',
                '1-year audit logs',
                'Priority support',
                'OPRF privacy',
                '99.9% uptime SLA'
            ]
        }
    else:
        # Enterprise tier: Custom pricing (default to $0.06/MAU for B2B)
        monthly_price = round(mau * 0.06, 2)
        annual_price = round(monthly_price * 12, 2)
        
        return {
            'tier': 'enterprise',
            'name': 'Enterprise',
            'monthly_price': monthly_price,
            'annual_price': annual_price,
            'mau_limit': None,  # No limit
            'per_mau_price': 0.06,
            'features': [
                f'{mau:,} MAU',
                'Everything in Growth',
                '7-year audit logs',
                '24/7 priority support',
                'SAML 2.0',
                'Custom SLA'
            ],
            'contact_sales': True
        }


def get_usage_summary(site_id: str) -> Dict[str, any]:
    """
    Get comprehensive usage summary for dashboard
    
    Args:
        site_id: Site identifier
    
    Returns:
        Usage summary including MAU, tier, pricing, historical data
    """
    try:
        # Get current month MAU
        current_mau = get_monthly_active_users(site_id)
        
        # Get last 3 months MAU
        historical_mau = []
        for i in range(3):
            month = (datetime.now() - timedelta(days=30 * i)).strftime('%Y-%m')
            mau_count = get_monthly_active_users(site_id, month)
            historical_mau.append({
                'month': month,
                'mau': mau_count
            })
        
        # Determine tier
        tier_info = get_tier_for_mau(current_mau)
        
        # Calculate if approaching tier limit
        if tier_info['mau_limit']:
            usage_percentage = (current_mau / tier_info['mau_limit']) * 100
            approaching_limit = usage_percentage > 80
        else:
            usage_percentage = 0
            approaching_limit = False
        
        return {
            'site_id': site_id,
            'current_mau': current_mau,
            'current_tier': tier_info,
            'usage_percentage': round(usage_percentage, 1),
            'approaching_limit': approaching_limit,
            'historical_mau': historical_mau,
            'next_tier': get_tier_for_mau(current_mau + 1) if approaching_limit else None
        }
        
    except Exception as e:
        logger.error(f"Failed to get usage summary: {e}")
        return {
            'error': str(e),
            'site_id': site_id,
            'current_mau': 0,
            'current_tier': get_tier_for_mau(0)
        }


def get_verification_count(site_id: str, period_days: int = 30) -> int:
    """
    Get total number of verifications in period
    
    Args:
        site_id: Site identifier
        period_days: Number of days to look back
    
    Returns:
        Total verification count
    """
    if not REDIS_AVAILABLE:
        return 0
    
    try:
        verification_key = f'verifications:{site_id}'
        
        # Get count from Redis counter
        count = redis_client.get(verification_key)
        return int(count) if count else 0
        
    except Exception as e:
        logger.error(f"Failed to get verification count: {e}")
        return 0


def increment_verification_count(site_id: str):
    """Increment verification counter for a site"""
    if not REDIS_AVAILABLE:
        return
    
    try:
        verification_key = f'verifications:{site_id}'
        redis_client.incr(verification_key)
        
        # Reset counter monthly
        if redis_client.ttl(verification_key) < 0:  # No expiry set
            # Set to expire at end of month
            now = datetime.now()
            next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
            seconds_until_next_month = int((next_month - now).total_seconds())
            redis_client.expire(verification_key, seconds_until_next_month)
        
    except Exception as e:
        logger.error(f"Failed to increment verification count: {e}")

