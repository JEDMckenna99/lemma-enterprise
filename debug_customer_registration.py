#!/usr/bin/env python3
"""Debug customer registration and API key validation."""

import requests
import json
import re

def debug_customer_registration():
    """Debug the customer registration and API key system."""
    
    print("🔍 Debugging Customer Registration & Bot Shield...")
    
    base_url = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'
    
    # Step 1: Access join-network page to trigger customer registration
    print("\n1️⃣ Accessing join-network page to trigger customer registration...")
    try:
        r = requests.get(f'{base_url}/join-network')
        if r.status_code == 200:
            print("✅ Join-network page loaded successfully")
            
            # Try to extract the API key from the page
            content = r.text
            
            # Look for the API key in the JavaScript configuration
            api_key_match = re.search(r"apiKey:\s*['\"]([^'\"]+)['\"]", content)
            if api_key_match:
                api_key = api_key_match.group(1)
                print(f"✅ Found API key in page: {api_key[:20]}...")
                
                # Test the API key
                print(f"\n2️⃣ Testing API key validation...")
                headers = {'X-API-Key': api_key}
                
                # Test with our extracted API key
                test_endpoints = [
                    '/api/health',
                    '/api/shield/health', 
                    '/api/generate-challenge'
                ]
                
                for endpoint in test_endpoints:
                    try:
                        test_r = requests.get(f'{base_url}{endpoint}', headers=headers)
                        print(f"   {endpoint}: Status {test_r.status_code}")
                        if test_r.status_code == 200:
                            try:
                                response_data = test_r.json()
                                print(f"   ✅ Response: {response_data}")
                            except:
                                print(f"   ✅ Response: {test_r.text[:100]}...")
                        elif test_r.status_code == 401:
                            print(f"   ❌ API key rejected (401 Unauthorized)")
                        elif test_r.status_code == 404:
                            print(f"   ⚠️  Endpoint not found (404)")
                        else:
                            print(f"   ⚠️  Unexpected status: {test_r.status_code}")
                    except Exception as e:
                        print(f"   ❌ Error testing {endpoint}: {e}")
                
            else:
                print("❌ Could not find API key in page content")
                # Show a sample of the content to debug
                print("Content sample:")
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'apiKey' in line or 'api_key' in line or 'lemma_prod' in line:
                        print(f"Line {i+1}: {line.strip()}")
                        
        else:
            print(f"❌ Join-network page failed: {r.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error accessing join-network page: {e}")
        return False
    
    # Step 3: Test if customer files were created
    print("\n3️⃣ Testing customer data persistence...")
    
    # We can't directly access the file system from here, but we can test 
    # if the customer registration route works
    try:
        # Access the page again to see if the customer persists
        r2 = requests.get(f'{base_url}/join-network')
        if r2.status_code == 200:
            content2 = r2.text
            api_key_match2 = re.search(r"apiKey:\s*['\"]([^'\"]+)['\"]", content2)
            if api_key_match2:
                api_key2 = api_key_match2.group(1)
                if api_key == api_key2:
                    print("✅ API key is consistent (customer data persisted)")
                else:
                    print("⚠️  API key changed (might be regenerating each time)")
                    print(f"   First:  {api_key[:20]}...")
                    print(f"   Second: {api_key2[:20]}...")
            else:
                print("❌ API key not found on second load")
    except Exception as e:
        print(f"⚠️  Error testing persistence: {e}")
    
    # Step 4: Check if Shield SDK is properly configured
    print("\n4️⃣ Checking Shield SDK configuration...")
    if 'LemmaShieldWidget' in content:
        print("✅ Shield SDK found in page")
    else:
        print("❌ Shield SDK not found in page")
    
    if 'LemmaConfig' in content:
        print("✅ Lemma configuration found in page")
    else:
        print("❌ Lemma configuration not found in page")
    
    # Step 5: Summary and recommendations
    print("\n📊 Debug Summary:")
    if api_key_match:
        print("✅ Customer registration appears to be working")
        print("✅ API key is being generated and embedded in page")
        print("🎯 Shield should be functional")
        print("\n🔧 If shield still not working, the issue might be:")
        print("   1. Client-side JavaScript errors")
        print("   2. API endpoints returning 404")
        print("   3. Shield SDK not loading properly")
        print("   4. Browser console errors")
    else:
        print("❌ Customer registration is NOT working properly")
        print("🔧 Needs investigation into:")
        print("   1. Customer registration code in join_network route")
        print("   2. Template rendering of API key")
        print("   3. Potential template errors")
    
    return True

if __name__ == "__main__":
    debug_customer_registration() 