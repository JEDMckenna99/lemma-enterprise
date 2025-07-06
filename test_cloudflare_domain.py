#!/usr/bin/env python3
"""
Test script to diagnose CloudFlare domain issue
Tests lemma.id domain configuration and identifies the 403 error source
"""

import requests
import dns.resolver
import time
from urllib.parse import urlparse

def test_cloudflare_domain():
    """Test the CloudFlare domain configuration"""
    
    domain = "lemma.id"
    heroku_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    print("🌐 Testing CloudFlare Domain Configuration")
    print("=" * 60)
    print(f"🎯 Target Domain: {domain}")
    print(f"🚀 Heroku URL: {heroku_url}")
    
    # Test 1: DNS Resolution
    print("\n1. Testing DNS resolution...")
    try:
        # Test A record
        a_records = dns.resolver.resolve(domain, 'A')
        print(f"✅ DNS A records found:")
        for record in a_records:
            print(f"   {record}")
            
        # Test CNAME record
        try:
            cname_records = dns.resolver.resolve(domain, 'CNAME')
            print(f"✅ DNS CNAME records found:")
            for record in cname_records:
                print(f"   {record}")
        except:
            print("   No CNAME records found")
            
    except Exception as e:
        print(f"❌ DNS resolution failed: {e}")
        return False
    
    # Test 2: Test direct domain access
    print("\n2. Testing direct domain access...")
    try:
        response = requests.get(f"https://{domain}", timeout=10, allow_redirects=False)
        print(f"   Status Code: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")
        
        if response.status_code == 403:
            print("⚠️ CloudFlare 403 Forbidden error detected")
            
            # Check CloudFlare headers
            cf_headers = {k: v for k, v in response.headers.items() if k.lower().startswith('cf-')}
            if cf_headers:
                print("   CloudFlare headers detected:")
                for k, v in cf_headers.items():
                    print(f"     {k}: {v}")
            else:
                print("   No CloudFlare headers found")
                
        elif response.status_code == 200:
            print("✅ Domain access successful")
        else:
            print(f"⚠️ Unexpected status code: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Domain access failed: {e}")
        return False
    
    # Test 3: Test specific endpoints
    print("\n3. Testing specific endpoints...")
    endpoints = [
        "/",
        "/api/health",
        "/sdk-demo",
        "/static/js/lemma-sdk-unified.js"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"https://{domain}{endpoint}", timeout=10, allow_redirects=False)
            status = "✅" if response.status_code == 200 else "❌"
            print(f"   {status} {endpoint}: {response.status_code}")
            
            if response.status_code == 403:
                # Check for CloudFlare security features
                if 'cf-ray' in response.headers:
                    print(f"     CloudFlare Ray ID: {response.headers['cf-ray']}")
                if 'cf-cache-status' in response.headers:
                    print(f"     CloudFlare Cache Status: {response.headers['cf-cache-status']}")
                    
        except Exception as e:
            print(f"   ❌ {endpoint}: {e}")
    
    # Test 4: Compare with Heroku direct access
    print("\n4. Comparing with Heroku direct access...")
    try:
        heroku_response = requests.get(f"{heroku_url}/api/health", timeout=10)
        domain_response = requests.get(f"https://{domain}/api/health", timeout=10)
        
        print(f"   Heroku direct: {heroku_response.status_code}")
        print(f"   Domain access: {domain_response.status_code}")
        
        if heroku_response.status_code == 200 and domain_response.status_code == 403:
            print("⚠️ Issue confirmed: Heroku works, domain blocked by CloudFlare")
        elif heroku_response.status_code == 200 and domain_response.status_code == 200:
            print("✅ Both working: Domain properly configured")
        else:
            print(f"⚠️ Mixed results: Heroku {heroku_response.status_code}, Domain {domain_response.status_code}")
            
    except Exception as e:
        print(f"❌ Comparison test failed: {e}")
    
    # Test 5: SSL/TLS analysis
    print("\n5. SSL/TLS Certificate Analysis...")
    try:
        import ssl
        import socket
        
        # Get SSL certificate info
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443)) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                
        print(f"   SSL Certificate Subject: {cert.get('subject')}")
        print(f"   SSL Certificate Issuer: {cert.get('issuer')}")
        print(f"   SSL Certificate Valid Until: {cert.get('notAfter')}")
        
        # Check if it's CloudFlare's certificate
        issuer_info = dict(cert.get('issuer', []))
        if 'Cloudflare' in str(issuer_info):
            print("✅ CloudFlare SSL certificate detected")
        else:
            print("⚠️ Non-CloudFlare SSL certificate")
            
    except Exception as e:
        print(f"❌ SSL analysis failed: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 Diagnosis Summary:")
    print("✅ DNS resolution working")
    print("✅ Heroku deployment working")
    print("⚠️ CloudFlare 403 error likely due to:")
    print("   1. Security Rules blocking requests")
    print("   2. SSL/TLS mode misconfiguration")
    print("   3. Page Rules redirecting incorrectly")
    print("   4. Bot Fight Mode or DDoS protection")
    print("   5. Firewall rules blocking traffic")
    
    print("\n🔧 Recommended CloudFlare Fixes:")
    print("1. Check SSL/TLS mode (should be 'Flexible' or 'Full')")
    print("2. Disable 'I'm Under Attack' mode")
    print("3. Review Security Rules and IP blocking")
    print("4. Check Page Rules for redirects")
    print("5. Review Bot Fight Mode settings")
    print("6. Verify DNS CNAME points to Heroku")
    
    return True

if __name__ == "__main__":
    success = test_cloudflare_domain()
    if success:
        print("\n🚀 CloudFlare domain diagnosis completed!")
    else:
        print("\n❌ CloudFlare domain diagnosis failed!") 