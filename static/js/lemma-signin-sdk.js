/**
 * Lemma Sign-In SDK
 * =================
 * Drop-in authentication for any website using Lemma IAM
 * 
 * Usage:
 * ```html
 * <script src="https://lemma.id/sdk/lemma-signin.js"></script>
 * <script>
 *   const auth = new LemmaSignIn({
 *     siteId: 'yoursite.com',
 *     onSignIn: (user) => {
 *       console.log('User signed in:', user);
 *       // Redirect or update UI
 *     },
 *     onSignOut: () => {
 *       console.log('User signed out');
 *     }
 *   });
 *   auth.init();
 * </script>
 * ```
 */

class LemmaSignIn {
    constructor(config = {}) {
        this.config = {
            siteId: config.siteId || window.location.hostname,
            apiBase: config.apiBase || 'https://lemma.id',
            autoSignIn: config.autoSignIn !== false, // Default true
            debug: config.debug || false,
            requiredPermission: config.requiredPermission || null, // e.g., 'admin_access'
            
            // Callbacks
            onSignIn: config.onSignIn || ((user) => console.log('Signed in:', user)),
            onSignOut: config.onSignOut || (() => console.log('Signed out')),
            onError: config.onError || ((error) => console.error('Auth error:', error)),
            
            // UI customization
            buttonText: config.buttonText || 'Sign in with Lemma',
            buttonStyle: config.buttonStyle || 'default', // 'default', 'minimal', 'custom'
            containerElement: config.containerElement || null
        };
        
        this.currentUser = null;
        this.wallet = null;
        this.isInitialized = false;
    }
    
    /**
     * Initialize SDK and check for existing session
     */
    async init() {
        if (this.isInitialized) {
            return;
        }
        
        if (this.config.debug) {
            console.log('🔐 Lemma Sign-In SDK initializing...');
            console.log('📍 Site ID:', this.config.siteId);
        }
        
        try {
            // Load Lemma wallet
            await this.loadWallet();
            
            // Check for existing valid credential
            if (this.config.autoSignIn) {
                await this.checkExistingCredential();
            }
            
            this.isInitialized = true;
            
            if (this.config.debug) {
                console.log('✅ Lemma Sign-In SDK ready');
            }
            
        } catch (error) {
            console.error('❌ SDK initialization failed:', error);
            this.config.onError(error);
        }
    }
    
    /**
     * Load Lemma wallet library
     */
    async loadWallet() {
        // Check if wallet already loaded
        if (window.LemmaIntegratedWallet) {
            this.wallet = new window.LemmaIntegratedWallet({debug: this.config.debug});
            await this.wallet.init();
            return;
        }
        
        // Dynamically load wallet script
        await this.loadScript(`${this.config.apiBase}/static/js/lemma-wallet.js?v=1016`);
        
        if (!window.LemmaIntegratedWallet) {
            throw new Error('Failed to load Lemma wallet library');
        }
        
        this.wallet = new window.LemmaIntegratedWallet({debug: this.config.debug});
        await this.wallet.init();
    }
    
    /**
     * Check for existing valid credential and auto-sign-in
     */
    async checkExistingCredential() {
        try {
            const permissions = await this.wallet.getCredentials('permission');
            
            if (this.config.debug) {
                console.log(`🔍 Found ${permissions.length} permission credential(s)`);
            }
            
            // Filter for this site's permissions
            const sitePermissions = permissions.filter(p => {
                const claims = p.claims || p.credentialSubject || {};
                return claims.siteId === this.config.siteId || claims.site === this.config.siteId;
            });
            
            if (sitePermissions.length === 0) {
                if (this.config.debug) {
                    console.log(`ℹ️ No valid permission for ${this.config.siteId}`);
                }
                return null;
            }
            
            // Check if required permission level is met
            let validCred = sitePermissions[0];
            
            if (this.config.requiredPermission) {
                validCred = sitePermissions.find(p => {
                    const claims = p.claims || p.credentialSubject || {};
                    return claims.permissionId === this.config.requiredPermission;
                });
                
                if (!validCred) {
                    if (this.config.debug) {
                        console.log(`❌ Required permission "${this.config.requiredPermission}" not found`);
                    }
                    return null;
                }
            }
            
            // Extract user info
            const claims = validCred.claims || validCred.credentialSubject || {};
            this.currentUser = {
                email: claims.email || claims.userEmail || 'user@unknown',
                role: claims.accountType || claims.role || 'user',
                permissionId: claims.permissionId || 'access',
                credential: validCred
            };
            
            if (this.config.debug) {
                console.log('✅ Valid credential found:', this.currentUser.email);
            }
            
            // Trigger sign-in callback
            this.config.onSignIn(this.currentUser);
            
            return this.currentUser;
            
        } catch (error) {
            console.error('Credential check failed:', error);
            return null;
        }
    }
    
    /**
     * Show sign-in UI
     */
    showSignInButton(containerElement) {
        const container = containerElement || this.config.containerElement;
        
        if (!container) {
            console.error('No container element provided for sign-in button');
            return;
        }
        
        const button = document.createElement('button');
        button.className = 'lemma-signin-button';
        button.textContent = this.config.buttonText;
        
        // Apply default styling if not custom
        if (this.config.buttonStyle === 'default') {
            button.style.cssText = `
                background: linear-gradient(135deg, #10b981, #059669);
                color: white;
                border: none;
                padding: 12px 32px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
            `;
            
            button.addEventListener('mouseenter', () => {
                button.style.transform = 'translateY(-2px)';
                button.style.boxShadow = '0 8px 16px rgba(16, 185, 129, 0.3)';
            });
            
            button.addEventListener('mouseleave', () => {
                button.style.transform = 'translateY(0)';
                button.style.boxShadow = 'none';
            });
        }
        
        button.addEventListener('click', () => this.initiateSignIn());
        
        if (typeof container === 'string') {
            document.querySelector(container).appendChild(button);
        } else {
            container.appendChild(button);
        }
        
        return button;
    }
    
    /**
     * Initiate sign-in flow (redirect to Lemma)
     */
    initiateSignIn() {
        const returnUrl = encodeURIComponent(window.location.href);
        window.location.href = `${this.config.apiBase}/auth/sdk-request?site=${this.config.siteId}&return=${returnUrl}`;
    }
    
    /**
     * Get current signed-in user
     */
    getCurrentUser() {
        return this.currentUser;
    }
    
    /**
     * Check if user is signed in
     */
    isSignedIn() {
        return this.currentUser !== null;
    }
    
    /**
     * Sign out user (clear credential)
     */
    async signOut() {
        try {
            // Clear session on server
            await fetch(`${this.config.apiBase}/api/auth/signout`, {
                method: 'POST',
                credentials: 'include'
            });
            
            // Clear local credential if requested
            if (this.currentUser && this.currentUser.credential) {
                // Optional: Remove credential from wallet
                // await this.wallet.removeCredential(this.currentUser.credential.id);
            }
            
            this.currentUser = null;
            this.config.onSignOut();
            
            if (this.config.debug) {
                console.log('✅ Signed out');
            }
            
        } catch (error) {
            console.error('Sign-out error:', error);
            this.config.onError(error);
        }
    }
    
    /**
     * Verify current credential is still valid
     */
    async verifyCredential() {
        if (!this.currentUser || !this.currentUser.credential) {
            return false;
        }
        
        try {
            const response = await fetch(`${this.config.apiBase}/api/verify-credential`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    credential: this.currentUser.credential
                })
            });
            
            const result = await response.json();
            return result.valid === true;
            
        } catch (error) {
            console.error('Verification error:', error);
            return false;
        }
    }
    
    /**
     * Utility: Load external script
     */
    loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
}

// Export for use in other scripts
if (typeof window !== 'undefined') {
    window.LemmaSignIn = LemmaSignIn;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaSignIn;
}



