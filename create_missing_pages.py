#!/usr/bin/env python3
"""
Create Missing Pages for Full Enterprise Structure
Based on the site structure diagrams, implement all missing pages
"""

import os
import requests

# Pages that should exist based on diagrams
EXPECTED_PAGES = {
    # Core pages
    '/': 'index.html',
    '/verify': 'verify.html', 
    '/protected': 'protected.html',
    '/error': 'error.html',
    
    # Onboarding flow
    '/onboarding': 'onboarding/start.html',
    '/onboarding/register': 'onboarding/register.html',
    '/onboarding/verify': 'onboarding/verify.html', 
    '/onboarding/dashboard': 'onboarding/dashboard.html',
    '/onboarding/api-keys': 'onboarding/api_keys.html',
    '/onboarding/usage': 'onboarding/usage.html',
    '/onboarding/integration': 'onboarding/integration.html',
    
    # Admin section
    '/admin/login': 'admin_login.html',
    '/admin': 'admin.html',
    
    # Billing system
    '/billing/invoices': 'billing/invoices.html',
    '/billing/payment-methods': 'billing/payment_methods.html',
    '/billing/identity-complete': 'billing/identity_complete.html',
    
    # Demo & testing
    '/gate-demo': 'gate_demo.html',
    '/widget-test': 'widget_test.html',
    
    # API documentation
    '/api-docs': 'api_docs.html'
}

def test_live_pages():
    """Test which pages exist on live site"""
    base_url = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'
    
    working = []
    missing = []
    redirects = []
    errors = []
    
    print("🔍 Testing Live Site Structure")
    print("=" * 50)
    
    for route, template in EXPECTED_PAGES.items():
        try:
            r = requests.get(base_url + route, timeout=10, allow_redirects=False)
            if r.status_code == 200:
                print(f"✅ {route} - Working")
                working.append(route)
            elif r.status_code in [301, 302, 303, 307, 308]:
                print(f"🔄 {route} - Redirect ({r.status_code})")
                redirects.append(route)
            elif r.status_code == 404:
                print(f"❌ {route} - Not Found")
                missing.append(route)
            elif r.status_code == 500:
                print(f"💥 {route} - Server Error")
                errors.append(route)
            else:
                print(f"⚠️  {route} - Status {r.status_code}")
                missing.append(route)
        except Exception as e:
            print(f"❌ {route} - Error: {str(e)[:30]}")
            missing.append(route)
    
    print(f"\n📊 SUMMARY")
    print(f"Working: {len(working)}/{len(EXPECTED_PAGES)}")
    print(f"Redirects: {len(redirects)}")
    print(f"Missing: {len(missing)}")
    print(f"Errors: {len(errors)}")
    
    return working, missing, redirects, errors

def check_templates():
    """Check which templates exist"""
    templates_dir = 'templates'
    existing_templates = []
    missing_templates = []
    
    print("\n🗂️  Template File Check")
    print("=" * 30)
    
    for route, template in EXPECTED_PAGES.items():
        template_path = os.path.join(templates_dir, template)
        if os.path.exists(template_path):
            print(f"✅ {template}")
            existing_templates.append(template)
        else:
            print(f"❌ {template}")
            missing_templates.append(template)
    
    print(f"\nTemplate Summary: {len(existing_templates)}/{len(EXPECTED_PAGES)}")
    return existing_templates, missing_templates

def check_routes():
    """Check which routes are defined"""
    print("\n🛣️  Route Definition Check")
    print("=" * 30)
    
    # This would require parsing the route files
    # For now, just list what we know from the test
    print("Need to check route definitions in:")
    print("- lemma/routes/main.py")
    print("- lemma/routes/admin.py") 
    print("- lemma/routes/onboarding.py")
    print("- lemma/routes/billing.py")

if __name__ == "__main__":
    print("🏗️  LEMMA ENTERPRISE - MISSING PAGES ANALYSIS")
    print("=" * 60)
    
    # Test live site
    working, missing, redirects, errors = test_live_pages()
    
    # Check templates
    existing_templates, missing_templates = check_templates()
    
    # Check routes
    check_routes()
    
    print(f"\n🎯 IMPLEMENTATION NEEDED")
    print("=" * 30)
    print("Missing pages that need implementation:")
    for page in missing + errors:
        template = EXPECTED_PAGES.get(page, 'unknown')
        print(f"  {page} → {template}") 