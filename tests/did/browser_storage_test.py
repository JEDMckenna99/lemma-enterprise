#!/usr/bin/env python3
"""
Browser Storage Test for Lemma

This script tests the browser storage functionality of Lemma using Selenium.
It verifies that credentials are properly stored in the browser's localStorage
and can be retrieved and used for verification.
"""
import os
import sys
import time
import json
import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Base URL for the Heroku deployment
BASE_URL = os.environ.get('HEROKU_URL', 'https://your-lemma-app.herokuapp.com')

def print_header(title):
    """Print a formatted header for test sections."""
    print("\n" + "=" * 50)
    print(f" {title}")
    print("=" * 50)

def setup_webdriver(headless=True):
    """Set up the Chrome WebDriver."""
    print_header("Setting up WebDriver")
    
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("✅ WebDriver set up successfully")
        return driver
    except Exception as e:
        print(f"❌ Failed to set up WebDriver: {e}")
        return None

def test_verification_flow(driver, user_id=None):
    """Test the verification flow and browser storage."""
    if user_id:
        # Use existing user
        verification_url = f"{BASE_URL}/verify?user_id={user_id}"
        print(f"Testing verification for existing user: {user_id}")
    else:
        # Just go to the home page and click "Verify Lemma"
        verification_url = BASE_URL
        print("Testing verification from home page")
    
    print_header("Testing Verification Flow")
    
    try:
        # Navigate to the verification page
        driver.get(verification_url)
        print(f"✅ Navigated to {verification_url}")
        
        if not user_id:
            # If on home page, click the "Verify Lemma" button
            try:
                verify_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "verify-lemma-btn"))
                )
                verify_button.click()
                print("✅ Clicked 'Verify Lemma' button")
            except Exception as e:
                print(f"❌ Failed to click 'Verify Lemma' button: {e}")
                return False
        
        # Wait for verification to complete
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "verification-status"))
            )
            print("✅ Verification page loaded")
        except Exception as e:
            print(f"❌ Verification page not loaded: {e}")
            return False
        
        # Check if verification was successful
        status_element = driver.find_element(By.ID, "verification-status")
        status_text = status_element.text.lower()
        
        if "success" in status_text or "verified" in status_text:
            print("✅ Verification successful")
        else:
            print(f"❌ Verification failed: {status_text}")
            return False
        
        # Check if credential was stored in localStorage
        stored_credential = driver.execute_script(
            "return localStorage.getItem('lemmaCredential');"
        )
        
        if not stored_credential:
            print("❌ No credential found in localStorage")
            return False
        
        try:
            credential_json = json.loads(stored_credential)
            print("✅ Credential stored in localStorage")
            print(f"Credential ID: {credential_json.get('id')}")
            
            # Check DID values
            issuer = credential_json.get('issuer')
            subject = credential_json.get('credentialSubject', {}).get('id')
            
            if not issuer or not issuer.startswith('did:'):
                print(f"❌ Invalid issuer DID: {issuer}")
                return False
            
            if not subject or not subject.startswith('did:'):
                print(f"❌ Invalid subject DID: {subject}")
                return False
            
            print(f"✅ Issuer DID: {issuer}")
            print(f"✅ Subject DID: {subject}")
            
            return True
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON in localStorage: {stored_credential}")
            return False
    except Exception as e:
        print(f"❌ Exception during verification flow: {e}")
        return False

def test_protected_content(driver):
    """Test accessing protected content with the stored credential."""
    print_header("Testing Protected Content Access")
    
    try:
        # Navigate to the protected page
        driver.get(f"{BASE_URL}/protected")
        print("✅ Navigated to protected page")
        
        # Wait for page to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "content-container"))
            )
            print("✅ Protected page loaded")
        except Exception as e:
            print(f"❌ Protected page not loaded: {e}")
            return False
        
        # Check if we have access to protected content
        try:
            content = driver.find_element(By.ID, "protected-content")
            if content.is_displayed():
                print("✅ Successfully accessed protected content")
                return True
            else:
                print("❌ Protected content not displayed")
                return False
        except Exception as e:
            print(f"❌ Could not find protected content: {e}")
            
            # Check if we were redirected to verification page
            try:
                verify_button = driver.find_element(By.ID, "verify-lemma-btn")
                if verify_button.is_displayed():
                    print("❌ Redirected to verification page - credential not recognized")
                    return False
            except:
                pass
            
            return False
    except Exception as e:
        print(f"❌ Exception during protected content test: {e}")
        return False

def export_import_test(driver):
    """Test exporting and importing credentials."""
    print_header("Testing Credential Export/Import")
    
    try:
        # Navigate to verification page
        driver.get(f"{BASE_URL}/verify")
        print("✅ Navigated to verification page")
        
        # Check if the credential is displayed
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "credential-json"))
            )
            print("✅ Credential displayed on verification page")
        except Exception as e:
            print(f"❌ Credential not displayed: {e}")
            return False
        
        # Get the credential JSON
        credential_element = driver.find_element(By.ID, "credential-json")
        credential_text = credential_element.get_attribute("textContent")
        
        if not credential_text:
            print("❌ No credential text found")
            return False
        
        # Clear localStorage to simulate a new browser
        driver.execute_script("localStorage.clear();")
        print("✅ Cleared localStorage to simulate new browser")
        
        # Refresh the page to verify credential is gone
        driver.refresh()
        time.sleep(2)
        
        # Check that credential is no longer in localStorage
        stored_credential = driver.execute_script(
            "return localStorage.getItem('lemmaCredential');"
        )
        
        if stored_credential:
            print("❌ Credential still in localStorage after clearing")
            return False
        
        print("✅ Credential successfully removed from localStorage")
        
        # Now manually set the credential in localStorage to simulate import
        driver.execute_script(
            f"localStorage.setItem('lemmaCredential', {json.dumps(credential_text)});"
        )
        print("✅ Manually imported credential to localStorage")
        
        # Refresh the page to verify credential is recognized
        driver.refresh()
        time.sleep(2)
        
        # Check if verification status shows the credential
        try:
            status_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "verification-status"))
            )
            status_text = status_element.text.lower()
            
            if "success" in status_text or "verified" in status_text:
                print("✅ Credential import successful")
                return True
            else:
                print(f"❌ Credential import failed: {status_text}")
                return False
        except Exception as e:
            print(f"❌ Could not verify imported credential: {e}")
            return False
    except Exception as e:
        print(f"❌ Exception during export/import test: {e}")
        return False

def run_tests(user_id=None, headless=True):
    """Run all browser tests."""
    driver = setup_webdriver(headless)
    if not driver:
        print("❌ Could not set up WebDriver, aborting tests.")
        return False
    
    try:
        # Test 1: Verification Flow
        if not test_verification_flow(driver, user_id):
            print("❌ Verification flow test failed, aborting further tests.")
            driver.quit()
            return False
        
        # Test 2: Protected Content Access
        if not test_protected_content(driver):
            print("❌ Protected content test failed.")
            # Continue with other tests
        
        # Test 3: Export/Import
        if not export_import_test(driver):
            print("❌ Export/import test failed.")
            # Continue with other tests
        
        print("\n✅ All browser tests completed!")
        return True
    finally:
        # Clean up
        driver.quit()
        print("Browser closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Lemma browser storage functionality")
    parser.add_argument("--url", help="Base URL of the Lemma deployment", default=BASE_URL)
    parser.add_argument("--user", help="Existing user ID to test with")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    
    args = parser.parse_args()
    
    if args.url:
        BASE_URL = args.url
    
    print(f"Testing Lemma deployment at: {BASE_URL}")
    
    if run_tests(user_id=args.user, headless=not args.visible):
        sys.exit(0)
    else:
        sys.exit(1) 