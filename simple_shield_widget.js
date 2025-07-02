/**
 * SIMPLIFIED LEMMA SHIELD WIDGET - Clean Bot Shield Circuit
 * Removes all overcomplicated layers and provides a straightforward verification flow
 */

class SimpleLemmaShield {
    constructor(options = {}) {
        this.options = {
            apiKey: options.apiKey || '',
            apiBase: options.apiBase || 'https://lemma.id',
            autoProtect: options.autoProtect !== false,
            debug: options.debug || false,
            ...options
        };
        
        this.initialized = false;
        this.wallet = null;
        this.state = {};
        
        console.log('🛡️ Simplified Lemma Shield initializing...');
    }
    
    async init() {
        if (this.initialized) {
            console.log('⚠️ Shield already initialized');
            return;
        }
        
        try {
            console.log('🚀 Starting simple shield initialization...');
            
            // Wait for wallet if available
            await this.waitForWallet();
            
            // Simple auto-protection check
            if (this.options.autoProtect) {
                await this.checkAndProtect();
            }
            
            this.initialized = true;
            console.log('✅ Simple shield initialized successfully');
            
        } catch (error) {
            console.error('❌ Shield initialization failed:', error);
        }
    }
    
    async waitForWallet() {
        // Simple wallet detection
        if (window.lemmaWallet) {
            this.wallet = window.lemmaWallet;
            console.log('🎯 Wallet found');
        } else {
            console.log('⚠️ No wallet available - shield will work without it');
        }
    }
    
    async checkAndProtect() {
        try {
            console.log('🔍 Checking if protection is needed...');
            
            // Simple credential check
            const hasValidCredential = await this.hasValidCredential();
            
            if (!hasValidCredential) {
                console.log('🛡️ No valid credential - showing shield');
                await this.showShield();
            } else {
                console.log('✅ Valid credential found - access granted');
                this.grantAccess();
            }
            
        } catch (error) {
            console.error('❌ Protection check failed:', error);
            // Default to showing shield on error
            await this.showShield();
        }
    }
    
    async hasValidCredential() {
        try {
            // Check wallet for credentials
            if (this.wallet && this.wallet.getCredentials) {
                const credentials = await this.wallet.getCredentials();
                return credentials && credentials.length > 0;
            }
            
            // Fallback: Check API (minimal calls)
            const response = await fetch(`${this.options.apiBase}/api/shield/status`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                return result.shield_action === 'allow_access';
            }
            
            return false;
            
        } catch (error) {
            console.error('❌ Credential check failed:', error);
            return false;
        }
    }
    
    async showShield() {
        console.log('🛡️ Showing verification shield...');
        
        const container = this.getOrCreateContainer();
        if (!container) return;
        
        // Simple shield UI
        container.innerHTML = `
            <div style="
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.8);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 9999;
            ">
                <div style="
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    max-width: 400px;
                    text-align: center;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                ">
                    <h2 style="margin: 0 0 1rem 0;">🛡️ Verification Required</h2>
                    <p style="margin: 0 0 1.5rem 0;">Please verify your identity to continue</p>
                    <button id="verify-btn" style="
                        background: #10b981;
                        color: white;
                        border: none;
                        padding: 0.75rem 1.5rem;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 1rem;
                    ">Start Verification</button>
                </div>
            </div>
        `;
        
        // Add verification handler
        const verifyBtn = container.querySelector('#verify-btn');
        if (verifyBtn) {
            verifyBtn.onclick = () => this.startVerification();
        }
        
        container.style.display = 'block';
    }
    
    async startVerification() {
        try {
            console.log('🚀 Starting verification process...');
            
            // Simple verification start
            const response = await fetch(`${this.options.apiBase}/api/shield/start-verification`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    return_url: window.location.href
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.verification_url) {
                    // Redirect to verification
                    window.location.href = result.verification_url;
                }
            }
            
        } catch (error) {
            console.error('❌ Verification start failed:', error);
        }
    }
    
    grantAccess() {
        console.log('✅ Access granted - hiding shield');
        
        const container = this.getOrCreateContainer();
        if (container) {
            container.style.display = 'none';
        }
        
        // Remove any overlays or barriers
        document.body.style.overflow = '';
    }
    
    getOrCreateContainer() {
        let container = document.getElementById('lemma-shield-container');
        
        if (!container) {
            container = document.createElement('div');
            container.id = 'lemma-shield-container';
            container.style.display = 'none';
            document.body.appendChild(container);
        }
        
        return container;
    }
    
    // Simple force show method
    forceShow(options = {}) {
        console.log('🚨 Force showing shield');
        this.showShield();
    }
}

// Auto-initialize if configuration is available
document.addEventListener('DOMContentLoaded', () => {
    if (window.LemmaConfig) {
        console.log('🚀 Auto-initializing simplified shield...');
        window.lemmaShield = new SimpleLemmaShield(window.LemmaConfig);
        window.lemmaShield.init();
    }
});

// Export for use
window.SimpleLemmaShield = SimpleLemmaShield; 