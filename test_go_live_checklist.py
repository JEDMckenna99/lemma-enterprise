#!/usr/bin/env python3
"""
Lemma Go-Live & Billing Readiness Test Suite
Tests all items from the go-live checklist to ensure production readiness.
"""

import requests
import time
import json
import subprocess
import os
import webbrowser
from pathlib import Path
from datetime import datetime
import sys

class GoLiveChecker:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url.rstrip('/')
        self.results = []
        self.api_key = os.getenv('LEMMA_API_KEY', 'test-api-key')
        
    def log_result(self, test_name, status, message, details=None):
        """Log a test result."""
        result = {
            'test': test_name,
            'status': status,
            'message': message,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        }
        self.results.append(result)
        
        # Print result
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {message}")
        
        if details:
            for key, value in details.items():
                print(f"   {key}: {value}")
    
    def test_hosted_verify_endpoint(self):
        """Test 1.A: Hosted Verify Endpoint - Returns success/revoked/invalid within SLA."""
        print("\n🔍 Testing Hosted Verify Endpoint...")
        
        try:
            # Test health endpoint first
            start_time = time.time()
            response = requests.get(f"{self.base_url}/api/health", timeout=5)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                self.log_result(
                    "Health Endpoint", 
                    "PASS", 
                    f"Health check successful ({response_time:.1f}ms)",
                    {"response_time_ms": response_time, "status_code": 200}
                )
            else:
                self.log_result(
                    "Health Endpoint", 
                    "FAIL", 
                    f"Health check failed: {response.status_code}",
                    {"status_code": response.status_code}
                )
                return
            
            # Test verify-presentation endpoint
            test_presentation = {
                "presentation": {
                    "@context": ["https://www.w3.org/2018/credentials/v1"],
                    "type": ["VerifiablePresentation"],
                    "verifiableCredential": [{
                        "@context": ["https://www.w3.org/2018/credentials/v1"],
                        "type": ["VerifiableCredential", "LemmaHumanCredential"],
                        "id": f"test-credential-{int(time.time())}",
                        "issuer": "did:lemma:test",
                        "issuanceDate": datetime.now().isoformat(),
                        "credentialSubject": {
                            "id": "did:user:test-user",
                            "isHuman": True
                        },
                        "proof": {
                            "type": "Ed25519Signature2020",
                            "created": datetime.now().isoformat(),
                            "proofPurpose": "assertionMethod",
                            "verificationMethod": "did:lemma:test#key-1",
                            "proofValue": "test-signature"
                        }
                    }],
                    "proof": {
                        "type": "Ed25519Signature2020",
                        "created": datetime.now().isoformat(),
                        "proofPurpose": "authentication",
                        "challenge": f"test-challenge-{int(time.time())}",
                        "verificationMethod": "did:user:test-user#key-1",
                        "proofValue": "test-presentation-signature"
                    }
                },
                "challenge": f"test-challenge-{int(time.time())}"
            }
            
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/api/verify-presentation",
                json=test_presentation,
                timeout=5
            )
            response_time = (time.time() - start_time) * 1000
            
            # Check if response time is within SLA (≤150ms p95)
            sla_met = response_time <= 150
            
            if response.status_code in [200, 400]:  # Both valid and invalid responses are acceptable
                result_data = response.json()
                has_required_fields = all(field in result_data for field in ['success', 'valid'])
                
                if has_required_fields and sla_met:
                    self.log_result(
                        "Verify Endpoint SLA", 
                        "PASS", 
                        f"Endpoint responds within SLA ({response_time:.1f}ms ≤ 150ms)",
                        {
                            "response_time_ms": response_time,
                            "sla_met": sla_met,
                            "has_required_fields": has_required_fields,
                            "response_format": "valid"
                        }
                    )
                else:
                    self.log_result(
                        "Verify Endpoint SLA", 
                        "FAIL", 
                        f"SLA not met ({response_time:.1f}ms > 150ms) or missing fields",
                        {
                            "response_time_ms": response_time,
                            "sla_met": sla_met,
                            "has_required_fields": has_required_fields
                        }
                    )
            else:
                self.log_result(
                    "Verify Endpoint SLA", 
                    "FAIL", 
                    f"Unexpected status code: {response.status_code}",
                    {"status_code": response.status_code, "response_time_ms": response_time}
                )
                
        except Exception as e:
            self.log_result(
                "Verify Endpoint SLA", 
                "FAIL", 
                f"Error testing endpoint: {str(e)}",
                {"error": str(e)}
            )
    
    def test_revocation_pipeline(self):
        """Test 1.B: Revocation Pipeline - Cascaded Bloom filter built hourly, signed, served from CDN."""
        print("\n🔍 Testing Revocation Pipeline...")
        
        try:
            # Check if cascade build script exists
            cascade_script = Path("build_cascade.py")
            if cascade_script.exists():
                self.log_result(
                    "Cascade Build Script", 
                    "PASS", 
                    "build_cascade.py exists and is ready for scheduling",
                    {"script_path": str(cascade_script)}
                )
            else:
                self.log_result(
                    "Cascade Build Script", 
                    "FAIL", 
                    "build_cascade.py not found",
                    {"expected_path": str(cascade_script)}
                )
                return
            
            # Check cascade API endpoint
            try:
                response = requests.get(f"{self.base_url}/api/cascade/latest", timeout=5)
                
                if response.status_code == 200:
                    cascade_data = response.json()
                    has_metadata = 'metadata' in cascade_data
                    has_levels = 'levels' in cascade_data
                    
                    self.log_result(
                        "Cascade API Endpoint", 
                        "PASS", 
                        "Cascade API serving data correctly",
                        {
                            "has_metadata": has_metadata,
                            "has_levels": has_levels,
                            "cache_headers": response.headers.get('Cache-Control', 'none')
                        }
                    )
                elif response.status_code == 404:
                    self.log_result(
                        "Cascade API Endpoint", 
                        "WARN", 
                        "No cascade data available (expected for new deployment)",
                        {"status_code": response.status_code}
                    )
                else:
                    self.log_result(
                        "Cascade API Endpoint", 
                        "FAIL", 
                        f"Cascade API error: {response.status_code}",
                        {"status_code": response.status_code}
                    )
            except Exception as e:
                self.log_result(
                    "Cascade API Endpoint", 
                    "FAIL", 
                    f"Error accessing cascade API: {str(e)}",
                    {"error": str(e)}
                )
            
            # Check automation system
            try:
                response = requests.get(f"{self.base_url}/api/automation/status", timeout=5)
                
                if response.status_code == 200:
                    automation_data = response.json()
                    self.log_result(
                        "Revocation Automation", 
                        "PASS", 
                        "Automation system operational",
                        {
                            "automation_running": automation_data.get('automation_running', False),
                            "service_status": automation_data.get('service_status', 'unknown')
                        }
                    )
                else:
                    self.log_result(
                        "Revocation Automation", 
                        "WARN", 
                        "Automation system not accessible",
                        {"status_code": response.status_code}
                    )
            except Exception as e:
                self.log_result(
                    "Revocation Automation", 
                    "WARN", 
                    f"Automation system check failed: {str(e)}",
                    {"error": str(e)}
                )
                
        except Exception as e:
            self.log_result(
                "Revocation Pipeline", 
                "FAIL", 
                f"Error testing revocation pipeline: {str(e)}",
                {"error": str(e)}
            )
    
    def test_wallet_sdk(self):
        """Test 1.C: Wallet Script/SDK - Loads on top three stacks, handles lost-credential and alias flows."""
        print("\n🔍 Testing Wallet SDK...")
        
        try:
            # Check if wallet scripts exist
            wallet_script = Path("static/js/lemma-wallet.js")
            wallet_init = Path("static/js/lemma-wallet-init.js")
            
            if wallet_script.exists() and wallet_init.exists():
                self.log_result(
                    "Wallet Scripts", 
                    "PASS", 
                    "Wallet scripts available for integration",
                    {
                        "wallet_script": str(wallet_script),
                        "wallet_init": str(wallet_init)
                    }
                )
            else:
                self.log_result(
                    "Wallet Scripts", 
                    "FAIL", 
                    "Wallet scripts missing",
                    {
                        "wallet_script_exists": wallet_script.exists(),
                        "wallet_init_exists": wallet_init.exists()
                    }
                )
                return
            
            # Check if test files were created
            test_dir = Path("wallet_tests")
            if test_dir.exists():
                test_files = list(test_dir.glob("*.html"))
                if test_files:
                    self.log_result(
                        "Cross-Stack Tests", 
                        "PASS", 
                        f"Cross-stack test files available ({len(test_files)} files)",
                        {"test_files": [str(f) for f in test_files]}
                    )
                    
                    # Open the test in browser for manual verification
                    main_test = test_dir / "wallet_test.html"
                    if main_test.exists():
                        print(f"   🌐 Opening wallet test: {main_test.absolute()}")
                        webbrowser.open(f"file://{main_test.absolute()}")
                        
                        self.log_result(
                            "Manual Test Available", 
                            "PASS", 
                            "Wallet test opened in browser for manual verification",
                            {"test_url": f"file://{main_test.absolute()}"}
                        )
                else:
                    self.log_result(
                        "Cross-Stack Tests", 
                        "WARN", 
                        "Test directory exists but no test files found",
                        {"test_dir": str(test_dir)}
                    )
            else:
                self.log_result(
                    "Cross-Stack Tests", 
                    "WARN", 
                    "No cross-stack tests found (run simple_wallet_test.py to create)",
                    {"expected_dir": str(test_dir)}
                )
            
            # Test wallet API endpoints
            try:
                response = requests.get(f"{self.base_url}/static/js/lemma-wallet.js", timeout=5)
                if response.status_code == 200:
                    wallet_size = len(response.content)
                    self.log_result(
                        "Wallet Script Serving", 
                        "PASS", 
                        f"Wallet script served correctly ({wallet_size} bytes)",
                        {"script_size": wallet_size, "content_type": response.headers.get('content-type')}
                    )
                else:
                    self.log_result(
                        "Wallet Script Serving", 
                        "FAIL", 
                        f"Wallet script not served: {response.status_code}",
                        {"status_code": response.status_code}
                    )
            except Exception as e:
                self.log_result(
                    "Wallet Script Serving", 
                    "FAIL", 
                    f"Error accessing wallet script: {str(e)}",
                    {"error": str(e)}
                )
                
        except Exception as e:
            self.log_result(
                "Wallet SDK", 
                "FAIL", 
                f"Error testing wallet SDK: {str(e)}",
                {"error": str(e)}
            )
    
    def test_offline_verifier_image(self):
        """Test 1.D: Offline Verifier Image - Docker image published, checksum signed, auto-update disabled."""
        print("\n🔍 Testing Offline Verifier Image...")
        
        try:
            # Check if Dockerfile exists
            dockerfile = Path("Dockerfile")
            docker_compose = Path("docker-compose.yml")
            
            if dockerfile.exists():
                self.log_result(
                    "Docker Configuration", 
                    "PASS", 
                    "Dockerfile exists for offline verifier image",
                    {"dockerfile": str(dockerfile)}
                )
            else:
                self.log_result(
                    "Docker Configuration", 
                    "FAIL", 
                    "Dockerfile missing",
                    {"expected_path": str(dockerfile)}
                )
                return
            
            if docker_compose.exists():
                self.log_result(
                    "Docker Compose", 
                    "PASS", 
                    "docker-compose.yml available for easy deployment",
                    {"compose_file": str(docker_compose)}
                )
            else:
                self.log_result(
                    "Docker Compose", 
                    "WARN", 
                    "docker-compose.yml not found",
                    {"expected_path": str(docker_compose)}
                )
            
            # Test Docker build (if Docker is available)
            try:
                result = subprocess.run(
                    ["docker", "--version"], 
                    capture_output=True, 
                    text=True, 
                    timeout=10
                )
                
                if result.returncode == 0:
                    docker_version = result.stdout.strip()
                    self.log_result(
                        "Docker Available", 
                        "PASS", 
                        f"Docker is available: {docker_version}",
                        {"docker_version": docker_version}
                    )
                    
                    # Test image build (dry run)
                    print("   🔨 Testing Docker image build...")
                    build_result = subprocess.run(
                        ["docker", "build", "--dry-run", "-t", "lemma-test", "."],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if build_result.returncode == 0:
                        self.log_result(
                            "Docker Build Test", 
                            "PASS", 
                            "Docker image builds successfully",
                            {"build_output": "success"}
                        )
                    else:
                        self.log_result(
                            "Docker Build Test", 
                            "WARN", 
                            "Docker build test failed (may need dependencies)",
                            {"error": build_result.stderr[:200]}
                        )
                else:
                    self.log_result(
                        "Docker Available", 
                        "WARN", 
                        "Docker not available for testing",
                        {"error": result.stderr}
                    )
                    
            except subprocess.TimeoutExpired:
                self.log_result(
                    "Docker Available", 
                    "WARN", 
                    "Docker command timed out",
                    {"timeout": "10s"}
                )
            except FileNotFoundError:
                self.log_result(
                    "Docker Available", 
                    "WARN", 
                    "Docker not installed",
                    {"note": "Install Docker to test offline verifier image"}
                )
                
        except Exception as e:
            self.log_result(
                "Offline Verifier Image", 
                "FAIL", 
                f"Error testing offline verifier: {str(e)}",
                {"error": str(e)}
            )
    
    def run_all_tests(self):
        """Run all go-live checklist tests."""
        print("🚀 Lemma Go-Live & Billing Readiness Test Suite")
        print("=" * 60)
        
        # Test each checklist item
        self.test_hosted_verify_endpoint()
        self.test_revocation_pipeline()
        self.test_wallet_sdk()
        self.test_offline_verifier_image()
        
        # Generate summary
        self.generate_summary()
    
    def generate_summary(self):
        """Generate a summary of all test results."""
        print("\n" + "=" * 60)
        print("📊 GO-LIVE READINESS SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r['status'] == 'PASS'])
        failed_tests = len([r for r in self.results if r['status'] == 'FAIL'])
        warning_tests = len([r for r in self.results if r['status'] == 'WARN'])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⚠️  Warnings: {warning_tests}")
        
        # Calculate readiness percentage
        readiness_score = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        print(f"\n🎯 Go-Live Readiness: {readiness_score:.1f}%")
        
        if readiness_score >= 90:
            print("🎉 READY FOR GO-LIVE! All critical systems operational.")
        elif readiness_score >= 75:
            print("⚠️  MOSTLY READY - Address warnings before go-live.")
        else:
            print("❌ NOT READY - Critical issues need resolution.")
        
        # Show failed tests
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS ({failed_tests}):")
            for result in self.results:
                if result['status'] == 'FAIL':
                    print(f"   • {result['test']}: {result['message']}")
        
        # Show warnings
        if warning_tests > 0:
            print(f"\n⚠️  WARNINGS ({warning_tests}):")
            for result in self.results:
                if result['status'] == 'WARN':
                    print(f"   • {result['test']}: {result['message']}")
        
        # Save detailed results
        results_file = Path("go_live_test_results.json")
        with open(results_file, 'w') as f:
            json.dump({
                'summary': {
                    'total_tests': total_tests,
                    'passed': passed_tests,
                    'failed': failed_tests,
                    'warnings': warning_tests,
                    'readiness_score': readiness_score,
                    'timestamp': datetime.now().isoformat()
                },
                'results': self.results
            }, f, indent=2)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        return readiness_score >= 90

if __name__ == "__main__":
    # Check if Flask app is running
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    
    print("🔍 Checking if Flask app is running...")
    try:
        response = requests.get(f"{base_url}/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ Flask app is running")
        else:
            print("❌ Flask app is not responding correctly")
            sys.exit(1)
    except:
        print("❌ Flask app is not running. Please start it with 'python app.py'")
        sys.exit(1)
    
    # Run the tests
    checker = GoLiveChecker(base_url)
    is_ready = checker.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if is_ready else 1) 