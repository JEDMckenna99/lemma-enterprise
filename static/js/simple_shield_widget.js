/**
 * MINIMAL LEMMA SHIELD - Essential Bot Protection Only
 * Ultra-simple implementation with useful debug logging
 */

class MinimalLemmaShield {
    constructor(options = {}) {
        this.options = {
            apiKey: options.apiKey || '',
            apiBase: options.apiBase || 'https://lemma.id',
            autoProtect: options.autoProtect !== false,
            debug: true, // Always debug for now
            ...options
        };
        
        this.initialized = false;
        this.shieldActive = false;
        
        this.log('🛡️ MINIMAL SHIELD: Initializing...');
    }
    
    log(message, data = null) {
        if (this.options.debug) {
            console.log(`[MINIMAL-SHIELD] ${message}`, data || '');
        }
    }
    
    async init() {
        if (this.initialized) {
            this.log('⚠️ Already initialized - skipping');
            return;
        }
        
        try {
            this.log('🚀 Starting initialization...');
            
            // Simple protection check
            if (this.options.autoProtect) {
                const needsProtection = await this.checkProtectionNeeded();
                this.log(`🔍 Protection needed: ${needsProtection}`);
                
                if (needsProtection) {
                    this.showShield();
                } else {
                    this.grantAccess();
                }
            }
            
            this.initialized = true;
            this.log('✅ Initialization complete');
            
        } catch (error) {
            this.log('❌ Initialization failed:', error.message);
        }
    }
    
    async checkProtectionNeeded() {
        try {
            // Simple API check
            const response = await fetch(`${this.options.apiBase}/api/shield/status`);
            
            if (response.ok) {
                const result = await response.json();
                this.log('📊 API response:', result);
                return result.shield_action !== 'allow_access';
            } else {
                this.log(`⚠️ API error: ${response.status}`);
                return true; // Default to showing shield on error
            }
            
        } catch (error) {
            this.log('❌ Check failed:', error.message);
            return true; // Default to showing shield on error
        }
    }
    
    showShield() {
        if (this.shieldActive) {
            this.log('⚠️ Shield already active');
            return;
        }
        
        this.log('🛡️ Showing shield...');
        this.shieldActive = true;
        
        const container = this.getContainer();
        if (!container) {
            this.log('❌ No container found');
            return;
        }
        
        // Ultra-simple shield UI
        container.innerHTML = `
            <div style="
                position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.8); display: flex; align-items: center;
                justify-content: center; z-index: 9999;
            ">
                <div style="
                    background: white; padding: 2rem; border-radius: 8px;
                    max-width: 400px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                ">
                    <h2>🛡️ Verification Required</h2>
                    <p>Please verify to continue</p>
                    <button onclick="window.minimalShield.startVerification()" style="
                        background: #10b981; color: white; border: none;
                        padding: 0.75rem 1.5rem; border-radius: 4px; cursor: pointer;
                    ">Verify Now</button>
                </div>
            </div>
        `;
        
        container.style.display = 'block';
        this.log('✅ Shield displayed');
    }
    
    async startVerification() {
        this.log('🚀 Starting verification...');
        
        try {
            const response = await fetch(`${this.options.apiBase}/api/shield/start-verification`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ return_url: window.location.href })
            });
            
            if (response.ok) {
                const result = await response.json();
                this.log('📊 Verification started:', result);
                
                if (result.verification_url) {
                    this.log('🔄 Redirecting to verification...');
                    window.location.href = result.verification_url;
                }
            } else {
                this.log(`❌ Verification start failed: ${response.status}`);
            }
            
        } catch (error) {
            this.log('❌ Verification error:', error.message);
        }
    }
    
    grantAccess() {
        this.log('✅ Access granted');
        this.shieldActive = false;
        
        const container = this.getContainer();
        if (container) {
            container.style.display = 'none';
        }
    }
    
    getContainer() {
        let container = document.getElementById('lemma-shield-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'lemma-shield-container';
            container.style.display = 'none';
            document.body.appendChild(container);
            this.log('📦 Created shield container');
        }
        return container;
    }
    
    // Simple force show
    forceShow() {
        this.log('🚨 Force showing shield');
        this.showShield();
    }
}

// Disable complex widget if it exists
if (window.LemmaShieldWidget) {
    console.log('[MINIMAL-SHIELD] 🚫 Disabling complex widget');
    window.LemmaShieldWidget = function() {
        console.log('[MINIMAL-SHIELD] 🚫 Complex widget call blocked');
    };
}

// Auto-initialize
document.addEventListener('DOMContentLoaded', () => {
    if (window.LemmaConfig) {
        console.log('[MINIMAL-SHIELD] 🚀 Auto-initializing...');
        window.minimalShield = new MinimalLemmaShield(window.LemmaConfig);
        window.lemmaShield = window.minimalShield; // Provide compatibility
        window.minimalShield.init();
    } else {
        console.log('[MINIMAL-SHIELD] ⚠️ No LemmaConfig found');
    }
});

// Export
window.MinimalLemmaShield = MinimalLemmaShield; 