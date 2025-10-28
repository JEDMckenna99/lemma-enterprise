/**
 * Lemma WebAssembly Verifier - OPTIMIZED
 * =======================================
 * 
 * Target: <100µs per verification
 * 
 * Optimizations:
 * - Pre-parsed message templates
 * - Cached hex conversions
 * - TypedArray pooling
 * - Reduced allocations
 * - Direct WASM calls (minimal wrapper)
 */

class LemmaWASMVerifierOptimized {
    constructor(config = {}) {
        this.debug = config.debug || false;
        this.wasm = null;
        this.ready = false;
        
        // Message constructor (MUST match Rust server)
        this.messageConstructor = new LemmaMessageConstructor();
        
        // Object pools (reduce allocations)
        this.messageBufferPool = [];
        this.hexCacheSize = 1000;
        this.hexCache = new Map();  // Cache hex→bytes conversions
        
        // Pre-allocated buffers
        this.textEncoder = new TextEncoder();
        this.textDecoder = new TextDecoder();
        
        // Bloom filter (synced from server)
        this.bloomFilter = new Set();
        this.bloomLastSync = 0;
        
        // Performance tracking
        this.stats = {
            total: 0,
            avgTimeUs: 0,
            minTimeUs: Infinity,
            maxTimeUs: 0,
            costSaved: 0
        };
        
        this.initPromise = this.init();
    }
    
    /**
     * Initialize WASM module
     */
    async init() {
        try {
            // Load WASM module
            if (window.lemmaWasm) {
                this.wasm = window.lemmaWasm;
            } else if (window.wasmReady) {
                // Already loaded by another script
                const module = await import('/static/wasm/lemma_crypto.js');
                await module.default();
                this.wasm = module;
                window.lemmaWasm = module;
            }
            
            // Sync bloom filter
            await this.syncBloomFilter();
            
            this.ready = true;
            
            if (this.debug) {
                console.log('✅ Optimized WASM verifier ready');
                console.log('🎯 Target: <100µs per verification');
            }
            
            return true;
            
        } catch (error) {
            console.error('WASM init failed:', error);
            this.ready = false;
            return false;
        }
    }
    
    /**
     * OPTIMIZED credential verification
     */
    async verify(credential) {
        const start = performance.now();
        
        // Wait for init
        if (!this.ready) await this.initPromise;
        if (!this.ready) return { verified: false, error: 'WASM not ready' };
        
        try {
            // OPTIMIZATION 1: Quick expiration check FIRST (cheapest)
            if (!this.checkExpirationFast(credential)) {
                return this.createResult(false, 'expired', start);
            }
            
            // OPTIMIZATION 2: Quick revocation check (Set lookup is O(1))
            if (this.isRevokedFast(credential)) {
                return this.createResult(false, 'revoked', start);
            }
            
            // OPTIMIZATION 3: Signature verification (most expensive, do last)
            const sigValid = await this.verifySignatureFast(credential);
            if (!sigValid) {
                return this.createResult(false, 'invalid_signature', start);
            }
            
            // All checks passed
            return this.createResult(true, 'valid', start);
            
        } catch (error) {
            if (this.debug) {
                console.error('Verification error:', error);
            }
            return this.createResult(false, 'error', start, error.message);
        }
    }
    
    /**
     * FAST expiration check (pure JavaScript, no allocations)
     */
    checkExpirationFast(credential) {
        const expiry = credential.expiresAt || 
                      credential.claims?.expiresAt;
        
        if (!expiry) return true;  // No expiration
        
        const expiryTime = typeof expiry === 'number' ? expiry : parseInt(expiry);
        const now = Math.floor(Date.now() / 1000);
        
        return now < expiryTime;
    }
    
    /**
     * FAST revocation check (Set lookup)
     */
    isRevokedFast(credential) {
        if (!this.bloomFilter.size) return false;  // No revocations
        return this.bloomFilter.has(credential.id);
    }
    
    /**
     * CORRECT signature verification (matches Rust server)
     */
    async verifySignatureFast(credential) {
        try {
            // Extract signature (cached hex conversion)
            const sigHex = credential.proof?.signatureValue;
            if (!sigHex) return false;
            const signature = this.hexToBytesOptimized(sigHex);
            
            // Extract public key (cached)
            const issuerDID = credential.issuer;
            const pubKeyHex = issuerDID.substring(11, 75);  // 'did:lemma:' = 11 chars, key = 64 chars
            const publicKey = this.hexToBytesOptimized(pubKeyHex);
            
            // Create message (CRITICAL: MUST match Rust server exactly!)
            const messageBytes = await this.messageConstructor.createVerificationMessage(credential);
            
            // Debug if enabled
            if (this.debug) {
                console.log('🔐 Verifying signature:', {
                    credentialId: credential.id,
                    messageLength: messageBytes.length,
                    messageHash: Array.from(messageBytes.slice(0, 8))
                        .map(b => b.toString(16).padStart(2, '0')).join('')
                });
            }
            
            // Verify (direct WASM/ed25519 call)
            const isValid = await (this.wasm?.verify || window.ed25519.verify)(
                signature,
                messageBytes,
                publicKey
            );
            
            return isValid;
            
        } catch (error) {
            if (this.debug) {
                console.error('Sig verification error:', error);
            }
            return false;
        }
    }
    
    /**
     * OPTIMIZED hex to bytes (with caching)
     */
    hexToBytesOptimized(hex) {
        // Check cache
        if (this.hexCache.has(hex)) {
            return this.hexCache.get(hex);
        }
        
        // Convert
        const len = hex.length / 2;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
        }
        
        // Cache if not too many
        if (this.hexCache.size < this.hexCacheSize) {
            this.hexCache.set(hex, bytes);
        }
        
        return bytes;
    }
    
    // Removed old createMessageFast() - now using LemmaMessageConstructor which matches Rust server
    
    /**
     * OPTIMIZED result creation (reused structure)
     */
    createResult(verified, reason, startTime, error = null) {
        const timeMs = performance.now() - startTime;
        const timeUs = timeMs * 1000;
        
        // Update stats
        this.stats.total++;
        this.stats.avgTimeUs = (
            (this.stats.avgTimeUs * (this.stats.total - 1) + timeUs) / 
            this.stats.total
        );
        this.stats.minTimeUs = Math.min(this.stats.minTimeUs, timeUs);
        this.stats.maxTimeUs = Math.max(this.stats.maxTimeUs, timeUs);
        
        if (verified) {
            this.stats.costSaved += 0.001;  // vs server-side
        }
        
        return {
            verified,
            reason,
            verification_time_us: timeUs,
            verification_time_ms: timeMs,
            cost: 0,
            server_calls: 0,
            method: 'wasm_optimized',
            error
        };
    }
    
    /**
     * Sync bloom filter (periodic)
     */
    async syncBloomFilter() {
        try {
            const now = Date.now();
            
            // Sync every 7 days
            if (this.bloomFilter.size && (now - this.bloomLastSync) < 7 * 24 * 60 * 60 * 1000) {
                return true;
            }
            
            const response = await fetch('/api/revocation/bloom-filter');
            const data = await response.json();
            
            if (data.success && data.revoked_ids) {
                this.bloomFilter = new Set(data.revoked_ids);
                this.bloomLastSync = now;
                
                // Cache locally
                localStorage.setItem('lemma_bloom_cache', JSON.stringify({
                    data: data.revoked_ids,
                    sync: now
                }));
            }
            
            return true;
            
        } catch (error) {
            // Try cached
            try {
                const cached = JSON.parse(localStorage.getItem('lemma_bloom_cache') || '{}');
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
     * Get performance stats
     */
    getStats() {
        return {
            ...this.stats,
            avgTimeMs: (this.stats.avgTimeUs / 1000).toFixed(3),
            minTimeMs: (this.stats.minTimeUs / 1000).toFixed(3),
            maxTimeMs: (this.stats.maxTimeUs / 1000).toFixed(3),
            monthlySavings: (this.stats.costSaved * 30).toFixed(2)
        };
    }
    
    /**
     * Batch verify (even more optimized)
     */
    async verifyBatch(credentials) {
        const results = [];
        
        // Process in batches to avoid blocking UI
        for (let i = 0; i < credentials.length; i += 10) {
            const batch = credentials.slice(i, i + 10);
            const batchResults = await Promise.all(
                batch.map(cred => this.verify(cred))
            );
            results.push(...batchResults);
            
            // Yield to browser every 10 verifications
            if (i % 10 === 0) {
                await new Promise(resolve => setTimeout(resolve, 0));
            }
        }
        
        return results;
    }
}

// Export
if (typeof window !== 'undefined') {
    window.LemmaWASMVerifierOptimized = LemmaWASMVerifierOptimized;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaWASMVerifierOptimized;
}

