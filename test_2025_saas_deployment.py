#!/usr/bin/env python3
"""
Test script to verify 2025 SaaS Verification Flow deployment
Tests the live production environment for Task 1 completion
"""

import requests
import json
import sys
from datetime import datetime

def test_2025_saas_deployment():
    """Test the deployed 2025 SaaS verification flow features"""
    
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    print("🚀 Testing 2025 SaaS Verification Flow Deployment")
    print("=" * 60)
    print(f"Base URL: {base_url}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print()
    
    results = {
        "deployment_status": "UNKNOWN",
        "tests": [],
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "success_rate": 0
        }
    }
    
    # Test 1: Health Check - Basic Deployment Verification
    try:
        print("📊 Test 1: Health Check - Basic Deployment")
        response = requests.get(f"{base_url}/api/health", timeout=30)
        
        test_result = {
            "name": "Health Check",
            "status": "PASS" if response.status_code == 200 else "FAIL",
            "details": f"Status: {response.status_code}, Response length: {len(response.text)}"
        }
        
        if response.status_code == 200:
            print(f"   ✅ Health check passed - Status: {response.status_code}")
        else:
            print(f"   ❌ Health check failed - Status: {response.status_code}")
            
        results["tests"].append(test_result)
        
    except Exception as e:
        print(f"   ❌ Health check error: {str(e)}")
        results["tests"].append({
            "name": "Health Check",
            "status": "ERROR",
            "details": f"Exception: {str(e)}"
        })
    
    print()
    
    # Test 2: Protected Page - Template Deployment
    try:
        print("🔒 Test 2: Protected Page - Enhanced Template Deployment")
        response = requests.get(f"{base_url}/protected", timeout=30, allow_redirects=True)
        
        # Check for key 2025 SaaS features in the response
        content = response.text
        features_found = {
            "verification_flow_script": "lemma-verification-flow.js" in content,
            "verification_status_indicator": "lemma-verification-status" in content,
            "credential_sync_indicator": "credential-sync-indicator" in content,
            "enhanced_management": "credential-management-enhanced" in content,
            "modern_saas_styles": "Enhanced 2025 SaaS Styles" in content
        }
        
        all_features_present = all(features_found.values())
        
        test_result = {
            "name": "Protected Page Template",
            "status": "PASS" if response.status_code == 200 and all_features_present else "FAIL",
            "details": f"Status: {response.status_code}, Features: {features_found}"
        }
        
        if response.status_code == 200:
            print(f"   ✅ Protected page accessible - Status: {response.status_code}")
            for feature, present in features_found.items():
                status = "✅" if present else "❌"
                print(f"      {status} {feature.replace('_', ' ').title()}: {'Present' if present else 'Missing'}")
        else:
            print(f"   ❌ Protected page failed - Status: {response.status_code}")
            
        results["tests"].append(test_result)
        
    except Exception as e:
        print(f"   ❌ Protected page error: {str(e)}")
        results["tests"].append({
            "name": "Protected Page Template",
            "status": "ERROR",
            "details": f"Exception: {str(e)}"
        })
    
    print()
    
    # Test 3: Verification Flow Script - Static Asset Deployment
    try:
        print("📜 Test 3: Verification Flow Script - Static Asset")
        response = requests.get(f"{base_url}/static/js/lemma-verification-flow.js", timeout=30)
        
        # Check for key script features
        if response.status_code == 200:
            script_content = response.text
            script_features = {
                "class_definition": "class LemmaVerificationFlow" in script_content,
                "version_2025": "2025.1.0" in script_content,
                "indexeddb_init": "initIndexedDB" in script_content,
                "session_mirroring": "initSessionStorageMirroring" in script_content,
                "credential_integrity": "verifyCredentialIntegrity" in script_content,
                "clear_modal": "showClearCredentialModal" in script_content
            }
            
            all_script_features = all(script_features.values())
            
            test_result = {
                "name": "Verification Flow Script",
                "status": "PASS" if all_script_features else "PARTIAL",
                "details": f"Status: {response.status_code}, Size: {len(script_content)} bytes, Features: {script_features}"
            }
            
            print(f"   ✅ Script accessible - Status: {response.status_code}, Size: {len(script_content)} bytes")
            for feature, present in script_features.items():
                status = "✅" if present else "❌"
                print(f"      {status} {feature.replace('_', ' ').title()}: {'Present' if present else 'Missing'}")
                
        else:
            test_result = {
                "name": "Verification Flow Script",
                "status": "FAIL",
                "details": f"Status: {response.status_code}"
            }
            print(f"   ❌ Script not accessible - Status: {response.status_code}")
            
        results["tests"].append(test_result)
        
    except Exception as e:
        print(f"   ❌ Script access error: {str(e)}")
        results["tests"].append({
            "name": "Verification Flow Script",
            "status": "ERROR",
            "details": f"Exception: {str(e)}"
        })
    
    print()
    
    # Test 4: Layout Template - Modern SaaS Design System
    try:
        print("🎨 Test 4: Layout Template - Modern SaaS Design System")
        response = requests.get(f"{base_url}/", timeout=30)  # Home page uses layout.html
        
        if response.status_code == 200:
            content = response.text
            design_features = {
                "modern_css_variables": "--font-system" in content,
                "saas_color_palette": "--primary-500: #4B3BA3" in content,
                "design_tokens": "--space-" in content and "--radius-" in content,
                "typography_scale": "--font-size-" in content,
                "modern_transitions": "cubic-bezier" in content
            }
            
            all_design_features = all(design_features.values())
            
            test_result = {
                "name": "Layout Design System",
                "status": "PASS" if all_design_features else "PARTIAL",
                "details": f"Status: {response.status_code}, Features: {design_features}"
            }
            
            print(f"   ✅ Layout accessible - Status: {response.status_code}")
            for feature, present in design_features.items():
                status = "✅" if present else "❌"
                print(f"      {status} {feature.replace('_', ' ').title()}: {'Present' if present else 'Missing'}")
                
        else:
            test_result = {
                "name": "Layout Design System",
                "status": "FAIL",
                "details": f"Status: {response.status_code}"
            }
            print(f"   ❌ Layout not accessible - Status: {response.status_code}")
            
        results["tests"].append(test_result)
        
    except Exception as e:
        print(f"   ❌ Layout access error: {str(e)}")
        results["tests"].append({
            "name": "Layout Design System",
            "status": "ERROR",
            "details": f"Exception: {str(e)}"
        })
    
    # Calculate summary
    results["summary"]["total_tests"] = len(results["tests"])
    results["summary"]["passed"] = len([t for t in results["tests"] if t["status"] == "PASS"])
    results["summary"]["failed"] = len([t for t in results["tests"] if t["status"] in ["FAIL", "ERROR"]])
    results["summary"]["success_rate"] = (results["summary"]["passed"] / results["summary"]["total_tests"]) * 100 if results["summary"]["total_tests"] > 0 else 0
    
    # Determine overall deployment status
    if results["summary"]["success_rate"] >= 100:
        results["deployment_status"] = "COMPLETE"
    elif results["summary"]["success_rate"] >= 75:
        results["deployment_status"] = "MOSTLY_COMPLETE"
    elif results["summary"]["success_rate"] >= 50:
        results["deployment_status"] = "PARTIAL"
    else:
        results["deployment_status"] = "FAILED"
    
    print()
    print("📊 DEPLOYMENT TEST SUMMARY")
    print("=" * 60)
    print(f"🎯 Overall Status: {results['deployment_status']}")
    print(f"✅ Tests Passed: {results['summary']['passed']}/{results['summary']['total_tests']}")
    print(f"❌ Tests Failed: {results['summary']['failed']}/{results['summary']['total_tests']}")
    print(f"📈 Success Rate: {results['summary']['success_rate']:.1f}%")
    
    if results["deployment_status"] == "COMPLETE":
        print("\n🎉 2025 SaaS VERIFICATION FLOW - DEPLOYMENT COMPLETE!")
        print("   All Task 1 features successfully deployed and operational")
    elif results["deployment_status"] == "MOSTLY_COMPLETE":
        print("\n⚠️  2025 SaaS VERIFICATION FLOW - MOSTLY COMPLETE")
        print("   Core features deployed, some minor issues detected")
    else:
        print(f"\n❌ 2025 SaaS VERIFICATION FLOW - {results['deployment_status']}")
        print("   Deployment issues detected, review required")
    
    # Save results
    with open('2025_saas_deployment_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: 2025_saas_deployment_test_results.json")
    
    return results

if __name__ == "__main__":
    try:
        results = test_2025_saas_deployment()
        
        # Exit with appropriate code
        if results["deployment_status"] == "COMPLETE":
            sys.exit(0)
        elif results["deployment_status"] == "MOSTLY_COMPLETE":
            sys.exit(1)
        else:
            sys.exit(2)
            
    except Exception as e:
        print(f"❌ Test execution failed: {str(e)}")
        sys.exit(3) 