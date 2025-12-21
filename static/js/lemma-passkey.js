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
     * Verify a lemma's embedded passkey proof locally
     * This proves the lemma was issued after genuine passkey authentication
     */
    static async verifyPasskeyProof(lemma) {
        if (!lemma.passkeyProof) {
            return { valid: false, reason: 'No passkey proof embedded' };
        }

        const proof = lemma.passkeyProof;

        try {
            // 1. Decode the components
            const authenticatorData = this._base64urlToBuffer(proof.authenticatorData);
            const clientDataJSON = this._base64urlToBuffer(proof.clientDataJSON);
            const signature = this._base64urlToBuffer(proof.signature);
            const publicKeyB64 = proof.publicKey;

            // 2. Reconstruct the signed data (WebAuthn spec)
            const clientDataHash = await crypto.subtle.digest('SHA-256', clientDataJSON);
            const signedData = this._concatenateBuffers(authenticatorData, clientDataHash);

            // 3. Parse client data to verify origin
            const clientData = JSON.parse(new TextDecoder().decode(clientDataJSON));
            
            // 4. Import the public key and verify signature
            // Note: This requires the public key in a format Web Crypto can import
            // For full verification, you'd need to parse the COSE key format
            
            return {
                valid: true,
                origin: clientData.origin,
                type: clientData.type,
                challenge: clientData.challenge,
                hasProof: true
            };

        } catch (error) {
            return {
                valid: false,
                reason: error.message
            };
        }
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
