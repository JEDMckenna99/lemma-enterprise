#!/usr/bin/env python3
"""
Test the admin dashboard on live Heroku deployment
"""

import requests
import time

def test_live_admin():
    """Test admin dashboard on live deployment"""
    base_url = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'
    
    print("🌐 Testing Admin Dashboard on Live Deployment")
    print("=" * 60)
    print(f"🔗 Base URL: {base_url}")
    print()
    
    try:
        print("1. Testing admin login page...")
        login_response = requests.get(f'{base_url}/admin/login', timeout=15)
        print(f"   ✅ Admin login page: {login_response.status_code}")
        
        if login_response.status_code == 200:
            print("   📄 Login page loaded successfully")
            # Check if it contains our new dashboard elements
            if 'admin_dashboard.html' in login_response.text or 'Admin Dashboard' in login_response.text:
                print("   🎯 New admin dashboard template detected!")
        
        print("\n2. Testing admin dashboard redirect...")
        admin_response = requests.get(f'{base_url}/admin', timeout=15, allow_redirects=False)
        print(f"   📍 Admin dashboard: {admin_response.status_code}")
        
        if admin_response.status_code == 302:
            print("   ✅ Proper redirect to login (expected behavior)")
        elif admin_response.status_code == 200:
            print("   ⚠️  Direct access allowed (check auth)")
        
        print("\n3. Testing dashboard data API...")
        try:
            # This should return 401/403 without auth, which is expected
            api_response = requests.get(f'{base_url}/admin/api/dashboard/data', timeout=15)
            print(f"   🔌 Dashboard API: {api_response.status_code}")
            if api_response.status_code in [401, 403]:
                print("   ✅ API properly protected (expected)")
            elif api_response.status_code == 404:
                print("   ⚠️  API not deployed yet - need to push latest changes")
        except Exception as api_error:
            print(f"   ⚠️  API test error: {api_error}")
        
        print("\n4. Checking for design system assets...")
        css_response = requests.get(f'{base_url}/static/css/stripe-design-system.css', timeout=15)
        print(f"   🎨 Design system CSS: {css_response.status_code}")
        
        print("\n" + "=" * 60)
        print("📊 LIVE DEPLOYMENT STATUS:")
        
        if login_response.status_code == 200:
            print("✅ Admin login page: WORKING")
        else:
            print("❌ Admin login page: ISSUE")
            
        if admin_response.status_code == 302:
            print("✅ Authentication: PROPERLY PROTECTED")
        else:
            print("⚠️  Authentication: CHECK REQUIRED")
            
        if css_response.status_code == 200:
            print("✅ Design system: ASSETS AVAILABLE")
        else:
            print("⚠️  Design system: CHECK ASSETS")
        
        print(f"\n🔗 ACCESS LIVE ADMIN:")
        print(f"   Login: {base_url}/admin/login")
        print(f"   Dashboard: {base_url}/admin")
        
        # Check if we need to deploy latest changes
        print("\n💡 NEXT STEPS:")
        if admin_response.status_code != 302:
            print("   1. Verify admin authentication is working")
        
        # Check if our new template is deployed
        print("   2. Deploy latest admin dashboard changes:")
        print("      git add .")
        print("      git commit -m 'Add comprehensive admin dashboard'")
        print("      git push heroku main")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to live deployment")
        print("   Check if Heroku app is running")
        return False
    except requests.exceptions.Timeout:
        print("⏱️  Request timeout - Heroku app may be sleeping")
        print("   Try again in a few seconds")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_live_admin() 