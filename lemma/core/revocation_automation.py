"""
Lemma Enterprise - Automated Revocation Management System
Provides automated key rotation, cascade rebuilding, and monitoring for production-ready revocation services.
"""

import os
import json
import time
import threading
import subprocess
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
from flask import current_app

logger = logging.getLogger(__name__)

class RevocationAutomationManager:
    """Manages automated revocation service operations for production readiness."""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.oprf_service_url = self.config.get('oprf_service_url', 'http://localhost:8080')
        self.key_rotation_days = self.config.get('key_rotation_days', 30)
        self.cascade_rebuild_hours = self.config.get('cascade_rebuild_hours', 24)
        self.monitoring_interval = self.config.get('monitoring_interval', 300)  # 5 minutes
        self.storage_dir = self.config.get('storage_dir', 'instance/data')
        
        # Threading control
        self._stop_event = threading.Event()
        self._automation_thread = None
        self._monitoring_thread = None
        
        # Metrics
        self.metrics = {
            'uptime_start': datetime.now(),
            'key_rotations': 0,
            'cascade_rebuilds': 0,
            'health_checks': 0,
            'last_key_rotation': None,
            'last_cascade_rebuild': None,
            'service_status': 'unknown'
        }

    def start_automation(self):
        """Start automated revocation service management."""
        if self._automation_thread and self._automation_thread.is_alive():
            logger.warning("Automation already running")
            return
            
        logger.info("Starting revocation automation manager")
        self._stop_event.clear()
        
        # Start automation thread
        self._automation_thread = threading.Thread(target=self._automation_loop, daemon=True)
        self._automation_thread.start()
        
        # Start monitoring thread
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()
        
        logger.info("Revocation automation started successfully")

    def stop_automation(self):
        """Stop automated revocation service management."""
        logger.info("Stopping revocation automation manager")
        self._stop_event.set()
        
        if self._automation_thread:
            self._automation_thread.join(timeout=10)
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=10)
            
        logger.info("Revocation automation stopped")

    def _automation_loop(self):
        """Main automation loop for key rotation and cascade rebuilding."""
        while not self._stop_event.is_set():
            try:
                # Check if key rotation is needed
                if self._should_rotate_keys():
                    self._rotate_keys()
                
                # Check if cascade rebuild is needed
                if self._should_rebuild_cascade():
                    self._rebuild_cascade()
                
                # Sleep for 1 hour between checks
                self._stop_event.wait(3600)
                
            except Exception as e:
                logger.error(f"Error in automation loop: {e}")
                self._stop_event.wait(300)  # Wait 5 minutes on error

    def _monitoring_loop(self):
        """Monitoring loop for service health and metrics."""
        while not self._stop_event.is_set():
            try:
                self._check_service_health()
                self._update_metrics()
                self._log_status()
                
                # Wait for monitoring interval
                self._stop_event.wait(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                self._stop_event.wait(60)  # Wait 1 minute on error

    def _should_rotate_keys(self) -> bool:
        """Check if OPRF keys should be rotated."""
        try:
            response = requests.get(f"{self.oprf_service_url}/keys", timeout=10)
            if response.status_code == 200:
                keys_data = response.json()
                active_key = keys_data.get('active_key')
                
                for key_info in keys_data.get('keys', []):
                    if key_info['key_id'] == active_key and key_info['is_active']:
                        created_at = datetime.fromisoformat(key_info['created_at'].replace('Z', '+00:00'))
                        age_days = (datetime.now() - created_at.replace(tzinfo=None)).days
                        
                        if age_days >= self.key_rotation_days:
                            logger.info(f"Key rotation needed: active key is {age_days} days old")
                            return True
                        
                return False
                
        except Exception as e:
            logger.error(f"Error checking key rotation status: {e}")
            return False

    def _rotate_keys(self) -> bool:
        """Rotate OPRF keys automatically."""
        try:
            logger.info("Starting automated key rotation")
            
            # Trigger key rotation via OPRF service API
            response = requests.post(f"{self.oprf_service_url}/admin/rotate-keys", timeout=30)
            
            if response.status_code == 200:
                self.metrics['key_rotations'] += 1
                self.metrics['last_key_rotation'] = datetime.now()
                logger.info("Key rotation completed successfully")
                
                # Trigger cascade rebuild after key rotation
                self._rebuild_cascade()
                return True
            else:
                logger.error(f"Key rotation failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error during key rotation: {e}")
            return False

    def _should_rebuild_cascade(self) -> bool:
        """Check if cascade should be rebuilt."""
        cascade_file = os.path.join(self.storage_dir, 'revocation', 'cascade.json')
        
        if not os.path.exists(cascade_file):
            return True
            
        # Check file age
        file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cascade_file))
        return file_age.total_seconds() > (self.cascade_rebuild_hours * 3600)

    def _rebuild_cascade(self) -> bool:
        """Rebuild revocation cascade automatically."""
        try:
            logger.info("Starting automated cascade rebuild")
            
            # Run cascade builder script
            result = subprocess.run(
                ['python', 'build_cascade.py', '--automated'],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                self.metrics['cascade_rebuilds'] += 1
                self.metrics['last_cascade_rebuild'] = datetime.now()
                logger.info("Cascade rebuild completed successfully")
                return True
            else:
                logger.error(f"Cascade rebuild failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Cascade rebuild timed out")
            return False
        except Exception as e:
            logger.error(f"Error during cascade rebuild: {e}")
            return False

    def _check_service_health(self):
        """Check OPRF service health and update status."""
        try:
            response = requests.get(f"{self.oprf_service_url}/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                self.metrics['service_status'] = health_data.get('status', 'unknown')
                self.metrics['health_checks'] += 1
            else:
                self.metrics['service_status'] = 'unhealthy'
                logger.warning(f"OPRF service health check failed: {response.status_code}")
                
        except Exception as e:
            self.metrics['service_status'] = 'unreachable'
            logger.error(f"OPRF service unreachable: {e}")

    def _update_metrics(self):
        """Update and persist automation metrics."""
        metrics_file = os.path.join(self.storage_dir, 'automation_metrics.json')
        os.makedirs(os.path.dirname(metrics_file), exist_ok=True)
        
        # Add computed metrics
        uptime = datetime.now() - self.metrics['uptime_start']
        computed_metrics = {
            'uptime_hours': uptime.total_seconds() / 3600,
            'uptime_days': uptime.days,
            'last_updated': datetime.now().isoformat()
        }
        
        full_metrics = {**self.metrics, **computed_metrics}
        
        # Convert datetime objects to ISO strings for JSON serialization
        for key, value in full_metrics.items():
            if isinstance(value, datetime):
                full_metrics[key] = value.isoformat()
        
        try:
            with open(metrics_file, 'w') as f:
                json.dump(full_metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save automation metrics: {e}")

    def _log_status(self):
        """Log current automation status."""
        uptime = datetime.now() - self.metrics['uptime_start']
        logger.info(
            f"Automation Status - Uptime: {uptime.days}d {uptime.seconds//3600}h, "
            f"Service: {self.metrics['service_status']}, "
            f"Key Rotations: {self.metrics['key_rotations']}, "
            f"Cascade Rebuilds: {self.metrics['cascade_rebuilds']}"
        )

    def get_status(self) -> Dict:
        """Get current automation status and metrics."""
        uptime = datetime.now() - self.metrics['uptime_start']
        
        status = {
            'automation_running': not self._stop_event.is_set(),
            'uptime_hours': uptime.total_seconds() / 3600,
            'service_status': self.metrics['service_status'],
            'key_rotations_total': self.metrics['key_rotations'],
            'cascade_rebuilds_total': self.metrics['cascade_rebuilds'],
            'health_checks_total': self.metrics['health_checks'],
            'last_key_rotation': self.metrics['last_key_rotation'].isoformat() if self.metrics['last_key_rotation'] else None,
            'last_cascade_rebuild': self.metrics['last_cascade_rebuild'].isoformat() if self.metrics['last_cascade_rebuild'] else None,
            'configuration': {
                'key_rotation_days': self.key_rotation_days,
                'cascade_rebuild_hours': self.cascade_rebuild_hours,
                'monitoring_interval': self.monitoring_interval
            }
        }
        
        return status

    def manual_key_rotation(self) -> Tuple[bool, str]:
        """Manually trigger key rotation."""
        try:
            success = self._rotate_keys()
            if success:
                return True, "Key rotation completed successfully"
            else:
                return False, "Key rotation failed - check logs for details"
        except Exception as e:
            return False, f"Key rotation error: {str(e)}"

    def manual_cascade_rebuild(self) -> Tuple[bool, str]:
        """Manually trigger cascade rebuild."""
        try:
            success = self._rebuild_cascade()
            if success:
                return True, "Cascade rebuild completed successfully"
            else:
                return False, "Cascade rebuild failed - check logs for details"
        except Exception as e:
            return False, f"Cascade rebuild error: {str(e)}"

# Global automation manager instance
automation_manager = None

def get_automation_manager() -> RevocationAutomationManager:
    """Get or create the global automation manager instance."""
    global automation_manager
    
    if automation_manager is None:
        config = {
            'oprf_service_url': os.getenv('OPRF_SERVICE_URL', 'http://localhost:8080'),
            'key_rotation_days': int(os.getenv('OPRF_ROTATION_DAYS', '30')),
            'cascade_rebuild_hours': int(os.getenv('CASCADE_REBUILD_HOURS', '24')),
            'monitoring_interval': int(os.getenv('AUTOMATION_MONITORING_INTERVAL', '300')),
            'storage_dir': os.getenv('LEMMA_STORAGE_DIR', 'instance/data')
        }
        automation_manager = RevocationAutomationManager(config)
    
    return automation_manager

def start_automation():
    """Start the revocation automation service."""
    manager = get_automation_manager()
    manager.start_automation()

def stop_automation():
    """Stop the revocation automation service."""
    if automation_manager:
        automation_manager.stop_automation() 