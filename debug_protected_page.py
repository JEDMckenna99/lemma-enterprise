#!/usr/bin/env python3
"""
Debug script to check exactly what's in the live protected page
"""

import requests
import re

def debug_protected_page():
    """Debug the live protected page to understand what's missing"""
    
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    print("🔍 Debugging Protected Page Content")
    print("=" * 60)
    
    try:
        response = requests.get(f"{base_url}/protected", timeout=30, allow_redirects=True)
        
        if response.status_code == 200:
            content = response.text
            print(f"✅ Page loaded successfully - Status: {response.status_code}")
            print(f"📄 Content length: {len(content)} characters")
            print()
            
            # Check for each missing element
            print("🔍 DETAILED ELEMENT ANALYSIS:")
            print("-" * 40)
            
            # 1. Check for "Enhanced 2025 SaaS Styles" comment
            saas_styles_match = re.search(r'/\*\s*Enhanced 2025 SaaS Styles\s*\*/', content)
            print(f"1. Enhanced 2025 SaaS Styles comment: {'✅ FOUND' if saas_styles_match else '❌ MISSING'}")
            if saas_styles_match:
                print(f"   Location: Character {saas_styles_match.start()}-{saas_styles_match.end()}")
            
            # 2. Check for lemma-verification-status class definition
            verification_status_css = re.search(r'\.lemma-verification-status\s*{', content)
            print(f"2. .lemma-verification-status CSS: {'✅ FOUND' if verification_status_css else '❌ MISSING'}")
            if verification_status_css:
                print(f"   Location: Character {verification_status_css.start()}-{verification_status_css.end()}")
            
            # 3. Check for credential-management-enhanced class definition
            enhanced_mgmt_css = re.search(r'\.credential-management-enhanced\s*{', content)
            print(f"3. .credential-management-enhanced CSS: {'✅ FOUND' if enhanced_mgmt_css else '❌ MISSING'}")
            if enhanced_mgmt_css:
                print(f"   Location: Character {enhanced_mgmt_css.start()}-{enhanced_mgmt_css.end()}")
            
            # 4. Check for HTML elements using these classes
            verification_status_html = re.search(r'class="[^"]*lemma-verification-status[^"]*"', content)
            print(f"4. lemma-verification-status HTML: {'✅ FOUND' if verification_status_html else '❌ MISSING'}")
            if verification_status_html:
                print(f"   Match: {verification_status_html.group()}")
            
            enhanced_mgmt_html = re.search(r'class="[^"]*credential-management-enhanced[^"]*"', content)
            print(f"5. credential-management-enhanced HTML: {'✅ FOUND' if enhanced_mgmt_html else '❌ MISSING'}")
            if enhanced_mgmt_html:
                print(f"   Match: {enhanced_mgmt_html.group()}")
            
            print()
            print("🔍 CONTENT SAMPLES:")
            print("-" * 40)
            
            # Show relevant sections
            if saas_styles_match:
                start = max(0, saas_styles_match.start() - 50)
                end = min(len(content), saas_styles_match.end() + 200)
                print(f"CSS Styles Section:\n{content[start:end]}")
                print()
            
            # Check for script inclusion
            script_match = re.search(r'lemma-verification-flow\.js', content)
            print(f"6. Verification Flow Script: {'✅ FOUND' if script_match else '❌ MISSING'}")
            
            print()
            print("🧐 POSSIBLE ISSUES:")
            print("-" * 40)
            
            issues = []
            if not saas_styles_match:
                issues.append("- 'Enhanced 2025 SaaS Styles' comment missing from CSS")
            if not verification_status_css:
                issues.append("- '.lemma-verification-status' CSS class definition missing")
            if not enhanced_mgmt_css:
                issues.append("- '.credential-management-enhanced' CSS class definition missing")
            if not verification_status_html:
                issues.append("- HTML element with 'lemma-verification-status' class missing")
            if not enhanced_mgmt_html:
                issues.append("- HTML element with 'credential-management-enhanced' class missing")
            
            if issues:
                for issue in issues:
                    print(issue)
            else:
                print("🎉 All elements found! Test should pass.")
                
            print()
            print("📋 DEPLOYMENT RECOMMENDATION:")
            if issues:
                print("❌ The protected.html template needs to be redeployed with the missing elements.")
                print("   Recommended action: Force redeploy with git push heroku main --force")
            else:
                print("✅ All elements are present. The test failure might be due to:")
                print("   - Case sensitivity in the search")
                print("   - Whitespace differences") 
                print("   - Caching issues")
                print("   - Test script needs to be updated")
                
        else:
            print(f"❌ Failed to load protected page - Status: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error accessing protected page: {str(e)}")

if __name__ == "__main__":
    debug_protected_page() 