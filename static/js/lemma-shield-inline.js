/**
 * SALVAGED: Lemma Shield Inline Widget - Enhanced with Rust Backend
 * =================================================================
 * Original: static/js/lemma-shield-inline.js
 * Enhanced: Microsecond performance with Rust engine backend
 * 
 * Provides seamless inline verification flow with:
 * - <50ms offline credential checking
 * - Inline Stripe Identity verification
 * - Performance monitoring and metrics
 * - Zero redirects or popups
 */

class LemmaShieldInlineRust {
    constructor(options = {}) {
        // Prevent duplicate initialization
        if (window.lemmaShieldInlineRust && window.lemmaShieldInlineRust.initialized) {
            console.warn('[LemmaShieldRust] Already initialized, returning existing instance');
            return window.lemmaShieldInlineRust;
        }

        this.config = {
            apiBase: options.apiBase || window.location.origin,
            apiKey: options.apiKey || '',
            onVerified: options.onVerified || (() => {}),
            onError: options.onError || (() => {}),
            onShieldShown: options.onShieldShown || (() => {}),
            onShieldHidden: options.onShieldHidden || (() => {}),
            debug: options.debug || false,
            
            // Enhanced with Rust backend features
            enableRustEngine: options.enableRustEngine !== false,
            enablePerformanceMetrics: options.enablePerformanceMetrics || false,
            offlineCheckTimeout: options.offlineCheckTimeout || 50, // 50ms max
            showShieldDelay: options.showShieldDelay || 100, // Brief delay before showing shield
            animationDuration: options.animationDuration || 300, // Smooth animations
            
            // Stripe configuration
            stripePublishableKey: options.stripePublishableKey || 'pk_test_51QJDkbP8RRlCYD4t8GWdrvJOlE6bZRnSqJ8Xzx8mKJHdVE3I8eOhCvMXZjNGq0gJNvJKFGP9t8QXzlW8NNQ6M2kN00XBuMjIuM',
            
            // UI customization
            theme: options.theme || 'modern',
            brandColor: options.brandColor || '#6366f1',
            showBranding: options.showBranding !== false
        };
        
        this.state = {
            initialized: false,
            checking: false,
            verified: false,
            shieldVisible: false,
            verifying: false,
            credentialStored: false,
            currentStep: 'init', // init, checking, shield, verifying, verified
            performanceMetrics: {
                initTime: 0,
                offlineCheckTime: 0,
                verificationTime: 0,
                totalApiCalls: 0,
                rustEngineResponses: 0,
                averageResponseTime: 0
            }
        };
        
        // Core components
        this.stripe = null;
        this.stripeIdentity = null;
        this.shieldOverlay = null;
        this.csrfToken = null;
        
        // Performance tracking
        this.performanceStartTime = performance.now();
        
        // Store as global instance
        window.lemmaShieldInlineRust = this;
        
        // Auto-initialize
        this.init().catch(error => this.handleError(error));
    }
    
    async init() {
        if (this.state.initialized) return;
        
        this.log('🚀 Initializing Lemma Shield with Rust backend...');
        
        try {
            // Validate configuration
            this.validateConfig();
            
            // Initialize CSRF token for API requests
            try {
                await this.getCsrfToken();
                this.log('✅ CSRF token initialized');
            } catch (error) {
                this.log('⚠️ Failed to initialize CSRF token, will retry on API calls:', error);
            }
            
            // Initialize Stripe
            await this.initializeStripe();
            
            // Create shield overlay (hidden initially)
            this.createShieldOverlay();
            
            // Start the enhanced inline flow
            await this.executeEnhancedInlineFlow();
            
            this.state.initialized = true;
            this.state.performanceMetrics.initTime = performance.now() - this.performanceStartTime;
            
            this.log(`✅ Lemma Shield initialized with Rust engine (${this.state.performanceMetrics.initTime.toFixed(2)}ms)`);
            
        } catch (error) {
            this.handleError(error);
        }
    }
    
    validateConfig() {
        if (!this.config.apiBase) {
            throw new Error('API base URL is required');
        }
        
        if (this.config.enableRustEngine && !this.config.apiKey) {
            this.log('⚠️ API key missing - some features may be limited');
        }
    }
    
    async initializeStripe() {
        if (!this.config.stripePublishableKey) {
            throw new Error('Stripe publishable key is required');
        }
        
        try {
            // Load Stripe.js if not already loaded
            if (!window.Stripe) {
                await this.loadStripeScript();
            }
            
            this.stripe = Stripe(this.config.stripePublishableKey);
            
            // Initialize Stripe Identity
            this.stripeIdentity = this.stripe.identity;
            
            this.log('✅ Stripe initialized successfully');
            
        } catch (error) {
            this.log('❌ Failed to initialize Stripe:', error);
            throw error;
        }
    }
    
    async loadStripeScript() {
        return new Promise((resolve, reject) => {
            if (window.Stripe) {
                resolve();
                return;
            }
            
            const script = document.createElement('script');
            script.src = 'https://js.stripe.com/v3/';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    async executeEnhancedInlineFlow() {
        this.log('🔄 Executing enhanced inline flow with Rust backend');
        
        try {
            this.updateCurrentStep('checking');
            
            // STEP 1: Ultra-fast offline check (< 50ms)
            const offlineStartTime = performance.now();
            const offlineResult = await this.checkOfflineCredentials();
            this.state.performanceMetrics.offlineCheckTime = performance.now() - offlineStartTime;
            
            if (offlineResult.verified) {
                this.log(`✅ Offline verification successful (${this.state.performanceMetrics.offlineCheckTime.toFixed(2)}ms)`);
                return this.grantAccess('offline_verification', offlineResult);
            }
            
            // STEP 2: Show shield for new users (with brief delay for smooth UX)
            setTimeout(() => {
                this.showShieldFlow();
            }, this.config.showShieldDelay);
            
        } catch (error) {
            this.handleError(error);
        }
    }
    
    async checkOfflineCredentials() {
        try {
            const credentials = this.getStoredCredentials();
            
            if (!credentials || credentials.length === 0) {
                this.log('ℹ️ No stored credentials found');
                return { verified: false, reason: 'no_credentials' };
            }
            
            // Create timeout promise for offline check
            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('Offline check timeout')), this.config.offlineCheckTimeout);
            });
            
            // Call Rust-enhanced API with timeout
            const apiPromise = this.makeApiRequest('/api/shield/status', {
                method: 'POST',
                body: JSON.stringify({
                    credentials: credentials,
                    enable_rust_engine: this.config.enableRustEngine,
                    enable_performance_metrics: this.config.enablePerformanceMetrics
                })
            });
            
            const response = await Promise.race([apiPromise, timeoutPromise]);
            
            this.state.performanceMetrics.totalApiCalls++;
            
            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }
            
            const result = await response.json();
            
            // Track Rust engine performance
            if (result.engine && result.engine.includes('rust')) {
                this.state.performanceMetrics.rustEngineResponses++;
                
                if (result.response_time_ns && this.config.enablePerformanceMetrics) {
                    const responseTimeMs = result.response_time_ns / 1000000;
                    this.state.performanceMetrics.averageResponseTime = 
                        (this.state.performanceMetrics.averageResponseTime + responseTimeMs) / 2;
                    
                    this.log(`🚀 Rust engine response: ${responseTimeMs.toFixed(3)}ms (${result.response_time_ns}ns)`);
                }
            }
            
            return {
                verified: result.success && result.shield_action === 'allow_access',
                reason: result.reason,
                engine: result.engine || 'unknown',
                performanceMetrics: {
                    responseTimeMs: result.response_time_ms || 0,
                    responseTimeNs: result.response_time_ns || 0,
                    validCredentials: result.valid_count || 0,
                    totalChecked: result.credentials_checked || 0
                }
            };
            
        } catch (error) {
            if (error.message === 'Offline check timeout') {
                this.log('⏱️ Offline check timed out - proceeding to shield');
                return { verified: false, reason: 'offline_timeout' };
            }
            
            this.log('❌ Offline check failed:', error);
            return { verified: false, reason: 'offline_check_failed', error: error.message };
        }
    }
    
    getStoredCredentials() {
        try {
            // Check localStorage for stored credentials
            const storedCreds = localStorage.getItem('lemma_credentials');
            if (storedCreds) {
                return JSON.parse(storedCreds);
            }
            
            // Check sessionStorage as fallback
            const sessionCreds = sessionStorage.getItem('lemma_credentials');
            if (sessionCreds) {
                return JSON.parse(sessionCreds);
            }
            
            return [];
        } catch (error) {
            this.log('❌ Failed to get stored credentials:', error);
            return [];
        }
    }
    
    async showShieldFlow() {
        if (this.state.shieldVisible) return;
        
        this.log('🛡️ Showing shield flow with inline Stripe Identity');
        
        try {
            this.updateCurrentStep('shield');
            this.showShieldOverlay();
            
            // Start inline Stripe Identity verification
            await this.startInlineStripeIdentity();
            
        } catch (error) {
            this.handleError(error);
        }
    }
    
    showShieldOverlay() {
        if (!this.shieldOverlay) {
            this.createShieldOverlay();
        }
        
        this.shieldOverlay.style.display = 'flex';
        this.shieldOverlay.style.opacity = '0';
        
        // Animate in
        setTimeout(() => {
            this.shieldOverlay.style.opacity = '1';
        }, 10);
        
        this.state.shieldVisible = true;
        this.config.onShieldShown();
    }
    
    hideShieldOverlay() {
        if (!this.shieldOverlay || !this.state.shieldVisible) return;
        
        // Animate out
        this.shieldOverlay.style.opacity = '0';
        
        setTimeout(() => {
            this.shieldOverlay.style.display = 'none';
        }, this.config.animationDuration);
        
        this.state.shieldVisible = false;
        this.config.onShieldHidden();
    }
    
    createShieldOverlay() {
        if (this.shieldOverlay) return;
        
        this.shieldOverlay = document.createElement('div');
        this.shieldOverlay.id = 'lemma-shield-overlay';
        this.shieldOverlay.innerHTML = `
            <div class="lemma-shield-backdrop"></div>
            <div class="lemma-shield-container">
                <div class="lemma-shield-header">
                    <h2>🛡️ Lemma Verification</h2>
                    <p>Complete identity verification to continue</p>
                </div>
                
                <div class="lemma-shield-content">
                    <div id="lemma-shield-status" class="lemma-shield-status">
                        <div class="lemma-shield-spinner"></div>
                        <p>Initializing verification...</p>
                    </div>
                    
                    <div id="lemma-stripe-identity-container" class="lemma-stripe-identity-container" style="display: none;">
                        <!-- Stripe Identity will be mounted here -->
                    </div>
                </div>
                
                <div class="lemma-shield-footer">
                    ${this.config.showBranding ? '<p>Powered by <strong>Lemma</strong> with Rust Engine</p>' : ''}
                </div>
            </div>
        `;
        
        // Add styles
        this.addShieldStyles();
        
        document.body.appendChild(this.shieldOverlay);
        
        this.log('✅ Shield overlay created');
    }
    
    addShieldStyles() {
        const styleId = 'lemma-shield-styles';
        
        if (document.getElementById(styleId)) return;
        
        const style = document.createElement('style');
        style.id = styleId;
        style.textContent = `
            #lemma-shield-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: 999999;
                display: none;
                justify-content: center;
                align-items: center;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
                transition: opacity ${this.config.animationDuration}ms ease;
            }
            
            .lemma-shield-backdrop {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.7);
                backdrop-filter: blur(8px);
            }
            
            .lemma-shield-container {
                position: relative;
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                max-width: 480px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
                padding: 32px;
                text-align: center;
            }
            
            .lemma-shield-header h2 {
                margin: 0 0 8px 0;
                color: ${this.config.brandColor};
                font-size: 24px;
                font-weight: 600;
            }
            
            .lemma-shield-header p {
                margin: 0 0 24px 0;
                color: #666;
                font-size: 16px;
            }
            
            .lemma-shield-content {
                min-height: 200px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            
            .lemma-shield-status {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 16px;
            }
            
            .lemma-shield-spinner {
                width: 32px;
                height: 32px;
                border: 3px solid #f3f3f3;
                border-top: 3px solid ${this.config.brandColor};
                border-radius: 50%;
                animation: lemma-spin 1s linear infinite;
            }
            
            @keyframes lemma-spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .lemma-stripe-identity-container {
                margin: 16px 0;
                min-height: 300px;
            }
            
            .lemma-shield-footer {
                margin-top: 24px;
                padding-top: 16px;
                border-top: 1px solid #eee;
                font-size: 14px;
                color: #888;
            }
            
            .lemma-shield-footer strong {
                color: ${this.config.brandColor};
            }
            
            .lemma-shield-error {
                color: #dc2626;
                padding: 16px;
                background: #fef2f2;
                border-radius: 8px;
                margin: 16px 0;
            }
            
            .lemma-shield-success {
                color: #059669;
                padding: 16px;
                background: #ecfdf5;
                border-radius: 8px;
                margin: 16px 0;
            }
            
            /* Mobile responsive */
            @media (max-width: 480px) {
                .lemma-shield-container {
                    width: 95%;
                    padding: 24px;
                }
                
                .lemma-shield-header h2 {
                    font-size: 20px;
                }
            }
        `;
        
        document.head.appendChild(style);
    }
    
    async startInlineStripeIdentity() {
        if (this.state.verifying) return;
        
        this.state.verifying = true;
        this.updateCurrentStep('verifying');
        
        try {
            this.log('🔐 Starting inline Stripe Identity verification');
            this.updateShieldStatus('Starting identity verification...', false);
            
            const verificationStartTime = performance.now();
            const user_id = `shield_${Date.now()}`;
            
            // Start Stripe Identity verification session
            const response = await this.makeApiRequest('/api/shield/start-stripe-identity', {
                method: 'POST',
                body: JSON.stringify({
                    user_id: user_id,
                    return_url: window.location.href,
                    inline_mode: true
                })
            });
            
            this.state.performanceMetrics.totalApiCalls++;
            
            if (!response.ok) {
                throw new Error(`Stripe Identity start failed: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.log('🔐 Identity verification session created:', data);
                
                // Mount Stripe Identity element
                await this.mountStripeIdentityElement(data.client_secret);
                
                // Start polling for completion
                this.startVerificationPolling(user_id, data.session_id);
                
            } else {
                throw new Error(data.error || 'Failed to start Stripe Identity');
            }
            
        } catch (error) {
            this.handleError(error);
        } finally {
            this.state.verifying = false;
        }
    }
    
    async mountStripeIdentityElement(clientSecret) {
        try {
            const container = document.getElementById('lemma-stripe-identity-container');
            const statusElement = document.getElementById('lemma-shield-status');
            
            if (!container || !this.stripeIdentity) {
                throw new Error('Stripe Identity container or client not available');
            }
            
            // Create verification element
            const verificationElement = this.stripeIdentity.create('verificationSession', {
                clientSecret: clientSecret,
                theme: 'stripe'
            });
            
            // Mount the element
            await verificationElement.mount(container);
            
            // Show the container and hide status
            statusElement.style.display = 'none';
            container.style.display = 'block';
            
            this.log('✅ Stripe Identity element mounted successfully');
            
        } catch (error) {
            this.log('❌ Failed to mount Stripe Identity element:', error);
            throw error;
        }
    }
    
    startVerificationPolling(userId, sessionId) {
        const pollInterval = 2000; // 2 seconds
        const maxPollingTime = 600000; // 10 minutes
        const startTime = Date.now();
        
        const poll = async () => {
            try {
                // Check if polling has timed out
                if (Date.now() - startTime > maxPollingTime) {
                    this.log('⏱️ Verification polling timed out');
                    this.updateShieldStatus('Verification timed out. Please try again.', true);
                    return;
                }
                
                // Check verification status
                const response = await this.makeApiRequest('/api/shield/check-stripe-verification', {
                    method: 'POST',
                    body: JSON.stringify({
                        user_id: userId,
                        session_id: sessionId
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`Status check failed: ${response.status}`);
                }
                
                const result = await response.json();
                
                if (result.success && result.verified) {
                    this.log('✅ Verification completed successfully');
                    
                    // Store credential
                    if (result.credential) {
                        this.storeCredential(result.credential);
                    }
                    
                    // Grant access
                    this.grantAccess('stripe_identity', result);
                    
                } else if (result.status === 'requires_input') {
                    this.log('⚠️ Verification requires additional input');
                    this.updateShieldStatus('Please complete the verification process above.', false);
                    
                    // Continue polling
                    setTimeout(poll, pollInterval);
                    
                } else if (result.status === 'processing') {
                    this.log('🔄 Verification still processing');
                    this.updateShieldStatus('Processing your verification...', false);
                    
                    // Continue polling
                    setTimeout(poll, pollInterval);
                    
                } else {
                    this.log('ℹ️ Verification not yet complete, continuing to poll');
                    
                    // Continue polling
                    setTimeout(poll, pollInterval);
                }
                
            } catch (error) {
                this.log('❌ Verification polling error:', error);
                
                // Continue polling unless it's a critical error
                if (error.message.includes('Status check failed')) {
                    setTimeout(poll, pollInterval);
                } else {
                    this.updateShieldStatus('Verification check failed. Please try again.', true);
                }
            }
        };
        
        // Start polling
        setTimeout(poll, pollInterval);
    }
    
    storeCredential(credential) {
        try {
            // Store in localStorage for persistence
            localStorage.setItem('lemma_credentials', JSON.stringify([credential]));
            
            // Also store in sessionStorage for immediate access
            sessionStorage.setItem('lemma_credentials', JSON.stringify([credential]));
            
            this.state.credentialStored = true;
            this.log('✅ Credential stored successfully');
            
        } catch (error) {
            this.log('❌ Failed to store credential:', error);
        }
    }
    
    grantAccess(method, result) {
        this.updateCurrentStep('verified');
        this.state.verified = true;
        
        // Record performance metrics
        this.state.performanceMetrics.verificationTime = performance.now() - this.performanceStartTime;
        
        this.log(`✅ Access granted via ${method}`);
        this.log('📊 Performance metrics:', this.state.performanceMetrics);
        
        // Update UI
        this.updateShieldStatus('✅ Verification successful!', false, 'success');
        
        // Hide shield after brief delay
        setTimeout(() => {
            this.hideShieldOverlay();
        }, 2000);
        
        // Notify callback
        this.config.onVerified({
            method: method,
            result: result,
            performanceMetrics: this.state.performanceMetrics
        });
    }
    
    updateCurrentStep(step) {
        this.state.currentStep = step;
        this.log(`📍 Step: ${step}`);
    }
    
    updateShieldStatus(message, isError = false, type = 'info') {
        const statusElement = document.getElementById('lemma-shield-status');
        if (!statusElement) return;
        
        const spinner = statusElement.querySelector('.lemma-shield-spinner');
        const textElement = statusElement.querySelector('p');
        
        if (textElement) {
            textElement.textContent = message;
        }
        
        if (spinner) {
            spinner.style.display = isError ? 'none' : 'block';
        }
        
        // Update styling based on type
        statusElement.className = `lemma-shield-status ${type === 'error' ? 'lemma-shield-error' : type === 'success' ? 'lemma-shield-success' : ''}`;
    }
    
    async getCsrfToken() {
        try {
            if (this.csrfToken) {
                return this.csrfToken;
            }

            const response = await fetch(`${this.config.apiBase}/api/csrf-token`, {
                method: 'GET',
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw new Error(`Failed to get CSRF token: ${response.status}`);
            }

            const data = await response.json();
            this.csrfToken = data.csrf_token;
            return this.csrfToken;
        } catch (error) {
            this.log('❌ Failed to get CSRF token:', error);
            throw error;
        }
    }
    
    async makeApiRequest(url, options = {}) {
        try {
            // Get CSRF token for protected endpoints
            const csrfToken = await this.getCsrfToken();
            
            // Set default headers
            const headers = {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRF-Token': csrfToken,
                ...options.headers
            };

            // Add API key if available
            if (this.config.apiKey) {
                headers['X-API-Key'] = this.config.apiKey;
            }

            const requestOptions = {
                credentials: 'same-origin',
                ...options,
                headers
            };

            const fullUrl = url.startsWith('http') ? url : `${this.config.apiBase}${url}`;
            
            this.log(`🌐 Making API request to ${fullUrl}`);
            
            return await fetch(fullUrl, requestOptions);
            
        } catch (error) {
            this.log('❌ API request failed:', error);
            throw error;
        }
    }
    
    handleError(error) {
        this.log('❌ Error:', error);
        
        if (this.state.shieldVisible) {
            this.updateShieldStatus(`Error: ${error.message}`, true, 'error');
        }
        
        this.config.onError(error);
    }
    
    log(message, ...args) {
        if (this.config.debug) {
            console.log(`[LemmaShieldRust] ${message}`, ...args);
        }
    }
    
    // Public API methods
    getPerformanceMetrics() {
        return { ...this.state.performanceMetrics };
    }
    
    getState() {
        return { ...this.state };
    }
    
    destroy() {
        if (this.shieldOverlay) {
            this.shieldOverlay.remove();
            this.shieldOverlay = null;
        }
        
        // Remove styles
        const styleElement = document.getElementById('lemma-shield-styles');
        if (styleElement) {
            styleElement.remove();
        }
        
        this.state.initialized = false;
        
        // Clear global instance
        if (window.lemmaShieldInlineRust === this) {
            window.lemmaShieldInlineRust = null;
        }
        
        this.log('🧹 Shield destroyed');
    }
}

// Make available globally
window.LemmaShieldInlineRust = LemmaShieldInlineRust;

// Auto-initialize if data attributes are present
document.addEventListener('DOMContentLoaded', function() {
    const autoInit = document.querySelector('[data-lemma-shield-rust]');
    if (autoInit) {
        const options = {
            apiKey: autoInit.dataset.apiKey,
            apiBase: autoInit.dataset.apiBase,
            debug: autoInit.dataset.debug === 'true',
            enableRustEngine: autoInit.dataset.enableRustEngine !== 'false',
            enablePerformanceMetrics: autoInit.dataset.enablePerformanceMetrics === 'true'
        };
        
        new LemmaShieldInlineRust(options);
    }
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaShieldInlineRust;
}

if (typeof exports !== 'undefined') {
    exports.LemmaShieldInlineRust = LemmaShieldInlineRust;
} 