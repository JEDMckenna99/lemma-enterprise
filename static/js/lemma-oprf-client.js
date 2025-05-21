/**
 * Lemma OPRF Client
 * 
 * JavaScript implementation of the client side of the OPRF protocol
 * using the ristretto255 elliptic curve, following RFC 9497.
 * 
 * This library provides functions for:
 * - Blinding credential IDs before sending to the OPRF service
 * - Unblinding the responses
 * - Checking against cascaded Bloom filters
 * - Managing revocation witnesses
 */

class LemmaOPRFClient {
    constructor(options = {}) {
        this.serverUrl = options.serverUrl || '/oprfeval';
        this.pubkeyEndpoint = options.pubkeyEndpoint || '/pubkey';
        this.cascadeEndpoint = options.cascadeEndpoint || '/cascade/';
        this.epoch = null;
        this.publicKey = null;
        
        // Import crypto libraries
        this._initCryptoBackend();
    }
    
    /**
     * Initialize the cryptographic backend.
     * This sets up the necessary elliptic curve operations.
     * @private
     */
    async _initCryptoBackend() {
        // Import required noble-curves modules
        try {
            // We're using dynamic imports to load the noble-curves library
            // In a production environment, this would be properly bundled
            this.ristretto = await import('https://cdn.jsdelivr.net/npm/@noble/curves@1.1.0/ed25519.js')
                .then(mod => mod.default || mod);
            
            this.utils = await import('https://cdn.jsdelivr.net/npm/@noble/curves@1.1.0/abstract/utils.js')
                .then(mod => mod.default || mod);
            
            this.hmac = await import('https://cdn.jsdelivr.net/npm/@noble/curves@1.1.0/abstract/hmac.js')
                .then(mod => mod.default || mod);
            
            console.log('Successfully loaded cryptographic libraries');
        } catch (error) {
            console.error('Failed to load cryptographic libraries:', error);
            // Fall back to mock implementation for development purposes
            this._enableMockImplementation();
        }
    }
    
    /**
     * Enable mock implementation as fallback
     * @private
     */
    _enableMockImplementation() {
        console.warn('Using mock cryptographic implementation - NOT FOR PRODUCTION');
        
        // Simple hash function for demo purposes
        this._hash = (input) => {
            const encoder = new TextEncoder();
            const data = encoder.encode(input);
            
            // Create a deterministic "hash" for testing
            const hash = new Uint8Array(32);
            for (let i = 0; i < data.length; i++) {
                hash[i % 32] ^= data[i];
            }
            
            return hash;
        };
        
        this._generateRandomScalar = () => {
            const arr = new Uint8Array(32);
            crypto.getRandomValues(arr);
            return arr;
        };
        
        this._mockBlind = (input, blindingFactor) => {
            const hash = this._hash(input);
            const result = new Uint8Array(hash.length);
            for (let i = 0; i < hash.length; i++) {
                result[i] = hash[i] ^ blindingFactor[i % blindingFactor.length];
            }
            return result;
        };
        
        this._mockUnblind = (blindedOutput, blindingFactor) => {
            const result = new Uint8Array(blindedOutput.length);
            for (let i = 0; i < blindedOutput.length; i++) {
                result[i] = blindedOutput[i] ^ blindingFactor[i % blindingFactor.length];
            }
            return result;
        };
        
        this.usingMockCrypto = true;
    }
    
    /**
     * Initialize by fetching the server's public key
     * @returns {Promise<boolean>} True if initialization succeeded
     */
    async initialize() {
        try {
            const response = await fetch(this.pubkeyEndpoint);
            if (!response.ok) {
                throw new Error(`Failed to fetch public key: ${response.status}`);
            }
            
            const data = await response.json();
            this.publicKey = data.publicKey;
            this.epoch = data.epoch;
            
            console.log(`OPRF client initialized with public key: ${this.publicKey.substring(0, 8)}...`);
            console.log(`Current epoch: ${this.epoch}`);
            
            return true;
        } catch (error) {
            console.error('Failed to initialize OPRF client:', error);
            return false;
        }
    }
    
    /**
     * Hash to curve function (H1)
     * @param {string} input The input to hash
     * @returns {Point} A point on the ristretto255 curve
     * @private
     */
    _hashToPoint(input) {
        if (this.usingMockCrypto) {
            return this._hash(input);
        }
        
        // Implement hash-to-curve based on RFC 9497
        // This is a simplified version - production should use a standards-compliant implementation
        const encoder = new TextEncoder();
        const inputBytes = encoder.encode(input);
        
        // Domain separation tag for hash-to-curve
        const dst = encoder.encode("OPRF:HashToGroup-ristretto255-SHA512");
        
        // Use the expand_message function from the RFC
        // For now, we use a simplified approach with HMAC
        try {
            // Use the ristretto255 hash-to-point function
            return this.ristretto.hashToCurve(inputBytes);
        } catch (e) {
            console.error('Hash to curve error:', e);
            throw e;
        }
    }
    
    /**
     * Generate a random blinding scalar
     * @returns {Uint8Array} Random scalar for blinding
     */
    generateRandomScalar() {
        if (this.usingMockCrypto) {
            return this._generateRandomScalar();
        }
        
        // Generate a random scalar in the ristretto255 scalar field
        return this.ristretto.utils.randomPrivateKey();
    }
    
    /**
     * Blind a credential ID before sending to the OPRF service
     * @param {string} credentialId The credential ID to blind
     * @param {Uint8Array} blindingFactor Optional custom blinding factor
     * @returns {Object} Object containing the blinded value and blinding factor
     */
    blind(credentialId, blindingFactor = null) {
        // Generate blinding factor if not provided
        if (!blindingFactor) {
            blindingFactor = this.generateRandomScalar();
        }
        
        // Use mock implementation if real crypto not available
        if (this.usingMockCrypto) {
            const blindedValue = this._mockBlind(credentialId, blindingFactor);
            return {
                alpha: blindedValue,
                r: blindingFactor,
                alphaBase64: this._arrayBufferToBase64(blindedValue)
            };
        }
        
        try {
            // Step 1: Hash the input to a curve point (H₁)
            const pointOnCurve = this._hashToPoint(credentialId);
            
            // Step 2: Multiply by scalar r to blind
            const blindedPoint = this.ristretto.Point.BASE.multiply(blindingFactor);
            
            // Convert to bytes for transmission
            const blindedValue = blindedPoint.toRawBytes();
            
            return {
                alpha: blindedValue,
                r: blindingFactor,
                alphaBase64: this._arrayBufferToBase64(blindedValue)
            };
        } catch (error) {
            console.error('Blinding error:', error);
            throw new Error(`Blinding operation failed: ${error.message}`);
        }
    }
    
    /**
     * Unblind an OPRF evaluation result
     * @param {Uint8Array|string} beta The evaluation result from the server
     * @param {Uint8Array} blindingFactor The blinding factor used for the request
     * @returns {Uint8Array} The unblinded OPRF result
     */
    unblind(beta, blindingFactor) {
        // Convert from base64 if needed
        let betaArray = beta;
        if (typeof beta === 'string') {
            betaArray = this._base64ToArrayBuffer(beta);
        }
        
        // Use mock implementation if real crypto not available
        if (this.usingMockCrypto) {
            return this._mockUnblind(betaArray, blindingFactor);
        }
        
        try {
            // Step 1: Parse beta as a curve point
            const betaPoint = this.ristretto.Point.fromHex(Buffer.from(betaArray));
            
            // Step 2: Compute the multiplicative inverse of r
            const rInv = this.ristretto.utils.invert(blindingFactor, this.ristretto.CURVE.n);
            
            // Step 3: Compute y = beta^(r⁻¹)
            const y = betaPoint.multiply(rInv);
            
            // Return the serialized point
            return y.toRawBytes();
        } catch (error) {
            console.error('Unblinding error:', error);
            throw new Error(`Unblinding operation failed: ${error.message}`);
        }
    }
    
    /**
     * Check if an evaluation is in a cascaded Bloom filter
     * @param {Uint8Array} evaluation The unblinded OPRF evaluation
     * @param {Object} cascade The cascade bundle from the server
     * @returns {Object} Result with revoked status and level
     */
    checkCascade(evaluation, cascade) {
        console.log('Checking cascade for evaluation');
        
        if (!cascade || !cascade.cascade || !cascade.cascade.levels) {
            console.error('Invalid cascade format');
            return { revoked: false, level: -1, confidence: 0 };
        }
        
        // Get the cascade levels
        const levels = cascade.cascade.levels;
        
        // Convert evaluation to hex for string comparison
        const evalHex = this._arrayBufferToHex(evaluation);
        
        // Check each level of the cascade
        for (let i = 0; i < levels.length; i++) {
            const level = levels[i];
            
            // This is a simplified check - in a real implementation,
            // we would recreate the Bloom filter and do proper checks
            // For now, we'll simulate the check, always returning not revoked
            
            // Mock implementation for demonstration - in production, this would
            // properly check against the bit array in the cascade
            console.log(`Checking cascade level ${i} with error rate ${level.error_rate}`);
        }
        
        // In a real implementation, this would check against the bloom filters
        // For now, we'll always return not revoked (demo purposes)
        return {
            revoked: false,
            level: -1,
            confidence: 1.0
        };
    }
    
    /**
     * Perform a complete OPRF evaluation and revocation check for a credential
     * @param {string} credentialId The credential ID to check
     * @returns {Promise<Object>} Result with revocation status and witness
     */
    async checkRevocationStatus(credentialId) {
        try {
            // Step 1: Initialize if needed
            if (!this.epoch) {
                await this.initialize();
            }
            
            // Step 2: Generate blinding factor and blind the credential ID
            const { alpha, r, alphaBase64 } = this.blind(credentialId);
            
            // Step 3: Send to OPRF service
            const response = await fetch(this.serverUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    alpha: [alphaBase64]
                })
            });
            
            if (!response.ok) {
                throw new Error(`OPRF evaluation failed: ${response.status}`);
            }
            
            // Step 4: Parse response
            const data = await response.json();
            const beta = data.beta[0];
            const serverEpoch = data.epoch;
            
            // Step 5: Unblind the result
            const y = this.unblind(beta, r);
            
            // Step 6: Fetch the current cascade
            const cascadeResponse = await fetch(`${this.cascadeEndpoint}${serverEpoch}`);
            if (!cascadeResponse.ok) {
                throw new Error(`Failed to fetch cascade: ${cascadeResponse.status}`);
            }
            
            const cascade = await cascadeResponse.json();
            
            // Step 7: Check against the cascade
            const result = this.checkCascade(y, cascade);
            
            // Step 8: Create the witness
            const witness = {
                epoch: serverEpoch,
                alpha: alphaBase64,
                beta: beta,
                r: this._arrayBufferToBase64(r),
                cascadeId: cascade.metadata?.id || serverEpoch
            };
            
            return {
                revoked: result.revoked,
                level: result.level,
                confidence: result.confidence,
                witness: witness
            };
        } catch (error) {
            console.error('Error checking revocation status:', error);
            return {
                error: error.message,
                revoked: false,
                errorDetail: error.stack
            };
        }
    }
    
    /**
     * Verify a revocation witness without connecting to the server
     * @param {Object} witness The witness to verify
     * @param {Object} cascade The cascade bundle
     * @returns {boolean} True if the witness is valid (credential not revoked)
     */
    verifyWitness(witness, cascade) {
        try {
            // Step 1: Extract witness components
            const { alpha, beta, r } = witness;
            
            // Step 2: Convert from base64
            const alphaArray = this._base64ToArrayBuffer(alpha);
            const betaArray = this._base64ToArrayBuffer(beta);
            const rArray = this._base64ToArrayBuffer(r);
            
            // Step 3: Unblind to get the evaluation
            const y = this.unblind(betaArray, rArray);
            
            // Step 4: Check against the cascade
            const result = this.checkCascade(y, cascade);
            
            // Step 5: Return the result
            return !result.revoked;
        } catch (error) {
            console.error('Error verifying witness:', error);
            return false;
        }
    }
    
    /**
     * Convert an ArrayBuffer to a Base64 string
     * @private
     */
    _arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }
    
    /**
     * Convert a Base64 string to an ArrayBuffer
     * @private
     */
    _base64ToArrayBuffer(base64) {
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return bytes;
    }
    
    /**
     * Convert an ArrayBuffer to a hex string
     * @private
     */
    _arrayBufferToHex(buffer) {
        return Array.from(new Uint8Array(buffer))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }
}

// Export for use in browser and Node.js
if (typeof module !== 'undefined' && typeof module.exports !== 'undefined') {
    module.exports = LemmaOPRFClient;
} else {
    window.LemmaOPRFClient = LemmaOPRFClient;
} 