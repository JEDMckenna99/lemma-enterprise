#!/usr/bin/env python3
"""
Test Shield Initialization on Live Deployment
Tests the fixes made to the shield widget initialization
"""

import requests
import json
import time
from bs4 import BeautifulSoup

def test_join_network_page():
    """Test that the join network page loads with shield components"""
    
    print("🚀 Testing Join Network Page Shield Components...")
    
    try:
        # Get the join network page
        url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/join-network"
        response = requests.get(url)
        
        print(f"✅ Page Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Failed to load page: {response.status_code}")
            return False
            
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check for shield container
        shield_container = soup.find('div', id='lemma-shield-container')
        print(f"✅ Shield Container: {'Found' if shield_container else 'Missing'}")
        
        # Check for shield widget script
        shield_script = soup.find('script', src=lambda x: x and 'lemma-shield-widget.js' in x)
        print(f"✅ Shield Widget Script: {'Found' if shield_script else 'Missing'}")
        
        # Check for debug buttons
        debug_buttons = {
            'testShieldInit': soup.find('button', id='testShieldInit'),
            'forceShieldShow': soup.find('button', id='forceShieldShow'),
            'checkShieldVars': soup.find('button', id='checkShieldVars')
        }
        
        print("🔧 Debug Buttons:")
        for button_name, button_element in debug_buttons.items():
            print(f"   {button_name}: {'Found' if button_element else 'Missing'}")
        
        # Check for initializeLemmaShield function
        has_init_function = 'function initializeLemmaShield(' in response.text
        print(f"✅ Shield Init Function: {'Found' if has_init_function else 'Missing'}")
        
        # Check for LemmaShieldWidget references
        has_widget_class = 'LemmaShieldWidget' in response.text
        print(f"✅ Shield Widget Class: {'Found' if has_widget_class else 'Missing'}")
        
        # Check for forceShow method
        has_force_show = 'forceShow' in response.text
        print(f"✅ Force Show Method: {'Found' if has_force_show else 'Missing'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing join network page: {e}")
        return False

def test_shield_api_endpoints():
    """Test shield-related API endpoints"""
    
    print("\n🛡️ Testing Shield API Endpoints...")
    
    endpoints = [
        "/api/health",
        "/api/shield/status",
        "/api/generate-challenge"
    ]
    
    base_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}")
            print(f"   {endpoint}: {response.status_code}")
            
            if endpoint == "/api/health":
                data = response.json()
                print(f"      Service: {data.get('service', 'Unknown')}")
                print(f"      Version: {data.get('version', 'Unknown')}")
                
        except Exception as e:
            print(f"   {endpoint}: Error - {e}")

def test_shield_widget_availability():
    """Test that the shield widget JavaScript is accessible"""
    
    print("\n📜 Testing Shield Widget Script Availability...")
    
    script_url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-shield-widget.js"
    
    try:
        response = requests.get(script_url)
        print(f"✅ Shield Widget Script Status: {response.status_code}")
        
        if response.status_code == 200:
            script_content = response.text
            
            # Check for key components
            checks = [
                ('LemmaShieldWidget class', 'class LemmaShieldWidget'),
                ('forceShow method', 'forceShow(options = {})'),
                ('showVerificationWidget method', 'showVerificationWidget()'),
                ('getShieldContainer method', 'getShieldContainer()'),
                ('static forceShow method', 'static forceShow(options = {})')
            ]
            
            print("   Component Checks:")
            for check_name, search_string in checks:
                found = search_string in script_content
                print(f"      {check_name}: {'✅ Found' if found else '❌ Missing'}")
                
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ Error testing shield widget script: {e}")
        return False

def main():
    """Run all shield tests"""
    
    print("🛡️ LEMMA SHIELD INITIALIZATION TEST")
    print("=" * 50)
    
    # Test join network page
    page_success = test_join_network_page()
    
    # Test API endpoints
    test_shield_api_endpoints()
    
    # Test shield widget script
    script_success = test_shield_widget_availability()
    
    print("\n📊 TEST RESULTS:")
    print("=" * 30)
    print(f"Join Network Page: {'✅ PASS' if page_success else '❌ FAIL'}")
    print(f"Shield Widget Script: {'✅ PASS' if script_success else '❌ FAIL'}")
    
    if page_success and script_success:
        print("\n🎉 ALL TESTS PASSED!")
        print("\n🔧 Next Steps:")
        print("1. Visit https://lemma-enterprise-0f6ba17076c1.herokuapp.com/join-network")
        print("2. Open browser console (F12)")
        print("3. Click the debug buttons in the 'Debug Shield Initialization' section")
        print("4. Test the shield functionality")
        print("\nDebug buttons available:")
        print("   🛡️ Test Shield Init - Tests initialization function")
        print("   🚨 Force Shield Show - Manually triggers shield display")
        print("   🔍 Check Variables - Shows status of shield variables")
    else:
        print("\n❌ SOME TESTS FAILED")
        print("Check the error messages above for details")

if __name__ == "__main__":
    main() 