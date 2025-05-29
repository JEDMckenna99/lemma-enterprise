/**
 * Lemma Reference Integration
 * 
 * This file demonstrates the EXACT integration pattern that any external site
 * should use with Lemma. The main Lemma site uses this same approach,
 * serving as a perfect reference implementation.
 * 
 * Key Principles:
 * - Uses ONLY public APIs (no internal shortcuts)
 * - Same wallet storage as any integrated site would use
 * - Same authentication flows as external integrations
 * - Same error handling and user experience patterns
 */

class LemmaReferenceIntegration {
    constructor(options = {}) {
        this.apiBaseUrl = options.apiBaseUrl || '';
        this.apiKey = options.apiKey || null; // For sites that have API keys
        this.wallet = null;
        this.initialized = false;
        
        // Security settings
        this.requireHTTPS = options.requireHTTPS !== false;
        this.enableCSRF = options.enableCSRF !== false;
        
        // UI settings
        this.showDebugInfo = options.showDebugInfo === true;
        this.autoHideMessages = options.autoHideMessages !== false;
        
        console.log('[LEMMA REFERENCE] Initializing reference integration...');
        
        // Don't auto-initialize in constructor to allow for proper async handling
        this.initPromise = null;
    }
    
    async init() {
        // Return existing promise if already initializing
        if (this.initPromise) {
            return this.initPromise;
        }
        
        // Create initialization promise
        this.initPromise = this._performInit();
        return this.initPromise;
    }
    
    async _performInit() {
        try {
            // Wait for LemmaWallet to be available with retry logic
            await this.waitForLemmaWallet();
            
            // Initialize wallet (same as any external site would)
            this.wallet = new LemmaWallet();
            await this.wallet.init();
            console.log('[LEMMA REFERENCE] Wallet initialized successfully');
            
            // Check HTTPS requirement
            if (this.requireHTTPS && window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') {
                console.warn('[LEMMA REFERENCE] HTTPS required for production use');
            }
            
            this.initialized = true;
            console.log('[LEMMA REFERENCE] Reference integration ready');
            
        } catch (error) {
            console.error('[LEMMA REFERENCE] Initialization failed:', error);
            this.initialized = false;
            throw error;
        }
    }
    
    /**
     * Wait for LemmaWallet to be available with retry logic
     */
    async waitForLemmaWallet(maxAttempts = 20, delayMs = 100) {
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            // Check if LemmaWallet class is available
            if (window.LemmaWallet && typeof window.LemmaWallet === 'function') {
                console.log('[LEMMA REFERENCE] LemmaWallet class found on attempt', attempt);
                return;
            }
            
            console.log(`[LEMMA REFERENCE] Waiting for LemmaWallet class (attempt ${attempt}/${maxAttempts})... Current: ${typeof window.LemmaWallet}`);
            await new Promise(resolve => setTimeout(resolve, delayMs));
        }
        
        // More detailed error message for debugging
        const availableGlobals = Object.keys(window).filter(key => key.toLowerCase().includes('lemma'));
        console.error('[LEMMA REFERENCE] Available Lemma-related globals:', availableGlobals);
        
        throw new Error(`LemmaWallet class not available after waiting ${maxAttempts * delayMs}ms - ensure lemma-wallet.js is loaded before lemma-reference-integration.js`);
    }
    
    /**
     * Check if user has valid Lemma credentials
     * Uses the same method any external site would use
     */
    async hasValidCredentials() {
        if (!this.initialized) {
            try {
                await this.init();
            } catch (error) {
                console.error('[LEMMA REFERENCE] Failed to initialize during hasValidCredentials:', error);
                return false;
            }
        }
        
        try {
            const credentials = await this.wallet.getAllCredentials();
            
            if (!credentials || credentials.length === 0) {
                console.log('[LEMMA REFERENCE] No credentials found in wallet');
                return false;
            }
            
            // Check if any credential is valid and not expired
            for (const cred of credentials) {
                if (await this.isCredentialValid(cred)) {
                    console.log('[LEMMA REFERENCE] Found valid credential:', cred.id);
                    return true;
                }
            }
            
            console.log('[LEMMA REFERENCE] No valid credentials found');
            return false;
            
        } catch (error) {
            console.error('[LEMMA REFERENCE] Error checking credentials:', error);
            return false;
        }
    }
    
    /**
     * Verify a credential using the public API
     * Same method any external site would use
     */
    async isCredentialValid(walletCredential) {
        try {
            const credential = walletCredential.credential;
            
            // Check expiration first (client-side optimization)
            if (credential.expirationDate) {
                const expiry = new Date(credential.expirationDate);
                if (expiry < new Date()) {
                    console.log('[LEMMA REFERENCE] Credential expired:', credential.id);
                    return false;
                }
            }
            
            // Verify using public API
            const response = await this.makeAPICall('/api/verify-credential', {
                method: 'POST',
                body: JSON.stringify({ credential: credential }),
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (response.ok && result.valid) {
                console.log('[LEMMA REFERENCE] Credential verified via API:', credential.id);
                return true;
            } else {
                console.log('[LEMMA REFERENCE] Credential verification failed:', result.reason || 'Unknown error');
                return false;
            }
            
        } catch (error) {
            console.error('[LEMMA REFERENCE] Error verifying credential:', error);
            return false;
        }
    }
    
    /**
     * Perform complete verification flow using public APIs only
     * This is the exact flow any external site would implement
     */
    async performVerification(options = {}) {
        if (!this.initialized) {
            try {
                await this.init();
            } catch (error) {
                console.error('[LEMMA REFERENCE] Failed to initialize during performVerification:', error);
                if (options.onError) {
                    options.onError(error);
                }
                return { success: false, error: error.message };
            }
        }
        
        try {
            console.log('[LEMMA REFERENCE] Starting verification flow...');
            
            // Step 1: Check if already verified
            if (await this.hasValidCredentials()) {
                console.log('[LEMMA REFERENCE] User already has valid credentials');
                if (options.onSuccess) {
                    options.onSuccess({ 
                        status: 'already_verified',
                        message: 'User already has valid Lemma credentials'
                    });
                }
                return { success: true, status: 'already_verified' };
            }
            
            // Step 2: Generate challenge for verification
            const challengeResponse = await this.makeAPICall('/api/generate-challenge');
            const challengeData = await challengeResponse.json();
            
            if (!challengeResponse.ok || !challengeData.success) {
                throw new Error('Failed to generate verification challenge');
            }
            
            console.log('[LEMMA REFERENCE] Challenge generated:', challengeData.challenge);
            
            // Step 3: Check if user has credentials that need presentation
            const credentials = await this.wallet.getAllCredentials();
            
            if (credentials && credentials.length > 0) {
                // Create and verify presentation
                return await this.createAndVerifyPresentation(credentials[0], challengeData.challenge, options);
            } else {
                // Redirect to verification (like any external site would)
                return await this.redirectToVerification(options);
            }
            
        } catch (error) {
            console.error('[LEMMA REFERENCE] Verification flow failed:', error);
            if (options.onError) {
                options.onError(error);
            }
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Create and verify presentation using public APIs
     * Same method any external site would use
     */
    async createAndVerifyPresentation(walletCredential, challenge, options = {}) {
        try {
            // Create presentation (this would typically be done by wallet)
            const presentation = {
                "@context": ["https://www.w3.org/2018/credentials/v1"],
                "type": ["VerifiablePresentation"],
                "verifiableCredential": [walletCredential.credential],
                "proof": {
                    "type": "Ed25519Signature2020",
                    "challenge": challenge,
                    "created": new Date().toISOString(),
                    "proofPurpose": "authentication"
                }
            };
            
            // Verify presentation using public API
            const response = await this.makeAPICall('/api/verify-presentation', {
                method: 'POST',
                body: JSON.stringify({
                    presentation: presentation,
                    challenge: challenge
                }),
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (response.ok && result.success && result.valid) {
                console.log('[LEMMA REFERENCE] Presentation verified successfully');
                
                if (options.onSuccess) {
                    options.onSuccess({
                        status: 'verified',
                        holder: result.holder,
                        credentials: result.credentials
                    });
                }
                
                return { success: true, status: 'verified', result: result };
            } else {
                throw new Error(result.reason || 'Presentation verification failed');
            }
            
        } catch (error) {
            console.error('[LEMMA REFERENCE] Presentation verification failed:', error);
            
            if (options.onError) {
                options.onError(error);
            }
            
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Redirect to verification page
     * Same method any external site would use
     */
    async redirectToVerification(options = {}) {
        console.log('[LEMMA REFERENCE] Redirecting to verification page...');
        
        // Store return URL for after verification
        if (options.returnUrl) {
            sessionStorage.setItem('lemma_return_url', options.returnUrl);
        }
        
        // Generate user ID for verification
        const userId = 'user_' + Array.from(crypto.getRandomValues(new Uint8Array(16)))
            .map(b => b.toString(16).padStart(2, '0')).join('').substring(0, 16);
        
        // Redirect to verification start page
        window.location.href = `/verification-start/${userId}`;
        
        return { success: true, status: 'redirected_to_verification' };
    }
    
    /**
     * Handle post-verification callback
     * Processes the credential after successful verification
     */
    async handleVerificationCallback(urlParams, options = {}) {
        try {
            const userId = urlParams.get('user_id');
            const verificationSuccess = urlParams.get('verification_success');
            const sessionId = urlParams.get('session_id');
            
            if (!userId || verificationSuccess !== 'true' || !sessionId) {
                console.log('[LEMMA REFERENCE] Invalid verification callback parameters');
                return { success: false, error: 'Invalid callback parameters' };
            }
            
            console.log('[LEMMA REFERENCE] Processing verification callback...');
            
            // Get CSRF token for secure API call
            const csrfResponse = await this.makeAPICall('/api/generate-csrf-token');
            const csrfData = await csrfResponse.json();
            
            // Complete verification flow using public API
            const response = await this.makeAPICall('/api/complete-verification-flow', {
                method: 'POST',
                body: JSON.stringify({
                    user_id: userId,
                    stripe_session_id: sessionId
                }),
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfData.csrf_token
                }
            });
            
            const result = await response.json();
            console.log('[LEMMA REFERENCE] Complete verification flow result:', result);
            
            if (response.ok && result.status === 'verified' && result.store_credential) {
                console.log('[LEMMA REFERENCE] Storing credential in wallet...');
                
                // Store credential in wallet (same as any external site)
                await this.wallet.storeCredential(result.store_credential);
                console.log('[LEMMA REFERENCE] Credential stored successfully');
                
                // Show success message
                this.showMessage('✅ Verification complete! Your Lemma credential has been stored.', 'success');
                
                // Check if we should stay on current page or redirect
                if (options.stayOnCurrentPage) {
                    console.log('[LEMMA REFERENCE] Staying on current page after verification');
                    return { success: true, status: 'credential_stored', shouldStay: true };
                } else {
                    // Redirect to return URL or protected content
                    const returnUrl = sessionStorage.getItem('lemma_return_url') || '/protected';
                    sessionStorage.removeItem('lemma_return_url');
                    
                    console.log('[LEMMA REFERENCE] Redirecting to:', returnUrl);
                    setTimeout(() => {
                        window.location.href = returnUrl;
                    }, 2000);
                    
                    return { success: true, status: 'credential_stored', redirect: returnUrl };
                }
                
            } else {
                console.error('[LEMMA REFERENCE] Verification failed:', result);
                throw new Error(result.error || 'Verification failed');
            }
            
        } catch (error) {
            console.error('[LEMMA REFERENCE] Verification callback failed:', error);
            this.showMessage(`❌ Verification failed: ${error.message}`, 'error');
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Protect a page or element (same as external sites would use)
     */
    async protectElement(element, options = {}) {
        try {
            console.log('[LEMMA REFERENCE] Protecting element with Lemma verification...');
            
            // Initialize if not already done
            if (!this.initialized) {
                console.log('[LEMMA REFERENCE] Initializing during protectElement...');
                
                const loadingDiv = document.createElement('div');
                loadingDiv.className = 'lemma-loading';
                loadingDiv.innerHTML = `
                    <div style="
                        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                        padding: 30px;
                        border-radius: 10px;
                        text-align: center;
                        margin: 20px 0;
                        border: 2px solid #dee2e6;
                    ">
                        <h3>🔄 Initializing Lemma...</h3>
                        <p style="margin: 10px 0;">Setting up human verification system...</p>
                    </div>
                `;
                
                // Insert loading state
                element.parentNode.insertBefore(loadingDiv, element);
                element.style.display = 'none';
                
                try {
                    await this.init();
                    // Remove loading state after successful initialization
                    loadingDiv.remove();
                } catch (error) {
                    console.error('[LEMMA REFERENCE] Failed to initialize during protectElement:', error);
                    
                    // Show error state
                    loadingDiv.innerHTML = `
                        <div style="
                            background: #f8d7da;
                            color: #721c24;
                            border: 1px solid #f5c6cb;
                            padding: 20px;
                            border-radius: 10px;
                            text-align: center;
                            margin: 20px 0;
                        ">
                            <h3>⚠️ Initialization Failed</h3>
                            <p style="margin: 10px 0;">Unable to initialize Lemma integration</p>
                            <button onclick="window.location.reload()" style="
                                background: #dc3545;
                                color: white;
                                border: none;
                                padding: 8px 16px;
                                border-radius: 4px;
                                cursor: pointer;
                                margin-top: 10px;
                            ">🔄 Refresh Page</button>
                        </div>
                    `;
                    
                    if (options.onError) {
                        options.onError(error);
                    }
                    return;
                }
            }
            
            const hasValid = await this.hasValidCredentials();
            
            if (hasValid) {
                // Show protected content
                element.style.display = '';
                if (options.onSuccess) {
                    options.onSuccess();
                }
                console.log('[LEMMA REFERENCE] Access granted to protected element');
            } else {
                // Hide content
                element.style.display = 'none';
                
                // Check if custom verification UI is disabled
                if (options.showDefaultVerificationUI === false) {
                    // Use custom verification required callback
                    if (options.onVerificationRequired) {
                        console.log('[LEMMA REFERENCE] Using custom verification UI');
                        options.onVerificationRequired();
                    } else {
                        console.log('[LEMMA REFERENCE] Custom verification UI disabled but no onVerificationRequired callback provided');
                        if (options.onError) {
                            options.onError(new Error('Custom verification UI disabled but no onVerificationRequired callback provided'));
                        }
                    }
                } else {
                    // Show default verification prompt
                    const promptDiv = document.createElement('div');
                    promptDiv.className = 'lemma-verification-prompt';
                    promptDiv.innerHTML = `
                        <div style="
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            padding: 30px;
                            border-radius: 10px;
                            text-align: center;
                            margin: 20px 0;
                        ">
                            <h3>🔒 Human Verification Required</h3>
                            <p style="margin: 15px 0;">This content requires Lemma human verification.</p>
                            <button id="verifyButton" style="
                                background: #28a745;
                                color: white;
                                border: none;
                                padding: 12px 24px;
                                border-radius: 6px;
                                font-size: 16px;
                                font-weight: 600;
                                cursor: pointer;
                                margin-top: 10px;
                            ">🚀 Verify with Lemma</button>
                        </div>
                    `;
                    
                    element.parentNode.insertBefore(promptDiv, element);
                    
                    // Add click handler
                    promptDiv.querySelector('#verifyButton').addEventListener('click', () => {
                        this.performVerification({
                            returnUrl: window.location.href,
                            onSuccess: () => {
                                promptDiv.remove();
                                element.style.display = '';
                                if (options.onSuccess) options.onSuccess();
                            },
                            onError: (error) => {
                                if (options.onError) options.onError(error);
                            }
                        });
                    });
                    
                    console.log('[LEMMA REFERENCE] Access denied - default verification prompt shown');
                }
            }
            
        } catch (error) {
            console.error('[LEMMA REFERENCE] Error protecting element:', error);
            if (options.onError) {
                options.onError(error);
            }
        }
    }
    
    /**
     * Refresh protection status for an element (typically called after verification)
     */
    async refreshProtection(element, options = {}) {
        console.log('[LEMMA REFERENCE] Refreshing protection status...');
        
        const hasValid = await this.hasValidCredentials();
        
        if (hasValid) {
            // Remove any existing verification prompts
            const existingPrompts = element.parentNode.querySelectorAll('.lemma-verification-prompt');
            existingPrompts.forEach(prompt => prompt.remove());
            
            // Show protected content
            element.style.display = '';
            if (options.onSuccess) {
                options.onSuccess();
            }
            console.log('[LEMMA REFERENCE] Protection refreshed - access granted');
        } else {
            // Still no valid credentials
            element.style.display = 'none';
            if (options.onVerificationRequired) {
                options.onVerificationRequired();
            }
            console.log('[LEMMA REFERENCE] Protection refreshed - still requires verification');
        }
    }
    
    /**
     * Make API calls with proper authentication and error handling
     * Same method any external site would use
     */
    async makeAPICall(endpoint, options = {}) {
        const url = this.apiBaseUrl + endpoint;
        
        // Add API key if available (for sites with API keys)
        if (this.apiKey && options.requiresAuth !== false) {
            options.headers = options.headers || {};
            options.headers['X-API-Key'] = this.apiKey;
        }
        
        // Add CSRF protection if enabled
        if (this.enableCSRF && (options.method === 'POST' || options.method === 'PUT' || options.method === 'DELETE')) {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (csrfToken) {
                options.headers = options.headers || {};
                options.headers['X-CSRF-Token'] = csrfToken;
            }
        }
        
        console.log(`[LEMMA REFERENCE] API Call: ${options.method || 'GET'} ${endpoint}`);
        
        return fetch(url, options);
    }
    
    /**
     * Show user messages (same as external sites would implement)
     */
    showMessage(message, type = 'info') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `lemma-message lemma-message-${type}`;
        messageDiv.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            border-radius: 8px;
            font-weight: 600;
            z-index: 10000;
            max-width: 400px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            ${type === 'success' ? 'background: #d4edda; color: #155724; border: 1px solid #c3e6cb;' : ''}
            ${type === 'error' ? 'background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;' : ''}
            ${type === 'info' ? 'background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb;' : ''}
        `;
        messageDiv.innerHTML = message;
        
        document.body.appendChild(messageDiv);
        
        // Auto-remove after delay if enabled
        if (this.autoHideMessages) {
            setTimeout(() => {
                if (messageDiv.parentNode) {
                    messageDiv.parentNode.removeChild(messageDiv);
                }
            }, 5000);
        }
        
        console.log(`[LEMMA REFERENCE] Message shown: ${message}`);
    }
    
    /**
     * Debug information for developers
     */
    getDebugInfo() {
        return {
            initialized: this.initialized,
            walletAvailable: this.wallet !== null,
            apiBaseUrl: this.apiBaseUrl,
            hasApiKey: !!this.apiKey,
            requireHTTPS: this.requireHTTPS,
            enableCSRF: this.enableCSRF,
            currentUrl: window.location.href,
            userAgent: navigator.userAgent
        };
    }
}

// Export for global use
window.LemmaReferenceIntegration = LemmaReferenceIntegration;

console.log('[LEMMA REFERENCE] Reference integration loaded - ready for use by any site'); 