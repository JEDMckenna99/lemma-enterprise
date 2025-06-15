#!/usr/bin/env python3
"""
Test script for live deployment verification of 2025 SaaS features
"""

import requests
import json
import time

LIVE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def test_live_deployment():
    print("🧪 Testing Live Deployment: 2025 SaaS Verification Flow")
    print("=" * 60)
    
    results = {}
    
    # Test 1: Health Check
    print("\n1. 🏥 Health Check")
    try:
        r = requests.get(f"{LIVE_URL}/api/health", timeout=10)
        results['health'] = r.status_code == 200
        print(f"   ✅ Status: {r.status_code}")
        print(f"   ✅ Response: {r.json()}")
    except Exception as e:
        results['health'] = False
        print(f"   ❌ Error: {e}")
    
    # Test 2: Protected Page with 2025 SaaS Scripts
    print("\n2. 🔒 Protected Page with Verification Flow")
    try:
        r = requests.get(f"{LIVE_URL}/protected", timeout=10)
        results['protected_page'] = r.status_code == 200
        
        # Check for 2025 SaaS features
        verification_flow_script = 'lemma-verification-flow.js' in r.text
        enhanced_styles = 'lemma-verification-status' in r.text
        modal_functionality = 'clearCredentialEnhanced' in r.text
        
        results['verification_flow_script'] = verification_flow_script
        results['enhanced_styles'] = enhanced_styles
        results['modal_functionality'] = modal_functionality
        
        print(f"   ✅ Page Status: {r.status_code}")
        print(f"   ✅ Verification Flow Script: {verification_flow_script}")
        print(f"   ✅ Enhanced 2025 Styles: {enhanced_styles}")
        print(f"   ✅ Modal Functionality: {modal_functionality}")
    except Exception as e:
        results['protected_page'] = False
        print(f"   ❌ Error: {e}")
    
    # Test 3: Static Files (Verification Flow Script)
    print("\n3. 📜 Verification Flow Script Availability")
    try:
        r = requests.get(f"{LIVE_URL}/static/js/lemma-verification-flow.js", timeout=10)
        results['verification_script'] = r.status_code == 200
        
        # Check for key 2025 features in the script
        indexeddb_support = 'IndexedDB' in r.text
        session_mirroring = 'sessionStorage' in r.text
        modal_implementation = 'showClearCredentialModal' in r.text
        
        results['indexeddb_support'] = indexeddb_support
        results['session_mirroring'] = session_mirroring
        results['modal_implementation'] = modal_implementation
        
        print(f"   ✅ Script Status: {r.status_code}")
        print(f"   ✅ IndexedDB Support: {indexeddb_support}")
        print(f"   ✅ Session Mirroring: {session_mirroring}")
        print(f"   ✅ Modal Implementation: {modal_implementation}")
        print(f"   ✅ Script Size: {len(r.text)} bytes")
    except Exception as e:
        results['verification_script'] = False
        print(f"   ❌ Error: {e}")
    
    # Test 4: SRE Endpoints (from v2.7.0)
    print("\n4. 📊 SRE Observability Endpoints")
    sre_endpoints = [
        '/api/sre/dashboard/metrics',
        '/api/sre/metrics/latency',
        '/api/sre/metrics/errors'
    ]
    
    sre_results = {}
    for endpoint in sre_endpoints:
        try:
            r = requests.get(f"{LIVE_URL}{endpoint}", timeout=5)
            sre_results[endpoint] = r.status_code == 200
            print(f"   ✅ {endpoint}: {r.status_code}")
        except Exception as e:
            sre_results[endpoint] = False
            print(f"   ❌ {endpoint}: Error - {str(e)[:50]}...")
    
    results['sre_endpoints'] = sre_results
    
    # Test 5: Billing System (from v2.6.0)
    print("\n5. 💰 Billing System Endpoints")
    try:
        r = requests.get(f"{LIVE_URL}/api/billing/health", timeout=10)
        results['billing_health'] = r.status_code == 200
        print(f"   ✅ Billing Health: {r.status_code}")
        if r.status_code == 200:
            billing_data = r.json()
            print(f"   ✅ Components: {list(billing_data.get('components', {}).keys())}")
    except Exception as e:
        results['billing_health'] = False
        print(f"   ❌ Billing Health Error: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("🎯 LIVE DEPLOYMENT TEST SUMMARY")
    print("=" * 60)
    
    # Task 1: End-User Verification Flow Components
    task1_components = [
        ('IndexedDB Support', results.get('indexeddb_support', False)),
        ('Session Storage Mirroring', results.get('session_mirroring', False)),
        ('Enhanced Clear Modal', results.get('modal_implementation', False)),
        ('Verification Flow Script', results.get('verification_script', False)),
        ('Enhanced UI Styles', results.get('enhanced_styles', False))
    ]
    
    print("\n✅ Task 1: End-User Verification Flow (2025 SaaS)")
    task1_passed = 0
    for name, status in task1_components:
        status_icon = "✅" if status else "❌"
        print(f"   {status_icon} {name}")
        if status:
            task1_passed += 1
    
    print(f"\n📊 Task 1 Completion: {task1_passed}/{len(task1_components)} ({task1_passed/len(task1_components)*100:.1f}%)")
    
    # Overall System Health
    core_systems = [
        ('Core API Health', results.get('health', False)),
        ('Protected Page', results.get('protected_page', False)),
        ('Billing System', results.get('billing_health', False))
    ]
    
    print(f"\n🏥 Core System Health:")
    for name, status in core_systems:
        status_icon = "✅" if status else "❌"
        print(f"   {status_icon} {name}")
    
    # SRE Observability Status
    sre_working = sum(1 for status in results.get('sre_endpoints', {}).values() if status)
    sre_total = len(results.get('sre_endpoints', {}))
    if sre_total > 0:
        print(f"\n📊 SRE Observability: {sre_working}/{sre_total} endpoints working")
    
    return results

if __name__ == "__main__":
    results = test_live_deployment()
    
    # Save results
    with open('live_deployment_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: live_deployment_test_results.json") 