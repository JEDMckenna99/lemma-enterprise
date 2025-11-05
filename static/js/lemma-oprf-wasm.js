/**
 * Lemma OPRF WebAssembly Wrapper
 * ================================
 * Client-side OPRF blinding/unblinding for zero-knowledge revocation checking
 * 
 * Usage:
 * ```javascript
 * import { LemmaOPRF } from './lemma-oprf-wasm.js';
 * 
 * const oprf = await LemmaOPRF.init();
 * 
 * // Check if credential is revoked (zero-knowledge)
 * const isRevoked = await oprf.checkRevocation('cred_abc123');
 * ```
 */

export class LemmaOPRF {
    constructor(wasmModule) {
        this.wasm = wasmModule;
        this.checker = new wasmModule.WasmRevocationChecker();
        this.bloomFilterLoaded = false;
    }

    /**
     * Initialize the OPRF module (async)
     * 
     * @returns {Promise<LemmaOPRF>} Initialized OPRF instance
     */
    static async init() {
        try {
            // Dynamically import the WASM module
            const wasmModule = await import('/static/wasm/lemma-oprf.js');
            await wasmModule.default(); // Initialize WASM
            
            console.log('✅ Lemma OPRF WASM initialized');
            return new LemmaOPRF(wasmModule);
        } catch (error) {
            console.error('❌ Failed to initialize Lemma OPRF WASM:', error);
            throw new Error(`OPRF initialization failed: ${error.message}`);
        }
    }

    /**
     * Load Bloom filter from server
     * 
     * @param {string} apiEndpoint - API endpoint for Bloom filter (default: /api/revocation/bloom-filter)
     * @returns {Promise<void>}
     */
    async loadBloomFilter(apiEndpoint = '/api/revocation/bloom-filter') {
        try {
            console.log('📦 Loading global Bloom filter...');
            
            const response = await fetch(apiEndpoint);
            const data = await response.json();
            
            if (!data.success || !data.filter_bytes) {
                throw new Error('Invalid Bloom filter response');
            }
            
            // Convert base64 or hex to bytes
            const filterBytes = this.decodeFilterBytes(data.filter_bytes);
            
            // Load into WASM Bloom filter
            this.checker.load_bloom_filter(filterBytes);
            this.bloomFilterLoaded = true;
            
            console.log(`✅ Bloom filter loaded: ${data.count} revocations, ${filterBytes.length} bytes`);
            
            // Cache for offline use
            localStorage.setItem('lemma_bloom_wasm', data.filter_bytes);
            localStorage.setItem('lemma_bloom_wasm_version', data.version);
            localStorage.setItem('lemma_bloom_wasm_sync', Date.now().toString());
        } catch (error) {
            console.warn('⚠️ Failed to load Bloom filter:', error);
            
            // Try cached version
            const cachedFilter = localStorage.getItem('lemma_bloom_wasm');
            if (cachedFilter) {
                console.log('📦 Using cached Bloom filter...');
                const filterBytes = this.decodeFilterBytes(cachedFilter);
                this.checker.load_bloom_filter(filterBytes);
                this.bloomFilterLoaded = true;
            } else {
                throw new Error('No Bloom filter available (online or cached)');
            }
        }
    }

    /**
     * Check if credential is revoked (zero-knowledge)
     * 
     * Steps:
     * 1. Blind credential ID locally (WASM)
     * 2. Send blinded point to server for OPRF evaluation
     * 3. Unblind server response locally (WASM)
     * 4. Check OPRF output against Bloom filter (WASM)
     * 
     * Privacy guarantee: Server never sees the credential ID!
     * 
     * @param {string} credentialId - Credential ID to check
     * @param {string} serverEndpoint - OPRF evaluation endpoint (default: /api/oprf/evaluate)
     * @returns {Promise<boolean>} True if revoked, false otherwise
     */
    async checkRevocation(credentialId, serverEndpoint = '/api/oprf/evaluate') {
        if (!this.bloomFilterLoaded) {
            console.warn('⚠️ Bloom filter not loaded, loading now...');
            await this.loadBloomFilter();
        }

        try {
            // Create server evaluation function for WASM
            const serverEvaluateFn = async (blindedHex) => {
                const response = await fetch(serverEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ blinded: blindedHex })
                });
                
                const data = await response.json();
                
                if (!data.success || !data.evaluated) {
                    throw new Error('Server OPRF evaluation failed');
                }
                
                return data.evaluated;
            };

            // Call WASM revocation checker
            const isRevoked = await this.checker.is_revoked(
                credentialId,
                serverEvaluateFn
            );

            return isRevoked;
        } catch (error) {
            console.error('❌ Revocation check failed:', error);
            // Fail-safe: If check fails, assume not revoked (don't block user)
            return false;
        }
    }

    /**
     * Manual OPRF flow (advanced usage)
     * 
     * @param {string} credentialId - Credential ID
     * @returns {Promise<{blind: Object, oprf_output: Uint8Array, is_revoked: boolean}>}
     */
    async manualOPRFFlow(credentialId) {
        if (!this.bloomFilterLoaded) {
            throw new Error('Bloom filter not loaded');
        }

        // 1. Create OPRF client
        const oprfClient = new this.wasm.WasmOPRFClient();

        // 2. Blind locally
        const blindResult = oprfClient.blind(credentialId);
        const blindedHex = blindResult.blinded_hex();

        console.log('🔐 Blinded credential ID:', blindedHex);

        // 3. Send to server for evaluation
        const response = await fetch('/api/oprf/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ blinded: blindedHex })
        });

        const data = await response.json();

        // 4. Unblind locally
        const oprfOutput = oprfClient.unblind(data.evaluated, blindResult);

        console.log('🔓 OPRF output length:', oprfOutput.length);

        // 5. Check Bloom filter
        const bloomFilter = new this.wasm.WasmBloomFilter(
            this.decodeFilterBytes(localStorage.getItem('lemma_bloom_wasm'))
        );
        const isRevoked = bloomFilter.contains(oprfOutput);

        return {
            blind_result: blindResult,
            oprf_output: oprfOutput,
            is_revoked: isRevoked
        };
    }

    /**
     * Get Bloom filter statistics
     * 
     * @returns {Object|null} Filter stats or null if not loaded
     */
    getBloomFilterStats() {
        if (!this.bloomFilterLoaded) {
            return null;
        }

        try {
            const cached = localStorage.getItem('lemma_bloom_wasm');
            if (cached) {
                const filterBytes = this.decodeFilterBytes(cached);
                const filter = new this.wasm.WasmBloomFilter(filterBytes);
                return filter.stats();
            }
        } catch (error) {
            console.error('Failed to get Bloom filter stats:', error);
        }
        
        return null;
    }

    /**
     * Decode filter bytes from base64 or hex
     * 
     * @param {string} encoded - Base64 or hex encoded bytes
     * @returns {Uint8Array} Decoded bytes
     */
    decodeFilterBytes(encoded) {
        // Try base64 first
        try {
            const binaryString = atob(encoded);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            return bytes;
        } catch {
            // Try hex
            const matches = encoded.match(/.{1,2}/g) || [];
            return new Uint8Array(matches.map(byte => parseInt(byte, 16)));
        }
    }
}

// Export for non-module usage
if (typeof window !== 'undefined') {
    window.LemmaOPRF = LemmaOPRF;
}

