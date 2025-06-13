#!/usr/bin/env python3
"""
🤖 LEMMA AUTOMATED BILLING WORKFLOW
===================================
Complete monthly billing automation for all customers
Runs on the 1st of each month with webhook notifications
"""

import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import schedule
import threading

from .usage_logger import get_usage_logger
from .rollup_engine import get_rollup_engine
from .billing_engine import get_billing_engine
from .webhook_service import get_webhook_service

logger = logging.getLogger(__name__)

class AutomatedBillingWorkflow:
    """Production-grade automated billing workflow."""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.environ.get('STORAGE_DIR', '.lemma_enterprise')
        self.billing_dir = os.path.join(self.storage_dir, 'billing')
        self.automation_dir = os.path.join(self.billing_dir, 'automation')
        
        # Ensure directories exist
        os.makedirs(self.automation_dir, exist_ok=True)
        
        # Components
        self.usage_logger = get_usage_logger()
        self.rollup_engine = get_rollup_engine()
        self.billing_engine = get_billing_engine()
        self.webhook_service = get_webhook_service()
        
        # Configuration
        self.monthly_billing_day = int(os.environ.get('LEMMA_BILLING_DAY', '1'))  # 1st of month
        
        # State tracking
        self.last_run_file = os.path.join(self.automation_dir, 'last_run.json')
        
        # Start scheduler
        self.scheduler_thread = None
        self.start_automation_scheduler()
    
    def start_automation_scheduler(self):
        """Start the automated billing scheduler."""
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return
        
        # Schedule monthly billing on the configured day
        schedule.clear("billing")  # Clear any existing billing jobs
        
        # Monthly billing at 3:00 AM UTC on the billing day
        if self.monthly_billing_day == 1:
            schedule.every().month.at("03:00").do(self.run_monthly_billing).tag("billing")
        
        # Weekly payment reminders on Mondays at 9:00 AM UTC
        schedule.every().monday.at("09:00").do(self.run_payment_reminders).tag("billing")
        
        # Daily data processing at 2:30 AM UTC (after rollup completes)
        schedule.every().day.at("02:30").do(self.run_daily_processing).tag("billing")
        
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(300)  # Check every 5 minutes
        
        self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info(f"Automated billing scheduler started - monthly billing on day {self.monthly_billing_day}")
    
    def run_monthly_billing(self, target_month: str = None) -> Dict[str, Any]:
        """Run the complete monthly billing process for all customers."""
        try:
            if target_month is None:
                # Default to last month
                last_month = datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
                target_month = last_month.strftime('%Y-%m')
            
            logger.info(f"Starting automated monthly billing for {target_month}")
            
            # Check if already processed
            if self._is_month_already_processed(target_month):
                logger.info(f"Month {target_month} already processed, skipping")
                return {"success": True, "message": "Already processed", "month": target_month}
            
            # Get all active customer sites
            active_sites = self._get_active_customer_sites(target_month)
            
            if not active_sites:
                logger.info(f"No active sites found for {target_month}")
                return {"success": True, "message": "No active sites", "month": target_month}
            
            billing_results = {
                "month": target_month,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "sites_processed": [],
                "sites_failed": [],
                "total_revenue": "0.00",
                "total_customers": 0,
                "webhooks_sent": 0
            }
            
            total_revenue = 0.0
            
            # Process each customer site
            for site_id in active_sites:
                try:
                    site_result = self._process_customer_billing(site_id, target_month)
                    
                    if site_result["success"]:
                        billing_results["sites_processed"].append(site_result)
                        total_revenue += float(site_result["total_amount"])
                        
                        # Send billing summary webhook
                        webhook_sent = self.webhook_service.send_billing_summary_webhook(
                            site_id, site_result["billing_data"]
                        )
                        if webhook_sent:
                            billing_results["webhooks_sent"] += 1
                        
                        logger.info(f"Processed billing for {site_id}: ${site_result['total_amount']}")
                    else:
                        billing_results["sites_failed"].append({
                            "site_id": site_id,
                            "error": site_result.get("error", "Unknown error")
                        })
                        logger.error(f"Failed to process billing for {site_id}: {site_result.get('error')}")
                
                except Exception as e:
                    logger.error(f"Error processing billing for {site_id}: {e}")
                    billing_results["sites_failed"].append({
                        "site_id": site_id,
                        "error": str(e)
                    })
            
            # Update summary
            billing_results["total_revenue"] = f"{total_revenue:.2f}"
            billing_results["total_customers"] = len(billing_results["sites_processed"])
            
            # Save billing results
            self._save_monthly_billing_results(target_month, billing_results)
            
            # Mark month as processed
            self._mark_month_processed(target_month, billing_results)
            
            logger.info(f"Monthly billing completed for {target_month}: "
                       f"{billing_results['total_customers']} customers, "
                       f"${billing_results['total_revenue']} revenue")
            
            return {"success": True, "results": billing_results}
            
        except Exception as e:
            logger.error(f"Error in monthly billing for {target_month}: {e}")
            return {"success": False, "error": str(e), "month": target_month}
    
    def _process_customer_billing(self, site_id: str, month: str) -> Dict[str, Any]:
        """Process billing for a single customer site."""
        try:
            # Calculate monthly bill
            billing_data = self.billing_engine.calculate_monthly_bill(site_id, month)
            
            if not billing_data["success"]:
                return {"success": False, "error": billing_data.get("error")}
            
            # Generate and save invoice files
            invoice_files = self.billing_engine.save_invoice(
                billing_data, formats=["pdf", "csv", "json"]
            )
            
            # Send invoice generated webhook
            self.webhook_service.send_invoice_generated_webhook(
                site_id, billing_data, invoice_files
            )
            
            # Attempt to post to Stripe if configured
            stripe_result = None
            if os.environ.get('STRIPE_SECRET_KEY'):
                stripe_result = self.billing_engine.post_to_stripe(billing_data)
            
            return {
                "success": True,
                "site_id": site_id,
                "month": month,
                "total_amount": billing_data["charges"]["total_amount"],
                "usage_summary": {
                    "mah": billing_data["usage"]["monthly_active_humans"],
                    "new_humans": billing_data["usage"]["new_humans"],
                    "verifications": billing_data["usage"]["total_verifications"]
                },
                "billing_data": billing_data,
                "invoice_files": invoice_files,
                "stripe_result": stripe_result
            }
            
        except Exception as e:
            logger.error(f"Error processing billing for {site_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def run_payment_reminders(self) -> Dict[str, Any]:
        """Send payment reminders for overdue invoices."""
        try:
            logger.info("Running payment reminders workflow")
            
            current_date = datetime.now(timezone.utc)
            reminders_sent = 0
            
            # Look for overdue invoices from the last 3 months
            for i in range(3):
                check_month = (current_date.replace(day=1) - timedelta(days=i*30)).strftime('%Y-%m')
                billing_results = self._load_monthly_billing_results(check_month)
                
                if not billing_results:
                    continue
                
                # Check each processed site for overdue payments
                for site_result in billing_results.get("sites_processed", []):
                    billing_data = site_result.get("billing_data")
                    if not billing_data:
                        continue
                    
                    # Calculate days overdue
                    due_date = datetime.fromisoformat(billing_data["due_date"].replace('Z', '+00:00'))
                    days_overdue = (current_date - due_date).days
                    
                    if days_overdue > 0:
                        # Send payment reminder
                        reminder_sent = self.webhook_service.send_payment_reminder_webhook(
                            site_result["site_id"], billing_data, days_overdue
                        )
                        if reminder_sent:
                            reminders_sent += 1
                        
                        logger.info(f"Payment reminder sent to {site_result['site_id']}: "
                                   f"{days_overdue} days overdue")
            
            return {
                "success": True,
                "reminders_sent": reminders_sent,
                "processed_at": current_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in payment reminders: {e}")
            return {"success": False, "error": str(e)}
    
    def run_daily_processing(self) -> Dict[str, Any]:
        """Run daily data processing and cleanup tasks."""
        try:
            logger.info("Running daily billing processing")
            
            # Flush any pending usage events
            self.usage_logger.flush_all()
            
            # Check webhook delivery stats
            webhook_stats = self.webhook_service.get_webhook_stats(days=1)
            
            # Clean up old temporary files (older than 30 days)
            self._cleanup_old_files()
            
            return {
                "success": True,
                "webhook_stats": webhook_stats,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in daily processing: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_active_customer_sites(self, month: str) -> List[str]:
        """Get list of customer sites that had usage in the given month."""
        try:
            monthly_data = self.rollup_engine.get_monthly_rollup(month)
            
            if not monthly_data:
                return []
            
            active_sites = set()
            
            # Collect all sites that had usage during the month
            for date, daily_rollup in monthly_data.get("daily_rollups", {}).items():
                site_metrics = daily_rollup.get("site_metrics", {})
                active_sites.update(site_metrics.keys())
            
            # Filter out test/internal sites
            filtered_sites = [
                site for site in active_sites 
                if not site.startswith(('test_', 'internal_', 'default_'))
            ]
            
            return sorted(filtered_sites)
            
        except Exception as e:
            logger.error(f"Error getting active customer sites: {e}")
            return []
    
    def _is_month_already_processed(self, month: str) -> bool:
        """Check if a month has already been processed."""
        try:
            results_file = os.path.join(self.automation_dir, f'billing_results_{month}.json')
            return os.path.exists(results_file)
        except:
            return False
    
    def _mark_month_processed(self, month: str, results: Dict[str, Any]):
        """Mark a month as processed."""
        try:
            last_run_data = {
                "last_processed_month": month,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "total_customers": results["total_customers"],
                    "total_revenue": results["total_revenue"],
                    "webhooks_sent": results["webhooks_sent"]
                }
            }
            
            with open(self.last_run_file, 'w') as f:
                json.dump(last_run_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error marking month processed: {e}")
    
    def _save_monthly_billing_results(self, month: str, results: Dict[str, Any]):
        """Save monthly billing results."""
        try:
            results_file = os.path.join(self.automation_dir, f'billing_results_{month}.json')
            
            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2)
                
            logger.info(f"Saved billing results for {month}")
            
        except Exception as e:
            logger.error(f"Error saving billing results: {e}")
    
    def _load_monthly_billing_results(self, month: str) -> Optional[Dict[str, Any]]:
        """Load monthly billing results."""
        try:
            results_file = os.path.join(self.automation_dir, f'billing_results_{month}.json')
            
            if not os.path.exists(results_file):
                return None
            
            with open(results_file, 'r') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Error loading billing results for {month}: {e}")
            return None
    
    def _cleanup_old_files(self):
        """Clean up old temporary and log files."""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
            cutoff_timestamp = cutoff_date.timestamp()
            
            # Clean up directories
            cleanup_dirs = [
                os.path.join(self.billing_dir, 'invoices'),
                os.path.join(self.billing_dir, 'webhooks'),
                os.path.join(self.billing_dir, 'events')
            ]
            
            files_cleaned = 0
            for cleanup_dir in cleanup_dirs:
                if not os.path.exists(cleanup_dir):
                    continue
                
                for filename in os.listdir(cleanup_dir):
                    file_path = os.path.join(cleanup_dir, filename)
                    
                    if os.path.isfile(file_path):
                        file_mtime = os.path.getmtime(file_path)
                        
                        if file_mtime < cutoff_timestamp:
                            try:
                                os.remove(file_path)
                                files_cleaned += 1
                            except Exception as e:
                                logger.warning(f"Could not delete {file_path}: {e}")
            
            if files_cleaned > 0:
                logger.info(f"Cleaned up {files_cleaned} old files")
                
        except Exception as e:
            logger.error(f"Error in file cleanup: {e}")
    
    def get_automation_status(self) -> Dict[str, Any]:
        """Get current automation status."""
        try:
            # Load last run info
            last_run_data = {}
            if os.path.exists(self.last_run_file):
                with open(self.last_run_file, 'r') as f:
                    last_run_data = json.load(f)
            
            # Get recent webhook stats
            webhook_stats = self.webhook_service.get_webhook_stats(days=7)
            
            return {
                "automation_active": self.scheduler_thread and self.scheduler_thread.is_alive(),
                "last_run": last_run_data,
                "webhook_stats": webhook_stats,
                "next_monthly_billing": self._get_next_billing_date().isoformat(),
                "billing_day": self.monthly_billing_day
            }
            
        except Exception as e:
            logger.error(f"Error getting automation status: {e}")
            return {"error": str(e)}
    
    def _get_next_billing_date(self) -> datetime:
        """Calculate next monthly billing date."""
        now = datetime.now(timezone.utc)
        
        # If we're past the billing day this month, next billing is next month
        if now.day >= self.monthly_billing_day:
            # Next month
            if now.month == 12:
                next_billing = datetime(now.year + 1, 1, self.monthly_billing_day, 3, 0, tzinfo=timezone.utc)
            else:
                next_billing = datetime(now.year, now.month + 1, self.monthly_billing_day, 3, 0, tzinfo=timezone.utc)
        else:
            # This month
            next_billing = datetime(now.year, now.month, self.monthly_billing_day, 3, 0, tzinfo=timezone.utc)
        
        return next_billing
    
    def force_monthly_billing(self, month: str) -> Dict[str, Any]:
        """Force run monthly billing for a specific month."""
        logger.info(f"Force running monthly billing for {month}")
        return self.run_monthly_billing(month)

# Global automation instance
_automated_billing = None

def get_automated_billing() -> AutomatedBillingWorkflow:
    """Get or create global automated billing instance."""
    global _automated_billing
    if _automated_billing is None:
        _automated_billing = AutomatedBillingWorkflow()
    return _automated_billing

def run_monthly_billing(month: str = None) -> Dict[str, Any]:
    """Convenience function to run monthly billing."""
    return get_automated_billing().run_monthly_billing(month) 