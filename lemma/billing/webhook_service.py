#!/usr/bin/env python3
"""
📡 LEMMA WEBHOOK SERVICE
========================
Sends billing notifications to customers with signature verification
Implements retry logic and webhook management for billing events
"""

import json
import os
import time
import hmac
import hashlib
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from threading import Lock, Thread
import queue
import schedule

logger = logging.getLogger(__name__)

class WebhookService:
    """Production-grade webhook service for billing notifications."""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.environ.get('STORAGE_DIR', '.lemma_enterprise')
        self.webhooks_dir = os.path.join(self.storage_dir, 'billing', 'webhooks')
        self.webhook_queue = queue.Queue()
        self.lock = Lock()
        
        # Ensure directories exist
        os.makedirs(self.webhooks_dir, exist_ok=True)
        
        # Webhook configuration
        self.webhook_secret = os.environ.get('LEMMA_WEBHOOK_SECRET', 'lemma_webhook_secret_2025')
        self.max_retries = 3
        self.retry_delays = [30, 300, 1800]  # 30s, 5m, 30m
        self.timeout = 30  # 30 second timeout
        
        # Load webhook endpoints
        self.webhook_endpoints = self._load_webhook_endpoints()
        
        # Start webhook worker
        self.worker_thread = None
        self.start_webhook_worker()
    
    def _load_webhook_endpoints(self) -> Dict[str, Dict[str, Any]]:
        """Load customer webhook endpoint configurations."""
        endpoints_file = os.path.join(self.webhooks_dir, 'endpoints.json')
        
        if not os.path.exists(endpoints_file):
            # Create default configuration
            default_endpoints = {
                "default_site": {
                    "billing_summary": "https://example.com/webhooks/lemma/billing",
                    "invoice_generated": "https://example.com/webhooks/lemma/invoice",
                    "payment_reminder": "https://example.com/webhooks/lemma/reminder",
                    "active": False  # Disabled by default
                }
            }
            
            with open(endpoints_file, 'w') as f:
                json.dump(default_endpoints, f, indent=2)
            
            return default_endpoints
        
        try:
            with open(endpoints_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading webhook endpoints: {e}")
            return {}
    
    def register_webhook_endpoint(self, site_id: str, webhook_type: str, url: str, 
                                active: bool = True) -> bool:
        """Register a webhook endpoint for a customer site."""
        try:
            if site_id not in self.webhook_endpoints:
                self.webhook_endpoints[site_id] = {}
            
            self.webhook_endpoints[site_id][webhook_type] = url
            self.webhook_endpoints[site_id]["active"] = active
            
            # Save to disk
            endpoints_file = os.path.join(self.webhooks_dir, 'endpoints.json')
            with open(endpoints_file, 'w') as f:
                json.dump(self.webhook_endpoints, f, indent=2)
            
            logger.info(f"Registered webhook for {site_id}: {webhook_type} -> {url}")
            return True
            
        except Exception as e:
            logger.error(f"Error registering webhook endpoint: {e}")
            return False
    
    def start_webhook_worker(self):
        """Start the webhook processing worker thread."""
        if self.worker_thread and self.worker_thread.is_alive():
            return
        
        def process_webhooks():
            while True:
                try:
                    # Get webhook from queue (blocking)
                    webhook_data = self.webhook_queue.get(timeout=60)
                    
                    if webhook_data is None:  # Shutdown signal
                        break
                    
                    self._process_webhook(webhook_data)
                    self.webhook_queue.task_done()
                    
                except queue.Empty:
                    continue  # Check for shutdown
                except Exception as e:
                    logger.error(f"Error in webhook worker: {e}")
        
        self.worker_thread = Thread(target=process_webhooks, daemon=True)
        self.worker_thread.start()
        logger.info("Webhook worker thread started")
    
    def send_billing_summary_webhook(self, site_id: str, billing_data: Dict[str, Any]) -> bool:
        """Send billing summary webhook to customer."""
        try:
            webhook_payload = {
                "event_type": "billing.summary",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "site_id": billing_data["site_id"],
                    "month": billing_data["month"],
                    "currency": billing_data["currency"],
                    "usage": billing_data["usage"],
                    "charges": billing_data["charges"],
                    "billing_date": billing_data["billing_date"],
                    "due_date": billing_data["due_date"]
                }
            }
            
            return self._queue_webhook(site_id, "billing_summary", webhook_payload)
            
        except Exception as e:
            logger.error(f"Error sending billing summary webhook: {e}")
            return False
    
    def send_invoice_generated_webhook(self, site_id: str, billing_data: Dict[str, Any], 
                                     invoice_files: Dict[str, str]) -> bool:
        """Send invoice generated webhook to customer."""
        try:
            webhook_payload = {
                "event_type": "invoice.generated",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "site_id": billing_data["site_id"],
                    "month": billing_data["month"],
                    "total_amount": billing_data["charges"]["total_amount"],
                    "currency": billing_data["currency"],
                    "invoice_files": list(invoice_files.keys()),  # pdf, csv, json
                    "due_date": billing_data["due_date"]
                }
            }
            
            return self._queue_webhook(site_id, "invoice_generated", webhook_payload)
            
        except Exception as e:
            logger.error(f"Error sending invoice generated webhook: {e}")
            return False
    
    def send_payment_reminder_webhook(self, site_id: str, billing_data: Dict[str, Any], 
                                    days_overdue: int) -> bool:
        """Send payment reminder webhook to customer."""
        try:
            webhook_payload = {
                "event_type": "payment.reminder",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "site_id": billing_data["site_id"],
                    "month": billing_data["month"],
                    "total_amount": billing_data["charges"]["total_amount"],
                    "currency": billing_data["currency"],
                    "due_date": billing_data["due_date"],
                    "days_overdue": days_overdue,
                    "reminder_type": "payment_overdue"
                }
            }
            
            return self._queue_webhook(site_id, "payment_reminder", webhook_payload)
            
        except Exception as e:
            logger.error(f"Error sending payment reminder webhook: {e}")
            return False
    
    def _queue_webhook(self, site_id: str, webhook_type: str, payload: Dict[str, Any]) -> bool:
        """Queue a webhook for processing."""
        try:
            # Check if site has webhook configured
            site_config = self.webhook_endpoints.get(site_id)
            if not site_config or not site_config.get("active", False):
                logger.info(f"No active webhook configured for site {site_id}")
                return False
            
            webhook_url = site_config.get(webhook_type)
            if not webhook_url:
                logger.info(f"No {webhook_type} webhook configured for site {site_id}")
                return False
            
            webhook_data = {
                "site_id": site_id,
                "webhook_type": webhook_type,
                "url": webhook_url,
                "payload": payload,
                "attempt": 0,
                "max_retries": self.max_retries,
                "created_at": time.time()
            }
            
            self.webhook_queue.put(webhook_data)
            logger.info(f"Queued {webhook_type} webhook for {site_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error queueing webhook: {e}")
            return False
    
    def _process_webhook(self, webhook_data: Dict[str, Any]):
        """Process a single webhook with retry logic."""
        site_id = webhook_data["site_id"]
        webhook_type = webhook_data["webhook_type"]
        url = webhook_data["url"]
        payload = webhook_data["payload"]
        attempt = webhook_data["attempt"]
        
        try:
            # Generate webhook signature
            payload_json = json.dumps(payload, separators=(',', ':'))
            signature = self._generate_webhook_signature(payload_json)
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json',
                'X-Lemma-Signature': signature,
                'X-Lemma-Event': webhook_data["webhook_type"],
                'X-Lemma-Timestamp': str(int(time.time())),
                'User-Agent': 'Lemma-Webhooks/1.0'
            }
            
            # Send webhook
            response = requests.post(
                url,
                data=payload_json,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code in [200, 201, 202]:
                # Success
                self._log_webhook_success(webhook_data, response.status_code)
                logger.info(f"Webhook delivered successfully: {webhook_type} to {site_id}")
                return
            else:
                # HTTP error
                raise requests.exceptions.HTTPError(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            # Handle failure with retry logic
            attempt += 1
            webhook_data["attempt"] = attempt
            
            self._log_webhook_failure(webhook_data, str(e))
            
            if attempt < self.max_retries:
                # Schedule retry
                retry_delay = self.retry_delays[min(attempt - 1, len(self.retry_delays) - 1)]
                logger.warning(f"Webhook failed (attempt {attempt}), retrying in {retry_delay}s: {e}")
                
                # Re-queue with delay (in a real system, use a proper job queue)
                Thread(
                    target=self._delayed_retry,
                    args=(webhook_data, retry_delay),
                    daemon=True
                ).start()
            else:
                # Max retries exceeded
                logger.error(f"Webhook failed permanently after {attempt} attempts: {e}")
                self._log_webhook_permanent_failure(webhook_data, str(e))
    
    def _delayed_retry(self, webhook_data: Dict[str, Any], delay: int):
        """Delay and retry webhook delivery."""
        time.sleep(delay)
        self.webhook_queue.put(webhook_data)
    
    def _generate_webhook_signature(self, payload: str) -> str:
        """Generate HMAC signature for webhook verification."""
        signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    def _log_webhook_success(self, webhook_data: Dict[str, Any], status_code: int):
        """Log successful webhook delivery."""
        log_entry = {
            "timestamp": time.time(),
            "site_id": webhook_data["site_id"],
            "webhook_type": webhook_data["webhook_type"],
            "url": webhook_data["url"],
            "status": "success",
            "status_code": status_code,
            "attempt": webhook_data["attempt"],
            "payload_size": len(json.dumps(webhook_data["payload"]))
        }
        
        self._write_webhook_log(log_entry)
    
    def _log_webhook_failure(self, webhook_data: Dict[str, Any], error: str):
        """Log webhook delivery failure."""
        log_entry = {
            "timestamp": time.time(),
            "site_id": webhook_data["site_id"],
            "webhook_type": webhook_data["webhook_type"],
            "url": webhook_data["url"],
            "status": "failure",
            "error": error,
            "attempt": webhook_data["attempt"],
            "max_retries": webhook_data["max_retries"]
        }
        
        self._write_webhook_log(log_entry)
    
    def _log_webhook_permanent_failure(self, webhook_data: Dict[str, Any], error: str):
        """Log permanent webhook failure."""
        log_entry = {
            "timestamp": time.time(),
            "site_id": webhook_data["site_id"],
            "webhook_type": webhook_data["webhook_type"],
            "url": webhook_data["url"],
            "status": "permanent_failure",
            "error": error,
            "total_attempts": webhook_data["attempt"],
            "created_at": webhook_data["created_at"]
        }
        
        self._write_webhook_log(log_entry)
    
    def _write_webhook_log(self, log_entry: Dict[str, Any]):
        """Write webhook log entry to file."""
        try:
            log_date = datetime.fromtimestamp(log_entry["timestamp"], timezone.utc).strftime('%Y-%m-%d')
            log_file = os.path.join(self.webhooks_dir, f'webhook_log_{log_date}.jsonl')
            
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry, separators=(',', ':')) + '\n')
                
        except Exception as e:
            logger.error(f"Error writing webhook log: {e}")
    
    def get_webhook_stats(self, site_id: str = None, days: int = 7) -> Dict[str, Any]:
        """Get webhook delivery statistics."""
        try:
            stats = {
                "total_webhooks": 0,
                "successful_deliveries": 0,
                "failed_deliveries": 0,
                "permanent_failures": 0,
                "success_rate": 0.0,
                "by_type": {},
                "by_site": {}
            }
            
            # Read logs from the last N days
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                log_file = os.path.join(self.webhooks_dir, f'webhook_log_{date_str}.jsonl')
                
                if os.path.exists(log_file):
                    with open(log_file, 'r') as f:
                        for line in f:
                            if line.strip():
                                entry = json.loads(line)
                                
                                # Filter by site if specified
                                if site_id and entry.get("site_id") != site_id:
                                    continue
                                
                                stats["total_webhooks"] += 1
                                
                                # Count by status
                                status = entry.get("status")
                                if status == "success":
                                    stats["successful_deliveries"] += 1
                                elif status == "failure":
                                    stats["failed_deliveries"] += 1
                                elif status == "permanent_failure":
                                    stats["permanent_failures"] += 1
                                
                                # Count by type
                                webhook_type = entry.get("webhook_type", "unknown")
                                if webhook_type not in stats["by_type"]:
                                    stats["by_type"][webhook_type] = {"total": 0, "success": 0}
                                stats["by_type"][webhook_type]["total"] += 1
                                if status == "success":
                                    stats["by_type"][webhook_type]["success"] += 1
                                
                                # Count by site
                                entry_site = entry.get("site_id", "unknown")
                                if entry_site not in stats["by_site"]:
                                    stats["by_site"][entry_site] = {"total": 0, "success": 0}
                                stats["by_site"][entry_site]["total"] += 1
                                if status == "success":
                                    stats["by_site"][entry_site]["success"] += 1
                
                current_date += timedelta(days=1)
            
            # Calculate success rate
            if stats["total_webhooks"] > 0:
                stats["success_rate"] = stats["successful_deliveries"] / stats["total_webhooks"] * 100
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting webhook stats: {e}")
            return {"error": str(e)}
    
    def test_webhook_endpoint(self, site_id: str, webhook_type: str) -> Dict[str, Any]:
        """Test a webhook endpoint with a sample payload."""
        try:
            site_config = self.webhook_endpoints.get(site_id)
            if not site_config:
                return {"success": False, "error": f"No webhook configuration for site {site_id}"}
            
            webhook_url = site_config.get(webhook_type)
            if not webhook_url:
                return {"success": False, "error": f"No {webhook_type} webhook configured"}
            
            # Create test payload
            test_payload = {
                "event_type": f"{webhook_type}.test",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "site_id": site_id,
                    "test": True,
                    "message": "This is a test webhook from Lemma"
                }
            }
            
            # Send test webhook
            payload_json = json.dumps(test_payload, separators=(',', ':'))
            signature = self._generate_webhook_signature(payload_json)
            
            headers = {
                'Content-Type': 'application/json',
                'X-Lemma-Signature': signature,
                'X-Lemma-Event': f"{webhook_type}.test",
                'X-Lemma-Timestamp': str(int(time.time())),
                'User-Agent': 'Lemma-Webhooks/1.0'
            }
            
            response = requests.post(
                webhook_url,
                data=payload_json,
                headers=headers,
                timeout=self.timeout
            )
            
            return {
                "success": response.status_code in [200, 201, 202],
                "status_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000,
                "response_text": response.text[:200] if response.text else ""
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}

# Global webhook service instance
_webhook_service = None

def get_webhook_service() -> WebhookService:
    """Get or create global webhook service instance."""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = WebhookService()
    return _webhook_service

def send_billing_summary_webhook(site_id: str, billing_data: Dict[str, Any]) -> bool:
    """Convenience function to send billing summary webhook."""
    return get_webhook_service().send_billing_summary_webhook(site_id, billing_data) 