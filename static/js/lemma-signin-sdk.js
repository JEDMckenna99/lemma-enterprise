/**
 * Lemma Sign-In SDK
 * =================
 * Drop-in authentication for any website using Lemma IAM
 * 
 * Usage:
 * ```html
 * <script src="https://lemma.id/static/js/lemma-signin-sdk.js"></script>
 * <script>
 *   const auth = new LemmaSignIn({
 *     siteId: 'yoursite.com',
 *     permissionLevel: 'member',  // Optional: specific permission to request
 *     autoIssue: true,            // Auto-issue credential if wallet exists
 *     onSignIn: (user) => {
 *       console.log('User signed in:', user);
 *       // Redirect or update UI
 *     },
 *     onNoWallet: () => {
 *       // User has no wallet - show setup prompt
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
            autoIssue: config.autoIssue !== false,   // Default true - auto-issue if wallet exists
            debug: config.debug || false,
            permissionLevel: config.permissionLevel || 'member', // Permission to request
            requiredPermission: config.requiredPermission || null, // e.g., 'admin_access' (specific required)
            
            // Callbacks
            onSignIn: config.onSignIn || ((user) => console.log('Signed in:', user)),
            onSignOut: config.onSignOut || (() => console.log('Signed out')),
            onError: config.onError || ((error) => console.error('Auth error:', error)),
            onNoWallet: config.onNoWallet || null, // Called when user has no wallet
            onLoading: config.onLoading || null, // Called during loading states
            
            // UI customization
            buttonText: config.buttonText || 'Sign in with Lemma',
            buttonStyle: config.buttonStyle || 'default', // 'default', 'minimal', 'custom'
            containerElement: config.containerElement || null
        };
        
        this.currentUser = null;
        this.wallet = null;
        this.credential = null;
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
            
            // Filter for this site's permissions (flexible matching)
            const sitePermissions = permissions.filter(p => {
                const claims = p.claims || p.credentialSubject || {};
                const siteId = claims.siteId || claims.site || claims.site_id || '';
                return siteId === this.config.siteId || 
                       siteId.includes(this.config.siteId) ||
                       this.config.siteId.includes(siteId);
            });
            
            if (sitePermissions.length === 0) {
                if (this.config.debug) {
                    console.log(`ℹ️ No valid permission for ${this.config.siteId}`);
                }
                
                // Try auto-issue if enabled
                if (this.config.autoIssue) {
                    return await this.autoIssueCredential();
                }
                
                // No credential and no auto-issue - notify caller
                if (this.config.onNoWallet) {
                    this.config.onNoWallet();
                }
                return null;
            }
            
            // Check if required permission level is met
            let validCred = sitePermissions[0];
            
            if (this.config.requiredPermission) {
                validCred = sitePermissions.find(p => {
                    const claims = p.claims || p.credentialSubject || {};
                    const permId = claims.permissionId || claims.permission_level || '';
                    return permId === this.config.requiredPermission ||
                           permId.includes(this.config.requiredPermission);
                });
                
                if (!validCred) {
                    if (this.config.debug) {
                        console.log(`❌ Required permission "${this.config.requiredPermission}" not found`);
                    }
                    return null;
                }
            }
            
            // Check revocation status
            try {
                const isRevoked = await this.wallet.isCredentialRevoked(validCred);
                if (isRevoked) {
                    if (this.config.debug) {
                        console.log('🚫 Credential is revoked');
                    }
                    await this.wallet.removeCredential(validCred.id);
                    
                    // Try to get a new one if auto-issue enabled
                    if (this.config.autoIssue) {
                        return await this.autoIssueCredential();
                    }
                    return null;
                }
            } catch (e) {
                if (this.config.debug) {
                    console.warn('Revocation check failed:', e);
                }
            }
            
            // Store and extract user info
            this.credential = validCred;
            const claims = validCred.claims || validCred.credentialSubject || {};
            this.currentUser = {
                ppid: claims.subject || validCred.subject,
                email: claims.email || claims.userEmail,
                role: claims.accountType || claims.role || 'user',
                permissionId: claims.permissionId || claims.permission_level || 'access',
                siteId: claims.siteId || claims.site,
                credential: validCred
            };
            
            if (this.config.debug) {
                console.log('✅ Valid credential found:', this.currentUser.ppid?.slice(0, 30) + '...');
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
     * Auto-issue a credential when wallet exists but no site permission
     */
    async autoIssueCredential() {
        try {
            if (this.config.onLoading) {
                this.config.onLoading('Signing you in...');
            }
            
            if (this.config.debug) {
                console.log('🔐 Auto-issuing credential for', this.config.siteId);
            }
            
            // Get wallet secret for PPID derivation
            let walletSecret = null;
            let passkeyCredentialId = null;
            
            try {
                walletSecret = await this.wallet.getWalletSecret();
            } catch (e) {
                if (this.config.debug) {
                    console.warn('Could not get wallet secret:', e.message);
                }
            }
            
            if (!walletSecret) {
                try {
                    passkeyCredentialId = await this.wallet.getPasskeyCredentialId();
                } catch (e) {
                    if (this.config.debug) {
                        console.warn('Could not get passkey:', e.message);
                    }
                }
            }
            
            // No wallet credentials available
            if (!walletSecret && !passkeyCredentialId) {
                if (this.config.debug) {
                    console.log('❌ No wallet secret or passkey available');
                }
                if (this.config.onNoWallet) {
                    this.config.onNoWallet();
                }
                return null;
            }
            
            // Request credential from server
            const response = await fetch(`${this.config.apiBase}/api/wallet-auth/issue`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    site_id: this.config.siteId,
                    permission_level: this.config.permissionLevel,
                    wallet_secret: walletSecret,
                    passkey_credential_id: passkeyCredentialId
                })
            });
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error || 'Failed to issue credential');
            }
            
            if (this.config.debug) {
                console.log('✅ Credential issued:', result.ppid?.slice(0, 30) + '...');
            }
            
            // Store in wallet
            await this.wallet.storeCredential(result.permission_lemma);
            
            // Set current user
            this.credential = result.permission_lemma;
            const claims = result.permission_lemma.claims || result.permission_lemma.credentialSubject || {};
            this.currentUser = {
                ppid: result.ppid,
                email: claims.email,
                role: claims.accountType || 'user',
                permissionId: claims.permissionId || this.config.permissionLevel,
                siteId: this.config.siteId,
                credential: result.permission_lemma,
                isNewUser: result.is_new_user
            };
            
            // Trigger sign-in callback
            this.config.onSignIn(this.currentUser);
            
            return this.currentUser;
            
        } catch (error) {
            if (this.config.debug) {
                console.error('Auto-issue failed:', error);
            }
            this.config.onError(error);
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
     * Get authorization headers for API calls
     * Use this to authenticate requests to your backend
     */
    getAuthHeaders() {
        if (!this.credential) {
            return {};
        }
        return {
            'Authorization': `Bearer ${JSON.stringify(this.credential)}`
        };
    }
    
    /**
     * Get the raw credential for custom use
     */
    getCredential() {
        return this.credential;
    }
    
    /**
     * Get credential as JSON string (for Authorization header)
     */
    getCredentialString() {
        return this.credential ? JSON.stringify(this.credential) : null;
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



