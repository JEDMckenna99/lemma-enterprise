/**
 * Lemma Message Construction - MATCHES RUST SERVER EXACTLY
 * =========================================================
 * 
 * CRITICAL: This MUST match lemma-crypto/src/minimal_core.rs::create_signing_message()
 * 
 * Any deviation will cause signature verification to fail!
 */

class LemmaMessageConstructor {
    constructor() {
        this.textEncoder = new TextEncoder();
    }
    
    /**
     * Create message for signature verification
     * MUST MATCH: lemma-crypto/src/minimal_core.rs::create_signing_message()
     * 
     * @param {Object} credential - The credential to create message from
     * @returns {Promise<Uint8Array>} - SHA-256 hash of message (32 bytes)
     */
    async createVerificationMessage(credential) {
        try {
            // Build message parts in EXACT order as Rust code
            const parts = [];
            
            // 1. credential.id (required)
            if (!credential.id) {
                throw new Error('Credential missing id field');
            }
            parts.push(this.textEncoder.encode(credential.id));
            
            // 2. credential.issuer (required)
            if (!credential.issuer) {
                throw new Error('Credential missing issuer field');
            }
            parts.push(this.textEncoder.encode(credential.issuer));
            
            // 3. credential.subject (required)
            if (!credential.subject) {
                throw new Error('Credential missing subject field');
            }
            parts.push(this.textEncoder.encode(credential.subject));
            
            // 4. credential.issued_at, issuedAt, or issuanceDate (W3C) (required, as u64 little-endian)
            const issuedAt = credential.issued_at || credential.issuedAt || credential.issuanceDate;
            if (!issuedAt) {
                throw new Error('Credential missing issued_at/issuedAt/issuanceDate field');
            }
            parts.push(this.u64ToLeBytes(issuedAt));
            
            // 5. credential.expires_at, expiresAt, or expirationDate (W3C) (optional, as u64 little-endian)
            const expiresAt = credential.expires_at || credential.expiresAt || credential.expirationDate;
            if (expiresAt) {
                parts.push(this.u64ToLeBytes(expiresAt));
            }
            
            // 6. credential.claims or credentialSubject (sorted alphabetically)
            const claims = credential.claims || credential.credentialSubject || {};
            const claimKeys = Object.keys(claims).sort(); // Alphabetical sort
            
            for (const key of claimKeys) {
                // Add key
                parts.push(this.textEncoder.encode(key));
                
                // Add value as JSON string (same as Rust serde_json::to_string)
                const value = claims[key];
                const valueJson = JSON.stringify(value);
                parts.push(this.textEncoder.encode(valueJson));
            }
            
            // Concatenate all parts
            const totalLength = parts.reduce((sum, part) => sum + part.length, 0);
            const message = new Uint8Array(totalLength);
            let offset = 0;
            for (const part of parts) {
                message.set(part, offset);
                offset += part.length;
            }
            
            // SHA-256 hash (CRITICAL - Rust uses SHA-256)
            const hashBuffer = await crypto.subtle.digest('SHA-256', message);
            return new Uint8Array(hashBuffer);
            
        } catch (error) {
            console.error('Message construction error:', error);
            throw error;
        }
    }
    
    /**
     * Convert u64 to little-endian bytes (matches Rust .to_le_bytes())
     * @param {number|string} value - Timestamp as number or string
     * @returns {Uint8Array} - 8 bytes in little-endian order
     */
    u64ToLeBytes(value) {
        // Convert to number if string
        const num = typeof value === 'string' ? parseInt(value, 10) : value;
        
        if (isNaN(num) || num < 0) {
            throw new Error(`Invalid u64 value: ${value}`);
        }
        
        // Create 8-byte array
        const bytes = new ArrayBuffer(8);
        const view = new DataView(bytes);
        
        // Set as little-endian u64
        // JavaScript numbers are safe up to 2^53, use BigInt for safety
        const bigNum = BigInt(num);
        view.setBigUint64(0, bigNum, true); // true = little-endian
        
        return new Uint8Array(bytes);
    }
    
    /**
     * Debug: Show message construction breakdown
     */
    async debugMessageConstruction(credential) {
        console.log('=== Message Construction Debug ===');
        console.log('Credential:', credential);
        
        const parts = [];
        
        console.log('\n1. ID:', credential.id);
        parts.push({ name: 'id', bytes: this.textEncoder.encode(credential.id) });
        
        console.log('2. Issuer:', credential.issuer);
        parts.push({ name: 'issuer', bytes: this.textEncoder.encode(credential.issuer) });
        
        console.log('3. Subject:', credential.subject);
        parts.push({ name: 'subject', bytes: this.textEncoder.encode(credential.subject) });
        
        const issuedAt = credential.issued_at || credential.issuedAt;
        console.log('4. Issued At:', issuedAt);
        const issuedBytes = this.u64ToLeBytes(issuedAt);
        console.log('   As LE bytes:', Array.from(issuedBytes).map(b => b.toString(16).padStart(2, '0')).join(' '));
        parts.push({ name: 'issued_at', bytes: issuedBytes });
        
        const expiresAt = credential.expires_at || credential.expiresAt;
        if (expiresAt) {
            console.log('5. Expires At:', expiresAt);
            const expiresBytes = this.u64ToLeBytes(expiresAt);
            console.log('   As LE bytes:', Array.from(expiresBytes).map(b => b.toString(16).padStart(2, '0')).join(' '));
            parts.push({ name: 'expires_at', bytes: expiresBytes });
        }
        
        const claims = credential.claims || credential.credentialSubject || {};
        const claimKeys = Object.keys(claims).sort();
        console.log('\n6. Claims (sorted):', claimKeys);
        for (const key of claimKeys) {
            const value = claims[key];
            const valueJson = JSON.stringify(value);
            console.log(`   ${key}: ${valueJson}`);
            parts.push({ 
                name: `claim_key_${key}`, 
                bytes: this.textEncoder.encode(key) 
            });
            parts.push({ 
                name: `claim_value_${key}`, 
                bytes: this.textEncoder.encode(valueJson) 
            });
        }
        
        // Show total message
        const totalLength = parts.reduce((sum, part) => sum + part.bytes.length, 0);
        console.log('\nTotal message length:', totalLength, 'bytes');
        
        // Show first 100 bytes
        const message = new Uint8Array(totalLength);
        let offset = 0;
        for (const part of parts) {
            message.set(part.bytes, offset);
            offset += part.bytes.length;
        }
        
        console.log('First 100 bytes:', 
            Array.from(message.slice(0, 100))
                .map(b => b.toString(16).padStart(2, '0'))
                .join(' ')
        );
        
        // SHA-256 hash
        const hash = await crypto.subtle.digest('SHA-256', message);
        const hashArray = Array.from(new Uint8Array(hash));
        console.log('\nSHA-256 hash:', hashArray.map(b => b.toString(16).padStart(2, '0')).join(''));
        
        return new Uint8Array(hash);
    }
}

// Export for use in other scripts
if (typeof window !== 'undefined') {
    window.LemmaMessageConstructor = LemmaMessageConstructor;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaMessageConstructor;
}

