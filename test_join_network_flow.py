#!/usr/bin/env python3
"""
Comprehensive Join Network Flow Test
Tests the actual user experience of going to /join_network and triggering the shield
"""

import requests
import time
import json
from urllib.parse import urljoin, urlparse
import re

class JoinNetworkFlowTester:
    def __init__(self, base_url="https://lemma-enterprise-0f6ba17076c1.herokuapp.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def test_complete_flow(self):
        """Test the complete join network flow"""
        print("🧪 COMPREHENSIVE JOIN NETWORK FLOW TEST")
        print("=" * 60)
        
        results = {
            'step1_page_load': None,
            'step2_shield_scripts': None,
            'step3_api_health': None,
            'step4_shield_status': None,
            'step5_revocation_test': None,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Step 1: Load the join network page
            print("\n📄 STEP 1: Loading /join_network page...")
            results['step1_page_load'] = self.test_page_load()
            
            # Step 2: Check shield script loading
            print("\n🛡️ STEP 2: Checking shield script availability...")
            results['step2_shield_scripts'] = self.test_shield_scripts()
            
            # Step 3: Test API health
            print("\n⚡ STEP 3: Testing API endpoints...")
            results['step3_api_health'] = self.test_api_health()
            
            # Step 4: Test shield status endpoint
            print("\n🔍 STEP 4: Testing shield status...")
            results['step4_shield_status'] = self.test_shield_status()
            
            # Step 5: Test revocation flow
            print("\n🚨 STEP 5: Testing revocation trigger...")
            results['step5_revocation_test'] = self.test_revocation_flow()
            
        except Exception as e:
            results['errors'].append(f"Flow test failed: {str(e)}")
            
        # Generate comprehensive report
        self.generate_report(results)
        return results
    
    def test_page_load(self):
        """Test loading the join network page"""
        try:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/join_network")
            load_time = (time.time() - start_time) * 1000
            
            result = {
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'load_time_ms': round(load_time, 2),
                'content_length': len(response.content),
                'has_shield_widget_script': False,
                'has_shield_container': False,
                'has_debug_buttons': False,
                'shield_initialization_code': False
            }
            
            if response.status_code == 200:
                content = response.text
                
                # Check for shield widget script
                if 'lemma-shield-widget.js' in content:
                    result['has_shield_widget_script'] = True
                    print("  ✅ Shield widget script found")
                else:
                    print("  ❌ Shield widget script NOT found")
                
                # Check for shield container
                if 'lemma-shield-widget' in content or 'shield-container' in content:
                    result['has_shield_container'] = True
                    print("  ✅ Shield container found")
                else:
                    print("  ❌ Shield container NOT found")
                
                # Check for debug buttons
                if 'testShieldInit' in content and 'forceShieldShow' in content:
                    result['has_debug_buttons'] = True
                    print("  ✅ Debug buttons found")
                else:
                    print("  ❌ Debug buttons NOT found")
                
                # Check for shield initialization
                if 'initializeLemmaShield' in content and 'LemmaShieldWidget' in content:
                    result['shield_initialization_code'] = True
                    print("  ✅ Shield initialization code found")
                else:
                    print("  ❌ Shield initialization code NOT found")
                
                print(f"  📊 Page loaded in {load_time:.2f}ms ({len(response.content)} bytes)")
            else:
                print(f"  ❌ Page load failed: {response.status_code}")
                
            return result
            
        except Exception as e:
            print(f"  ❌ Page load error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def test_shield_scripts(self):
        """Test shield script availability"""
        scripts_to_test = [
            '/static/js/lemma-shield-widget.js',
            '/static/js/lemma-wallet-background.js',
            '/static/js/lemma-shield-flow-orchestrator.js'
        ]
        
        results = {}
        
        for script_path in scripts_to_test:
            try:
                start_time = time.time()
                response = self.session.get(f"{self.base_url}{script_path}")
                load_time = (time.time() - start_time) * 1000
                
                result = {
                    'success': response.status_code == 200,
                    'status_code': response.status_code,
                    'load_time_ms': round(load_time, 2),
                    'size_bytes': len(response.content)
                }
                
                if response.status_code == 200:
                    print(f"  ✅ {script_path}: {len(response.content)} bytes in {load_time:.2f}ms")
                    
                    # Check for key functions in the script
                    content = response.text
                    if 'LemmaShieldWidget' in content:
                        result['has_shield_widget_class'] = True
                    if 'forceShow' in content:
                        result['has_force_show'] = True
                    if 'showVerificationWidget' in content:
                        result['has_show_verification'] = True
                        
                else:
                    print(f"  ❌ {script_path}: HTTP {response.status_code}")
                    
                results[script_path] = result
                
            except Exception as e:
                print(f"  ❌ {script_path}: Error - {str(e)}")
                results[script_path] = {'success': False, 'error': str(e)}
        
        return results
    
    def test_api_health(self):
        """Test API endpoint health"""
        endpoints_to_test = [
            '/api/health',
            '/api/shield/status',
            '/api/generate-challenge'
        ]
        
        results = {}
        
        for endpoint in endpoints_to_test:
            try:
                start_time = time.time()
                response = self.session.get(f"{self.base_url}{endpoint}")
                response_time = (time.time() - start_time) * 1000
                
                result = {
                    'success': response.status_code == 200,
                    'status_code': response.status_code,
                    'response_time_ms': round(response_time, 2)
                }
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        result['response_data'] = data
                        print(f"  ✅ {endpoint}: {response.status_code} in {response_time:.2f}ms")
                        
                        # Log key information
                        if endpoint == '/api/health' and 'service' in data:
                            print(f"    📊 Service: {data.get('service', 'unknown')}")
                        elif endpoint == '/api/shield/status' and 'shield_action' in data:
                            print(f"    🛡️ Shield Action: {data.get('shield_action', 'unknown')}")
                            
                    except json.JSONDecodeError:
                        result['response_text'] = response.text[:200]
                        print(f"  ⚠️ {endpoint}: Non-JSON response")
                else:
                    print(f"  ❌ {endpoint}: HTTP {response.status_code}")
                    
                results[endpoint] = result
                
            except Exception as e:
                print(f"  ❌ {endpoint}: Error - {str(e)}")
                results[endpoint] = {'success': False, 'error': str(e)}
        
        return results
    
    def test_shield_status(self):
        """Test shield status specifically"""
        try:
            print("  🔍 Testing shield status endpoint...")
            
            # Test with different parameters
            test_cases = [
                {'url': '/api/shield/status', 'description': 'Basic status'},
                {'url': '/api/shield/status?force_check=true', 'description': 'Force check'},
                {'url': '/api/shield/status?detailed=true', 'description': 'Detailed status'}
            ]
            
            results = {}
            
            for case in test_cases:
                try:
                    start_time = time.time()
                    response = self.session.get(f"{self.base_url}{case['url']}")
                    response_time = (time.time() - start_time) * 1000
                    
                    result = {
                        'success': response.status_code == 200,
                        'status_code': response.status_code,
                        'response_time_ms': round(response_time, 2)
                    }
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            result['data'] = data
                            
                            print(f"    ✅ {case['description']}: {response_time:.2f}ms")
                            
                            # Check key shield status fields
                            if 'shield_action' in data:
                                print(f"      🛡️ Shield Action: {data['shield_action']}")
                            if 'requires_verification' in data:
                                print(f"      ✋ Requires Verification: {data['requires_verification']}")
                            if 'response_time_ms' in data:
                                print(f"      ⚡ Server Time: {data['response_time_ms']:.2f}ms")
                                
                        except json.JSONDecodeError:
                            result['response_text'] = response.text
                            print(f"    ⚠️ {case['description']}: Non-JSON response")
                    else:
                        print(f"    ❌ {case['description']}: HTTP {response.status_code}")
                        
                    results[case['description']] = result
                    
                except Exception as e:
                    print(f"    ❌ {case['description']}: Error - {str(e)}")
                    results[case['description']] = {'success': False, 'error': str(e)}
            
            return results
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def test_revocation_flow(self):
        """Test the revocation flow that should trigger shield"""
        try:
            print("  🚨 Testing revocation trigger...")
            
            # First, try to revoke a test credential
            revoke_data = {
                'credential_id': 'test_credential_12345',
                'reason': 'flow_test',
                'test_mode': True
            }
            
            start_time = time.time()
            response = self.session.post(
                f"{self.base_url}/api/shield/revoke-credential",
                json=revoke_data,
                headers={'Content-Type': 'application/json'}
            )
            response_time = (time.time() - start_time) * 1000
            
            result = {
                'revoke_success': response.status_code == 200,
                'revoke_status_code': response.status_code,
                'revoke_response_time_ms': round(response_time, 2)
            }
            
            if response.status_code == 200:
                try:
                    revoke_result = response.json()
                    result['revoke_data'] = revoke_result
                    print(f"    ✅ Revocation API: {response_time:.2f}ms")
                    
                    if 'success' in revoke_result:
                        print(f"      🎯 Success: {revoke_result['success']}")
                    if 'actions_completed' in revoke_result:
                        print(f"      📋 Actions: {len(revoke_result['actions_completed'])}")
                        
                except json.JSONDecodeError:
                    result['revoke_response_text'] = response.text
                    print("    ⚠️ Revocation: Non-JSON response")
            else:
                print(f"    ❌ Revocation API: HTTP {response.status_code}")
                
            # Test the status after revocation
            time.sleep(0.5)  # Brief delay
            
            status_response = self.session.get(f"{self.base_url}/api/shield/status")
            if status_response.status_code == 200:
                try:
                    status_data = status_response.json()
                    result['post_revoke_status'] = status_data
                    
                    if 'shield_action' in status_data:
                        print(f"      🛡️ Post-Revoke Shield Action: {status_data['shield_action']}")
                        
                        # Check if shield action is require_verification
                        if status_data['shield_action'] == 'require_verification':
                            print("      ✅ Shield should appear - revocation triggered correctly")
                            result['shield_should_appear'] = True
                        else:
                            print("      ⚠️ Shield action not set to require_verification")
                            result['shield_should_appear'] = False
                            
                except json.JSONDecodeError:
                    print("    ⚠️ Post-revoke status: Non-JSON response")
            
            return result
            
        except Exception as e:
            print(f"  ❌ Revocation test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def generate_report(self, results):
        """Generate comprehensive test report"""
        print("\n" + "=" * 60)
        print("🧪 COMPREHENSIVE FLOW TEST REPORT")
        print("=" * 60)
        
        # Summary
        total_tests = 0
        passed_tests = 0
        
        for step_name, step_result in results.items():
            if step_name in ['errors', 'warnings']:
                continue
                
            if isinstance(step_result, dict):
                if step_result.get('success'):
                    passed_tests += 1
                total_tests += 1
            elif isinstance(step_result, list):
                for sub_result in step_result:
                    if isinstance(sub_result, dict) and sub_result.get('success'):
                        passed_tests += 1
                    total_tests += 1
        
        print(f"\n📊 OVERALL RESULTS: {passed_tests}/{total_tests} tests passed")
        
        # Detailed breakdown
        print(f"\n📄 STEP 1 - PAGE LOAD:")
        step1 = results.get('step1_page_load', {})
        if step1.get('success'):
            print(f"  ✅ Page loads successfully ({step1.get('load_time_ms', 0):.2f}ms)")
            print(f"  📊 Content: {step1.get('content_length', 0)} bytes")
            print(f"  🛡️ Shield widget script: {'✅' if step1.get('has_shield_widget_script') else '❌'}")
            print(f"  📦 Shield container: {'✅' if step1.get('has_shield_container') else '❌'}")
            print(f"  🔧 Debug buttons: {'✅' if step1.get('has_debug_buttons') else '❌'}")
            print(f"  🎯 Initialization code: {'✅' if step1.get('shield_initialization_code') else '❌'}")
        else:
            print(f"  ❌ Page load failed: {step1.get('error', 'Unknown error')}")
        
        print(f"\n🛡️ STEP 2 - SHIELD SCRIPTS:")
        step2 = results.get('step2_shield_scripts', {})
        for script_path, script_result in step2.items():
            if script_result.get('success'):
                print(f"  ✅ {script_path}: {script_result.get('size_bytes', 0)} bytes")
            else:
                print(f"  ❌ {script_path}: {script_result.get('error', 'Failed to load')}")
        
        print(f"\n⚡ STEP 3 - API HEALTH:")
        step3 = results.get('step3_api_health', {})
        for endpoint, endpoint_result in step3.items():
            if endpoint_result.get('success'):
                print(f"  ✅ {endpoint}: {endpoint_result.get('response_time_ms', 0):.2f}ms")
            else:
                print(f"  ❌ {endpoint}: {endpoint_result.get('error', 'Failed')}")
        
        print(f"\n🔍 STEP 4 - SHIELD STATUS:")
        step4 = results.get('step4_shield_status', {})
        for test_name, test_result in step4.items():
            if test_result.get('success'):
                print(f"  ✅ {test_name}: {test_result.get('response_time_ms', 0):.2f}ms")
                if 'data' in test_result and 'shield_action' in test_result['data']:
                    print(f"    🛡️ Shield Action: {test_result['data']['shield_action']}")
            else:
                print(f"  ❌ {test_name}: {test_result.get('error', 'Failed')}")
        
        print(f"\n🚨 STEP 5 - REVOCATION TEST:")
        step5 = results.get('step5_revocation_test', {})
        if step5.get('revoke_success'):
            print(f"  ✅ Revocation API: {step5.get('revoke_response_time_ms', 0):.2f}ms")
            if step5.get('shield_should_appear'):
                print(f"  ✅ Shield trigger: Should appear after revocation")
            else:
                print(f"  ⚠️ Shield trigger: May not appear correctly")
        else:
            print(f"  ❌ Revocation test failed: {step5.get('error', 'Unknown error')}")
        
        # Issues found
        if results.get('errors'):
            print(f"\n❌ ERRORS FOUND:")
            for error in results['errors']:
                print(f"  • {error}")
        
        if results.get('warnings'):
            print(f"\n⚠️ WARNINGS:")
            for warning in results['warnings']:
                print(f"  • {warning}")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        
        if not step1.get('has_shield_widget_script'):
            print("  • Shield widget script not found - check script loading")
        
        if not step1.get('has_shield_container'):
            print("  • Shield container not found - check HTML structure")
        
        if not step1.get('shield_initialization_code'):
            print("  • Shield initialization code missing - check JavaScript")
        
        # Check if all API endpoints are working
        api_issues = []
        for endpoint, result in step3.items():
            if not result.get('success'):
                api_issues.append(endpoint)
        
        if api_issues:
            print(f"  • API endpoints not working: {', '.join(api_issues)}")
        
        # Shield status issues
        shield_status_working = False
        for test_name, test_result in step4.items():
            if test_result.get('success') and test_result.get('data', {}).get('shield_action'):
                shield_status_working = True
                break
        
        if not shield_status_working:
            print("  • Shield status endpoint not returning proper data")
        
        print("\n" + "=" * 60)
        
        return results

if __name__ == "__main__":
    tester = JoinNetworkFlowTester()
    results = tester.test_complete_flow()
    
    # Save results to file for further analysis
    with open('join_network_flow_test_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to: join_network_flow_test_results.json") 