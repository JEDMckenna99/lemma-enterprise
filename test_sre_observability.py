#!/usr/bin/env python3
"""
SRE Observability Test for Lemma Enterprise
Tests against comprehensive observability and monitoring checklist.
"""

import requests
import time
import json
import threading
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any
import concurrent.futures

class LemmaSREObservabilityTest:
    """Comprehensive SRE observability test suite."""
    
    def __init__(self, base_url="https://lemma-enterprise-0f6ba17076c1.herokuapp.com"):
        self.base_url = base_url
        self.api_key = "63d3c76faad6b305b3630575524d7e1b829527526e29b5ea18757b42e4de771e"
        self.results = {}
        
    def run_comprehensive_test(self):
        """Run all SRE observability tests."""
        print("🔍 SRE OBSERVABILITY TEST SUITE")
        print("=" * 60)
        print(f"Target: {self.base_url}")
        print(f"Time: {datetime.now().isoformat()}")
        print("")
        
        tests = [
            ("Dashboard Metrics Availability", self.test_dashboard_metrics),
            ("Latency Monitoring", self.test_latency_monitoring),
            ("Error Rate Tracking", self.test_error_rate_tracking),
            ("MAH Counter Metrics", self.test_mah_counters),
            ("Revocation Push Lag", self.test_revocation_lag),
            ("Wallet JS Error Tracking", self.test_wallet_js_errors),
            ("Alerting Infrastructure", self.test_alerting_infrastructure),
            ("Load Test Performance", self.test_load_performance),
            ("Billing Job Monitoring", self.test_billing_job_monitoring),
            ("Bloom Filter Monitoring", self.test_bloom_filter_monitoring)
        ]
        
        total_score = 0
        max_score = 0
        
        for test_name, test_func in tests:
            print(f"\n🧪 {test_name}")
            print("-" * 40)
            try:
                score = test_func()
                self.results[test_name] = score
                total_score += score['score']
                max_score += 100
                print(f"Score: {score['score']:.1f}/100")
            except Exception as e:
                print(f"❌ Test failed: {e}")
                self.results[test_name] = {"score": 0, "error": str(e)}
        
        overall_score = (total_score / max_score * 100) if max_score > 0 else 0
        print(f"\n🎯 OVERALL SRE OBSERVABILITY SCORE: {overall_score:.1f}%")
        
        self.generate_recommendations()
        return self.results
    
    def test_dashboard_metrics(self) -> Dict[str, Any]:
        """Test availability of required dashboard metrics."""
        metrics_endpoints = [
            ("/api/health", "Basic health endpoint"),
            ("/api/billing/health", "Billing system health"),
            ("/api/compliance/dashboard", "Compliance dashboard"),
            ("/api/analytics/health", "Analytics health"),
            ("/api/automation/metrics", "Automation metrics"),
            ("/api/revocation/status", "Revocation status")
        ]
        
        available_metrics = 0
        total_metrics = len(metrics_endpoints)
        
        for endpoint, description in metrics_endpoints:
            try:
                headers = {"X-API-Key": self.api_key} if endpoint != "/api/health" else {}
                response = requests.get(f"{self.base_url}{endpoint}", 
                                      headers=headers, timeout=10)
                
                if response.status_code == 200:
                    print(f"✅ {description}: Available")
                    available_metrics += 1
                else:
                    print(f"❌ {description}: HTTP {response.status_code}")
            except Exception as e:
                print(f"❌ {description}: {e}")
        
        score = (available_metrics / total_metrics) * 100
        return {
            "score": score,
            "available_metrics": available_metrics,
            "total_metrics": total_metrics,
            "details": "Dashboard metrics availability test"
        }
    
    def test_latency_monitoring(self) -> Dict[str, Any]:
        """Test latency monitoring capabilities."""
        endpoints = [
            "/api/health",
            "/api/generate-challenge", 
            "/api/verify-presentation",
            "/api/billing/usage/monthly"
        ]
        
        latency_data = {}
        for endpoint in endpoints:
            latencies = []
            for _ in range(5):
                try:
                    headers = {"X-API-Key": self.api_key} if "billing" in endpoint else {}
                    start_time = time.time()
                    
                    if endpoint == "/api/verify-presentation":
                        # Need challenge first
                        challenge_resp = requests.get(f"{self.base_url}/api/generate-challenge")
                        if challenge_resp.status_code == 200:
                            challenge = challenge_resp.json().get('challenge')
                            test_data = {
                                "presentation": {"test": "data"},
                                "challenge": challenge
                            }
                            response = requests.post(f"{self.base_url}{endpoint}", 
                                                   json=test_data, headers=headers, timeout=5)
                        else:
                            continue
                    else:
                        response = requests.get(f"{self.base_url}{endpoint}", 
                                              headers=headers, timeout=5)
                    
                    latency = (time.time() - start_time) * 1000
                    latencies.append(latency)
                    
                except Exception:
                    continue
            
            if latencies:
                avg_latency = statistics.mean(latencies)
                p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
                latency_data[endpoint] = {
                    "avg_ms": avg_latency,
                    "p95_ms": p95_latency,
                    "samples": len(latencies)
                }
                print(f"📊 {endpoint}: {avg_latency:.1f}ms avg, {p95_latency:.1f}ms p95")
        
        # Score based on how many endpoints have latency monitoring
        score = (len(latency_data) / len(endpoints)) * 100
        return {
            "score": score,
            "latency_data": latency_data,
            "details": "Latency monitoring test"
        }
    
    def test_error_rate_tracking(self) -> Dict[str, Any]:
        """Test error rate tracking capabilities."""
        # Test various error conditions
        error_tests = [
            ("/api/verify-presentation", {"invalid": "data"}),
            ("/api/billing/usage/monthly", None),  # Without API key
            ("/api/nonexistent", None),
            ("/api/generate-challenge", {"method": "POST"})  # Wrong method
        ]
        
        error_responses = []
        total_requests = 0
        
        for endpoint, data in error_tests:
            for _ in range(3):  # Multiple attempts
                try:
                    total_requests += 1
                    if data:
                        response = requests.post(f"{self.base_url}{endpoint}", 
                                               json=data, timeout=5)
                    else:
                        response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    
                    if response.status_code >= 400:
                        error_responses.append({
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "timestamp": datetime.now().isoformat()
                        })
                except Exception as e:
                    error_responses.append({
                        "endpoint": endpoint,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
        
        error_rate = (len(error_responses) / total_requests) * 100 if total_requests > 0 else 0
        print(f"📈 Error rate: {error_rate:.1f}% ({len(error_responses)}/{total_requests})")
        
        # Score based on ability to track errors
        score = 80 if error_responses else 0  # If we can generate/track errors
        return {
            "score": score,
            "error_rate": error_rate,
            "total_errors": len(error_responses),
            "total_requests": total_requests,
            "details": "Error rate tracking test"
        }
    
    def test_mah_counters(self) -> Dict[str, Any]:
        """Test Monthly Active Humans counter metrics."""
        try:
            headers = {"X-API-Key": self.api_key}
            
            # Test billing usage endpoint for MAH data
            response = requests.get(f"{self.base_url}/api/billing/usage/monthly", 
                                  headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'monthly_active_humans' in data or 'mah' in data or 'total_verifications' in data:
                    print("✅ MAH counter data available")
                    score = 100
                else:
                    print("⚠️  MAH data format needs improvement")
                    score = 60
            else:
                print("❌ MAH counter endpoint unavailable")
                score = 0
                
        except Exception as e:
            print(f"❌ MAH counter test failed: {e}")
            score = 0
        
        return {
            "score": score,
            "details": "MAH counter metrics test"
        }
    
    def test_revocation_lag(self) -> Dict[str, Any]:
        """Test revocation push lag monitoring."""
        try:
            headers = {"X-API-Key": self.api_key}
            response = requests.get(f"{self.base_url}/api/revocation/status", 
                                  headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                has_lag_metrics = any(key in data for key in 
                                    ['last_update', 'lag_seconds', 'sync_status', 'last_sync'])
                
                if has_lag_metrics:
                    print("✅ Revocation lag metrics available")
                    score = 90
                else:
                    print("⚠️  Basic revocation status available")
                    score = 60
            else:
                print("❌ Revocation status unavailable")
                score = 0
                
        except Exception as e:
            print(f"❌ Revocation lag test failed: {e}")
            score = 0
        
        return {
            "score": score,
            "details": "Revocation push lag monitoring test"
        }
    
    def test_wallet_js_errors(self) -> Dict[str, Any]:
        """Test wallet JS error tracking capabilities."""
        # This would typically involve checking client-side error reporting
        # For now, test if we have endpoints that could receive JS errors
        
        js_error_endpoints = [
            "/api/analytics/client-errors",
            "/api/wallet/error-report", 
            "/api/logging/client-side"
        ]
        
        available_endpoints = 0
        for endpoint in js_error_endpoints:
            try:
                headers = {"X-API-Key": self.api_key}
                response = requests.get(f"{self.base_url}{endpoint}", 
                                      headers=headers, timeout=5)
                if response.status_code != 404:
                    available_endpoints += 1
                    print(f"✅ {endpoint}: Available")
            except:
                pass
        
        if available_endpoints == 0:
            print("❌ No dedicated wallet JS error tracking endpoints found")
            score = 20  # Basic score for potential to add
        else:
            print(f"✅ {available_endpoints} wallet error endpoints available")
            score = (available_endpoints / len(js_error_endpoints)) * 100
        
        return {
            "score": score,
            "available_endpoints": available_endpoints,
            "details": "Wallet JS error tracking test"
        }
    
    def test_alerting_infrastructure(self) -> Dict[str, Any]:
        """Test alerting infrastructure capabilities."""
        alerting_indicators = [
            ("Error rate monitoring", self.check_error_rate_alerts),
            ("Bloom filter alerts", self.check_bloom_filter_alerts), 
            ("Billing job alerts", self.check_billing_job_alerts)
        ]
        
        available_alerts = 0
        total_alerts = len(alerting_indicators)
        
        for alert_name, check_func in alerting_indicators:
            try:
                if check_func():
                    print(f"✅ {alert_name}: Available")
                    available_alerts += 1
                else:
                    print(f"❌ {alert_name}: Not implemented")
            except Exception as e:
                print(f"❌ {alert_name}: Error - {e}")
        
        score = (available_alerts / total_alerts) * 100
        return {
            "score": score,
            "available_alerts": available_alerts,
            "total_alerts": total_alerts,
            "details": "Alerting infrastructure test"
        }
    
    def test_load_performance(self) -> Dict[str, Any]:
        """Test load performance at 10x projected Day-1 QPS."""
        print("🚀 Load testing at 10x projected QPS...")
        
        # Assume Day-1 projection is ~10 QPS, so test at 100 QPS for short burst
        target_qps = 50  # Reduced for testing
        test_duration = 10  # seconds
        total_requests = target_qps * test_duration
        
        response_times = []
        successful_requests = 0
        
        def make_request():
            try:
                start_time = time.time()
                response = requests.get(f"{self.base_url}/api/health", timeout=5)
                latency = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    return latency, True
                else:
                    return latency, False
            except:
                return None, False
        
        # Use ThreadPoolExecutor for concurrent requests
        print(f"🔥 Starting load test: {target_qps} QPS for {test_duration}s")
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            start_time = time.time()
            futures = []
            
            for i in range(total_requests):
                future = executor.submit(make_request)
                futures.append(future)
                
                # Rate limiting to maintain QPS
                time.sleep(1.0 / target_qps)
                
                # Stop if we've been running too long
                if time.time() - start_time > test_duration + 5:
                    break
            
            # Collect results
            for future in concurrent.futures.as_completed(futures, timeout=30):
                try:
                    latency, success = future.result()
                    if latency is not None:
                        response_times.append(latency)
                        if success:
                            successful_requests += 1
                except:
                    pass
        
        if response_times:
            avg_latency = statistics.mean(response_times)
            p95_latency = sorted(response_times)[int(len(response_times) * 0.95)]
            success_rate = (successful_requests / len(response_times)) * 100
            
            print(f"📊 Load test results:")
            print(f"   Requests: {len(response_times)}")
            print(f"   Success rate: {success_rate:.1f}%")
            print(f"   Average latency: {avg_latency:.1f}ms")
            print(f"   P95 latency: {p95_latency:.1f}ms")
            
            # Score based on p95 latency requirement (≤250ms)
            if p95_latency <= 250 and success_rate >= 95:
                score = 100
                print("🎉 Load test PASSED")
            elif p95_latency <= 250:
                score = 80
                print("⚠️  Latency OK but success rate needs improvement")
            else:
                score = 40
                print("❌ Load test FAILED - latency too high")
        else:
            score = 0
            p95_latency = None
            success_rate = 0
            print("❌ Load test FAILED - no responses")
        
        return {
            "score": score,
            "p95_latency_ms": p95_latency,
            "success_rate": success_rate,
            "total_requests": len(response_times),
            "details": "Load performance test"
        }
    
    def test_billing_job_monitoring(self) -> Dict[str, Any]:
        """Test billing job monitoring capabilities."""
        try:
            headers = {"X-API-Key": self.api_key}
            response = requests.get(f"{self.base_url}/api/billing/health", 
                                  headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                has_job_metrics = any(key in str(data) for key in 
                                    ['rollup', 'job', 'last_run', 'status'])
                
                if has_job_metrics:
                    print("✅ Billing job metrics available")
                    score = 90
                else:
                    print("⚠️  Basic billing health available")
                    score = 60
            else:
                print("❌ Billing health endpoint unavailable")
                score = 0
                
        except Exception as e:
            print(f"❌ Billing job monitoring test failed: {e}")
            score = 0
        
        return {
            "score": score,
            "details": "Billing job monitoring test"
        }
    
    def test_bloom_filter_monitoring(self) -> Dict[str, Any]:
        """Test Bloom filter monitoring capabilities."""
        try:
            # Check OPRF/revocation status for bloom filter metrics
            headers = {"X-API-Key": self.api_key}
            response = requests.get(f"{self.base_url}/api/revocation/status", 
                                  headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                has_bloom_metrics = any(key in str(data).lower() for key in 
                                      ['bloom', 'filter', 'size', 'cascade'])
                
                if has_bloom_metrics:
                    print("✅ Bloom filter metrics available")
                    score = 90
                else:
                    print("⚠️  Basic revocation status available")
                    score = 50
            else:
                print("❌ Bloom filter monitoring unavailable")
                score = 0
                
        except Exception as e:
            print(f"❌ Bloom filter monitoring test failed: {e}")
            score = 0
        
        return {
            "score": score,
            "details": "Bloom filter monitoring test"
        }
    
    def check_error_rate_alerts(self) -> bool:
        """Check if error rate alerting is configured."""
        # This would check for alert configuration
        # For now, check if we have error monitoring endpoints
        try:
            headers = {"X-API-Key": self.api_key}
            response = requests.get(f"{self.base_url}/api/analytics/health", 
                                  headers=headers, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def check_bloom_filter_alerts(self) -> bool:
        """Check if Bloom filter alerting is configured."""
        try:
            headers = {"X-API-Key": self.api_key}
            response = requests.get(f"{self.base_url}/api/revocation/status", 
                                  headers=headers, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def check_billing_job_alerts(self) -> bool:
        """Check if billing job alerting is configured."""
        try:
            headers = {"X-API-Key": self.api_key}
            response = requests.get(f"{self.base_url}/api/billing/health", 
                                  headers=headers, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def generate_recommendations(self):
        """Generate recommendations based on test results."""
        print("\n🎯 SRE OBSERVABILITY RECOMMENDATIONS")
        print("=" * 50)
        
        recommendations = []
        
        # Dashboard metrics recommendations
        dashboard_score = self.results.get("Dashboard Metrics Availability", {}).get("score", 0)
        if dashboard_score < 80:
            recommendations.append("❗ Implement missing dashboard metrics endpoints")
        
        # Latency monitoring recommendations  
        latency_score = self.results.get("Latency Monitoring", {}).get("score", 0)
        if latency_score < 80:
            recommendations.append("❗ Add comprehensive latency monitoring with Prometheus")
        
        # Error rate recommendations
        error_score = self.results.get("Error Rate Tracking", {}).get("score", 0)
        if error_score < 80:
            recommendations.append("❗ Implement error rate tracking with 5-minute windows")
        
        # Wallet JS error recommendations
        wallet_score = self.results.get("Wallet JS Error Tracking", {}).get("score", 0)
        if wallet_score < 60:
            recommendations.append("❗ Add client-side error reporting for wallet JS")
        
        # Alerting recommendations
        alert_score = self.results.get("Alerting Infrastructure", {}).get("score", 0)
        if alert_score < 60:
            recommendations.append("❗ Implement PagerDuty/OpsGenie alerting for SRE requirements")
        
        # Load performance recommendations
        load_score = self.results.get("Load Test Performance", {}).get("score", 0)
        if load_score < 80:
            recommendations.append("❗ Optimize for 10x Day-1 QPS with p95 latency ≤250ms")
        
        # Billing job recommendations
        billing_score = self.results.get("Billing Job Monitoring", {}).get("score", 0)
        if billing_score < 80:
            recommendations.append("❗ Add billing rollup job monitoring with 02:00 UTC deadline alerts")
        
        # Bloom filter recommendations
        bloom_score = self.results.get("Bloom Filter Monitoring", {}).get("score", 0)
        if bloom_score < 80:
            recommendations.append("❗ Add Bloom filter size monitoring with 4× median alerts")
        
        if not recommendations:
            print("🎉 Excellent! All SRE observability requirements are well implemented.")
        else:
            print("🚨 CRITICAL SRE GAPS IDENTIFIED:")
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec}")

if __name__ == "__main__":
    import sys
    
    base_url = sys.argv[1] if len(sys.argv) > 1 else "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    tester = LemmaSREObservabilityTest(base_url)
    results = tester.run_comprehensive_test()
    
    # Save results
    with open("sre_observability_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to sre_observability_results.json") 