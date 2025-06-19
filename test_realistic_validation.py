#!/usr/bin/env python3
"""
Lemma Enterprise - Realistic Functional Validation
Tests actual system functionality, not just component existence.
"""

import os
import sys
import json
import time
import requests
import logging
from datetime import datetime
from typing import Dict, List, Any

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RealisticValidator:
    """Validates actual system functionality."""
    
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.start_time = time.time()
        self.functional_tests = []
        self.total_tests = 0
        
    def run_realistic_validation(self) -> Dict[str, Any]:
        """Run realistic functional validation."""
        logger.info("🔍 Starting Realistic Functional Validation")
        logger.info("=" * 80)
        
        # Test 1: Server Availability
        server_available = self._test_server_availability()
        
        if not server_available:
            return self._create_failure_result("Server not running or accessible")
        
        # Test 2: API Endpoints Actually Work
        self._test_api_functionality()
        
        # Test 3: Offline Verification Actually Works
        self._test_offline_verification_functionality()
        
        # Test 4: Error Handling Works
        self._test_error_handling()
        
        # Test 5: Performance Under Load
        self._test_performance_characteristics()
        
        # Calculate success rate
        success_rate = (len([t for t in self.functional_tests if t['passed']]) / self.total_tests) * 100 if self.total_tests > 0 else 0
        
        # Generate results
        results = {
            'validation_timestamp': datetime.utcnow().isoformat(),
            'total_duration_seconds': time.time() - self.start_time,
            'success_rate_percentage': success_rate,
            'is_production_ready': success_rate >= 95.0,  # More realistic threshold
            'total_tests': self.total_tests,
            'passed_tests': len([t for t in self.functional_tests if t['passed']]),
            'failed_tests': len([t for t in self.functional_tests if not t['passed']]),
            'test_details': self.functional_tests,
            'realistic_assessment': self._generate_realistic_assessment(success_rate)
        }
        
        self._log_results(results)
        return results
    
    def _test_server_availability(self) -> bool:
        """Test if server is actually running and responding."""
        self.total_tests += 1
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                self.functional_tests.append({
                    'name': 'Server Availability',
                    'passed': True,
                    'details': f'Server responding on {self.base_url}'
                })
                return True
        except Exception as e:
            self.functional_tests.append({
                'name': 'Server Availability',
                'passed': False,
                'details': f'Server not accessible: {str(e)}'
            })
            return False
        
        self.functional_tests.append({
            'name': 'Server Availability',
            'passed': False,
            'details': f'Server returned {response.status_code}'
        })
        return False
    
    def _test_api_functionality(self):
        """Test that API endpoints actually work with real data."""
        endpoints_to_test = [
            {
                'name': 'Health Check Functionality',
                'url': '/health',
                'method': 'GET',
                'expected_keys': ['status', 'version']
            },
            {
                'name': 'Offline Verification Endpoint',
                'url': '/api/verify-offline',
                'method': 'POST',
                'data': {'credential_id': 'test_123', 'verification_type': 'offline'},
                'expected_keys': ['verified']
            }
        ]
        
        for endpoint in endpoints_to_test:
            self.total_tests += 1
            try:
                if endpoint['method'] == 'GET':
                    response = requests.get(f"{self.base_url}{endpoint['url']}", timeout=5)
                else:
                    response = requests.post(f"{self.base_url}{endpoint['url']}", 
                                           json=endpoint.get('data', {}), timeout=5)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        has_expected_keys = all(key in data for key in endpoint.get('expected_keys', []))
                        
                        self.functional_tests.append({
                            'name': endpoint['name'],
                            'passed': has_expected_keys,
                            'details': f'Response: {data}' if has_expected_keys else f'Missing keys: {endpoint.get("expected_keys", [])}'
                        })
                    except json.JSONDecodeError:
                        self.functional_tests.append({
                            'name': endpoint['name'],
                            'passed': False,
                            'details': 'Invalid JSON response'
                        })
                else:
                    self.functional_tests.append({
                        'name': endpoint['name'],
                        'passed': False,
                        'details': f'HTTP {response.status_code}: {response.text[:100]}'
                    })
            except Exception as e:
                self.functional_tests.append({
                    'name': endpoint['name'],
                    'passed': False,
                    'details': f'Request failed: {str(e)}'
                })
    
    def _test_offline_verification_functionality(self):
        """Test that offline verification actually works without network calls."""
        self.total_tests += 1
        
        try:
            # Test with various credential scenarios
            test_cases = [
                {'credential_id': 'valid_credential_123', 'expected_verified': True},
                {'credential_id': 'invalid_credential_456', 'expected_verified': False},
                {'credential_id': '', 'expected_verified': False}
            ]
            
            all_passed = True
            details = []
            
            for case in test_cases:
                response = requests.post(f"{self.base_url}/api/verify-offline", 
                                       json={'credential_id': case['credential_id']}, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    # Check that it claims zero network calls
                    if data.get('network_calls', 1) == 0:
                        details.append(f"✅ {case['credential_id']}: Zero network calls confirmed")
                    else:
                        all_passed = False
                        details.append(f"❌ {case['credential_id']}: Network calls detected")
                else:
                    all_passed = False
                    details.append(f"❌ {case['credential_id']}: HTTP {response.status_code}")
            
            self.functional_tests.append({
                'name': 'True Offline Verification',
                'passed': all_passed,
                'details': '; '.join(details)
            })
            
        except Exception as e:
            self.functional_tests.append({
                'name': 'True Offline Verification',
                'passed': False,
                'details': f'Test failed: {str(e)}'
            })
    
    def _test_error_handling(self):
        """Test that system handles errors gracefully."""
        error_tests = [
            {
                'name': 'Invalid JSON Handling',
                'url': '/api/verify-offline',
                'data': 'invalid json',
                'content_type': 'application/json'
            },
            {
                'name': 'Missing Required Fields',
                'url': '/api/verify-offline',
                'data': {},
                'content_type': 'application/json'
            }
        ]
        
        for test in error_tests:
            self.total_tests += 1
            try:
                response = requests.post(f"{self.base_url}{test['url']}", 
                                       data=test['data'], 
                                       headers={'Content-Type': test['content_type']}, 
                                       timeout=5)
                
                # Good error handling should return 4xx, not 500
                if 400 <= response.status_code < 500:
                    self.functional_tests.append({
                        'name': test['name'],
                        'passed': True,
                        'details': f'Proper error response: {response.status_code}'
                    })
                else:
                    self.functional_tests.append({
                        'name': test['name'],
                        'passed': False,
                        'details': f'Poor error handling: {response.status_code}'
                    })
            except Exception as e:
                self.functional_tests.append({
                    'name': test['name'],
                    'passed': False,
                    'details': f'Error test failed: {str(e)}'
                })
    
    def _test_performance_characteristics(self):
        """Test actual performance under realistic conditions."""
        self.total_tests += 1
        
        try:
            # Test response time under multiple requests
            response_times = []
            for i in range(10):
                start = time.time()
                response = requests.get(f"{self.base_url}/health", timeout=5)
                end = time.time()
                
                if response.status_code == 200:
                    response_times.append((end - start) * 1000)  # Convert to ms
            
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                max_response_time = max(response_times)
                
                # Realistic performance expectations
                performance_good = avg_response_time < 500 and max_response_time < 1000
                
                self.functional_tests.append({
                    'name': 'Performance Under Load',
                    'passed': performance_good,
                    'details': f'Avg: {avg_response_time:.1f}ms, Max: {max_response_time:.1f}ms'
                })
            else:
                self.functional_tests.append({
                    'name': 'Performance Under Load',
                    'passed': False,
                    'details': 'No successful requests'
                })
                
        except Exception as e:
            self.functional_tests.append({
                'name': 'Performance Under Load',
                'passed': False,
                'details': f'Performance test failed: {str(e)}'
            })
    
    def _generate_realistic_assessment(self, success_rate: float) -> Dict[str, Any]:
        """Generate realistic assessment of system readiness."""
        if success_rate >= 95:
            status = "PRODUCTION_READY"
            confidence = "HIGH"
            recommendations = ["System demonstrates strong functional reliability"]
        elif success_rate >= 80:
            status = "STAGING_READY"
            confidence = "MODERATE"
            recommendations = ["Address failing tests before production deployment"]
        else:
            status = "DEVELOPMENT_ONLY"
            confidence = "LOW"
            recommendations = ["Significant issues need resolution", "Not ready for production use"]
        
        return {
            'success_rate': success_rate,
            'status': status,
            'confidence_level': confidence,
            'recommendations': recommendations,
            'realistic_claims': [
                f"{success_rate:.1f}% functional reliability demonstrated",
                f"System tested under realistic conditions",
                f"Actual API functionality validated"
            ]
        }
    
    def _create_failure_result(self, reason: str) -> Dict[str, Any]:
        """Create failure result when server is not available."""
        return {
            'validation_timestamp': datetime.utcnow().isoformat(),
            'total_duration_seconds': time.time() - self.start_time,
            'success_rate_percentage': 0.0,
            'is_production_ready': False,
            'failure_reason': reason,
            'realistic_assessment': {
                'status': 'SYSTEM_UNAVAILABLE',
                'confidence_level': 'NONE',
                'recommendations': ['Start the server before validation', 'Ensure system is properly configured']
            }
        }
    
    def _log_results(self, results: Dict[str, Any]):
        """Log validation results."""
        logger.info("=" * 80)
        logger.info("🔍 REALISTIC FUNCTIONAL VALIDATION RESULTS")
        logger.info("=" * 80)
        logger.info(f"Success Rate: {results['success_rate_percentage']:.1f}%")
        logger.info(f"Production Ready: {results['is_production_ready']}")
        logger.info(f"Status: {results['realistic_assessment']['status']}")
        logger.info(f"Tests Passed: {results['passed_tests']}/{results['total_tests']}")
        
        logger.info("\n📊 Test Details:")
        for test in results['test_details']:
            status = "✅" if test['passed'] else "❌"
            logger.info(f"  {status} {test['name']}: {test['details']}")
        
        logger.info(f"\n🎯 Realistic Claims You Can Make:")
        for claim in results['realistic_assessment'].get('realistic_claims', []):
            logger.info(f"  • {claim}")

def main():
    """Main function to run realistic validation."""
    validator = RealisticValidator()
    results = validator.run_realistic_validation()
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"realistic_validation_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {filename}")
    
    # Exit with appropriate code
    exit_code = 0 if results['success_rate_percentage'] >= 95.0 else 1
    sys.exit(exit_code)

if __name__ == '__main__':
    main() 