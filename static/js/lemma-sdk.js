/**
 * Lemma SDK - Consolidated Authentication Module
 * =============================================
 * 
 * Combines functionality from:
 * - lemma-auth-simple.js → LemmaAuth class
 * - lemma-signin-sdk.js → LemmaSignIn class
 * - lemma-passkey.js → LemmaPasskey class
 * 
 * Usage:
 *   // Simple auth (recommended for most sites)
 *   const auth = new LemmaAuth({ apiKey: 'your-key', siteId: 'yoursite.com' });
 *   const isLoggedIn = await auth.isAuthenticated();
 *   
 *   // Sign-in SDK with UI
 *   const signIn = new LemmaSignIn({ siteId: 'yoursite.com', onSignIn: (user) => {} });
 *   
 *   // Passkey operations
 *   const passkey = new LemmaPasskey();
 *   await passkey.register(userId, email);
 * 
 * @version 2.0.0 (Consolidated)
 */

(function() {
'use strict';

// Guard against double-loading
if (typeof window !== 'undefined' && window.LemmaSDK) {
    console.log('LemmaSDK already loaded');
    return;
}

// ============================================
// LEMMA AUTH (Simple Authentication)
// ============================================

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
        
        this.walletReady = false;
        this.wallet = null;
        this._initPromise = this._initWallet();
        
        if (this.debug) {
            console.log('LemmaAuth initialized', { siteId: this.siteId, siteDomain: this.siteDomain });
        }
    }
    
    async _initWallet() {
        try {
            if (typeof LemmaWallet === 'undefined') {
                await this._waitForWallet();
            }
            
            this.wallet = new LemmaWallet({
                encryptionEnabled: true,
                autoSync: true,
                debug: this.debug
            });
            
            await this.wallet.init();
            this.walletReady = true;
            
            if (this.debug) console.log('Wallet initialized');
        } catch (error) {
            console.error('Failed to initialize wallet:', error);
            this.walletReady = false;
        }
    }
    
    async _waitForWallet(timeout = 5000) {
        const startTime = Date.now();
        while (typeof LemmaWallet === 'undefined') {
            if (Date.now() - startTime > timeout) {
                throw new Error('LemmaWallet not available after timeout');
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }
    
    async _ensureWalletReady() {
        if (!this.walletReady) {
            await this._initPromise;
        }
        if (!this.walletReady) {
            throw new Error('Wallet not ready');
        }
    }
    
    /**
     * Send login email to user
     */
    async sendLoginEmail(email, options = {}) {
        if (!email || !email.includes('@')) {
            return { success: false, error: 'Valid email address required' };
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
            
            return await response.json();
        } catch (error) {
            console.error('Send login email failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Check if user is authenticated (with optional bot resistance)
     */
    async isAuthenticated(skipNonce = false) {
        try {
            await this._ensureWalletReady();
            
            const credentials = await this.wallet.getCredentials('permission');
            if (!credentials || credentials.length === 0) return false;
            
            const siteCreds = credentials.filter(cred => {
                const claims = cred.claims || cred.credentialSubject || {};
                const credDomain = claims.siteDomain || claims.site_domain;
                return credDomain === this.siteDomain;
            });
            
            if (siteCreds.length === 0) return false;
            
            const cred = siteCreds[0];
            if (cred.expirationDate) {
                const expiry = new Date(cred.expirationDate);
                if (expiry < new Date()) return false;
            }
            
            if (skipNonce) return true;
            
            const nonce = this.generateNonce();
            const result = await this._verifyWithNonce(siteCreds[0], nonce);
            return result.verified;
        } catch (error) {
            console.error('Auth check failed:', error);
            return false;
        }
    }
    
    /**
     * Get current user info
     */
    async getUser() {
        try {
            await this._ensureWalletReady();
            
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
            console.error('Get user failed:', error);
            return null;
        }
    }
    
    /**
     * Logout user
     */
    async logout() {
        try {
            await this._ensureWalletReady();
            
            const credentials = await this.wallet.getCredentials('permission');
            const siteCreds = credentials.filter(cred => {
                const claims = cred.claims || cred.credentialSubject || {};
                const credDomain = claims.siteDomain || claims.site_domain;
                return credDomain === this.siteDomain;
            });
            
            for (const cred of siteCreds) {
                await this.wallet.removeCredential(cred.id);
            }
            
            return { success: true };
        } catch (error) {
            console.error('Logout failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Generate cryptographically secure nonce
     */
    generateNonce() {
        const array = new Uint8Array(32);
        crypto.getRandomValues(array);
        return Array.from(array).map(b => b.toString(16).padStart(2, '0')).join('');
    }
    
    async _verifyWithNonce(credential, nonce) {
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
            return await response.json();
        } catch (error) {
            return { verified: false, error: error.message };
        }
    }
    
    /**
     * Check if user has specific permission
     */
    async hasPermission(permission) {
        const user = await this.getUser();
        if (!user) return false;
        return user.role === permission || user.role === 'admin' || user.role === 'super_admin';
    }
}


// ============================================
// LEMMA SIGN-IN (UI-focused authentication)
// ============================================

class LemmaSignIn {
    constructor(config = {}) {
        this.config = {
            siteId: config.siteId || window.location.hostname,
            apiBase: config.apiBase || 'https://lemma.id',
            autoSignIn: config.autoSignIn !== false,
            debug: config.debug || false,
            requiredPermission: config.requiredPermission || null,
            onSignIn: config.onSignIn || ((user) => console.log('Signed in:', user)),
            onSignOut: config.onSignOut || (() => console.log('Signed out')),
            onError: config.onError || ((error) => console.error('Auth error:', error)),
            buttonText: config.buttonText || 'Sign in with Lemma',
            buttonStyle: config.buttonStyle || 'default',
            containerElement: config.containerElement || null
        };
        
        this.currentUser = null;
        this.wallet = null;
        this.isInitialized = false;
    }
    
    async init() {
        if (this.isInitialized) return;
        
        if (this.config.debug) {
            console.log('Lemma Sign-In SDK initializing...');
        }
        
        try {
            await this._loadWallet();
            
            if (this.config.autoSignIn) {
                await this._checkExistingCredential();
            }
            
            this.isInitialized = true;
        } catch (error) {
            console.error('SDK initialization failed:', error);
            this.config.onError(error);
        }
    }
    
    async _loadWallet() {
        if (window.LemmaWallet) {
            this.wallet = new window.LemmaWallet({ debug: this.config.debug });
            await this.wallet.init();
            return;
        }
        
        await this._loadScript(`${this.config.apiBase}/static/js/lemma-wallet.js`);
        
        if (!window.LemmaWallet) {
            throw new Error('Failed to load Lemma wallet library');
        }
        
        this.wallet = new window.LemmaWallet({ debug: this.config.debug });
        await this.wallet.init();
    }
    
    async _loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    async _checkExistingCredential() {
        const credentials = await this.wallet.getCredentials('permission');
        const validCred = credentials.find(cred => {
            const claims = cred.claims || cred.credentialSubject || {};
            const siteId = claims.siteId || claims.site_id;
            return siteId === this.config.siteId;
        });
        
        if (validCred) {
            this.currentUser = this._extractUserFromCredential(validCred);
            this.config.onSignIn(this.currentUser);
        }
    }
    
    _extractUserFromCredential(credential) {
        const claims = credential.claims || credential.credentialSubject || {};
        return {
            email: claims.email,
            userId: credential.subject,
            permissions: claims.permissions ? claims.permissions.split(',') : [],
            credential: credential
        };
    }
    
    /**
     * Trigger sign-in flow
     */
    async signIn() {
        try {
            // Check if already signed in
            const authState = await this.wallet.getAuthState();
            
            if (authState.isUnlocked) {
                // Wallet unlocked, check for existing credential
                const credentials = await this.wallet.getCredentials('permission');
                const siteCred = credentials.find(c => {
                    const claims = c.claims || c.credentialSubject || {};
                    return (claims.siteId || claims.site_id) === this.config.siteId;
                });
                
                if (siteCred) {
                    this.currentUser = this._extractUserFromCredential(siteCred);
                    this.config.onSignIn(this.currentUser);
                    return { success: true, user: this.currentUser };
                }
                
                // No credential for this site, redirect to get one
                return this._redirectToGetPermission();
            }
            
            // Wallet locked, redirect to unlock
            return this._redirectToUnlock();
            
        } catch (error) {
            this.config.onError(error);
            return { success: false, error: error.message };
        }
    }
    
    _redirectToUnlock() {
        const returnUrl = encodeURIComponent(window.location.href);
        window.location.href = `${this.config.apiBase}/wallet/unlock?return_url=${returnUrl}&site_id=${this.config.siteId}`;
        return { success: false, redirecting: true };
    }
    
    _redirectToGetPermission() {
        const returnUrl = encodeURIComponent(window.location.href);
        window.location.href = `${this.config.apiBase}/wallet?request_permission=${this.config.siteId}&return_url=${returnUrl}`;
        return { success: false, redirecting: true };
    }
    
    /**
     * Sign out user
     */
    async signOut() {
        if (this.wallet) {
            const credentials = await this.wallet.getCredentials('permission');
            for (const cred of credentials) {
                const claims = cred.claims || cred.credentialSubject || {};
                if ((claims.siteId || claims.site_id) === this.config.siteId) {
                    await this.wallet.removeCredential(cred.id);
                }
            }
        }
        
        this.currentUser = null;
        this.config.onSignOut();
        return { success: true };
    }
    
    /**
     * Get current user
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
}


// ============================================
// LEMMA PASSKEY (WebAuthn Operations)
// ============================================

class LemmaPasskey {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '';
        this.onSuccess = options.onSuccess || (() => {});
        this.onError = options.onError || ((e) => console.error('Passkey error:', e));
    }
    
    /**
     * Check if passkeys are supported
     */
    static isSupported() {
        return window.PublicKeyCredential !== undefined &&
               typeof window.PublicKeyCredential === 'function';
    }
    
    /**
     * Check if platform authenticator is available
     */
    static async isPlatformAuthenticatorAvailable() {
        if (!this.isSupported()) return false;
        try {
            return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
        } catch {
            return false;
        }
    }
    
    /**
     * Register a new passkey
     */
    async register(userId, userEmail, deviceName = 'My Device') {
        if (!LemmaPasskey.isSupported()) {
            throw new Error('Passkeys are not supported in this browser');
        }
        
        try {
            // Get registration options
            const beginResponse = await fetch(`${this.baseUrl}/api/passkey/register/begin`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    user_id: userId,
                    user_email: userEmail,
                    device_name: deviceName
                })
            });
            
            const beginData = await beginResponse.json();
            if (!beginData.success) {
                throw new Error(beginData.error || 'Failed to start registration');
            }
            
            // Prepare options for WebAuthn
            const options = this._prepareRegistrationOptions(beginData.options);
            
            // Create credential (browser prompts for biometric)
            const credential = await navigator.credentials.create({ publicKey: options });
            
            // Complete registration
            const completeResponse = await fetch(`${this.baseUrl}/api/passkey/register/complete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    user_id: userId,
                    credential: this._serializeCredential(credential)
                })
            });
            
            const result = await completeResponse.json();
            if (!result.success) {
                throw new Error(result.error || 'Failed to complete registration');
            }
            
            this.onSuccess(result);
            return result;
            
        } catch (error) {
            this.onError(error);
            throw error;
        }
    }
    
    /**
     * Authenticate with passkey
     */
    async authenticate(userId = null) {
        if (!LemmaPasskey.isSupported()) {
            throw new Error('Passkeys are not supported in this browser');
        }
        
        try {
            // Get authentication options
            const beginResponse = await fetch(`${this.baseUrl}/api/passkey/authenticate/begin`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ user_id: userId })
            });
            
            const beginData = await beginResponse.json();
            if (!beginData.success) {
                throw new Error(beginData.error || 'Failed to start authentication');
            }
            
            // Prepare options
            const options = this._prepareAuthOptions(beginData.options);
            
            // Get credential (browser prompts for biometric)
            const credential = await navigator.credentials.get({ publicKey: options });
            
            // Complete authentication
            const completeResponse = await fetch(`${this.baseUrl}/api/passkey/authenticate/complete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    credential: this._serializeCredential(credential)
                })
            });
            
            const result = await completeResponse.json();
            if (!result.success) {
                throw new Error(result.error || 'Authentication failed');
            }
            
            this.onSuccess(result);
            return result;
            
        } catch (error) {
            this.onError(error);
            throw error;
        }
    }
    
    _prepareRegistrationOptions(options) {
        return {
            challenge: this._base64ToBuffer(options.challenge),
            rp: options.rp,
            user: {
                id: this._base64ToBuffer(options.user.id),
                name: options.user.name,
                displayName: options.user.displayName
            },
            pubKeyCredParams: options.pubKeyCredParams,
            timeout: options.timeout || 60000,
            authenticatorSelection: options.authenticatorSelection || {
                authenticatorAttachment: 'platform',
                userVerification: 'required',
                residentKey: 'preferred'
            },
            attestation: options.attestation || 'none'
        };
    }
    
    _prepareAuthOptions(options) {
        const prepared = {
            challenge: this._base64ToBuffer(options.challenge),
            timeout: options.timeout || 60000,
            userVerification: options.userVerification || 'required',
            rpId: options.rpId
        };
        
        if (options.allowCredentials) {
            prepared.allowCredentials = options.allowCredentials.map(cred => ({
                type: cred.type,
                id: this._base64ToBuffer(cred.id),
                transports: cred.transports
            }));
        }
        
        return prepared;
    }
    
    _serializeCredential(credential) {
        return {
            id: credential.id,
            rawId: this._bufferToBase64(credential.rawId),
            response: {
                clientDataJSON: this._bufferToBase64(credential.response.clientDataJSON),
                attestationObject: credential.response.attestationObject 
                    ? this._bufferToBase64(credential.response.attestationObject)
                    : undefined,
                authenticatorData: credential.response.authenticatorData
                    ? this._bufferToBase64(credential.response.authenticatorData)
                    : undefined,
                signature: credential.response.signature
                    ? this._bufferToBase64(credential.response.signature)
                    : undefined,
                userHandle: credential.response.userHandle
                    ? this._bufferToBase64(credential.response.userHandle)
                    : undefined
            },
            type: credential.type,
            authenticatorAttachment: credential.authenticatorAttachment
        };
    }
    
    _base64ToBuffer(base64) {
        const binary = atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }
    
    _bufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    }
}


// ============================================
// LEMMA SDK NAMESPACE
// ============================================

const LemmaSDK = {
    version: '2.0.0',
    Auth: LemmaAuth,
    SignIn: LemmaSignIn,
    Passkey: LemmaPasskey,
    
    // Convenience factory methods
    createAuth(config) {
        return new LemmaAuth(config);
    },
    
    createSignIn(config) {
        return new LemmaSignIn(config);
    },
    
    createPasskey(options) {
        return new LemmaPasskey(options);
    },
    
    // Feature detection
    isPasskeySupported() {
        return LemmaPasskey.isSupported();
    },
    
    async isPlatformAuthenticatorAvailable() {
        return LemmaPasskey.isPlatformAuthenticatorAvailable();
    }
};


// ============================================
// EXPORTS
// ============================================

// Browser globals
if (typeof window !== 'undefined') {
    window.LemmaSDK = LemmaSDK;
    window.LemmaAuth = LemmaAuth;
    window.LemmaSignIn = LemmaSignIn;
    window.LemmaPasskey = LemmaPasskey;
}

// Module exports
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LemmaSDK, LemmaAuth, LemmaSignIn, LemmaPasskey };
}

})();
