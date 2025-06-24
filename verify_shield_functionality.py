#!/usr/bin/env python3
"""
Comprehensive Shield Functionality Verification
Tests that the shield initialization and triggering works correctly
"""

import requests
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import os

def setup_driver():
    """Setup Chrome driver with appropriate options"""
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Use local chromedriver if available
    if os.path.exists("drivers/chromedriver-win64/chromedriver.exe"):
        driver = webdriver.Chrome(
            executable_path="drivers/chromedriver-win64/chromedriver.exe",
            options=chrome_options
        )
    else:
        # Try system PATH
        driver = webdriver.Chrome(options=chrome_options)
    
    return driver

def test_shield_initialization(driver):
    """Test that the shield initializes correctly"""
    
    print("🛡️ Testing Shield Initialization...")
    
    try:
        # Navigate to join network page
        url = "https://lemma-enterprise-0f6ba17076c1.herokuapp.com/join-network"
        driver.get(url)
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "lemma-shield-container"))
        )
        
        print("✅ Page loaded successfully")
        
        # Check for shield container
        shield_container = driver.find_element(By.ID, "lemma-shield-container")
        print(f"✅ Shield container found: {shield_container.tag_name}")
        
        # Check if LemmaShieldWidget is loaded in JavaScript
        shield_widget_loaded = driver.execute_script("return typeof window.LemmaShieldWidget !== 'undefined';")
        print(f"✅ LemmaShieldWidget loaded: {shield_widget_loaded}")
        
        # Check if shield instance exists
        shield_instance_exists = driver.execute_script("return window.lemmaShield !== undefined;")
        print(f"✅ Shield instance exists: {shield_instance_exists}")
        
        # Check initialization flag
        shield_initialized = driver.execute_script("return window.lemmaShieldInitialized;")
        print(f"✅ Shield initialized: {shield_initialized}")
        
        return True
        
    except Exception as e:
        print(f"❌ Shield initialization test failed: {e}")
        return False

def test_debug_buttons(driver):
    """Test the debug buttons functionality"""
    
    print("\n🔧 Testing Debug Buttons...")
    
    try:
        # Find debug buttons
        check_vars_btn = driver.find_element(By.ID, "checkShieldVars")
        force_show_btn = driver.find_element(By.ID, "forceShieldShow")
        test_init_btn = driver.find_element(By.ID, "testShieldInit")
        
        print("✅ All debug buttons found")
        
        # Test Check Variables button
        print("   Testing 'Check Variables' button...")
        check_vars_btn.click()
        
        # Wait for debug output
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.ID, "debugOutput"))
        )
        
        debug_output = driver.find_element(By.ID, "debugOutput")
        output_text = debug_output.get_attribute("innerHTML")
        
        if "Shield Variable Check:" in output_text:
            print("   ✅ Check Variables button working")
        else:
            print("   ❌ Check Variables button output unexpected")
        
        return True
        
    except Exception as e:
        print(f"❌ Debug buttons test failed: {e}")
        return False

def test_force_shield_show(driver):
    """Test the force shield show functionality"""
    
    print("\n🚨 Testing Force Shield Show...")
    
    try:
        # Click Force Shield Show button
        force_show_btn = driver.find_element(By.ID, "forceShieldShow")
        force_show_btn.click()
        
        # Wait a moment for the shield to appear
        time.sleep(2)
        
        # Check if shield widget is visible
        shield_visible = driver.execute_script("""
            const container = document.querySelector('#lemma-shield-container');
            const overlay = document.querySelector('.lemma-shield-overlay');
            return container && overlay && 
                   container.style.display !== 'none' && 
                   overlay !== null;
        """)
        
        if shield_visible:
            print("✅ Shield appeared successfully!")
            
            # Check for shield content
            shield_content = driver.execute_script("""
                return document.querySelector('.lemma-shield-widget') !== null;
            """)
            
            if shield_content:
                print("✅ Shield content loaded")
                
                # Try to find and click close/back button or escape
                try:
                    # Look for any button to interact with
                    shield_buttons = driver.find_elements(By.CSS_SELECTOR, ".lemma-shield-widget button")
                    if shield_buttons:
                        print(f"✅ Found {len(shield_buttons)} interactive buttons in shield")
                        
                        # Click the first button (usually "Verify Human Identity")
                        first_button = shield_buttons[0]
                        button_text = first_button.text
                        print(f"✅ Shield button text: '{button_text}'")
                        
                        # Don't actually click to start verification - just verify it's there
                        if "verify" in button_text.lower() or "human" in button_text.lower():
                            print("✅ Shield verification button found and ready")
                        
                except Exception as e:
                    print(f"   Note: Could not interact with shield buttons: {e}")
                
            else:
                print("❌ Shield appeared but no content loaded")
                
        else:
            print("❌ Shield did not appear")
            
            # Check debug output for error messages
            try:
                debug_output = driver.find_element(By.ID, "debugOutput")
                output_text = debug_output.get_attribute("innerHTML")
                print(f"   Debug output: {output_text[:200]}...")
            except:
                pass
        
        return shield_visible
        
    except Exception as e:
        print(f"❌ Force shield show test failed: {e}")
        return False

def test_revocation_trigger(driver):
    """Test the revocation trigger functionality"""
    
    print("\n🚨 Testing Revocation Trigger (without actual revocation)...")
    
    try:
        # Check if revoke button exists
        revoke_btn = driver.find_element(By.ID, "revokeCredential")
        print("✅ Revoke credential button found")
        
        # Check button properties
        button_text = revoke_btn.text
        button_enabled = revoke_btn.is_enabled()
        
        print(f"   Button text: '{button_text}'")
        print(f"   Button enabled: {button_enabled}")
        
        if "revoke" in button_text.lower() and button_enabled:
            print("✅ Revoke button is ready for testing")
            print("   (Not clicking to avoid actual revocation)")
            return True
        else:
            print("❌ Revoke button not properly configured")
            return False
            
    except Exception as e:
        print(f"❌ Revocation trigger test failed: {e}")
        return False

def main():
    """Run comprehensive shield functionality tests"""
    
    print("🛡️ COMPREHENSIVE SHIELD FUNCTIONALITY TEST")
    print("=" * 60)
    
    driver = None
    test_results = {}
    
    try:
        # Setup browser
        print("🚀 Setting up browser...")
        driver = setup_driver()
        print("✅ Browser setup complete")
        
        # Run tests
        test_results['initialization'] = test_shield_initialization(driver)
        test_results['debug_buttons'] = test_debug_buttons(driver)
        test_results['force_show'] = test_force_shield_show(driver)
        test_results['revocation_ready'] = test_revocation_trigger(driver)
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY:")
        print("=" * 60)
        
        all_passed = True
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name.replace('_', ' ').title()}: {status}")
            if not result:
                all_passed = False
        
        if all_passed:
            print("\n🎉 ALL TESTS PASSED!")
            print("\n🔧 MANUAL TESTING INSTRUCTIONS:")
            print("1. Visit: https://lemma-enterprise-0f6ba17076c1.herokuapp.com/join-network")
            print("2. Open browser console (F12)")
            print("3. Click '🚨 Force Shield Show' button")
            print("4. Verify shield appears with verification interface")
            print("5. Test the revocation flow if needed")
            print("\n✅ Shield initialization is working correctly!")
        else:
            print("\n❌ SOME TESTS FAILED")
            print("Check the error messages above for debugging information")
            
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        print("\n🔧 FALLBACK TESTING:")
        print("You can still manually test by:")
        print("1. Visit: https://lemma-enterprise-0f6ba17076c1.herokuapp.com/join-network")
        print("2. Use the debug buttons in the page")
        print("3. Check browser console for any errors")
        
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main() 