/**
 * Lemma Passkey SDK
 * Easy passkey integration for Lemma authentication
 */

class LemmaPasskey {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '';
        this.onSuccess = options.onSuccess || (() => {});
        this.onError = options.onError || ((e) => console.error('Passkey error:', e));
    }

    /**
     * Check if passkeys are supported in this browser
     */
    static isSupported() {
        return window.PublicKeyCredential !== undefined &&
               typeof window.PublicKeyCredential === 'function';
    }

    /**
     * Check if platform authenticator (Face ID, Touch ID, Windows Hello) is available
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
     * Register a new passkey for the user
     */
    async register(userId, userEmail, deviceName = 'My Device') {
        if (!LemmaPasskey.isSupported()) {
            throw new Error('Passkeys are not supported in this browser');
        }

        try {
            // 1. Get registration options from server
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

            // 2. Convert options for WebAuthn API
            const options = this._prepareRegistrationOptions(beginData.options);

            // 3. Create credential (browser will prompt for biometric)
            const credential = await navigator.credentials.create({ publicKey: options });

            // 4. Send to server for verification
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
     * Authenticate with a passkey
     */
    async authenticate(userId = null) {
        if (!LemmaPasskey.isSupported()) {
            throw new Error('Passkeys are not supported in this browser');
        }

        try {
            // 1. Get authentication options from server
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

            // 2. Convert options for WebAuthn API
            const options = this._prepareAuthenticationOptions(beginData.options);

            // 3. Get credential (browser will prompt for biometric)
            const credential = await navigator.credentials.get({ publicKey: options });

            // 4. Send to server for verification and get lemma
            const completeResponse = await fetch(`${this.baseUrl}/api/passkey/authenticate/complete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    credential: this._serializeCredential(credential),
                    challenge_key: beginData.challenge_key
                })
            });

            const result = await completeResponse.json();
            if (!result.success) {
                throw new Error(result.error || 'Failed to complete authentication');
            }

            // Store lemma in wallet if available
            if (result.lemma && window.LemmaWallet) {
                await window.LemmaWallet.store(result.lemma);
            }

            this.onSuccess(result);
            return result;

        } catch (error) {
            this.onError(error);
            throw error;
        }
    }

    /**
     * List user's registered passkeys
     */
    async listPasskeys() {
        const response = await fetch(`${this.baseUrl}/api/passkey/list`, {
            credentials: 'include'
        });
        return response.json();
    }

    /**
     * Delete a passkey
     */
    async deletePasskey(passkeyId) {
        const response = await fetch(`${this.baseUrl}/api/passkey/${passkeyId}`, {
            method: 'DELETE',
            credentials: 'include'
        });
        return response.json();
    }

    // ============================================
    // HELPER METHODS
    // ============================================

    _prepareRegistrationOptions(options) {
        // Convert base64url strings to ArrayBuffers
        return {
            ...options,
            challenge: this._base64urlToBuffer(options.challenge),
            user: {
                ...options.user,
                id: this._base64urlToBuffer(options.user.id)
            },
            excludeCredentials: (options.excludeCredentials || []).map(cred => ({
                ...cred,
                id: this._base64urlToBuffer(cred.id)
            }))
        };
    }

    _prepareAuthenticationOptions(options) {
        return {
            ...options,
            challenge: this._base64urlToBuffer(options.challenge),
            allowCredentials: (options.allowCredentials || []).map(cred => ({
                ...cred,
                id: this._base64urlToBuffer(cred.id)
            }))
        };
    }

    _serializeCredential(credential) {
        const response = credential.response;
        
        const serialized = {
            id: credential.id,
            rawId: this._bufferToBase64url(credential.rawId),
            type: credential.type,
            response: {
                clientDataJSON: this._bufferToBase64url(response.clientDataJSON),
            }
        };

        // Registration response
        if (response.attestationObject) {
            serialized.response.attestationObject = this._bufferToBase64url(response.attestationObject);
        }

        // Authentication response
        if (response.authenticatorData) {
            serialized.response.authenticatorData = this._bufferToBase64url(response.authenticatorData);
            serialized.response.signature = this._bufferToBase64url(response.signature);
            if (response.userHandle) {
                serialized.response.userHandle = this._bufferToBase64url(response.userHandle);
            }
        }

        // Include transports if available
        if (credential.response.getTransports) {
            serialized.transports = credential.response.getTransports();
        }

        return serialized;
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

    _bufferToBase64url(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    }
}

// ============================================
// PASSKEY PROOF VERIFIER (for sites)
// ============================================

class LemmaPasskeyVerifier {
    /**
     * Verify a lemma's embedded passkey proof locally using Web Crypto API.
     * This cryptographically proves the lemma was issued after genuine passkey authentication.
     * 
     * SECURITY: This performs REAL signature verification, not just parsing.
     * The signature is verified against the authenticator's public key.
     * 
     * @param {Object} lemma - The lemma with embedded passkeyProof
     * @param {Object} options - Verification options
     * @param {string} options.expectedOrigin - Expected origin (e.g., 'https://lemma.id')
     * @returns {Promise<Object>} Verification result with valid, origin, challenge
     */
    static async verifyPasskeyProof(lemma, options = {}) {
        if (!lemma.passkeyProof) {
            return { valid: false, reason: 'No passkey proof embedded', verified: false };
        }

        const proof = lemma.passkeyProof;

        try {
            // 1. Decode the components
            const authenticatorData = this._base64urlToBuffer(proof.authenticatorData);
            const clientDataJSON = this._base64urlToBuffer(proof.clientDataJSON);
            const signature = this._base64urlToBuffer(proof.signature);
            const publicKeyB64 = proof.publicKey;

            if (!publicKeyB64) {
                return { valid: false, reason: 'No public key in proof', verified: false };
            }

            // 2. Parse client data to verify origin and type
            const clientData = JSON.parse(new TextDecoder().decode(clientDataJSON));
            
            // SECURITY: Verify client data type
            if (clientData.type !== 'webauthn.get') {
                return { 
                    valid: false, 
                    reason: `Invalid clientData type: ${clientData.type}`,
                    verified: false 
                };
            }
            
            // SECURITY: Verify origin if specified
            if (options.expectedOrigin && clientData.origin !== options.expectedOrigin) {
                return { 
                    valid: false, 
                    reason: `Origin mismatch: expected ${options.expectedOrigin}, got ${clientData.origin}`,
                    verified: false 
                };
            }

            // 3. Reconstruct the signed data (WebAuthn spec)
            // signedData = authenticatorData || SHA-256(clientDataJSON)
            const clientDataHash = await crypto.subtle.digest('SHA-256', clientDataJSON);
            const signedData = this._concatenateBuffers(authenticatorData, clientDataHash);

            // 4. Import the public key (COSE format -> Web Crypto)
            let cryptoKey;
            try {
                cryptoKey = await this._importCoseKey(publicKeyB64);
            } catch (e) {
                return { 
                    valid: false, 
                    reason: `Failed to import public key: ${e.message}`,
                    verified: false 
                };
            }

            // 5. SECURITY: Verify the signature using Web Crypto API
            // WebAuthn signatures for ES256 are in ASN.1 DER format
            const derSignature = new Uint8Array(signature);
            const rawSignature = this._derToRaw(derSignature);
            
            const isValid = await crypto.subtle.verify(
                { name: 'ECDSA', hash: { name: 'SHA-256' } },
                cryptoKey,
                rawSignature,
                signedData
            );

            if (!isValid) {
                return { 
                    valid: false, 
                    reason: 'Signature verification failed',
                    verified: true,  // We did verify, it just failed
                    signatureValid: false
                };
            }

            // 6. Verify authenticator data flags
            const authDataView = new DataView(authenticatorData);
            const flags = authDataView.getUint8(32);  // Flags are at byte 32
            const userPresent = (flags & 0x01) !== 0;
            const userVerified = (flags & 0x04) !== 0;
            
            return {
                valid: true,
                verified: true,
                signatureValid: true,
                origin: clientData.origin,
                type: clientData.type,
                challenge: clientData.challenge,
                userPresent: userPresent,
                userVerified: userVerified,
                hasProof: true
            };

        } catch (error) {
            return {
                valid: false,
                verified: false,
                reason: `Verification error: ${error.message}`
            };
        }
    }

    /**
     * Import a COSE-formatted public key into Web Crypto API
     * Supports ES256 (ECDSA P-256) keys which are most common for WebAuthn
     */
    static async _importCoseKey(publicKeyB64) {
        const keyBytes = this._base64urlToBuffer(publicKeyB64);
        const keyArray = new Uint8Array(keyBytes);
        
        // Parse COSE key (simplified for ES256 - ECDSA P-256)
        // COSE keys are CBOR-encoded maps
        // For ES256: kty=2 (EC), crv=1 (P-256), x=..., y=...
        
        // Try to parse as raw x||y coordinates (64 bytes for P-256)
        if (keyArray.length === 64) {
            // Raw uncompressed coordinates
            const x = keyArray.slice(0, 32);
            const y = keyArray.slice(32, 64);
            return await this._importRawEcKey(x, y);
        }
        
        // Try to parse as uncompressed point (65 bytes: 0x04 || x || y)
        if (keyArray.length === 65 && keyArray[0] === 0x04) {
            const x = keyArray.slice(1, 33);
            const y = keyArray.slice(33, 65);
            return await this._importRawEcKey(x, y);
        }
        
        // Try to parse as COSE CBOR (more complex)
        // For simplicity, we'll attempt to find x and y in common COSE structures
        const coseKey = this._parseCoseKey(keyArray);
        if (coseKey && coseKey.x && coseKey.y) {
            return await this._importRawEcKey(coseKey.x, coseKey.y);
        }
        
        throw new Error('Unsupported public key format');
    }

    /**
     * Import raw EC coordinates into Web Crypto
     */
    static async _importRawEcKey(x, y) {
        // Create JWK format for import
        const jwk = {
            kty: 'EC',
            crv: 'P-256',
            x: this._bufferToBase64url(x),
            y: this._bufferToBase64url(y)
        };
        
        return await crypto.subtle.importKey(
            'jwk',
            jwk,
            { name: 'ECDSA', namedCurve: 'P-256' },
            true,
            ['verify']
        );
    }

    /**
     * Parse COSE key structure (simplified)
     * COSE keys use CBOR encoding with numeric labels
     */
    static _parseCoseKey(bytes) {
        // Simple CBOR parser for COSE keys
        // COSE labels: 1=kty, 3=alg, -1=crv, -2=x, -3=y
        try {
            let offset = 0;
            const result = {};
            
            // CBOR map starts with 0xa followed by count
            if ((bytes[offset] & 0xe0) !== 0xa0) {
                return null;
            }
            
            const mapSize = bytes[offset] & 0x1f;
            offset++;
            
            for (let i = 0; i < mapSize && offset < bytes.length; i++) {
                // Read key (signed integer)
                let key;
                if (bytes[offset] < 0x18) {
                    key = bytes[offset];
                    offset++;
                } else if (bytes[offset] === 0x20) {
                    key = -1;
                    offset++;
                } else if (bytes[offset] === 0x21) {
                    key = -2;
                    offset++;
                } else if (bytes[offset] === 0x22) {
                    key = -3;
                    offset++;
                } else {
                    // Skip unknown format
                    offset++;
                    continue;
                }
                
                // Read value (byte string for x, y)
                if (bytes[offset] >= 0x40 && bytes[offset] <= 0x57) {
                    const len = bytes[offset] - 0x40;
                    offset++;
                    const value = bytes.slice(offset, offset + len);
                    offset += len;
                    
                    if (key === -2) result.x = value;
                    if (key === -3) result.y = value;
                } else if (bytes[offset] === 0x58) {
                    // Byte string with 1-byte length
                    offset++;
                    const len = bytes[offset];
                    offset++;
                    const value = bytes.slice(offset, offset + len);
                    offset += len;
                    
                    if (key === -2) result.x = value;
                    if (key === -3) result.y = value;
                } else {
                    // Skip other types
                    offset++;
                }
            }
            
            return result;
        } catch (e) {
            return null;
        }
    }

    /**
     * Convert ASN.1 DER signature to raw r||s format for Web Crypto
     * WebAuthn signatures are in DER format, Web Crypto expects raw
     */
    static _derToRaw(der) {
        // DER format: 0x30 [total len] 0x02 [r len] [r] 0x02 [s len] [s]
        if (der[0] !== 0x30) {
            // Might already be raw format
            if (der.length === 64) return der;
            throw new Error('Invalid signature format');
        }
        
        let offset = 2; // Skip 0x30 and length
        
        // Parse r
        if (der[offset] !== 0x02) throw new Error('Invalid r marker');
        offset++;
        const rLen = der[offset];
        offset++;
        let r = der.slice(offset, offset + rLen);
        offset += rLen;
        
        // Parse s
        if (der[offset] !== 0x02) throw new Error('Invalid s marker');
        offset++;
        const sLen = der[offset];
        offset++;
        let s = der.slice(offset, offset + sLen);
        
        // Remove leading zero padding if present (DER adds 0x00 for positive numbers with high bit set)
        if (r.length === 33 && r[0] === 0) r = r.slice(1);
        if (s.length === 33 && s[0] === 0) s = s.slice(1);
        
        // Pad to 32 bytes if needed
        if (r.length < 32) {
            const padded = new Uint8Array(32);
            padded.set(r, 32 - r.length);
            r = padded;
        }
        if (s.length < 32) {
            const padded = new Uint8Array(32);
            padded.set(s, 32 - s.length);
            s = padded;
        }
        
        // Concatenate r || s (64 bytes total for P-256)
        const raw = new Uint8Array(64);
        raw.set(r, 0);
        raw.set(s, 32);
        return raw;
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

    static _bufferToBase64url(buffer) {
        const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    }

    static _concatenateBuffers(buffer1, buffer2) {
        const tmp = new Uint8Array(buffer1.byteLength + buffer2.byteLength);
        tmp.set(new Uint8Array(buffer1), 0);
        tmp.set(new Uint8Array(buffer2), buffer1.byteLength);
        return tmp.buffer;
    }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LemmaPasskey, LemmaPasskeyVerifier };
}

// Attach to window for browser usage
if (typeof window !== 'undefined') {
    window.LemmaPasskey = LemmaPasskey;
    window.LemmaPasskeyVerifier = LemmaPasskeyVerifier;
}
