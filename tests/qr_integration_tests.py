"""
Lemma QR System - End-to-End Integration Tests
Phase 4: Production readiness testing framework

This module provides comprehensive integration testing for the entire QR system,
covering all phases from Rust core to frontend interfaces.
"""

import unittest
import time
import json
import requests
import asyncio
from unittest.mock import patch, MagicMock
from typing import Dict, List, Any, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QRIntegrationTestSuite(unittest.TestCase):
    """Comprehensive integration test suite for QR system"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.base_url = "http://localhost:5000"
        cls.api_endpoints = {
            'generate': f"{cls.base_url}/api/qr/generate",
            'verify': f"{cls.base_url}/api/qr/verify",
            'types': f"{cls.base_url}/api/qr/types"
        }
        cls.test_data = cls._load_test_data()
        cls.performance_targets = {
            'api_generation': 5.0,  # µs
            'api_verification': 5.0,  # µs
            'wasm_verification': 0.5,  # µs
            'throughput': 1000  # QR/sec minimum
        }
        
    @classmethod
    def _load_test_data(cls) -> Dict[str, Any]:
        """Load test data for different QR types"""
        return {
            'ticket': {
                'event_name': 'Integration Test Concert',
                'event_id': 'TEST_EVENT_001',
                'seat': 'Section A, Row 1, Seat 1',
                'venue': 'Test Arena',
                'price_paid': '$100.00',
                'purchaser_did': 'did:lemma:test:user123',
                'valid_until': '2024-12-31T23:59:59Z'
            },
            'product': {
                'product_name': 'Test Product',
                'product_id': 'TEST_PROD_001',
                'manufacturer': 'Test Manufacturing Co.',
                'serial_number': 'SN_TEST_123456',
                'batch_number': 'BATCH_TEST_001',
                'manufacture_date': '2024-01-15'
            },
            'access': {
                'employee_name': 'Test Employee',
                'employee_id': 'EMP_TEST_001',
                'department': 'Testing Department',
                'access_level': 'Advanced',
                'clearance': 'Level 3',
                'valid_from': '2024-01-01T00:00:00Z',
                'valid_until': '2024-12-31T23:59:59Z'
            },
            'identity': {
                'identity_did': 'did:lemma:test:identity123',
                'verification_type': 'age_verification',
                'age_over_18': True,
                'age_over_21': True,
                'country': 'United States',
                'state': 'California'
            }
        }

    def test_01_system_health_check(self):
        """Test system health and availability"""
        logger.info("🏥 Testing system health...")
        
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=5)
            self.assertEqual(response.status_code, 200)
            logger.info("✅ System health check passed")
        except requests.RequestException as e:
            self.fail(f"❌ System health check failed: {e}")

    def test_02_api_endpoints_availability(self):
        """Test all QR API endpoints are available"""
        logger.info("🌐 Testing API endpoint availability...")
        
        # Test QR types endpoint
        response = requests.get(self.api_endpoints['types'])
        self.assertEqual(response.status_code, 200)
        
        types_data = response.json()
        self.assertTrue(types_data.get('success'))
        self.assertIn('qr_types', types_data)
        
        expected_types = ['ticket', 'product', 'access', 'identity']
        for qr_type in expected_types:
            self.assertIn(qr_type, types_data['qr_types'])
            
        logger.info("✅ All API endpoints are available")

    def test_03_qr_generation_all_types(self):
        """Test QR generation for all supported types"""
        logger.info("🔄 Testing QR generation for all types...")
        
        generation_times = []
        
        for qr_type, claims in self.test_data.items():
            with self.subTest(qr_type=qr_type):
                start_time = time.perf_counter()
                
                response = requests.post(
                    self.api_endpoints['generate'],
                    json={'type': qr_type, 'claims': claims},
                    headers={'Content-Type': 'application/json'}
                )
                
                end_time = time.perf_counter()
                generation_time = (end_time - start_time) * 1_000_000  # Convert to µs
                generation_times.append(generation_time)
                
                self.assertEqual(response.status_code, 200)
                
                data = response.json()
                self.assertTrue(data.get('success'))
                self.assertIn('qr_image', data)
                self.assertIn('generation_time_us', data)
                self.assertEqual(data.get('type'), qr_type)
                
                # Performance check
                api_time = data.get('generation_time_us', generation_time)
                self.assertLess(
                    api_time, 
                    self.performance_targets['api_generation'] * 1000,  # Convert to µs
                    f"Generation time {api_time}µs exceeds target for {qr_type}"
                )
                
                logger.info(f"✅ {qr_type} QR generated in {api_time:.2f}µs")
        
        avg_generation_time = sum(generation_times) / len(generation_times)
        logger.info(f"📊 Average generation time: {avg_generation_time:.2f}µs")

    def test_04_qr_verification_workflow(self):
        """Test complete QR generation -> verification workflow"""
        logger.info("🔍 Testing complete QR workflow...")
        
        for qr_type, claims in self.test_data.items():
            with self.subTest(qr_type=qr_type):
                # Step 1: Generate QR
                gen_response = requests.post(
                    self.api_endpoints['generate'],
                    json={'type': qr_type, 'claims': claims}
                )
                self.assertEqual(gen_response.status_code, 200)
                gen_data = gen_response.json()
                
                # Step 2: Verify QR
                start_time = time.perf_counter()
                
                verify_response = requests.post(
                    self.api_endpoints['verify'],
                    json={
                        'qr_data': json.dumps({
                            'lemma': gen_data.get('lemma', {}),
                            'qr_type': qr_type
                        }),
                        'expected_type': qr_type
                    }
                )
                
                end_time = time.perf_counter()
                verification_time = (end_time - start_time) * 1_000_000
                
                self.assertEqual(verify_response.status_code, 200)
                verify_data = verify_response.json()
                
                self.assertTrue(verify_data.get('success'))
                self.assertTrue(verify_data.get('verified'))
                self.assertEqual(verify_data.get('qr_type'), qr_type)
                
                # Performance check
                api_time = verify_data.get('verification_time_us', verification_time)
                self.assertLess(
                    api_time,
                    self.performance_targets['api_verification'] * 1000,
                    f"Verification time {api_time}µs exceeds target for {qr_type}"
                )
                
                logger.info(f"✅ {qr_type} QR workflow completed in {api_time:.2f}µs")

    def test_05_batch_generation_performance(self):
        """Test batch QR generation performance"""
        logger.info("⚡ Testing batch generation performance...")
        
        batch_size = 100
        qr_types = list(self.test_data.keys())
        
        start_time = time.perf_counter()
        successful_generations = 0
        
        for i in range(batch_size):
            qr_type = qr_types[i % len(qr_types)]
            claims = self.test_data[qr_type].copy()
            claims['batch_id'] = i
            
            try:
                response = requests.post(
                    self.api_endpoints['generate'],
                    json={'type': qr_type, 'claims': claims},
                    timeout=5
                )
                if response.status_code == 200:
                    successful_generations += 1
            except requests.RequestException:
                continue
        
        end_time = time.perf_counter()
        total_time = end_time - start_time
        throughput = successful_generations / total_time
        
        self.assertGreaterEqual(
            throughput,
            self.performance_targets['throughput'],
            f"Throughput {throughput:.1f} QR/sec below target"
        )
        
        logger.info(f"✅ Batch generation: {successful_generations}/{batch_size} successful")
        logger.info(f"📊 Throughput: {throughput:.1f} QR/sec")

    def test_06_concurrent_verification_load(self):
        """Test concurrent verification load handling"""
        logger.info("🚀 Testing concurrent verification load...")
        
        # Generate test QR codes first
        test_qrs = []
        for qr_type, claims in self.test_data.items():
            response = requests.post(
                self.api_endpoints['generate'],
                json={'type': qr_type, 'claims': claims}
            )
            if response.status_code == 200:
                test_qrs.append((qr_type, response.json()))
        
        # Simulate concurrent verification
        concurrent_requests = 50
        successful_verifications = 0
        start_time = time.perf_counter()
        
        for i in range(concurrent_requests):
            qr_type, qr_data = test_qrs[i % len(test_qrs)]
            
            try:
                response = requests.post(
                    self.api_endpoints['verify'],
                    json={
                        'qr_data': json.dumps({
                            'lemma': qr_data.get('lemma', {}),
                            'qr_type': qr_type
                        }),
                        'expected_type': qr_type
                    },
                    timeout=5
                )
                if response.status_code == 200 and response.json().get('verified'):
                    successful_verifications += 1
            except requests.RequestException:
                continue
        
        end_time = time.perf_counter()
        success_rate = (successful_verifications / concurrent_requests) * 100
        
        self.assertGreaterEqual(
            success_rate,
            95.0,
            f"Success rate {success_rate:.1f}% below 95% threshold"
        )
        
        logger.info(f"✅ Concurrent load test: {success_rate:.1f}% success rate")

    def test_07_error_handling_and_validation(self):
        """Test error handling and input validation"""
        logger.info("🛡️ Testing error handling and validation...")
        
        # Test invalid QR type
        response = requests.post(
            self.api_endpoints['generate'],
            json={'type': 'invalid_type', 'claims': {}}
        )
        self.assertNotEqual(response.status_code, 200)
        
        # Test missing claims
        response = requests.post(
            self.api_endpoints['generate'],
            json={'type': 'ticket'}
        )
        self.assertNotEqual(response.status_code, 200)
        
        # Test invalid verification data
        response = requests.post(
            self.api_endpoints['verify'],
            json={'qr_data': 'invalid_json'}
        )
        self.assertNotEqual(response.status_code, 200)
        
        logger.info("✅ Error handling tests passed")

    def test_08_security_validation(self):
        """Test security features and tamper detection"""
        logger.info("🔒 Testing security validation...")
        
        # Generate a valid QR
        response = requests.post(
            self.api_endpoints['generate'],
            json={'type': 'ticket', 'claims': self.test_data['ticket']}
        )
        self.assertEqual(response.status_code, 200)
        qr_data = response.json()
        
        # Test tampering detection (modify lemma data)
        tampered_data = qr_data.copy()
        if 'lemma' in tampered_data:
            tampered_data['lemma']['claims'] = {'fake': 'data'}
        
        response = requests.post(
            self.api_endpoints['verify'],
            json={
                'qr_data': json.dumps(tampered_data),
                'expected_type': 'ticket'
            }
        )
        
        # Should detect tampering
        if response.status_code == 200:
            verify_data = response.json()
            self.assertFalse(
                verify_data.get('verified', True),
                "Tampered QR was incorrectly verified as valid"
            )
        
        logger.info("✅ Security validation tests passed")

    def test_09_frontend_integration(self):
        """Test frontend page accessibility"""
        logger.info("🌐 Testing frontend integration...")
        
        frontend_pages = [
            f"{self.base_url}/demo/qr",
            f"{self.base_url}/demo/qr/generator",
            f"{self.base_url}/demo/qr/scanner",
            f"{self.base_url}/demo/qr/use-cases",
            f"{self.base_url}/demo/qr/wasm",
            f"{self.base_url}/demo/qr/advanced"
        ]
        
        for page_url in frontend_pages:
            with self.subTest(page=page_url):
                try:
                    response = requests.get(page_url, timeout=10)
                    self.assertEqual(
                        response.status_code, 200,
                        f"Frontend page {page_url} not accessible"
                    )
                except requests.RequestException as e:
                    self.fail(f"Frontend page {page_url} failed: {e}")
        
        logger.info("✅ All frontend pages accessible")

    def test_10_system_performance_benchmark(self):
        """Final system performance benchmark"""
        logger.info("📊 Running final performance benchmark...")
        
        benchmark_results = {
            'api_generation_avg': 0,
            'api_verification_avg': 0,
            'throughput': 0,
            'success_rate': 0
        }
        
        # Benchmark API generation
        generation_times = []
        for _ in range(10):
            start_time = time.perf_counter()
            response = requests.post(
                self.api_endpoints['generate'],
                json={'type': 'ticket', 'claims': self.test_data['ticket']}
            )
            end_time = time.perf_counter()
            
            if response.status_code == 200:
                generation_times.append((end_time - start_time) * 1_000_000)
        
        benchmark_results['api_generation_avg'] = sum(generation_times) / len(generation_times)
        
        # Benchmark API verification
        verification_times = []
        for _ in range(10):
            # Generate QR first
            gen_response = requests.post(
                self.api_endpoints['generate'],
                json={'type': 'ticket', 'claims': self.test_data['ticket']}
            )
            
            if gen_response.status_code == 200:
                start_time = time.perf_counter()
                verify_response = requests.post(
                    self.api_endpoints['verify'],
                    json={
                        'qr_data': json.dumps({
                            'lemma': gen_response.json().get('lemma', {}),
                            'qr_type': 'ticket'
                        }),
                        'expected_type': 'ticket'
                    }
                )
                end_time = time.perf_counter()
                
                if verify_response.status_code == 200:
                    verification_times.append((end_time - start_time) * 1_000_000)
        
        benchmark_results['api_verification_avg'] = sum(verification_times) / len(verification_times)
        
        # Log benchmark results
        logger.info("🏆 FINAL BENCHMARK RESULTS:")
        logger.info(f"   API Generation: {benchmark_results['api_generation_avg']:.2f}µs")
        logger.info(f"   API Verification: {benchmark_results['api_verification_avg']:.2f}µs")
        logger.info(f"   Target Generation: ≤{self.performance_targets['api_generation']*1000}µs")
        logger.info(f"   Target Verification: ≤{self.performance_targets['api_verification']*1000}µs")
        
        # Assert performance targets met
        self.assertLess(
            benchmark_results['api_generation_avg'],
            self.performance_targets['api_generation'] * 1000,
            "API generation performance below target"
        )
        
        self.assertLess(
            benchmark_results['api_verification_avg'],
            self.performance_targets['api_verification'] * 1000,
            "API verification performance below target"
        )
        
        logger.info("✅ All performance targets met!")

def run_integration_tests():
    """Run the complete integration test suite"""
    # Configure test runner
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(QRIntegrationTestSuite)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=None,
        descriptions=True,
        failfast=False
    )
    
    logger.info("🚀 Starting Lemma QR System Integration Tests...")
    logger.info("=" * 60)
    
    result = runner.run(suite)
    
    logger.info("=" * 60)
    logger.info("📊 INTEGRATION TEST SUMMARY:")
    logger.info(f"   Tests Run: {result.testsRun}")
    logger.info(f"   Failures: {len(result.failures)}")
    logger.info(f"   Errors: {len(result.errors)}")
    logger.info(f"   Success Rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.wasSuccessful():
        logger.info("🎉 ALL INTEGRATION TESTS PASSED!")
        logger.info("✅ System is ready for production deployment")
    else:
        logger.error("❌ Some integration tests failed")
        logger.error("🔧 Please review and fix issues before deployment")
    
    return result.wasSuccessful()

if __name__ == '__main__':
    success = run_integration_tests()
    exit(0 if success else 1) 