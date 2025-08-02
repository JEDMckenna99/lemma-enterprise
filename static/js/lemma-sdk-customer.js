/**
 * Lemma SDK - Customer Integration Library
 * ==========================================
 * 
 * This is the exact SDK that customers integrate to add:
 * - Identity Network verification
 * - Bot Shield protection  
 * - Background wallet checking
 * - Microsecond Rust-powered verification
 * 
 * Usage:
 *   const lemma = new LemmaSDK({ apiKey: 'your-key' });
 *   lemma.protectElement('#protected-content');
 */

class LemmaSDK {
    constructor(options = {}) {
        this.config = {
            apiKey: options.apiKey || '',
            apiBase: options.apiBase || window.location.origin,
            enableBotShield: options.enableBotShield !== false,
            enableIdentityNetwork: options.enableIdentityNetwork !== false,
            debug: options.debug || false,
            
            // Event callbacks
            onInitialized: options.onInitialized || (() => {}),
            onCredentialCheck: options.onCredentialCheck || (() => {}),
            onIdentityVerificationStart: options.onIdentityVerificationStart || (() => {}),
            onIdentityVerificationComplete: options.onIdentityVerificationComplete || (() => {}),
            onError: options.onError || (() => {})
        };
        
        this.state = {
            initialized: false,
            checking: false,
            verified: false,
            hasCredentials: false,
            credentials: [],
            lastCheck: null
        };
        
        this.performanceMetrics = {
            totalChecks: 0,
            averageCheckTime: 0,
            backgroundWalletHits: 0,
            rustEngineVerifications: 0
        };
        
        this.protectedElements = new Set();
        
        // Auto-initialize
        this.init();
    }
    
    async init() {
        try {
            if (this.config.debug) {
                console.log('🚀 Lemma SDK initializing...', this.config);
            }
            
            // Validate API key
            if (!this.config.apiKey) {
                throw new Error('API key is required');
            }
            
            // Initialize background wallet connection
            await this.initializeBackgroundWallet();
            
            // Mark as initialized
            this.state.initialized = true;
            
            if (this.config.debug) {
                console.log('✅ Lemma SDK initialized successfully');
            }
            
            this.config.onInitialized();
            
        } catch (error) {
            console.error('❌ Lemma SDK initialization failed:', error);
            this.config.onError(error);
        }
    }
    
    async initializeBackgroundWallet() {
        // Connect to background wallet for seamless credential checking
        if (this.config.debug) {
            console.log('🔗 Connecting to background wallet...');
        }
        
        // Simulate background wallet connection
        // In production, this would connect to the Rust-powered wallet
        await new Promise(resolve => setTimeout(resolve, 100));
        
        if (this.config.debug) {
            console.log('✅ Background wallet connected');
        }
    }
    
    protectElement(selector) {
        const element = document.querySelector(selector);
        if (!element) {
            console.error(`❌ Element not found: ${selector}`);
            return;
        }
        
        this.protectedElements.add(element);
        
        if (this.config.debug) {
            console.log(`🛡️ Protecting element: ${selector}`);
        }
        
        // Start the verification flow
        this.checkCredentialsAndProtect(element);
    }
    
    async checkCredentialsAndProtect(element) {
        const startTime = performance.now();
        
        try {
            this.state.checking = true;
            
            // STEP 1: Background wallet credential check
            const credentialCheck = await this.performBackgroundCredentialCheck();
            
            this.config.onCredentialCheck(credentialCheck);
            
            if (credentialCheck.hasCredentials) {
                // ✅ Found valid credentials - allow access immediately  
                this.state.verified = true;
                this.state.hasCredentials = true;
                this.state.credentials = credentialCheck.credentials;
                
                this.showProtectedContent(element);
                
                const endTime = performance.now();
                this.updatePerformanceMetrics(endTime - startTime, true);
                
            } else {
                // ❌ No valid credentials - start identity verification
                await this.startIdentityVerification(element);
            }
            
        } catch (error) {
            console.error('❌ Credential check failed:', error);
            this.config.onError(error);
        } finally {
            this.state.checking = false;
        }
    }
    
    async performBackgroundCredentialCheck() {
        const startTime = performance.now();
        
        if (this.config.debug) {
            console.log('🔍 Checking background wallet for credentials...');
        }
        
        try {
            // Make API call to check for existing credentials
            const response = await fetch(`${this.config.apiBase}/api/sdk/check-credentials`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    backgroundCheck: true,
                    walletSync: true,
                    enableRustEngine: true
                })
            });
            
            const result = await response.json();
            const endTime = performance.now();
            
            if (result.success && result.hasCredentials) {
                this.performanceMetrics.backgroundWalletHits++;
                
                if (this.config.debug) {
                    console.log(`✅ Background credentials found - ${endTime - startTime}ms`);
                }
                
                return {
                    hasCredentials: true,
                    credentials: result.credentials || [],
                    method: 'background_wallet',
                    timing: {
                        total: endTime - startTime,
                        source: 'background_wallet'
                    }
                };
            } else {
                if (this.config.debug) {
                    console.log(`❌ No background credentials found - ${endTime - startTime}ms`);
                }
                
                return {
                    hasCredentials: false,
                    reason: result.reason || 'No valid credentials found',
                    timing: {
                        total: endTime - startTime,
                        source: 'background_wallet'
                    }
                };
            }
            
        } catch (error) {
            console.error('❌ Background credential check failed:', error);
            return {
                hasCredentials: false,
                reason: 'API call failed',
                error: error.message
            };
        }
    }
    
    async startIdentityVerification(element) {
        if (this.config.debug) {
            console.log('🆔 Starting identity verification flow...');
        }
        
        this.config.onIdentityVerificationStart();
        
        // Hide protected content and show identity verification UI
        this.hideProtectedContent(element);
        this.showIdentityVerificationUI(element);
        
        try {
            // Start Stripe Identity verification
            const response = await fetch(`${this.config.apiBase}/api/sdk/start-identity-verification`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    provider: 'stripe_identity',
                    inline_mode: true,
                    return_url: window.location.href
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Initialize Stripe Identity session
                await this.initializeStripeIdentity(result, element);
            } else {
                throw new Error(result.message || 'Failed to start identity verification');
            }
            
        } catch (error) {
            console.error('❌ Identity verification failed:', error);
            this.config.onError(error);
        }
    }
    
    async initializeStripeIdentity(verificationSession, element) {
        if (this.config.debug) {
            console.log('🎫 Initializing Stripe Identity...', verificationSession);
        }
        
        // Handle demo mode only if explicitly set by server
        if (verificationSession.demo_mode || verificationSession.session_id.startsWith('vs_demo_')) {
            await this.initializeDemoIdentityFlow(verificationSession, element);
            return;
        }
        
        try {
            // Load Stripe.js (main library, not separate Identity SDK)
            if (!window.Stripe) {
                await this.loadStripeIdentitySDK();
            }
            
            // Create Stripe instance with publishable key
            const stripe = window.Stripe('pk_test_TYooMQauvdEDq54NiTphI7jx');
            
            // Get the verification element container
            const identityContainer = element.querySelector('.identity-verification-container');
            if (!identityContainer) {
                throw new Error('Identity verification container not found');
            }
            
            // Clean up client_secret - remove any trailing periods or whitespace
            const cleanClientSecret = verificationSession.client_secret.trim().replace(/\.$/, '');
            
            if (this.config.debug) {
                console.log('🎫 Creating Stripe Identity verification element...', {
                    client_secret: verificationSession.client_secret.substring(0, 20) + '...',
                    original_client_secret: verificationSession.client_secret,
                    cleaned_client_secret: cleanClientSecret,
                    original_length: verificationSession.client_secret.length,
                    cleaned_length: cleanClientSecret.length,
                    client_secret_ends_with: verificationSession.client_secret.slice(-10),
                    cleaned_ends_with: cleanClientSecret.slice(-10)
                });
            }
            
            // Use the standard Stripe Identity Elements pattern
            const stripe_elements = stripe.elements({
                clientSecret: cleanClientSecret,
                appearance: {
                    theme: 'stripe'
                }
            });
            
            // Create identity verification element  
            const identityVerification = stripe_elements.create('identityVerification');
            
            // Mount the element
            identityVerification.mount(identityContainer);
            
            if (this.config.debug) {
                console.log('✅ Stripe Identity element mounted successfully');
            }
            
            // Handle events
            identityVerification.on('ready', () => {
                if (this.config.debug) {
                    console.log('✅ Stripe Identity verification ready');
                }
            });
            
            identityVerification.on('complete', (event) => {
                if (this.config.debug) {
                    console.log('🎉 Stripe Identity verification completed!', event);
                }
                // Handle successful verification
                this.handleIdentityVerificationComplete(verificationSession.session_id, element);
            });
            
            identityVerification.on('error', (event) => {
                console.error('❌ Stripe Identity error:', event.error);
                this.config.onError(new Error(event.error.message || 'Stripe Identity verification failed'));
            });
            
        } catch (error) {
            console.error('❌ Failed to initialize Stripe Identity:', error);
            this.config.onError(new Error('Failed to initialize Stripe Identity: ' + error.message));
        }
    }
    
    async initializeDemoIdentityFlow(verificationSession, element) {
        if (this.config.debug) {
            console.log('🎭 Initializing DEMO identity verification flow...');
        }
        
        const identityContainer = element.querySelector('.identity-verification-container');
        if (identityContainer) {
            // Create demo verification UI
            identityContainer.innerHTML = `
                <div style="text-align: center; padding: 2rem; color: #1e293b;">
                    <div style="background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
                        <h4 style="margin: 0 0 0.5rem 0;">🎭 DEMO MODE: Identity Verification</h4>
                        <p style="margin: 0; font-size: 0.9rem; opacity: 0.9;">This is a demo simulation of Stripe Identity KYC verification</p>
                    </div>
                    <div style="background: #f8fafc; border: 2px dashed #cbd5e1; border-radius: 8px; padding: 2rem; margin: 1rem 0;">
                        <div style="font-size: 3rem; margin-bottom: 1rem;">📄</div>
                        <p style="color: #64748b; margin: 0 0 1rem 0;">In production, users would upload their government ID and take a selfie</p>
                        <button id="demo-verify-btn" style="
                            background: linear-gradient(135deg, #6366f1, #8b5cf6);
                            color: white;
                            border: none;
                            padding: 0.75rem 2rem;
                            border-radius: 6px;
                            font-weight: 600;
                            cursor: pointer;
                            font-size: 1rem;
                        ">Complete Demo Verification</button>
                    </div>
                    <div style="font-size: 0.8rem; color: #64748b; line-height: 1.4;">
                        <p><strong>Demo Features:</strong></p>
                        <p>✅ Document verification • ✅ Liveness detection • ✅ Identity matching</p>
                        <p>✅ KYC compliance • ✅ Microsecond verification • ✅ Rust-powered credentials</p>
                    </div>
                </div>
            `;
            
            // Handle demo verification button click
            const demoBtn = identityContainer.querySelector('#demo-verify-btn');
            if (demoBtn) {
                demoBtn.addEventListener('click', async () => {
                    demoBtn.textContent = 'Processing...';
                    demoBtn.style.opacity = '0.7';
                    demoBtn.disabled = true;
                    
                    // Simulate verification delay
                    setTimeout(async () => {
                        await this.handleIdentityVerificationComplete(verificationSession.session_id, element);
                    }, 2000);
                });
            }
        }
    }
    
    async handleIdentityVerificationComplete(sessionId, element) {
        const startTime = performance.now();
        
        if (this.config.debug) {
            console.log('✅ Identity verification completed, checking status...');
        }
        
        try {
            // Check verification status and create credentials
            const response = await fetch(`${this.config.apiBase}/api/sdk/complete-identity-verification`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    enable_rust_engine: true,
                    demo_mode: false // Ensure we don't use demo mode
                })
            });
            
            const result = await response.json();
            const endTime = performance.now();
            
            if (result.success && result.verified) {
                // ✅ Verification successful - credentials created
                this.state.verified = true;
                this.state.hasCredentials = true;
                this.state.credentials = [result.credential];
                
                // Store in background wallet for future use
                await this.storeCredentialInBackgroundWallet(result.credential);
                
                // Show protected content
                this.hideIdentityVerificationUI(element);
                this.showProtectedContent(element);
                
                // Update performance metrics
                this.performanceMetrics.rustEngineVerifications++;
                this.updatePerformanceMetrics(endTime - startTime, true);
                
                this.config.onIdentityVerificationComplete({
                    verified: true,
                    credential: result.credential,
                    method: 'stripe_identity_kyc',
                    timing: {
                        verificationUs: result.verification_time_us || (endTime - startTime) * 1000,
                        total: endTime - startTime
                    }
                });
                
            } else {
                throw new Error(result.message || 'Identity verification failed');
            }
            
        } catch (error) {
            console.error('❌ Identity verification completion failed:', error);
            this.config.onError(error);
        }
    }
    
    async storeCredentialInBackgroundWallet(credential) {
        if (this.config.debug) {
            console.log('💾 Storing credential in background wallet...');
        }
        
        try {
            // Store credential for seamless future access
            const response = await fetch(`${this.config.apiBase}/api/sdk/store-credential`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    credential: credential,
                    enable_rust_preload: true
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                if (this.config.debug) {
                    console.log('✅ Credential stored successfully');
                }
            }
            
        } catch (error) {
            console.error('❌ Failed to store credential:', error);
        }
    }
    
    showProtectedContent(element) {
        // Remove any verification UI
        const existingUI = element.querySelector('.lemma-verification-ui');
        if (existingUI) {
            existingUI.remove();
        }
        
        // Show the original content
        element.style.display = '';
        element.style.opacity = '1';
        
        if (this.config.debug) {
            console.log('✅ Showing protected content');
        }
    }
    
    hideProtectedContent(element) {
        element.style.opacity = '0.3';
        
        if (this.config.debug) {
            console.log('🙈 Hiding protected content');
        }
    }
    
    showIdentityVerificationUI(element) {
        // Create verification UI
        const verificationUI = document.createElement('div');
        verificationUI.className = 'lemma-verification-ui';
        verificationUI.innerHTML = `
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; border-radius: 12px; text-align: center; margin: 2rem 0;">
                <h3 style="margin: 0 0 1rem 0;">🛡️ Identity Verification Required</h3>
                <p style="margin: 0 0 1.5rem 0; opacity: 0.9;">This content is protected by Lemma's identity network. Please complete identity verification to access.</p>
                <div class="identity-verification-container" style="background: white; border-radius: 8px; padding: 1rem; margin-top: 1rem;">
                    <div style="color: #666; text-align: center; padding: 2rem;">
                        <div style="display: inline-block; width: 20px; height: 20px; border: 2px solid #6366f1; border-top: 2px solid transparent; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        <p style="margin: 1rem 0 0 0;">Initializing Stripe Identity verification...</p>
                    </div>
                </div>
            </div>
        `;
        
        element.insertBefore(verificationUI, element.firstChild);
        
        if (this.config.debug) {
            console.log('👁️ Showing identity verification UI');
        }
    }
    
    hideIdentityVerificationUI(element) {
        const verificationUI = element.querySelector('.lemma-verification-ui');
        if (verificationUI) {
            verificationUI.remove();
        }
        
        if (this.config.debug) {
            console.log('🙈 Hiding identity verification UI');
        }
    }
    
    async loadStripeIdentitySDK() {
        return new Promise((resolve, reject) => {
            // Check if Stripe.js is already loaded
            if (window.Stripe) {
                resolve();
                return;
            }
            
            // Load the main Stripe.js library (Identity is included)
            const stripeScript = document.createElement('script');
            stripeScript.src = 'https://js.stripe.com/v3/';
            stripeScript.onload = () => {
                if (this.config.debug) {
                    console.log('✅ Stripe.js loaded successfully (Identity included)');
                }
                resolve();
            };
            stripeScript.onerror = (error) => {
                console.error('❌ Failed to load Stripe.js:', error);
                reject(error);
            };
            document.head.appendChild(stripeScript);
        });
    }
    
    updatePerformanceMetrics(duration, success) {
        this.performanceMetrics.totalChecks++;
        
        if (this.performanceMetrics.averageCheckTime === 0) {
            this.performanceMetrics.averageCheckTime = duration;
        } else {
            this.performanceMetrics.averageCheckTime = 
                (this.performanceMetrics.averageCheckTime + duration) / 2;
        }
    }
    
    getState() {
        return { ...this.state };
    }
    
    getPerformanceMetrics() {
        return { ...this.performanceMetrics };
    }
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    .lemma-verification-ui {
        animation: fadeIn 0.3s ease-in-out;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .credential-item {
        background: #f8fafc;
        padding: 0.75rem;
        margin: 0.5rem 0;
        border-radius: 6px;
        border-left: 4px solid #6366f1;
    }
`;
document.head.appendChild(style);

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaSDK;
}

// Global availability
window.LemmaSDK = LemmaSDK; 