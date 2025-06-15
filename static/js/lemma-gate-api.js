/**
 * Lemma Gate API Client - Clean API-Driven Implementation
 * 
 * This client handles all gate functionality through centralized API endpoints.
 * All verification logic, session management, and security is handled server-side.
 * 
 * Perfect Flow:
 * 1. Call API to check status
 * 2. If has credentials → API handles background verification automatically
 * 3. If no credentials → Show gate → Direct to verification flow
 * 
 * Usage:
 * const gate = new LemmaGateAPI({
 *   protectedContent: '#protected-content',
 *   onVerified: () => console.log('User verified!'),
 *   onError: (error) => console.error('Gate error:', error)
 * });
 */

class LemmaGateAPI {
    constructor(options = {}) {
        this.options = {
            // UI Elements
            protectedContent: options.protectedContent || '#protected-content',
            gateContainer: options.gateContainer || '#lemma-gate',
            
            // API Configuration 
            apiBase: options.apiBase || '',
            
            // UI Customization
            gateTitle: options.gateTitle || '🛡️ Human Verification Required',
            gateMessage: options.gateMessage || 'This content is protected. Please verify you are human to continue.',
            verifyButtonText: options.verifyButtonText || '✨ Verify with Lemma',
            loadingText: options.loadingText || 'Verifying...',
            
            // Callbacks
            onVerified: options.onVerified || (() => {}),
            onError: options.onError || ((error) => console.error('Lemma Gate Error:', error)),
            onGateShown: options.onGateShown || (() => {}),
            onGateHidden: options.onGateHidden || (() => {}),
            
            // Advanced Options
            autoInit: options.autoInit !== false, // Default true
            retryAttempts: options.retryAttempts || 3,
            retryDelay: options.retryDelay || 1000,
            debug: options.debug || false,
            
            ...options
        };
        
        // State
        this.isInitialized = false;
        this.isVerifying = false;
        this.isVerified = false;
        this.config = null;
        this.retryCount = 0;
        
        // DOM elements
        this.protectedElement = null;
        this.gateElement = null;
        
        if (this.options.autoInit) {
            this.init();
        }
    }
    
    /**
     * Initialize the gate
     */
    async init() {
        if (this.isInitialized) {
            this.log('Gate already initialized');
            return;
        }
        
        this.log('Initializing Lemma Gate API...');
        
        try {
            // Get API configuration
            await this.loadConfig();
            
            // Set up DOM elements
            this.setupDOM();
            
            // Start verification flow
            await this.checkVerificationStatus();
            
            this.isInitialized = true;
            this.log('Lemma Gate initialized successfully');
            
        } catch (error) {
            this.error('Gate initialization failed:', error);
            this.showError('Failed to initialize human verification system');
        }
    }
    
    /**
     * Load gate configuration from API
     */
    async loadConfig() {
        try {
            const response = await fetch(`${this.options.apiBase}/api/gate/config`);
            
            if (!response.ok) {
                throw new Error(`Config request failed: ${response.status}`);
            }
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error || 'Failed to load configuration');
            }
            
            this.config = result.config;
            this.log('Configuration loaded:', this.config);
            
        } catch (error) {
            this.error('Failed to load configuration:', error);
            // Use default config as fallback
            this.config = {
                endpoints: {
                    status: '/api/gate/status',
                    verify_credentials: '/api/gate/verify-credentials',
                    challenge: '/api/gate/challenge',
                    start_verification: '/api/gate/start-verification'
                },
                settings: {
                    verification_timeout: 300,
                    session_timeout: 86400,
                    retry_attempts: 3,
                    retry_delay: 1000
                }
            };
        }
    }
    
    /**
     * Set up DOM elements
     */
    setupDOM() {
        // Find protected content element
        this.protectedElement = document.querySelector(this.options.protectedContent);
        if (!this.protectedElement) {
            throw new Error(`Protected content element not found: ${this.options.protectedContent}`);
        }
        
        // Create or find gate element
        this.gateElement = document.querySelector(this.options.gateContainer);
        if (!this.gateElement) {
            this.gateElement = this.createGateElement();
            document.body.appendChild(this.gateElement);
        }
        
        this.log('DOM elements set up successfully');
    }
    
    /**
     * Create gate overlay element
     */
    createGateElement() {
        const gateDiv = document.createElement('div');
        gateDiv.id = 'lemma-gate';
        gateDiv.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 10000;
            font-family: system-ui, -apple-system, sans-serif;
        `;
        
        gateDiv.innerHTML = `
            <div style="
                background: white;
                padding: 2rem;
                border-radius: 12px;
                text-align: center;
                max-width: 400px;
                margin: 1rem;
                box-shadow: 0 20px 40px rgba(0,0,0,0.3);
            ">
                <div id="gate-content">
                    <h2 style="margin: 0 0 1rem 0; color: #333; font-size: 1.5rem;">
                        ${this.options.gateTitle}
                    </h2>
                    <p style="margin: 0 0 1.5rem 0; color: #666; line-height: 1.5;">
                        ${this.options.gateMessage}  
                    </p>
                    <button id="verify-button" style="
                        background: #635bff;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 6px;
                        font-size: 1rem;
                        cursor: pointer;
                        transition: background 0.2s;
                    ">
                        ${this.options.verifyButtonText}
                    </button>
                    <div id="gate-loading" style="display: none; margin-top: 1rem;">
                        <div style="color: #666;">${this.options.loadingText}</div>
                    </div>
                    <div id="gate-error" style="display: none; margin-top: 1rem; color: #d63384;"></div>
                </div>
            </div>
        `;
        
        // Add event listeners
        const verifyButton = gateDiv.querySelector('#verify-button');
        verifyButton.addEventListener('click', () => this.startVerification());
        
        // Hover effects
        verifyButton.addEventListener('mouseenter', () => {
            verifyButton.style.background = '#5a52d5';
        });
        verifyButton.addEventListener('mouseleave', () => {
            verifyButton.style.background = '#635bff';
        });
        
        return gateDiv;
    }
    
    /**
     * Check verification status with the API
     */
    async checkVerificationStatus() {
        this.log('Checking verification status...');
        this.isVerifying = true;
        
        try {
            // First check if user is already verified in session
            const statusResponse = await fetch(`${this.options.apiBase}${this.config.endpoints.status}`, {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (statusResponse.ok) {
                const statusResult = await statusResponse.json();
                
                if (statusResult.success) {
                    await this.handleGateAction(statusResult.gate_action, statusResult.data, statusResult.message);
                    return;
                }
            }
            
            // If status check failed, check for wallet credentials
            await this.checkWalletCredentials();
            
        } catch (error) {
            this.error('Status check failed:', error);
            this.showGate(); // Fallback to showing gate
        } finally {
            this.isVerifying = false;
        }
    }
    
    /**
     * Check for wallet credentials and verify them
     */
    async checkWalletCredentials() {
        try {
            // Check if Lemma wallet is available
            if (!window.lemmaWallet) {
                this.log('No Lemma wallet found');
                this.showGate();
                return;
            }
            
            // Get credentials from wallet
            const credentials = await window.lemmaWallet.getAllCredentials();
            
            if (!credentials || credentials.length === 0) {
                this.log('No credentials in wallet');
                this.showGate();
                return;
            }
            
            this.log('Found credentials in wallet, verifying...');
            await this.verifyCredentialsWithAPI(credentials);
            
        } catch (error) {
            this.error('Wallet credential check failed:', error);
            this.showGate();
        }
    }
    
    /**
     * Verify credentials with the API
     */
    async verifyCredentialsWithAPI(credentials) {
        try {
            // Get challenge from API
            const challengeResponse = await fetch(`${this.options.apiBase}${this.config.endpoints.challenge}`, {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (!challengeResponse.ok) {
                throw new Error(`Challenge request failed: ${challengeResponse.status}`);
            }
            
            const challengeResult = await challengeResponse.json();
            
            if (!challengeResult.success) {
                throw new Error(challengeResult.error || 'Failed to get challenge');
            }
            
            // Verify credentials with API
            const verifyResponse = await fetch(`${this.options.apiBase}${this.config.endpoints.verify_credentials}`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    credentials: credentials,
                    challenge: challengeResult.challenge,
                    domain: window.location.hostname
                })
            });
            
            if (!verifyResponse.ok) {
                const errorData = await verifyResponse.json().catch(() => ({}));
                throw new Error(errorData.error || `Verification failed: ${verifyResponse.status}`);
            }
            
            const verifyResult = await verifyResponse.json();
            
            if (verifyResult.success) {
                await this.handleGateAction(verifyResult.gate_action, verifyResult.data, verifyResult.message);
            } else {
                throw new Error(verifyResult.error || 'Verification failed');
            }
            
        } catch (error) {
            this.error('Credential verification failed:', error);
            this.showGate();
        }
    }
    
    /**
     * Handle gate action from API response
     */
    async handleGateAction(action, data = {}, message = '') {
        this.log(`Gate action: ${action}`, data, message);
        
        switch (action) {
            case 'allow_access':
                await this.grantAccess(data);
                break;
                
            case 'check_credentials':
                await this.checkWalletCredentials();
                break;
                
            case 'show_gate':
            default:
                this.showGate();
                break;
        }
    }
    
    /**
     * Grant access to protected content
     */
    async grantAccess(data = {}) {
        this.log('Access granted', data);
        
        this.isVerified = true;
        this.hideGate();
        this.showProtectedContent();
        
        // Call success callback
        try {
            await this.options.onVerified(data);
        } catch (error) {
            this.error('onVerified callback error:', error);
        }
    }
    
    /**
     * Show the gate overlay
     */
    showGate() {
        this.log('Showing gate');
        
        if (this.gateElement) {
            this.gateElement.style.display = 'flex';
            this.hideProtectedContent();
            
            // Call gate shown callback
            try {
                this.options.onGateShown();
            } catch (error) {
                this.error('onGateShown callback error:', error);
            }
        }
    }
    
    /**
     * Hide the gate overlay
     */
    hideGate() {
        this.log('Hiding gate');
        
        if (this.gateElement) {
            this.gateElement.style.display = 'none';
            
            // Call gate hidden callback
            try {
                this.options.onGateHidden();
            } catch (error) {
                this.error('onGateHidden callback error:', error);
            }
        }
    }
    
    /**
     * Show protected content
     */
    showProtectedContent() {
        if (this.protectedElement) {
            this.protectedElement.style.display = '';
        }
    }
    
    /**
     * Hide protected content
     */
    hideProtectedContent() {
        if (this.protectedElement) {
            this.protectedElement.style.display = 'none';
        }
    }
    
    /**
     * Start verification process
     */
    async startVerification() {
        this.log('Starting verification process...');
        
        try {
            this.showLoading();
            
            const response = await fetch(`${this.options.apiBase}${this.config.endpoints.start_verification}`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    return_url: window.location.href
                })
            });
            
            if (!response.ok) {
                throw new Error(`Start verification failed: ${response.status}`);
            }
            
            const result = await response.json();
            
            if (result.success && result.verification_url) {
                // Redirect to verification flow
                window.location.href = result.verification_url;
            } else {
                throw new Error(result.error || 'Failed to start verification');
            }
            
        } catch (error) {
            this.error('Start verification failed:', error);
            this.showError('Failed to start verification process');
        }
    }
    
    /**
     * Show loading state
     */
    showLoading() {
        if (this.gateElement) {
            const button = this.gateElement.querySelector('#verify-button');
            const loading = this.gateElement.querySelector('#gate-loading');
            const errorDiv = this.gateElement.querySelector('#gate-error');
            
            if (button) button.style.display = 'none';
            if (loading) loading.style.display = 'block';
            if (errorDiv) errorDiv.style.display = 'none';
        }
    }
    
    /**
     * Show error message
     */
    showError(message) {
        this.error('Showing error:', message);
        
        if (this.gateElement) {
            const button = this.gateElement.querySelector('#verify-button');
            const loading = this.gateElement.querySelector('#gate-loading');
            const errorDiv = this.gateElement.querySelector('#gate-error');
            
            if (button) button.style.display = 'inline-block';
            if (loading) loading.style.display = 'none';
            if (errorDiv) {
                errorDiv.textContent = message;
                errorDiv.style.display = 'block';
            }
        }
        
        // Call error callback
        try {
            this.options.onError(new Error(message));
        } catch (callbackError) {
            this.error('onError callback error:', callbackError);  
        }
    }
    
    /**
     * Retry verification check
     */
    async retry() {
        if (this.retryCount >= this.options.retryAttempts) {
            this.showError('Maximum retry attempts reached');
            return;
        }
        
        this.retryCount++;
        this.log(`Retrying verification check (attempt ${this.retryCount}/${this.options.retryAttempts})`);
        
        // Wait before retrying
        await new Promise(resolve => setTimeout(resolve, this.options.retryDelay));
        
        await this.checkVerificationStatus();
    }
    
    /**
     * Force recheck verification status
     */
    async forceRecheck() {
        this.log('Forcing verification recheck...');
        this.retryCount = 0;
        this.isVerified = false;
        await this.checkVerificationStatus();
    }
    
    /**
     * Get current gate status
     */
    getStatus() {
        return {
            isInitialized: this.isInitialized,
            isVerifying: this.isVerifying,
            isVerified: this.isVerified,
            retryCount: this.retryCount,
            config: this.config
        };
    }
    
    /**
     * Logging helper
     */
    log(...args) {
        if (this.options.debug) {
            console.log('[Lemma Gate API]', ...args);
        }
    }
    
    /**
     * Error logging helper
     */
    error(...args) {
        console.error('[Lemma Gate API]', ...args);
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaGateAPI;
}

// Global access
window.LemmaGateAPI = LemmaGateAPI; 