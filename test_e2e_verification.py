#!/usr/bin/env python3
"""
Lemma End-to-End Verification Test Script

This script demonstrates how to test the entire Lemma verification chain
to ensure all components are working correctly after credential minting
or Shield verification.

Usage:
    python test_e2e_verification.py
    python test_e2e_verification.py --test-existing-user user123
    python test_e2e_verification.py --full-chain-test
"""

import requests
import json
import time
import argparse
import sys
from datetime import datetime

class LemmaE2EVerificationTester:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        
    def test_credential_minting_and_verification(self, user_id=None):
        """
        Test the complete flow:
        1. Issue a new credential
        2. Immediately run E2E verification
        3. Validate the entire chain works
        """
        print("🧪 Testing Credential Minting + E2E Verification")
        print("=" * 60)
        
        # Generate test user ID if not provided
        if not user_id:
            user_id = f"test-user-{int(time.time())}"
        
        print(f"📋 Test User ID: {user_id}")
        
        try:
            # Step 1: Issue a credential
            print("\n📝 Step 1: Issuing credential...")
            issue_response = self.session.post(
                f"{self.base_url}/api/issue-credential",
                json={"user_id": user_id},
                headers={"X-API-Key": "your-api-key-here"}  # Replace with actual key
            )
            
            if issue_response.status_code != 200:
                print(f"❌ Credential issuance failed: {issue_response.status_code}")
                print(f"Response: {issue_response.text}")
                return False
            
            credential_data = issue_response.json()
            credential = credential_data.get('credential')
            
            if not credential:
                print("❌ No credential returned from issuance")
                return False
                
            print(f"✅ Credential issued successfully")
            print(f"   Credential ID: {credential.get('id')}")
            print(f"   Issuer: {credential.get('issuer')}")
            print(f"   Subject: {credential.get('credentialSubject', {}).get('id')}")
            
            # Step 2: Run immediate E2E verification
            print("\n🔍 Step 2: Running immediate E2E verification...")
            
            e2e_response = self.session.post(
                f"{self.base_url}/api/end-to-end-verification-test",
                json={
                    "user_id": user_id,
                    "credential": credential,
                    "force_new_credential": False,
                    "test_shield_flow": True,
                    "test_revocation": True,
                    "test_background_verification": True,
                    "cleanup_test_data": True
                }
            )
            
            if e2e_response.status_code not in [200, 202]:
                print(f"❌ E2E verification failed: {e2e_response.status_code}")
                print(f"Response: {e2e_response.text}")
                return False
            
            e2e_results = e2e_response.json()
            
            # Step 3: Analyze results
            print(f"\n📊 Step 3: Analyzing E2E verification results...")
            self.print_e2e_results(e2e_results)
            
            return e2e_results.get('overall_success', False)
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {e}")
            return False
        except Exception as e:
            print(f"❌ Test error: {e}")
            return False
    
    def test_shield_verification_chain(self, user_id=None):
        """
        Test the Shield verification chain end-to-end
        """
        print("🛡️ Testing Shield Verification Chain")
        print("=" * 60)
        
        if not user_id:
            user_id = f"test-shield-{int(time.time())}"
        
        print(f"📋 Test User ID: {user_id}")
        
        try:
            # Run E2E test focusing on Shield flow
            print("\n🔍 Running Shield-focused E2E verification...")
            
            e2e_response = self.session.post(
                f"{self.base_url}/api/end-to-end-verification-test",
                json={
                    "user_id": user_id,
                    "force_new_credential": True,  # Force new credential for testing
                    "test_shield_flow": True,
                    "test_revocation": True,
                    "test_background_verification": True,
                    "cleanup_test_data": True
                }
            )
            
            if e2e_response.status_code not in [200, 202]:
                print(f"❌ Shield E2E verification failed: {e2e_response.status_code}")
                print(f"Response: {e2e_response.text}")
                return False
            
            e2e_results = e2e_response.json()
            
            # Analyze Shield-specific results
            print(f"\n📊 Analyzing Shield verification results...")
            self.print_e2e_results(e2e_results)
            
            # Check Shield-specific components
            shield_tests = e2e_results.get('tests', {})
            shield_api_result = shield_tests.get('shield_api_chain', {})
            
            if shield_api_result.get('success'):
                print("✅ Shield API chain is fully operational")
            else:
                print("❌ Shield API chain has issues")
                print(f"   Error: {shield_api_result.get('error')}")
            
            return e2e_results.get('overall_success', False)
            
        except Exception as e:
            print(f"❌ Shield test error: {e}")
            return False
    
    def test_monitoring_endpoint(self):
        """
        Test the E2E verification as a monitoring endpoint
        """
        print("📊 Testing E2E Verification for Monitoring")
        print("=" * 60)
        
        try:
            # Run a quick monitoring check
            monitor_response = self.session.post(
                f"{self.base_url}/api/end-to-end-verification-test",
                json={
                    "test_shield_flow": True,
                    "test_revocation": True,
                    "cleanup_test_data": True,
                    "timeout_ms": 5000  # Quick 5-second timeout for monitoring
                }
            )
            
            if monitor_response.status_code not in [200, 202]:
                print(f"❌ Monitoring check failed: {monitor_response.status_code}")
                return False
            
            results = monitor_response.json()
            
            print(f"📈 Monitoring Results:")
            print(f"   Overall Success: {results.get('overall_success')}")
            print(f"   Success Rate: {results.get('success_rate')}%")
            print(f"   Total Time: {results.get('performance', {}).get('total_test_time_ms')}ms")
            print(f"   Tests Passed: {results.get('summary', {}).get('tests_passed')}/{results.get('summary', {}).get('total_tests')}")
            
            if results.get('errors'):
                print(f"❌ Errors detected: {len(results['errors'])}")
                for error in results['errors']:
                    print(f"   - {error}")
            
            if results.get('warnings'):
                print(f"⚠️ Warnings: {len(results['warnings'])}")
                for warning in results['warnings']:
                    print(f"   - {warning}")
            
            return results.get('overall_success', False)
            
        except Exception as e:
            print(f"❌ Monitoring test error: {e}")
            return False
    
    def print_e2e_results(self, results):
        """
        Print detailed E2E verification results
        """
        print(f"🎯 Overall Success: {results.get('overall_success')}")
        print(f"📈 Success Rate: {results.get('success_rate')}%")
        print(f"⏱️ Total Time: {results.get('performance', {}).get('total_test_time_ms')}ms")
        print(f"📋 Test ID: {results.get('test_id')}")
        
        # Print individual test results
        tests = results.get('tests', {})
        print(f"\n🔍 Individual Test Results:")
        for test_name, test_result in tests.items():
            status = "✅" if test_result.get('success') else "❌"
            print(f"   {status} {test_name}: {test_result.get('success')}")
            if not test_result.get('success') and test_result.get('error'):
                print(f"      Error: {test_result['error']}")
        
        # Print chain validation steps
        chain_validation = results.get('chain_validation', [])
        if chain_validation:
            print(f"\n🔗 Chain Validation Steps:")
            for step in chain_validation:
                print(f"   {step}")
        
        # Print performance metrics
        performance = results.get('performance', {})
        if performance:
            print(f"\n⚡ Performance Metrics:")
            for metric, value in performance.items():
                print(f"   {metric}: {value}")
        
        # Print recommendation
        summary = results.get('summary', {})
        if summary.get('recommendation'):
            print(f"\n💡 Recommendation: {summary['recommendation']}")

def main():
    parser = argparse.ArgumentParser(description='Lemma End-to-End Verification Tester')
    parser.add_argument('--base-url', default='http://localhost:5000', 
                       help='Base URL of Lemma instance')
    parser.add_argument('--test-existing-user', metavar='USER_ID',
                       help='Test with existing user ID')
    parser.add_argument('--full-chain-test', action='store_true',
                       help='Run full chain test including Shield')
    parser.add_argument('--monitoring-only', action='store_true',
                       help='Run only monitoring endpoint test')
    
    args = parser.parse_args()
    
    tester = LemmaE2EVerificationTester(args.base_url)
    
    print(f"🚀 Lemma End-to-End Verification Tester")
    print(f"🌐 Target: {args.base_url}")
    print(f"⏰ Time: {datetime.now().isoformat()}")
    print("")
    
    success = True
    
    if args.monitoring_only:
        # Run monitoring test only
        success = tester.test_monitoring_endpoint()
    elif args.full_chain_test:
        # Run comprehensive testing
        print("🔄 Running comprehensive E2E testing...")
        success &= tester.test_credential_minting_and_verification(args.test_existing_user)
        print("\n" + "="*60 + "\n")
        success &= tester.test_shield_verification_chain()
        print("\n" + "="*60 + "\n")
        success &= tester.test_monitoring_endpoint()
    else:
        # Default: test credential minting and verification
        success = tester.test_credential_minting_and_verification(args.test_existing_user)
    
    print("\n" + "="*60)
    if success:
        print("🎉 ALL TESTS PASSED - Lemma verification chain is operational!")
        sys.exit(0)
    else:
        print("❌ TESTS FAILED - Issues detected in Lemma verification chain")
        sys.exit(1)

if __name__ == "__main__":
    main() 