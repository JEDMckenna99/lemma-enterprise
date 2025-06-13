#!/usr/bin/env python3
"""
Simple Wallet Test Generator
Creates a basic test page to verify Lemma wallet functionality.
"""

import os
from pathlib import Path

def create_wallet_test():
    """Create a simple wallet test page."""
    
    test_dir = Path("wallet_tests")
    test_dir.mkdir(exist_ok=True)
    
    # Simple HTML test page
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lemma Wallet Test</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .test-section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; }
        .success { color: green; }
        .error { color: red; }
        button { margin: 5px; padding: 10px; }
        #results { margin-top: 20px; padding: 10px; background: #f5f5f5; }
    </style>
</head>
<body>
    <h1>Lemma Wallet Test</h1>
    
    <div class="test-section">
        <h2>Wallet Initialization</h2>
        <button onclick="testWalletInit()">Test Wallet Init</button>
        <div id="init-result"></div>
    </div>
    
    <div class="test-section">
        <h2>Credential Storage</h2>
        <button onclick="testCredentialStorage()">Test Store Credential</button>
        <div id="storage-result"></div>
    </div>
    
    <div class="test-section">
        <h2>Lost Credential Recovery</h2>
        <button onclick="testLostCredentialFlow()">Test Recovery Flow</button>
        <div id="lost-result"></div>
    </div>
    
    <div id="results"></div>
    
    <!-- Lemma Wallet Scripts -->
    <script src="http://localhost:5000/static/js/lemma-wallet.js"></script>
    <script src="http://localhost:5000/static/js/lemma-wallet-init.js"></script>
    
    <script>
        let testResults = [];
        
        function logResult(test, status, message) {
            const result = { test, status, message, timestamp: new Date().toISOString() };
            testResults.push(result);
            updateResults();
        }
        
        function updateResults() {
            const resultsDiv = document.getElementById('results');
            resultsDiv.innerHTML = '<h3>Test Results:</h3>' + 
                testResults.map(r => 
                    `<div class="${r.status}">[${r.status.toUpperCase()}] ${r.test}: ${r.message}</div>`
                ).join('');
        }
        
        async function testWalletInit() {
            const resultDiv = document.getElementById('init-result');
            try {
                await waitForWallet();
                
                if (window.lemmaWallet) {
                    await window.lemmaWallet.init();
                    resultDiv.innerHTML = '<span class="success">✅ Wallet initialized successfully</span>';
                    logResult('Wallet Initialization', 'success', 'Wallet available and initialized');
                } else {
                    throw new Error('Wallet not available');
                }
            } catch (error) {
                resultDiv.innerHTML = `<span class="error">❌ Failed: ${error.message}</span>`;
                logResult('Wallet Initialization', 'error', error.message);
            }
        }
        
        async function testCredentialStorage() {
            const resultDiv = document.getElementById('storage-result');
            try {
                await waitForWallet();
                
                const testCredential = {
                    "@context": ["https://www.w3.org/2018/credentials/v1"],
                    "type": ["VerifiableCredential", "LemmaHumanCredential"],
                    "id": `test-credential-${Date.now()}`,
                    "issuer": "did:lemma:test",
                    "issuanceDate": new Date().toISOString(),
                    "credentialSubject": {
                        "id": "did:user:test-user",
                        "isHuman": true
                    },
                    "proof": {
                        "type": "Ed25519Signature2020",
                        "created": new Date().toISOString(),
                        "proofPurpose": "assertionMethod",
                        "verificationMethod": "did:lemma:test#key-1",
                        "proofValue": "test-signature"
                    }
                };
                
                const stored = await window.lemmaWallet.storeCredential(testCredential);
                resultDiv.innerHTML = '<span class="success">✅ Credential stored successfully</span>';
                logResult('Credential Storage', 'success', `Stored credential: ${stored.id}`);
                
            } catch (error) {
                resultDiv.innerHTML = `<span class="error">❌ Failed: ${error.message}</span>`;
                logResult('Credential Storage', 'error', error.message);
            }
        }
        
        async function testLostCredentialFlow() {
            const resultDiv = document.getElementById('lost-result');
            try {
                await waitForWallet();
                
                const userId = 'test-user-lost';
                
                const originalCredential = {
                    "@context": ["https://www.w3.org/2018/credentials/v1"],
                    "type": ["VerifiableCredential", "LemmaHumanCredential"],
                    "id": `lost-credential-${Date.now()}`,
                    "issuer": "did:lemma:test",
                    "issuanceDate": new Date().toISOString(),
                    "credentialSubject": {
                        "id": `did:user:${userId}`,
                        "isHuman": true
                    },
                    "proof": {
                        "type": "Ed25519Signature2020",
                        "created": new Date().toISOString(),
                        "proofPurpose": "assertionMethod",
                        "verificationMethod": "did:lemma:test#key-1",
                        "proofValue": "test-signature"
                    }
                };
                
                await window.lemmaWallet.storeCredential(originalCredential);
                const backup = await window.lemmaWallet.exportCredentials(userId);
                await window.lemmaWallet.deleteCredential(originalCredential.id);
                
                const deleted = await window.lemmaWallet.getCredential(originalCredential.id);
                if (deleted) {
                    throw new Error('Credential was not properly deleted');
                }
                
                await window.lemmaWallet.importCredentials(backup);
                const restored = await window.lemmaWallet.getCredential(originalCredential.id);
                if (!restored) {
                    throw new Error('Failed to restore credential from backup');
                }
                
                resultDiv.innerHTML = '<span class="success">✅ Lost credential flow completed successfully</span>';
                logResult('Lost Credential Flow', 'success', 'Backup and restore working correctly');
                
            } catch (error) {
                resultDiv.innerHTML = `<span class="error">❌ Failed: ${error.message}</span>`;
                logResult('Lost Credential Flow', 'error', error.message);
            }
        }
        
        function waitForWallet(timeout = 5000) {
            return new Promise((resolve, reject) => {
                const startTime = Date.now();
                
                function checkWallet() {
                    if (window.lemmaWallet) {
                        resolve(window.lemmaWallet);
                    } else if (Date.now() - startTime > timeout) {
                        reject(new Error('Wallet initialization timeout'));
                    } else {
                        setTimeout(checkWallet, 100);
                    }
                }
                
                checkWallet();
            });
        }
        
        window.addEventListener('load', () => {
            setTimeout(testWalletInit, 1000);
        });
    </script>
</body>
</html>'''
    
    # Write the test file
    test_file = test_dir / "wallet_test.html"
    with open(test_file, "w", encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Created wallet test: {test_file}")
    return test_file

def create_test_runner():
    """Create a simple test runner."""
    
    test_dir = Path("wallet_tests")
    
    runner_content = '''#!/usr/bin/env python3
import webbrowser
import time
from pathlib import Path

def run_tests():
    print("🚀 Starting Lemma Wallet Test...")
    
    try:
        import requests
        response = requests.get("http://localhost:5000/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ Flask app is running")
        else:
            print("❌ Flask app is not responding correctly")
            return
    except:
        print("❌ Flask app is not running. Please start it with 'python app.py'")
        return
    
    test_file = Path("wallet_tests/wallet_test.html")
    
    if test_file.exists():
        print("🌐 Opening wallet test...")
        webbrowser.open(f"file://{test_file.absolute()}")
    else:
        print("❌ Test file not found")
    
    print("\\n📋 Test Instructions:")
    print("1. Test page will open in your browser")
    print("2. Click the test buttons to run wallet functionality tests")
    print("3. Check for green ✅ success messages and red ❌ error messages")

if __name__ == "__main__":
    run_tests()
'''
    
    runner_file = test_dir / "run_test.py"
    with open(runner_file, "w", encoding='utf-8') as f:
        f.write(runner_content)
    
    print(f"✅ Created test runner: {runner_file}")
    return runner_file

if __name__ == "__main__":
    print("🔧 Generating simple wallet test...")
    
    test_file = create_wallet_test()
    runner_file = create_test_runner()
    
    print(f"\\n🚀 To run the test:")
    print(f"   1. Make sure your Flask app is running: python app.py")
    print(f"   2. Run the test: python {runner_file}")
    print(f"\\n🎯 This will test:")
    print(f"   - Wallet initialization")
    print(f"   - Credential storage and retrieval")
    print(f"   - Lost credential recovery flow") 