/**
 * Advanced Lemma Wallet with Recovery and Multi-Device Sync
 * Implements the advanced wallet specification with vault integration
 */

class LemmaAdvancedWallet {
    constructor(options = {}) {
        this.debug = options.debug || false;
        this.vaultUrl = options.vaultUrl || '/vault';
        this.enableRecovery = options.enableRecovery !== false;
        
        // Wallet state
        this.masterSeed = null;
        this.deviceKey = null;
        this.currentRID = null;
        this.currentVID = null;
        
        // Per-RP derived keys cache
        this.rpKeys = new Map();
        this.rpDIDs = new Map();
        this.rpTags = new Map();
        
        // Recovery state
        this.envelopeCounter = 0;
        this.recoveryFactors = new Map();
        
        if (this.debug) {
            console.log('🔐 Advanced Lemma Wallet initialized');
            console.log('⚡ Features: Recovery, Multi-device, Per-RP keys, Sybil prevention');
        }
    }

    /**
     * Initialize wallet with master seed generation
     */
    async initialize() {
        try {
            // Check if wallet already exists
            const existingWallet = await this.loadWalletFromStorage();
            
            if (existingWallet) {
                if (this.debug) {
                    console.log('✅ Loaded existing wallet from storage');
                }
                return { success: true, existing: true };
            }
            
            // Generate new wallet
            await this.generateNewWallet();
            
            if (this.debug) {
                console.log('✅ Generated new advanced wallet');
                console.log(`🔑 Master seed: ${this.masterSeed ? 'Generated' : 'Failed'}`);
                console.log(`📱 Device key: ${this.deviceKey ? 'Generated' : 'Failed'}`);
            }
            
            return { success: true, existing: false };
            
        } catch (error) {
            console.error('❌ Wallet initialization failed:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Generate new wallet with cryptographic keys
     */
    async generateNewWallet() {
        // Generate master seed (32 bytes)
        this.masterSeed = new Uint8Array(32);
        crypto.getRandomValues(this.masterSeed);
        
        // Generate device key for this device
        this.deviceKey = new Uint8Array(32);
        crypto.getRandomValues(this.deviceKey);
        
        // Initialize envelope counter
        this.envelopeCounter = 1;
        
        // Save to local storage
        await this.saveWalletToStorage();
        
        if (this.debug) {
            console.log('🔐 Generated new wallet keys');
        }
    }

    /**
     * Derive per-RP child key using HKDF
     */
    async deriveRPKey(rpId) {
        // Check cache first (performance optimization)
        if (this.rpKeys.has(rpId)) {
            if (this.debug) {
                console.log(`⚡ Using cached RP key for ${rpId}`);
            }
            return this.rpKeys.get(rpId);
        }
        
        if (!this.masterSeed) {
            throw new Error('Wallet not initialized - no master seed');
        }
        
        // Derive child key using HKDF (Web Crypto API)
        const start = performance.now();
        
        try {
            // Import master seed as key material
            const masterKey = await crypto.subtle.importKey(
                'raw',
                this.masterSeed,
                'HKDF',
                false,
                ['deriveKey']
            );
            
            // Derive child key for this RP
            const childKey = await crypto.subtle.deriveKey(
                {
                    name: 'HKDF',
                    hash: 'SHA-256',
                    salt: new Uint8Array(0),
                    info: new TextEncoder().encode(rpId)
                },
                masterKey,
                { name: 'AES-GCM', length: 256 },
                true,
                ['encrypt', 'decrypt']
            );
            
            // Export as raw bytes
            const childKeyBytes = await crypto.subtle.exportKey('raw', childKey);
            const childKeyArray = new Uint8Array(childKeyBytes);
            
            // Cache the result
            this.rpKeys.set(rpId, childKeyArray);
            
            const derivationTime = (performance.now() - start) * 1000;
            
            if (this.debug) {
                console.log(`🔑 Derived RP key for ${rpId}: ${derivationTime.toFixed(3)}μs`);
            }
            
            return childKeyArray;
            
        } catch (error) {
            throw new Error(`RP key derivation failed: ${error.message}`);
        }
    }

    /**
     * Generate DID for specific RP
     */
    async generateRPDID(rpId) {
        // Check cache first
        if (this.rpDIDs.has(rpId)) {
            return this.rpDIDs.get(rpId);
        }
        
        // Derive RP-specific key
        const rpKey = await this.deriveRPKey(rpId);
        
        // Generate Ed25519 key pair from derived key
        // TODO: Implement proper Ed25519 key generation
        // For now, use derived key as public key material
        const publicKeyHex = Array.from(rpKey)
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
        
        const did = `did:lemma:${publicKeyHex}`;
        
        // Cache the result
        this.rpDIDs.set(rpId, did);
        
        if (this.debug) {
            console.log(`🆔 Generated RP DID for ${rpId}: ${did.substring(0, 50)}...`);
        }
        
        return did;
    }

    /**
     * Generate pairwise tag for RP uniqueness enforcement
     */
    async generatePairwiseTag(rpId) {
        // Check cache first
        if (this.rpTags.has(rpId)) {
            return this.rpTags.get(rpId);
        }
        
        if (!this.currentRID) {
            throw new Error('No RID available - complete KYC first');
        }
        
        // Generate HMAC-based pairwise tag
        // tag_rp = HMAC(k_pair, RID || rp_id)
        const start = performance.now();
        
        try {
            // Simulate HMAC generation (would use server endpoint in production)
            const response = await fetch('/api/issuer/tag', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    rp_id: rpId,
                    rid_proof: 'internal_session_reference'  // Server knows RID from session
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                const tag = result.tag_rp;
                
                // Cache the result
                this.rpTags.set(rpId, tag);
                
                const tagTime = (performance.now() - start) * 1000;
                
                if (this.debug) {
                    console.log(`🏷️ Generated pairwise tag for ${rpId}: ${tagTime.toFixed(3)}μs`);
                }
                
                return tag;
            } else {
                throw new Error(`Tag generation failed: ${response.status}`);
            }
            
        } catch (error) {
            // Fallback to client-side HMAC (less secure but functional)
            if (this.debug) {
                console.warn('⚠️ Using client-side tag generation (fallback)');
            }
            
            const encoder = new TextEncoder();
            const ridBytes = encoder.encode(this.currentRID);
            const rpBytes = encoder.encode(rpId);
            
            // Simple hash as fallback (not cryptographically secure)
            const combined = new Uint8Array(ridBytes.length + rpBytes.length);
            combined.set(ridBytes);
            combined.set(rpBytes, ridBytes.length);
            
            const hashBuffer = await crypto.subtle.digest('SHA-256', combined);
            const tag = Array.from(new Uint8Array(hashBuffer))
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            this.rpTags.set(rpId, tag);
            return tag;
        }
    }

    /**
     * Save wallet to vault service
     */
    async saveToVault(passphrase) {
        if (!this.currentVID) {
            throw new Error('No VID available - complete KYC first');
        }
        
        try {
            // Create wallet envelope
            const envelope = {
                version: 1,
                counter: this.envelopeCounter + 1,
                wallet_schema: 1,
                master_seed: Array.from(this.masterSeed),
                device_records: this.getDeviceRecords(),
                metadata: {
                    created_at: new Date().toISOString(),
                    device_count: 1
                }
            };
            
            // Encrypt envelope (simplified - would use proper AEAD)
            const envelopeJson = JSON.stringify(envelope);
            const ciphertext = new TextEncoder().encode(envelopeJson); // Placeholder encryption
            const aad = new TextEncoder().encode('wallet_envelope_v1');
            
            // Save to vault
            const response = await fetch(`${this.vaultUrl}/put`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vid: this.currentVID,
                    ciphertext: Array.from(ciphertext).map(b => b.toString(16).padStart(2, '0')).join(''),
                    counter: envelope.counter,
                    aad: Array.from(aad).map(b => b.toString(16).padStart(2, '0')).join('')
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                this.envelopeCounter = envelope.counter;
                
                if (this.debug) {
                    console.log('✅ Wallet saved to vault');
                    console.log(`📊 Storage size: ${result.storage_size_bytes} bytes`);
                }
                
                return { success: true, counter: envelope.counter };
            } else {
                const error = await response.json();
                throw new Error(error.message || 'Vault storage failed');
            }
            
        } catch (error) {
            console.error('❌ Vault save failed:', error);
            throw error;
        }
    }

    /**
     * Load wallet from vault service
     */
    async loadFromVault(passphrase) {
        if (!this.currentVID) {
            throw new Error('No VID available - complete KYC first');
        }
        
        try {
            const response = await fetch(`${this.vaultUrl}/get`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vid: this.currentVID
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                
                // Decrypt envelope (simplified - would use proper AEAD)
                const ciphertext = new Uint8Array(
                    result.ciphertext.match(/.{2}/g).map(byte => parseInt(byte, 16))
                );
                const envelopeJson = new TextDecoder().decode(ciphertext); // Placeholder decryption
                const envelope = JSON.parse(envelopeJson);
                
                // Restore wallet state
                this.masterSeed = new Uint8Array(envelope.master_seed);
                this.envelopeCounter = envelope.counter;
                
                if (this.debug) {
                    console.log('✅ Wallet loaded from vault');
                    console.log(`📊 Counter: ${envelope.counter}`);
                }
                
                return { success: true, envelope };
            } else {
                const error = await response.json();
                throw new Error(error.message || 'Vault retrieval failed');
            }
            
        } catch (error) {
            console.error('❌ Vault load failed:', error);
            throw error;
        }
    }

    /**
     * Save wallet to local storage
     */
    async saveWalletToStorage() {
        const walletData = {
            masterSeed: this.masterSeed ? Array.from(this.masterSeed) : null,
            deviceKey: this.deviceKey ? Array.from(this.deviceKey) : null,
            envelopeCounter: this.envelopeCounter,
            rpKeys: Object.fromEntries(this.rpKeys),
            rpDIDs: Object.fromEntries(this.rpDIDs),
            rpTags: Object.fromEntries(this.rpTags),
            currentRID: this.currentRID,
            currentVID: this.currentVID
        };
        
        localStorage.setItem('lemma_advanced_wallet', JSON.stringify(walletData));
    }

    /**
     * Load wallet from local storage
     */
    async loadWalletFromStorage() {
        const walletData = localStorage.getItem('lemma_advanced_wallet');
        if (!walletData) return null;
        
        try {
            const data = JSON.parse(walletData);
            
            this.masterSeed = data.masterSeed ? new Uint8Array(data.masterSeed) : null;
            this.deviceKey = data.deviceKey ? new Uint8Array(data.deviceKey) : null;
            this.envelopeCounter = data.envelopeCounter || 0;
            this.currentRID = data.currentRID;
            this.currentVID = data.currentVID;
            
            // Restore caches
            this.rpKeys = new Map(Object.entries(data.rpKeys || {}));
            this.rpDIDs = new Map(Object.entries(data.rpDIDs || {}));
            this.rpTags = new Map(Object.entries(data.rpTags || {}));
            
            return data;
            
        } catch (error) {
            console.error('❌ Failed to load wallet from storage:', error);
            return null;
        }
    }

    /**
     * Get device records for envelope
     */
    getDeviceRecords() {
        return {
            device_key: this.deviceKey ? Array.from(this.deviceKey) : null,
            device_id: this.getDeviceFingerprint(),
            registered_at: new Date().toISOString()
        };
    }

    /**
     * Get device fingerprint for identification
     */
    getDeviceFingerprint() {
        // Create deterministic device fingerprint
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        ctx.textBaseline = 'top';
        ctx.font = '14px Arial';
        ctx.fillText('Device fingerprint', 2, 2);
        
        const fingerprint = canvas.toDataURL();
        return btoa(fingerprint).substring(0, 32);
    }

    /**
     * Sign up to RP with uniqueness enforcement
     */
    async signupToRP(rpId, userData) {
        try {
            const start = performance.now();
            
            // Generate RP-specific DID
            const rpDID = await this.generateRPDID(rpId);
            
            // Generate pairwise tag for uniqueness
            const pairwiseTag = await this.generatePairwiseTag(rpId);
            
            // Prepare signup data
            const signupData = {
                rp_id: rpId,
                user_did: rpDID,
                pairwise_tag: pairwiseTag,
                user_data: userData,
                wallet_version: 'advanced_v1'
            };
            
            const signupTime = (performance.now() - start) * 1000;
            
            if (this.debug) {
                console.log(`✅ RP signup prepared for ${rpId}: ${signupTime.toFixed(3)}μs`);
                console.log(`🆔 DID: ${rpDID.substring(0, 50)}...`);
                console.log(`🏷️ Tag: ${pairwiseTag.substring(0, 16)}...`);
            }
            
            return {
                success: true,
                signup_data: signupData,
                preparation_time_us: signupTime
            };
            
        } catch (error) {
            console.error('❌ RP signup preparation failed:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Initialize device transfer
     */
    async initializeDeviceTransfer() {
        if (!this.currentVID) {
            throw new Error('No VID available for transfer');
        }
        
        try {
            const response = await fetch(`${this.vaultUrl}/transfer/init`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    device_auth: this.generateDeviceAuth(),
                    vid: this.currentVID
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                
                if (this.debug) {
                    console.log('✅ Device transfer initialized');
                    console.log(`🎫 Transfer token expires in: ${result.expires_in_seconds}s`);
                }
                
                return result;
            } else {
                const error = await response.json();
                throw new Error(error.message || 'Transfer init failed');
            }
            
        } catch (error) {
            console.error('❌ Device transfer init failed:', error);
            throw error;
        }
    }

    /**
     * Generate device authentication signature
     */
    generateDeviceAuth() {
        // Simplified device authentication
        const timestamp = Date.now();
        const deviceId = this.getDeviceFingerprint();
        return `device_${deviceId}_${timestamp}`;
    }

    /**
     * Get wallet statistics
     */
    getWalletStats() {
        return {
            master_seed_available: !!this.masterSeed,
            device_key_available: !!this.deviceKey,
            envelope_counter: this.envelopeCounter,
            cached_rp_keys: this.rpKeys.size,
            cached_rp_dids: this.rpDIDs.size,
            cached_rp_tags: this.rpTags.size,
            current_rid: !!this.currentRID,
            current_vid: !!this.currentVID,
            recovery_enabled: this.enableRecovery
        };
    }

    /**
     * Clear wallet (for testing)
     */
    clearWallet() {
        this.masterSeed = null;
        this.deviceKey = null;
        this.currentRID = null;
        this.currentVID = null;
        this.envelopeCounter = 0;
        
        this.rpKeys.clear();
        this.rpDIDs.clear();
        this.rpTags.clear();
        
        localStorage.removeItem('lemma_advanced_wallet');
        
        if (this.debug) {
            console.log('🧹 Wallet cleared');
        }
    }
}

// Global instance
window.LemmaAdvancedWallet = LemmaAdvancedWallet;
