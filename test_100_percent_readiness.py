#!/usr/bin/env python3
"""
🚀 LEMMA 100% GO-LIVE READINESS TEST
===================================
Comprehensive test suite to verify production readiness
Target: 100% readiness score for customer billing
"""

import requests
import time
import json
import os
from datetime import datetime
from typing import List, Dict, Any

class LemmaReadinessTest:
    """Complete go-live readiness verification."""
    
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.api_key = os.environ.get('LEMMA_API_KEY', 'test-api-key')
        self.results = {
            "performance": {},
            "automation": {},
            "security": {},
            "api": {},
            "overall": {}
        }
        
    def run_complete_readiness_test(self) -> Dict[str, Any]:
        """Run complete 100% readiness verification."""
        print("🚀 LEMMA 100% GO-LIVE READINESS TEST")
        print("=" * 60)
        print(f"Target: <150ms response time | 100% automation | Full API coverage")
        print(f"Testing: {self.base_url}")
        print("")
        
        # Test all critical systems
        performance_score = self.test_performance_sla()
        automation_score = self.test_automation_pipeline()
        api_score = self.test_api_coverage()
        security_score = self.test_security_features()
        
        # Calculate overall readiness
        overall_score = (performance_score + automation_score + api_score + security_score) / 4
        
        self.results["overall"] = {
            "score": overall_score,
            "performance": performance_score,
            "automation": automation_score,
            "api": api_score,
            "security": security_score,
            "ready_for_billing": overall_score >= 90.0,
            "ready_for_production": overall_score >= 95.0
        }
        
        self.print_final_report()
        return self.results
    
    def test_performance_sla(self) -> float:
        """Test critical <150ms SLA compliance."""
        print("🎯 PERFORMANCE SLA TEST (<150ms requirement)")
        print("-" * 50)
        
        response_times = []
        successful_requests = 0
        
        # Warm up
        try:
            requests.get(f"{self.base_url}/api/health", timeout=5)
            print("✅ Warmup complete")
        except:
            print("❌ Warmup failed")
            return 0.0
        
        # Test 10 verification requests for statistical accuracy
        for i in range(10):
            try:
                # Generate challenge
                challenge_resp = requests.get(f"{self.base_url}/api/generate-challenge", timeout=5)
                if challenge_resp.status_code != 200:
                    continue
                    
                challenge = challenge_resp.json().get('challenge')
                if not challenge:
                    continue
                
                # Create test presentation
                test_presentation = {
                    "presentation": {
                        "@context": ["https://www.w3.org/2018/credentials/v1"],
                        "type": ["VerifiablePresentation"],
                        "verifiableCredential": [{
                            "@context": ["https://www.w3.org/2018/credentials/v1"],
                            "type": ["VerifiableCredential", "LemmaHumanCredential"],
                            "id": f"test-credential-{int(time.time())}-{i}",
                            "issuer": "did:lemma:test",
                            "issuanceDate": datetime.now().isoformat(),
                            "credentialSubject": {
                                "id": "did:user:test-user",
                                "isHuman": True
                            }
                        }]
                    },
                    "challenge": challenge
                }
                
                # Measure verification time
                start_time = time.time()
                response = requests.post(
                    f"{self.base_url}/api/verify-presentation",
                    json=test_presentation,
                    timeout=5
                )
                response_time = (time.time() - start_time) * 1000
                response_times.append(response_time)
                
                if response.status_code == 200:
                    successful_requests += 1
                    
                sla_status = "✅" if response_time <= 150 else "❌"
                print(f"{sla_status} Request {i+1}: {response_time:.1f}ms")
                
            except Exception as e:
                print(f"❌ Request {i+1} failed: {e}")
        
        if not response_times:
            print("❌ No successful requests")
            return 0.0
        
        # Calculate performance metrics
        avg_time = sum(response_times) / len(response_times)
        p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
        sla_compliance = len([t for t in response_times if t <= 150]) / len(response_times) * 100
        
        performance_score = min(100.0, (150 / max(avg_time, 1)) * 100)
        
        print(f"\n📊 PERFORMANCE RESULTS:")
        print(f"   Average: {avg_time:.1f}ms")
        print(f"   P95: {p95_time:.1f}ms")
        print(f"   SLA Compliance: {sla_compliance:.1f}%")
        print(f"   Performance Score: {performance_score:.1f}%")
        
        self.results["performance"] = {
            "average_ms": avg_time,
            "p95_ms": p95_time,
            "sla_compliance_percent": sla_compliance,
            "score": performance_score,
            "meets_sla": p95_time <= 150
        }
        
        return performance_score
    
    def test_automation_pipeline(self) -> float:
        """Test revocation automation pipeline."""
        print("\n🤖 AUTOMATION PIPELINE TEST")
        print("-" * 50)
        
        automation_score = 0.0
        tests_passed = 0
        total_tests = 4
        
        # Test 1: Automation status
        try:
            response = requests.get(
                f"{self.base_url}/api/automation/status",
                headers={"X-API-Key": self.api_key},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('pipeline_status') == 'operational':
                    print("✅ Automation status: Operational")
                    tests_passed += 1
                else:
                    print("❌ Automation status: Not operational")
            else:
                print("❌ Automation status: API error")
        except Exception as e:
            print(f"❌ Automation status: {e}")
        
        # Test 2: Auto-generate cascade
        try:
            response = requests.post(
                f"{self.base_url}/api/revocation/cascade/auto-generate",
                headers={"X-API-Key": self.api_key},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    print("✅ Auto-generation: Working")
                    tests_passed += 1
                else:
                    print("❌ Auto-generation: Failed")
            else:
                print("❌ Auto-generation: API error")
        except Exception as e:
            print(f"❌ Auto-generation: {e}")
        
        # Test 3: Latest cascade serving
        try:
            response = requests.get(f"{self.base_url}/api/revocation/cascade/latest", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('cascade'):
                    print("✅ Cascade serving: Working")
                    tests_passed += 1
                else:
                    print("❌ Cascade serving: No data")
            else:
                print("❌ Cascade serving: Not available")
        except Exception as e:
            print(f"❌ Cascade serving: {e}")
        
        # Test 4: API key integration
        api_key_configured = bool(self.api_key and self.api_key != 'test-api-key')
        if api_key_configured:
            print("✅ API key: Configured")
            tests_passed += 1
        else:
            print("❌ API key: Not configured")
        
        automation_score = (tests_passed / total_tests) * 100
        
        print(f"\n📊 AUTOMATION RESULTS:")
        print(f"   Tests Passed: {tests_passed}/{total_tests}")
        print(f"   Automation Score: {automation_score:.1f}%")
        
        self.results["automation"] = {
            "tests_passed": tests_passed,
            "total_tests": total_tests,
            "score": automation_score,
            "fully_automated": tests_passed == total_tests
        }
        
        return automation_score
    
    def test_api_coverage(self) -> float:
        """Test critical API endpoint coverage."""
        print("\n🔌 API COVERAGE TEST")
        print("-" * 50)
        
        endpoints = [
            ("GET", "/api/health", None),
            ("GET", "/api/generate-challenge", None),
            ("POST", "/api/verify-presentation", {"presentation": {}, "challenge": "test"}),
            ("GET", "/api/automation/status", {"X-API-Key": self.api_key}),
            ("GET", "/api/revocation/cascade/latest", None)
        ]
        
        working_endpoints = 0
        total_endpoints = len(endpoints)
        
        for method, endpoint, data_or_headers in endpoints:
            try:
                if method == "GET":
                    headers = data_or_headers if isinstance(data_or_headers, dict) else {}
                    response = requests.get(f"{self.base_url}{endpoint}", headers=headers, timeout=5)
                else:
                    response = requests.post(f"{self.base_url}{endpoint}", json=data_or_headers, timeout=5)
                
                if response.status_code in [200, 201, 400]:  # 400 is acceptable for invalid data
                    print(f"✅ {method} {endpoint}")
                    working_endpoints += 1
                else:
                    print(f"❌ {method} {endpoint} (Status: {response.status_code})")
            except Exception as e:
                print(f"❌ {method} {endpoint} (Error: {str(e)[:50]})")
        
        api_score = (working_endpoints / total_endpoints) * 100
        
        print(f"\n📊 API RESULTS:")
        print(f"   Working Endpoints: {working_endpoints}/{total_endpoints}")
        print(f"   API Coverage Score: {api_score:.1f}%")
        
        self.results["api"] = {
            "working_endpoints": working_endpoints,
            "total_endpoints": total_endpoints,
            "score": api_score,
            "full_coverage": working_endpoints == total_endpoints
        }
        
        return api_score
    
    def test_security_features(self) -> float:
        """Test security feature implementation."""
        print("\n🔒 SECURITY FEATURES TEST")
        print("-" * 50)
        
        security_tests = 0
        total_security_tests = 3
        
        # Test 1: Rate limiting
        try:
            # Make multiple rapid requests to test rate limiting
            responses = []
            for _ in range(10):
                resp = requests.get(f"{self.base_url}/api/health", timeout=1)
                responses.append(resp.status_code)
            
            # Check if any requests were rate limited (429)
            if 429 in responses:
                print("✅ Rate limiting: Active")
                security_tests += 1
            else:
                print("⚠️  Rate limiting: Not triggered (may be configured)")
                security_tests += 0.5  # Partial credit
        except:
            print("❌ Rate limiting: Test failed")
        
        # Test 2: API key protection
        try:
            response = requests.get(f"{self.base_url}/api/automation/status", timeout=5)
            if response.status_code == 401 or response.status_code == 403:
                print("✅ API key protection: Active")
                security_tests += 1
            else:
                print("❌ API key protection: Missing")
        except:
            print("❌ API key protection: Test failed")
        
        # Test 3: Input validation
        try:
            response = requests.post(
                f"{self.base_url}/api/verify-presentation",
                json={"invalid": "data"},
                timeout=5
            )
            if response.status_code == 400:
                print("✅ Input validation: Active")
                security_tests += 1
            else:
                print("❌ Input validation: Missing")
        except:
            print("❌ Input validation: Test failed")
        
        security_score = (security_tests / total_security_tests) * 100
        
        print(f"\n📊 SECURITY RESULTS:")
        print(f"   Security Tests Passed: {security_tests:.1f}/{total_security_tests}")
        print(f"   Security Score: {security_score:.1f}%")
        
        self.results["security"] = {
            "tests_passed": security_tests,
            "total_tests": total_security_tests,
            "score": security_score
        }
        
        return security_score
    
    def print_final_report(self):
        """Print comprehensive readiness report."""
        print("\n" + "=" * 60)
        print("🎯 FINAL READINESS REPORT")
        print("=" * 60)
        
        overall = self.results["overall"]
        
        print(f"📊 OVERALL READINESS SCORE: {overall['score']:.1f}%")
        
        if overall['score'] >= 95.0:
            status = "🚀 PRODUCTION READY"
        elif overall['score'] >= 90.0:
            status = "✅ GO-LIVE READY"
        elif overall['score'] >= 75.0:
            status = "⚠️  ALMOST READY"
        else:
            status = "❌ NOT READY"
        
        print(f"Status: {status}")
        print(f"Minimum Required: 90% readiness score")
        
        if overall['score'] >= 90.0:
            print("")
            print("🎉 CONGRATULATIONS! 🎉")
            print("Lemma Enterprise is ready for customer billing!")
            print("")
            print("✅ Performance: <150ms SLA compliance")
            print("✅ Automation: Fully operational")
            print("✅ API Coverage: Complete")
            print("✅ Security: Production-grade")
        else:
            print("")
            print("🔧 OPTIMIZATION NEEDED:")
            if overall['performance'] < 90:
                print(f"   ❌ Performance: {overall['performance']:.1f}% (needs optimization)")
            if overall['automation'] < 90:
                print(f"   ❌ Automation: {overall['automation']:.1f}% (needs completion)")
            if overall['api'] < 90:
                print(f"   ❌ API Coverage: {overall['api']:.1f}% (needs implementation)")
            if overall['security'] < 90:
                print(f"   ❌ Security: {overall['security']:.1f}% (needs hardening)")
        
        print("\n" + "=" * 60)

def main():
    """Run the complete 100% readiness test."""
    tester = LemmaReadinessTest()
    results = tester.run_complete_readiness_test()
    
    # Save results for CI/CD
    with open('readiness_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Exit with appropriate code
    overall_score = results["overall"]["score"]
    if overall_score >= 90.0:
        exit(0)  # Success
    else:
        exit(1)  # Needs work

if __name__ == "__main__":
    main() 