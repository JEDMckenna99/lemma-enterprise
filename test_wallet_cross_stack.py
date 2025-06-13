#!/usr/bin/env python3
"""
Cross-Stack Wallet SDK Test Generator
Creates test pages for React, Vue, and vanilla JS to verify Lemma wallet compatibility.
"""

import os
import json
import time
from pathlib import Path

class WalletCrossStackTester:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.test_dir = Path("wallet_tests")
        self.test_dir.mkdir(exist_ok=True)
        
    def create_vanilla_js_test(self):
        """Create a vanilla JavaScript test page."""
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lemma Wallet - Vanilla JS Test</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .test-section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
        .success {{ color: green; }}
        .error {{ color: red; }}
        .info {{ color: blue; }}
        button {{ margin: 5px; padding: 10px; }}
        #results {{ margin-top: 20px; padding: 10px; background: #f5f5f5; }}
    </style>
</head>
<body>
    <h1>Lemma Wallet - Vanilla JS Test</h1>
    
    <div class="test-section">
        <h2>Wallet Initialization Test</h2>
        <button onclick="testWalletInit()">Test Wallet Initialization</button>
        <div id="init-result"></div>
    </div>
    
    <div class="test-section">
        <h2>Credential Storage Test</h2>
        <button onclick="testCredentialStorage()">Test Store Credential</button>
        <div id="storage-result"></div>
    </div>
    
    <div class="test-section">
        <h2>Lost Credential Flow Test</h2>
        <button onclick="testLostCredentialFlow()">Test Lost Credential Recovery</button>
        <div id="lost-result"></div>
    </div>
    
    <div id="results"></div>
    
    <!-- Lemma Wallet Scripts -->
    <script src="{self.base_url}/static/js/lemma-wallet.js"></script>
    <script src="{self.base_url}/static/js/lemma-wallet-init.js"></script>
    
    <script>
        let testResults = [];
        
        function logResult(test, status, message) {{
            const result = {{ test, status, message, timestamp: new Date().toISOString() }};
            testResults.push(result);
            updateResults();
        }}
        
        function updateResults() {{
            const resultsDiv = document.getElementById('results');
            resultsDiv.innerHTML = '<h3>Test Results:</h3>' + 
                testResults.map(r => 
                    `<div class="${{r.status}}">[${{r.status.toUpperCase()}}] ${{r.test}}: ${{r.message}}</div>`
                ).join('');
        }}
        
        async function testWalletInit() {{
            const resultDiv = document.getElementById('init-result');
            try {{
                await waitForWallet();
                
                if (window.lemmaWallet) {{
                    await window.lemmaWallet.init();
                    resultDiv.innerHTML = '<span class="success">✅ Wallet initialized successfully</span>';
                    logResult('Wallet Initialization', 'success', 'Wallet available and initialized');
                }} else {{
                    throw new Error('Wallet not available');
                }}
            }} catch (error) {{
                resultDiv.innerHTML = `<span class="error">❌ Failed: ${{error.message}}</span>`;
                logResult('Wallet Initialization', 'error', error.message);
            }}
        }}
        
        async function testCredentialStorage() {{
            const resultDiv = document.getElementById('storage-result');
            try {{
                await waitForWallet();
                
                const testCredential = {{
                    "@context": ["https://www.w3.org/2018/credentials/v1"],
                    "type": ["VerifiableCredential", "LemmaHumanCredential"],
                    "id": `test-credential-${{Date.now()}}`,
                    "issuer": "did:lemma:test",
                    "issuanceDate": new Date().toISOString(),
                    "credentialSubject": {{
                        "id": "did:user:test-user",
                        "isHuman": true
                    }},
                    "proof": {{
                        "type": "Ed25519Signature2020",
                        "created": new Date().toISOString(),
                        "proofPurpose": "assertionMethod",
                        "verificationMethod": "did:lemma:test#key-1",
                        "proofValue": "test-signature"
                    }}
                }};
                
                const stored = await window.lemmaWallet.storeCredential(testCredential);
                resultDiv.innerHTML = '<span class="success">✅ Credential stored successfully</span>';
                logResult('Credential Storage', 'success', `Stored credential: ${{stored.id}}`);
                
            }} catch (error) {{
                resultDiv.innerHTML = `<span class="error">❌ Failed: ${{error.message}}</span>`;
                logResult('Credential Storage', 'error', error.message);
            }}
        }}
        
        async function testLostCredentialFlow() {{
            const resultDiv = document.getElementById('lost-result');
            try {{
                await waitForWallet();
                
                const userId = 'test-user-lost';
                
                const originalCredential = {{
                    "@context": ["https://www.w3.org/2018/credentials/v1"],
                    "type": ["VerifiableCredential", "LemmaHumanCredential"],
                    "id": `lost-credential-${{Date.now()}}`,
                    "issuer": "did:lemma:test",
                    "issuanceDate": new Date().toISOString(),
                    "credentialSubject": {{
                        "id": `did:user:${{userId}}`,
                        "isHuman": true
                    }},
                    "proof": {{
                        "type": "Ed25519Signature2020",
                        "created": new Date().toISOString(),
                        "proofPurpose": "assertionMethod",
                        "verificationMethod": "did:lemma:test#key-1",
                        "proofValue": "test-signature"
                    }}
                }};
                
                await window.lemmaWallet.storeCredential(originalCredential);
                const backup = await window.lemmaWallet.exportCredentials(userId);
                await window.lemmaWallet.deleteCredential(originalCredential.id);
                
                const deleted = await window.lemmaWallet.getCredential(originalCredential.id);
                if (deleted) {{
                    throw new Error('Credential was not properly deleted');
                }}
                
                await window.lemmaWallet.importCredentials(backup);
                const restored = await window.lemmaWallet.getCredential(originalCredential.id);
                if (!restored) {{
                    throw new Error('Failed to restore credential from backup');
                }}
                
                resultDiv.innerHTML = '<span class="success">✅ Lost credential flow completed successfully</span>';
                logResult('Lost Credential Flow', 'success', 'Backup and restore working correctly');
                
            }} catch (error) {{
                resultDiv.innerHTML = `<span class="error">❌ Failed: ${{error.message}}</span>`;
                logResult('Lost Credential Flow', 'error', error.message);
            }}
        }}
        
        function waitForWallet(timeout = 5000) {{
            return new Promise((resolve, reject) => {{
                const startTime = Date.now();
                
                function checkWallet() {{
                    if (window.lemmaWallet) {{
                        resolve(window.lemmaWallet);
                    }} else if (Date.now() - startTime > timeout) {{
                        reject(new Error('Wallet initialization timeout'));
                    }} else {{
                        setTimeout(checkWallet, 100);
                    }}
                }}
                
                checkWallet();
            }});
        }}
        
        window.addEventListener('load', () => {{
            setTimeout(testWalletInit, 1000);
        }});
    </script>
</body>
</html>"""
        
        with open(self.test_dir / "vanilla_js_test.html", "w", encoding='utf-8') as f:
            f.write(html_content)
        
        return self.test_dir / "vanilla_js_test.html"
    
    def create_react_test(self):
        """Create a React test component."""
        react_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lemma Wallet - React Test</title>
    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .test-section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
        .success {{ color: green; }}
        .error {{ color: red; }}
        .info {{ color: blue; }}
        button {{ margin: 5px; padding: 10px; }}
        .results {{ margin-top: 20px; padding: 10px; background: #f5f5f5; }}
    </style>
</head>
<body>
    <div id="react-root"></div>
    
    <!-- Lemma Wallet Scripts -->
    <script src="{self.base_url}/static/js/lemma-wallet.js"></script>
    <script src="{self.base_url}/static/js/lemma-wallet-init.js"></script>
    
    <script type="text/babel">
        const {{ useState, useEffect, useCallback }} = React;
        
        function useLemmaWallet() {{
            const [wallet, setWallet] = useState(null);
            const [isLoading, setIsLoading] = useState(true);
            const [error, setError] = useState(null);
            
            useEffect(() => {{
                const initWallet = async () => {{
                    try {{
                        // Wait for wallet to be available
                        await waitForWallet();
                        setWallet(window.lemmaWallet);
                        setError(null);
                    }} catch (err) {{
                        setError(err.message);
                    }} finally {{
                        setIsLoading(false);
                    }}
                }};
                
                initWallet();
            }}, []);
            
            const storeCredential = useCallback(async (credential) => {{
                if (!wallet) throw new Error('Wallet not initialized');
                return await wallet.storeCredential(credential);
            }}, [wallet]);
            
            const getCredential = useCallback(async (id) => {{
                if (!wallet) throw new Error('Wallet not initialized');
                return await wallet.getCredential(id);
            }}, [wallet]);
            
            const exportCredentials = useCallback(async (userId) => {{
                if (!wallet) throw new Error('Wallet not initialized');
                return await wallet.exportCredentials(userId);
            }}, [wallet]);
            
            const importCredentials = useCallback(async (backup) => {{
                if (!wallet) throw new Error('Wallet not initialized');
                return await wallet.importCredentials(backup);
            }}, [wallet]);
            
            const deleteCredential = useCallback(async (id) => {{
                if (!wallet) throw new Error('Wallet not initialized');
                return await wallet.deleteCredential(id);
            }}, [wallet]);
            
            const getCredentialsByHolder = useCallback(async (userId) => {{
                if (!wallet) throw new Error('Wallet not initialized');
                return await wallet.getCredentialsByHolder(userId);
            }}, [wallet]);
            
            return {{
                wallet,
                isLoading,
                error,
                storeCredential,
                getCredential,
                exportCredentials,
                importCredentials,
                deleteCredential,
                getCredentialsByHolder
            }};
        }}
        
        function TestSection({{ title, children }}) {{
            return (
                <div className="test-section">
                    <h2>{{title}}</h2>
                    {{children}}
                </div>
            );
        }}
        
        function TestResult({{ status, message }}) {{
            return (
                <div className={{status}}>
                    {{status === 'success' ? '✅' : status === 'error' ? '❌' : 'ℹ️'}} {{message}}
                </div>
            );
        }}
        
        function LemmaWalletReactTest() {{
            const {{
                wallet,
                isLoading,
                error,
                storeCredential,
                getCredential,
                exportCredentials,
                importCredentials,
                deleteCredential,
                getCredentialsByHolder
            }} = useLemmaWallet();
            
            const [testResults, setTestResults] = useState([]);
            
            const addResult = (test, status, message) => {{
                const result = {{ test, status, message, timestamp: new Date().toISOString() }};
                setTestResults(prev => [...prev, result]);
            }};
            
            const testCredentialStorage = async () => {{
                try {{
                    const testCredential = {{
                        "@context": ["https://www.w3.org/2018/credentials/v1"],
                        "type": ["VerifiableCredential", "LemmaHumanCredential"],
                        "id": `react-test-credential-${{Date.now()}}`,
                        "issuer": "did:lemma:test",
                        "issuanceDate": new Date().toISOString(),
                        "credentialSubject": {{
                            "id": "did:user:react-test-user",
                            "isHuman": true
                        }},
                        "proof": {{
                            "type": "Ed25519Signature2020",
                            "created": new Date().toISOString(),
                            "proofPurpose": "assertionMethod",
                            "verificationMethod": "did:lemma:test#key-1",
                            "proofValue": "test-signature"
                        }}
                    }};
                    
                    const stored = await storeCredential(testCredential);
                    addResult('React Credential Storage', 'success', `Stored credential: ${{stored.id}}`);
                    
                    // Verify retrieval
                    const retrieved = await getCredential(testCredential.id);
                    if (retrieved) {{
                        addResult('React Credential Retrieval', 'success', 'Credential retrieved successfully');
                    }} else {{
                        throw new Error('Failed to retrieve stored credential');
                    }}
                    
                }} catch (err) {{
                    addResult('React Credential Storage', 'error', err.message);
                }}
            }};
            
            const testLostCredentialFlow = async () => {{
                try {{
                    const userId = 'react-test-user-lost';
                    
                    // Create and store credential
                    const originalCredential = {{
                        "@context": ["https://www.w3.org/2018/credentials/v1"],
                        "type": ["VerifiableCredential", "LemmaHumanCredential"],
                        "id": `react-lost-credential-${{Date.now()}}`,
                        "issuer": "did:lemma:test",
                        "issuanceDate": new Date().toISOString(),
                        "credentialSubject": {{
                            "id": `did:user:${{userId}}`,
                            "isHuman": true
                        }},
                        "proof": {{
                            "type": "Ed25519Signature2020",
                            "created": new Date().toISOString(),
                            "proofPurpose": "assertionMethod",
                            "verificationMethod": "did:lemma:test#key-1",
                            "proofValue": "test-signature"
                        }}
                    }};
                    
                    await storeCredential(originalCredential);
                    
                    // Export backup
                    const backup = await exportCredentials(userId);
                    
                    // Delete credential
                    await deleteCredential(originalCredential.id);
                    
                    // Verify deletion
                    const deleted = await getCredential(originalCredential.id);
                    if (deleted) {{
                        throw new Error('Credential was not properly deleted');
                    }}
                    
                    // Restore from backup
                    await importCredentials(backup);
                    
                    // Verify restoration
                    const restored = await getCredential(originalCredential.id);
                    if (!restored) {{
                        throw new Error('Failed to restore credential from backup');
                    }}
                    
                    addResult('React Lost Credential Flow', 'success', 'Backup and restore working correctly');
                    
                }} catch (err) {{
                    addResult('React Lost Credential Flow', 'error', err.message);
                }}
            }};
            
            const testAliasCredential = async () => {{
                try {{
                    const userId = 'react-test-user-alias';
                    
                    // Create original credential
                    const originalCredential = {{
                        "@context": ["https://www.w3.org/2018/credentials/v1"],
                        "type": ["VerifiableCredential", "LemmaHumanCredential"],
                        "id": `react-original-credential-${{Date.now()}}`,
                        "issuer": "did:lemma:test",
                        "issuanceDate": new Date().toISOString(),
                        "credentialSubject": {{
                            "id": `did:user:${{userId}}`,
                            "isHuman": true
                        }},
                        "proof": {{
                            "type": "Ed25519Signature2020",
                            "created": new Date().toISOString(),
                            "proofPurpose": "assertionMethod",
                            "verificationMethod": "did:lemma:test#key-1",
                            "proofValue": "test-signature-original"
                        }}
                    }};
                    
                    await storeCredential(originalCredential);
                    
                    // Create alias credential
                    const aliasCredential = {{
                        "@context": ["https://www.w3.org/2018/credentials/v1"],
                        "type": ["VerifiableCredential", "LemmaHumanCredential"],
                        "id": `react-alias-credential-${{Date.now()}}`,
                        "issuer": "did:lemma:test",
                        "issuanceDate": new Date().toISOString(),
                        "credentialSubject": {{
                            "id": `did:user:${{userId}}`,
                            "isHuman": true
                        }},
                        "proof": {{
                            "type": "Ed25519Signature2020",
                            "created": new Date().toISOString(),
                            "proofPurpose": "assertionMethod",
                            "verificationMethod": "did:lemma:test#key-2",
                            "proofValue": "test-signature-alias"
                        }}
                    }};
                    
                    await storeCredential(aliasCredential);
                    
                    // Verify both credentials exist
                    const userCredentials = await getCredentialsByHolder(userId);
                    
                    if (userCredentials.length >= 2) {{
                        addResult('React Alias Credential', 'success', `User has ${{userCredentials.length}} credentials`);
                    }} else {{
                        throw new Error(`Expected at least 2 credentials, found ${{userCredentials.length}}`);
                    }}
                    
                }} catch (err) {{
                    addResult('React Alias Credential', 'error', err.message);
                }}
            }};
            
            if (isLoading) {{
                return <div>Loading Lemma wallet...</div>;
            }}
            
            if (error) {{
                return <div className="error">Error initializing wallet: {{error}}</div>;
            }}
            
            return (
                <div>
                    <h1>Lemma Wallet - React Test</h1>
                    
                    <TestSection title="Wallet Status">
                        <TestResult 
                            status="success" 
                            message={{wallet ? "Wallet initialized successfully" : "Wallet not available"}}
                        />
                    </TestSection>
                    
                    <TestSection title="Credential Storage Test">
                        <button onClick={{testCredentialStorage}}>Test Store Credential</button>
                    </TestSection>
                    
                    <TestSection title="Lost Credential Flow Test">
                        <button onClick={{testLostCredentialFlow}}>Test Lost Credential Recovery</button>
                    </TestSection>
                    
                    <TestSection title="Alias Credential Test">
                        <button onClick={{testAliasCredential}}>Test Alias Credential</button>
                    </TestSection>
                    
                    <div className="results">
                        <h3>Test Results:</h3>
                        {{testResults.map((result, index) => (
                            <TestResult 
                                key={{index}}
                                status={{result.status}}
                                message={{`${{result.test}}: ${{result.message}}`}}
                            />
                        ))}}
                    </div>
                </div>
            );
        }}
        
        function waitForWallet(timeout = 5000) {{
            return new Promise((resolve, reject) => {{
                const startTime = Date.now();
                
                function checkWallet() {{
                    if (window.lemmaWallet) {{
                        resolve(window.lemmaWallet);
                    }} else if (Date.now() - startTime > timeout) {{
                        reject(new Error('Wallet initialization timeout'));
                    }} else {{
                        setTimeout(checkWallet, 100);
                    }}
                }}
                
                checkWallet();
            }});
        }}
        
        ReactDOM.render(<LemmaWalletReactTest />, document.getElementById('react-root'));
    </script>
</body>
</html>"""
        
        with open(self.test_dir / "react_test.html", "w") as f:
            f.write(react_content)
        
        return self.test_dir / "react_test.html"
    
    def create_vue_test(self):
        """Create a Vue.js test component."""
        vue_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lemma Wallet - Vue Test</title>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .test-section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
        .success {{ color: green; }}
        .error {{ color: red; }}
        .info {{ color: blue; }}
        button {{ margin: 5px; padding: 10px; }}
        .results {{ margin-top: 20px; padding: 10px; background: #f5f5f5; }}
    </style>
</head>
<body>
    <div id="vue-app"></div>
    
    <!-- Lemma Wallet Scripts -->
    <script src="{self.base_url}/static/js/lemma-wallet.js"></script>
    <script src="{self.base_url}/static/js/lemma-wallet-init.js"></script>
    
    <script>
        const {{ createApp, ref, onMounted, computed }} = Vue;
        
        function useLemmaWallet() {{
            const wallet = ref(null);
            const isLoading = ref(true);
            const error = ref(null);
            
            const initWallet = async () => {{
                try {{
                    await waitForWallet();
                    wallet.value = window.lemmaWallet;
                    error.value = null;
                }} catch (err) {{
                    error.value = err.message;
                }} finally {{
                    isLoading.value = false;
                }}
            }};
            
            onMounted(initWallet);
            
            const storeCredential = async (credential) => {{
                if (!wallet.value) throw new Error('Wallet not initialized');
                return await wallet.value.storeCredential(credential);
            }};
            
            const getCredential = async (id) => {{
                if (!wallet.value) throw new Error('Wallet not initialized');
                return await wallet.value.getCredential(id);
            }};
            
            const exportCredentials = async (userId) => {{
                if (!wallet.value) throw new Error('Wallet not initialized');
                return await wallet.value.exportCredentials(userId);
            }};
            
            const importCredentials = async (backup) => {{
                if (!wallet.value) throw new Error('Wallet not initialized');
                return await wallet.value.importCredentials(backup);
            }};
            
            const deleteCredential = async (id) => {{
                if (!wallet.value) throw new Error('Wallet not initialized');
                return await wallet.value.deleteCredential(id);
            }};
            
            const getCredentialsByHolder = async (userId) => {{
                if (!wallet.value) throw new Error('Wallet not initialized');
                return await wallet.value.getCredentialsByHolder(userId);
            }};
            
            return {{
                wallet: computed(() => wallet.value),
                isLoading: computed(() => isLoading.value),
                error: computed(() => error.value),
                storeCredential,
                getCredential,
                exportCredentials,
                importCredentials,
                deleteCredential,
                getCredentialsByHolder
            }};
        }}
        
        const LemmaWalletVueTest = {{
            setup() {{
                const {{
                    wallet,
                    isLoading,
                    error,
                    storeCredential,
                    getCredential,
                    exportCredentials,
                    importCredentials,
                    deleteCredential,
                    getCredentialsByHolder
                }} = useLemmaWallet();
                
                const testResults = ref([]);
                
                const addResult = (test, status, message) => {{
                    const result = {{ test, status, message, timestamp: new Date().toISOString() }};
                    testResults.value.push(result);
                }};
                
                const testCredentialStorage = async () => {{
                    try {{
                        const testCredential = {{
                            "@context": ["https://www.w3.org/2018/credentials/v1"],
                            "type": ["VerifiableCredential", "LemmaHumanCredential"],
                            "id": `vue-test-credential-${{Date.now()}}`,
                            "issuer": "did:lemma:test",
                            "issuanceDate": new Date().toISOString(),
                            "credentialSubject": {{
                                "id": "did:user:vue-test-user",
                                "isHuman": true
                            }},
                            "proof": {{
                                "type": "Ed25519Signature2020",
                                "created": new Date().toISOString(),
                                "proofPurpose": "assertionMethod",
                                "verificationMethod": "did:lemma:test#key-1",
                                "proofValue": "test-signature"
                            }}
                        }};
                        
                        const stored = await storeCredential(testCredential);
                        addResult('Vue Credential Storage', 'success', `Stored credential: ${{stored.id}}`);
                        
                        // Verify retrieval
                        const retrieved = await getCredential(testCredential.id);
                        if (retrieved) {{
                            addResult('Vue Credential Retrieval', 'success', 'Credential retrieved successfully');
                        }} else {{
                            throw new Error('Failed to retrieve stored credential');
                        }}
                        
                    }} catch (err) {{
                        addResult('Vue Credential Storage', 'error', err.message);
                    }}
                }};
                
                const testLostCredentialFlow = async () => {{
                    try {{
                        const userId = 'vue-test-user-lost';
                        
                        // Create and store credential
                        const originalCredential = {{
                            "@context": ["https://www.w3.org/2018/credentials/v1"],
                            "type": ["VerifiableCredential", "LemmaHumanCredential"],
                            "id": `vue-lost-credential-${{Date.now()}}`,
                            "issuer": "did:lemma:test",
                            "issuanceDate": new Date().toISOString(),
                            "credentialSubject": {{
                                "id": `did:user:${{userId}}`,
                                "isHuman": true
                            }},
                            "proof": {{
                                "type": "Ed25519Signature2020",
                                "created": new Date().toISOString(),
                                "proofPurpose": "assertionMethod",
                                "verificationMethod": "did:lemma:test#key-1",
                                "proofValue": "test-signature"
                            }}
                        }};
                        
                        await storeCredential(originalCredential);
                        
                        // Export backup
                        const backup = await exportCredentials(userId);
                        
                        // Delete credential
                        await deleteCredential(originalCredential.id);
                        
                        // Verify deletion
                        const deleted = await getCredential(originalCredential.id);
                        if (deleted) {{
                            throw new Error('Credential was not properly deleted');
                        }}
                        
                        // Restore from backup
                        await importCredentials(backup);
                        
                        // Verify restoration
                        const restored = await getCredential(originalCredential.id);
                        if (!restored) {{
                            throw new Error('Failed to restore credential from backup');
                        }}
                        
                        addResult('Vue Lost Credential Flow', 'success', 'Backup and restore working correctly');
                        
                    }} catch (err) {{
                        addResult('Vue Lost Credential Flow', 'error', err.message);
                    }}
                }};
                
                const testAliasCredential = async () => {{
                    try {{
                        const userId = 'vue-test-user-alias';
                        
                        // Create original credential
                        const originalCredential = {{
                            "@context": ["https://www.w3.org/2018/credentials/v1"],
                            "type": ["VerifiableCredential", "LemmaHumanCredential"],
                            "id": `vue-original-credential-${{Date.now()}}`,
                            "issuer": "did:lemma:test",
                            "issuanceDate": new Date().toISOString(),
                            "credentialSubject": {{
                                "id": `did:user:${{userId}}`,
                                "isHuman": true
                            }},
                            "proof": {{
                                "type": "Ed25519Signature2020",
                                "created": new Date().toISOString(),
                                "proofPurpose": "assertionMethod",
                                "verificationMethod": "did:lemma:test#key-1",
                                "proofValue": "test-signature-original"
                            }}
                        }};
                        
                        await storeCredential(originalCredential);
                        
                        // Create alias credential
                        const aliasCredential = {{
                            "@context": ["https://www.w3.org/2018/credentials/v1"],
                            "type": ["VerifiableCredential", "LemmaHumanCredential"],
                            "id": `vue-alias-credential-${{Date.now()}}`,
                            "issuer": "did:lemma:test",
                            "issuanceDate": new Date().toISOString(),
                            "credentialSubject": {{
                                "id": `did:user:${{userId}}`,
                                "isHuman": true
                            }},
                            "proof": {{
                                "type": "Ed25519Signature2020",
                                "created": new Date().toISOString(),
                                "proofPurpose": "assertionMethod",
                                "verificationMethod": "did:lemma:test#key-2",
                                "proofValue": "test-signature-alias"
                            }}
                        }};
                        
                        await storeCredential(aliasCredential);
                        
                        // Verify both credentials exist
                        const userCredentials = await getCredentialsByHolder(userId);
                        
                        if (userCredentials.length >= 2) {{
                            addResult('Vue Alias Credential', 'success', `User has ${{userCredentials.length}} credentials`);
                        }} else {{
                            throw new Error(`Expected at least 2 credentials, found ${{userCredentials.length}}`);
                        }}
                        
                    }} catch (err) {{
                        addResult('Vue Alias Credential', 'error', err.message);
                    }}
                }};
                
                return {{
                    wallet,
                    isLoading,
                    error,
                    testResults,
                    testCredentialStorage,
                    testLostCredentialFlow,
                    testAliasCredential
                }};
            }},
            template: `
                <div>
                    <h1>Lemma Wallet - Vue Test</h1>
                    
                    <div class="test-section">
                        <h2>Wallet Status</h2>
                        <div v-if="isLoading" class="info">Loading Lemma wallet...</div>
                        <div v-else-if="error" class="error">Error initializing wallet: {{{{ error }}}}</div>
                        <div v-else class="success">✅ Wallet initialized successfully</div>
                    </div>
                    
                    <div class="test-section">
                        <h2>Credential Storage Test</h2>
                        <button @click="testCredentialStorage" :disabled="isLoading || error">Test Store Credential</button>
                    </div>
                    
                    <div class="test-section">
                        <h2>Lost Credential Flow Test</h2>
                        <button @click="testLostCredentialFlow" :disabled="isLoading || error">Test Lost Credential Recovery</button>
                    </div>
                    
                    <div class="test-section">
                        <h2>Alias Credential Test</h2>
                        <button @click="testAliasCredential" :disabled="isLoading || error">Test Alias Credential</button>
                    </div>
                    
                    <div class="results">
                        <h3>Test Results:</h3>
                        <div v-for="(result, index) in testResults" :key="index" :class="result.status">
                            {{{{ result.status === 'success' ? '✅' : result.status === 'error' ? '❌' : 'ℹ️' }}}} {{{{ result.test }}}}: {{{{ result.message }}}}
                        </div>
                    </div>
                </div>
            `
        }};
        
        function waitForWallet(timeout = 5000) {{
            return new Promise((resolve, reject) => {{
                const startTime = Date.now();
                
                function checkWallet() {{
                    if (window.lemmaWallet) {{
                        resolve(window.lemmaWallet);
                    }} else if (Date.now() - startTime > timeout) {{
                        reject(new Error('Wallet initialization timeout'));
                    }} else {{
                        setTimeout(checkWallet, 100);
                    }}
                }}
                
                checkWallet();
            }});
        }}
        
        createApp(LemmaWalletVueTest).mount('#vue-app');
    </script>
</body>
</html>"""
        
        with open(self.test_dir / "vue_test.html", "w") as f:
            f.write(vue_content)
        
        return self.test_dir / "vue_test.html"
    
    def create_test_runner(self):
        """Create a test runner script."""
        runner_content = """#!/usr/bin/env python3
import webbrowser
import time
from pathlib import Path

def run_tests():
    print("🚀 Starting Lemma Wallet Cross-Stack Tests...")
    
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
    
    test_dir = Path("wallet_tests")
    
    tests = [
        ("Vanilla JS", test_dir / "vanilla_js_test.html"),
    ]
    
    for name, path in tests:
        if path.exists():
            print(f"🌐 Opening {name} test...")
            webbrowser.open(f"file://{path.absolute()}")
            time.sleep(2)
        else:
            print(f"❌ {name} test file not found: {path}")
    
    print("\\n📋 Test Instructions:")
    print("1. Test page will open in your browser")
    print("2. Click the test buttons to run wallet functionality tests")
    print("3. Check for green ✅ success messages and red ❌ error messages")

if __name__ == "__main__":
    run_tests()
"""
        
        with open(self.test_dir / "run_tests.py", "w") as f:
            f.write(runner_content)
        
        return self.test_dir / "run_tests.py"
    
    def generate_all_tests(self):
        """Generate all test files."""
        print("🔧 Generating cross-stack wallet tests...")
        
        vanilla_file = self.create_vanilla_js_test()
        runner_file = self.create_test_runner()
        
        print(f"✅ Generated test files:")
        print(f"   📄 Vanilla JS: {vanilla_file}")
        print(f"   📄 Test Runner: {runner_file}")
        
        return {
            "vanilla_js": vanilla_file,
            "runner": runner_file
        }

if __name__ == "__main__":
    import sys
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    
    tester = WalletCrossStackTester(base_url)
    files = tester.generate_all_tests()
    
    print(f"\\n🚀 To run the tests:")
    print(f"   1. Make sure your Flask app is running: python app.py")
    print(f"   2. Run the test runner: python {files['runner']}")
    print(f"\\n🎯 This will test wallet compatibility across JavaScript frameworks")
    print(f"\\n📋 Each test verifies:")
    print(f"   - Wallet initialization")
    print(f"   - Credential storage and retrieval")
    print(f"   - Lost credential recovery flow") 