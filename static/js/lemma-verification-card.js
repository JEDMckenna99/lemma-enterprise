/**
 * Lemma Verification Card - Standalone Widget
 * ==========================================
 * 
 * STANDALONE VERIFICATION CARD - Drop anywhere on your site:
 * 1. Works independently without full shield protection
 * 2. Shows verification status and allows one-click verification
 * 3. Integrates with federated network for cross-site credentials
 * 4. Configurable appearance and behavior
 * 5. Microsecond verification with 99.9% offline operation
 * 
 * Usage Examples:
 * 
 * <!-- Simple drop-in card -->
 * <div data-lemma-card></div>
 * 
 * <!-- Custom styled card -->
 * <div data-lemma-card 
 *      data-theme="minimal" 
 *      data-size="compact"
 *      data-show-status="true"></div>
 * 
 * <!-- Programmatic usage -->
 * new LemmaVerificationCard({
 *   target: '#my-verification-area',
 *   theme: 'professional',
 *   onVerified: (result) => console.log('User verified!', result)
 * });
 */

class LemmaVerificationCard {
    constructor(options = {}) {
        this.config = {
            // Core configuration
            apiKey: options.apiKey || this.getApiKeyFromScript() || 'demo-integration-key-12345',
            apiBase: options.apiBase || window.location.origin,
            debug: options.debug !== false,
            
            // Card appearance
            theme: options.theme || 'default', // 'default', 'minimal', 'professional', 'compact'
            size: options.size || 'normal', // 'compact', 'normal', 'large'
            showStatus: options.showStatus !== false, // Show verification status
            showLogo: options.showLogo !== false, // Show Lemma logo
            
            // Behavior
            autoVerify: options.autoVerify === true, // Auto-start verification on load
            showAlways: options.showAlways === true, // Show card even when verified
            target: options.target || null, // Target element selector
            
            // Security configuration (SAME AS SHIELD)
            securityLevel: options.securityLevel || 'medium', // 'low', 'medium', 'high', 'critical', 'realtime'
            customCheckInterval: options.customCheckInterval || null, // Custom interval in milliseconds
            checkOnEvents: options.checkOnEvents || ['entry', 'checkout', 'sensitive_action'],
            backgroundChecks: options.backgroundChecks !== false, // Default enabled
            onSecurityEvent: options.onSecurityEvent || null, // Custom security event handler
            
            // Callbacks
            onVerified: options.onVerified || null,
            onVerificationStart: options.onVerificationStart || null,
            onError: options.onError || null
        };
        
        this.state = {
            initialized: false,
            hasCredentials: false,
            verifying: false,
            checking: false,
            cardElement: null
        };
        
        // Initialize federated wallet for network access
        this.initializeFederatedWallet();
        
        if (this.config.debug) {
            console.log('🎯 Lemma Verification Card initialized', this.config);
        }
    }
    
    /**
     * Get API key from script tag data attribute
     */
    getApiKeyFromScript() {
        const scripts = document.querySelectorAll('script[src*="lemma-verification-card"]');
        for (const script of scripts) {
            const apiKey = script.getAttribute('data-api-key');
            if (apiKey) return apiKey;
        }
        return null;
    }
    
    /**
     * Initialize federated wallet for network access (EXACT SAME as shield)
     */
    async initializeFederatedWallet() {
        try {
            // Fetch network configuration from server (same as shield)
            const configResponse = await fetch(`${this.config.apiBase}/api/network/client-config`);
            let networkConfig = {
                networkRegistryUrl: this.config.apiBase + '/api/network/sync',
                networkAuthKey: 'lemma_network_federated_sync_2024'
            };
            
            if (configResponse.ok) {
                const serverConfig = await configResponse.json();
                if (serverConfig.success) {
                    networkConfig = {
                        networkRegistryUrl: serverConfig.network_registry_url,
                        networkAuthKey: serverConfig.network_auth_key,
                        syncInterval: serverConfig.sync_interval,
                        federationEndpoints: serverConfig.federation_endpoints,
                        nodeId: serverConfig.node_id
                    };
                    
                    if (this.config.debug) {
                        console.log(`🌐 Verification Card: Loaded network config for ${serverConfig.node_name}:`, networkConfig);
                    }
                }
            }
            
            // Initialize federated wallet with network configuration (same as shield)
            if (typeof LemmaFederatedWallet !== 'undefined') {
                this.backgroundWallet = new LemmaFederatedWallet({
                    debug: this.config.debug,
                    securityLevel: this.config.securityLevel || 'medium',
                    customCheckInterval: this.config.customCheckInterval || null,
                    checkOnEvents: this.config.checkOnEvents || ['entry', 'checkout', 'sensitive_action'],
                    backgroundChecks: this.config.backgroundChecks !== false,
                    onSecurityEvent: this.config.onSecurityEvent || null,
                    ...networkConfig
                });
                
                await this.backgroundWallet.init();
                
                if (this.config.debug) {
                    console.log('🌐 Verification Card: Connected to federated network with same config as shield');
                }
            } else {
                if (this.config.debug) {
                    console.warn('⚠️ Federated wallet not available, using standalone mode');
                }
            }
        } catch (error) {
            if (this.config.debug) {
                console.warn('⚠️ Verification Card: Failed to initialize federated wallet:', error.message);
            }
        }
    }
    
    /**
     * Render the verification card in the target element
     */
    async render(targetSelector) {
        const target = typeof targetSelector === 'string' 
            ? document.querySelector(targetSelector) 
            : targetSelector;
            
        if (!target) {
            console.error('❌ Target element not found:', targetSelector);
            return;
        }
        
        // Check current verification status
        const hasCredentials = await this.checkCredentials();
        
        // Create card based on current status
        this.createCard(target, hasCredentials);
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Auto-verify if configured
        if (this.config.autoVerify && !hasCredentials) {
            setTimeout(() => this.startVerification(), 1000);
        }
        
        this.state.initialized = true;
        
        if (this.config.debug) {
            console.log('🎯 Verification card rendered', { hasCredentials, target: targetSelector });
        }
    }
    
    /**
     * Check for existing credentials using EXACT SAME FLOW as shield
     * This performs full cryptographic verification, not just existence check
     */
    async checkCredentials() {
        if (this.state.checking) return false;
        
        this.state.checking = true;
        
        try {
            if (this.config.debug) {
                console.log('🔍 Verification Card: Checking background wallet for existing lemma...');
            }
            
            // EXACT SAME LOGIC as shield: Check background wallet (client-side, works across all sites)
            const hasCredentials = await this.backgroundWallet.hasValidCredentials('identity');
            
            if (hasCredentials) {
                // Get stored credentials for verification
                const credentials = await this.backgroundWallet.getCredentials('identity');
                if (credentials.length > 0) {
                    const credential = credentials[0];
                    
                    if (this.config.debug) {
                        console.log('🔐 Verification Card: Found credential, performing full verification...', {
                            credentialId: credential.id,
                            packageType: credential.packageType,
                            isHuman: credential.claims?.isHuman,
                            storedAt: new Date(credential.storedAt).toLocaleString()
                        });
                    }
                    
                    // CRITICAL: Perform FULL VERIFICATION using same engine as shield
                    const verificationResult = await this.backgroundWallet.verifyCredential(credential);
                    
                    if (verificationResult.verified) {
                        this.state.hasCredentials = true;
                        
                        if (this.config.debug) {
                            console.log('✅ Verification Card: Credential verified successfully', {
                                credentialId: credential.id,
                                confidence: verificationResult.confidence,
                                verificationTimeUs: verificationResult.verification_time_us,
                                engine: verificationResult.engine,
                                offline: verificationResult.offline
                            });
                        }
                        
                        return true;
                    } else {
                        if (this.config.debug) {
                            console.log('❌ Verification Card: Credential verification failed', {
                                credentialId: credential.id,
                                reason: verificationResult.reason || 'verification_failed'
                            });
                        }
                        
                        // Remove invalid credential from wallet
                        await this.backgroundWallet.removeCredential(credential.id);
                        this.state.hasCredentials = false;
                        return false;
                    }
                }
            }
            
            if (this.config.debug) {
                console.log('ℹ️ Verification Card: No valid lemma found in background wallet');
            }
            
            this.state.hasCredentials = false;
            return false;
            
        } catch (error) {
            console.error('❌ Verification Card: Error checking background wallet:', error);
            this.state.hasCredentials = false;
            return false;
        } finally {
            this.state.checking = false;
        }
    }
    
    /**
     * Create the verification card HTML
     */
    createCard(target, hasCredentials) {
        const themes = this.getThemeStyles();
        const currentTheme = themes[this.config.theme] || themes.default;
        
        let cardContent;
        
        if (hasCredentials && !this.config.showAlways) {
            // User is verified - show success state
            cardContent = this.createVerifiedCard(currentTheme);
        } else if (hasCredentials && this.config.showAlways) {
            // User is verified but show card anyway - show status
            cardContent = this.createStatusCard(currentTheme, true);
        } else {
            // User needs verification - show verification card
            cardContent = this.createVerificationCard(currentTheme);
        }
        
        target.innerHTML = cardContent;
        this.state.cardElement = target;
    }
    
    /**
     * Create verification card for unverified users
     */
    createVerificationCard(theme) {
        const sizeClass = this.config.size === 'compact' ? 'compact' : 
                         this.config.size === 'large' ? 'large' : 'normal';
        
        return `
            <div class="lemma-verification-card ${sizeClass}" style="${theme.container}">
                ${this.config.showLogo ? `
                    <div style="margin: 0 auto 1rem; text-align: center;">
                        <img src="/static/img/lemma_logo.svg" alt="Lemma" style="width: 160px; height: 160px;">
                    </div>
                ` : ''}
                
                <div style="${theme.content}">
                    <p style="${theme.description}">One-time verification • Works across the network</p>
                    
                    <button id="lemma-verify-btn" style="${theme.button}" 
                            onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(0,0,0,0.15)'" 
                            onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='${theme.buttonShadow}'">
                        Verify with Lemma
                    </button>
                    
                    <p style="${theme.footer}">Powered by Lemma • Microsecond verification</p>
                </div>
            </div>
        `;
    }
    
    /**
     * Create success card for verified users
     */
    createVerifiedCard(theme) {
        return `
            <div class="lemma-verification-card verified" style="${theme.container.replace('#667eea', '#10b981')}">
                <div style="margin: 0 auto 1rem; text-align: center;">
                    <img src="/static/img/lemma_logo.svg" alt="Lemma" style="width: 80px; height: 80px;">
                </div>
                
                <div style="${theme.content}">
                    <h3 style="${theme.title}">Verified Human</h3>
                    <p style="${theme.description}">Your Lemma is active across the network</p>
                    
                    ${this.config.showStatus ? `
                        <div style="${theme.status}">
                            <span style="color: #10b981;">✅</span>
                            <span style="font-size: 0.875rem; color: #059669;">Verified & Protected</span>
                        </div>
                    ` : ''}
                    
                    <button style="${theme.button.replace('#667eea 0%, #764ba2 100%', '#10b981 0%, #059669 100%')}" 
                            onclick="window.open('/wallet', '_blank')"
                            onmouseover="this.style.transform='translateY(-1px)'" 
                            onmouseout="this.style.transform='translateY(0)'">
                        Open Wallet
                    </button>
                    
                    <p style="${theme.footer}">Protected by Lemma • Active verification</p>
                </div>
            </div>
        `;
    }
    
    /**
     * Create status card (shows verification status)
     */
    createStatusCard(theme, isVerified) {
        const statusColor = isVerified ? '#10b981' : '#f59e0b';
        const statusText = isVerified ? 'Verified & Active' : 'Verification Required';
        const statusIcon = isVerified ? '✅' : '⚡';
        
        return `
            <div class="lemma-verification-card status" style="${theme.container}">
                ${this.config.showLogo ? `
                    <div style="margin: 0 auto 1rem; text-align: center;">
                        <img src="/static/img/lemma_logo.svg" alt="Lemma" style="width: 160px; height: 160px;">
                    </div>
                ` : ''}
                
                <div style="${theme.content}">
                    <h3 style="${theme.title}">Lemma Status</h3>
                    
                    <div style="${theme.status}">
                        <span style="color: ${statusColor};">${statusIcon}</span>
                        <span style="font-size: 0.875rem; color: ${statusColor};">${statusText}</span>
                    </div>
                    
                    ${!isVerified ? `
                        <button id="lemma-verify-btn" style="${theme.button}" 
                                onmouseover="this.style.transform='translateY(-1px)'" 
                                onmouseout="this.style.transform='translateY(0)'">
                            Verify Now
                        </button>
                    ` : `
                        <button style="${theme.button.replace('#667eea 0%, #764ba2 100%', '#10b981 0%, #059669 100%')}" 
                                onclick="window.open('/wallet', '_blank')"
                                onmouseover="this.style.transform='translateY(-1px)'" 
                                onmouseout="this.style.transform='translateY(0)'">
                            Manage Credentials
                        </button>
                    `}
                    
                    <p style="${theme.footer}">Lemma Network • Cross-site verification</p>
                </div>
            </div>
        `;
    }
    
    /**
     * Get theme styles based on configuration
     */
    getThemeStyles() {
        const baseStyles = {
            container: `
                max-width: 320px;
                margin: 1rem auto;
                padding: 1.5rem;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                text-align: center;
                border: 2px solid #667eea;
                transition: all 0.3s ease;
            `,
            icon: `
                width: 48px;
                height: 48px;
                margin: 0 auto 1rem;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 20px;
                font-weight: bold;
            `,
            content: `
                display: flex;
                flex-direction: column;
                gap: 0.75rem;
            `,
            title: `
                margin: 0;
                color: #1f2937;
                font-size: 1.125rem;
                font-weight: 600;
            `,
            description: `
                margin: 0;
                color: #6b7280;
                font-size: 0.875rem;
                line-height: 1.4;
            `,
            status: `
                display: none;
            `,
            button: `
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 8px;
                font-size: 0.9rem;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                width: 100%;
                box-shadow: 0 2px 8px rgba(102, 126, 234, 0.25);
            `,
            buttonShadow: 'none',
            footer: `
                margin: 0;
                color: #9ca3af;
                font-size: 0.75rem;
            `
        };
        
        return {
            default: baseStyles,
            
            minimal: {
                ...baseStyles,
                container: baseStyles.container.replace('1.5rem', '1rem').replace('border: 2px solid #e5e7eb;', 'border: 1px solid #e5e7eb;'),
                icon: baseStyles.icon.replace('48px', '36px').replace('20px', '16px'),
                title: baseStyles.title.replace('1.125rem', '1rem'),
                description: baseStyles.description.replace('0.875rem', '0.8rem')
            },
            
            professional: {
                ...baseStyles,
                container: `
                    max-width: 380px;
                    margin: 1rem auto;
                    padding: 2rem;
                    background: linear-gradient(135deg, #f8fafc 0%, #ffffff 100%);
                    border-radius: 16px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
                    text-align: center;
                    border: 2px solid #667eea;
                    transition: all 0.3s ease;
                `,
                icon: `
                    width: 60px;
                    height: 60px;
                    margin: 0 auto 1.5rem;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                `,
                button: `
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    padding: 1rem 2rem;
                    border-radius: 12px;
                    font-size: 1rem;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s;
                    width: 100%;
                    letter-spacing: 0.5px;
                `,
                title: baseStyles.title.replace('1.125rem', '1.25rem').replace('#1f2937', '#1a1a1a'),
                buttonShadow: '0 4px 12px rgba(102, 126, 234, 0.3)'
            },
            
            compact: {
                ...baseStyles,
                container: `
                    max-width: 240px;
                    margin: 0.5rem auto;
                    padding: 1rem;
                    background: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    text-align: center;
                    border: 1px solid #e5e7eb;
                    transition: all 0.3s ease;
                `,
                icon: baseStyles.icon.replace('48px', '32px').replace('20px', '14px').replace('1rem', '0.5rem'),
                title: baseStyles.title.replace('1.125rem', '0.95rem'),
                description: baseStyles.description.replace('0.875rem', '0.75rem'),
                button: baseStyles.button.replace('0.75rem 1.5rem', '0.5rem 1rem').replace('0.9rem', '0.8rem')
            }
        };
    }
    
    /**
     * Setup event listeners for the card
     */
    setupEventListeners() {
        // Listen for verification button clicks
        const verifyBtn = this.state.cardElement.querySelector('#lemma-verify-btn');
        if (verifyBtn) {
            if (this.config.debug) {
                console.log('🎯 Verification Card: Setting up click listener for verify button');
            }
            verifyBtn.addEventListener('click', (event) => {
                event.preventDefault();
                if (this.config.debug) {
                    console.log('🎯 Verification Card: Verify button clicked - starting verification...');
                }
                this.startVerification();
            });
        } else {
            if (this.config.debug) {
                console.warn('⚠️ Verification Card: Verify button not found for event listener');
            }
        }
        
        // Listen for credential updates from other tabs/widgets
        window.addEventListener('lemma-credentials-updated', (event) => {
            this.handleCredentialUpdate(event.detail);
        });
        
        // Listen for card refresh events
        window.addEventListener('lemma-card-refresh', () => {
            this.refresh();
        });
    }
    
    /**
     * Handle credential updates from federated network
     */
    async handleCredentialUpdate(detail) {
        if (this.config.debug) {
            console.log('🎯 Verification card received credential update:', detail);
        }
        
        // Refresh the card to show updated status
        await this.refresh();
        
        // Call verification callback if user just got verified
        if (detail.action === 'added' && this.config.onVerified) {
            this.config.onVerified({
                verified: true,
                source: 'network_update',
                credentialId: detail.credentialId
            });
        }
    }
    
    /**
     * Start the verification process
     */
    async startVerification() {
        if (this.config.debug) {
            console.log('🚀 Verification Card: startVerification() called');
        }
        
        if (this.state.verifying) {
            if (this.config.debug) {
                console.log('⚠️ Verification Card: Already verifying, skipping...');
            }
            return;
        }
        
        this.state.verifying = true;
        
        // Update button to show loading state (using shield's exact logic)
        const verifyBtn = this.state.cardElement.querySelector('#lemma-verify-btn');
        if (verifyBtn) {
            const originalText = verifyBtn.textContent;
            verifyBtn.textContent = 'Starting verification...';
            verifyBtn.disabled = true;
            
            if (this.config.debug) {
                console.log('🎯 Verification Card: Button updated to loading state');
            }
        }
        
        // Call verification start callback
        if (this.config.onVerificationStart) {
            this.config.onVerificationStart();
        }
        
        try {
            if (this.config.debug) {
                console.log('🚀 Verification Card: Starting Stripe Identity verification...');
                console.log('🚀 Verification Card: API Base:', this.config.apiBase);
                console.log('🚀 Verification Card: API Key:', this.config.apiKey);
            }
            
            // Start identity verification (using shield's exact API call)
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
                
                // Store session info for completion (SAME AS SHIELD)
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
            
            // Reset button (using shield's exact error handling)
            verifyBtn.textContent = 'Verification failed - Try again';
            verifyBtn.disabled = false;
            
            // Call error callback
            if (this.config.onError) {
                this.config.onError(error);
            }
            
            // Reset after 3 seconds
            setTimeout(() => {
                verifyBtn.textContent = originalText;
            }, 3000);
            
        } finally {
            this.state.verifying = false;
        }
    }
    
    /**
     * Update button state
     */
    updateButtonState(state) {
        const verifyBtn = this.state.cardElement?.querySelector('#lemma-verify-btn');
        if (!verifyBtn) return;
        
        const states = {
            ready: { text: 'Verify Identity', disabled: false },
            loading: { text: 'Starting verification...', disabled: true },
            error: { text: 'Verification failed - Try again', disabled: false },
            verified: { text: 'Verified ✅', disabled: true }
        };
        
        const currentState = states[state] || states.ready;
        verifyBtn.textContent = currentState.text;
        verifyBtn.disabled = currentState.disabled;
    }
    
    /**
     * Refresh the card (re-check credentials and update display)
     */
    async refresh() {
        if (!this.state.cardElement) return;
        
        const hasCredentials = await this.checkCredentials();
        this.createCard(this.state.cardElement, hasCredentials);
        this.setupEventListeners();
        
        if (this.config.debug) {
            console.log('🎯 Verification card refreshed', { hasCredentials });
        }
    }
    
    /**
     * Get current verification status
     */
    async getStatus() {
        const hasCredentials = await this.checkCredentials();
        
        return {
            verified: hasCredentials,
            cardInitialized: this.state.initialized,
            verifying: this.state.verifying,
            checking: this.state.checking,
            networkConnected: !!this.backgroundWallet
        };
    }
    
    /**
     * Perform background security check (same as shield)
     */
    async performBackgroundCheck() {
        if (this.config.debug) {
            console.log('🛡️ Verification Card: Performing background security check...');
        }
        
        return await this.backgroundWallet.performBackgroundCheck();
    }
    
    /**
     * Check on specific event (same as shield)
     */
    async checkOnEvent(eventType = 'unknown') {
        if (this.config.debug) {
            console.log(`🛡️ Verification Card: Event-triggered security check: ${eventType}`);
        }
        
        return await this.backgroundWallet.checkOnEvent(eventType);
    }
    
    /**
     * Get security status (same as shield)
     */
    getSecurityStatus() {
        return this.backgroundWallet.getSecurityStatus();
    }
    
    /**
     * Update card configuration
     */
    updateConfig(newConfig) {
        this.config = { ...this.config, ...newConfig };
        
        if (this.state.initialized) {
            this.refresh();
        }
        
        if (this.config.debug) {
            console.log('🎯 Verification card config updated', newConfig);
        }
    }
    
    /**
     * Destroy the card and clean up
     */
    destroy() {
        if (this.state.cardElement) {
            this.state.cardElement.innerHTML = '';
        }
        
        // Remove event listeners
        window.removeEventListener('lemma-credentials-updated', this.handleCredentialUpdate);
        window.removeEventListener('lemma-card-refresh', this.refresh);
        
        if (this.config.debug) {
            console.log('🎯 Verification card destroyed');
        }
    }
}

// Global initialization
window.LemmaVerificationCard = LemmaVerificationCard;

// Auto-initialize cards with data attributes
document.addEventListener('DOMContentLoaded', () => {
    // Find all elements with data-lemma-card attribute
    const cardElements = document.querySelectorAll('[data-lemma-card]');
    
    cardElements.forEach((element, index) => {
        // Get configuration from data attributes
        const config = {
            // Core API configuration
            apiKey: element.getAttribute('data-api-key') || 'demo-integration-key-12345',
            apiBase: element.getAttribute('data-api-base') || window.location.origin,
            debug: element.getAttribute('data-debug') !== 'false',
            
            // Visual configuration
            theme: element.getAttribute('data-theme') || 'default',
            size: element.getAttribute('data-size') || 'normal',
            showStatus: element.getAttribute('data-show-status') !== 'false',
            showLogo: element.getAttribute('data-show-logo') !== 'false',
            
            // Behavior configuration
            autoVerify: element.getAttribute('data-auto-verify') === 'true',
            showAlways: element.getAttribute('data-show-always') === 'true'
        };
        
        // Create and render the card
        const card = new LemmaVerificationCard(config);
        card.render(element);
        
        // Store reference for later access
        element.lemmaCard = card;
        
        if (config.debug) {
            console.log(`🎯 Auto-initialized verification card ${index + 1}`, config);
        }
    });
});

// Utility function for easy programmatic creation
window.createLemmaCard = function(targetSelector, options = {}) {
    const card = new LemmaVerificationCard(options);
    card.render(targetSelector);
    return card;
};

// Handle returns from verification (using shield's exact logic)
window.addEventListener('load', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const verificationReturn = urlParams.get('verification_return');
    
    if (verificationReturn === 'true') {
        // Handle verification completion (same as shield)
        setTimeout(async () => {
            await handleVerificationReturn();
        }, 1000);
    }
});

/**
 * Handle return from Stripe Identity verification (using shield's exact logic)
 */
async function handleVerificationReturn() {
    try {
        // Find the first verification card to get API configuration
        const cardElement = document.querySelector('[data-lemma-card]');
        if (!cardElement || !cardElement.lemmaCard) {
            console.warn('⚠️ No verification card found to complete verification');
            return;
        }
        
        const card = cardElement.lemmaCard;
        const config = card.config;
        
        if (config.debug) {
            console.log('🎉 Processing Stripe verification completion...');
        }
        
        // Get stored session info (SAME AS SHIELD)
        const storedSession = localStorage.getItem('lemma_verification_session');
        let sessionData = null;
        
        if (config.debug) {
            console.log('🔍 Checking localStorage for verification session...');
            console.log('📋 Raw stored session:', storedSession);
            console.log('📋 All localStorage keys:', Object.keys(localStorage));
        }
        
        if (storedSession) {
            try {
                sessionData = JSON.parse(storedSession);
                if (config.debug) {
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
            if (config.debug) {
                console.warn('⚠️ No verification session found in localStorage');
            }
        }
        
        if (!sessionData?.session_id) {
            if (config.debug) {
                console.error('❌ Session validation failed:', {
                    sessionData,
                    hasSessionId: sessionData?.session_id,
                    localStorageKeys: Object.keys(localStorage)
                });
            }
            throw new Error('No verification session found. Please restart the verification process.');
        }
        
        // Complete the identity verification (using shield's exact API call)
        const response = await fetch(`${config.apiBase}/api/sdk/complete-identity-verification`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${config.apiKey}`
            },
            body: JSON.stringify({
                session_id: sessionData?.session_id,
                verification_return: true,
                enable_rust_engine: true
            })
        });
        
        const result = await response.json();
        
        if (result.success && result.verified && result.credential) {
            // Clean up stored session data (SAME AS SHIELD)
            localStorage.removeItem('lemma_verification_session');
            
            // Store credential in background wallet (using shield's exact logic)
            const storeResult = await card.federatedWallet.storeCredential({
                ...result.credential,
                packageType: 'identity',
                networkShared: true,
                expiresAt: Date.now() + (30 * 24 * 60 * 60 * 1000) // 30 days
            });
            
            if (storeResult.success) {
                if (config.debug) {
                    console.log('✅ Lemma credential created and stored in background wallet!', {
                        credential_id: result.credential?.id,
                        verification_time_us: result.verification_time_us,
                        network_shared: storeResult.networkShared,
                        storage_layers: storeResult.layers
                    });
                }
                
                // Clean up URL parameters (shield's exact logic)
                const url = new URL(window.location);
                url.searchParams.delete('verification_return');
                window.history.replaceState({}, document.title, url);
                
                // Call verification callback
                if (config.onVerified) {
                    config.onVerified({
                        verified: true,
                        source: 'stripe_verification',
                        credential: result.credential,
                        verificationTimeUs: result.verification_time_us
                    });
                }
                
                // Trigger card refresh for all cards on the page
                window.dispatchEvent(new CustomEvent('lemma-card-refresh'));
                
                // Notify other components of successful verification
                window.dispatchEvent(new CustomEvent('lemma-credentials-updated', {
                    detail: {
                        action: 'added',
                        credentialId: result.credential?.id,
                        source: 'verification_card'
                    }
                }));
                
            } else {
                throw new Error('Failed to store credential in background wallet');
            }
            
        } else {
            throw new Error(result.message || 'Credential creation failed');
        }
        
    } catch (error) {
        console.error('❌ Failed to complete verification:', error);
        
        // Find cards and call error callback
        const cardElements = document.querySelectorAll('[data-lemma-card]');
        cardElements.forEach(element => {
            if (element.lemmaCard && element.lemmaCard.config.onError) {
                element.lemmaCard.config.onError(error);
            }
        });
        
        // Still clean up URL even on error
        const url = new URL(window.location);
        url.searchParams.delete('verification_return');
        window.history.replaceState({}, document.title, url);
    }
}
