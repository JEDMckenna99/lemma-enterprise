"""
Usage Tracking System for Lemma Shield
Automatically tracks verified users and reports usage to Stripe for billing

This integrates with the shield verification process to automatically
track and bill for verified users.
"""

import os
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set
from collections import defaultdict
import threading
import time

logger = logging.getLogger(__name__)

class UsageTracker:
    """Tracks verified users for automated billing"""
    
    def __init__(self):
        self.verified_users = defaultdict(set)  # customer_id -> set of user_ids
        self.daily_counts = defaultdict(lambda: defaultdict(int))  # customer_id -> date -> count
        self.lock = threading.Lock()
        
        # Start background reporting thread
        self.reporting_thread = threading.Thread(target=self._background_reporter, daemon=True)
        self.reporting_thread.start()
        
    def track_verified_user(self, customer_id: str, user_id: str, 
                           timestamp: Optional[datetime] = None) -> bool:
        """
        Track a verified user for billing purposes
        
        Args:
            customer_id: The customer's Stripe ID
            user_id: Unique identifier for the verified user
            timestamp: When verification occurred (defaults to now)
            
        Returns:
            True if this is a new user for the month, False if already tracked
        """
        if not timestamp:
            timestamp = datetime.utcnow()
            
        date_key = timestamp.strftime('%Y-%m-%d')
        month_key = timestamp.strftime('%Y-%m')
        
        with self.lock:
            # Track this user for the customer
            user_set = self.verified_users[customer_id]
            is_new_user = user_id not in user_set
            
            if is_new_user:
                user_set.add(user_id)
                self.daily_counts[customer_id][date_key] += 1
                
                logger.info(f"New verified user tracked: {customer_id} -> {user_id}")
                
                # If this is a new user, they incur the $2 setup fee
                if is_new_user:
                    self._track_setup_fee(customer_id, user_id)
                
            return is_new_user
    
    def _track_setup_fee(self, customer_id: str, user_id: str):
        """Track setup fee for new user (to be invoiced)"""
        # TODO: Create invoice item for $2 setup fee
        logger.info(f"Setup fee tracked for customer {customer_id}, user {user_id}: $2.00")
    
    def get_monthly_user_count(self, customer_id: str, 
                              month: Optional[datetime] = None) -> int:
        """Get total verified users for a customer in a given month"""
        if not month:
            month = datetime.utcnow()
            
        month_key = month.strftime('%Y-%m')
        
        with self.lock:
            # Count unique users for the month
            total_users = len(self.verified_users.get(customer_id, set()))
            return total_users
    
    def get_usage_summary(self, customer_id: str, 
                         start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get detailed usage summary for a customer"""
        with self.lock:
            user_count = len(self.verified_users.get(customer_id, set()))
            
            # Calculate costs
            monthly_cost = user_count * 0.10  # $0.10 per user per month
            
            # Count new users in period (setup fees)
            new_users_in_period = 0  # TODO: Track this properly
            setup_fees = new_users_in_period * 2.00  # $2.00 per new user
            
            return {
                'customer_id': customer_id,
                'period_start': start_date.isoformat(),
                'period_end': end_date.isoformat(),
                'verified_users': user_count,
                'monthly_cost': monthly_cost,
                'new_users_in_period': new_users_in_period,
                'setup_fees': setup_fees,
                'total_cost': monthly_cost + setup_fees,
                'currency': 'USD'
            }
    
    def _background_reporter(self):
        """Background thread that reports usage to Stripe periodically"""
        while True:
            try:
                # Sleep for 1 hour between reports
                time.sleep(3600)
                
                # Report usage for all customers
                with self.lock:
                    for customer_id in self.verified_users.keys():
                        user_count = len(self.verified_users[customer_id])
                        if user_count > 0:
                            self._report_to_stripe(customer_id, user_count)
                            
            except Exception as e:
                logger.error(f"Error in background reporter: {e}")
    
    def _report_to_stripe(self, customer_id: str, user_count: int):
        """Report usage to Stripe for billing"""
        try:
            # TODO: Use Stripe Meter API to report usage
            logger.info(f"Reporting to Stripe: Customer {customer_id} has {user_count} verified users")
            
            # This would use the automated_billing_manager to report usage
            # from api.automated_billing import billing_manager
            # billing_manager.report_user_usage(customer_id, user_count)
            
        except Exception as e:
            logger.error(f"Failed to report usage to Stripe: {e}")

# Global usage tracker instance
usage_tracker = UsageTracker()

def track_user_verification(customer_id: str, user_id: str) -> bool:
    """
    Convenience function to track user verification
    
    This should be called whenever a user is successfully verified
    through the Lemma Shield system.
    """
    return usage_tracker.track_verified_user(customer_id, user_id)

def get_customer_usage(customer_id: str, start_date: datetime, 
                      end_date: datetime) -> Dict[str, Any]:
    """Get usage summary for a customer"""
    return usage_tracker.get_usage_summary(customer_id, start_date, end_date)

# Export the tracker and functions
__all__ = ['usage_tracker', 'track_user_verification', 'get_customer_usage']