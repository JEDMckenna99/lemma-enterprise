#!/usr/bin/env python3
"""
Lemma Enterprise - 100% Real-World Compliance Validation Test
Tests the actual running system for true production readiness.
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime
from typing import Dict, List, Any

# Add lemma package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RealWorldComplianceValidator:
    """Real-world compliance validator that tests the actual running system."""
    
    def __init__(self):
        self.base_url = "http://localhost:5000"
        self.api_key = os.getenv('LEMMA_API_KEY', 'test_api_key')
        self.headers = {'X-API-Key': self.api_key, 'Content-Type': 'application/json'}
        self.start_time = time.time()
        
    def run_real_world_validation(self) -> Dict[str, Any]:
        """Run comprehensive real-world validation of the running system."""
        logger.info("🚀 Starting Real-World 100% Compliance Validation")
        logger.info("=" * 80)
        
        # Test system availability first
        system_health = self._test_system_health()
        if not system_health['healthy']:
            return self._create_failure_result("System not healthy", system_health)
        
        # Run all compliance tests
        test_results = {}
        
        # Test 1: System Health & Configuration
        test_results['system_health'] = self._test_comprehensive_health()
        
        # Test 2: API Endpoints Availability
        test_results['api_endpoints'] = self._test_api_endpoints()
        
        # Test 3: Offline Verification Functionality
        test_results['offline_verification'] = self._test_offline_verification()
        
        # Test 4: Security & Compliance
        test_results['security_compliance'] = self._test_security_compliance()
        
        # Test 5: Performance & Reliability
        test_results['performance'] = self._test_performance()
        
        # Test 6: Production Readiness
        test_results['production_readiness'] = self._test_production_readiness()
        
        # Calculate overall success rate
        success_rate = self._calculate_success_rate(test_results)
        
        # Generate final results
        final_results = {
            'validation_timestamp': datetime.utcnow().isoformat(),
            'total_duration_seconds': time.time() - self.start_time,
            'success_rate_percentage': success_rate,
            'is_production_ready': success_rate >= 100.0,
            'test_results': test_results,
            'summary': self._generate_summary(test_results, success_rate)
        }
        
        # Log and save results
        self._log_results(final_results)
        self._save_results(final_results)
        
        return final_results
    
    def _test_system_health(self) -> Dict[str, Any]:
        """Test basic system health."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return {
                'healthy': response.status_code == 200,
                'status_code': response.status_code,
                'response': response.json() if response.status_code == 200 else None
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e)
            }
    
    def _test_comprehensive_health(self) -> Dict[str, Any]:
        """Test comprehensive system health."""
        logger.info("Testing comprehensive system health...")
        
        results = {
            'tests_passed': 0,
            'tests_total': 0,
            'details': {}
        }
        
        # Test 1: Health endpoint
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            results['tests_total'] += 1
            if response.status_code == 200:
                results['tests_passed'] += 1
                results['details']['health_endpoint'] = {'success': True, 'response': response.json()}
            else:
                results['details']['health_endpoint'] = {'success': False, 'status_code': response.status_code}
        except Exception as e:
            results['tests_total'] += 1
            results['details']['health_endpoint'] = {'success': False, 'error': str(e)}
        
        # Test 2: Environment variables
        results['tests_total'] += 1
        if os.getenv('LEMMA_API_KEY') and os.getenv('LEMMA_SECRET_KEY'):
            results['tests_passed'] += 1
            results['details']['environment_vars'] = {'success': True, 'api_key_set': True, 'secret_key_set': True}
        else:
            results['details']['environment_vars'] = {'success': False, 'missing_vars': True}
        
        # Test 3: Basic API availability
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            results['tests_total'] += 1
            if response.status_code in [200, 302]:  # 302 for redirects is OK
                results['tests_passed'] += 1
                results['details']['basic_api'] = {'success': True, 'status_code': response.status_code}
            else:
                results['details']['basic_api'] = {'success': False, 'status_code': response.status_code}
        except Exception as e:
            results['tests_total'] += 1
            results['details']['basic_api'] = {'success': False, 'error': str(e)}
        
        return results
    
    def _test_api_endpoints(self) -> Dict[str, Any]:
        """Test critical API endpoints."""
        logger.info("Testing critical API endpoints...")
        
        results = {
            'tests_passed': 0,
            'tests_total': 0,
            'details': {}
        }
        
        # Critical endpoints to test
        endpoints = [
            {'path': '/health', 'method': 'GET', 'expected_status': 200},
            {'path': '/api/verify-offline', 'method': 'POST', 'expected_status': 200},
            {'path': '/api/compliance/status', 'method': 'GET', 'expected_status': 200},
        ]
        
        for endpoint in endpoints:
            results['tests_total'] += 1
            try:
                if endpoint['method'] == 'GET':
                    response = requests.get(f"{self.base_url}{endpoint['path']}", 
                                          headers=self.headers, timeout=5)
                else:
                    response = requests.post(f"{self.base_url}{endpoint['path']}", 
                                           json={}, headers=self.headers, timeout=5)
                
                if response.status_code == endpoint['expected_status']:
                    results['tests_passed'] += 1
                    results['details'][endpoint['path']] = {
                        'success': True, 
                        'status_code': response.status_code,
                        'response_time_ms': response.elapsed.total_seconds() * 1000
                    }
                else:
                    results['details'][endpoint['path']] = {
                        'success': False, 
                        'status_code': response.status_code,
                        'expected': endpoint['expected_status']
                    }
            except Exception as e:
                results['details'][endpoint['path']] = {'success': False, 'error': str(e)}
        
        return results
    
    def _test_offline_verification(self) -> Dict[str, Any]:
        """Test offline verification functionality."""
        logger.info("Testing offline verification functionality...")
        
        results = {
            'tests_passed': 0,
            'tests_total': 0,
            'details': {}
        }
        
        # Test offline verification endpoint
        results['tests_total'] += 1
        try:
            test_data = {
                'credential_id': 'test_credential_123',
                'verification_type': 'offline'
            }
            
            response = requests.post(f"{self.base_url}/api/verify-offline", 
                                   json=test_data, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('verified') and data.get('network_calls') == 0:
                    results['tests_passed'] += 1
                    results['details']['offline_verification'] = {
                        'success': True,
                        'verified': data.get('verified'),
                        'latency_ms': data.get('latency_ms'),
                        'network_calls': data.get('network_calls')
                    }
                else:
                    results['details']['offline_verification'] = {
                        'success': False,
                        'reason': 'Verification failed or network calls detected'
                    }
            else:
                results['details']['offline_verification'] = {
                    'success': False,
                    'status_code': response.status_code
                }
        except Exception as e:
            results['details']['offline_verification'] = {'success': False, 'error': str(e)}
        
        return results
    
    def _test_security_compliance(self) -> Dict[str, Any]:
        """Test security and compliance features."""
        logger.info("Testing security and compliance...")
        
        results = {
            'tests_passed': 0,
            'tests_total': 0,
            'details': {}
        }
        
        # Test compliance status endpoint
        results['tests_total'] += 1
        try:
            response = requests.get(f"{self.base_url}/api/compliance/status", 
                                  headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                compliance_checks = ['gdpr_compliant', 'iso27001_compliant', 'soc2_compliant']
                all_compliant = all(data.get(check, False) for check in compliance_checks)
                
                if all_compliant:
                    results['tests_passed'] += 1
                    results['details']['compliance_status'] = {
                        'success': True,
                        'compliance_data': data
                    }
                else:
                    results['details']['compliance_status'] = {
                        'success': False,
                        'reason': 'Not all compliance checks passed'
                    }
            else:
                results['details']['compliance_status'] = {
                    'success': False,
                    'status_code': response.status_code
                }
        except Exception as e:
            results['details']['compliance_status'] = {'success': False, 'error': str(e)}
        
        return results
    
    def _test_performance(self) -> Dict[str, Any]:
        """Test performance characteristics."""
        logger.info("Testing performance...")
        
        results = {
            'tests_passed': 0,
            'tests_total': 0,
            'details': {}
        }
        
        # Test response time
        results['tests_total'] += 1
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/health", timeout=5)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200 and response_time < 1000:  # Under 1 second
                results['tests_passed'] += 1
                results['details']['response_time'] = {
                    'success': True,
                    'response_time_ms': response_time
                }
            else:
                results['details']['response_time'] = {
                    'success': False,
                    'response_time_ms': response_time,
                    'status_code': response.status_code
                }
        except Exception as e:
            results['details']['response_time'] = {'success': False, 'error': str(e)}
        
        return results
    
    def _test_production_readiness(self) -> Dict[str, Any]:
        """Test production readiness indicators."""
        logger.info("Testing production readiness...")
        
        results = {
            'tests_passed': 0,
            'tests_total': 0,
            'details': {}
        }
        
        # Test health endpoint for production indicators
        results['tests_total'] += 1
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('production_ready') and data.get('compliance') == '100%':
                    results['tests_passed'] += 1
                    results['details']['production_indicators'] = {
                        'success': True,
                        'production_ready': data.get('production_ready'),
                        'compliance': data.get('compliance'),
                        'version': data.get('version')
                    }
                else:
                    results['details']['production_indicators'] = {
                        'success': False,
                        'reason': 'Production readiness indicators not met'
                    }
            else:
                results['details']['production_indicators'] = {
                    'success': False,
                    'status_code': response.status_code
                }
        except Exception as e:
            results['details']['production_indicators'] = {'success': False, 'error': str(e)}
        
        return results
    
    def _calculate_success_rate(self, test_results: Dict[str, Any]) -> float:
        """Calculate overall success rate."""
        total_tests = 0
        passed_tests = 0
        
        for category, results in test_results.items():
            total_tests += results.get('tests_total', 0)
            passed_tests += results.get('tests_passed', 0)
        
        if total_tests == 0:
            return 0.0
        
        return (passed_tests / total_tests) * 100
    
    def _generate_summary(self, test_results: Dict[str, Any], success_rate: float) -> Dict[str, Any]:
        """Generate validation summary."""
        return {
            'success_rate': success_rate,
            'production_ready': success_rate >= 100.0,
            'status': 'PRODUCTION_READY' if success_rate >= 100.0 else 'NEEDS_IMPROVEMENT',
            'total_tests': sum(r.get('tests_total', 0) for r in test_results.values()),
            'passed_tests': sum(r.get('tests_passed', 0) for r in test_results.values()),
            'failed_tests': sum(r.get('tests_total', 0) - r.get('tests_passed', 0) for r in test_results.values()),
            'recommendations': [] if success_rate >= 100.0 else ['Fix failing tests to achieve 100% success rate']
        }
    
    def _create_failure_result(self, reason: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Create failure result when system is not available."""
        return {
            'validation_timestamp': datetime.utcnow().isoformat(),
            'total_duration_seconds': time.time() - self.start_time,
            'success_rate_percentage': 0.0,
            'is_production_ready': False,
            'failure_reason': reason,
            'failure_details': details,
            'summary': {
                'success_rate': 0.0,
                'production_ready': False,
                'status': 'SYSTEM_UNAVAILABLE',
                'recommendations': ['Start the Lemma server', 'Fix system health issues']
            }
        }
    
    def _log_results(self, results: Dict[str, Any]):
        """Log validation results."""
        logger.info("=" * 80)
        logger.info("🎯 REAL-WORLD COMPLIANCE VALIDATION RESULTS")
        logger.info("=" * 80)
        logger.info(f"Success Rate: {results['success_rate_percentage']:.1f}%")
        logger.info(f"Production Ready: {results['is_production_ready']}")
        logger.info(f"Status: {results['summary']['status']}")
        
        if results['success_rate_percentage'] >= 100.0:
            logger.info("🎉 CONGRATULATIONS! You've achieved 100% real-world success probability!")
        else:
            logger.info("🔧 Areas for improvement:")
            for rec in results['summary'].get('recommendations', []):
                logger.info(f"  - {rec}")
    
    def _save_results(self, results: Dict[str, Any]):
        """Save results to file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"real_world_compliance_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Results saved to: {filename}")

def main():
    """Main function to run real-world compliance validation."""
    validator = RealWorldComplianceValidator()
    results = validator.run_real_world_validation()
    
    # Exit with appropriate code
    exit_code = 0 if results['success_rate_percentage'] >= 100.0 else 1
    sys.exit(exit_code)

if __name__ == '__main__':
    main()