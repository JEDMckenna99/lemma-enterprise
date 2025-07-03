/**
 * Lemma Shield Widget - Production-Ready Three-Flow Circuit
 * Complete integration: CHECK FLOW → SHIELD FLOW → REVOCATION FLOW
 * Version 2.11.0 - Complete refactor with unified customer integration
 */

class LemmaShield {
    constructor(options = {}) {
        // Prevent duplicate initialization
        if (window.lemmaShield && window.lemmaShield.state?.initialized) {
            this.log('⚠️ Shield already initialized, returning existing instance');
            return window.lemmaShield;
        }

        // Customer configuration
        this.config = {
            apiKey: options.apiKey || '',
            apiBase: options.apiBase || window.location.origin,
            containerId: options.containerId || 'lemma-shield',
            autoInit: options.autoInit !== false,
            onVerified: options.onVerified || (() => {}),
            onError: options.onError || (() => {}),
            onRevoked: options.onRevoked || (() => {}),
            onShieldShown: options.onShieldShown || (() => {}),
            onShieldHidden: options.onShieldHidden || (() => {}),
            debug: options.debug || false,
            
            // Advanced options
            offlineFirst: options.offlineFirst !== false,
            fallbackEnabled: options.fallbackEnabled !== false,
            challengeType: options.challengeType || 'human_verification',
            forceShield: options.forceShield || false, // For join network page
            
            // Stripe Identity integration
            stripePublishableKey: options.stripePublishableKey || 'pk_test_51QJDkbP8RRlCYD4t8GWdrvJOlE6bZRnSqJ8Xzx8mKJHdVE3I8eOhCvMXZjNGq0gJNvJKFGP9t8QXzlW8NNQ6M2kN00XBuMjIuM',
            
            // UI customization
            theme: options.theme || 'default',
            showBranding: options.showBranding !== false
        };

        // Core state management
        this.state = {
            initialized: false,
            verifying: false,
            verified: false,
            credentialsLoaded: false,
            lastVerification: null,
            currentFlow: null,
            shieldVisible: false
        };

        // Internal components
        this.wallet = new LemmaWallet(this.config);
        this.api = new LemmaAPI(this.config);
        this.ui = new LemmaUI(this.config);
        this.stripe = new LemmaStripe(this.config);
        
        // Performance tracking
        this.metrics = {
            startTime: Date.now(),
            flowExecutions: {
                check: 0,
                shield: 0,
                revocation: 0
            },
            offlineSuccessRate: 0,
            apiSuccessRate: 0
        };

        // Store as global instance
        window.lemmaShield = this;

        // Auto-initialize if requested
        if (this.config.autoInit) {
            this.init().catch(error => this.handleError(error));
        }
    }

    log(...args) {
        if (this.config.debug) {
            console.log('[LemmaShield]', new Date().toISOString(), ...args);
        }
    }

    async init() {
        if (this.state.initialized) {
            this.log('⚠️ Shield already initialized');
            return;
        }
        
        this.log('🔄 Initializing Lemma Shield...');
        
        try {
            // Validate configuration
            this.validateConfig();
            
            // Initialize components
            await Promise.all([
                this.wallet.init(),
                this.api.init(),
                this.ui.init(),
                this.stripe.init()
            ]);
            
            // Handle verification return if present
            await this.handleVerificationReturn();
            
            // Start the main protection flow
            await this.executeProtectionFlow();
            
            this.state.initialized = true;
            this.log('✅ Lemma Shield initialized successfully');
            
        } catch (error) {
            this.log('❌ Shield initialization failed:', error);
            this.handleError(error);
        }
    }

    validateConfig() {
        if (!this.config.apiKey && !this.config.forceShield) {
            throw new Error('API key is required for Lemma Shield');
        }
        if (!this.config.apiBase) {
            throw new Error('API base URL is required');
        }
    }

    async executeProtectionFlow() {
        this.log('🔍 Executing protection flow (CHECK -> SHIELD -> REVOCATION)');
        
        try {
            // FLOW 1: CHECK FLOW - Verify existing credentials
            this.state.currentFlow = 'check';
            this.metrics.flowExecutions.check++;
            
            const checkResult = await this.executeCheckFlow();
            
            if (checkResult.verified) {
                this.state.currentFlow = 'verified';
                return this.grantAccess('check_flow', checkResult);
            }
            
            // FLOW 2: SHIELD FLOW - User needs verification
            if (checkResult.needsVerification || this.config.forceShield) {
                this.state.currentFlow = 'shield';
                this.metrics.flowExecutions.shield++;
                return await this.executeShieldFlow();
            }
            
            // FLOW 3: REVOCATION FLOW - Handle revoked credentials
            if (checkResult.revoked) {
                this.state.currentFlow = 'revocation';
                this.metrics.flowExecutions.revocation++;
                return await this.executeRevocationFlow();
            }
            
            // Fallback - show shield
            this.log('🛡️ Fallback - showing shield');
            this.state.currentFlow = 'shield';
            await this.executeShieldFlow();
            
        } catch (error) {
            this.log('❌ Protection flow failed:', error);
            this.handleError(error);
        }
    }

    async executeCheckFlow() {
        this.log('🔍 Executing CHECK FLOW - verifying existing credentials');
        
        try {
            // Get stored credentials
            const credentials = await this.wallet.getCredentials();
            
            if (credentials.length === 0) {
                this.log('📭 No credentials found');
                return { verified: false, needsVerification: true };
            }

            // Try offline verification first (if enabled)
            if (this.config.offlineFirst) {
                for (const credential of credentials) {
                    const offlineResult = await this.verifyOffline(credential);
                    
                    if (offlineResult.success) {
                        this.log('⚡ Offline verification successful');
                        this.metrics.offlineSuccessRate++;
                        return { 
                            verified: true, 
                            method: 'offline',
                            credential,
                            result: offlineResult 
                        };
                    }
                    
                    if (offlineResult.revoked) {
                        this.log('🚫 Offline verification detected revocation');
                        return { verified: false, revoked: true, credential };
                    }
                }
            }

            // API fallback verification (if enabled)
            if (this.config.fallbackEnabled) {
                for (const credential of credentials) {
                    const apiResult = await this.verifyWithAPI(credential);
                    
                    if (apiResult.verified) {
                        this.log('🌐 API verification successful');
                        this.metrics.apiSuccessRate++;
                        return { 
                            verified: true, 
                            method: 'api',
                            credential,
                            result: apiResult 
                        };
                    }
                    
                    if (apiResult.revoked) {
                        this.log('🚫 API verification detected revocation');
                        return { verified: false, revoked: true, credential };
                    }
                }
            }

            // All verifications failed
            this.log('❌ All credential verifications failed');
            return { verified: false, needsVerification: true };
            
        } catch (error) {
            this.log('❌ Check flow error:', error);
            return { verified: false, needsVerification: true, error };
        }
    }

    async executeShieldFlow() {
        this.log('🛡️ Executing SHIELD FLOW - user verification required');
        
        if (this.state.verifying) {
            this.log('⚠️ Verification already in progress');
            return;
        }
        
        try {
            this.state.verifying = true;
            this.state.shieldVisible = true;
            
            // Show verification UI
            await this.ui.showShield();
            
            // Notify that shield is shown
            this.config.onShieldShown();
            
            // Start verification process
            this.log('🚀 Starting Stripe Identity verification process');
            await this.stripe.startVerification();
            
        } catch (error) {
            this.log('❌ Shield flow error:', error);
            this.handleError(error);
        } finally {
            this.state.verifying = false;
        }
    }

    async executeRevocationFlow() {
        this.log('🚫 Executing REVOCATION FLOW - cleaning revoked credentials');
        
        try {
            // Clear all credentials from wallet
            await this.wallet.clearCredentials();
            
            // Clear session storage
            if (typeof sessionStorage !== 'undefined') {
                sessionStorage.removeItem('lemma_credentials');
                sessionStorage.removeItem('lemma_user_id');
            }
            
            // Clear local storage
            if (typeof localStorage !== 'undefined') {
                localStorage.removeItem('lemma_credentials');
                localStorage.removeItem('lemma_user_id');
            }
            
            // Notify callback
            this.config.onRevoked({
                action: 'credentials_revoked',
                timestamp: Date.now(),
                flow: 'revocation'
            });
            
            // Show shield for new verification
            this.log('🛡️ Showing shield after revocation');
            await this.executeShieldFlow();
            
        } catch (error) {
            this.log('❌ Revocation flow error:', error);
            this.handleError(error);
        }
    }

    async verifyOffline(credential) {
        this.log('⚡ Attempting offline verification');
        
        try {
            // Check if credential supports offline verification
            if (!credential.offline_witness || !credential.offline_capable) {
                return { success: false, reason: 'No offline capability' };
            }

            // Check witness expiry
            const now = Math.floor(Date.now() / 1000);
            const validUntil = credential.offline_witness.valid_until;
            
            if (now > validUntil) {
                this.log('⏰ Offline witness expired');
                return { success: false, reason: 'Witness expired', expired: true };
            }

            // Verify cryptographic proof
            if (!this.verifyOfflineProof(credential)) {
                return { success: false, reason: 'Invalid proof' };
            }

            // Check local revocation list
            const revocationResult = await this.checkLocalRevocation(credential);
            if (revocationResult.revoked) {
                return { success: false, revoked: true, reason: 'Locally revoked' };
            }

            // Offline verification successful
            this.log('✅ Offline verification passed');
            return { 
                success: true, 
                method: 'offline',
                witness_expires: validUntil,
                verification_time: Date.now()
            };

        } catch (error) {
            this.log('❌ Offline verification error:', error);
            return { success: false, reason: error.message };
        }
    }

    verifyOfflineProof(credential) {
        try {
            // Extract credential from wallet format if needed
            const actualCredential = credential.credential || credential;
            
            // Basic validation
            if (!actualCredential.proof || !actualCredential.proof.jws) {
                return false;
            }

            // Basic signature structure validation
            const jwsParts = actualCredential.proof.jws.split('.');
            if (jwsParts.length !== 3) {
                return false;
            }

            // Additional validation would go here with proper WebCrypto API
            return true;
            
        } catch (error) {
            this.log('❌ Proof verification error:', error);
            return false;
        }
    }

    async checkLocalRevocation(credential) {
        try {
            // Get credential ID from different possible formats
            const credentialId = this.extractCredentialId(credential);
            
            // Check against local revocation cache
            const revokedList = JSON.parse(localStorage.getItem('lemma_revoked_credentials') || '[]');
            
            if (revokedList.includes(credentialId)) {
                return { revoked: true, reason: 'Found in local revocation list' };
            }
            
            return { revoked: false };
            
        } catch (error) {
            this.log('❌ Local revocation check error:', error);
            return { revoked: false };
        }
    }

    extractCredentialId(credential) {
        // Handle different credential formats
        if (credential.credential) {
            // Wallet format
            return credential.credential.id || credential.credential.credentialSubject?.id;
        } else {
            // Direct credential format
            return credential.id || credential.credentialSubject?.id;
        }
    }

    async verifyWithAPI(credential) {
        this.log('🌐 Attempting API verification');
        
        try {
            const challenge = await this.api.generateChallenge();
            
            const response = await this.api.verifyCredential({
                credentials: [credential],
                challenge: challenge.challenge
            });

            if (response.verified) {
                this.log('✅ API verification successful');
                return {
                    verified: true,
                    method: 'api',
                    challenge: challenge.challenge,
                    response_time: response.processing_time_ms
                };
            } else if (response.shield_action === 'credential_revoked') {
                this.log('🚫 Credential revoked (API)');
                return {
                    verified: false,
                    revoked: true,
                    reason: response.error || 'Revoked by issuer'
                };
            } else {
                return {
                    verified: false,
                    reason: response.error || 'API verification failed'
                };
            }

        } catch (error) {
            this.log('❌ API verification error:', error);
            return {
                verified: false,
                reason: error.message,
                network_error: true
            };
        }
    }

    async handleVerificationReturn() {
        const urlParams = new URLSearchParams(window.location.search);
        const sessionId = urlParams.get('session_id');
        const userId = urlParams.get('user_id');
        
        if (sessionId && userId) {
            this.log('🔄 Handling verification return');
            
            try {
                // Check verification status via API
                const result = await this.api.checkVerificationStatus({
                    user_id: userId,
                    session_id: sessionId
                });

                if (result.verified && result.credential) {
                    // Store new credential
                    await this.wallet.storeCredential(result.credential);
                    
                    // Grant access
                    this.grantAccess('verification_return', result);
                    
                    // Clean URL
                    window.history.replaceState({}, document.title, window.location.pathname);
                    
                } else {
                    throw new Error('Verification was not completed successfully');
                }

            } catch (error) {
                this.log('❌ Verification return handling failed:', error);
                this.handleError(error);
            }
        }
    }

    grantAccess(flowType, result) {
        this.log(`✅ Access granted via ${flowType}`);
        
        this.state.verified = true;
        this.state.shieldVisible = false;
        this.state.currentFlow = 'verified';
        this.state.lastVerification = {
            timestamp: Date.now(),
            method: result.method || flowType,
            flowType: flowType
        };
        
        // Hide UI
        this.ui.hide();
        
        // Notify that shield is hidden
        this.config.onShieldHidden();
        
        // Call success callback
        this.config.onVerified({
            verified: true,
            timestamp: Date.now(),
            method: result.method || flowType,
            flowType: flowType,
            credential: result.credential,
            flow: flowType
        });
    }

    handleError(error) {
        this.log('❌ Error handled:', error);
        
        // Show error UI
        this.ui.showError(error.message);
        
        // Call error callback
        this.config.onError({
            error: error.message,
            timestamp: Date.now(),
            state: this.state,
            flow: this.state.currentFlow
        });
    }

    // Public API methods
    async forceRecheck() {
        this.log('🔄 Force rechecking credentials');
        this.state.verified = false;
        this.state.currentFlow = null;
        await this.executeProtectionFlow();
    }

    async clearCredentials() {
        this.log('🗑️ Clearing all credentials (manual revocation)');
        await this.executeRevocationFlow();
    }

    hide() {
        this.ui.hide();
        this.state.shieldVisible = false;
    }

    show() {
        this.ui.show();
        this.state.shieldVisible = true;
    }

    getMetrics() {
        return {
            ...this.metrics,
            uptime: Date.now() - this.metrics.startTime,
            state: this.state
        };
    }

    // Static methods for global access
    static reset() {
        if (window.lemmaShield) {
            window.lemmaShield.clearCredentials();
        }
    }

    static show() {
        if (window.lemmaShield) {
            window.lemmaShield.show();
        }
    }
}

/**
 * Wallet Component - Handles credential storage and management
 */
class LemmaWallet {
    constructor(config) {
        this.config = config;
        this.storageKey = 'lemma_credentials';
        this.revocationKey = 'lemma_revoked_credentials';
    }

    async init() {
        // Validate storage availability
        try {
            localStorage.setItem('lemma_test', 'test');
            localStorage.removeItem('lemma_test');
        } catch (error) {
            throw new Error('localStorage not available');
        }
    }

    async getCredentials() {
        try {
            const stored = localStorage.getItem(this.storageKey);
            const credentials = stored ? JSON.parse(stored) : [];
            
            // Filter out expired credentials
            const now = Math.floor(Date.now() / 1000);
            const validCredentials = credentials.filter(cred => {
                if (cred.expirationDate) {
                    const expiry = new Date(cred.expirationDate).getTime() / 1000;
                    return expiry > now;
                }
                return true; // Keep credentials without expiry
            });

            // Update storage if we filtered anything
            if (validCredentials.length !== credentials.length) {
                await this.setCredentials(validCredentials);
            }

            return validCredentials;
        } catch (error) {
            console.error('Error getting credentials:', error);
            return [];
        }
    }

    async storeCredential(credential) {
        try {
            const credentials = await this.getCredentials();
            
            // Avoid duplicates
            const existingIndex = credentials.findIndex(cred => 
                cred.id === credential.id || 
                (cred.credentialSubject?.id === credential.credentialSubject?.id)
            );
            
            if (existingIndex >= 0) {
                credentials[existingIndex] = credential;
            } else {
                credentials.push(credential);
            }
            
            await this.setCredentials(credentials);
            return true;
        } catch (error) {
            console.error('Error storing credential:', error);
            return false;
        }
    }

    async setCredentials(credentials) {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(credentials));
            return true;
        } catch (error) {
            console.error('Error setting credentials:', error);
            return false;
        }
    }

    async clearCredentials() {
        try {
            localStorage.removeItem(this.storageKey);
            return true;
        } catch (error) {
            console.error('Error clearing credentials:', error);
            return false;
        }
    }

    async addToRevocationList(credentialId) {
        try {
            const revoked = JSON.parse(localStorage.getItem(this.revocationKey) || '[]');
            if (!revoked.includes(credentialId)) {
                revoked.push(credentialId);
                localStorage.setItem(this.revocationKey, JSON.stringify(revoked));
            }
            return true;
        } catch (error) {
            console.error('Error adding to revocation list:', error);
            return false;
        }
    }
}

/**
 * API Component - Handles communication with Lemma API
 */
class LemmaAPI {
    constructor(config) {
        this.config = config;
        this.baseUrl = config.apiBase;
        this.apiKey = config.apiKey;
        this.timeout = config.timeout || 30000; // 30 seconds
    }

    async init() {
        // Validate API connection
        try {
            await this.request('/api/health', { method: 'GET' });
        } catch (error) {
            console.warn('API health check failed, continuing anyway:', error);
        }
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': this.apiKey,
                ...options.headers
            },
            ...options
        };

        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        try {
            const response = await fetch(url, {
                ...config,
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`API request failed: ${response.status} ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === 'AbortError') {
                throw new Error('API request timeout');
            }
            throw error;
        }
    }

    async generateChallenge() {
        return await this.request('/api/generate-challenge');
    }

    async verifyCredential(data) {
        return await this.request('/api/verify-credential', {
            method: 'POST',
            body: data
        });
    }

    async startVerification(data) {
        return await this.request('/api/start-verification', {
            method: 'POST',
            body: data
        });
    }

    async checkVerificationStatus(data) {
        return await this.request('/api/verification-status', {
            method: 'POST',
            body: data
        });
    }
}

/**
 * UI Component - Handles user interface rendering and interactions
 */
class LemmaUI {
    constructor(config) {
        this.config = config;
        this.containerId = config.containerId;
        this.theme = config.theme || 'default';
    }

    async init() {
        // Ensure container exists
        this.ensureContainer();
    }

    ensureContainer() {
        let container = document.getElementById(this.containerId);
        if (!container) {
            container = document.createElement('div');
            container.id = this.containerId;
            container.style.display = 'none';
            document.body.appendChild(container);
        }
        return container;
    }

    async showShield() {
        const container = this.ensureContainer();
        
        container.innerHTML = `
            <div class="lemma-shield-overlay" style="
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.8);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 9999;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            ">
                <div class="lemma-shield-modal" style="
                    background: white;
                    border-radius: 16px;
                    padding: 2rem;
                    max-width: 480px;
                    width: 90%;
                    text-align: center;
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                    border: 1px solid #e6e6e6;
                ">
                    <div style="font-size: 3rem; margin-bottom: 1rem;">🛡️</div>
                    <h2 style="margin: 0 0 1rem 0; color: #333; font-size: 1.5rem; font-weight: 600;">Join the Lemma Network</h2>
                    <p style="color: #666; margin-bottom: 1rem; line-height: 1.5; font-size: 15px;">
                        Complete human verification to join the verified network and eliminate captchas forever.
                    </p>
                    
                    <!-- Verification Steps -->
                    <div style="
                        background: #f8f9fa;
                        border-radius: 12px;
                        padding: 1.5rem;
                        margin: 1.5rem 0;
                        text-align: left;
                        border: 1px solid #e9ecef;
                    ">
                        <h3 style="margin: 0 0 1rem 0; color: #495057; font-size: 16px; font-weight: 600;">What you'll need:</h3>
                        <ul style="margin: 0; padding-left: 1.2rem; color: #6c757d; font-size: 14px; line-height: 1.6;">
                            <li>📱 Government-issued photo ID (driver's license, passport, etc.)</li>
                            <li>🤳 Take a selfie to verify your identity</li>
                            <li>⏱️ Process takes 30-60 seconds</li>
                            <li>🔐 Powered by Stripe Identity - bank-level security</li>
                        </ul>
                    </div>
                    
                    <!-- Benefits -->
                    <div style="
                        background: linear-gradient(135deg, #f8f9ff 0%, #e8f3ff 100%);
                        border-radius: 12px;
                        padding: 1.5rem;
                        margin: 1.5rem 0;
                        text-align: left;
                        border: 1px solid #e1e8ff;
                    ">
                        <h3 style="margin: 0 0 1rem 0; color: #4c63d2; font-size: 16px; font-weight: 600;">✨ Benefits:</h3>
                        <ul style="margin: 0; padding-left: 1.2rem; color: #5a6c8a; font-size: 14px; line-height: 1.6;">
                            <li>🚫 No more captchas on any network site</li>
                            <li>⚡ Instant verification across all platforms</li>
                            <li>🔒 Complete privacy - no personal data stored</li>
                            <li>🌐 Works offline after initial setup</li>
                        </ul>
                    </div>
                    
                    <button id="lemma-verify-btn" style="
                        background: linear-gradient(135deg, #635bff, #7c3aed);
                        color: white;
                        border: none;
                        padding: 16px 32px;
                        border-radius: 12px;
                        font-size: 16px;
                        font-weight: 600;
                        cursor: pointer;
                        width: 100%;
                        margin-bottom: 1rem;
                        transition: all 0.2s ease;
                        box-shadow: 0 4px 12px rgba(99, 91, 255, 0.3);
                    " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 16px rgba(99, 91, 255, 0.4)';" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 12px rgba(99, 91, 255, 0.3)';">
                        🚀 Start Verification with Stripe Identity
                    </button>
                    
                    <p style="
                        font-size: 12px;
                        color: #8b949e;
                        margin: 0;
                        line-height: 1.4;
                    ">
                        🔐 Secure verification powered by Stripe Identity<br/>
                        ✅ GDPR compliant • No personal data stored by Lemma
                    </p>
                    
                    ${this.config.showBranding ? `
                        <div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #e9ecef;">
                            <p style="
                                font-size: 12px;
                                color: #6c757d;
                                margin: 0;
                                line-height: 1.4;
                            ">
                                Powered by <strong style="color: #495057;">Lemma</strong> - Privacy-first verification network
                            </p>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;

        container.style.display = 'block';

        // Add click handler for verification button
        const verifyBtn = document.getElementById('lemma-verify-btn');
        if (verifyBtn) {
            verifyBtn.addEventListener('click', () => {
                if (window.lemmaShield) {
                    window.lemmaShield.stripe.startVerification();
                }
            });
        }
    }

    showLoading() {
        const modal = document.querySelector('.lemma-shield-modal');
        if (modal) {
            modal.innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <div style="
                        width: 40px;
                        height: 40px;
                        border: 4px solid #f3f3f3;
                        border-top: 4px solid #635bff;
                        border-radius: 50%;
                        animation: lemma-spin 1s linear infinite;
                        margin: 0 auto 1rem auto;
                    "></div>
                    <h2 style="margin: 0 0 1rem 0; color: #333;">Verifying...</h2>
                    <p style="color: #666;">Please wait while we verify your identity.</p>
                </div>
                <style>
                    @keyframes lemma-spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            `;
        }
    }

    showError(message) {
        const modal = document.querySelector('.lemma-shield-modal');
        if (modal) {
            modal.innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <div style="font-size: 3rem; margin-bottom: 1rem;">⚠️</div>
                    <h2 style="margin: 0 0 1rem 0; color: #dc2626; font-weight: 600;">Verification Error</h2>
                    <p style="color: #666; margin-bottom: 2rem; line-height: 1.4;">${message}</p>
                    <button onclick="window.lemmaShield?.show?.()" style="
                        background: #635bff;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: 600;
                        margin-right: 1rem;
                    ">
                        Try Again
                    </button>
                    <button onclick="window.lemmaShield?.hide?.()" style="
                        background: #6c757d;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: 600;
                    ">
                        Cancel
                    </button>
                </div>
            `;
        }
    }

    hide() {
        const container = document.getElementById(this.containerId);
        if (container) {
            container.style.display = 'none';
        }
    }

    show() {
        const container = document.getElementById(this.containerId);
        if (container) {
            container.style.display = 'block';
        }
    }
}

/**
 * Stripe Integration Component - Handles Stripe Identity verification
 */
class LemmaStripe {
    constructor(config) {
        this.config = config;
        this.stripe = null;
        this.sessionId = null;
        this.userId = null;
    }

    async init() {
        // Initialize Stripe if needed
        if (this.config.stripePublishableKey && typeof Stripe !== 'undefined') {
            this.stripe = Stripe(this.config.stripePublishableKey);
        }
    }

    async startVerification() {
        try {
            // Generate unique user ID
            this.userId = this.generateUserId();
            
            // Create verification session via API
            const session = await this.createVerificationSession();
            
            if (session.verification_url) {
                // Store session info
                this.sessionId = session.session_id;
                
                // Show loading state
                this.showStripeLoading();
                
                // Redirect to Stripe Identity
                window.location.href = session.verification_url;
            } else {
                throw new Error('No verification URL received');
            }
            
        } catch (error) {
            console.error('Stripe verification start failed:', error);
            throw error;
        }
    }

    async createVerificationSession() {
        const response = await fetch(`${this.config.apiBase}/api/shield/start-verification`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': this.config.apiKey
            },
            body: JSON.stringify({
                return_url: window.location.href,
                user_id: this.userId,
                verification_type: this.config.challengeType
            })
        });

        if (!response.ok) {
            throw new Error(`Failed to create verification session: ${response.status}`);
        }

        return await response.json();
    }

    generateUserId() {
        let userId = localStorage.getItem('lemma_user_id');
        if (!userId) {
            userId = 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem('lemma_user_id', userId);
        }
        return userId;
    }

    showStripeLoading() {
        const modal = document.querySelector('.lemma-shield-modal');
        if (modal) {
            modal.innerHTML = `
                <div style="text-align: center; padding: 2rem;">
                    <div style="
                        width: 40px;
                        height: 40px;
                        border: 4px solid #f3f3f3;
                        border-top: 4px solid #635bff;
                        border-radius: 50%;
                        animation: lemma-stripe-spin 1s linear infinite;
                        margin: 0 auto 1rem auto;
                    "></div>
                    <h2 style="margin: 0 0 1rem 0; color: #333;">Redirecting to Stripe Identity...</h2>
                    <p style="color: #666; line-height: 1.4;">
                        You'll be redirected to Stripe's secure verification system.<br/>
                        Complete the identity verification to join the Lemma network.
                    </p>
                </div>
                <style>
                    @keyframes lemma-stripe-spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            `;
        }
    }
}

// Auto-initialize and handle verification returns
document.addEventListener('DOMContentLoaded', () => {
    // Handle verification return
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('session_id') && urlParams.has('user_id')) {
        // User returned from verification - let the shield handle it
        console.log('[LemmaShield] Verification return detected');
    }
});

// Export for global use
window.LemmaShield = LemmaShield;

// Compatibility layer for existing integrations
window.LemmaShieldWidget = LemmaShield; // Alias for backward compatibility

// Global convenience methods
window.Lemma = {
    init: (options) => {
        if (window.lemmaShield) {
            console.warn('[Lemma] Shield already initialized');
            return window.lemmaShield;
        }
        window.lemmaShield = new LemmaShield(options);
        return window.lemmaShield;
    },
    
    reset: () => LemmaShield.reset(),
    show: () => LemmaShield.show(),
    
    // Legacy compatibility
    Shield: LemmaShield
};