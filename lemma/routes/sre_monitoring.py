"""
SRE Monitoring and Observability Module
Comprehensive monitoring for Lemma Enterprise SRE requirements
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, deque
from flask import Blueprint, jsonify, request, current_app
import logging
import threading
from dataclasses import dataclass, asdict

from lemma.routes.api import require_api_key
from lemma.monitoring.alert_manager import get_alert_manager

# Simple rate limiting decorator
def rate_limit(f):
    """Simple rate limiting placeholder."""
    return f

# Create blueprint
sre_bp = Blueprint('sre_monitoring', __name__, url_prefix='/api/sre')
logger = logging.getLogger(__name__)

# Global metrics collectors
class MetricsCollector:
    """Thread-safe metrics collection for SRE monitoring."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.latency_samples = defaultdict(lambda: deque(maxlen=1000))
        self.error_rates = defaultdict(lambda: deque(maxlen=300))  # 5-minute windows
        self.mah_counters = defaultdict(int)
        self.wallet_js_errors = deque(maxlen=1000)
        self.billing_job_status = {"last_run": None, "status": "unknown"}
        self.bloom_filter_metrics = {"size": 0, "last_update": None}
        self.revocation_lag = {"last_sync": None, "lag_seconds": 0}
        
    def record_latency(self, endpoint: str, latency_ms: float):
        """Record latency sample for endpoint."""
        with self._lock:
            timestamp = time.time()
            self.latency_samples[endpoint].append({
                "timestamp": timestamp,
                "latency_ms": latency_ms
            })
    
    def record_error(self, endpoint: str, error_code: int):
        """Record error for 5-minute error rate tracking."""
        with self._lock:
            timestamp = time.time()
            window_start = timestamp - 300  # 5 minutes
            
            # Clean old entries
            while (self.error_rates[endpoint] and 
                   self.error_rates[endpoint][0]["timestamp"] < window_start):
                self.error_rates[endpoint].popleft()
            
            self.error_rates[endpoint].append({
                "timestamp": timestamp,
                "error_code": error_code
            })
    
    def update_mah_counter(self, site_id: str, count: int):
        """Update Monthly Active Humans counter."""
        with self._lock:
            self.mah_counters[site_id] = count
    
    def record_wallet_js_error(self, error_data: Dict):
        """Record wallet JS error."""
        with self._lock:
            error_data["timestamp"] = time.time()
            self.wallet_js_errors.append(error_data)
    
    def update_billing_job_status(self, status: str, last_run: Optional[datetime] = None):
        """Update billing job status."""
        with self._lock:
            self.billing_job_status["status"] = status
            if last_run:
                self.billing_job_status["last_run"] = last_run.isoformat()
    
    def update_bloom_filter_metrics(self, size: int):
        """Update Bloom filter metrics."""
        with self._lock:
            self.bloom_filter_metrics["size"] = size
            self.bloom_filter_metrics["last_update"] = datetime.now().isoformat()
    
    def update_revocation_lag(self, lag_seconds: float):
        """Update revocation synchronization lag."""
        with self._lock:
            self.revocation_lag["lag_seconds"] = lag_seconds
            self.revocation_lag["last_sync"] = datetime.now().isoformat()

# Global metrics instance
metrics = MetricsCollector()

@dataclass
class AlertRule:
    """Alert rule configuration."""
    name: str
    condition: str
    threshold: float
    message: str
    enabled: bool = True

class AlertManager:
    """Alert manager for SRE monitoring."""
    
    def __init__(self):
        self.rules = [
            AlertRule(
                name="error_rate_5min",
                condition="error_rate_5min >= 0.01",  # 1%
                threshold=0.01,
                message="5-minute error rate ≥ 1%"
            ),
            AlertRule(
                name="bloom_filter_size",
                condition="bloom_filter_size > 4 * median",
                threshold=4.0,
                message="Bloom filter size > 4× median"
            ),
            AlertRule(
                name="billing_rollup_deadline",
                condition="billing_rollup not completed by 02:00 UTC",
                threshold=0,
                message="Billing roll-up job not completed by 02:00 UTC"
            ),
            AlertRule(
                name="p95_latency",
                condition="p95_latency > 250",
                threshold=250.0,
                message="P95 latency > 250ms"
            )
        ]
        self.alerts_history = deque(maxlen=1000)
    
    def check_alerts(self) -> List[Dict]:
        """Check all alert rules and return triggered alerts."""
        triggered = []
        
        # Check 5-minute error rate
        for endpoint, errors in metrics.error_rates.items():
            if len(errors) > 0:
                error_rate = len(errors) / 300.0  # Errors per second over 5 minutes
                if error_rate >= 0.01:  # 1% error rate
                    triggered.append({
                        "rule": "error_rate_5min",
                        "endpoint": endpoint,
                        "value": error_rate,
                        "message": f"Error rate {error_rate:.2%} on {endpoint}",
                        "timestamp": datetime.now().isoformat()
                    })
        
        # Check Bloom filter size (simplified - would need historical median)
        bloom_size = metrics.bloom_filter_metrics["size"]
        if bloom_size > 10000:  # Simplified threshold
            triggered.append({
                "rule": "bloom_filter_size",
                "value": bloom_size,
                "message": f"Bloom filter size {bloom_size} exceeds threshold",
                "timestamp": datetime.now().isoformat()
            })
        
        # Check billing job deadline (02:00 UTC)
        now = datetime.utcnow()
        if now.hour > 2 and metrics.billing_job_status["status"] != "completed":
            if metrics.billing_job_status["last_run"]:
                last_run = datetime.fromisoformat(metrics.billing_job_status["last_run"])
                if last_run.date() < now.date():
                    triggered.append({
                        "rule": "billing_rollup_deadline",
                        "message": "Billing rollup job not completed by 02:00 UTC deadline",
                        "timestamp": datetime.now().isoformat()
                    })
        
        # Store alerts history
        for alert in triggered:
            self.alerts_history.append(alert)
        
        return triggered

alert_manager = AlertManager()

# SRE Dashboard Endpoints

@sre_bp.route('/dashboard/metrics', methods=['GET'])
@require_api_key
@rate_limit
def get_sre_dashboard():
    """Comprehensive SRE dashboard metrics."""
    try:
        dashboard_data = {
            "latency_metrics": get_latency_dashboard(),
            "error_rate_metrics": get_error_rate_dashboard(),
            "mah_counters": get_mah_dashboard(),
            "revocation_lag": get_revocation_lag_dashboard(),
            "wallet_js_errors": get_wallet_js_errors_dashboard(),
            "bloom_filter_metrics": get_bloom_filter_dashboard(),
            "billing_job_status": get_billing_job_dashboard(),
            "alerts": alert_manager.check_alerts(),
            "timestamp": datetime.now().isoformat()
        }
        
        return jsonify({
            "success": True,
            "dashboard": dashboard_data
        })
        
    except Exception as e:
        logger.error(f"Error generating SRE dashboard: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@sre_bp.route('/metrics/latency', methods=['GET'])
@require_api_key
@rate_limit
def get_latency_dashboard():
    """Latency monitoring dashboard."""
    endpoint_filter = request.args.get('endpoint')
    time_range = int(request.args.get('time_range', 3600))  # 1 hour default
    
    cutoff_time = time.time() - time_range
    latency_stats = {}
    
    for endpoint, samples in metrics.latency_samples.items():
        if endpoint_filter and endpoint != endpoint_filter:
            continue
            
        recent_samples = [s for s in samples if s["timestamp"] >= cutoff_time]
        
        if recent_samples:
            latencies = [s["latency_ms"] for s in recent_samples]
            latencies.sort()
            
            latency_stats[endpoint] = {
                "sample_count": len(latencies),
                "avg_ms": sum(latencies) / len(latencies),
                "min_ms": min(latencies),
                "max_ms": max(latencies),
                "p50_ms": latencies[len(latencies) // 2],
                "p95_ms": latencies[int(len(latencies) * 0.95)],
                "p99_ms": latencies[int(len(latencies) * 0.99)],
                "sla_breach": latencies[int(len(latencies) * 0.95)] > 250
            }
    
    return {
        "latency_stats": latency_stats,
        "time_range_seconds": time_range,
        "timestamp": datetime.now().isoformat()
    }

@sre_bp.route('/metrics/errors', methods=['GET'])
@require_api_key
@rate_limit
def get_error_rate_dashboard():
    """Error rate monitoring dashboard."""
    error_stats = {}
    
    for endpoint, errors in metrics.error_rates.items():
        if errors:
            # Calculate 5-minute error rate
            current_time = time.time()
            recent_errors = [e for e in errors if current_time - e["timestamp"] <= 300]
            error_rate = len(recent_errors) / 300.0  # Errors per second
            
            error_codes = defaultdict(int)
            for error in recent_errors:
                error_codes[error["error_code"]] += 1
            
            error_stats[endpoint] = {
                "error_rate_5min": error_rate,
                "error_rate_percent": error_rate * 100,
                "total_errors_5min": len(recent_errors),
                "error_codes": dict(error_codes),
                "alert_triggered": error_rate >= 0.01
            }
    
    return {
        "error_stats": error_stats,
        "timestamp": datetime.now().isoformat()
    }

@sre_bp.route('/metrics/mah', methods=['GET'])
@require_api_key
@rate_limit
def get_mah_dashboard():
    """Monthly Active Humans dashboard."""
    return {
        "mah_counters": dict(metrics.mah_counters),
        "total_mah": sum(metrics.mah_counters.values()),
        "active_sites": len(metrics.mah_counters),
        "timestamp": datetime.now().isoformat()
    }

@sre_bp.route('/metrics/revocation-lag', methods=['GET'])
@require_api_key
@rate_limit
def get_revocation_lag_dashboard():
    """Revocation push lag dashboard."""
    return {
        "revocation_lag": metrics.revocation_lag,
        "timestamp": datetime.now().isoformat()
    }

@sre_bp.route('/metrics/wallet-errors', methods=['GET'])
@require_api_key
@rate_limit
def get_wallet_js_errors_dashboard():
    """Wallet JS errors dashboard."""
    time_range = int(request.args.get('time_range', 3600))  # 1 hour default
    cutoff_time = time.time() - time_range
    
    recent_errors = [e for e in metrics.wallet_js_errors if e["timestamp"] >= cutoff_time]
    
    error_types = defaultdict(int)
    error_timeline = defaultdict(int)
    
    for error in recent_errors:
        error_types[error.get("type", "unknown")] += 1
        # Group by hour for timeline
        hour_bucket = int(error["timestamp"] // 3600) * 3600
        error_timeline[hour_bucket] += 1
    
    return {
        "total_errors": len(recent_errors),
        "error_types": dict(error_types),
        "error_timeline": dict(error_timeline),
        "time_range_seconds": time_range,
        "timestamp": datetime.now().isoformat()
    }

@sre_bp.route('/metrics/bloom-filter', methods=['GET'])
@require_api_key
@rate_limit
def get_bloom_filter_dashboard():
    """Bloom filter monitoring dashboard."""
    return {
        "bloom_filter_metrics": metrics.bloom_filter_metrics,
        "timestamp": datetime.now().isoformat()
    }

@sre_bp.route('/metrics/billing-jobs', methods=['GET'])
@require_api_key
@rate_limit
def get_billing_job_dashboard():
    """Billing job monitoring dashboard."""
    # Check if job should have run by now
    now = datetime.utcnow()
    deadline_missed = False
    
    if now.hour >= 2:  # After 02:00 UTC
        if metrics.billing_job_status["last_run"]:
            last_run = datetime.fromisoformat(metrics.billing_job_status["last_run"])
            if last_run.date() < now.date():
                deadline_missed = True
        else:
            deadline_missed = True
    
    return {
        "billing_job_status": metrics.billing_job_status,
        "deadline_missed": deadline_missed,
        "next_deadline": f"{now.strftime('%Y-%m-%d')} 02:00:00 UTC",
        "timestamp": datetime.now().isoformat()
    }

# Alert Management Endpoints

@sre_bp.route('/alerts/current', methods=['GET'])
@require_api_key
@rate_limit
def get_current_alerts():
    """Get all currently active alerts"""
    try:
        alert_manager = get_alert_manager()
        active_alerts = alert_manager.get_active_alerts()
        
        return jsonify({
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "active_alerts": active_alerts,
            "alert_count": len(active_alerts)
        })
    except Exception as e:
        logger.error(f"Error getting current alerts: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to retrieve current alerts"
        }), 500

@sre_bp.route('/alerts/history', methods=['GET'])
@require_api_key
@rate_limit
def get_alert_history():
    """Get alert history"""
    try:
        limit = request.args.get('limit', 100, type=int)
        alert_manager = get_alert_manager()
        alert_history = alert_manager.get_alert_history(limit=limit)
        
        return jsonify({
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "alert_history": alert_history,
            "history_count": len(alert_history)
        })
    except Exception as e:
        logger.error(f"Error getting alert history: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to retrieve alert history"
        }), 500

@sre_bp.route('/alerts/rules', methods=['GET'])
@require_api_key
@rate_limit
def get_alert_rules():
    """Get configured alert rules and thresholds"""
    try:
        alert_manager = get_alert_manager()
        
        rules = [
            {
                "id": "verify_error_rate",
                "name": "Verify Error Rate High",
                "threshold": "≥ 1% for 5 min",
                "severity": "critical",
                "auto_action": "Create status-page incident",
                "description": "Notify SRE-OnCall when verification error rate exceeds 1% for 5 minutes"
            },
            {
                "id": "p95_latency",
                "name": "P95 Latency High", 
                "threshold": "> 250ms for 15 min",
                "severity": "warning",
                "auto_action": "Scale pods / CDN purge",
                "description": "Auto-scale and purge CDN when P95 latency exceeds 250ms for 15 minutes"
            },
            {
                "id": "bloom_filter_issue",
                "name": "Bloom Filter Issue",
                "threshold": "Download fail or size > 4× median",
                "severity": "critical", 
                "auto_action": "Roll back to previous epoch",
                "description": "Auto-rollback bloom filter on download failure or size anomaly"
            },
            {
                "id": "billing_rollup_miss",
                "name": "Billing Rollup Missed",
                "threshold": "Misses 02:00 UTC",
                "severity": "critical",
                "auto_action": "Page Billing-Ops",
                "description": "Page billing operations team when rollup misses 02:00 UTC deadline"
            },
            {
                "id": "secrets_overdue",
                "name": "Secrets Rotation Overdue",
                "threshold": "> 90 days",
                "severity": "warning",
                "auto_action": "Slack #sec-ops",
                "description": "Notify security operations when secrets rotation is overdue"
            }
        ]
        
        return jsonify({
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "alert_rules": rules,
            "rule_count": len(rules)
        })
    except Exception as e:
        logger.error(f"Error getting alert rules: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to retrieve alert rules"
        }), 500

@sre_bp.route('/alerts/run-check', methods=['POST'])
def run_alert_check():
    """Manually trigger alert monitoring cycle"""
    try:
        alert_manager = get_alert_manager()
        results = alert_manager.run_monitoring_cycle()
        
        return jsonify({
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "monitoring_results": results
        })
    except Exception as e:
        logger.error(f"Error running alert check: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to run alert check"
        }), 500

@sre_bp.route('/alerts/resolve/<alert_id>', methods=['POST'])
def resolve_alert(alert_id):
    """Manually resolve an active alert"""
    try:
        alert_manager = get_alert_manager()
        success = alert_manager.resolve_alert(alert_id)
        
        if success:
            return jsonify({
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "message": f"Alert {alert_id} resolved successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Alert {alert_id} not found or already resolved"
            }), 404
    except Exception as e:
        logger.error(f"Error resolving alert {alert_id}: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to resolve alert"
        }), 500

@sre_bp.route('/alerts/test-pagerduty', methods=['POST'])
def test_pagerduty_integration():
    """Test PagerDuty integration with a test alert"""
    try:
        from lemma.monitoring.alert_manager import Alert, AlertSeverity, AlertStatus
        
        # Create a test alert
        test_alert = Alert(
            id="test_alert",
            name="Test Alert",
            description="This is a test alert to verify PagerDuty integration",
            severity=AlertSeverity.INFO,
            status=AlertStatus.ACTIVE,
            threshold="Test threshold",
            current_value="Test value",
            triggered_at=datetime.utcnow(),
            auto_action="Test action"
        )
        
        alert_manager = get_alert_manager()
        incident_id = alert_manager.pagerduty.create_incident(test_alert)
        
        if incident_id:
            return jsonify({
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "message": "PagerDuty test alert sent successfully",
                "incident_id": incident_id
            })
        else:
            return jsonify({
                "success": False,
                "error": "PagerDuty integration not configured or failed"
            }), 500
    except Exception as e:
        logger.error(f"Error testing PagerDuty integration: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to test PagerDuty integration"
        }), 500

@sre_bp.route('/alerts/monitor-status', methods=['GET'])
def get_monitor_status():
    """Get background monitoring service status"""
    try:
        from lemma.monitoring.background_monitor import get_background_monitor
        
        monitor = get_background_monitor()
        status = monitor.get_status()
        
        return jsonify({
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "monitor_status": status,
            "integrations": {
                "pagerduty_configured": bool(os.getenv('PAGERDUTY_INTEGRATION_KEY')),
                "slack_configured": bool(os.getenv('SLACK_WEBHOOK_URL')),
                "statuspage_configured": bool(os.getenv('STATUSPAGE_API_KEY'))
            }
        })
    except Exception as e:
        logger.error(f"Error getting monitor status: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get monitor status"
        }), 500

# Data Collection Endpoints

@sre_bp.route('/collect/latency', methods=['POST'])
@require_api_key
@rate_limit
def collect_latency():
    """Collect latency data."""
    data = request.get_json()
    
    endpoint = data.get('endpoint')
    latency_ms = data.get('latency_ms')
    
    if endpoint and latency_ms is not None:
        metrics.record_latency(endpoint, latency_ms)
        return jsonify({"success": True})
    
    return jsonify({"success": False, "error": "Invalid data"}), 400

@sre_bp.route('/collect/error', methods=['POST'])
@require_api_key
@rate_limit
def collect_error():
    """Collect error data."""
    data = request.get_json()
    
    endpoint = data.get('endpoint')
    error_code = data.get('error_code')
    
    if endpoint and error_code:
        metrics.record_error(endpoint, error_code)
        return jsonify({"success": True})
    
    return jsonify({"success": False, "error": "Invalid data"}), 400

@sre_bp.route('/collect/wallet-error', methods=['POST'])
def collect_wallet_js_error():
    """Collect wallet JS error (no API key required for client-side)."""
    data = request.get_json()
    
    # Validate and sanitize client data
    error_data = {
        "type": data.get('type', 'unknown'),
        "message": str(data.get('message', ''))[:500],  # Limit message length
        "url": str(data.get('url', ''))[:200],
        "user_agent": request.headers.get('User-Agent', '')[:200]
    }
    
    metrics.record_wallet_js_error(error_data)
    
    return jsonify({"success": True})

@sre_bp.route('/collect/mah', methods=['POST'])
@require_api_key
@rate_limit
def collect_mah():
    """Update MAH counter."""
    data = request.get_json()
    
    site_id = data.get('site_id')
    count = data.get('count')
    
    if site_id and count is not None:
        metrics.update_mah_counter(site_id, count)
        return jsonify({"success": True})
    
    return jsonify({"success": False, "error": "Invalid data"}), 400

# Load Test Endpoint for Performance Validation

@sre_bp.route('/loadtest/validate', methods=['POST'])
@require_api_key
@rate_limit
def validate_load_performance():
    """Validate current performance against SRE requirements."""
    # Simulate load test internally
    target_qps = request.json.get('target_qps', 100)
    duration_seconds = request.json.get('duration_seconds', 10)
    
    # This would trigger internal performance testing
    # For now, return current metrics
    current_latency = get_latency_dashboard()
    
    # Check if any endpoint has p95 > 250ms
    performance_issues = []
    for endpoint, stats in current_latency.get('latency_stats', {}).items():
        if stats.get('p95_ms', 0) > 250:
            performance_issues.append({
                "endpoint": endpoint,
                "p95_ms": stats['p95_ms'],
                "issue": "P95 latency exceeds 250ms requirement"
            })
    
    return jsonify({
        "success": True,
        "performance_validation": {
            "target_qps": target_qps,
            "duration_seconds": duration_seconds,
            "performance_issues": performance_issues,
            "meets_sla": len(performance_issues) == 0,
            "current_metrics": current_latency
        },
        "timestamp": datetime.now().isoformat()
    })

# Prometheus Metrics Export

@sre_bp.route('/metrics/prometheus', methods=['GET'])
def prometheus_metrics():
    """Export metrics in Prometheus format."""
    output = []
    
    # Add metric metadata comments for Prometheus
    output.append('# HELP lemma_latency_ms Average response latency in milliseconds')
    output.append('# TYPE lemma_latency_ms gauge')
    output.append('# HELP lemma_error_rate Error rate per second')
    output.append('# TYPE lemma_error_rate gauge')
    output.append('# HELP lemma_mah_total Total Monthly Active Humans')
    output.append('# TYPE lemma_mah_total counter')
    output.append('# HELP lemma_bloom_filter_size Current bloom filter size')
    output.append('# TYPE lemma_bloom_filter_size gauge')
    output.append('# HELP lemma_revocation_lag_seconds Revocation sync lag in seconds')
    output.append('# TYPE lemma_revocation_lag_seconds gauge')
    output.append('')
    
    # Latency metrics
    for endpoint, samples in metrics.latency_samples.items():
        if samples:
            recent_samples = [s for s in samples if time.time() - s["timestamp"] <= 300]
            if recent_samples:
                avg_latency = sum(s["latency_ms"] for s in recent_samples) / len(recent_samples)
                output.append(f'lemma_latency_ms{{endpoint="{endpoint}"}} {avg_latency:.2f}')
    
    # Error rate metrics - ensure we always export error rates even if zero
    all_endpoints = set(metrics.latency_samples.keys()) | set(metrics.error_rates.keys())
    for endpoint in all_endpoints:
        # Get recent errors (last 5 minutes)
        errors = metrics.error_rates.get(endpoint, [])
        recent_errors = [e for e in errors if time.time() - e["timestamp"] <= 300]
        
        # Calculate error rate as errors per second over 5-minute window
        error_rate = len(recent_errors) / 300.0
        output.append(f'lemma_error_rate{{endpoint="{endpoint}"}} {error_rate:.6f}')
    
    # Ensure we always have at least one error rate metric even if no endpoints have been hit
    if not all_endpoints:
        output.append('lemma_error_rate{endpoint="/api/health"} 0.000000')
    
    # MAH counters
    for site_id, count in metrics.mah_counters.items():
        output.append(f'lemma_mah_total{{site_id="{site_id}"}} {count}')
    
    # Ensure MAH metric exists even if no data
    if not metrics.mah_counters:
        output.append('lemma_mah_total{site_id="default"} 0')
    
    # Bloom filter size
    bloom_size = metrics.bloom_filter_metrics["size"]
    output.append(f'lemma_bloom_filter_size {bloom_size}')
    
    # Revocation lag
    lag = metrics.revocation_lag["lag_seconds"]
    output.append(f'lemma_revocation_lag_seconds {lag}')
    
    return '\n'.join(output), 200, {'Content-Type': 'text/plain'} 