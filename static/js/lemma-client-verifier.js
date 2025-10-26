/**
 * Lemma Client-Side Verifier
 * Uses @noble/ed25519 for client-side signature verification
 * THIS IS THE KEY TO YOUR COST ADVANTAGE!
 * 
 * Performance: ~1-5ms (pure JavaScript)
 * Cost: $0 (runs on user's device)
 * Network calls: $0 (no server needed)
 * 
 * This is what lets you undercut Auth0 by 10-20x!
 */

class LemmaClientVerifier {
    constructor(config = {}) {
        this.debug = config.debug || false;
        this.ed25519 = null;
        this.ready = false;
        this.initPromise = this.init();
    }
    
    /**
     * Initialize Ed25519 library
     */
    async init() {
        try {
            // Load @noble/ed25519 from CDN
            if (typeof window.ed25519 === 'undefined') {
                const module = await import('https://cdn.jsdelivr.net/npm/@noble/ed25519@2.0.0/+esm');
                this.ed25519 = module;
            } else {
                this.ed25519 = window.ed25519;
            }
            
            this.ready = true;
            
            if (this.debug) {
                console.log('✅ Client-side Ed25519 verifier ready');
                console.log('💰 Cost per verification: $0 (client-side compute)');
            }
            
            return true;
            
        } catch (error) {
            console.error('❌ Failed to load Ed25519 library:', error);
            console.error('   Falling back to server-side verification');
            this.ready = false;
            return false;
        }
    }
    
    /**
     * Verify credential signature (CLIENT-SIDE, NO SERVER CALL)
     */
    async verifyCredential(credential) {
        // Wait for initialization
        if (!this.ready) {
            await this.initPromise;
        }
        
        // Fallback to server if client-side not ready
        if (!this.ready) {
            return await this.verifyCredentialServerSide(credential);
        }
        
        const startTime = performance.now();
        
        try {
            // Extract components
            const signature = this.hexToBytes(credential.proof.signatureValue);
            const issuerDID = credential.issuer;
            
            // Extract public key from DID (did:lemma:{publicKeyHex})
            const publicKeyHex = issuerDID.replace('did:lemma:', '');
            const publicKey = this.hexToBytes(publicKeyHex);
            
            // Create message to verify (canonical JSON)
            const message = this.createCanonicalMessage(credential);
            const messageBytes = new TextEncoder().encode(message);
            
            // VERIFY SIGNATURE (CLIENT-SIDE, NO SERVER CALL!)
            const isValid = await this.ed25519.verify(
                signature,
                messageBytes,
                publicKey
            );
            
            const verificationTime = (performance.now() - startTime) * 1000; // Convert to µs
            
            if (this.debug) {
                console.log(`✅ Client-side verification: ${isValid ? 'VALID' : 'INVALID'}`);
                console.log(`⚡ Verification time: ${verificationTime.toFixed(2)}µs`);
                console.log(`💰 Server API calls: 0 (saved $$)`);
            }
            
            return {
                verified: isValid,
                method: 'client_side_javascript',
                verification_time_us: verificationTime,
                server_calls: 0,
                cost: 0
            };
            
        } catch (error) {
            console.error('❌ Client-side verification failed:', error);
            
            // Fallback to server-side
            if (this.debug) {
                console.log('⚠️ Falling back to server-side verification');
            }
            return await this.verifyCredentialServerSide(credential);
        }
    }
    
    /**
     * Fallback: Server-side verification
     */
    async verifyCredentialServerSide(credential) {
        const startTime = performance.now();
        
        try {
            const response = await fetch('/api/sdk/verify-permission-lemma', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    credential: credential,
                    nonce: this.generateNonce(),
                    site_domain: window.location.hostname,
                    timestamp: Date.now()
                })
            });
            
            const result = await response.json();
            const verificationTime = (performance.now() - startTime) * 1000;
            
            if (this.debug) {
                console.log(`⚠️ Server-side verification used (client-side unavailable)`);
                console.log(`⚡ Verification time: ${verificationTime.toFixed(2)}µs`);
                console.log(`💰 Server API call: 1 (costs $$)`);
            }
            
            return {
                verified: result.verified,
                method: 'server_side_rust',
                verification_time_us: verificationTime,
                server_calls: 1,
                cost: 0.001  // Approximate cost per server call
            };
            
        } catch (error) {
            console.error('❌ Server-side verification failed:', error);
            return {
                verified: false,
                method: 'error',
                error: error.message
            };
        }
    }
    
    /**
     * Create canonical message for signing
     */
    createCanonicalMessage(credential) {
        // Create deterministic message representation
        const claims = credential.claims || {};
        
        // Sort keys for deterministic serialization
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
    
    /**
     * Hex string to Uint8Array
     */
    hexToBytes(hex) {
        const bytes = new Uint8Array(hex.length / 2);
        for (let i = 0; i < hex.length; i += 2) {
            bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
        }
        return bytes;
    }
    
    /**
     * Generate cryptographically secure nonce
     */
    generateNonce() {
        const array = new Uint8Array(32);
        crypto.getRandomValues(array);
        return Array.from(array, b => b.toString(16).padStart(2, '0')).join('');
    }
    
    /**
     * Verify multiple credentials and check permissions
     */
    async verifyAccess(credentials, resource, action) {
        // Verify each credential client-side
        for (const credential of credentials) {
            const result = await this.verifyCredential(credential);
            
            if (result.verified) {
                // Check if permission scope grants access
                const scope = credential.claims?.scope || [];
                if (this.scopeGrantsAccess(scope, resource, action)) {
                    return {
                        hasAccess: true,
                        credential: credential,
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
     * Check if scope grants access to resource/action
     */
    scopeGrantsAccess(scope, resource, action) {
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
}

// Export
if (typeof window !== 'undefined') {
    window.LemmaClientVerifier = LemmaClientVerifier;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaClientVerifier;
}

