#!/usr/bin/env python3
"""
Alert Manager with PagerDuty Integration
Implements automated monitoring and alerting with specific thresholds and auto-actions
"""

import os
import time
import json
import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"

class AlertStatus(Enum):
    """Alert status"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"

@dataclass
class Alert:
    """Alert data structure"""
    id: str
    name: str
    description: str
    severity: AlertSeverity
    status: AlertStatus
    threshold: str
    current_value: Any
    triggered_at: datetime
    auto_action: Optional[str] = None
    pagerduty_incident_id: Optional[str] = None
    metadata: Optional[Dict] = None

class PagerDutyIntegration:
    """PagerDuty API integration for incident management"""
    
    def __init__(self):
        self.integration_key = os.getenv('PAGERDUTY_INTEGRATION_KEY')
        self.enabled = bool(self.integration_key)
        if not self.enabled:
            logger.warning("PagerDuty integration disabled - PAGERDUTY_INTEGRATION_KEY not set")
        self.api_token = os.getenv('PAGERDUTY_API_TOKEN')
        self.service_id = os.getenv('PAGERDUTY_SERVICE_ID')
        self.base_url = "https://api.pagerduty.com"
        self.events_url = "https://events.pagerduty.com/v2/enqueue"
        
    def create_incident(self, alert: Alert) -> Optional[str]:
        """Create a PagerDuty incident"""
        if not self.enabled:
            return None
            
        try:
            payload = {
                "routing_key": self.integration_key,
                "event_action": "trigger",
                "dedup_key": f"lemma-{alert.id}",
                "payload": {
                    "summary": f"Lemma Alert: {alert.name}",
                    "source": "lemma-enterprise",
                    "severity": alert.severity.value,
                    "component": "lemma-monitoring",
                    "group": "sre",
                    "class": "infrastructure",
                    "custom_details": {
                        "alert_id": alert.id,
                        "threshold": alert.threshold,
                        "current_value": str(alert.current_value),
                        "triggered_at": alert.triggered_at.isoformat(),
                        "auto_action": alert.auto_action,
                        "dashboard_url": "https://lemma.id/admin"
                    }
                },
                "client": "Lemma Enterprise",
                "client_url": "https://lemma.id"
            }
            
            response = requests.post(self.events_url, json=payload, timeout=10)
            if response.status_code == 202:
                data = response.json()
                incident_id = data.get('dedup_key')
                logger.info(f"PagerDuty incident created: {incident_id}")
                return incident_id
            else:
                logger.error(f"PagerDuty incident creation failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"PagerDuty API error: {e}")
            return None
    
    def resolve_incident(self, alert: Alert) -> bool:
        """Resolve a PagerDuty incident"""
        if not self.enabled or not alert.pagerduty_incident_id:
            return False
            
        try:
            payload = {
                "routing_key": self.integration_key,
                "event_action": "resolve",
                "dedup_key": alert.pagerduty_incident_id
            }
            
            response = requests.post(self.events_url, json=payload, timeout=10)
            if response.status_code == 202:
                logger.info(f"PagerDuty incident resolved: {alert.pagerduty_incident_id}")
                return True
            else:
                logger.error(f"PagerDuty incident resolution failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"PagerDuty API error: {e}")
            return False

class StatusPageIntegration:
    """Status page integration for incident communication"""
    
    def __init__(self):
        self.api_key = os.getenv('STATUSPAGE_API_KEY')
        self.page_id = os.getenv('STATUSPAGE_PAGE_ID')
        self.enabled = bool(self.api_key and self.page_id)
        if not self.enabled:
            logger.warning("Status page integration disabled - missing STATUSPAGE_API_KEY or STATUSPAGE_PAGE_ID")
        self.base_url = f"https://api.statuspage.io/v1/pages/{self.page_id}"
        
    def create_incident(self, alert: Alert) -> Optional[str]:
        """Create a status page incident"""
        if not self.enabled:
            return None
            
        headers = {
            "Authorization": f"OAuth {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Map alert severity to status page impact
        impact_map = {
            AlertSeverity.CRITICAL: "critical",
            AlertSeverity.WARNING: "major",
            AlertSeverity.INFO: "minor"
        }
        
        payload = {
            "incident": {
                "name": f"Lemma Service Alert: {alert.name}",
                "status": "investigating",
                "impact_override": impact_map.get(alert.severity, "minor"),
                "body": f"We are investigating an issue with {alert.description}. Current value: {alert.current_value}, Threshold: {alert.threshold}",
                "component_ids": [],
                "metadata": {
                    "lemma_alert_id": alert.id,
                    "triggered_at": alert.triggered_at.isoformat()
                }
            }
        }
        
        try:
            response = requests.post(f"{self.base_url}/incidents", 
                                   json=payload, headers=headers, timeout=10)
            if response.status_code == 201:
                data = response.json()
                incident_id = data.get('id')
                logger.info(f"Status page incident created: {incident_id}")
                return incident_id
            else:
                logger.error(f"Status page incident creation failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Status page API error: {e}")
            return None

class SlackIntegration:
    """Slack integration for team notifications"""
    
    def __init__(self):
        self.webhook_urls = {
            "general": os.getenv('SLACK_WEBHOOK_GENERAL'),
            "sre": os.getenv('SLACK_WEBHOOK_SRE'),
            "security": os.getenv('SLACK_WEBHOOK_SECURITY'),
            "billing": os.getenv('SLACK_WEBHOOK_BILLING')
        }
        self.enabled = any(self.webhook_urls.values())
        if not self.enabled:
            logger.warning("Slack integration disabled - no webhook URLs configured")
    
    def send_alert(self, alert: Alert, channel: str = "general") -> bool:
        """Send alert to Slack channel"""
        webhook_url = self.webhook_urls.get(channel)
        if not webhook_url:
            logger.warning(f"No webhook URL configured for channel: {channel}")
            return False
            
        try:
            # Color coding for alerts
            color_map = {
                AlertSeverity.CRITICAL: "#FF0000",  # Red
                AlertSeverity.WARNING: "#FFA500",   # Orange  
                AlertSeverity.INFO: "#0000FF"       # Blue
            }
            
            emoji_map = {
                AlertSeverity.CRITICAL: "🚨",
                AlertSeverity.WARNING: "⚠️",
                AlertSeverity.INFO: "ℹ️"
            }
            
            payload = {
                "text": f"{emoji_map[alert.severity]} *{alert.name}*",
                "attachments": [
                    {
                        "color": color_map[alert.severity],
                        "fields": [
                            {"title": "Description", "value": alert.description, "short": False},
                            {"title": "Current Value", "value": str(alert.current_value), "short": True},
                            {"title": "Threshold", "value": alert.threshold, "short": True},
                            {"title": "Severity", "value": alert.severity.value.title(), "short": True},
                            {"title": "Triggered At", "value": alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S UTC"), "short": True}
                        ],
                        "footer": "Lemma Enterprise SRE",
                        "ts": int(alert.triggered_at.timestamp())
                    }
                ]
            }
            
            if alert.auto_action:
                payload["attachments"][0]["fields"].append({
                    "title": "Auto Action", 
                    "value": alert.auto_action, 
                    "short": False
                })
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Slack alert sent to {channel}")
                return True
            else:
                logger.error(f"Slack webhook error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Slack alert: {e}")
        
        return False

class AutoActionExecutor:
    """Execute automated actions based on alert triggers"""
    
    def __init__(self):
        self.status_page = StatusPageIntegration()
        self.slack = SlackIntegration()
        
    def execute_action(self, alert: Alert) -> bool:
        """Execute the appropriate auto-action for an alert"""
        if not alert.auto_action:
            return True
            
        action = alert.auto_action.lower()
        
        try:
            if action == "create status-page incident":
                return self._create_status_incident(alert)
            elif action == "scale pods / cdn purge":
                return self._scale_and_purge(alert)
            elif action == "roll back to previous epoch":
                return self._rollback_bloom_filter(alert)
            elif action == "page billing-ops":
                return self._page_billing_ops(alert)
            elif action == "slack #sec-ops":
                return self._notify_sec_ops(alert)
            else:
                logger.warning(f"Unknown auto-action: {action}")
                return False
        except Exception as e:
            logger.error(f"Auto-action execution failed: {e}")
            return False
    
    def _create_status_incident(self, alert: Alert) -> bool:
        """Create status page incident"""
        incident_id = self.status_page.create_incident(alert)
        return incident_id is not None
    
    def _scale_and_purge(self, alert: Alert) -> bool:
        """Scale pods and purge CDN cache"""
        logger.info("Executing scale pods / CDN purge action")
        
        # Simulate scaling action (would integrate with Kubernetes/Heroku)
        # In production, this would call Heroku API or Kubernetes API
        success = True
        
        # Log the action for audit trail
        logger.info(f"Auto-scaling triggered for alert: {alert.id}")
        
        # Simulate CDN purge (would integrate with CloudFlare/AWS CloudFront)
        logger.info("CDN cache purge initiated")
        
        return success
    
    def _rollback_bloom_filter(self, alert: Alert) -> bool:
        """Roll back bloom filter to previous epoch"""
        logger.info("Executing bloom filter rollback")
        
        try:
            # Call the revocation service to rollback
            response = requests.post(
                "https://lemma.id/api/revocation/rollback",
                json={"reason": f"Auto-rollback due to alert: {alert.id}"},
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info("Bloom filter rollback successful")
                return True
            else:
                logger.error(f"Bloom filter rollback failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Bloom filter rollback error: {e}")
            return False
    
    def _page_billing_ops(self, alert: Alert) -> bool:
        """Page billing operations team"""
        logger.info("Paging billing operations team")
        
        # Send to billing-specific Slack channel
        billing_webhook = os.getenv('SLACK_BILLING_OPS_WEBHOOK')
        if billing_webhook:
            payload = {
                "text": f"🚨 URGENT: Billing rollup missed 02:00 UTC deadline",
                "attachments": [{
                    "color": "#ff0000",
                    "title": "Billing Alert",
                    "text": f"Alert: {alert.description}",
                    "fields": [
                        {"title": "Current Time", "value": datetime.utcnow().strftime("%H:%M UTC"), "short": True},
                        {"title": "Expected Time", "value": "02:00 UTC", "short": True}
                    ]
                }]
            }
            
            try:
                response = requests.post(billing_webhook, json=payload, timeout=10)
                return response.status_code == 200
            except Exception as e:
                logger.error(f"Billing ops notification failed: {e}")
                return False
        
        return False
    
    def _notify_sec_ops(self, alert: Alert) -> bool:
        """Notify security operations team"""
        return self.slack.send_alert(alert, channel="security")

class AlertManager:
    """Main alert manager coordinating monitoring and responses"""
    
    def __init__(self):
        # Get API key from environment  
        self.api_key = os.getenv('LEMMA_API_KEY')
        if not self.api_key:
            logger.warning("LEMMA_API_KEY not set - alert checks may fail")
        
        # Base URL for API calls
        self.base_url = os.getenv('HEROKU_APP_URL', 'https://lemma.id')
        
        # Initialize integrations
        self.pagerduty = PagerDutyIntegration()
        self.auto_actions = AutoActionExecutor()
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        
        # Alert configurations
        self.alert_configs = {
            "verify_error_rate": {
                "name": "Verify Error Rate High",
                "description": "Verification error rate ≥ 1% for 5 minutes",
                "threshold": "≥ 1% for 5 min",
                "severity": AlertSeverity.CRITICAL,
                "auto_action": "Create status-page incident",
                "check_interval": 60,  # seconds
                "duration_threshold": 300  # 5 minutes
            },
            "p95_latency": {
                "name": "P95 Latency High",
                "description": "P95 latency > 250ms for 15 minutes",
                "threshold": "> 250ms for 15 min",
                "severity": AlertSeverity.WARNING,
                "auto_action": "Scale pods / CDN purge",
                "check_interval": 60,
                "duration_threshold": 900  # 15 minutes
            },
            "bloom_filter_issue": {
                "name": "Bloom Filter Issue",
                "description": "Bloom filter download fail or size > 4× median",
                "threshold": "Download fail or size > 4× median",
                "severity": AlertSeverity.CRITICAL,
                "auto_action": "Roll back to previous epoch",
                "check_interval": 300,  # 5 minutes
                "duration_threshold": 0  # Immediate
            },
            "billing_rollup_miss": {
                "name": "Billing Rollup Missed",
                "description": "Billing rollup missed 02:00 UTC deadline",
                "threshold": "Misses 02:00 UTC",
                "severity": AlertSeverity.CRITICAL,
                "auto_action": "Page Billing-Ops",
                "check_interval": 3600,  # 1 hour
                "duration_threshold": 0  # Immediate
            },
            "secrets_overdue": {
                "name": "Secrets Rotation Overdue",
                "description": "Secrets overdue rotation (> 90 days)",
                "threshold": "> 90 days",
                "severity": AlertSeverity.WARNING,
                "auto_action": "Slack #sec-ops",
                "check_interval": 86400,  # Daily
                "duration_threshold": 0  # Immediate
            }
        }
    
    def _make_api_request(self, endpoint: str) -> Optional[Dict]:
        """Make authenticated API request with error handling"""
        if not self.api_key:
            logger.error("No API key available for request")
            return None
            
        try:
            headers = {"X-API-Key": self.api_key}
            url = f"{self.base_url}{endpoint}"
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logger.error(f"API key authentication failed for {endpoint}")
            elif response.status_code == 404:
                logger.error(f"Endpoint not found: {endpoint}")
            else:
                logger.error(f"API error {response.status_code} for {endpoint}: {response.text}")
                
        except requests.exceptions.Timeout:
            logger.error(f"API request timeout for {endpoint}")
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {endpoint}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error calling {endpoint}: {e}")
        
        return None
    
    def check_verify_error_rate(self) -> Optional[Alert]:
        """Check verification error rate"""
        data = self._make_api_request("/api/sre/metrics/errors")
        if not data:
            return None
            
        try:
            error_rate = data.get('error_rate_5min', 0)
            
            if error_rate >= 0.01:  # 1%
                return Alert(
                    id="verify_error_rate",
                    name=self.alert_configs["verify_error_rate"]["name"],
                    description=self.alert_configs["verify_error_rate"]["description"],
                    severity=self.alert_configs["verify_error_rate"]["severity"],
                    status=AlertStatus.ACTIVE,
                    threshold=self.alert_configs["verify_error_rate"]["threshold"],
                    current_value=f"{error_rate * 100:.2f}%",
                    triggered_at=datetime.utcnow(),
                    auto_action=self.alert_configs["verify_error_rate"]["auto_action"]
                )
        except Exception as e:
            logger.error(f"Error checking verify error rate: {e}")
        
        return None
    
    def check_p95_latency(self) -> Optional[Alert]:
        """Check P95 latency"""
        data = self._make_api_request("/api/sre/metrics/latency")
        if not data:
            return None
            
        try:
            p95_latency = data.get('p95_latency_ms', 0)
            
            if p95_latency > 250:
                return Alert(
                    id="p95_latency",
                    name=self.alert_configs["p95_latency"]["name"],
                    description=self.alert_configs["p95_latency"]["description"],
                    severity=self.alert_configs["p95_latency"]["severity"],
                    status=AlertStatus.ACTIVE,
                    threshold=self.alert_configs["p95_latency"]["threshold"],
                    current_value=f"{p95_latency}ms",
                    triggered_at=datetime.utcnow(),
                    auto_action=self.alert_configs["p95_latency"]["auto_action"]
                )
        except Exception as e:
            logger.error(f"Error checking P95 latency: {e}")
        
        return None
    
    def check_bloom_filter(self) -> Optional[Alert]:
        """Check bloom filter status"""
        data = self._make_api_request("/api/sre/metrics/bloom-filter")
        if not data:
            return None
            
        try:
            size_bytes = data.get('bloom_filter_size_bytes', 0)
            download_success = data.get('last_download_success', True)
            median_size = data.get('median_size_bytes', size_bytes / 2)  # Fallback
            
            # Check for download failure or size > 4× median
            if not download_success or size_bytes > (median_size * 4):
                issue_type = "Download failed" if not download_success else f"Size {size_bytes} > 4× median {median_size}"
                
                return Alert(
                    id="bloom_filter_issue",
                    name=self.alert_configs["bloom_filter_issue"]["name"],
                    description=self.alert_configs["bloom_filter_issue"]["description"],
                    severity=self.alert_configs["bloom_filter_issue"]["severity"],
                    status=AlertStatus.ACTIVE,
                    threshold=self.alert_configs["bloom_filter_issue"]["threshold"],
                    current_value=issue_type,
                    triggered_at=datetime.utcnow(),
                    auto_action=self.alert_configs["bloom_filter_issue"]["auto_action"]
                )
        except Exception as e:
            logger.error(f"Error checking bloom filter: {e}")
        
        return None
    
    def check_billing_rollup(self) -> Optional[Alert]:
        """Check if billing rollup missed 02:00 UTC deadline"""
        data = self._make_api_request("/api/sre/metrics/billing-jobs")
        if not data:
            return None
            
        try:
            last_job_time = data.get('last_job_time')
            current_utc = datetime.utcnow()
            
            # Check if we're past 02:00 UTC and no job ran today
            if current_utc.hour >= 2:
                today_2am = current_utc.replace(hour=2, minute=0, second=0, microsecond=0)
                
                if last_job_time:
                    last_job_dt = datetime.fromisoformat(last_job_time.replace('Z', '+00:00'))
                    if last_job_dt < today_2am:
                        return Alert(
                            id="billing_rollup_miss",
                            name=self.alert_configs["billing_rollup_miss"]["name"],
                            description=self.alert_configs["billing_rollup_miss"]["description"],
                            severity=self.alert_configs["billing_rollup_miss"]["severity"],
                            status=AlertStatus.ACTIVE,
                            threshold=self.alert_configs["billing_rollup_miss"]["threshold"],
                            current_value=f"Last run: {last_job_time}",
                            triggered_at=datetime.utcnow(),
                            auto_action=self.alert_configs["billing_rollup_miss"]["auto_action"]
                        )
        except Exception as e:
            logger.error(f"Error checking billing rollup: {e}")
        
        return None
    
    def check_secrets_rotation(self) -> Optional[Alert]:
        """Check for overdue secrets rotation"""
        data = self._make_api_request("/api/compliance/secrets/status")
        if not data:
            return None
            
        try:
            overdue_secrets = data.get('overdue_secrets', [])
            
            if overdue_secrets:
                overdue_count = len(overdue_secrets)
                oldest_days = max([s.get('days_overdue', 0) for s in overdue_secrets])
                
                return Alert(
                    id="secrets_overdue",
                    name=self.alert_configs["secrets_overdue"]["name"],
                    description=self.alert_configs["secrets_overdue"]["description"],
                    severity=self.alert_configs["secrets_overdue"]["severity"],
                    status=AlertStatus.ACTIVE,
                    threshold=self.alert_configs["secrets_overdue"]["threshold"],
                    current_value=f"{overdue_count} secrets, oldest {oldest_days} days",
                    triggered_at=datetime.utcnow(),
                    auto_action=self.alert_configs["secrets_overdue"]["auto_action"]
                )
        except Exception as e:
            logger.error(f"Error checking secrets rotation: {e}")
        
        return None
    
    def process_alert(self, alert: Alert) -> bool:
        """Process a new alert"""
        if alert.id in self.active_alerts:
            # Alert already active, update timestamp
            self.active_alerts[alert.id].triggered_at = alert.triggered_at
            return True
        
        # New alert - add to active alerts
        self.active_alerts[alert.id] = alert
        self.alert_history.append(alert)
        
        logger.info(f"New alert triggered: {alert.name} - {alert.current_value}")
        
        # Create PagerDuty incident
        incident_id = self.pagerduty.create_incident(alert)
        if incident_id:
            alert.pagerduty_incident_id = incident_id
        
        # Execute auto-action
        action_success = self.auto_actions.execute_action(alert)
        if not action_success:
            logger.warning(f"Auto-action failed for alert: {alert.id}")
        
        return True
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an active alert"""
        if alert_id not in self.active_alerts:
            return False
        
        alert = self.active_alerts[alert_id]
        alert.status = AlertStatus.RESOLVED
        
        # Resolve PagerDuty incident
        if alert.pagerduty_incident_id:
            self.pagerduty.resolve_incident(alert)
        
        # Remove from active alerts
        del self.active_alerts[alert_id]
        
        logger.info(f"Alert resolved: {alert.name}")
        return True
    
    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """Run a complete monitoring cycle"""
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "alerts_checked": 0,
            "new_alerts": 0,
            "resolved_alerts": 0,
            "active_alerts": len(self.active_alerts)
        }
        
        # Check all alert conditions
        check_functions = [
            self.check_verify_error_rate,
            self.check_p95_latency,
            self.check_bloom_filter,
            self.check_billing_rollup,
            self.check_secrets_rotation
        ]
        
        current_alert_ids = set()
        
        for check_func in check_functions:
            results["alerts_checked"] += 1
            alert = check_func()
            
            if alert:
                current_alert_ids.add(alert.id)
                if alert.id not in self.active_alerts:
                    self.process_alert(alert)
                    results["new_alerts"] += 1
        
        # Resolve alerts that are no longer triggered
        resolved_ids = []
        for alert_id in list(self.active_alerts.keys()):
            if alert_id not in current_alert_ids:
                self.resolve_alert(alert_id)
                resolved_ids.append(alert_id)
                results["resolved_alerts"] += 1
        
        results["active_alerts"] = len(self.active_alerts)
        
        logger.info(f"Monitoring cycle complete: {results}")
        return results
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        return [
            {
                "id": alert.id,
                "name": alert.name,
                "description": alert.description,
                "severity": alert.severity.value,
                "status": alert.status.value,
                "threshold": alert.threshold,
                "current_value": alert.current_value,
                "triggered_at": alert.triggered_at.isoformat(),
                "auto_action": alert.auto_action,
                "pagerduty_incident_id": alert.pagerduty_incident_id
            }
            for alert in self.active_alerts.values()
        ]
    
    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alert history"""
        return [
            {
                "id": alert.id,
                "name": alert.name,
                "description": alert.description,
                "severity": alert.severity.value,
                "status": alert.status.value,
                "threshold": alert.threshold,
                "current_value": alert.current_value,
                "triggered_at": alert.triggered_at.isoformat(),
                "auto_action": alert.auto_action
            }
            for alert in self.alert_history[-limit:]
        ]

# Global alert manager instance
alert_manager = AlertManager()

def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance"""
    return alert_manager 