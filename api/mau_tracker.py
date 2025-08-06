"""
Monthly Active User (MAU) Tracking System for Lemma Shield
Tracks actual monthly active users with privacy-preserving salted identifiers

Key Features:
- Only charges for users who actually visit/verify in a given month
- Uses customer-specific salting for privacy protection
- Rolling 30-day windows for accurate MAU calculation
- Automatic cleanup of old tracking data
"""

import os
import logging
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set, List
from collections import defaultdict
import threading
import time
import json

logger = logging.getLogger(__name__)

class MAUTracker:
    """Tracks Monthly Active Users with privacy-preserving salted identifiers"""
    
    def __init__(self):
        # Customer-specific salt storage (in production, store in database)
        self.customer_salts = {}
        
        # MAU tracking data: customer_id -> month -> set of salted_user_ids
        self.monthly_active_users = defaultdict(lambda: defaultdict(set))
        
        # Daily tracking for rolling windows: customer_id -> date -> set of salted_user_ids
        self.daily_active_users = defaultdict(lambda: defaultdict(set))
        
        # Stripe Identity verification tracking: customer_id -> month -> set of salted_user_ids
        # This tracks users who went through initial Stripe Identity verification ($2 fee)
        self.stripe_identity_verifications = defaultdict(lambda: defaultdict(set))
        
        self.lock = threading.Lock()
        
        # Start background cleanup thread
        self.cleanup_thread = threading.Thread(target=self._background_cleanup, daemon=True)
        self.cleanup_thread.start()
        
        logger.info("MAU Tracker initialized with privacy-preserving salting")
    
    def get_customer_salt(self, customer_id: str) -> bytes:
        """Get or create a customer-specific salt for user ID hashing"""
        with self.lock:
            if customer_id not in self.customer_salts:
                # Generate a unique salt for this customer
                # In production, this should be stored securely in database
                salt = os.urandom(32)  # 256-bit salt
                self.customer_salts[customer_id] = salt
                logger.info(f"Generated new salt for customer {customer_id}")
            
            return self.customer_salts[customer_id]
    
    def create_salted_user_id(self, customer_id: str, user_id: str) -> str:
        """
        Create a privacy-preserving salted hash of user ID
        
        This ensures:
        - Same user always gets same hash for a customer
        - Different customers get different hashes for same user
        - Original user ID cannot be reverse-engineered
        """
        salt = self.get_customer_salt(customer_id)
        
        # Use HMAC-SHA256 for secure hashing with customer-specific salt
        salted_hash = hmac.new(
            salt, 
            user_id.encode('utf-8'), 
            hashlib.sha256
        ).hexdigest()
        
        return f"salted_{salted_hash[:16]}"  # Use first 16 chars for compact storage
    
    def track_user_activity(self, customer_id: str, user_id: str, 
                           timestamp: Optional[datetime] = None, 
                           stripe_identity_verified: bool = False) -> Dict[str, Any]:
        """
        Track a user's activity for MAU calculation
        
        Args:
            customer_id: Customer's Stripe ID
            user_id: Original user identifier (email, username, etc.)
            timestamp: When activity occurred (defaults to now)
            stripe_identity_verified: True if user completed Stripe Identity verification ($2 fee)
            
        Returns:
            Dictionary with tracking results and MAU info
        """
        if not timestamp:
            timestamp = datetime.utcnow()
        
        # Create privacy-preserving salted user ID
        salted_user_id = self.create_salted_user_id(customer_id, user_id)
        
        # Get month and date keys
        month_key = timestamp.strftime('%Y-%m')
        date_key = timestamp.strftime('%Y-%m-%d')
        
        with self.lock:
            # Track for monthly billing (MAU)
            was_new_monthly_user = salted_user_id not in self.monthly_active_users[customer_id][month_key]
            self.monthly_active_users[customer_id][month_key].add(salted_user_id)
            
            # Track for rolling 30-day windows
            was_new_daily_user = salted_user_id not in self.daily_active_users[customer_id][date_key]
            self.daily_active_users[customer_id][date_key].add(salted_user_id)
            
            # Track Stripe Identity verifications (for $2 fee)
            was_new_stripe_identity = False
            if stripe_identity_verified:
                was_new_stripe_identity = salted_user_id not in self.stripe_identity_verifications[customer_id][month_key]
                self.stripe_identity_verifications[customer_id][month_key].add(salted_user_id)
            
            # Calculate current MAU (rolling 30 days)
            rolling_mau = self._calculate_rolling_mau(customer_id, timestamp)
            
            # Calculate monthly MAU (calendar month)
            monthly_mau = len(self.monthly_active_users[customer_id][month_key])
            
            # Calculate monthly Stripe Identity verifications
            monthly_stripe_identity = len(self.stripe_identity_verifications[customer_id][month_key])
        
        logger.info(f"User activity tracked: {customer_id} -> {salted_user_id} (MAU: {was_new_monthly_user}, Identity: {was_new_stripe_identity})")
        
        return {
            'customer_id': customer_id,
            'salted_user_id': salted_user_id,
            'month': month_key,
            'was_new_monthly_user': was_new_monthly_user,
            'was_new_daily_user': was_new_daily_user,
            'was_new_stripe_identity': was_new_stripe_identity,
            'current_monthly_mau': monthly_mau,
            'monthly_stripe_identity_count': monthly_stripe_identity,
            'rolling_30_day_mau': rolling_mau,
            'timestamp': timestamp.isoformat()
        }
    
    def _calculate_rolling_mau(self, customer_id: str, reference_date: datetime) -> int:
        """Calculate MAU for rolling 30-day window ending on reference_date"""
        end_date = reference_date.date()
        start_date = end_date - timedelta(days=29)  # 30 days total including end_date
        
        active_users = set()
        current_date = start_date
        
        while current_date <= end_date:
            date_key = current_date.strftime('%Y-%m-%d')
            if date_key in self.daily_active_users[customer_id]:
                active_users.update(self.daily_active_users[customer_id][date_key])
            current_date += timedelta(days=1)
        
        return len(active_users)
    
    def get_monthly_mau(self, customer_id: str, month: Optional[str] = None) -> Dict[str, Any]:
        """
        Get MAU and Stripe Identity billing data for a specific month
        
        Args:
            customer_id: Customer's Stripe ID
            month: Month in YYYY-MM format (defaults to current month)
            
        Returns:
            Dictionary with MAU and Stripe Identity data for billing
        """
        if not month:
            month = datetime.utcnow().strftime('%Y-%m')
        
        with self.lock:
            # Monthly Active Users (MAU) - $0.10 each
            mau_count = len(self.monthly_active_users[customer_id][month])
            active_users = list(self.monthly_active_users[customer_id][month])
            
            # Stripe Identity verifications - $2.00 each
            stripe_identity_count = len(self.stripe_identity_verifications[customer_id][month])
            stripe_identity_users = list(self.stripe_identity_verifications[customer_id][month])
        
        # Calculate billing amounts
        mau_cost = mau_count * 0.10  # $0.10 per monthly active user
        stripe_identity_cost = stripe_identity_count * 2.00  # $2.00 per Stripe Identity verification
        total_cost = mau_cost + stripe_identity_cost
        
        return {
            'customer_id': customer_id,
            'month': month,
            'mau_count': mau_count,
            'mau_cost': mau_cost,
            'stripe_identity_count': stripe_identity_count,
            'stripe_identity_cost': stripe_identity_cost,
            'total_monthly_cost': total_cost,
            'active_user_hashes': active_users,  # Salted hashes for verification
            'stripe_identity_hashes': stripe_identity_users,  # Users who did Identity verification
            'billing_period': f"{month}-01 to {month}-31",
            'billing_breakdown': {
                'mau_billing': f"{mau_count} users × $0.10 = ${mau_cost:.2f}",
                'identity_billing': f"{stripe_identity_count} verifications × $2.00 = ${stripe_identity_cost:.2f}",
                'total': f"${total_cost:.2f}"
            }
        }
    
    def get_rolling_mau(self, customer_id: str, reference_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Get MAU for rolling 30-day window"""
        if not reference_date:
            reference_date = datetime.utcnow()
        
        mau_count = self._calculate_rolling_mau(customer_id, reference_date)
        
        end_date = reference_date.date()
        start_date = end_date - timedelta(days=29)
        
        return {
            'customer_id': customer_id,
            'rolling_mau_count': mau_count,
            'window_start': start_date.isoformat(),
            'window_end': end_date.isoformat(),
            'reference_date': reference_date.isoformat()
        }
    
    def get_customer_analytics(self, customer_id: str, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive analytics for a customer"""
        reference_date = datetime.utcnow()
        current_month = reference_date.strftime('%Y-%m')
        
        # Get current month MAU
        monthly_data = self.get_monthly_mau(customer_id, current_month)
        
        # Get rolling MAU
        rolling_data = self.get_rolling_mau(customer_id, reference_date)
        
        # Calculate daily active users for the period
        daily_stats = []
        for i in range(days):
            date = (reference_date - timedelta(days=i)).date()
            date_key = date.strftime('%Y-%m-%d')
            
            with self.lock:
                dau = len(self.daily_active_users[customer_id][date_key])
            
            daily_stats.append({
                'date': date.isoformat(),
                'dau': dau
            })
        
        return {
            'customer_id': customer_id,
            'current_month': monthly_data,
            'rolling_30_day': rolling_data,
            'daily_stats': daily_stats[::-1],  # Reverse to show oldest first
            'analytics_generated': reference_date.isoformat()
        }
    
    def _background_cleanup(self):
        """Background thread to clean up old tracking data"""
        while True:
            try:
                # Sleep for 24 hours between cleanups
                time.sleep(24 * 60 * 60)
                
                cutoff_date = datetime.utcnow() - timedelta(days=90)  # Keep 90 days of data
                cutoff_month = cutoff_date.strftime('%Y-%m')
                cutoff_day = cutoff_date.strftime('%Y-%m-%d')
                
                with self.lock:
                    # Clean up old monthly data
                    for customer_id in list(self.monthly_active_users.keys()):
                        months_to_remove = []
                        for month in self.monthly_active_users[customer_id]:
                            if month < cutoff_month:
                                months_to_remove.append(month)
                        
                        for month in months_to_remove:
                            del self.monthly_active_users[customer_id][month]
                    
                    # Clean up old daily data
                    for customer_id in list(self.daily_active_users.keys()):
                        days_to_remove = []
                        for day in self.daily_active_users[customer_id]:
                            if day < cutoff_day:
                                days_to_remove.append(day)
                        
                        for day in days_to_remove:
                            del self.daily_active_users[customer_id][day]
                
                logger.info(f"Cleaned up MAU tracking data older than {cutoff_date.date()}")
                
            except Exception as e:
                logger.error(f"Error in MAU cleanup: {e}")
    
    def export_billing_data(self, customer_id: str, month: str) -> Dict[str, Any]:
        """Export billing data for Stripe integration"""
        mau_data = self.get_monthly_mau(customer_id, month)
        
        return {
            'customer_id': customer_id,
            'billing_month': month,
            'mau_billing': {
                'count': mau_data['mau_count'],
                'unit_price': 0.10,
                'total_amount': mau_data['mau_cost'],
                'description': 'Monthly Active Users'
            },
            'stripe_identity_billing': {
                'count': mau_data['stripe_identity_count'],
                'unit_price': 2.00,
                'total_amount': mau_data['stripe_identity_cost'],
                'description': 'Stripe Identity Verifications'
            },
            'total_amount': mau_data['total_monthly_cost'],
            'currency': 'usd',
            'billing_breakdown': mau_data['billing_breakdown'],
            'verification_hash': hashlib.sha256(
                f"{customer_id}:{month}:{mau_data['mau_count']}:{mau_data['stripe_identity_count']}".encode()
            ).hexdigest()[:16]
        }

# Global MAU tracker instance
mau_tracker = MAUTracker()

def track_user_activity(customer_id: str, user_id: str, timestamp: Optional[datetime] = None, 
                       stripe_identity_verified: bool = False) -> Dict[str, Any]:
    """
    Convenience function to track user activity for MAU billing
    
    Args:
        customer_id: Customer's Stripe ID
        user_id: User identifier (email, username, etc.)
        timestamp: When activity occurred (defaults to now)
        stripe_identity_verified: True if user completed Stripe Identity verification ($2 fee)
    
    This should be called:
    1. Whenever a user visits a page with Lemma Shield (stripe_identity_verified=False)
    2. When a user completes Stripe Identity verification (stripe_identity_verified=True)
    """
    return mau_tracker.track_user_activity(customer_id, user_id, timestamp, stripe_identity_verified)

def track_stripe_identity_verification(customer_id: str, user_id: str, timestamp: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Convenience function to track Stripe Identity verification for $2 billing
    
    This should be called when a user successfully completes Stripe Identity verification
    """
    return mau_tracker.track_user_activity(customer_id, user_id, timestamp, stripe_identity_verified=True)

def get_monthly_billing_data(customer_id: str, month: Optional[str] = None) -> Dict[str, Any]:
    """Get MAU billing data for a specific month"""
    return mau_tracker.get_monthly_mau(customer_id, month)

def get_customer_analytics(customer_id: str, days: int = 30) -> Dict[str, Any]:
    """Get comprehensive MAU analytics for a customer"""
    return mau_tracker.get_customer_analytics(customer_id, days)

# Export the tracker and functions
__all__ = ['mau_tracker', 'track_user_activity', 'track_stripe_identity_verification', 'get_monthly_billing_data', 'get_customer_analytics']