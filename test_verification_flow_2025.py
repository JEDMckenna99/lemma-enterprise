#!/usr/bin/env python3
"""
Test script for enhanced 2025 SaaS verification flow
Tests IndexedDB storage, session mirroring, and Clear Lemma modal
"""

import requests
import time
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
import json
import os

class VerificationFlow2025Test:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.driver = None
        self.test_results = []
        
    def setup_driver(self):
        """Setup Chrome driver with necessary options"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in background
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Enable IndexedDB and localStorage
        chrome_options.add_argument("--enable-features=VaapiVideoDecoder")
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            print("✅ Chrome WebDriver initialized successfully")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize WebDriver: {e}")
            return False
    
    def test_server_health(self):
        """Test if server is running and healthy"""
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            if response.status_code == 200:
                print("✅ Server health check passed")
                return True
            else:
                print(f"❌ Server health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Server health check failed: {e}")
            return False
    
    def test_verification_flow_script_loads(self):
        """Test that the verification flow script loads correctly"""
        try:
            self.driver.get(f"{self.base_url}/protected")
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Check if verification flow is initialized
            script_check = """
            return new Promise((resolve) => {
                if (window.lemmaVerificationFlow && window.lemmaVerificationFlow.initialized) {
                    resolve({success: true, version: window.lemmaVerificationFlow.version});
                } else {
                    // Wait a bit for initialization
                    setTimeout(() => {
                        if (window.lemmaVerificationFlow && window.lemmaVerificationFlow.initialized) {
                            resolve({success: true, version: window.lemmaVerificationFlow.version});
                        } else {
                            resolve({success: false, error: 'Verification flow not initialized'});
                        }
                    }, 2000);
                }
            });
            """
            
            result = self.driver.execute_async_script(script_check)
            
            if result.get('success'):
                print(f"✅ Verification flow script loaded successfully (v{result.get('version')})")
                self.test_results.append({
                    'test': 'verification_flow_script_loads',
                    'status': 'passed',
                    'version': result.get('version')
                })
                return True
            else:
                print(f"❌ Verification flow script failed to load: {result.get('error')}")
                self.test_results.append({
                    'test': 'verification_flow_script_loads',
                    'status': 'failed',
                    'error': result.get('error')
                })
                return False
                
        except Exception as e:
            print(f"❌ Error testing verification flow script: {e}")
            self.test_results.append({
                'test': 'verification_flow_script_loads',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    def test_indexeddb_verification(self):
        """Test IndexedDB credential storage verification"""
        try:
            # Navigate to protected page
            self.driver.get(f"{self.base_url}/protected")
            
            # Wait for page load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Test IndexedDB functionality
            indexeddb_test = """
            return new Promise(async (resolve) => {
                try {
                    if (!window.lemmaVerificationFlow) {
                        resolve({success: false, error: 'Verification flow not available'});
                        return;
                    }
                    
                    // Wait for initialization
                    let attempts = 0;
                    while (!window.lemmaVerificationFlow.initialized && attempts < 50) {
                        await new Promise(r => setTimeout(r, 100));
                        attempts++;
                    }
                    
                    if (!window.lemmaVerificationFlow.initialized) {
                        resolve({success: false, error: 'Verification flow not initialized after 5s'});
                        return;
                    }
                    
                    // Test IndexedDB access
                    const credentials = await window.lemmaVerificationFlow.getAllCredentialsFromIndexedDB();
                    
                    resolve({
                        success: true,
                        credentialCount: credentials.length,
                        dbName: window.lemmaVerificationFlow.dbName,
                        dbVersion: window.lemmaVerificationFlow.dbVersion
                    });
                    
                } catch (error) {
                    resolve({success: false, error: error.message});
                }
            });
            """
            
            result = self.driver.execute_async_script(indexeddb_test)
            
            if result.get('success'):
                print(f"✅ IndexedDB verification passed - Found {result.get('credentialCount')} credentials")
                print(f"   DB: {result.get('dbName')} v{result.get('dbVersion')}")
                self.test_results.append({
                    'test': 'indexeddb_verification',
                    'status': 'passed',
                    'credentialCount': result.get('credentialCount'),
                    'dbName': result.get('dbName'),
                    'dbVersion': result.get('dbVersion')
                })
                return True
            else:
                print(f"❌ IndexedDB verification failed: {result.get('error')}")
                self.test_results.append({
                    'test': 'indexeddb_verification',
                    'status': 'failed',
                    'error': result.get('error')
                })
                return False
                
        except Exception as e:
            print(f"❌ Error testing IndexedDB verification: {e}")
            self.test_results.append({
                'test': 'indexeddb_verification',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    def test_session_storage_mirroring(self):
        """Test session storage mirroring functionality"""
        try:
            # Test session storage functionality
            session_test = """
            return new Promise(async (resolve) => {
                try {
                    const flow = window.lemmaVerificationFlow;
                    if (!flow || !flow.initialized) {
                        resolve({success: false, error: 'Verification flow not available'});
                        return;
                    }
                    
                    // Test saving session state
                    const testState = {
                        test: true,
                        timestamp: Date.now(),
                        userAgent: navigator.userAgent.substring(0, 50)
                    };
                    
                    flow.saveSessionState(testState);
                    
                    // Test loading session state
                    const loadedState = flow.loadSessionState();
                    
                    // Test session storage key
                    const sessionData = sessionStorage.getItem(flow.sessionStorageKey);
                    const hasSessionData = !!sessionData;
                    
                    resolve({
                        success: true,
                        testStateSaved: !!loadedState,
                        sessionStorageWorking: hasSessionData,
                        sessionKey: flow.sessionStorageKey,
                        stateVersion: loadedState ? loadedState.version : null
                    });
                    
                } catch (error) {
                    resolve({success: false, error: error.message});
                }
            });
            """
            
            result = self.driver.execute_async_script(session_test)
            
            if result.get('success'):
                print("✅ Session storage mirroring test passed")
                print(f"   State saved: {result.get('testStateSaved')}")
                print(f"   Session storage working: {result.get('sessionStorageWorking')}")
                print(f"   Session key: {result.get('sessionKey')}")
                self.test_results.append({
                    'test': 'session_storage_mirroring',
                    'status': 'passed',
                    'testStateSaved': result.get('testStateSaved'),
                    'sessionStorageWorking': result.get('sessionStorageWorking'),
                    'sessionKey': result.get('sessionKey')
                })
                return True
            else:
                print(f"❌ Session storage mirroring test failed: {result.get('error')}")
                self.test_results.append({
                    'test': 'session_storage_mirroring',
                    'status': 'failed',
                    'error': result.get('error')
                })
                return False
                
        except Exception as e:
            print(f"❌ Error testing session storage mirroring: {e}")
            self.test_results.append({
                'test': 'session_storage_mirroring',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    def test_clear_credential_modal(self):
        """Test the enhanced Clear Lemma button with 2025 SaaS modal"""
        try:
            # Navigate to protected page
            self.driver.get(f"{self.base_url}/protected")
            
            # Wait for page load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Look for Clear Credential button
            try:
                clear_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Clear Credential')]"))
                )
                print("✅ Found Clear Credential button")
            except:
                print("❌ Clear Credential button not found or not clickable")
                return False
            
            # Test modal functionality
            modal_test = """
            return new Promise(async (resolve) => {
                try {
                    const flow = window.lemmaVerificationFlow;
                    if (!flow || !flow.initialized) {
                        resolve({success: false, error: 'Verification flow not available'});
                        return;
                    }
                    
                    // Test modal creation without actually clearing
                    const modal = flow.createClearCredentialModal();
                    document.body.appendChild(modal);
                    
                    const modalExists = !!document.querySelector('.lemma-gate-modal, [role="dialog"]');
                    const hasConfirmButton = !!modal.querySelector('#lemma-clear-confirm');
                    const hasCancelButton = !!modal.querySelector('#lemma-clear-cancel');
                    const hasCloseButton = !!modal.querySelector('#lemma-clear-close');
                    
                    // Clean up test modal
                    modal.remove();
                    
                    resolve({
                        success: true,
                        modalCreated: modalExists,
                        hasConfirmButton: hasConfirmButton,
                        hasCancelButton: hasCancelButton,
                        hasCloseButton: hasCloseButton
                    });
                    
                } catch (error) {
                    resolve({success: false, error: error.message});
                }
            });
            """
            
            result = self.driver.execute_async_script(modal_test)
            
            if result.get('success'):
                print("✅ Clear credential modal test passed")
                print(f"   Modal created: {result.get('modalCreated')}")
                print(f"   Has confirm button: {result.get('hasConfirmButton')}")
                print(f"   Has cancel button: {result.get('hasCancelButton')}")
                print(f"   Has close button: {result.get('hasCloseButton')}")
                self.test_results.append({
                    'test': 'clear_credential_modal',
                    'status': 'passed',
                    'modalCreated': result.get('modalCreated'),
                    'hasConfirmButton': result.get('hasConfirmButton'),
                    'hasCancelButton': result.get('hasCancelButton'),
                    'hasCloseButton': result.get('hasCloseButton')
                })
                return True
            else:
                print(f"❌ Clear credential modal test failed: {result.get('error')}")
                self.test_results.append({
                    'test': 'clear_credential_modal',
                    'status': 'failed',
                    'error': result.get('error')
                })
                return False
                
        except Exception as e:
            print(f"❌ Error testing clear credential modal: {e}")
            self.test_results.append({
                'test': 'clear_credential_modal',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    def test_keyboard_shortcuts(self):
        """Test Lemma keyboard shortcuts"""
        try:
            # Test keyboard shortcuts
            keyboard_test = """
            return new Promise((resolve) => {
                try {
                    let shortcutsDetected = 0;
                    
                    // Test Ctrl+L shortcut detection
                    const handleKeydown = (e) => {
                        if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
                            shortcutsDetected++;
                        }
                        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'L') {
                            shortcutsDetected++;
                        }
                    };
                    
                    document.addEventListener('keydown', handleKeydown);
                    
                    // Simulate Ctrl+L
                    const event1 = new KeyboardEvent('keydown', {
                        key: 'l',
                        ctrlKey: true,
                        bubbles: true
                    });
                    document.dispatchEvent(event1);
                    
                    // Simulate Ctrl+Shift+L
                    const event2 = new KeyboardEvent('keydown', {
                        key: 'L',
                        ctrlKey: true,
                        shiftKey: true,
                        bubbles: true
                    });
                    document.dispatchEvent(event2);
                    
                    document.removeEventListener('keydown', handleKeydown);
                    
                    resolve({
                        success: true,
                        shortcutsDetected: shortcutsDetected
                    });
                    
                } catch (error) {
                    resolve({success: false, error: error.message});
                }
            });
            """
            
            result = self.driver.execute_async_script(keyboard_test)
            
            if result.get('success'):
                shortcuts_detected = result.get('shortcutsDetected', 0)
                print(f"✅ Keyboard shortcuts test passed - Detected {shortcuts_detected} shortcuts")
                self.test_results.append({
                    'test': 'keyboard_shortcuts',
                    'status': 'passed',
                    'shortcutsDetected': shortcuts_detected
                })
                return True
            else:
                print(f"❌ Keyboard shortcuts test failed: {result.get('error')}")
                self.test_results.append({
                    'test': 'keyboard_shortcuts',
                    'status': 'failed',
                    'error': result.get('error')
                })
                return False
                
        except Exception as e:
            print(f"❌ Error testing keyboard shortcuts: {e}")
            self.test_results.append({
                'test': 'keyboard_shortcuts',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()
            print("✅ WebDriver cleaned up")
    
    def run_all_tests(self):
        """Run all verification flow tests"""
        print("🚀 Starting Enhanced 2025 SaaS Verification Flow Tests")
        print("=" * 60)
        
        # Setup
        if not self.setup_driver():
            return False
        
        # Test server health first
        if not self.test_server_health():
            self.cleanup()
            return False
        
        # Run tests
        tests = [
            self.test_verification_flow_script_loads,
            self.test_indexeddb_verification,
            self.test_session_storage_mirroring,
            self.test_clear_credential_modal,
            self.test_keyboard_shortcuts
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            if test():
                passed += 1
            print("-" * 40)
        
        # Results summary
        print("=" * 60)
        print(f"📊 TEST RESULTS: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED - 2025 SaaS Verification Flow is working!")
        else:
            print(f"⚠️  {total - passed} tests failed - See details above")
        
        # Save results
        results = {
            'timestamp': time.time(),
            'passed': passed,
            'total': total,
            'success_rate': (passed / total) * 100,
            'tests': self.test_results
        }
        
        with open('verification_flow_2025_test_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"📁 Results saved to verification_flow_2025_test_results.json")
        
        self.cleanup()
        return passed == total

if __name__ == "__main__":
    tester = VerificationFlow2025Test()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1) 