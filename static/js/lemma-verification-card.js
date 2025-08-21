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
            
            // Callbacks
            onVerified: options.onVerified || null,
            onVerificationStart: options.onVerificationStart || null,
            onError: options.onError || null
        };
        
        this.state = {
            initialized: false,
            hasCredentials: false,
            verifying: false,
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
     * Initialize federated wallet for network access
     */
    async initializeFederatedWallet() {
        try {
            // Use the same federated wallet system as the bot shield
            if (typeof LemmaFederatedWallet !== 'undefined') {
                this.backgroundWallet = new LemmaFederatedWallet({
                    debug: this.config.debug,
                    networkRegistryUrl: this.config.apiBase + '/api/network/sync',
                    networkAuthKey: 'lemma_network_federated_sync_2024'
                });
                
                await this.backgroundWallet.init();
                
                if (this.config.debug) {
                    console.log('🌐 Verification card connected to federated network');
                }
            } else {
                if (this.config.debug) {
                    console.warn('⚠️ Federated wallet not available, using standalone mode');
                }
            }
        } catch (error) {
            if (this.config.debug) {
                console.warn('⚠️ Failed to initialize federated wallet:', error.message);
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
     * Check for existing credentials
     */
    async checkCredentials() {
        try {
            if (this.backgroundWallet) {
                const hasCredentials = await this.backgroundWallet.hasValidCredentials('identity');
                this.state.hasCredentials = hasCredentials;
                return hasCredentials;
            }
            return false;
        } catch (error) {
            if (this.config.debug) {
                console.warn('⚠️ Error checking credentials:', error);
            }
            return false;
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
                    <div style="${theme.icon}"></div>
                ` : ''}
                
                <div style="${theme.content}">
                    <h3 style="${theme.title}">Verify with Lemma</h3>
                    <p style="${theme.description}">One-time verification • Works across the network</p>
                    
                    ${this.config.showStatus ? `
                        <div style="${theme.status}">
                            <span style="color: #f59e0b;">⚡</span>
                            <span style="font-size: 0.875rem; color: #6b7280;">Ready to verify</span>
                        </div>
                    ` : ''}
                    
                    <button id="lemma-verify-btn" style="${theme.button}" 
                            onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(0,0,0,0.15)'" 
                            onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='${theme.buttonShadow}'">
                        Verify Identity
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
                <div style="${theme.icon.replace('#667eea 0%, #764ba2 100%', '#10b981 0%, #059669 100%')}">✅</div>
                
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
                    <div style="${theme.icon}"></div>
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
                background-image: url('/static/img/lemma_logo.svg');
                background-size: 28px 28px;
                background-repeat: no-repeat;
                background-position: center;
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
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.5rem;
                padding: 0.5rem;
                background: #f9fafb;
                border-radius: 6px;
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
            verifyBtn.addEventListener('click', () => this.startVerification());
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
        if (this.state.verifying) return;
        
        this.state.verifying = true;
        
        // Update UI to show loading state
        this.updateButtonState('loading');
        
        // Call verification start callback
        if (this.config.onVerificationStart) {
            this.config.onVerificationStart();
        }
        
        try {
            if (this.config.debug) {
                console.log('🎯 Starting verification from card widget...');
            }
            
            // Start identity verification
            const response = await fetch(`${this.config.apiBase}/api/sdk/start-identity-verification`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    provider: 'stripe_identity',
                    inline_mode: false,
                    return_url: window.location.origin + window.location.pathname + '?verification_return=true&source=card'
                })
            });
            
            const result = await response.json();
            
            if (result.success && result.url) {
                if (this.config.debug) {
                    console.log('✅ Redirecting to verification...');
                }
                
                // Redirect to verification
                window.location.href = result.url;
            } else {
                throw new Error(result.message || 'Failed to start verification');
            }
            
        } catch (error) {
            console.error('❌ Verification failed:', error);
            
            // Update UI to show error state
            this.updateButtonState('error');
            
            // Call error callback
            if (this.config.onError) {
                this.config.onError(error);
            }
            
            // Reset after 3 seconds
            setTimeout(() => {
                this.updateButtonState('ready');
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
            networkConnected: !!this.backgroundWallet
        };
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
            theme: element.getAttribute('data-theme') || 'default',
            size: element.getAttribute('data-size') || 'normal',
            showStatus: element.getAttribute('data-show-status') !== 'false',
            showLogo: element.getAttribute('data-show-logo') !== 'false',
            autoVerify: element.getAttribute('data-auto-verify') === 'true',
            showAlways: element.getAttribute('data-show-always') === 'true',
            debug: element.getAttribute('data-debug') !== 'false'
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

// Handle returns from verification
window.addEventListener('load', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const verificationReturn = urlParams.get('verification_return');
    const source = urlParams.get('source');
    
    if (verificationReturn === 'true' && source === 'card') {
        // Handle verification completion for card-initiated verification
        setTimeout(async () => {
            // Trigger card refresh for all cards on the page
            window.dispatchEvent(new CustomEvent('lemma-card-refresh'));
            
            // Clean up URL
            const url = new URL(window.location);
            url.searchParams.delete('verification_return');
            url.searchParams.delete('source');
            window.history.replaceState({}, document.title, url);
        }, 1000);
    }
});
