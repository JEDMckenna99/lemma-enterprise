/**
 * Lemma Site Issuer SDK
 * 
 * Allows sites to issue their own lemmas to users' wallets.
 * Sites generate their own signing keypair and can issue credentials
 * that users store in their Lemma wallet.
 */

// IIFE to avoid global scope pollution (fixes Cloudflare Rocket Loader issues)
(function() {
'use strict';

// Guard against double-loading
if (typeof window !== 'undefined' && window.LemmaSiteIssuer) {
    return; // Already loaded
}

// ============================================
// SITE ISSUER CLASS
// ============================================

class LemmaSiteIssuer {
    constructor(options = {}) {
        this.domain = options.domain || window.location.hostname;
        this.name = options.name || this.domain;
        this.did = options.did || `did:web:${this.domain}`;
        this.lemmaApiUrl = options.lemmaApiUrl || 'https://lemma.id';
        
        this._privateKey = null;
        this._publicKey = null;
        this._initialized = false;
    }

    // ========================================
    // INITIALIZATION
    // ========================================

    /**
     * Initialize the issuer with a new or existing keypair
     */
    async init(existingKeyPair = null) {
        if (existingKeyPair) {
            this._privateKey = existingKeyPair.privateKey;
            this._publicKey = existingKeyPair.publicKey;
        } else {
            // Generate new Ed25519 keypair
            const keyPair = await this._generateKeyPair();
            this._privateKey = keyPair.privateKey;
            this._publicKey = keyPair.publicKey;
        }
        
        this._initialized = true;
        return this.getPublicKeyInfo();
    }

    /**
     * Initialize from stored keys (e.g., from server)
     */
    async initFromKeys(privateKeyB64, publicKeyB64) {
        this._privateKey = await this._importPrivateKey(privateKeyB64);
        this._publicKey = await this._importPublicKey(publicKeyB64);
        this._initialized = true;
        return this.getPublicKeyInfo();
    }

    /**
     * Get public key info for registration/sharing
     */
    getPublicKeyInfo() {
        if (!this._initialized) {
            throw new Error('Issuer not initialized');
        }
        
        return {
            did: this.did,
            domain: this.domain,
            name: this.name,
            publicKey: this._publicKeyB64
        };
    }

    // ========================================
    // LEMMA ISSUANCE
    // ========================================

    /**
     * Issue a lemma for a user
     * 
     * @param {string} subjectId - User's pairwise ID or DID
     * @param {object} claims - Claims to include in the lemma
     * @param {object} options - Additional options
     */
    async issueLemma(subjectId, claims, options = {}) {
        if (!this._initialized) {
            throw new Error('Issuer not initialized. Call init() first.');
        }

        const now = Date.now();
        const expiresIn = options.expiresIn || 30 * 24 * 60 * 60 * 1000; // 30 days default

        // Create lemma structure
        const lemma = {
            id: this._generateLemmaId(),
            '@context': ['https://www.w3.org/2018/credentials/v1', 'https://lemma.id/credentials/v1'],
            type: ['VerifiableCredential', 'LemmaCredential'],
            issuer: this.did,
            subject: subjectId,
            issuanceDate: new Date(now).toISOString(),
            expirationDate: new Date(now + expiresIn).toISOString(),
            issuedAt: now,
            expiresAt: now + expiresIn,
            claims: {
                ...claims,
                issuedBy: this.name,
                issuedAt: now
            }
        };

        // Sign the lemma
        const signature = await this._signLemma(lemma);
        lemma.signature = signature;
        lemma.proof = {
            type: 'Ed25519Signature2020',
            created: new Date(now).toISOString(),
            verificationMethod: `${this.did}#key-1`,
            proofPurpose: 'assertionMethod',
            proofValue: signature
        };

        return lemma;
    }

    /**
     * Issue a role-based permission lemma
     */
    async issueRoleLemma(subjectId, role, permissions = [], options = {}) {
        return this.issueLemma(subjectId, {
            type: 'role',
            role: role,
            permissions: permissions,
            scope: options.scope || '*'
        }, options);
    }

    /**
     * Issue a membership lemma
     */
    async issueMembershipLemma(subjectId, tier = 'member', options = {}) {
        return this.issueLemma(subjectId, {
            type: 'membership',
            tier: tier,
            memberSince: Date.now(),
            benefits: options.benefits || []
        }, options);
    }

    /**
     * Issue an access token lemma
     */
    async issueAccessLemma(subjectId, resource, permissions = ['read'], options = {}) {
        return this.issueLemma(subjectId, {
            type: 'access',
            resource: resource,
            permissions: permissions,
            restrictions: options.restrictions || {}
        }, options);
    }

    // ========================================
    // STORE IN WALLET
    // ========================================

    /**
     * Issue lemma and store directly in user's wallet
     */
    async issueToWallet(subjectId, claims, options = {}) {
        // Issue the lemma
        const lemma = await this.issueLemma(subjectId, claims, options);
        
        // Store in wallet if available
        if (window.LemmaWallet) {
            const issuerInfo = this.getPublicKeyInfo();
            await window.LemmaWallet.storeLemma(lemma, issuerInfo);
        }
        
        return lemma;
    }

    // ========================================
    // VERIFICATION (for other sites)
    // ========================================

    /**
     * Verify a lemma was issued by this issuer
     */
    async verifyOwnLemma(lemma) {
        if (lemma.issuer !== this.did) {
            return { valid: false, reason: 'Not issued by this issuer' };
        }

        // Check expiration
        if (lemma.expiresAt && lemma.expiresAt < Date.now()) {
            return { valid: false, reason: 'Lemma expired' };
        }

        // Verify signature
        const isValid = await this._verifySignature(lemma);
        if (!isValid) {
            return { valid: false, reason: 'Invalid signature' };
        }

        return {
            valid: true,
            issuer: this.name,
            claims: lemma.claims
        };
    }

    /**
     * Verify any lemma using provided public key
     */
    static async verifyLemma(lemma, publicKeyB64) {
        // Check expiration
        if (lemma.expiresAt && lemma.expiresAt < Date.now()) {
            return { valid: false, reason: 'Lemma expired' };
        }

        try {
            const publicKey = await LemmaSiteIssuer._importPublicKeyStatic(publicKeyB64);
            const { signature, proof, ...lemmaData } = lemma;
            const message = new TextEncoder().encode(JSON.stringify(lemmaData));
            const signatureBytes = LemmaSiteIssuer._base64urlToBuffer(signature);

            const isValid = await crypto.subtle.verify(
                'Ed25519',
                publicKey,
                signatureBytes,
                message
            );

            return {
                valid: isValid,
                issuer: lemma.issuer,
                claims: lemma.claims
            };
        } catch (e) {
            return { valid: false, reason: e.message };
        }
    }

    // ========================================
    // REVOCATION (Network Defense)
    // ========================================

    /**
     * Revoke a lemma - adds to global revocation network
     * This bans the credential across ALL participating sites
     */
    async revokeLemma(lemmaId, reason = 'issuer_revoked') {
        if (!this._initialized) {
            throw new Error('Issuer not initialized');
        }

        const response = await fetch(`${this.lemmaApiUrl}/api/v1/revoke`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                issuer_did: this.did,
                credential_id: lemmaId,
                reason: reason
            })
        });

        return response.json();
    }

    /**
     * Check if credentials are revoked (batch)
     */
    async checkRevocations(lemmaIds) {
        const response = await fetch(`${this.lemmaApiUrl}/api/v1/revocation/check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                credential_ids: lemmaIds
            })
        });

        return response.json();
    }

    // ========================================
    // REGISTRY INTEGRATION
    // ========================================

    /**
     * Register this issuer with Lemma's issuer registry
     */
    async registerWithLemma() {
        if (!this._initialized) {
            throw new Error('Issuer not initialized');
        }

        const response = await fetch(`${this.lemmaApiUrl}/api/issuers/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                did: this.did,
                domain: this.domain,
                name: this.name,
                publicKey: this._publicKeyB64
            })
        });

        return response.json();
    }

    /**
     * Fetch an issuer's public key from Lemma registry
     */
    static async fetchIssuerKey(issuerDid, lemmaApiUrl = 'https://lemma.id') {
        const response = await fetch(`${lemmaApiUrl}/api/issuers/${encodeURIComponent(issuerDid)}`);
        if (!response.ok) {
            throw new Error('Issuer not found');
        }
        return response.json();
    }

    // ========================================
    // PAIRWISE ID GENERATION
    // ========================================

    /**
     * Generate a pairwise subject ID for a user
     * This ensures user has different ID per site (privacy)
     */
    async generatePairwiseId(userIdentifier) {
        const data = new TextEncoder().encode(`${this.domain}:${userIdentifier}`);
        const hash = await crypto.subtle.digest('SHA-256', data);
        const hashB64 = this._bufferToBase64url(hash);
        return `did:lemma:ppid_${hashB64.substring(0, 32)}`;
    }

    // ========================================
    // KEY MANAGEMENT (Private)
    // ========================================

    async _generateKeyPair() {
        const keyPair = await crypto.subtle.generateKey(
            { name: 'Ed25519' },
            true,
            ['sign', 'verify']
        );
        
        // Export for storage
        const publicKeyRaw = await crypto.subtle.exportKey('raw', keyPair.publicKey);
        this._publicKeyB64 = this._bufferToBase64url(publicKeyRaw);
        
        return keyPair;
    }

    async _importPrivateKey(privateKeyB64) {
        const keyBuffer = this._base64urlToBuffer(privateKeyB64);
        return crypto.subtle.importKey(
            'pkcs8',
            keyBuffer,
            { name: 'Ed25519' },
            false,
            ['sign']
        );
    }

    async _importPublicKey(publicKeyB64) {
        this._publicKeyB64 = publicKeyB64;
        const keyBuffer = this._base64urlToBuffer(publicKeyB64);
        return crypto.subtle.importKey(
            'raw',
            keyBuffer,
            { name: 'Ed25519' },
            true,
            ['verify']
        );
    }

    static async _importPublicKeyStatic(publicKeyB64) {
        const keyBuffer = LemmaSiteIssuer._base64urlToBuffer(publicKeyB64);
        return crypto.subtle.importKey(
            'raw',
            keyBuffer,
            { name: 'Ed25519' },
            true,
            ['verify']
        );
    }

    async _signLemma(lemma) {
        const { signature, proof, ...lemmaData } = lemma;
        const message = new TextEncoder().encode(JSON.stringify(lemmaData));
        const signatureBuffer = await crypto.subtle.sign(
            'Ed25519',
            this._privateKey,
            message
        );
        return this._bufferToBase64url(signatureBuffer);
    }

    async _verifySignature(lemma) {
        try {
            const { signature, proof, ...lemmaData } = lemma;
            const message = new TextEncoder().encode(JSON.stringify(lemmaData));
            const signatureBytes = this._base64urlToBuffer(signature);
            
            return crypto.subtle.verify(
                'Ed25519',
                this._publicKey,
                signatureBytes,
                message
            );
        } catch (e) {
            return false;
        }
    }

    // ========================================
    // UTILITY METHODS
    // ========================================

    _generateLemmaId() {
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        return 'lemma_' + Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
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

    static _base64urlToBuffer(base64url) {
        const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
        const padding = '='.repeat((4 - base64.length % 4) % 4);
        const binary = atob(base64 + padding);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }

    // ========================================
    // KEY EXPORT (for server storage)
    // ========================================

    /**
     * Export keypair for server-side storage
     * WARNING: Handle private key securely!
     */
    async exportKeyPair() {
        if (!this._initialized) {
            throw new Error('Issuer not initialized');
        }

        const privateKeyBuffer = await crypto.subtle.exportKey('pkcs8', this._privateKey);
        
        return {
            privateKey: this._bufferToBase64url(privateKeyBuffer),
            publicKey: this._publicKeyB64,
            did: this.did,
            domain: this.domain
        };
    }
}

// ============================================
// VERIFIER HELPER CLASS
// ============================================

class LemmaVerifier {
    constructor(options = {}) {
        this.lemmaApiUrl = options.lemmaApiUrl || 'https://lemma.id';
        this._issuerCache = new Map();
    }

    /**
     * Verify a lemma, fetching issuer key if needed
     */
    async verify(lemma) {
        // Check cache first
        let issuerInfo = this._issuerCache.get(lemma.issuer);
        
        if (!issuerInfo) {
            // Fetch from registry
            try {
                issuerInfo = await LemmaSiteIssuer.fetchIssuerKey(lemma.issuer, this.lemmaApiUrl);
                this._issuerCache.set(lemma.issuer, issuerInfo);
            } catch (e) {
                // Try to get from wallet
                if (window.LemmaWallet) {
                    issuerInfo = await window.LemmaWallet.getIssuer(lemma.issuer);
                }
            }
        }

        if (!issuerInfo) {
            return { valid: false, reason: 'Unknown issuer' };
        }

        return LemmaSiteIssuer.verifyLemma(lemma, issuerInfo.publicKey);
    }

    /**
     * Request a specific lemma from user's wallet
     */
    async requestLemma(criteria) {
        if (!window.LemmaWallet) {
            throw new Error('Lemma Wallet not available');
        }

        if (!window.LemmaWallet.isUnlocked()) {
            throw new Error('Wallet is locked');
        }

        const lemma = await window.LemmaWallet.presentLemmaMatching(criteria);
        if (!lemma) {
            return { found: false };
        }

        // Verify it
        const verification = await this.verify(lemma);
        
        return {
            found: true,
            lemma: lemma,
            verification: verification
        };
    }
}

// ============================================
// EXPORTS
// ============================================

if (typeof window !== 'undefined') {
    window.LemmaSiteIssuer = LemmaSiteIssuer;
    window.LemmaVerifier = LemmaVerifier;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LemmaSiteIssuer, LemmaVerifier };
}

})(); // End of IIFE
