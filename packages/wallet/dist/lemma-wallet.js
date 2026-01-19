/**
 * @lemma/wallet - Passkey-protected credential wallet SDK
 * 
 * Local-first authentication with passkey unlock.
 * No server calls required for wallet operations.
 * 
 * @version 1.0.0
 * @license MIT
 * @see https://lemma.id/docs
 */

// Core constants
const WALLET_DB_NAME = 'LemmaWallet';
const WALLET_DB_VERSION = 3;
const SESSION_DURATION_MS = 8 * 60 * 60 * 1000; // 8 hours

const AUTH_STATE = {
    LOCKED: 'locked',
    UNLOCKED: 'unlocked',
    UNLOCKED_TODAY: 'unlocked_today'
};

/**
 * LemmaWallet - Client-side credential wallet with passkey protection
 */
class LemmaWallet {
    constructor(options = {}) {
        this.db = null;
        this.session = {
            isUnlocked: false,
            unlockedAt: null,
            expiresAt: null
        };
        this._initialized = false;
        this._options = {
            debug: false,
            autoSync: true,
            ...options
        };
        this._verifiedSignatures = new Set();
        this._cryptoKeyCache = new Map();
    }

    _log(...args) {
        if (this._options.debug) {
            console.log('[LemmaWallet]', ...args);
        }
    }

    /**
     * Initialize the wallet (open IndexedDB)
     */
    async init() {
        if (this._initialized) return this;

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(WALLET_DB_NAME, WALLET_DB_VERSION);

            request.onerror = () => reject(request.error);
            
            request.onsuccess = () => {
                this.db = request.result;
                this._initialized = true;
                this._checkSessionState();
                this._log('Wallet initialized');
                resolve(this);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                if (!db.objectStoreNames.contains('passkey')) {
                    db.createObjectStore('passkey', { keyPath: 'id' });
                }

                if (!db.objectStoreNames.contains('lemmas')) {
                    const lemmaStore = db.createObjectStore('lemmas', { keyPath: 'id' });
                    lemmaStore.createIndex('issuer', 'issuer', { unique: false });
                    lemmaStore.createIndex('subject', 'subject', { unique: false });
                }

                if (!db.objectStoreNames.contains('issuers')) {
                    db.createObjectStore('issuers', { keyPath: 'did' });
                }

                if (!db.objectStoreNames.contains('session')) {
                    db.createObjectStore('session', { keyPath: 'id' });
                }

                if (!db.objectStoreNames.contains('revocations')) {
                    db.createObjectStore('revocations', { keyPath: 'id' });
                }

                if (!db.objectStoreNames.contains('secrets')) {
                    db.createObjectStore('secrets', { keyPath: 'id' });
                }
            };
        }).then(() => {
            if (this._options.autoSync) {
                this._autoSyncRevocations();
            }
            return this;
        });
    }

    async _autoSyncRevocations() {
        try {
            const revInfo = await this.getRevocationInfo();
            const ONE_HOUR = 60 * 60 * 1000;
            
            if (!revInfo.synced || revInfo.age > ONE_HOUR) {
                await this.syncRevocations();
            }
        } catch (e) {
            this._log('Auto-sync revocations failed:', e);
        }
    }

    async _checkSessionState() {
        try {
            const storedSession = await this._get('session', 'current');
            if (storedSession && storedSession.expiresAt > Date.now()) {
                this.session = {
                    isUnlocked: true,
                    unlockedAt: storedSession.unlockedAt,
                    expiresAt: storedSession.expiresAt,
                    walletSecret: storedSession.walletSecret
                };
            }
        } catch (e) {
            // No stored session
        }
    }

    /**
     * Register a passkey for local wallet unlock
     * @returns {Promise<{success: boolean, credentialId: string, walletSecret: string}>}
     */
    async registerPasskey() {
        await this.init();

        if (!this._isPasskeySupported()) {
            throw new Error('Passkeys not supported in this browser');
        }

        const challenge = crypto.getRandomValues(new Uint8Array(32));
        
        let walletId = await this._get('passkey', 'walletId');
        if (!walletId) {
            walletId = { id: 'walletId', value: this._generateId() };
            await this._put('passkey', walletId);
        }

        const credential = await navigator.credentials.create({
            publicKey: {
                challenge: challenge,
                rp: {
                    name: 'Lemma Wallet',
                    id: typeof window !== 'undefined' ? window.location.hostname : 'localhost'
                },
                user: {
                    id: new TextEncoder().encode(walletId.value),
                    name: 'Wallet User',
                    displayName: 'Lemma Wallet'
                },
                pubKeyCredParams: [
                    { alg: -7, type: 'public-key' },
                    { alg: -257, type: 'public-key' }
                ],
                authenticatorSelection: {
                    authenticatorAttachment: 'platform',
                    userVerification: 'required',
                    residentKey: 'preferred'
                },
                timeout: 60000
            }
        });

        const publicKeyData = this._extractPublicKey(credential.response);
        
        const passkeyRecord = {
            id: 'primary',
            credentialId: this._bufferToBase64url(credential.rawId),
            publicKey: publicKeyData.publicKey,
            algorithm: publicKeyData.algorithm,
            createdAt: Date.now()
        };

        await this._put('passkey', passkeyRecord);

        let walletSecret = await this._get('secrets', 'master');
        if (!walletSecret) {
            const secretBytes = crypto.getRandomValues(new Uint8Array(32));
            const secretHex = Array.from(secretBytes)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            walletSecret = {
                id: 'master',
                secret: secretHex,
                createdAt: Date.now()
            };
            await this._put('secrets', walletSecret);
        }

        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + SESSION_DURATION_MS,
            walletId: walletId.value,
            walletSecret: walletSecret.secret
        };
        await this._put('session', { id: 'current', ...this.session });

        return {
            success: true,
            credentialId: passkeyRecord.credentialId,
            walletId: walletId.value,
            walletSecret: walletSecret.secret
        };
    }

    /**
     * Unlock the wallet using passkey (100% local, no server call)
     * @returns {Promise<{success: boolean, expiresAt: number, walletSecret: string}>}
     */
    async unlock() {
        await this.init();

        const passkey = await this._get('passkey', 'primary');
        if (!passkey) {
            throw new Error('No passkey registered. Call registerPasskey() first.');
        }

        const challenge = crypto.getRandomValues(new Uint8Array(32));

        const credential = await navigator.credentials.get({
            publicKey: {
                challenge: challenge,
                rpId: typeof window !== 'undefined' ? window.location.hostname : 'localhost',
                allowCredentials: [{
                    id: this._base64urlToBuffer(passkey.credentialId),
                    type: 'public-key'
                }],
                userVerification: 'required',
                timeout: 60000
            }
        });

        if (!credential) {
            throw new Error('Passkey authentication cancelled');
        }

        const walletIdRecord = await this._get('passkey', 'walletId');
        const walletId = walletIdRecord?.value || 'wallet_' + Date.now();

        let walletSecretRecord = await this._get('secrets', 'master');
        
        if (!walletSecretRecord) {
            const secretBytes = crypto.getRandomValues(new Uint8Array(32));
            const secretHex = Array.from(secretBytes)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            walletSecretRecord = {
                id: 'master',
                secret: secretHex,
                createdAt: Date.now()
            };
            await this._put('secrets', walletSecretRecord);
        }

        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + SESSION_DURATION_MS,
            walletId: walletId,
            walletSecret: walletSecretRecord.secret
        };

        await this._put('session', { id: 'current', ...this.session });
        
        this._log('Wallet unlocked');
            
        return { 
            success: true, 
            expiresAt: this.session.expiresAt,
            expiresIn: SESSION_DURATION_MS,
            walletId: walletId,
            walletSecret: walletSecretRecord.secret
        };
    }

    /**
     * Lock the wallet
     */
    async lock() {
        this.session = {
            isUnlocked: false,
            unlockedAt: null,
            expiresAt: null
        };
        await this._delete('session', 'current');
        this._log('Wallet locked');
    }

    /**
     * Check if wallet is unlocked
     * @returns {boolean}
     */
    isUnlocked() {
        if (!this.session.isUnlocked) return false;
        if (this.session.expiresAt && this.session.expiresAt < Date.now()) {
            this.session.isUnlocked = false;
            return false;
        }
        return true;
    }

    /**
     * Get current authentication state
     * @returns {{state: string, authenticated: boolean}}
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
     * Get wallet secret for PPID derivation
     * @returns {Promise<string|null>}
     */
    async getWalletSecret() {
        await this.init();
        
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to get wallet secret');
        }
        
        if (this.session.walletSecret) {
            return this.session.walletSecret;
        }
        
        const secretRecord = await this._get('secrets', 'master');
        if (secretRecord?.secret) {
            this.session.walletSecret = secretRecord.secret;
            return secretRecord.secret;
        }
        
        return null;
    }

    /**
     * Get passkey credential ID
     * @returns {Promise<string|null>}
     */
    async getPasskeyCredentialId() {
        await this.init();
        const passkey = await this._get('passkey', 'primary');
        return passkey?.credentialId || null;
    }

    /**
     * Store a credential in the wallet
     * @param {Object} credential - The credential to store
     * @returns {Promise<{success: boolean, id: string}>}
     */
    async storeCredential(credential) {
        await this.init();
        
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
        this._log('Credential stored:', lemma.id);
        return { success: true, id: lemma.id };
    }

    /**
     * Get credentials from the wallet
     * @param {string} [type] - Optional filter by packageType
     * @returns {Promise<Array>}
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
     * Remove a credential from the wallet
     * @param {string} credentialId
     * @returns {Promise<{success: boolean}>}
     */
    async removeCredential(credentialId) {
        await this.init();
        await this._delete('lemmas', credentialId);
        return { success: true };
    }

    /**
     * Verify a credential locally
     * @param {Object} credential
     * @returns {Promise<{valid: boolean, reason?: string}>}
     */
    async verifyCredential(credential) {
        await this.init();
        
        // Check revocation
        const revocationStatus = await this.isRevoked(credential.id);
        if (revocationStatus.revoked) {
            return { valid: false, reason: 'Revoked' };
        }

        // Check expiration
        const expiresAt = credential.expiresAt || credential.expirationDate;
        if (expiresAt && new Date(expiresAt).getTime() < Date.now()) {
            return { valid: false, reason: 'Expired' };
        }

        return { valid: true };
    }

    /**
     * Sync revocation list from server
     * @returns {Promise<{success: boolean, count?: number}>}
     */
    async syncRevocations() {
        if (typeof navigator !== 'undefined' && !navigator.onLine) {
            return { success: false, offline: true };
        }
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            
            const response = await fetch('/api/v1/revocation/list', {
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                return { success: false, httpError: response.status };
            }
            
            const data = await response.json();
            const revocations = data.revocations || data.revoked_ids || [];
            
            await this._put('revocations', {
                id: 'current',
                listArray: revocations,
                lastSynced: Date.now(),
                count: revocations.length
            });
            
            return { success: true, count: revocations.length };
        } catch (e) {
            return { success: false, error: e.message };
        }
    }

    /**
     * Check if a credential is revoked
     * @param {string} credentialId
     * @returns {Promise<{revoked: boolean, unchecked?: boolean}>}
     */
    async isRevoked(credentialId) {
        const revocations = await this._get('revocations', 'current');
        if (!revocations || !revocations.listArray) {
            return { revoked: false, unchecked: true };
        }
        
        return {
            revoked: revocations.listArray.includes(credentialId), 
            unchecked: false
        };
    }

    /**
     * Get revocation cache info
     * @returns {Promise<{synced: boolean, count: number, age?: number}>}
     */
    async getRevocationInfo() {
        const revocations = await this._get('revocations', 'current');
        if (!revocations) {
            return { synced: false, count: 0 };
        }
        return {
            synced: true,
            count: revocations.count,
            lastSynced: revocations.lastSynced,
            age: Date.now() - revocations.lastSynced
        };
    }

    /**
     * Get wallet info
     * @returns {Promise<Object>}
     */
    async getWalletInfo() {
        await this.init();

        const passkey = await this._get('passkey', 'primary');
        const lemmas = await this._getAll('lemmas');
        const secretRecord = await this._get('secrets', 'master');
            
        return {
            hasPasskey: !!passkey,
            hasWalletSecret: !!secretRecord?.secret,
            isUnlocked: this.isUnlocked(),
            credentialCount: lemmas.length,
            passkeyCredentialId: passkey?.credentialId || null
        };
    }

    /**
     * Export wallet data for backup
     * @returns {Promise<Object>}
     */
    async export() {
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to export');
        }
        
        return {
            credentials: await this._getAll('lemmas'),
            issuers: await this._getAll('issuers'),
            exportedAt: Date.now()
        };
    }

    /**
     * Import wallet data from backup
     * @param {Object} data
     * @returns {Promise<{success: boolean}>}
     */
    async import(data) {
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to import');
        }

        if (data.credentials || data.lemmas) {
            for (const cred of (data.credentials || data.lemmas)) {
                await this._put('lemmas', cred);
            }
        }

        if (data.issuers) {
            for (const issuer of data.issuers) {
                await this._put('issuers', issuer);
            }
        }

        return { success: true };
    }

    // Utility methods
    _isPasskeySupported() {
        return typeof window !== 'undefined' && 
               window.PublicKeyCredential !== undefined &&
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
        const publicKeyBytes = attestationResponse.getPublicKey();
        const algorithm = attestationResponse.getPublicKeyAlgorithm();
        return {
            publicKey: this._bufferToBase64url(publicKeyBytes),
            algorithm: algorithm
        };
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

    get isReady() {
        return this._initialized;
    }
}

// Export for different module systems

module.exports = LemmaWallet;
module.exports.LemmaWallet = LemmaWallet;
module.exports.default = LemmaWallet;
