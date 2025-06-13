#!/usr/bin/env python3
"""
📊 LEMMA NIGHTLY ROLLUP ENGINE
==============================
Processes daily usage events into MAH & New-Human metrics
Implements deduplication by DID hash with retry logic
"""

import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Set, List, Optional, Any
from threading import Lock
import schedule
import threading

from .usage_logger import get_usage_logger

logger = logging.getLogger(__name__)

class NightlyRollupEngine:
    """Production-grade rollup engine for billing calculations."""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.environ.get('STORAGE_DIR', '.lemma_enterprise')
        self.rollup_dir = os.path.join(self.storage_dir, 'billing', 'rollups')
        self.state_dir = os.path.join(self.storage_dir, 'billing', 'state')
        self.lock = Lock()
        
        # Ensure directories exist
        os.makedirs(self.rollup_dir, exist_ok=True)
        os.makedirs(self.state_dir, exist_ok=True)
        
        # Initialize global human registry
        self.global_humans = self._load_global_human_registry()
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 300  # 5 minutes
        
        # Usage logger instance (for testing)
        self._usage_logger = None
        
        # Start scheduler in background
        self.scheduler_thread = None
        # Only start scheduler if not in test mode
        if not storage_dir or 'tmp' not in storage_dir:
            self.start_scheduler()
        
    def start_scheduler(self):
        """Start the nightly rollup scheduler."""
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return
            
        # Schedule nightly rollup at 2:00 AM UTC
        schedule.clear()
        schedule.every().day.at("02:00").do(self.run_nightly_rollup)
        
        # Start scheduler thread
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
                
        self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Nightly rollup scheduler started - runs at 2:00 AM UTC")
    
    def set_usage_logger(self, usage_logger):
        """Set the usage logger instance (for testing)."""
        self._usage_logger = usage_logger
    
    def run_nightly_rollup(self, target_date: str = None) -> Dict[str, Any]:
        """
        Run the nightly rollup job with retry logic.
        
        Args:
            target_date: Date to process (defaults to yesterday)
            
        Returns:
            Rollup results
        """
        if target_date is None:
            # Default to yesterday
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            target_date = yesterday.strftime('%Y-%m-%d')
        
        logger.info(f"Starting nightly rollup for {target_date}")
        
        attempt = 0
        while attempt < self.max_retries:
            try:
                with self.lock:
                    result = self._process_daily_rollup(target_date)
                    
                    if result['success']:
                        logger.info(f"Nightly rollup completed successfully for {target_date}")
                        return result
                    else:
                        raise Exception(f"Rollup failed: {result.get('error', 'Unknown error')}")
                        
            except Exception as e:
                attempt += 1
                logger.error(f"Rollup attempt {attempt} failed for {target_date}: {e}")
                
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"All {self.max_retries} rollup attempts failed for {target_date}")
                    return {
                        "success": False,
                        "date": target_date,
                        "error": str(e),
                        "attempts": attempt
                    }
        
        return {"success": False, "date": target_date, "error": "Max retries exceeded"}
    
    def _process_daily_rollup(self, date: str) -> Dict[str, Any]:
        """Process daily events into rollup metrics."""
        try:
            # Get usage logger - use instance if available, otherwise global
            if hasattr(self, '_usage_logger') and self._usage_logger:
                usage_logger = self._usage_logger
            else:
                usage_logger = get_usage_logger()
            
            # Load daily events
            events = usage_logger.get_daily_events(date)
            if not events:
                logger.info(f"No events found for {date}")
                return {
                    "success": True,
                    "date": date,
                    "metrics": self._create_empty_metrics()
                }
            
            # Process events with deduplication
            metrics = self._calculate_daily_metrics(events, date)
            
            # Save rollup results
            self._save_daily_rollup(date, metrics)
            
            # Update monthly aggregates
            self._update_monthly_aggregates(date, metrics)
            
            # Update global human registry
            self._update_global_human_registry(metrics['global_summary']['new_humans'])
            
            logger.info(f"Processed {len(events)} events into rollup metrics for {date}")
            
            return {
                "success": True,
                "date": date,
                "events_processed": len(events),
                "metrics": metrics
            }
            
        except Exception as e:
            logger.error(f"Error processing daily rollup for {date}: {e}")
            raise
    
    def _calculate_daily_metrics(self, events: List[Dict], date: str) -> Dict[str, Any]:
        """Calculate MAH and New-Human metrics with deduplication."""
        # Site-specific metrics
        site_metrics = {}
        
        # Global deduplication sets
        all_dids_today = set()
        
        # Process each event
        for event in events:
            site_id = event['site_id']
            did_hash = event['subject_did_hash']
            
            # Initialize site metrics
            if site_id not in site_metrics:
                site_metrics[site_id] = {
                    "site_id": site_id,
                    "total_verifications": 0,
                    "unique_humans": set(),
                    "new_humans": set()
                }
            
            # Count verification
            site_metrics[site_id]["total_verifications"] += 1
            
            # Add to unique humans for this site
            site_metrics[site_id]["unique_humans"].add(did_hash)
            
            # Add to global deduplication set
            all_dids_today.add(did_hash)
            
            # Check if this is a new human globally
            if did_hash not in self.global_humans:
                site_metrics[site_id]["new_humans"].add(did_hash)
        
        # Convert sets to counts and lists for serialization
        processed_metrics = {}
        total_new_humans_today = set()
        
        for site_id, metrics in site_metrics.items():
            unique_humans_list = list(metrics["unique_humans"])
            new_humans_list = list(metrics["new_humans"])
            
            # Add to global new humans
            total_new_humans_today.update(new_humans_list)
            
            processed_metrics[site_id] = {
                "site_id": site_id,
                "date": date,
                "total_verifications": metrics["total_verifications"],
                "monthly_active_humans": len(unique_humans_list),  # MAH for this site
                "new_humans": len(new_humans_list),
                "unique_human_hashes": unique_humans_list,
                "new_human_hashes": new_humans_list
            }
        
        # Global summary
        global_summary = {
            "date": date,
            "total_verifications": sum(event for event in [m["total_verifications"] for m in processed_metrics.values()]),
            "global_unique_humans": len(all_dids_today),
            "global_new_humans": len(total_new_humans_today),
            "active_sites": len(processed_metrics),
            "new_humans": list(total_new_humans_today)  # For updating global registry
        }
        
        return {
            "global_summary": global_summary,
            "site_metrics": processed_metrics,
            "calculated_at": time.time()
        }
    
    def _create_empty_metrics(self) -> Dict[str, Any]:
        """Create empty metrics structure."""
        return {
            "global_summary": {
                "date": None,
                "total_verifications": 0,
                "global_unique_humans": 0,
                "global_new_humans": 0,
                "active_sites": 0,
                "new_humans": []
            },
            "site_metrics": {},
            "calculated_at": time.time()
        }
    
    def _save_daily_rollup(self, date: str, metrics: Dict[str, Any]):
        """Save daily rollup results."""
        rollup_file = os.path.join(self.rollup_dir, f'rollup_{date}.json')
        
        # Add metadata
        rollup_data = {
            "date": date,
            "created_at": time.time(),
            "version": "1.0",
            "metrics": metrics
        }
        
        # Write atomically
        temp_file = rollup_file + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump(rollup_data, f, separators=(',', ':'), indent=2)
        os.replace(temp_file, rollup_file)
        
        logger.info(f"Saved daily rollup: {rollup_file}")
    
    def _update_monthly_aggregates(self, date: str, metrics: Dict[str, Any]):
        """Update monthly aggregate metrics."""
        month = date[:7]  # YYYY-MM
        monthly_file = os.path.join(self.rollup_dir, f'monthly_{month}.json')
        
        # Load existing monthly data
        if os.path.exists(monthly_file):
            with open(monthly_file, 'r') as f:
                monthly_data = json.load(f)
        else:
            monthly_data = {
                "month": month,
                "created_at": time.time(),
                "daily_rollups": {},
                "monthly_summary": {
                    "total_verifications": 0,
                    "monthly_active_humans": set(),
                    "new_humans_this_month": set(),
                    "active_sites": set(),
                    "days_processed": 0
                }
            }
        
        # Add this day's rollup
        monthly_data["daily_rollups"][date] = metrics
        monthly_data["updated_at"] = time.time()
        
        # Update monthly summary
        summary = monthly_data["monthly_summary"]
        summary["total_verifications"] += metrics["global_summary"]["total_verifications"]
        
        # Convert sets for JSON serialization
        if isinstance(summary["monthly_active_humans"], list):
            summary["monthly_active_humans"] = set(summary["monthly_active_humans"])
        if isinstance(summary["new_humans_this_month"], list):
            summary["new_humans_this_month"] = set(summary["new_humans_this_month"])
        if isinstance(summary["active_sites"], list):
            summary["active_sites"] = set(summary["active_sites"])
        
        # Add today's humans to monthly totals
        for site_metrics in metrics["site_metrics"].values():
            summary["monthly_active_humans"].update(site_metrics["unique_human_hashes"])
            summary["new_humans_this_month"].update(site_metrics["new_human_hashes"])
            summary["active_sites"].add(site_metrics["site_id"])
        
        summary["days_processed"] = len(monthly_data["daily_rollups"])
        
        # Convert sets back to lists for JSON
        summary["monthly_active_humans"] = list(summary["monthly_active_humans"])
        summary["new_humans_this_month"] = list(summary["new_humans_this_month"])
        summary["active_sites"] = list(summary["active_sites"])
        
        # Write atomically
        temp_file = monthly_file + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump(monthly_data, f, separators=(',', ':'), indent=2)
        os.replace(temp_file, monthly_file)
        
        logger.info(f"Updated monthly aggregates: {monthly_file}")
    
    def _load_global_human_registry(self) -> Set[str]:
        """Load the global human registry for new human detection."""
        registry_file = os.path.join(self.state_dir, 'global_humans.json')
        
        if not os.path.exists(registry_file):
            return set()
        
        try:
            with open(registry_file, 'r') as f:
                data = json.load(f)
            return set(data.get('human_hashes', []))
        except Exception as e:
            logger.error(f"Error loading global human registry: {e}")
            return set()
    
    def _update_global_human_registry(self, new_humans: List[str]):
        """Update the global human registry with new humans."""
        if not new_humans:
            return
        
        # Add to in-memory set
        self.global_humans.update(new_humans)
        
        # Save to disk
        registry_file = os.path.join(self.state_dir, 'global_humans.json')
        registry_data = {
            "updated_at": time.time(),
            "total_humans": len(self.global_humans),
            "human_hashes": list(self.global_humans)
        }
        
        # Write atomically
        temp_file = registry_file + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump(registry_data, f, separators=(',', ':'))
        os.replace(temp_file, registry_file)
        
        logger.info(f"Updated global human registry: {len(new_humans)} new humans added")
    
    def get_daily_rollup(self, date: str) -> Optional[Dict[str, Any]]:
        """Get daily rollup results."""
        rollup_file = os.path.join(self.rollup_dir, f'rollup_{date}.json')
        
        if not os.path.exists(rollup_file):
            return None
        
        try:
            with open(rollup_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading daily rollup {date}: {e}")
            return None
    
    def get_monthly_rollup(self, month: str) -> Optional[Dict[str, Any]]:
        """Get monthly rollup results."""
        monthly_file = os.path.join(self.rollup_dir, f'monthly_{month}.json')
        
        if not os.path.exists(monthly_file):
            return None
        
        try:
            with open(monthly_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading monthly rollup {month}: {e}")
            return None
    
    def force_daily_rollup(self, date: str) -> Dict[str, Any]:
        """Force run rollup for a specific date (manual trigger)."""
        logger.info(f"Force running rollup for {date}")
        return self.run_nightly_rollup(date)
    
    def get_billing_summary(self, month: str) -> Dict[str, Any]:
        """Get billing summary for a month."""
        monthly_data = self.get_monthly_rollup(month)
        
        if not monthly_data:
            return {"error": f"No data found for month {month}"}
        
        summary = monthly_data["monthly_summary"]
        
        return {
            "month": month,
            "total_verifications": summary["total_verifications"],
            "monthly_active_humans": len(summary["monthly_active_humans"]),
            "new_humans": len(summary["new_humans_this_month"]),
            "active_sites": len(summary["active_sites"]),
            "days_processed": summary["days_processed"],
            "data_available": True
        }

# Global rollup engine instance
_rollup_engine = None

def get_rollup_engine() -> NightlyRollupEngine:
    """Get or create global rollup engine instance."""
    global _rollup_engine
    if _rollup_engine is None:
        _rollup_engine = NightlyRollupEngine()
    return _rollup_engine

def run_nightly_rollup(target_date: str = None) -> Dict[str, Any]:
    """Convenience function to run nightly rollup."""
    return get_rollup_engine().run_nightly_rollup(target_date) 