/**
 * Lemma Auto-Configuration Library
 * Dramatically simplifies integration by auto-detecting needs and configuring everything
 */

class LemmaAutoConfig {
    constructor(apiKey, options = {}) {
        this.apiKey = apiKey;
        this.domain = options.domain || window.location.hostname;
        this.debug = options.debug || false;
        this.autoDetect = options.autoDetect !== false; // Default true
        
        this.features = {
            iam: false,
            botShield: false,
            zkp: false
        };
        
        this.initialized = false;
    }
    
    /**
     * Auto-detect what features are needed based on page content
     */
    detectNeeds() {
        const needs = [];
        
        // Check for login/auth forms
        const loginForms = document.querySelectorAll('form[action*="login"], form[action*="auth"], input[type="email"] + input[type="password"]');
        if (loginForms.length > 0) {
            needs.push('iam');
            this.log('🔐 Detected login forms - enabling IAM');
        }
        
        // Check for registration/signup forms  
        const signupForms = document.querySelectorAll('form[action*="register"], form[action*="signup"], input[placeholder*="email"]');
        if (signupForms.length > 0) {
            needs.push('bot-protection');
            this.log('🛡️ Detected signup forms - enabling bot protection');
        }
        
        // Check for admin/protected content
        const adminElements = document.querySelectorAll('[class*="admin"], [id*="admin"], [data-role*="admin"]');
        if (adminElements.length > 0) {
            needs.push('permissions');
            this.log('🔒 Detected admin content - enabling permission checking');
        }
        
        // Check for forms that need protection
        const forms = document.querySelectorAll('form');
        if (forms.length > 0) {
            needs.push('bot-protection');
            this.log('🛡️ Detected forms - enabling bot protection');
        }
        
        return needs;
    }
    
    /**
     * Configure everything automatically based on detected needs
     */
    async autoSetup() {
        this.log('🚀 Starting Lemma auto-configuration...');
        
        // Detect what's needed
        const needs = this.autoDetect ? this.detectNeeds() : [];
        
        // Configure features
        if (needs.includes('iam') || needs.includes('permissions')) {
            await this.setupIAM();
        }
        
        if (needs.includes('bot-protection')) {
            await this.setupBotShield();
        }
        
        // Apply automatic protection to detected elements
        this.applyAutoProtection();
        
        this.initialized = true;
        this.log('✅ Lemma auto-configuration complete');
        
        return {
            success: true,
            features: this.features,
            message: 'Lemma configured automatically'
        };
    }
    
    /**
     * Setup IAM system
     */
    async setupIAM() {
        this.log('🔐 Setting up Lemma IAM...');
        
        // Load IAM scripts
        await this.loadScript('https://lemma.id/static/js/lemma-oauth.js');
        await this.loadScript('https://lemma.id/static/js/lemma-permissions.js');
        
        // Initialize OAuth
        window.lemmaAuth = new LemmaOAuth({
            clientId: `lemma_oauth_${this.domain.replace('.', '_')}`,
            redirectUri: `https://${this.domain}/auth/callback`,
            scope: 'profile permissions'
        });
        
        // Add sign in buttons automatically
        this.addSignInButtons();
        
        this.features.iam = true;
        this.log('✅ Lemma IAM configured');
    }
    
    /**
     * Setup Bot Shield protection
     */
    async setupBotShield() {
        this.log('🛡️ Setting up Lemma Bot Shield...');
        
        // Load bot shield scripts
        await this.loadScript('https://lemma.id/static/js/lemma-bot-shield-simple.js');
        
        // Initialize bot shield
        window.lemmaShield = new LemmaBotShield({ 
            apiKey: this.apiKey,
            debug: this.debug
        });
        
        this.features.botShield = true;
        this.log('✅ Lemma Bot Shield configured');
    }
    
    /**
     * Apply automatic protection to forms and elements
     */
    applyAutoProtection() {
        // Protect all forms with bot shield
        if (this.features.botShield) {
            const forms = document.querySelectorAll('form:not([data-lemma-protect])');
            forms.forEach(form => {
                form.setAttribute('data-lemma-protect', 'bot-shield');
                this.log(`🛡️ Auto-protected form: ${form.action || 'unnamed'}`);
            });
        }
        
        // Add permission checks to admin elements
        if (this.features.iam) {
            const adminElements = document.querySelectorAll('[class*="admin"]:not([data-lemma-require])');
            adminElements.forEach(element => {
                element.setAttribute('data-lemma-require', 'admin');
                this.log(`🔒 Auto-protected admin element: ${element.tagName}`);
            });
        }
    }
    
    /**
     * Add "Sign in with Lemma" buttons automatically
     */
    addSignInButtons() {
        // Find existing login buttons and add Lemma option
        const loginButtons = document.querySelectorAll('button[type="submit"]:not([data-lemma-added])');
        const loginForms = document.querySelectorAll('form[action*="login"], form[action*="auth"]');
        
        loginForms.forEach(form => {
            const lemmaButton = document.createElement('button');
            lemmaButton.type = 'button';
            lemmaButton.className = 'btn btn-primary lemma-signin';
            lemmaButton.innerHTML = 'Sign in with Lemma';
            lemmaButton.style.cssText = 'margin: 10px 0; background: #007bff; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer;';
            lemmaButton.onclick = () => this.signInWithLemma();
            lemmaButton.setAttribute('data-lemma-added', 'true');
            
            form.appendChild(lemmaButton);
            this.log('🔐 Added "Sign in with Lemma" button');
        });
    }
    
    /**
     * Handle Lemma sign in
     */
    async signInWithLemma() {
        try {
            if (window.lemmaAuth) {
                await window.lemmaAuth.authorize();
            } else {
                this.log('❌ Lemma Auth not initialized');
            }
        } catch (error) {
            this.log('❌ Sign in error:', error);
        }
    }
    
    /**
     * Load external script
     */
    loadScript(src) {
        return new Promise((resolve, reject) => {
            if (document.querySelector(`script[src="${src}"]`)) {
                resolve(); // Already loaded
                return;
            }
            
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    /**
     * Debug logging
     */
    log(...args) {
        if (this.debug) {
            console.log('[Lemma Auto]', ...args);
        }
    }
    
    /**
     * Get current configuration status
     */
    getStatus() {
        return {
            initialized: this.initialized,
            features: this.features,
            domain: this.domain,
            apiKey: this.apiKey ? 'SET' : 'NOT SET'
        };
    }
}

/**
 * Global convenience functions for maximum simplicity
 */

// Ultra-simple one-line setup
window.LemmaAutoSetup = async (apiKey, options = {}) => {
    const autoConfig = new LemmaAutoConfig(apiKey, { debug: true, ...options });
    return await autoConfig.autoSetup();
};

// Even simpler - detect API key from script tag
window.LemmaAutoInit = async () => {
    const scriptTag = document.querySelector('script[data-api-key]');
    if (scriptTag) {
        const apiKey = scriptTag.getAttribute('data-api-key');
        return await LemmaAutoSetup(apiKey);
    } else {
        console.error('❌ Lemma: No API key found. Add data-api-key to script tag.');
        return { success: false, error: 'No API key found' };
    }
};

// Initialize automatically if API key is in script tag
document.addEventListener('DOMContentLoaded', async () => {
    const scriptTag = document.querySelector('script[data-api-key][src*="lemma-auto-config"]');
    if (scriptTag) {
        console.log('🚀 Lemma: Auto-initializing...');
        const result = await LemmaAutoInit();
        if (result.success) {
            console.log('✅ Lemma: Auto-configuration successful', result.features);
        } else {
            console.error('❌ Lemma: Auto-configuration failed', result.error);
        }
    }
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LemmaAutoConfig, LemmaAutoSetup, LemmaAutoInit };
}
