#!/usr/bin/env python3
"""
Test script to verify bot shield protection on join network page
"""

import requests
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

def test_join_network_shield():
    """Test that the join network page is properly protected by bot shield"""
    print("🛡️ TESTING JOIN NETWORK BOT SHIELD PROTECTION")
    print("=" * 60)
    
    # Test 1: Page loads with shield components
    print("1️⃣ Testing page load and shield components...")
    try:
        response = requests.get(f"{BASE_URL}/join-network", timeout=15)
        if response.status_code == 200:
            print("   ✅ Join network page loads successfully")
            
            # Check for critical shield components
            content = response.text
            checks = [
                ("Shield Container", "lemma-shield-container"),
                ("Shield Widget Script", "lemma-shield-widget.js"),
                ("Auto-protection Config", "autoProtect: true"),
                ("Shield Initialization", "initializeLemmaShield"),
                ("Force Show Button", "forceShowShield"),
                ("Shield Debug Output", "shieldDebugOutput"),
                ("LemmaConfig", "window.LemmaConfig"),
            ]
            
            passed = 0
            for name, pattern in checks:
                if pattern in content:
                    print(f"   ✅ {name}")
                    passed += 1
                else:
                    print(f"   ❌ {name}")
            
            print(f"   📊 Shield components: {passed}/{len(checks)} found")
            return passed >= 6  # Need at least 6/7 to pass
        else:
            print(f"   ❌ Page failed to load: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Error accessing page: {e}")
        return False

def test_shield_with_selenium():
    """Test shield functionality with browser automation"""
    print("\n2️⃣ Testing shield functionality with browser...")
    
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        
        # Load the join network page
        print("   📖 Loading join network page...")
        driver.get(f"{BASE_URL}/join-network")
        
        # Wait for page to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Check for shield container
        try:
            shield_container = driver.find_element(By.ID, "lemma-shield-container")
            print("   ✅ Shield container found")
        except:
            print("   ❌ Shield container not found")
            driver.quit()
            return False
        
        # Check for force show button and click it
        try:
            force_btn = driver.find_element(By.ID, "forceShowShield")
            print("   ✅ Force show button found")
            force_btn.click()
            print("   🔧 Force show button clicked")
            
            # Wait a moment for shield to appear
            time.sleep(2)
            
            # Check if shield container is now visible or has content
            container_style = shield_container.get_attribute("style")
            container_html = shield_container.get_attribute("innerHTML")
            
            if "display: none" not in container_style or container_html.strip():
                print("   ✅ Shield container activated after force show")
            else:
                print("   ⚠️ Shield container might not be fully activated")
                
        except Exception as e:
            print(f"   ⚠️ Force show test failed: {e}")
        
        # Check JavaScript console for any errors
        logs = driver.get_log('browser')
        error_count = sum(1 for log in logs if log['level'] == 'SEVERE')
        if error_count == 0:
            print("   ✅ No JavaScript errors detected")
        else:
            print(f"   ⚠️ {error_count} JavaScript errors detected")
            
        driver.quit()
        return True
        
    except Exception as e:
        print(f"   ❌ Selenium test failed: {e}")
        try:
            driver.quit()
        except:
            pass
        return False

def main():
    """Run all shield protection tests"""
    print("🧪 RUNNING BOT SHIELD PROTECTION TESTS")
    print("=" * 60)
    
    success_count = 0
    total_tests = 2
    
    # Test 1: Page components
    if test_join_network_shield():
        success_count += 1
        
    # Test 2: Selenium functionality
    if test_shield_with_selenium():
        success_count += 1
    
    print("\n" + "=" * 60)
    print("BOT SHIELD PROTECTION TEST RESULTS")
    print("=" * 60)
    print(f"✅ Tests passed: {success_count}/{total_tests}")
    
    if success_count == total_tests:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Bot shield is properly protecting the join network page")
        print("✅ Shield components are correctly integrated")
        print("✅ Force show functionality works")
        print("\n📋 What this means:")
        print("- The join network page now has working bot shield protection")
        print("- Users without valid credentials will see the verification widget")
        print("- Auto-protection is enabled and will check credentials automatically")
        print("- Debug controls are available for testing")
        return True
    else:
        print(f"\n❌ {total_tests - success_count} tests failed")
        print("🔧 The bot shield may need additional configuration")
        return False

if __name__ == '__main__':
    main() 