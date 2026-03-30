/**
 * Lemma Verifier - Consolidated Verification Module
 * ==================================================
 * 
 * Combines functionality from:
 * - lemma-client-verifier.js → Basic Ed25519 verification
 * - lemma-full-client-verifier.js → Full verification with revocation
 * - lemma-wasm-verifier-optimized.js → WASM-optimized verification
 * 
 * Cost per verification: $0 (client-side)
 * Network calls: 0 (fully offline after bloom filter sync)
 * Performance: ~1-5ms (JavaScript) or <100µs (WASM)
 * 
 * Usage:
 *   const verifier = new LemmaVerifier({ mode: 'auto' }); // or 'wasm', 'webcrypto', 'js'
 *   const result = await verifier.verify(credential);
 * 
 * @version 2.0.0 (Consolidated)
 */

(function() {
'use strict';

// Guard against double-loading
if (typeof window !== 'undefined' && window.LemmaVerifier) {
    console.log('LemmaVerifier already loaded');
    return;
}


// ============================================
// MESSAGE CONSTRUCTOR (Matches Rust Server)
// ============================================

class LemmaMessageConstructor {
    constructor() {
        this.textEncoder = new TextEncoder();
    }
    
    /**
     * Create verification message (MUST match Rust server exactly)
     */
    async createVerificationMessage(credential) {
        const claims = credential.claims || credential.credentialSubject || {};
        
        // Sort keys for deterministic serialization
        const sortedClaims = {};
        Object.keys(claims).sort().forEach(key => {
            sortedClaims[key] = claims[key];
        });
        
        const message = JSON.stringify({
            issuer: credential.issuer,
            subject: credential.subject,
            claims: sortedClaims,
            issuedAt: credential.issuedAt,
            expiresAt: credential.expiresAt
        });
        
        // SHA-256 hash of message
        const messageBytes = this.textEncoder.encode(message);
        const hashBuffer = await crypto.subtle.digest('SHA-256', messageBytes);
        return new Uint8Array(hashBuffer);
    }
    
    /**
     * Create canonical message string (for basic verification)
     */
    createCanonicalMessage(credential) {
        const claims = credential.claims || credential.credentialSubject || {};
        
        const sortedClaims = {};
        Object.keys(claims).sort().forEach(key => {
            sortedClaims[key] = claims[key];
        });
        
        return JSON.stringify({
            issuer: credential.issuer,
            subject: credential.subject,
            claims: sortedClaims,
            issuedAt: credential.issuedAt,
            expiresAt: credential.expiresAt
        });
    }
}


// ============================================
// LEMMA VERIFIER (Main Class)
// ============================================

class LemmaVerifier {
    /**
     * @param {Object} config
     * @param {string} config.mode - 'auto', 'wasm', 'webcrypto', 'js'
     * @param {boolean} config.debug - Enable debug logging
     * @param {string} config.apiBase - API base URL
     * @param {string} config.siteId - Site ID for bloom filter
     */
    constructor(config = {}) {
        this.debug = config.debug || false;
        this.apiBase = config.apiBase || window.location.origin;
        this.siteId = config.siteId || 'lemma_platform';
        this.mode = config.mode || 'auto';
        
        this.wasm = null;
        this.ed25519 = null;
        this.ready = false;
        
        // Message constructor (matches Rust server)
        this.messageConstructor = new LemmaMessageConstructor();
        
        // Bloom filter for revocations
        this.bloomFilter = new Set();
        this.bloomLastSync = 0;
        this.bloomSyncInterval = 7 * 24 * 60 * 60 * 1000; // 7 days
        
        // Hex cache for optimization
        this.hexCache = new Map();
        this.hexCacheSize = 1000;
        
        // Performance tracking
        this.stats = {
            totalVerifications: 0,
            clientSideVerifications: 0,
            serverFallbacks: 0,
            avgTimeUs: 0,
            minTimeUs: Infinity,
            maxTimeUs: 0,
            costSaved: 0
        };
        
        this.textEncoder = new TextEncoder();
        this.initPromise = this.init();
    }
    
    /**
     * Initialize verifier based on mode
     */
    async init() {
        try {
            if (this.mode === 'auto' || this.mode === 'wasm') {
                await this._initWASM();
            }
            
            if (!this.wasm && (this.mode === 'auto' || this.mode === 'webcrypto')) {
                await this._initWebCrypto();
            }
            
            if (!this.wasm && !this.ed25519 && (this.mode === 'auto' || this.mode === 'js')) {
                await this._initNobleEd25519();
            }
            
            // Sync bloom filter
            await this.syncBloomFilter();
            
            this.ready = true;
            
            if (this.debug) {
                const method = this.wasm ? 'WASM (Rust)' : 
                              this.ed25519 ? '@noble/ed25519' : 'Web Crypto API';
                console.log(`Verifier ready using: ${method}`);
            }
            
            return true;
            
        } catch (error) {
            console.error('Verifier init failed:', error);
            this.ready = false;
            return false;
        }
    }
    
    async _initWASM() {
        try {
            if (window.lemmaWasm) {
                this.wasm = window.lemmaWasm;
                return true;
            }
            
            const WASM_VERSION = '985';
            const module = await import(`/static/wasm/lemma_crypto.js?v=${WASM_VERSION}`);
            await module.default(`/static/wasm/lemma_crypto_bg.wasm?v=${WASM_VERSION}`);
            this.wasm = module;
            window.lemmaWasm = module;
            
            if (this.debug) {
                console.log('WASM module loaded');
            }
            return true;
            
        } catch (error) {
            if (this.debug) {
                console.warn('WASM load failed:', error.message);
            }
            return false;
        }
    }
    
    async _initWebCrypto() {
        // Web Crypto API with Ed25519 is available in modern browsers
        if (typeof crypto !== 'undefined' && crypto.subtle) {
            try {
                // Test if Ed25519 is supported
                const testKey = new Uint8Array(32);
                await crypto.subtle.importKey(
                    'raw',
                    testKey,
                    { name: 'Ed25519', namedCurve: 'Ed25519' },
                    false,
                    ['verify']
                );
                this._useWebCrypto = true;
                
                if (this.debug) {
                    console.log('Web Crypto Ed25519 available');
                }
                return true;
            } catch (e) {
                this._useWebCrypto = false;
            }
        }
        return false;
    }
    
    async _initNobleEd25519() {
        try {
            if (typeof window.ed25519 !== 'undefined') {
                this.ed25519 = window.ed25519;
                return true;
            }
            
            const module = await import('https://cdn.jsdelivr.net/npm/@noble/ed25519@2.0.0/+esm');
            this.ed25519 = module;
            window.ed25519 = module;
            
            if (this.debug) {
                console.log('@noble/ed25519 loaded');
            }
            return true;
            
        } catch (error) {
            if (this.debug) {
                console.warn('@noble/ed25519 load failed:', error.message);
            }
            return false;
        }
    }
    
    /**
     * Verify credential (main entry point)
     */
    async verify(credential) {
        const startTime = performance.now();
        
        // Wait for init
        if (!this.ready) {
            await this.initPromise;
        }
        
        // No crypto backend available — cannot verify locally
        if (!this.ready && !this.wasm && !this.ed25519 && !this._useWebCrypto) {
            return this._createResult(false, 'no_crypto_backend', startTime,
                'No local crypto backend available (WASM, WebCrypto, or noble_ed25519 required)');
        }
        
        try {
            // Step 1: Quick expiration check (cheapest)
            if (!this._checkExpiration(credential)) {
                return this._createResult(false, 'expired', startTime);
            }
            
            // Step 2: Quick revocation check (O(1) Set lookup)
            if (this._isRevoked(credential)) {
                return this._createResult(false, 'revoked', startTime);
            }
            
            // Step 3: Signature verification (most expensive)
            const sigValid = await this._verifySignature(credential);
            if (!sigValid) {
                return this._createResult(false, 'invalid_signature', startTime);
            }
            
            // All checks passed
            return this._createResult(true, 'valid', startTime);
            
        } catch (error) {
            if (this.debug) {
                console.error('Verification error:', error);
            }
            return this._createResult(false, 'error', startTime, error.message);
        }
    }
    
    /**
     * Check expiration
     */
    _checkExpiration(credential) {
        const expiry = credential.expiresAt || credential.claims?.expiresAt;
        if (!expiry) return true;
        
        const expiryTime = typeof expiry === 'number' ? expiry : parseInt(expiry);
        const now = Math.floor(Date.now() / 1000);
        return now < expiryTime;
    }
    
    /**
     * Check revocation (bloom filter)
     */
    _isRevoked(credential) {
        if (!this.bloomFilter.size) return false;
        return this.bloomFilter.has(credential.id);
    }
    
    /**
     * Verify signature using best available method
     */
    async _verifySignature(credential) {
        try {
            const sigHex = credential.proof?.signatureValue;
            if (!sigHex) return false;
            const signature = this._hexToBytes(sigHex);
            
            const issuerDID = credential.issuer;
            const pubKeyHex = issuerDID.replace('did:lemma:', '').substring(0, 64);
            const publicKey = this._hexToBytes(pubKeyHex);
            
            // Create message (matches Rust server)
            const messageBytes = await this.messageConstructor.createVerificationMessage(credential);
            
            // Try WASM first (fastest)
            if (this.wasm && this.wasm.verify_signature_bytes) {
                return this.wasm.verify_signature_bytes(publicKey, messageBytes, signature);
            }
            
            // Try Web Crypto API
            if (this._useWebCrypto) {
                try {
                    const cryptoKey = await crypto.subtle.importKey(
                        'raw',
                        publicKey,
                        { name: 'Ed25519', namedCurve: 'Ed25519' },
                        false,
                        ['verify']
                    );
                    return await crypto.subtle.verify('Ed25519', cryptoKey, signature, messageBytes);
                } catch (e) {
                    if (this.debug) console.warn('Web Crypto verify failed:', e);
                }
            }
            
            // Try @noble/ed25519
            if (this.ed25519) {
                return await this.ed25519.verify(signature, messageBytes, publicKey);
            }
            
            return false;
            
        } catch (error) {
            if (this.debug) {
                console.error('Signature verification error:', error);
            }
            return false;
        }
    }
    
    /**
     * Hex to bytes with caching
     */
    _hexToBytes(hex) {
        if (!hex) return new Uint8Array(0);
        
        if (this.hexCache.has(hex)) {
            return this.hexCache.get(hex);
        }
        
        const len = hex.length / 2;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
        }
        
        if (this.hexCache.size < this.hexCacheSize) {
            this.hexCache.set(hex, bytes);
        }
        
        return bytes;
    }
    
    /**
     * Create result object
     */
    _createResult(verified, reason, startTime, error = null) {
        const timeMs = performance.now() - startTime;
        const timeUs = timeMs * 1000;
        
        this.stats.totalVerifications++;
        if (verified) {
            this.stats.clientSideVerifications++;
            this.stats.costSaved += 0.001;
        }
        
        this.stats.avgTimeUs = (
            (this.stats.avgTimeUs * (this.stats.totalVerifications - 1) + timeUs) /
            this.stats.totalVerifications
        );
        this.stats.minTimeUs = Math.min(this.stats.minTimeUs, timeUs);
        this.stats.maxTimeUs = Math.max(this.stats.maxTimeUs, timeUs);
        
        const method = this.wasm ? 'wasm' : 
                      this._useWebCrypto ? 'webcrypto' : 
                      this.ed25519 ? 'noble_ed25519' : 'unknown';
        
        return {
            verified,
            reason,
            verification_time_us: timeUs,
            verification_time_ms: timeMs,
            method,
            cost: 0,
            server_calls: 0,
            error
        };
    }
    
    // Server-side verification removed — all verification is local-first.
    
    /**
     * Sync bloom filter from server
     */
    async syncBloomFilter() {
        try {
            const now = Date.now();
            
            if (this.bloomFilter.size && (now - this.bloomLastSync) < this.bloomSyncInterval) {
                return true;
            }
            
            const response = await fetch(
                `${this.apiBase}/api/revocation/bloom-filter?site_id=${encodeURIComponent(this.siteId)}`
            );
            const data = await response.json();
            
            if (data.success && data.revoked_ids) {
                this.bloomFilter = new Set(data.revoked_ids);
                this.bloomLastSync = now;
                
                // Cache locally
                const cacheKey = `lemma_bloom_${this.siteId}`;
                localStorage.setItem(cacheKey, JSON.stringify({
                    data: data.revoked_ids,
                    sync: now,
                    siteId: this.siteId
                }));
                
                if (this.debug) {
                    console.log(`Bloom filter synced: ${data.revoked_ids.length} revocations`);
                }
            }
            
            return true;
            
        } catch (error) {
            // Try cached
            try {
                const cacheKey = `lemma_bloom_${this.siteId}`;
                const cached = JSON.parse(localStorage.getItem(cacheKey) || '{}');
                if (cached.data) {
                    this.bloomFilter = new Set(cached.data);
                    this.bloomLastSync = cached.sync;
                    return true;
                }
            } catch (e) {}
            
            return false;
        }
    }
    
    /**
     * Verify multiple credentials and check permissions
     */
    async verifyAccess(credentials, resource, action) {
        for (const credential of credentials) {
            const result = await this.verify(credential);
            
            if (result.verified) {
                const scope = credential.claims?.scope || [];
                if (this._scopeGrantsAccess(scope, resource, action)) {
                    return {
                        hasAccess: true,
                        credential,
                        verification: result
                    };
                }
            }
        }
        
        return {
            hasAccess: false,
            reason: 'no_valid_permission'
        };
    }
    
    /**
     * Check if scope grants access
     */
    _scopeGrantsAccess(scope, resource, action) {
        for (const scopeItem of scope) {
            if (scopeItem === '*') return true;
            
            const [scopeResource, scopeAction] = scopeItem.split(':');
            
            const resourceMatch = (
                scopeResource === '*' ||
                scopeResource === resource ||
                (scopeResource.endsWith('/*') && resource.startsWith(scopeResource.slice(0, -2)))
            );
            
            const actionMatch = (
                !scopeAction ||
                scopeAction === '*' ||
                scopeAction === action
            );
            
            if (resourceMatch && actionMatch) return true;
        }
        
        return false;
    }
    
    /**
     * Batch verify credentials
     */
    async verifyBatch(credentials) {
        const results = [];
        
        for (let i = 0; i < credentials.length; i += 10) {
            const batch = credentials.slice(i, i + 10);
            const batchResults = await Promise.all(
                batch.map(cred => this.verify(cred))
            );
            results.push(...batchResults);
            
            // Yield to browser
            if (i % 10 === 0) {
                await new Promise(resolve => setTimeout(resolve, 0));
            }
        }
        
        return results;
    }
    
    /**
     * Get performance statistics
     */
    getStats() {
        return {
            ...this.stats,
            avgTimeMs: (this.stats.avgTimeUs / 1000).toFixed(3),
            minTimeMs: (this.stats.minTimeUs / 1000).toFixed(3),
            maxTimeMs: this.stats.maxTimeUs === Infinity ? 'N/A' : (this.stats.maxTimeUs / 1000).toFixed(3),
            clientSidePercentage: this.stats.totalVerifications > 0
                ? ((this.stats.clientSideVerifications / this.stats.totalVerifications * 100).toFixed(1))
                : '0.0',
            monthlySavings: (this.stats.costSaved * 30).toFixed(2)
        };
    }
}


// ============================================
// LEGACY COMPATIBILITY WRAPPERS
// ============================================

// LemmaClientVerifier - Basic verifier (legacy)
class LemmaClientVerifier extends LemmaVerifier {
    constructor(config = {}) {
        super({ ...config, mode: 'js' });
    }
    
    async verifyCredential(credential) {
        return this.verify(credential);
    }
}

// LemmaFullClientVerifier - Full verifier with revocation (legacy)
class LemmaFullClientVerifier extends LemmaVerifier {
    constructor(config = {}) {
        super({ ...config, mode: 'auto' });
    }
    
    async verifyCredential(credential) {
        return this.verify(credential);
    }
}

// LemmaWASMVerifierOptimized - WASM verifier (legacy)
class LemmaWASMVerifierOptimized extends LemmaVerifier {
    constructor(config = {}) {
        super({ ...config, mode: 'wasm' });
        this.options = config;
    }
}


// ============================================
// EXPORTS
// ============================================

if (typeof window !== 'undefined') {
    window.LemmaVerifier = LemmaVerifier;
    window.LemmaMessageConstructor = LemmaMessageConstructor;
    
    // Legacy compatibility
    window.LemmaClientVerifier = LemmaClientVerifier;
    window.LemmaFullClientVerifier = LemmaFullClientVerifier;
    window.LemmaWASMVerifierOptimized = LemmaWASMVerifierOptimized;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { 
        LemmaVerifier, 
        LemmaMessageConstructor,
        LemmaClientVerifier,
        LemmaFullClientVerifier,
        LemmaWASMVerifierOptimized
    };
}

})();
