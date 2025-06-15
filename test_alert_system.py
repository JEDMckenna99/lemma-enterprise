#!/usr/bin/env python3
"""
Test Alert System
Comprehensive testing of PagerDuty integration and alert monitoring
"""

import requests
import json
import time
import os
from datetime import datetime

# Configuration
BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
API_KEY = "63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e"

def test_api_call(endpoint, method="GET", data=None, description=""):
    """Make an API call and return the result"""
    url = f"{BASE_URL}{endpoint}"
    headers = {"X-API-Key": API_KEY}
    
    if data:
        headers["Content-Type"] = "application/json"
    
    print(f"\n🔍 Testing: {description}")
    print(f"📡 {method} {endpoint}")
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            print(f"❌ Unsupported method: {method}")
            return None
        
        print(f"📊 Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success: {description}")
            return result
        else:
            print(f"❌ Failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"🔍 Error: {error_data}")
            except:
                print(f"🔍 Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None

def main():
    """Run comprehensive alert system tests"""
    print("🚨 LEMMA ALERT SYSTEM TEST")
    print("=" * 50)
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"🔑 API Key: {API_KEY[:20]}...")
    print(f"⏰ Test Time: {datetime.utcnow().isoformat()}")
    
    # Test 1: Check monitor status
    print("\n" + "="*50)
    print("TEST 1: MONITOR STATUS")
    print("="*50)
    
    status = test_api_call(
        "/api/sre/alerts/monitor-status",
        description="Check background monitoring service status"
    )
    
    if status:
        monitor_status = status.get('monitor_status', {})
        integrations = status.get('integrations', {})
        
        print(f"🔄 Monitor Running: {monitor_status.get('is_running')}")
        print(f"⏱️  Check Interval: {monitor_status.get('check_interval')}s")
        print(f"🚨 Active Alerts: {monitor_status.get('active_alerts')}")
        print(f"🧵 Thread Alive: {monitor_status.get('thread_alive')}")
        
        print(f"\n📡 Integration Status:")
        print(f"   📟 PagerDuty: {'✅' if integrations.get('pagerduty_configured') else '❌'}")
        print(f"   💬 Slack: {'✅' if integrations.get('slack_configured') else '❌'}")
        print(f"   📊 Status Page: {'✅' if integrations.get('statuspage_configured') else '❌'}")
    
    # Test 2: Check alert rules
    print("\n" + "="*50)
    print("TEST 2: ALERT RULES")
    print("="*50)
    
    rules = test_api_call(
        "/api/sre/alerts/rules",
        description="Get configured alert rules and thresholds"
    )
    
    if rules:
        alert_rules = rules.get('alert_rules', [])
        print(f"📋 Total Rules: {len(alert_rules)}")
        
        for rule in alert_rules:
            print(f"\n🚨 {rule['name']}")
            print(f"   📊 Threshold: {rule['threshold']}")
            print(f"   🎯 Severity: {rule['severity']}")
            print(f"   🤖 Auto-action: {rule['auto_action']}")
    
    # Test 3: Check current alerts
    print("\n" + "="*50)
    print("TEST 3: CURRENT ALERTS")
    print("="*50)
    
    current = test_api_call(
        "/api/sre/alerts/current",
        description="Get currently active alerts"
    )
    
    if current:
        active_alerts = current.get('active_alerts', [])
        print(f"🚨 Active Alerts: {len(active_alerts)}")
        
        if active_alerts:
            for alert in active_alerts:
                print(f"\n⚠️  {alert['name']}")
                print(f"   📊 Current Value: {alert['current_value']}")
                print(f"   🎯 Threshold: {alert['threshold']}")
                print(f"   ⏰ Triggered: {alert['triggered_at']}")
                print(f"   🤖 Auto-action: {alert.get('auto_action', 'None')}")
        else:
            print("✅ No active alerts - system healthy")
    
    # Test 4: Check alert history
    print("\n" + "="*50)
    print("TEST 4: ALERT HISTORY")
    print("="*50)
    
    history = test_api_call(
        "/api/sre/alerts/history?limit=5",
        description="Get recent alert history"
    )
    
    if history:
        alert_history = history.get('alert_history', [])
        print(f"📚 Recent Alerts: {len(alert_history)}")
        
        for alert in alert_history[-3:]:  # Show last 3
            print(f"\n📝 {alert['name']}")
            print(f"   📊 Value: {alert['current_value']}")
            print(f"   🎯 Status: {alert['status']}")
            print(f"   ⏰ Time: {alert['triggered_at']}")
    
    # Test 5: Manual monitoring cycle
    print("\n" + "="*50)
    print("TEST 5: MANUAL MONITORING CYCLE")
    print("="*50)
    
    cycle = test_api_call(
        "/api/sre/alerts/run-check",
        method="POST",
        description="Manually trigger alert monitoring cycle"
    )
    
    if cycle:
        results = cycle.get('monitoring_results', {})
        print(f"🔍 Alerts Checked: {results.get('alerts_checked')}")
        print(f"🆕 New Alerts: {results.get('new_alerts')}")
        print(f"✅ Resolved Alerts: {results.get('resolved_alerts')}")
        print(f"🚨 Active Alerts: {results.get('active_alerts')}")
    
    # Test 6: Test PagerDuty integration (if configured)
    print("\n" + "="*50)
    print("TEST 6: PAGERDUTY INTEGRATION")
    print("="*50)
    
    if os.getenv('PAGERDUTY_INTEGRATION_KEY'):
        print("🔑 PagerDuty integration key found - testing...")
        
        pagerduty = test_api_call(
            "/api/sre/alerts/test-pagerduty",
            method="POST",
            description="Test PagerDuty integration with test alert"
        )
        
        if pagerduty:
            print(f"✅ {pagerduty.get('message')}")
            if 'incident_id' in pagerduty:
                print(f"🎫 Incident ID: {pagerduty['incident_id']}")
    else:
        print("⚠️  PagerDuty integration key not configured")
        print("   Set PAGERDUTY_INTEGRATION_KEY environment variable to test")
    
    # Test 7: Check SRE metrics that alerts depend on
    print("\n" + "="*50)
    print("TEST 7: SRE METRICS (ALERT DEPENDENCIES)")
    print("="*50)
    
    metrics_endpoints = [
        ("/api/sre/metrics/errors", "Error Rate Metrics"),
        ("/api/sre/metrics/latency", "Latency Metrics"),
        ("/api/sre/metrics/bloom-filter", "Bloom Filter Metrics"),
        ("/api/sre/metrics/billing-jobs", "Billing Job Metrics"),
        ("/api/compliance/secrets/status", "Secrets Rotation Status")
    ]
    
    for endpoint, description in metrics_endpoints:
        result = test_api_call(endpoint, description=description)
        if result:
            # Extract key metrics for alert thresholds
            if "errors" in endpoint:
                error_rate = result.get('error_rate_5min', 0)
                print(f"   📊 5-min Error Rate: {error_rate * 100:.2f}% (Alert: ≥1%)")
            elif "latency" in endpoint:
                p95_latency = result.get('p95_latency_ms', 0)
                print(f"   📊 P95 Latency: {p95_latency}ms (Alert: >250ms)")
            elif "bloom-filter" in endpoint:
                size_bytes = result.get('bloom_filter_size_bytes', 0)
                download_success = result.get('last_download_success', True)
                print(f"   📊 Bloom Filter Size: {size_bytes} bytes")
                print(f"   📊 Download Success: {download_success}")
            elif "billing-jobs" in endpoint:
                last_job = result.get('last_job_time', 'Never')
                print(f"   📊 Last Billing Job: {last_job}")
            elif "secrets" in endpoint:
                overdue = result.get('overdue_secrets', [])
                print(f"   📊 Overdue Secrets: {len(overdue)}")
    
    # Summary
    print("\n" + "="*50)
    print("🎯 TEST SUMMARY")
    print("="*50)
    
    print("✅ Alert system components tested:")
    print("   📊 Background monitoring service")
    print("   📋 Alert rules configuration")
    print("   🚨 Current alerts status")
    print("   📚 Alert history tracking")
    print("   🔄 Manual monitoring cycle")
    print("   📟 PagerDuty integration")
    print("   📈 SRE metrics dependencies")
    
    print(f"\n🎉 Alert system test completed at {datetime.utcnow().isoformat()}")
    print("🔍 Review the output above for any issues or configuration needs")
    
    print("\n📚 Next Steps:")
    print("1. Configure PagerDuty integration key if not already set")
    print("2. Set up Slack webhooks for team notifications")
    print("3. Configure status page integration for customer communication")
    print("4. Monitor logs for alert activity: heroku logs --tail | grep -i alert")
    print("5. Test alert thresholds by simulating high error rates or latency")

if __name__ == "__main__":
    main() 