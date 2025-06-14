"""
SRE Metrics Collection Middleware
Automatically collects latency, error rate, and other SRE metrics for all requests.
"""

import time
from flask import Flask, request, g
from typing import Any
import logging

logger = logging.getLogger(__name__)

class SREMetricsMiddleware:
    """Middleware to automatically collect SRE metrics."""
    
    def __init__(self, app: Flask = None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize middleware with Flask app."""
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        app.teardown_appcontext(self.teardown)
    
    def before_request(self):
        """Record request start time."""
        g.start_time = time.time()
        g.endpoint = request.endpoint or request.path
    
    def after_request(self, response):
        """Record metrics after request completion."""
        try:
            if hasattr(g, 'start_time'):
                # Calculate latency
                latency_ms = (time.time() - g.start_time) * 1000
                endpoint = getattr(g, 'endpoint', request.path)
                
                # Skip SRE metrics collection for static files to prevent issues
                if request.path.startswith('/static/'):
                    return response
                
                # Skip SRE metrics collection for ultra-fast paths
                if not getattr(g, 'skip_sre_metrics', False):
                    # Import here to avoid circular imports
                    from lemma.routes.sre_monitoring import metrics
                    
                    # Record latency for all requests
                    metrics.record_latency(endpoint, latency_ms)
                    
                    # Record errors (4xx and 5xx status codes)
                    if response.status_code >= 400:
                        metrics.record_error(endpoint, response.status_code)
                        logger.info(f"SRE: Recorded error {response.status_code} for {endpoint}")
                    
                    # Also record successful requests (for error rate calculation baseline)
                    elif response.status_code < 400:
                        # Record successful request for error rate baseline calculation
                        pass  # Latency recording above is sufficient for success tracking
                
                # Add performance headers for debugging (but lighter for fast paths)
                if not getattr(g, 'skip_heavy_ops', False):
                    response.headers['X-Response-Time'] = f"{latency_ms:.2f}ms"
                
        except Exception as e:
            logger.error(f"Error recording SRE metrics: {e}")
        
        return response
    
    def teardown(self, exception):
        """Cleanup after request."""
        # Clean up any request-specific data
        if hasattr(g, 'start_time'):
            delattr(g, 'start_time')
        if hasattr(g, 'endpoint'):
            delattr(g, 'endpoint')

# Helper function to integrate MAH counter updates
def update_mah_metrics():
    """Update MAH metrics from billing data."""
    try:
        from lemma.routes.sre_monitoring import metrics
        from lemma.core.analytics_service import get_analytics_service
        
        analytics = get_analytics_service()
        platform_analytics = analytics.get_platform_analytics(30)
        
        # Update total MAH from platform analytics
        total_mah = platform_analytics.get('usage', {}).get('total_verifications', 0)
        metrics.update_mah_counter('platform_total', total_mah)
        
        # Update per-customer MAH
        top_customers = platform_analytics.get('top_customers', [])
        for customer_id, usage in top_customers:
            metrics.update_mah_counter(customer_id, usage)
            
    except Exception as e:
        logger.error(f"Error updating MAH metrics: {e}")

# Helper function to update billing job status
def update_billing_job_metrics():
    """Update billing job metrics from billing system."""
    try:
        from lemma.routes.sre_monitoring import metrics
        from lemma.billing.rollup_engine import get_rollup_engine
        from datetime import datetime
        
        rollup_engine = get_rollup_engine()
        status = rollup_engine.get_status()
        
        # Update billing job status
        if status.get('last_rollup_time'):
            last_run = datetime.fromisoformat(status['last_rollup_time'])
            job_status = "completed" if status.get('rollup_running') else "idle"
            metrics.update_billing_job_status(job_status, last_run)
        else:
            metrics.update_billing_job_status("unknown")
            
    except Exception as e:
        logger.error(f"Error updating billing job metrics: {e}")

# Helper function to update revocation lag metrics
def update_revocation_metrics():
    """Update revocation lag metrics."""
    try:
        from lemma.routes.sre_monitoring import metrics
        from lemma.core.revocation_automation import get_automation_manager
        
        manager = get_automation_manager()
        status = manager.get_status()
        
        # Calculate lag based on last update
        if status.get('last_cascade_rebuild'):
            from datetime import datetime
            last_rebuild = datetime.fromisoformat(status['last_cascade_rebuild'])
            lag_seconds = (datetime.now() - last_rebuild).total_seconds()
            metrics.update_revocation_lag(lag_seconds)
        
    except Exception as e:
        logger.error(f"Error updating revocation metrics: {e}")

# Background task to update metrics periodically
import threading
import time as time_module

class MetricsUpdater:
    """Background metrics updater."""
    
    def __init__(self, interval=60):  # Update every minute
        self.interval = interval
        self.running = False
        self.thread = None
    
    def start(self):
        """Start the metrics updater."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._update_loop, daemon=True)
            self.thread.start()
            logger.info("SRE metrics updater started")
    
    def stop(self):
        """Stop the metrics updater."""
        self.running = False
        if self.thread:
            self.thread.join()
            logger.info("SRE metrics updater stopped")
    
    def _update_loop(self):
        """Main update loop."""
        while self.running:
            try:
                update_mah_metrics()
                update_billing_job_metrics()
                update_revocation_metrics()
            except Exception as e:
                logger.error(f"Error in metrics update loop: {e}")
            
            time_module.sleep(self.interval)

# Global metrics updater instance
metrics_updater = MetricsUpdater()

def init_sre_monitoring(app: Flask):
    """Initialize complete SRE monitoring for the app."""
    # Add metrics middleware
    middleware = SREMetricsMiddleware(app)
    
    # Start background metrics updater
    metrics_updater.start()
    
    logger.info("SRE monitoring initialized successfully")
    
    return middleware 