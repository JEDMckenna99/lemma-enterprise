#!/usr/bin/env python3
"""
Background Monitoring Service
Runs continuous monitoring and alert checks
"""

import os
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from lemma.monitoring.alert_manager import get_alert_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BackgroundMonitor:
    """Background monitoring service for continuous alert checking"""
    
    def __init__(self):
        self.alert_manager = get_alert_manager()
        self.monitoring_thread = None
        self.stop_event = threading.Event()
        self.check_interval = int(os.getenv('ALERT_CHECK_INTERVAL', 60))  # Default 60 seconds
        self.is_running = False
        
    def start(self):
        """Start the background monitoring service"""
        if self.is_running:
            logger.warning("Background monitor is already running")
            return
            
        logger.info("Starting background monitoring service")
        self.stop_event.clear()
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        self.is_running = True
        
    def stop(self):
        """Stop the background monitoring service"""
        if not self.is_running:
            logger.warning("Background monitor is not running")
            return
            
        logger.info("Stopping background monitoring service")
        self.stop_event.set()
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=10)
        self.is_running = False
        
    def _monitoring_loop(self):
        """Main monitoring loop"""
        logger.info(f"Background monitoring started with {self.check_interval}s interval")
        
        while not self.stop_event.is_set():
            try:
                # Run monitoring cycle
                results = self.alert_manager.run_monitoring_cycle()
                
                # Log results
                if results.get('new_alerts', 0) > 0:
                    logger.warning(f"New alerts triggered: {results['new_alerts']}")
                
                if results.get('resolved_alerts', 0) > 0:
                    logger.info(f"Alerts resolved: {results['resolved_alerts']}")
                
                # Log periodic status
                if datetime.utcnow().minute % 5 == 0:  # Every 5 minutes
                    logger.info(f"Monitoring status: {results['active_alerts']} active alerts")
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            # Wait for next check
            self.stop_event.wait(self.check_interval)
        
        logger.info("Background monitoring stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get monitoring service status"""
        return {
            "is_running": self.is_running,
            "check_interval": self.check_interval,
            "active_alerts": len(self.alert_manager.active_alerts),
            "thread_alive": self.monitoring_thread.is_alive() if self.monitoring_thread else False,
            "last_check": datetime.utcnow().isoformat()
        }

# Global background monitor instance
background_monitor = BackgroundMonitor()

def get_background_monitor() -> BackgroundMonitor:
    """Get the global background monitor instance"""
    return background_monitor

def start_background_monitoring():
    """Start background monitoring if not already running"""
    monitor = get_background_monitor()
    if not monitor.is_running:
        monitor.start()
        logger.info("Background monitoring service started")
    return monitor

def stop_background_monitoring():
    """Stop background monitoring"""
    monitor = get_background_monitor()
    if monitor.is_running:
        monitor.stop()
        logger.info("Background monitoring service stopped")
    return monitor 