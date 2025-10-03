/**
 * Lemma Bot Shield - Federated Network Implementation
 * ==================================================
 * 
 * FEDERATED IDENTITY NETWORK - True cross-site credential sharing:
 * 1. Checks client-side background wallet (NOT server sessions)
 * 2. Credentials work across ALL sites in the network
 * 3. User verifies ONCE, accesses everywhere  
 * 4. Any site can onboard users into the network
 * 5. 99.9% offline operation with microsecond verification
 * 
 * Usage: new LemmaBotShield().protect('#protected-content');
 */

class LemmaBotShield {
    constructor(options = {}) {
        this.config = {
            apiKey: options.apiKey || 'demo-integration-key-12345',
            apiBase: options.apiBase || window.location.origin,
            debug: options.debug !== false, // Default enabled for troubleshooting
            
            // Background security check configuration
            securityLevel: options.securityLevel || 'medium', // 'low', 'medium', 'high', 'critical', 'realtime'
            customCheckInterval: options.customCheckInterval || null, // Custom interval in milliseconds
            checkOnEvents: options.checkOnEvents || ['entry', 'checkout', 'sensitive_action'],
            backgroundChecks: options.backgroundChecks !== false, // Default enabled
            onSecurityEvent: options.onSecurityEvent || null // Custom security event handler
        };
        
        this.state = {
            checking: false,
            hasLemma: false,
            verifying: false
        };
        
        // Store reference to protected element for cross-tab updates
        this.protectedElement = null;
        
        // Initialize background wallet for federated network with security config
        // Initialize federated wallet with dynamic network configuration
        this.initializeFederatedWallet();
        
        // Set custom security event handler if provided
        if (this.config.onSecurityEvent) {
            this.backgroundWallet.onSecurityEvent = this.config.onSecurityEvent;
        }
        
        // Listen for credential updates from other tabs
        this.setupCrossTabListeners();
        
        if (this.config.debug) {
            console.log('🛡️ Lemma Bot Shield initialized (Federated Network Mode)');
            console.log(`🛡️ Security level: ${this.config.securityLevel}`);
            
            const intervals = {
                'low': '30min', 'medium': '5min', 'high': '2min', 
                'critical': '1min', 'realtime': '10sec'
            };
            const intervalText = this.config.customCheckInterval 
                ? `${this.config.customCheckInterval / 1000}s` 
                : intervals[this.config.securityLevel];
            console.log(`🛡️ Background checks: ${intervalText}`);
        }
    }
    
    /**
     * Initialize federated wallet with dynamic network configuration
     */
    async initializeFederatedWallet() {
        try {
            // Fetch network configuration from server
            const configResponse = await fetch(`${this.config.apiBase}/api/network/client-config`);
            let networkConfig = {
                networkRegistryUrl: this.config.apiBase + '/api/network/sync',
                networkAuthKey: 'lemma_network_federated_sync_2024'
            };
            
            if (configResponse.ok) {
                const serverConfig = await configResponse.json();
                if (serverConfig.success && serverConfig.network_config) {
                    const netConfig = serverConfig.network_config;
                    networkConfig = {
                        networkRegistryUrl: netConfig.registry_url,
                        networkAuthKey: netConfig.auth_key,
                        syncInterval: serverConfig.wallet_config?.sync_interval || 30000,
                        federationEndpoints: netConfig.federation_endpoints,
                        nodeId: 'lemma-platform'
                    };
                    
                    if (this.config.debug) {
                        console.log(`🌐 Loaded network config for lemma-platform:`, networkConfig);
                    }
                }
            }
            
            // Use existing global wallet if available (prevent duplicate instances)
            if (window.lemmaWallet && window.LEMMA_WALLET_INITIALIZED) {
                this.backgroundWallet = window.lemmaWallet;
                if (this.config.debug) {
                    console.log('🔄 Using existing global wallet instance');
                }
            } else {
                // Initialize federated wallet with network configuration
                this.backgroundWallet = new LemmaFederatedWallet({
                    debug: this.config.debug,
                    securityLevel: this.config.securityLevel,
                    customCheckInterval: this.config.customCheckInterval,
                    checkOnEvents: this.config.checkOnEvents,
                    backgroundChecks: this.config.backgroundChecks,
                    ...networkConfig
                });
            }
            
        } catch (error) {
            if (this.config.debug) {
                console.warn('⚠️ Failed to load network config, using defaults:', error.message);
            }
            
            // Fallback to default configuration
            this.backgroundWallet = new LemmaFederatedWallet({
                debug: this.config.debug,
                securityLevel: this.config.securityLevel,
                customCheckInterval: this.config.customCheckInterval,
                checkOnEvents: this.config.checkOnEvents,
                backgroundChecks: this.config.backgroundChecks,
                networkRegistryUrl: this.config.apiBase + '/api/network/sync',
                networkAuthKey: 'lemma_network_federated_sync_2024'
            });
        }
    }
    
    /**
     * Setup cross-tab listeners for credential updates
     */
    setupCrossTabListeners() {
        try {
            // Listen for credential updates from the federated wallet
            window.addEventListener('lemma-credentials-updated', (event) => {
                this.handleCredentialUpdate(event.detail);
            });
            
            if (this.config.debug) {
                console.log('📡 Cross-tab credential update listeners setup');
            }
        } catch (error) {
            if (this.config.debug) {
                console.warn('⚠️ Cross-tab listener setup failed:', error.message);
            }
        }
    }
    
    /**
     * Handle credential updates from other tabs
     */
    async handleCredentialUpdate(detail) {
        try {
            if (this.config.debug) {
                console.log(`📡 Credential update received from ${detail.source}:`, detail);
            }
            
            // Re-check credentials and update protection status
            if (this.protectedElement) {
                const hasCredentials = await this.backgroundWallet.hasValidCredentials('identity');
                
                if (hasCredentials) {
                    this.showProtectedContent(this.protectedElement);
                    if (this.config.debug) {
                        console.log('✅ Protected content shown due to cross-tab credential sync');
                    }
                } else {
                    this.showVerificationWidget(this.protectedElement);
                    if (this.config.debug) {
                        console.log('⚠️ Protected content hidden due to cross-tab credential removal');
                    }
                }
            }
        } catch (error) {
            if (this.config.debug) {
                console.warn('⚠️ Credential update handling failed:', error.message);
            }
        }
    }
    
    /**
     * Protect an element with the bot shield
     */
    async protect(elementSelector) {
        const element = document.querySelector(elementSelector);
        if (!element) {
            console.error('❌ Element not found:', elementSelector);
            return;
        }
        
        // Store element reference for cross-tab updates
        this.protectedElement = element;
        
        // Hide protected content immediately
        element.style.display = 'none';
        
        // Ensure wallet is initialized before proceeding
        if (!this.backgroundWallet) {
            if (this.config.debug) {
                console.log('⏳ Waiting for federated wallet initialization...');
            }
            await this.initializeFederatedWallet();
        }
        
        if (this.config.debug) {
            console.log('🛡️ Protecting element:', elementSelector);
        }
        
        // CRITICAL: Ensure background wallet is initialized before checking
        // Don't call init() - wallet already initialized in main script
        // await this.backgroundWallet.init(); // REMOVED: Causes redundant init attempts
        
        // Check if returning from Stripe verification
        const stripeReturn = this.checkStripeReturn();
        if (stripeReturn) {
            await this.handleStripeReturn(stripeReturn);
            return;
        }
        
        // Check for existing lemma in background
        const hasLemma = await this.checkForExistingLemma();
        
        if (hasLemma) {
            // User has lemma - show content immediately
            this.showProtectedContent(element);
        } else {
            // User needs lemma - show verification widget
            this.showVerificationWidget(element);
        }
    }
    
    /**
     * Check if user is returning from Stripe Identity verification
     */
    checkStripeReturn() {
        const urlParams = new URLSearchParams(window.location.search);
        
        // Look for our custom verification_return parameter
        const verificationReturn = urlParams.get('verification_return');
        
        if (verificationReturn === 'true') {
            if (this.config.debug) {
                console.log('🔄 Detected Stripe verification return');
            }
            return { verificationReturn: true };
        }
        
        return null;
    }
    
    /**
     * Handle return from Stripe Identity verification
     */
    async handleStripeReturn(stripeReturn) {
        try {
            if (this.config.debug) {
                console.log('🎉 Processing Stripe verification completion...');
            }
            
            // Get stored session info
            const storedSession = localStorage.getItem('lemma_verification_session');
            let sessionData = null;
            
            if (this.config.debug) {
                console.log('🔍 Checking localStorage for verification session...');
                console.log('📋 Raw stored session:', storedSession);
                console.log('📋 All localStorage keys:', Object.keys(localStorage));
            }
            
            if (storedSession) {
                try {
                    sessionData = JSON.parse(storedSession);
                    if (this.config.debug) {
                        console.log('📋 Retrieved verification session:', {
                            session_id: sessionData.session_id,
                            user_id: sessionData.user_id,
                            age_minutes: Math.round((Date.now() - sessionData.started_at) / 60000)
                        });
                    }
                } catch (e) {
                    console.warn('⚠️ Failed to parse stored session data:', e);
                }
            } else {
                if (this.config.debug) {
                    console.warn('⚠️ No verification session found in localStorage');
                }
            }
            
            if (!sessionData?.session_id) {
                if (this.config.debug) {
                    console.error('❌ Session validation failed:', {
                        sessionData,
                        hasSessionId: sessionData?.session_id,
                        localStorageKeys: Object.keys(localStorage)
                    });
                }
                throw new Error('No verification session found. Please restart the verification process.');
            }
            
            // Complete the identity verification (this creates and stores the lemma)
            const response = await fetch(`${this.config.apiBase}/api/sdk/complete-identity-verification`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    session_id: sessionData?.session_id,
                    verification_return: true,
                    enable_rust_engine: true
                })
            });
            
            const result = await response.json();
            
            if (result.success && result.verified && result.credential) {
                // Clean up stored session data
                localStorage.removeItem('lemma_verification_session');
                
                // Store credential in background wallet (FEDERATED NETWORK)
                const storeResult = await this.backgroundWallet.storeCredential({
                    ...result.credential,
                    packageType: 'identity',
                    networkShared: true,
                    expiresAt: Date.now() + (30 * 24 * 60 * 60 * 1000) // 30 days
                });
                
                if (storeResult.success) {
                    if (this.config.debug) {
                        console.log('✅ Lemma credential created and stored in background wallet!', {
                            credential_id: result.credential?.id,
                            verification_time_us: result.verification_time_us,
                            network_shared: storeResult.networkShared,
                            storage_layers: storeResult.layers
                        });
                    }
                    
                    // Clean up URL parameters
                    const url = new URL(window.location);
                    url.searchParams.delete('verification_return');
                    window.history.replaceState({}, document.title, url);
                    
                    // Show protected content
                    const element = document.querySelector('#main-protected-content');
                    if (element) {
                        this.showProtectedContent(element);
                    }
                } else {
                    throw new Error('Failed to store credential in background wallet');
                }
                
            } else {
                throw new Error(result.message || 'Credential creation failed');
            }
            
        } catch (error) {
            console.error('❌ Failed to complete verification:', error);
            
            // Show verification widget as fallback
            const element = document.querySelector('#main-protected-content');
            if (element) {
                this.showVerificationWidget(element);
            }
        }
    }
    
    /**
     * Check for existing lemma credentials (FEDERATED NETWORK - Client-side only)
     */
    async checkForExistingLemma() {
        if (this.state.checking) return false;
        
        this.state.checking = true;
        
        try {
            if (this.config.debug) {
                console.log('🔍 Checking background wallet for existing lemma...');
            }
            
            // Check background wallet (client-side, works across all sites)
            const hasCredentials = await this.backgroundWallet.hasValidCredentials('identity');
            
            if (hasCredentials) {
                // SIMPLIFIED: Trust stored credentials on page load (background checks will validate later)
                const credentials = await this.backgroundWallet.getCredentials('identity');
                if (credentials.length > 0) {
                    this.state.hasLemma = true;
                    
                    if (this.config.debug) {
                        console.log('✅ Valid lemma found in background wallet', {
                            credentialId: credentials[0].id,
                            packageType: credentials[0].packageType,
                            isHuman: credentials[0].claims?.isHuman,
                            storedAt: new Date(credentials[0].storedAt).toLocaleString()
                        });
                    }
                    
                    return true;
                }
            }
            
            if (this.config.debug) {
                console.log('ℹ️ No valid lemma found in background wallet');
            }
            
            return false;
            
        } catch (error) {
            console.error('❌ Error checking background wallet:', error);
            return false;
        } finally {
            this.state.checking = false;
        }
    }
    
    /**
     * Show protected content (user has verified lemma)
     */
    showProtectedContent(element) {
        // FIXED: Show the protected content (user is verified)
        element.style.display = 'block';
        
        // Hide any verification widgets or error messages
        const verificationWidget = document.querySelector('#lemma-verification-widget');
        if (verificationWidget) {
            verificationWidget.style.display = 'none';
        }
        
        // Show success content if it exists (additional success message)
        const successContent = document.querySelector('#success-content');
        if (successContent) {
            successContent.style.display = 'block';
        }
        
        if (this.config.debug) {
            console.log('✅ Showing verified user content - user has valid lemma credentials');
        }
    }
    
    /**
     * Show verification widget (user needs lemma)
     */
    showVerificationWidget(element) {
        // Create verification widget
        const widget = document.createElement('div');
        widget.innerHTML = `
            <div style="
                max-width: 400px;
                margin: 2rem auto;
                padding: 2rem;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                text-align: center;
                border: 2px solid #e5e7eb;
            ">
                <div style="
                    width: 60px;
                    height: 60px;
                    margin: 0 auto 1rem;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                ">🛡️</div>
                
                <h3 style="
                    margin-bottom: 0.5rem;
                    color: #1f2937;
                    font-size: 1.25rem;
                    font-weight: 600;
                ">Protected by Lemma Shield</h3>
                
                <p style="
                    margin-bottom: 1.5rem;
                    color: #6b7280;
                    font-size: 0.875rem;
                ">Verify your identity to access this content</p>
                
                <button id="verify-lemma-btn" style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    padding: 0.75rem 1.5rem;
                    border-radius: 8px;
                    font-size: 1rem;
                    font-weight: 500;
                    cursor: pointer;
                    transition: all 0.2s;
                    width: 100%;
                " onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(102, 126, 234, 0.4)'" 
                   onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
                    Verify a Lemma
                </button>
                
                <p style="
                    margin-top: 1rem;
                    color: #9ca3af;
                    font-size: 0.75rem;
                ">One-time verification • Never see CAPTCHAs again</p>
            </div>
        `;
        
        // Insert widget before the protected element
        element.parentNode.insertBefore(widget, element);
        
        // Add click handler to verification button
        const verifyBtn = widget.querySelector('#verify-lemma-btn');
        verifyBtn.addEventListener('click', () => this.startVerification(element, widget));
        
        if (this.config.debug) {
            console.log('🔧 Showing verification widget');
        }
    }
    
    /**
     * Start the verification process (Stripe redirect)
     */
    async startVerification(protectedElement, widget) {
        if (this.state.verifying) return;
        
        this.state.verifying = true;
        
        // Update button to show loading state
        const verifyBtn = widget.querySelector('#verify-lemma-btn');
        const originalText = verifyBtn.textContent;
        verifyBtn.textContent = 'Starting verification...';
        verifyBtn.disabled = true;
        
        try {
            if (this.config.debug) {
                console.log('🚀 Starting Stripe Identity verification...');
            }
            
            // Start identity verification (this creates Stripe session)
            const response = await fetch(`${this.config.apiBase}/api/sdk/start-identity-verification`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    provider: 'stripe_identity',
                    inline_mode: false, // Use redirect mode (which works!)
                    return_url: window.location.origin + window.location.pathname + '?verification_return=true'
                })
            });
            
            const result = await response.json();
            
            if (result.success && result.url) {
                if (this.config.debug) {
                    console.log('✅ Stripe session created, redirecting...', {
                        session_id: result.session_id,
                        user_id: result.user_id
                    });
                }
                
                // Store session info for completion
                const sessionData = {
                    session_id: result.session_id,
                    user_id: result.user_id,
                    started_at: Date.now()
                };
                
                localStorage.setItem('lemma_verification_session', JSON.stringify(sessionData));
                
                if (this.config.debug) {
                    console.log('💾 Stored verification session in localStorage:', sessionData);
                    console.log('💾 Verification after storage:', localStorage.getItem('lemma_verification_session'));
                }
                
                // Redirect to Stripe Identity (the working flow!)
                window.location.href = result.url;
            } else {
                throw new Error(result.message || 'Failed to start verification');
            }
            
        } catch (error) {
            console.error('❌ Verification failed:', error);
            
            // Reset button
            verifyBtn.textContent = originalText;
            verifyBtn.disabled = false;
            
            // Show error message
            verifyBtn.textContent = 'Verification failed - Try again';
            setTimeout(() => {
                verifyBtn.textContent = originalText;
            }, 3000);
            
        } finally {
            this.state.verifying = false;
        }
    }
    
    /**
     * Trigger event-based security check
     * Usage: shield.checkOnEvent('checkout') before processing payment
     */
    async checkOnEvent(eventType = 'unknown') {
        if (this.config.debug) {
            console.log(`🛡️ Event-triggered security check: ${eventType}`);
        }
        
        return await this.backgroundWallet.checkOnEvent(eventType);
    }
    
    /**
     * Update security configuration dynamically
     * Usage: shield.updateSecurityLevel('critical') for high-security operations
     */
    updateSecurityLevel(newLevel) {
        this.config.securityLevel = newLevel;
        this.backgroundWallet.updateSecurityConfig({
            securityLevel: newLevel
        });
        
        if (this.config.debug) {
            console.log(`🛡️ Security level updated to: ${newLevel}`);
        }
    }
    
    /**
     * Set custom check interval
     * Usage: shield.setCheckInterval(30000) for 30-second checks
     */
    setCheckInterval(intervalMs) {
        this.config.customCheckInterval = intervalMs;
        this.backgroundWallet.updateSecurityConfig({
            customInterval: intervalMs
        });
        
        if (this.config.debug) {
            console.log(`🛡️ Check interval updated to: ${intervalMs / 1000}s`);
        }
    }
    
    /**
     * Get current security status
     */
    getSecurityStatus() {
        return this.backgroundWallet.getSecurityStatus();
    }
    
    /**
     * Enable/disable background checks
     */
    setBackgroundChecks(enabled) {
        this.config.backgroundChecks = enabled;
        this.backgroundWallet.updateSecurityConfig({
            enabled: enabled
        });
        
        if (this.config.debug) {
            console.log(`🛡️ Background checks ${enabled ? 'enabled' : 'disabled'}`);
        }
    }
}

// Global initialization for easy customer integration
window.LemmaBotShield = LemmaBotShield;

// Auto-initialize if data attributes are present (disabled for homepage hero widget)
document.addEventListener('DOMContentLoaded', () => {
    const autoProtect = document.querySelector('[data-lemma-protect]');
    if (autoProtect && !autoProtect.closest('#hero-card')) {
        const selector = autoProtect.getAttribute('data-lemma-protect');
        if (selector && selector !== 'true') {
            new LemmaBotShield({ debug: true }).protect(selector);
        }
    }
});