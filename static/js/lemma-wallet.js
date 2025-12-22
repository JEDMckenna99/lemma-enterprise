/**
 * Lemma Wallet SDK - Wallet-Centric Architecture
 * 
 * The wallet is unlocked locally via passkey (no server call).
 * Sites can issue their own lemmas to be stored in the wallet.
 * Lemmas can be presented to any site for local verification.
 */

// IIFE to avoid global scope pollution (fixes Cloudflare Rocket Loader issues)
(function() {
'use strict';

// Guard against double-loading
if (typeof window !== 'undefined' && window.LemmaWallet) {
    return; // Already loaded
}

// ============================================
// CONSTANTS
// ============================================

const WALLET_DB_NAME = 'LemmaWallet';
const WALLET_DB_VERSION = 1;
const SESSION_DURATION_MS = 8 * 60 * 60 * 1000; // 8 hours

// Auth states
const AUTH_STATE = {
    LOCKED: 'locked',
    UNLOCKED: 'unlocked',
    UNLOCKED_TODAY: 'unlocked_today'  // Unlocked via passkey today
};

// ============================================
// WALLET CLASS
// ============================================

class LemmaWallet {
    constructor() {
        this.db = null;
        this.session = {
            isUnlocked: false,
            unlockedAt: null,
            expiresAt: null
        };
        this._initialized = false;
    }

    // ========================================
    // INITIALIZATION
    // ========================================

    /**
     * Initialize the wallet (open IndexedDB)
     */
    async init() {
        if (this._initialized) return;

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(WALLET_DB_NAME, WALLET_DB_VERSION);

            request.onerror = () => reject(request.error);
            
            request.onsuccess = () => {
                this.db = request.result;
                this._initialized = true;
                this._checkSessionState();
                resolve();
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Passkey store (for local unlock)
                if (!db.objectStoreNames.contains('passkey')) {
                    db.createObjectStore('passkey', { keyPath: 'id' });
                }

                // Lemmas store
                if (!db.objectStoreNames.contains('lemmas')) {
                    const lemmaStore = db.createObjectStore('lemmas', { keyPath: 'id' });
                    lemmaStore.createIndex('issuer', 'issuer', { unique: false });
                    lemmaStore.createIndex('subject', 'subject', { unique: false });
                }

                // Trusted issuers store
                if (!db.objectStoreNames.contains('issuers')) {
                    db.createObjectStore('issuers', { keyPath: 'did' });
                }

                // Session store
                if (!db.objectStoreNames.contains('session')) {
                    db.createObjectStore('session', { keyPath: 'id' });
                }
            };
        });
    }

    /**
     * Check and restore session state from storage
     */
    async _checkSessionState() {
        try {
            const storedSession = await this._get('session', 'current');
            if (storedSession && storedSession.expiresAt > Date.now()) {
                this.session = {
                    isUnlocked: true,
                    unlockedAt: storedSession.unlockedAt,
                    expiresAt: storedSession.expiresAt
                };
            }
        } catch (e) {
            // No stored session, that's fine
        }
    }

    // ========================================
    // PASSKEY REGISTRATION (for local unlock)
    // ========================================

    /**
     * Register a passkey for local wallet unlock
     * This stores the public key locally for future verification
     */
    async registerPasskey() {
        await this.init();

        if (!this._isPasskeySupported()) {
            throw new Error('Passkeys not supported in this browser');
        }

        // Generate a local challenge
        const challenge = crypto.getRandomValues(new Uint8Array(32));
        
        // Get wallet ID (or create one)
        let walletId = await this._get('passkey', 'walletId');
        if (!walletId) {
            walletId = { id: 'walletId', value: this._generateId() };
            await this._put('passkey', walletId);
        }

        // Create credential
        const credential = await navigator.credentials.create({
            publicKey: {
                challenge: challenge,
                rp: {
                    name: 'Lemma Wallet',
                    id: window.location.hostname
                },
                user: {
                    id: new TextEncoder().encode(walletId.value),
                    name: 'Wallet User',
                    displayName: 'Lemma Wallet'
                },
                pubKeyCredParams: [
                    { alg: -7, type: 'public-key' },   // ES256
                    { alg: -257, type: 'public-key' }  // RS256
                ],
                authenticatorSelection: {
                    authenticatorAttachment: 'platform',
                    userVerification: 'required',
                    residentKey: 'preferred'
                },
                timeout: 60000
            }
        });

        // Extract and store public key
        const publicKeyData = this._extractPublicKey(credential.response);
        
        const passkeyRecord = {
            id: 'primary',
            credentialId: this._bufferToBase64url(credential.rawId),
            publicKey: publicKeyData.publicKey,
            algorithm: publicKeyData.algorithm,
            createdAt: Date.now()
        };

        await this._put('passkey', passkeyRecord);

        return {
            success: true,
            credentialId: passkeyRecord.credentialId
        };
    }

    // ========================================
    // LOCAL PASSKEY UNLOCK (No Server!)
    // ========================================

    /**
     * Unlock the wallet using passkey (100% local)
     * No server call required!
     */
    async unlock() {
        await this.init();

        // Get stored passkey
        const passkey = await this._get('passkey', 'primary');
        if (!passkey) {
            throw new Error('No passkey registered. Call registerPasskey() first.');
        }

        // Generate local challenge
        const challenge = crypto.getRandomValues(new Uint8Array(32));

        // Get passkey signature (browser prompts biometric)
        const credential = await navigator.credentials.get({
            publicKey: {
                challenge: challenge,
                rpId: window.location.hostname,
                allowCredentials: [{
                    id: this._base64urlToBuffer(passkey.credentialId),
                    type: 'public-key'
                }],
                userVerification: 'required',
                timeout: 60000
            }
        });

        // Verify signature LOCALLY
        const isValid = await this._verifyPasskeySignature(
            passkey.publicKey,
            passkey.algorithm,
            credential.response,
            challenge
        );

        if (!isValid) {
            throw new Error('Passkey verification failed');
        }

        // Unlock the wallet
        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + SESSION_DURATION_MS
        };

        // Persist session
        await this._put('session', {
            id: 'current',
            ...this.session
        });
            
            return { 
                success: true, 
            expiresAt: this.session.expiresAt,
            expiresIn: SESSION_DURATION_MS
        };
    }

    /**
     * Lock the wallet (clear session)
     */
    async lock() {
        this.session = {
            isUnlocked: false,
            unlockedAt: null,
            expiresAt: null
        };
        await this._delete('session', 'current');
    }

    /**
     * Check if wallet is currently unlocked
     */
    isUnlocked() {
        if (!this.session.isUnlocked) return false;
        if (this.session.expiresAt && this.session.expiresAt < Date.now()) {
            this.session.isUnlocked = false;
                    return false;
                    }
                    return true;
                }
                
    // ========================================
    // AUTH STATE (replaces email-based auth)
    // ========================================

    /**
     * Get current authentication state
     * This can be used as the primary auth method instead of email
     */
    getAuthState() {
        if (!this.session.isUnlocked) {
                return {
                state: AUTH_STATE.LOCKED,
                authenticated: false,
                reason: 'Wallet is locked'
            };
        }

        if (this.session.expiresAt && this.session.expiresAt < Date.now()) {
                    return {
                state: AUTH_STATE.LOCKED,
                authenticated: false,
                reason: 'Session expired'
            };
        }

        // Check if unlocked today (same calendar day)
        const unlockedDate = new Date(this.session.unlockedAt);
        const today = new Date();
        const isToday = unlockedDate.toDateString() === today.toDateString();
            
            return {
            state: isToday ? AUTH_STATE.UNLOCKED_TODAY : AUTH_STATE.UNLOCKED,
            authenticated: true,
            unlockedAt: this.session.unlockedAt,
            expiresAt: this.session.expiresAt,
            unlockedToday: isToday,
            timeRemaining: this.session.expiresAt - Date.now()
        };
    }

    /**
     * Get an auth proof that can be sent to servers
     * This replaces the need for email-based session tokens
     */
    async getAuthProof() {
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to get auth proof');
        }

        const passkey = await this._get('passkey', 'primary');
        if (!passkey) {
            throw new Error('No passkey registered');
        }

        // Create a timestamped proof of wallet unlock
        const proof = {
            type: 'wallet_auth',
            method: 'passkey_unlock',
            walletId: (await this._get('passkey', 'walletId'))?.value,
            unlockedAt: this.session.unlockedAt,
            expiresAt: this.session.expiresAt,
            timestamp: Date.now(),
            // Include passkey credential ID for verification
            passkeyCredentialId: passkey.credentialId
        };

        return proof;
    }

    /**
     * Check if user is authenticated (wallet unlocked via passkey today)
     * Use this as the primary auth check instead of email sessions
     */
    isAuthenticated() {
        const authState = this.getAuthState();
        return authState.authenticated && authState.unlockedToday;
    }

    /**
     * Require authentication - unlock if needed
     * Returns auth proof that can be sent to servers
     */
    async requireAuth() {
        if (!this.isAuthenticated()) {
            // Need to unlock
            await this.unlock();
        }
        return this.getAuthProof();
    }

    // ========================================
    // LEMMA STORAGE
    // ========================================

    /**
     * Store a lemma in the wallet
     * Accepts lemmas from any issuer
     */
    async storeLemma(lemma, issuerInfo = null) {
        await this.init();

        if (!this.isUnlocked()) {
            throw new Error('Wallet is locked. Call unlock() first.');
        }

        // Validate lemma structure
        if (!lemma.id || !lemma.issuer || !lemma.signature) {
            throw new Error('Invalid lemma structure');
        }

        // Store issuer info if provided
        if (issuerInfo && issuerInfo.publicKey) {
            await this._put('issuers', {
                did: lemma.issuer,
                publicKey: issuerInfo.publicKey,
                name: issuerInfo.name || lemma.issuer,
                verified: issuerInfo.verified || false,
                addedAt: Date.now()
            });
        }

        // Store the lemma
        await this._put('lemmas', {
            ...lemma,
            storedAt: Date.now()
        });

        return { success: true, id: lemma.id };
    }

    /**
     * Get all lemmas in the wallet
     */
    async getLemmas() {
        await this.init();
        return this._getAll('lemmas');
    }

    /**
     * Get lemmas from a specific issuer
     */
    async getLemmasByIssuer(issuerDid) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('lemmas', 'readonly');
            const store = tx.objectStore('lemmas');
            const index = store.index('issuer');
            const request = index.getAll(issuerDid);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Get a specific lemma by ID
     */
    async getLemma(lemmaId) {
        await this.init();
        return this._get('lemmas', lemmaId);
    }

    /**
     * Remove a lemma from the wallet
     */
    async removeLemma(lemmaId) {
        await this.init();

        if (!this.isUnlocked()) {
            throw new Error('Wallet is locked');
        }

        await this._delete('lemmas', lemmaId);
        return { success: true };
    }

    // ========================================
    // LEMMA PRESENTATION
    // ========================================

    /**
     * Present a lemma to a requesting site
     * Returns the lemma if wallet is unlocked and lemma exists
     */
    async presentLemma(lemmaId) {
        if (!this.isUnlocked()) {
            throw new Error('Wallet is locked');
        }

        const lemma = await this.getLemma(lemmaId);
        if (!lemma) {
            throw new Error('Lemma not found');
        }

        // Check expiration
        if (lemma.expiresAt && lemma.expiresAt < Date.now()) {
            throw new Error('Lemma has expired');
        }

        return lemma;
    }

    /**
     * Find and present a lemma matching criteria
     */
    async presentLemmaMatching(criteria) {
        if (!this.isUnlocked()) {
            throw new Error('Wallet is locked');
        }

        const lemmas = await this.getLemmas();
        
        for (const lemma of lemmas) {
            // Check issuer
            if (criteria.issuer && lemma.issuer !== criteria.issuer) continue;
            
            // Check claims
            if (criteria.claims) {
                let matches = true;
                for (const [key, value] of Object.entries(criteria.claims)) {
                    if (lemma.claims[key] !== value) {
                        matches = false;
                        break;
                    }
                }
                if (!matches) continue;
            }

            // Check expiration
            if (lemma.expiresAt && lemma.expiresAt < Date.now()) continue;

            return lemma;
        }

        return null;
    }

    // ========================================
    // ISSUER MANAGEMENT
    // ========================================

    /**
     * Add a trusted issuer
     */
    async addIssuer(issuerInfo) {
        await this.init();

        if (!issuerInfo.did || !issuerInfo.publicKey) {
            throw new Error('Issuer must have did and publicKey');
        }

        await this._put('issuers', {
            did: issuerInfo.did,
            publicKey: issuerInfo.publicKey,
            name: issuerInfo.name || issuerInfo.did,
            verified: issuerInfo.verified || false,
            addedAt: Date.now()
        });

        return { success: true };
    }

    /**
     * Get an issuer's info
     */
    async getIssuer(issuerDid) {
        await this.init();
        return this._get('issuers', issuerDid);
    }

    /**
     * Get all issuers
     */
    async getIssuers() {
        await this.init();
        return this._getAll('issuers');
    }

    // ========================================
    // LOCAL VERIFICATION
    // ========================================

    /**
     * Verify a lemma locally using cached issuer public key
     */
    async verifyLemma(lemma) {
        await this.init();

        // Get issuer's public key
        const issuer = await this.getIssuer(lemma.issuer);
        if (!issuer) {
            return { valid: false, reason: 'Unknown issuer' };
        }

        // Check expiration
        if (lemma.expiresAt && lemma.expiresAt < Date.now()) {
            return { valid: false, reason: 'Lemma expired' };
        }

        // Verify signature
        try {
            const isValid = await this._verifyLemmaSignature(lemma, issuer.publicKey);
            if (!isValid) {
                return { valid: false, reason: 'Invalid signature' };
            }
        } catch (e) {
            return { valid: false, reason: `Verification error: ${e.message}` };
        }

            return {
            valid: true,
            issuer: issuer.name,
            verified: issuer.verified,
            claims: lemma.claims
        };
    }

    // ========================================
    // UTILITY METHODS
    // ========================================

    _isPasskeySupported() {
        return window.PublicKeyCredential !== undefined &&
               typeof window.PublicKeyCredential === 'function';
    }

    _generateId() {
        return 'wallet_' + Array.from(crypto.getRandomValues(new Uint8Array(16)))
            .map(b => b.toString(16).padStart(2, '0')).join('');
    }

    _bufferToBase64url(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    }

    _base64urlToBuffer(base64url) {
        const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
        const padding = '='.repeat((4 - base64.length % 4) % 4);
        const binary = atob(base64 + padding);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }

    _extractPublicKey(attestationResponse) {
        // Parse attestation object to extract public key
        // This is simplified - full implementation would parse CBOR
        const publicKeyBytes = attestationResponse.getPublicKey();
        const algorithm = attestationResponse.getPublicKeyAlgorithm();
            
            return {
            publicKey: this._bufferToBase64url(publicKeyBytes),
            algorithm: algorithm
        };
    }

    async _verifyPasskeySignature(publicKeyB64, algorithm, response, challenge) {
        try {
            // Import the public key
            const publicKeyBuffer = this._base64urlToBuffer(publicKeyB64);
            
            const cryptoKey = await crypto.subtle.importKey(
                'spki',
                publicKeyBuffer,
                {
                    name: algorithm === -7 ? 'ECDSA' : 'RSASSA-PKCS1-v1_5',
                    namedCurve: algorithm === -7 ? 'P-256' : undefined,
                    hash: 'SHA-256'
                },
                false,
                ['verify']
            );

            // Reconstruct signed data
            const authenticatorData = new Uint8Array(response.authenticatorData);
            const clientDataHash = await crypto.subtle.digest(
                'SHA-256',
                response.clientDataJSON
            );
            
            const signedData = new Uint8Array(
                authenticatorData.length + new Uint8Array(clientDataHash).length
            );
            signedData.set(authenticatorData, 0);
            signedData.set(new Uint8Array(clientDataHash), authenticatorData.length);

            // Verify
            const signature = new Uint8Array(response.signature);
            
            return await crypto.subtle.verify(
                {
                    name: algorithm === -7 ? 'ECDSA' : 'RSASSA-PKCS1-v1_5',
                    hash: 'SHA-256'
                },
                cryptoKey,
                signature,
                signedData
            );
        } catch (e) {
            console.error('Passkey verification error:', e);
            return false;
        }
    }

    async _verifyLemmaSignature(lemma, publicKeyB64) {
        // Ed25519 signature verification
        // Uses Web Crypto API (Ed25519 support varies by browser)
        try {
            const publicKeyBuffer = this._base64urlToBuffer(publicKeyB64);
            const signatureBuffer = this._base64urlToBuffer(lemma.signature);
            
            // Create message to verify (canonical form without signature)
            const { signature, ...lemmaWithoutSig } = lemma;
            const message = new TextEncoder().encode(JSON.stringify(lemmaWithoutSig));

            const cryptoKey = await crypto.subtle.importKey(
                'raw',
                publicKeyBuffer,
                { name: 'Ed25519' },
                false,
                ['verify']
            );

            return await crypto.subtle.verify(
                'Ed25519',
                cryptoKey,
                signatureBuffer,
                message
            );
        } catch (e) {
            console.error('Lemma verification error:', e);
            return false;
        }
    }

    // IndexedDB helpers
    async _get(storeName, key) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async _getAll(storeName) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async _put(storeName, value) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.put(value);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async _delete(storeName, key) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.delete(key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    // ========================================
    // WALLET INFO
    // ========================================

    async getWalletInfo() {
        await this.init();

        const passkey = await this._get('passkey', 'primary');
        const lemmas = await this._getAll('lemmas');
        const issuers = await this._getAll('issuers');
            
            return {
            hasPasskey: !!passkey,
            isUnlocked: this.isUnlocked(),
            session: this.session,
            lemmaCount: lemmas.length,
            issuerCount: issuers.length
        };
    }

    // ========================================
    // BACKWARDS COMPATIBILITY (for old templates)
    // ========================================

    /**
     * Store credential (backwards compatible alias for storeLemma)
     * Does NOT require unlock for backwards compatibility with existing flows
     */
    async storeCredential(credential) {
        await this.init();
        
        // Normalize credential format
        const lemma = {
            id: credential.id || `cred_${Date.now()}`,
            issuer: credential.issuer || 'did:web:lemma.id',
            signature: credential.signature || credential.proof?.proofValue || 'legacy',
            claims: credential.claims || credential.credentialSubject || {},
            type: credential.type || ['VerifiableCredential'],
            packageType: credential.packageType || 'permission',
            ...credential,
            storedAt: Date.now()
        };
        
        await this._put('lemmas', lemma);
        console.log('✅ Credential stored (backwards compat):', lemma.id);
        return { success: true, id: lemma.id };
    }

    /**
     * Get credentials (backwards compatible alias for getLemmas)
     * @param {string} type - Optional filter by packageType ('permission', 'identity', etc)
     */
    async getCredentials(type = null) {
        await this.init();
        const lemmas = await this._getAll('lemmas');
        
        if (type) {
            return lemmas.filter(l => {
                const pkgType = l.packageType || l.claims?.type || l.type?.[1];
                return pkgType === type || 
                       (type === 'permission' && (pkgType === 'permission' || pkgType === 'PermissionLemma')) ||
                       (type === 'identity' && (pkgType === 'identity' || pkgType === 'IdentityCredential'));
            });
        }
        
        return lemmas;
    }

    /**
     * Remove credential (backwards compatible alias)
     */
    async removeCredential(credentialId) {
        await this.init();
        await this._delete('lemmas', credentialId);
        return { success: true };
    }

    /**
     * Property for backwards compatibility with isReady checks
     */
    get isReady() {
        return this._initialized;
    }

    /**
     * Export wallet data (for backup)
     */
    async export() {
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to export');
        }
        
        return {
            lemmas: await this._getAll('lemmas'),
            issuers: await this._getAll('issuers'),
            exportedAt: Date.now()
        };
    }
    
    /**
     * Import wallet data (from backup)
     */
    async import(data) {
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to import');
        }

        if (data.lemmas) {
            for (const lemma of data.lemmas) {
                await this._put('lemmas', lemma);
            }
        }

        if (data.issuers) {
            for (const issuer of data.issuers) {
                await this._put('issuers', issuer);
            }
        }

        return { success: true };
    }
}

// ============================================
// GLOBAL EXPORTS
// ============================================

// Export CLASS (constructor) to window.LemmaWallet
// Export INSTANCE to window.lemmaWallet (lowercase)
if (typeof window !== 'undefined') {
    window.LemmaWallet = LemmaWallet;  // The CLASS (constructor)
    window.LemmaWalletClass = LemmaWallet;  // Alias for backwards compatibility
    
    // Create singleton instance
    const lemmaWalletInstance = new LemmaWallet();
    window.lemmaWallet = lemmaWalletInstance;  // The INSTANCE (lowercase)
    window.globalLemmaWallet = lemmaWalletInstance;  // For templates that use this
    
    // Auto-initialize on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => lemmaWalletInstance.init());
    } else {
        lemmaWalletInstance.init();
    }
}

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LemmaWallet };
}

})(); // End of IIFE
