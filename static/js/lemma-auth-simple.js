/**
 * Lemma Simple Auth
 * Dead-simple authentication for apps that just need login/logout
 * Built-in bot resistance via cryptographic nonces
 * 
 * @version 1.0.0
 * @license MIT
 */

class LemmaAuth {
    constructor(config = {}) {
        if (!config.apiKey) {
            throw new Error('LemmaAuth requires apiKey in config');
        }
        
        this.apiKey = config.apiKey;
        this.siteId = config.siteId || 'default';
        this.siteDomain = config.siteDomain || window.location.hostname;
        this.debug = config.debug || false;
        this.apiBase = config.apiBase || '';
        
        // Initialize wallet under the hood
        this.walletReady = false;
        this.initWallet();
        
        if (this.debug) {
            console.log('🔐 LemmaAuth initialized', {
                siteId: this.siteId,
                siteDomain: this.siteDomain,
                apiBase: this.apiBase
            });
        }
    }
    
    async initWallet() {
        try {
            // Wait for LemmaWallet to be available
            if (typeof LemmaWallet === 'undefined') {
                if (this.debug) {
                    console.warn('⚠️ LemmaWallet not loaded yet, waiting...');
                }
                await this.waitForWallet();
            }
            
            this.wallet = new LemmaWallet({
                encryptionEnabled: true,
                autoSync: true,
                debug: this.debug
            });
            
            await this.wallet.init();
            this.walletReady = true;
            
            if (this.debug) {
                console.log('✅ Wallet initialized');
            }
        } catch (error) {
            console.error('❌ Failed to initialize wallet:', error);
            this.walletReady = false;
        }
    }
    
    async waitForWallet(timeout = 5000) {
        const startTime = Date.now();
        while (typeof LemmaWallet === 'undefined') {
            if (Date.now() - startTime > timeout) {
                throw new Error('LemmaWallet not available after timeout');
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }
    
    async ensureWalletReady() {
        if (!this.walletReady) {
            await this.initWallet();
        }
        if (!this.walletReady) {
            throw new Error('Wallet not ready');
        }
    }
    
    /**
     * Send login email to user
     * @param {string} email - User's email address
     * @param {object} options - Additional options
     * @param {string} options.role - User role (default: 'user')
     * @param {string} options.redirectUrl - URL to redirect after login
     * @returns {Promise<{success: boolean, message: string}>}
     */
    async sendLoginEmail(email, options = {}) {
        if (!email || !email.includes('@')) {
            return {
                success: false,
                error: 'Valid email address required'
            };
        }
        
        try {
            const response = await fetch(`${this.apiBase}/api/v1/iam/request-access`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify({
                    site_id: this.siteId,
                    site_domain: this.siteDomain,
                    user_email: email,
                    permission_level: options.role || 'user',
                    redirect_url: options.redirectUrl || window.location.href
                })
            });
            
            const result = await response.json();
            
            if (this.debug) {
                console.log('📧 Login email request:', result);
            }
            
            return result;
        } catch (error) {
            console.error('❌ Send login email failed:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    /**
     * Check if user is authenticated
     * Includes bot resistance via nonce verification
     * @param {boolean} skipNonce - Skip nonce verification (use cached result)
     * @returns {Promise<boolean>}
     */
    async isAuthenticated(skipNonce = false) {
        try {
            await this.ensureWalletReady();
            
            // Get credentials from wallet
            const credentials = await this.wallet.getCredentials('permission');
            
            if (!credentials || credentials.length === 0) {
                if (this.debug) {
                    console.log('ℹ️ No credentials found');
                }
                return false;
            }
            
            // Filter for current site
            const siteCreds = credentials.filter(cred => {
                const claims = cred.claims || cred.credentialSubject || {};
                const credDomain = claims.siteDomain || claims.site_domain;
                return credDomain === this.siteDomain;
            });
            
            if (siteCreds.length === 0) {
                if (this.debug) {
                    console.log(`ℹ️ No credentials for domain: ${this.siteDomain}`);
                }
                return false;
            }
            
            // Check expiration
            const cred = siteCreds[0];
            if (cred.expirationDate) {
                const expiry = new Date(cred.expirationDate);
                if (expiry < new Date()) {
                    if (this.debug) {
                        console.log('⚠️ Credential expired');
                    }
                    return false;
                }
            }
            
            // For quick checks, we can skip nonce verification
            // Nonce verification will happen in background or on sensitive operations
            if (skipNonce) {
                if (this.debug) {
                    console.log('✅ Authenticated (cached check)');
                }
                return true;
            }
            
            // Verify with fresh nonce (bot resistance)
            const nonce = this.generateNonce();
            const result = await this.verifyWithNonce(siteCreds[0], nonce);
            
            if (this.debug) {
                console.log(`${result.verified ? '✅' : '❌'} Authentication verified with nonce`);
            }
            
            return result.verified;
        } catch (error) {
            console.error('❌ Auth check failed:', error);
            return false;
        }
    }
    
    /**
     * Get current user info
     * @returns {Promise<{email: string, role: string, authenticated: boolean} | null>}
     */
    async getUser() {
        try {
            await this.ensureWalletReady();
            
            const credentials = await this.wallet.getCredentials('permission');
            const siteCreds = credentials.filter(cred => {
                const claims = cred.claims || cred.credentialSubject || {};
                const credDomain = claims.siteDomain || claims.site_domain;
                return credDomain === this.siteDomain;
            });
            
            if (siteCreds.length === 0) return null;
            
            const claims = siteCreds[0].claims || siteCreds[0].credentialSubject || {};
            return {
                email: claims.email,
                role: claims.permissionId || claims.permission_level || 'user',
                authenticated: true,
                credential: siteCreds[0]
            };
        } catch (error) {
            console.error('❌ Get user failed:', error);
            return null;
        }
    }
    
    /**
     * Logout (clear credential)
     */
    async logout() {
        try {
            await this.ensureWalletReady();
            
            const credentials = await this.wallet.getCredentials('permission');
            const siteCreds = credentials.filter(cred => {
                const claims = cred.claims || cred.credentialSubject || {};
                const credDomain = claims.siteDomain || claims.site_domain;
                return credDomain === this.siteDomain;
            });
            
            for (const cred of siteCreds) {
                await this.wallet.removeCredential(cred.id);
            }
            
            if (this.debug) {
                console.log('✅ Logged out');
            }
            
            return { success: true };
        } catch (error) {
            console.error('❌ Logout failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Generate cryptographically secure nonce (256-bit)
     * Used for bot resistance and replay attack prevention
     * @returns {string} Hex-encoded nonce
     */
    generateNonce() {
        const array = new Uint8Array(32);
        crypto.getRandomValues(array);
        return Array.from(array)
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }
    
    /**
     * Verify credential with fresh nonce (bot resistance)
     * @private
     */
    async verifyWithNonce(credential, nonce) {
        try {
            const response = await fetch(`${this.apiBase}/api/sdk/verify-permission-lemma`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    credential,
                    nonce,
                    site_domain: this.siteDomain,
                    timestamp: Date.now()
                })
            });
            
            const result = await response.json();
            
            if (this.debug && result.verified === false) {
                console.warn('⚠️ Verification failed:', result.error);
            }
            
            return result;
        } catch (error) {
            console.error('❌ Nonce verification failed:', error);
            return { verified: false, error: error.message };
        }
    }
    
    /**
     * Check if user has specific permission
     * @param {string} permission - Permission to check
     * @returns {Promise<boolean>}
     */
    async hasPermission(permission) {
        const user = await this.getUser();
        if (!user) return false;
        
        // Check if role matches or includes permission
        return user.role === permission || 
               user.role === 'admin' || 
               user.role === 'super_admin';
    }
}

// Export for use in both browser and module environments
if (typeof window !== 'undefined') {
    window.LemmaAuth = LemmaAuth;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaAuth;
}




