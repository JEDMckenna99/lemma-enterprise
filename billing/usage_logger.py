#!/usr/bin/env python3
"""
🔢 LEMMA USAGE METERING & EVENT LOGGER
=====================================
Captures every successful verification for billing purposes
Implements immutable event logging with DID privacy protection
"""

import json
import os
import time
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from threading import Lock
import logging

logger = logging.getLogger(__name__)

class UsageEventLogger:
    """Production-grade usage event logger for billing operations."""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.environ.get('STORAGE_DIR', '.lemma_enterprise')
        self.events_dir = os.path.join(self.storage_dir, 'billing', 'events')
        self.ledger_dir = os.path.join(self.storage_dir, 'billing', 'ledger')
        self.lock = Lock()
        
        # Ensure directories exist
        os.makedirs(self.events_dir, exist_ok=True)
        os.makedirs(self.ledger_dir, exist_ok=True)
        
        # Event buffering for performance
        self.event_buffer = []
        self.buffer_size = 100
        self.last_flush = time.time()
        
    def log_verification_success(self, site_id: str, subject_did: str, 
                                timestamp: float = None, metadata: Dict = None) -> str:
        """
        Log a successful verification event for billing.
        
        Args:
            site_id: Customer site identifier
            subject_did: User's DID (will be hashed for privacy)
            timestamp: Event timestamp (defaults to now)
            metadata: Additional event metadata
            
        Returns:
            Event ID for tracking
        """
        if timestamp is None:
            timestamp = time.time()
            
        # Generate event ID
        event_id = str(uuid.uuid4())
        
        # Hash the DID for privacy protection
        did_hash = self._hash_did(subject_did)
        
        # Create immutable event record
        event = {
            "event_id": event_id,
            "event_type": "verification_success",
            "site_id": site_id,
            "subject_did_hash": did_hash,
            "timestamp": timestamp,
            "iso_timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            "date": datetime.fromtimestamp(timestamp, timezone.utc).strftime('%Y-%m-%d'),
            "metadata": metadata or {},
            "logged_at": time.time()
        }
        
        # Add to buffer
        with self.lock:
            self.event_buffer.append(event)
            
            # Flush buffer if needed
            if (len(self.event_buffer) >= self.buffer_size or 
                time.time() - self.last_flush > 60):  # Flush every minute
                self._flush_buffer()
        
        logger.info(f"Logged verification success: site={site_id}, event={event_id}")
        return event_id
    
    def _hash_did(self, did: str) -> str:
        """Create privacy-preserving hash of DID for deduplication."""
        # Use SHA-256 with salt for security
        salt = os.environ.get('LEMMA_DID_SALT', 'lemma_did_salt_2025')
        return hashlib.sha256(f"{salt}{did}".encode()).hexdigest()
    
    def _flush_buffer(self):
        """Flush event buffer to persistent storage."""
        if not self.event_buffer:
            return
            
        try:
            # Group events by date for proper partitioning
            events_by_date = {}
            for event in self.event_buffer:
                event_date = event['iso_timestamp'][:10]  # YYYY-MM-DD
                if event_date not in events_by_date:
                    events_by_date[event_date] = []
                events_by_date[event_date].append(event)
            
            # Write events to appropriate daily files
            for date, events in events_by_date.items():
                events_file = os.path.join(self.events_dir, f'events_{date}.jsonl')
                
                # Append events to daily file (JSONL format for streaming)
                with open(events_file, 'a') as f:
                    for event in events:
                        f.write(json.dumps(event, separators=(',', ':')) + '\n')
            
            # Update ledger
            self._update_immutable_ledger(self.event_buffer)
            
            # Clear buffer
            events_flushed = len(self.event_buffer)
            self.event_buffer.clear()
            self.last_flush = time.time()
            
            logger.info(f"Flushed {events_flushed} events to storage")
            
        except Exception as e:
            logger.error(f"Error flushing event buffer: {e}")
            # Keep events in buffer on failure for retry
    
    def _update_immutable_ledger(self, events: List[Dict]):
        """Update immutable ledger with checksum chain."""
        try:
            # Group events by month for ledger partitioning
            monthly_events = {}
            for event in events:
                month_key = event['iso_timestamp'][:7]  # YYYY-MM
                if month_key not in monthly_events:
                    monthly_events[month_key] = []
                monthly_events[month_key].append(event)
            
            # Update each month's ledger
            for month, month_events in monthly_events.items():
                self._update_monthly_ledger(month, month_events)
                
        except Exception as e:
            logger.error(f"Error updating immutable ledger: {e}")
    
    def _update_monthly_ledger(self, month: str, events: List[Dict]):
        """Update monthly ledger with checksum verification."""
        ledger_file = os.path.join(self.ledger_dir, f'ledger_{month}.json')
        
        # Load existing ledger or create new
        if os.path.exists(ledger_file):
            with open(ledger_file, 'r') as f:
                ledger = json.load(f)
        else:
            ledger = {
                "month": month,
                "created_at": time.time(),
                "events": [],
                "checksums": [],
                "event_count": 0
            }
        
        # Add new events
        ledger["events"].extend(events)
        ledger["event_count"] = len(ledger["events"])
        ledger["updated_at"] = time.time()
        
        # Calculate checksum chain
        current_checksum = self._calculate_ledger_checksum(ledger["events"])
        ledger["checksums"].append({
            "timestamp": time.time(),
            "event_count": ledger["event_count"],
            "checksum": current_checksum,
            "previous_checksum": ledger["checksums"][-1]["checksum"] if ledger["checksums"] else None
        })
        
        # Write atomically
        temp_file = ledger_file + '.tmp'
        with open(temp_file, 'w') as f:
            json.dump(ledger, f, separators=(',', ':'))
        os.replace(temp_file, ledger_file)
        
        logger.info(f"Updated monthly ledger {month}: {len(events)} new events")
    
    def _calculate_ledger_checksum(self, events: List[Dict]) -> str:
        """Calculate cryptographic checksum of events."""
        # Sort events by timestamp for consistent checksum
        sorted_events = sorted(events, key=lambda x: x['timestamp'])
        
        # Create deterministic hash
        content = json.dumps(sorted_events, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get_daily_events(self, date: str) -> List[Dict]:
        """Retrieve events for a specific date."""
        events_file = os.path.join(self.events_dir, f'events_{date}.jsonl')
        
        if not os.path.exists(events_file):
            return []
        
        events = []
        try:
            with open(events_file, 'r') as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        except Exception as e:
            logger.error(f"Error reading daily events {date}: {e}")
            
        return events
    
    def get_monthly_ledger(self, month: str) -> Optional[Dict]:
        """Retrieve monthly ledger with verification."""
        ledger_file = os.path.join(self.ledger_dir, f'ledger_{month}.json')
        
        if not os.path.exists(ledger_file):
            return None
        
        try:
            with open(ledger_file, 'r') as f:
                ledger = json.load(f)
            
            # Verify ledger integrity
            if self._verify_ledger_integrity(ledger):
                return ledger
            else:
                logger.error(f"Ledger integrity check failed for {month}")
                return None
                
        except Exception as e:
            logger.error(f"Error reading monthly ledger {month}: {e}")
            return None
    
    def _verify_ledger_integrity(self, ledger: Dict) -> bool:
        """Verify ledger checksum chain integrity."""
        try:
            # Verify latest checksum
            if ledger["checksums"]:
                latest_checksum = ledger["checksums"][-1]
                calculated_checksum = self._calculate_ledger_checksum(ledger["events"])
                
                if latest_checksum["checksum"] != calculated_checksum:
                    logger.error("Ledger checksum mismatch detected")
                    return False
            
            # Verify checksum chain
            for i, checksum in enumerate(ledger["checksums"]):
                if i > 0:
                    prev_checksum = ledger["checksums"][i-1]["checksum"]
                    if checksum["previous_checksum"] != prev_checksum:
                        logger.error(f"Checksum chain break at index {i}")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error verifying ledger integrity: {e}")
            return False
    
    def flush_all(self):
        """Force flush all buffered events."""
        with self.lock:
            self._flush_buffer()
    
    def get_usage_stats(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Get usage statistics for date range."""
        try:
            from datetime import datetime, timedelta
            
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            
            total_events = 0
            unique_dids = set()
            site_stats = {}
            
            current = start
            while current <= end:
                date_str = current.strftime('%Y-%m-%d')
                events = self.get_daily_events(date_str)
                
                for event in events:
                    total_events += 1
                    unique_dids.add(event['subject_did_hash'])
                    
                    site_id = event['site_id']
                    if site_id not in site_stats:
                        site_stats[site_id] = 0
                    site_stats[site_id] += 1
                
                current += timedelta(days=1)
            
            return {
                "date_range": f"{start_date} to {end_date}",
                "total_verifications": total_events,
                "unique_humans": len(unique_dids),
                "sites": len(site_stats),
                "site_breakdown": site_stats
            }
            
        except Exception as e:
            logger.error(f"Error calculating usage stats: {e}")
            return {}

# Global usage logger instance
_usage_logger = None

def get_usage_logger() -> UsageEventLogger:
    """Get or create global usage logger instance."""
    global _usage_logger
    if _usage_logger is None:
        _usage_logger = UsageEventLogger()
    return _usage_logger

def log_verification_success(site_id: str, subject_did: str, 
                           timestamp: float = None, metadata: Dict = None) -> str:
    """Convenience function to log verification success."""
    return get_usage_logger().log_verification_success(
        site_id, subject_did, timestamp, metadata
    ) 