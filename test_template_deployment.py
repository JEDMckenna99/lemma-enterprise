#!/usr/bin/env python3
"""
Test to verify that template changes are actually being deployed
"""

import requests
import re

def test_template_deployment():
    """Test if the template is actually being updated"""
    
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    print("🔍 Testing Template Deployment")
    print("=" * 50)
    
    try:
        response = requests.get(f"{base_url}/protected", timeout=30)
        
        if response.status_code == 200:
            content = response.text
            
            # Check for our debug marker
            debug_marker = "2025 SaaS Deployment Debug: Template Updated"
            has_debug_marker = debug_marker in content
            
            # Check for cache_bust variable
            cache_bust_found = content.count('cache_bust')
            
            # Check for our CSS styles
            enhanced_styles = "Enhanced 2025 SaaS Styles" in content
            verification_status_css = ".lemma-verification-status" in content
            enhanced_management_css = ".credential-management-enhanced" in content
            
            print(f"✅ Protected page loaded - Status: {response.status_code}")
            print(f"📄 Content length: {len(content)} characters")
            print()
            print("🔍 TEMPLATE UPDATE VERIFICATION:")
            print(f"   Debug Marker Present: {'✅ YES' if has_debug_marker else '❌ NO'}")
            print(f"   Cache Bust Variables: {cache_bust_found} found")
            print(f"   Enhanced 2025 SaaS Styles: {'✅ YES' if enhanced_styles else '❌ NO'}")
            print(f"   Verification Status CSS: {'✅ YES' if verification_status_css else '❌ NO'}")
            print(f"   Enhanced Management CSS: {'✅ YES' if enhanced_management_css else '❌ NO'}")
            print()
            
            if has_debug_marker:
                print("🎉 SUCCESS: Template is being updated properly!")
                print("   The template changes are reaching the live server.")
            else:
                print("❌ PROBLEM: Template is NOT being updated!")
                print("   Possible causes:")
                print("   1. Template file not included in deployment")
                print("   2. Flask template folder configuration issue")
                print("   3. Heroku build process not copying templates")
                print("   4. Template caching at Heroku level")
                
                # Check what content we actually get
                print("\n📋 ACTUAL CONTENT SAMPLE (first 500 chars):")
                print(content[:500])
                print()
                
                # Look for any template markers
                if "<!-- " in content:
                    comments = re.findall(r'<!--.*?-->', content)
                    print("📝 HTML Comments found in template:")
                    for comment in comments[:5]:  # Show first 5 comments
                        print(f"   {comment}")
                
        else:
            print(f"❌ Failed to load protected page - Status: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing template deployment: {str(e)}")

if __name__ == "__main__":
    test_template_deployment() 