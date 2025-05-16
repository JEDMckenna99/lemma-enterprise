#!/usr/bin/env python3
"""
Wallet Test Script for Lemma

Tests the wallet storage functionality and verifiable credential workflow:
1. Getting a credential
2. Storing it in the wallet
3. Creating a verifiable presentation
4. Verifying the presentation
"""
import sys
import json
import requests
import uuid
import time
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Base URL - change this to your local or Heroku instance
BASE_URL = "http://localhost:5000"

def print_header(title):
    """Print a formatted header for test sections."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)

def setup_webdriver(headless=False):
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

def get_credential(user_id=None):
    """Get a credential for a user via API."""
    if not user_id:
        user_id = f"test-{uuid.uuid4().hex[:8]}"
    
    print_header(f"Getting Credential for User: {user_id}")
    
    url = urljoin(BASE_URL, f"/api/credential-lookup/{user_id}")
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            credential = response.json()
            print("✅ Successfully retrieved credential")
            print(f"Credential ID: {credential.get('id')}")
            
            # Check DID values in credential
            issuer = credential.get('issuer')
            subject = credential.get('credentialSubject', {}).get('id')
            
            print(f"Issuer DID: {issuer}")
            print(f"Subject DID: {subject}")
            
            return credential, user_id
        else:
            print(f"❌ Failed to get credential: {response.status_code}")
            print(f"Response: {response.text}")
            return None, user_id
    except Exception as e:
        print(f"❌ Exception during credential retrieval: {e}")
        return None, user_id

def test_browser_wallet_storage(driver, credential, user_id):
    """Test storing credential in the browser wallet."""
    print_header("Testing Browser Wallet Storage")
    
    if not credential:
        print("❌ No credential to store")
        return False
    
    try:
        # Navigate to the verification page
        driver.get(f"{BASE_URL}/verify")
        print(f"✅ Navigated to verification page")
        
        # Use JavaScript to initialize the wallet and store the credential
        init_wallet_script = """
        if (!window.lemmaWallet) {
            window.lemmaWallet = new LemmaWallet();
            await window.lemmaWallet.init();
        }
        return window.lemmaWallet ? true : false;
        """
        
        wallet_initialized = driver.execute_script(init_wallet_script)
        if not wallet_initialized:
            print("❌ Failed to initialize wallet")
            return False
        
        print("✅ Wallet initialized")
        
        # Store the credential in the wallet
        store_credential_script = f"""
        const credential = {json.dumps(credential)};
        const userId = "{user_id}";
        
        try {{
            // Format for wallet if needed
            let walletCredential = credential;
            if (!credential.credential && !credential.wallet_metadata) {{
                walletCredential = {{
                    credential: credential,
                    wallet_metadata: {{
                        added_at: new Date().toISOString(),
                        holder_id: userId,
                        status: "active",
                        display_name: "Lemma Human Verification",
                        fingerprint: credential.id || `fingerprint-${{Date.now()}}`
                    }}
                }};
            }}
            
            // Store in wallet
            await window.lemmaWallet.storeCredential(walletCredential);
            return true;
        }} catch (error) {{
            console.error('Failed to store credential:', error);
            return false;
        }}
        """
        
        credential_stored = driver.execute_script(store_credential_script)
        if not credential_stored:
            print("❌ Failed to store credential in wallet")
            return False
        
        print("✅ Credential stored in wallet")
        
        # Verify the credential is in the wallet
        check_wallet_script = """
        try {
            const credentials = await window.lemmaWallet.getAllCredentials();
            return credentials;
        } catch (error) {
            console.error('Failed to get credentials:', error);
            return [];
        }
        """
        
        wallet_credentials = driver.execute_script(check_wallet_script)
        if not wallet_credentials:
            print("❌ No credentials found in wallet")
            return False
        
        print(f"✅ Found {len(wallet_credentials)} credentials in wallet")
        
        # Check if our credential is in the wallet
        credential_found = any(wc.get('credential', {}).get('id') == credential.get('id') for wc in wallet_credentials)
        if not credential_found:
            print("❌ Our credential is not in the wallet")
            return False
        
        print("✅ Our credential is in the wallet")
        return True
    except Exception as e:
        print(f"❌ Exception during wallet storage test: {e}")
        return False

def create_presentation(credential, challenge="test-challenge"):
    """Create a verifiable presentation from a credential."""
    print_header("Creating Verifiable Presentation")
    
    if not credential:
        print("❌ No credential to create presentation from")
        return None
    
    url = urljoin(BASE_URL, "/api/presentation")
    
    try:
        response = requests.post(
            url,
            json={"credential": credential, "challenge": challenge}
        )
        
        if response.status_code == 200:
            presentation = response.json()
            print("✅ Successfully created verifiable presentation")
            print(f"Presentation type: {presentation.get('type')}")
            print(f"Challenge: {presentation.get('proof', {}).get('challenge')}")
            return presentation
        else:
            print(f"❌ Failed to create presentation: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Exception during presentation creation: {e}")
        return None

def verify_presentation(presentation):
    """Verify a presentation."""
    print_header("Verifying Presentation")
    
    if not presentation:
        print("❌ No presentation to verify")
        return False
    
    url = urljoin(BASE_URL, "/api/verify")
    
    try:
        response = requests.post(url, json=presentation)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('valid'):
                print("✅ Presentation verified successfully")
                print(f"Issuer: {result.get('issuer')}")
                print(f"Subject: {result.get('subject')}")
                return True
            else:
                print(f"❌ Presentation verification failed: {result.get('reason')}")
                return False
        else:
            print(f"❌ Verification request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception during verification: {e}")
        return False

def test_protected_access_with_wallet(driver):
    """Test accessing protected content with stored wallet credential."""
    print_header("Testing Protected Access with Wallet Credential")
    
    try:
        # Navigate to the protected page
        driver.get(f"{BASE_URL}/protected")
        print("✅ Navigated to protected page")
        
        # Wait for page to load
        time.sleep(2)
        
        # Check if we have access to protected content
        try:
            if "protected content" in driver.page_source.lower():
                print("✅ Successfully accessed protected content")
                return True
            else:
                print("❌ Protected content not found on the page")
                
                # If we were redirected to verification, the wallet didn't work
                if "verify your humanity" in driver.page_source.lower():
                    print("❌ Redirected to verification page - wallet credential not recognized")
                
                return False
        except Exception as e:
            print(f"❌ Could not check for protected content: {e}")
            return False
    except Exception as e:
        print(f"❌ Exception during protected access test: {e}")
        return False

def main():
    """Run the wallet and VC workflow tests."""
    if len(sys.argv) > 1:
        global BASE_URL
        BASE_URL = sys.argv[1]
    
    print(f"Testing Lemma wallet at: {BASE_URL}")
    
    # Step 1: Get a credential
    credential, user_id = get_credential()
    
    if not credential:
        print("❌ Failed to get a credential, cannot continue testing")
        return 1
    
    # Step 2: Test browser wallet storage
    driver = setup_webdriver(headless=False)
    if not driver:
        print("❌ Failed to set up WebDriver, cannot continue testing")
        return 1
    
    try:
        # Test storing the credential in the wallet
        wallet_test_result = test_browser_wallet_storage(driver, credential, user_id)
        
        if not wallet_test_result:
            print("❌ Wallet storage test failed, cannot continue testing")
            return 1
        
        # Step 3: Test protected access with wallet credential
        protected_access_result = test_protected_access_with_wallet(driver)
        
        # Step 4: Create a presentation
        presentation = create_presentation(credential)
        
        # Step 5: Verify the presentation
        if presentation:
            verify_presentation(presentation)
    finally:
        # Clean up
        driver.quit()
    
    print_header("Test Summary")
    print("Completed wallet and VC workflow testing for Lemma")
    print(f"URL tested: {BASE_URL}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 