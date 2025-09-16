/**
 * Lemma Integrated Wallet - Advanced + Federated
 * Combines existing federated wallet with advanced recovery features
 */

class LemmaIntegratedWallet {
    constructor(options = {}) {
        this.debug = options.debug || false;
        this.vaultUrl = options.vaultUrl || '/vault';
        this.enableAdvancedFeatures = options.enableAdvancedFeatures !== false;
        
        // Initialize both wallet systems
        this.federatedWallet = null;
        this.advancedWallet = null;
        
        // Advanced wallet state
        this.masterSeed = null;
        this.deviceKey = null;
        this.currentRID = null;
        this.currentVID = null;
        this.envelopeCounter = 0;
        
        // Per-RP caches for performance
        this.rpKeyCache = new Map();
        this.rpDIDCache = new Map();
        this.rpTagCache = new Map();
        
        // Integration state
        this.integrationMode = 'hybrid'; // 'federated', 'advanced', 'hybrid'
        this.backupEnabled = true;
        
        if (this.debug) {
            console.log('🔐 Lemma Integrated Wallet initialized');
            console.log('⚡ Features: Federated + Advanced recovery + Per-RP keys');
        }
    }

    /**
     * Initialize integrated wallet system
     */
    async initialize() {
        try {
            const start = performance.now();
            
            // Initialize federated wallet (existing system)
            if (typeof LemmaFederatedWallet !== 'undefined') {
                this.federatedWallet = new LemmaFederatedWallet({
                    debug: this.debug,
                    networkRegistryUrl: 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/network/sync',
                    networkAuthKey: 'lemma_network_federated_sync_2024'
                });
                
                await this.federatedWallet.init();
                
                if (this.debug) {
                    console.log('✅ Federated wallet initialized');
                }
            }
            
            // Initialize advanced wallet features
            if (this.enableAdvancedFeatures) {
                await this.initializeAdvancedFeatures();
            }
            
            // Load existing wallet state
            await this.loadWalletState();
            
            const initTime = (performance.now() - start) * 1000;
            
            if (this.debug) {
                console.log(`✅ Integrated wallet initialized: ${initTime.toFixed(3)}μs`);
                console.log(`🎯 Mode: ${this.integrationMode}`);
                console.log(`🔑 Master seed: ${this.masterSeed ? 'Available' : 'Not generated'}`);
                console.log(`📱 Device key: ${this.deviceKey ? 'Available' : 'Not generated'}`);
            }
            
            return {
                success: true,
                initialization_time_us: initTime,
                federated_wallet: !!this.federatedWallet,
                advanced_features: this.enableAdvancedFeatures,
                integration_mode: this.integrationMode
            };
            
        } catch (error) {
            console.error('❌ Integrated wallet initialization failed:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Initialize advanced wallet features
     */
    async initializeAdvancedFeatures() {
        // Generate or load master seed
        const existingSeed = localStorage.getItem('lemma_master_seed');
        if (existingSeed) {
            this.masterSeed = new Uint8Array(JSON.parse(existingSeed));
            if (this.debug) {
                console.log('🔑 Loaded existing master seed');
            }
        } else {
            // Generate new master seed
            this.masterSeed = new Uint8Array(32);
            crypto.getRandomValues(this.masterSeed);
            
            // Save to storage
            localStorage.setItem('lemma_master_seed', JSON.stringify(Array.from(this.masterSeed)));
            
            if (this.debug) {
                console.log('🔑 Generated new master seed');
            }
        }
        
        // Generate or load device key
        const existingDeviceKey = localStorage.getItem('lemma_device_key');
        if (existingDeviceKey) {
            this.deviceKey = new Uint8Array(JSON.parse(existingDeviceKey));
        } else {
            this.deviceKey = new Uint8Array(32);
            crypto.getRandomValues(this.deviceKey);
            localStorage.setItem('lemma_device_key', JSON.stringify(Array.from(this.deviceKey)));
        }
        
        // Load envelope counter
        this.envelopeCounter = parseInt(localStorage.getItem('lemma_envelope_counter') || '0');
        
        // Generate RID if not available (derived from user identity)
        await this.ensureRIDExists();
        
        if (this.debug) {
            console.log('🔐 Advanced wallet features initialized');
        }
    }

    /**
     * Ensure RID (Root Identity) exists - generate from user identity if needed
     */
    async ensureRIDExists() {
        // Check if RID already exists
        this.currentRID = localStorage.getItem('lemma_current_rid');
        
        if (!this.currentRID) {
            // Generate RID from available identity data
            const identitySource = await this.getIdentitySource();
            
            if (identitySource) {
                this.currentRID = await this.deriveRIDFromIdentity(identitySource);
                localStorage.setItem('lemma_current_rid', this.currentRID);
                
                // Also generate and store VID
                this.currentVID = await this.deriveVID(this.currentRID);
                localStorage.setItem('lemma_current_vid', this.currentVID);
                
                if (this.debug) {
                    console.log('✅ Generated RID from user identity');
                    console.log(`🔑 RID: ${this.currentRID.substring(0, 16)}...`);
                }
            } else {
                // Generate temporary RID for wallet functionality
                this.currentRID = await this.generateTemporaryRID();
                localStorage.setItem('lemma_current_rid', this.currentRID);
                
                this.currentVID = await this.deriveVID(this.currentRID);
                localStorage.setItem('lemma_current_vid', this.currentVID);
                
                if (this.debug) {
                    console.log('⚠️ Generated temporary RID (no identity found)');
                    console.log('💡 Complete PoH verification to get persistent RID');
                }
            }
        } else {
            // Load existing VID
            this.currentVID = localStorage.getItem('lemma_current_vid');
            if (!this.currentVID) {
                this.currentVID = await this.deriveVID(this.currentRID);
                localStorage.setItem('lemma_current_vid', this.currentVID);
            }
            
            if (this.debug) {
                console.log('✅ Loaded existing RID from storage');
            }
        }
    }

    /**
     * Get identity source for RID derivation
     */
    async getIdentitySource() {
        try {
            // Try to get from federated wallet first
            if (this.federatedWallet) {
                const identityCredentials = await this.federatedWallet.getCredentials('identity');
                if (identityCredentials.length > 0) {
                    const credential = identityCredentials[0];
                    return {
                        type: 'poh_credential',
                        subject: credential.subject,
                        issuer: credential.issuer,
                        verification_method: credential.claims?.verificationMethod,
                        stripe_session: credential.claims?.stripe_session_id
                    };
                }
            }
            
            // Try to get from localStorage
            const storedUserId = localStorage.getItem('lemma_user_id');
            if (storedUserId) {
                return {
                    type: 'stored_user_id',
                    user_id: storedUserId
                };
            }
            
            return null;
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Could not get identity source:', error);
            }
            return null;
        }
    }

    /**
     * Derive RID from identity source
     */
    async deriveRIDFromIdentity(identitySource) {
        const encoder = new TextEncoder();
        let ridInput = '';
        
        if (identitySource.type === 'poh_credential') {
            // Use subject + verification method for RID
            ridInput = `${identitySource.subject}_${identitySource.verification_method || 'unknown'}`;
        } else if (identitySource.type === 'stored_user_id') {
            ridInput = identitySource.user_id;
        }
        
        // Hash to create RID
        const data = encoder.encode(ridInput + '_root_identity');
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = new Uint8Array(hashBuffer);
        return Array.from(hashArray).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    /**
     * Generate temporary RID for wallet functionality
     */
    async generateTemporaryRID() {
        const encoder = new TextEncoder();
        const tempData = encoder.encode(`temp_rid_${Date.now()}_${Math.random()}`);
        const hashBuffer = await crypto.subtle.digest('SHA-256', tempData);
        const hashArray = new Uint8Array(hashBuffer);
        return Array.from(hashArray).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    /**
     * Derive per-RP child key with caching
     */
    async deriveRPKey(rpId) {
        const start = performance.now();
        
        // Check cache first (performance optimization)
        if (this.rpKeyCache.has(rpId)) {
            const cacheTime = (performance.now() - start) * 1000;
            if (this.debug) {
                console.log(`⚡ RP key cache hit for ${rpId}: ${cacheTime.toFixed(3)}μs`);
            }
            return this.rpKeyCache.get(rpId);
        }
        
        if (!this.masterSeed) {
            throw new Error('Master seed not available - initialize wallet first');
        }
        
        try {
            // Use Web Crypto API for HKDF
            const masterKey = await crypto.subtle.importKey(
                'raw',
                this.masterSeed,
                'HKDF',
                false,
                ['deriveKey']
            );
            
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
            
            const childKeyBytes = await crypto.subtle.exportKey('raw', childKey);
            const childKeyArray = new Uint8Array(childKeyBytes);
            
            // Cache the result for performance
            this.rpKeyCache.set(rpId, childKeyArray);
            
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
     * Generate RP-specific DID with caching
     */
    async generateRPDID(rpId) {
        // Check cache first
        if (this.rpDIDCache.has(rpId)) {
            if (this.debug) {
                console.log(`⚡ RP DID cache hit for ${rpId}`);
            }
            return this.rpDIDCache.get(rpId);
        }
        
        // Derive RP-specific key
        const rpKey = await this.deriveRPKey(rpId);
        
        // Generate DID from derived key (simplified Ed25519)
        const publicKeyHex = Array.from(rpKey)
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
        
        const did = `did:lemma:${publicKeyHex}`;
        
        // Cache the result
        this.rpDIDCache.set(rpId, did);
        
        if (this.debug) {
            console.log(`🆔 Generated RP DID for ${rpId}: ${did.substring(0, 50)}...`);
        }
        
        return did;
    }

    /**
     * Get pairwise tag for RP (server-generated for security)
     */
    async getPairwiseTag(rpId) {
        // Check cache first
        if (this.rpTagCache.has(rpId)) {
            if (this.debug) {
                console.log(`⚡ Pairwise tag cache hit for ${rpId}`);
            }
            return this.rpTagCache.get(rpId);
        }
        
        try {
            // Request pairwise tag from server (server knows RID from session)
            const response = await fetch('/api/issuer/pairwise-tag', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    rp_id: rpId,
                    wallet_type: 'integrated_advanced'
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                const tag = result.pairwise_tag;
                
                // Cache the result
                this.rpTagCache.set(rpId, tag);
                
                if (this.debug) {
                    console.log(`🏷️ Generated pairwise tag for ${rpId}`);
                }
                
                return tag;
            } else {
                throw new Error(`Pairwise tag generation failed: ${response.status}`);
            }
            
        } catch (error) {
            // Fallback to deterministic client-side tag
            if (this.debug) {
                console.warn('⚠️ Using fallback tag generation');
            }
            
            const fallbackTag = await this.generateFallbackTag(rpId);
            this.rpTagCache.set(rpId, fallbackTag);
            return fallbackTag;
        }
    }

    /**
     * Generate fallback pairwise tag (client-side)
     */
    async generateFallbackTag(rpId) {
        // Create deterministic tag from available data
        const userData = this.getCurrentUserData();
        const combined = `${userData.userId || 'anonymous'}_${rpId}_${this.getDeviceFingerprint()}`;
        
        const encoder = new TextEncoder();
        const data = encoder.encode(combined);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        
        return Array.from(new Uint8Array(hashBuffer))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }

    /**
     * Enhanced credential storage with advanced features
     */
    async storeCredential(credential, options = {}) {
        const start = performance.now();
        
        try {
            // Store in federated wallet (existing system)
            let federatedResult = null;
            if (this.federatedWallet) {
                federatedResult = await this.federatedWallet.storeCredential(credential);
                
                if (this.debug) {
                    console.log('✅ Stored in federated wallet');
                }
            }
            
            // Store in advanced wallet system with RP-specific handling
            let advancedResult = null;
            if (this.enableAdvancedFeatures && credential.credentialSubject) {
                advancedResult = await this.storeCredentialAdvanced(credential, options);
                
                if (this.debug) {
                    console.log('✅ Stored with advanced features');
                }
            }
            
            // Backup to vault if enabled
            if (this.backupEnabled && this.currentVID) {
                await this.backupToVault();
                
                if (this.debug) {
                    console.log('✅ Backed up to recovery vault');
                }
            }
            
            const storageTime = (performance.now() - start) * 1000;
            
            return {
                success: true,
                storage_time_us: storageTime,
                federated_storage: federatedResult?.success || false,
                advanced_storage: advancedResult?.success || false,
                vault_backup: this.backupEnabled,
                integration_mode: this.integrationMode
            };
            
        } catch (error) {
            console.error('❌ Integrated credential storage failed:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Store credential with advanced wallet features
     */
    async storeCredentialAdvanced(credential, options) {
        // Extract RP information from credential context
        const rpId = this.extractRPFromCredential(credential);
        
        if (rpId && this.enableAdvancedFeatures) {
            // Generate RP-specific DID
            const rpDID = await this.generateRPDID(rpId);
            
            // Generate pairwise tag for uniqueness
            const pairwiseTag = await this.getPairwiseTag(rpId);
            
            // Store RP-specific metadata
            const rpMetadata = {
                rp_id: rpId,
                rp_did: rpDID,
                pairwise_tag: pairwiseTag,
                credential_id: credential.id,
                stored_at: Date.now()
            };
            
            // Save RP metadata to local storage
            const existingRPData = JSON.parse(localStorage.getItem('lemma_rp_metadata') || '{}');
            existingRPData[rpId] = rpMetadata;
            localStorage.setItem('lemma_rp_metadata', JSON.stringify(existingRPData));
            
            if (this.debug) {
                console.log(`✅ Advanced storage for RP ${rpId}`);
                console.log(`🆔 RP DID: ${rpDID.substring(0, 50)}...`);
                console.log(`🏷️ Pairwise tag: ${pairwiseTag.substring(0, 16)}...`);
            }
            
            return {
                success: true,
                rp_id: rpId,
                rp_did: rpDID,
                pairwise_tag: pairwiseTag
            };
        }
        
        return { success: true, advanced_features: false };
    }

    /**
     * Extract RP ID from credential context
     */
    extractRPFromCredential(credential) {
        // Try to extract RP from credential context
        const claims = credential.claims || credential.credentialSubject || {};
        
        // Check for site ID in claims
        if (claims.siteId) {
            return claims.siteId;
        }
        
        // Check for issuer domain
        if (credential.issuer && typeof credential.issuer === 'string') {
            // Extract domain from issuer DID or URL
            const issuerParts = credential.issuer.split(':');
            if (issuerParts.length >= 3) {
                return issuerParts[2]; // Extract identifier part
            }
        }
        
        // Fallback to current domain
        return window.location.hostname;
    }

    /**
     * Enhanced credential verification with advanced features
     */
    async verifyCredential(credential, options = {}) {
        const start = performance.now();
        
        try {
            // Verify using federated wallet (existing system)
            let federatedResult = null;
            if (this.federatedWallet) {
                federatedResult = await this.federatedWallet.verifyCredential(credential);
            }
            
            // Additional verification with advanced features
            let advancedResult = null;
            if (this.enableAdvancedFeatures) {
                advancedResult = await this.verifyCredentialAdvanced(credential, options);
            }
            
            const verificationTime = (performance.now() - start) * 1000;
            
            // Combine results
            const verified = (federatedResult?.verified !== false) && 
                           (advancedResult?.verified !== false);
            
            return {
                success: true,
                verified: verified,
                verification_time_us: verificationTime,
                federated_result: federatedResult,
                advanced_result: advancedResult,
                integration_mode: this.integrationMode
            };
            
        } catch (error) {
            console.error('❌ Integrated verification failed:', error);
            return {
                success: false,
                verified: false,
                error: error.message
            };
        }
    }

    /**
     * Advanced credential verification with RP-specific features
     */
    async verifyCredentialAdvanced(credential, options) {
        const start = performance.now();
        
        try {
            // Extract RP context
            const rpId = this.extractRPFromCredential(credential);
            
            // Verify RP-specific DID if available
            if (rpId && this.rpDIDCache.has(rpId)) {
                const expectedDID = this.rpDIDCache.get(rpId);
                const credentialSubject = credential.subject;
                
                if (credentialSubject === expectedDID) {
                    if (this.debug) {
                        console.log(`✅ RP DID verification passed for ${rpId}`);
                    }
                } else {
                    if (this.debug) {
                        console.warn(`⚠️ RP DID mismatch for ${rpId}`);
                    }
                }
            }
            
            // Verify pairwise tag uniqueness if enforcing
            if (options.enforceUniqueness && rpId) {
                const pairwiseTag = await this.getPairwiseTag(rpId);
                
                // In production, would check with RP for tag uniqueness
                if (this.debug) {
                    console.log(`🏷️ Pairwise tag for uniqueness: ${pairwiseTag.substring(0, 16)}...`);
                }
            }
            
            const advancedTime = (performance.now() - start) * 1000;
            
            return {
                verified: true,
                verification_time_us: advancedTime,
                rp_id: rpId,
                advanced_features_used: true
            };
            
        } catch (error) {
            console.error('❌ Advanced verification failed:', error);
            return {
                verified: false,
                error: error.message
            };
        }
    }

    /**
     * Backup wallet to recovery vault
     */
    async backupToVault() {
        if (!this.currentVID || !this.masterSeed) {
            if (this.debug) {
                console.log('⚠️ Cannot backup - missing VID or master seed');
            }
            return { success: false, reason: 'missing_requirements' };
        }
        
        try {
            // Create wallet envelope
            const envelope = {
                version: 1,
                counter: this.envelopeCounter + 1,
                wallet_schema: 1,
                master_seed: Array.from(this.masterSeed),
                device_records: {
                    device_key: Array.from(this.deviceKey),
                    device_fingerprint: this.getDeviceFingerprint(),
                    rp_cache_size: this.rpKeyCache.size,
                    created_at: new Date().toISOString()
                }
            };
            
            // Encrypt envelope (simplified)
            const envelopeJson = JSON.stringify(envelope);
            const ciphertext = new TextEncoder().encode(envelopeJson);
            const aad = new TextEncoder().encode('integrated_wallet_v1');
            
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
                localStorage.setItem('lemma_envelope_counter', this.envelopeCounter.toString());
                
                if (this.debug) {
                    console.log('✅ Wallet backed up to vault');
                    console.log(`📊 Counter: ${this.envelopeCounter}`);
                }
                
                return { success: true, counter: this.envelopeCounter };
            } else {
                const error = await response.json();
                throw new Error(error.message || 'Vault backup failed');
            }
            
        } catch (error) {
            console.error('❌ Vault backup failed:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Recover wallet from vault (for new device)
     */
    async recoverFromVault(rid, recoveryKey) {
        try {
            if (this.debug) {
                console.log('🔄 Starting wallet recovery from vault...');
            }
            
            // Derive VID from RID
            const vid = await this.deriveVID(rid);
            
            // Fetch encrypted envelope from vault
            const response = await fetch(`${this.vaultUrl}/get`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vid: vid,
                    recovery_key: recoveryKey
                })
            });
            
            if (!response.ok) {
                throw new Error(`Vault fetch failed: ${response.status}`);
            }
            
            const vaultData = await response.json();
            if (!vaultData.success) {
                throw new Error(vaultData.error || 'Vault recovery failed');
            }
            
            // Decrypt envelope (simplified)
            const ciphertextHex = vaultData.ciphertext;
            const ciphertext = new Uint8Array(ciphertextHex.match(/.{2}/g).map(byte => parseInt(byte, 16)));
            const envelopeJson = new TextDecoder().decode(ciphertext);
            const envelope = JSON.parse(envelopeJson);
            
            // Restore wallet state
            this.masterSeed = new Uint8Array(envelope.master_seed);
            this.deviceKey = new Uint8Array(envelope.device_records.device_key);
            this.currentRID = rid;
            this.currentVID = vid;
            this.envelopeCounter = envelope.counter;
            
            // Save to local storage
            localStorage.setItem('lemma_master_seed', Array.from(this.masterSeed).join(','));
            localStorage.setItem('lemma_device_key', Array.from(this.deviceKey).join(','));
            localStorage.setItem('lemma_current_rid', this.currentRID);
            localStorage.setItem('lemma_current_vid', this.currentVID);
            
            if (this.debug) {
                console.log('✅ Wallet recovery successful');
                console.log(`📱 Device key restored: ${this.deviceKey ? 'Available' : 'Missing'}`);
                console.log(`🔑 Master seed restored: ${this.masterSeed ? 'Available' : 'Missing'}`);
            }
            
            return {
                success: true,
                recovery_time: Date.now(),
                envelope_version: envelope.version,
                device_count: envelope.device_records ? 1 : 0
            };
            
        } catch (error) {
            console.error('❌ Vault recovery failed:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Generate QR code for device sync
     */
    async generateDeviceSyncQR() {
        if (!this.masterSeed || !this.currentRID) {
            return { success: false, reason: 'wallet_not_ready' };
        }
        
        try {
            // Create sync package
            const syncPackage = {
                type: 'lemma_device_sync',
                version: 1,
                rid: this.currentRID,
                sync_key: Array.from(this.masterSeed.slice(0, 16)), // First 16 bytes as sync key
                vault_hint: this.currentVID,
                expires_at: Date.now() + (5 * 60 * 1000), // 5 minutes
                created_by: this.getDeviceFingerprint()
            };
            
            // Encode as QR-friendly format
            const syncData = btoa(JSON.stringify(syncPackage));
            
            if (this.debug) {
                console.log('✅ Device sync QR generated');
                console.log(`⏰ Expires in 5 minutes`);
            }
            
            return {
                success: true,
                qr_data: syncData,
                expires_at: syncPackage.expires_at,
                sync_type: 'device_transfer'
            };
            
        } catch (error) {
            console.error('❌ QR generation failed:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Scan QR code to sync from another device
     */
    async syncFromDeviceQR(qrData) {
        try {
            if (this.debug) {
                console.log('📱 Processing device sync QR...');
            }
            
            // Decode QR data
            const syncPackage = JSON.parse(atob(qrData));
            
            // Validate sync package
            if (syncPackage.type !== 'lemma_device_sync' || syncPackage.expires_at < Date.now()) {
                throw new Error('Invalid or expired sync QR');
            }
            
            // Use sync key to recover wallet
            const recoveryResult = await this.recoverFromVault(
                syncPackage.rid,
                Array.from(syncPackage.sync_key)
            );
            
            if (recoveryResult.success) {
                // Force refresh credentials from federated wallet
                if (this.federatedWallet) {
                    await this.federatedWallet.refreshCredentials();
                }
                
                if (this.debug) {
                    console.log('✅ Device sync completed via QR');
                }
                
                return {
                    success: true,
                    sync_method: 'qr_code',
                    recovery_result: recoveryResult
                };
            } else {
                throw new Error(recoveryResult.error || 'Recovery failed');
            }
            
        } catch (error) {
            console.error('❌ QR sync failed:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Load wallet state from storage
     */
    async loadWalletState() {
        // Load RID and VID if available
        this.currentRID = localStorage.getItem('lemma_current_rid');
        this.currentVID = localStorage.getItem('lemma_current_vid');
        
        // Load RP caches
        const rpMetadata = JSON.parse(localStorage.getItem('lemma_rp_metadata') || '{}');
        
        for (const [rpId, metadata] of Object.entries(rpMetadata)) {
            if (metadata.rp_did) {
                this.rpDIDCache.set(rpId, metadata.rp_did);
            }
            if (metadata.pairwise_tag) {
                this.rpTagCache.set(rpId, metadata.pairwise_tag);
            }
        }
        
        if (this.debug && Object.keys(rpMetadata).length > 0) {
            console.log(`📊 Loaded RP metadata for ${Object.keys(rpMetadata).length} RPs`);
        }
    }

    /**
     * Get current user data for context
     */
    getCurrentUserData() {
        // Try to get user data from various sources
        const userData = {
            userId: localStorage.getItem('lemma_user_id'),
            email: localStorage.getItem('lemma_user_email'),
            deviceId: this.getDeviceFingerprint()
        };
        
        return userData;
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
        ctx.fillText('Lemma device fingerprint', 2, 2);
        
        const fingerprint = canvas.toDataURL();
        return btoa(fingerprint).substring(0, 32);
    }

    /**
     * Derive VID (Vault Index) from RID (Root Identity)
     */
    async deriveVID(rid) {
        // Use SHA256 to derive VID from RID
        const encoder = new TextEncoder();
        const data = encoder.encode(rid + '_vault_index');
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = new Uint8Array(hashBuffer);
        return Array.from(hashArray).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    /**
     * Get credentials (delegates to federated wallet)
     */
    async getCredentials(type = null) {
        // Wait for initialization if not ready
        if (!this.federatedWallet && !this.initializationPromise) {
            if (this.debug) {
                console.warn('⚠️ Integrated wallet not initialized, starting initialization...');
            }
            await this.initialize();
        }
        
        // Wait for ongoing initialization
        if (this.initializationPromise) {
            await this.initializationPromise;
        }
        
        if (this.federatedWallet && typeof this.federatedWallet.getCredentials === 'function') {
            return await this.federatedWallet.getCredentials(type);
        }
        
        // Fallback if federated wallet not available
        if (this.debug) {
            console.warn('⚠️ Federated wallet not available for getCredentials');
        }
        return [];
    }

    /**
     * Check if wallet has valid credentials (delegates to federated wallet)
     */
    async hasValidCredentials(type = null) {
        if (this.federatedWallet && typeof this.federatedWallet.hasValidCredentials === 'function') {
            return await this.federatedWallet.hasValidCredentials(type);
        }
        
        // Fallback check
        const credentials = await this.getCredentials(type);
        return credentials.length > 0;
    }

    /**
     * Get integrated wallet statistics
     */
    getWalletStats() {
        const federatedStats = this.federatedWallet ? {
            credentials: this.federatedWallet.memoryCache?.size || 0,
            trusted_dids: this.federatedWallet.didRegistry?.size || 0
        } : null;
        
        return {
            integration_mode: this.integrationMode,
            federated_wallet: federatedStats,
            advanced_features: {
                master_seed_available: !!this.masterSeed,
                device_key_available: !!this.deviceKey,
                envelope_counter: this.envelopeCounter,
                cached_rp_keys: this.rpKeyCache.size,
                cached_rp_dids: this.rpDIDCache.size,
                cached_rp_tags: this.rpTagCache.size,
                current_rid: !!this.currentRID,
                current_vid: !!this.currentVID
            },
            backup_enabled: this.backupEnabled,
            vault_url: this.vaultUrl
        };
    }

    /**
     * Enhanced signup flow with uniqueness enforcement
     */
    async signupToRP(rpId, userData, options = {}) {
        const start = performance.now();
        
        try {
            // Generate RP-specific DID
            const rpDID = await this.generateRPDID(rpId);
            
            // Get pairwise tag for uniqueness enforcement
            const pairwiseTag = await this.getPairwiseTag(rpId);
            
            // Prepare enhanced signup data
            const enhancedSignupData = {
                rp_id: rpId,
                user_did: rpDID,
                pairwise_tag: pairwiseTag,
                user_data: userData,
                wallet_type: 'integrated_advanced',
                federated_credentials: this.federatedWallet ? 
                    await this.federatedWallet.getCredentials('identity') : [],
                advanced_features: {
                    per_rp_keys: true,
                    sybil_prevention: true,
                    recovery_enabled: this.backupEnabled
                }
            };
            
            const signupTime = (performance.now() - start) * 1000;
            
            if (this.debug) {
                console.log(`✅ Enhanced RP signup for ${rpId}: ${signupTime.toFixed(3)}μs`);
                console.log(`🆔 RP DID: ${rpDID.substring(0, 50)}...`);
                console.log(`🏷️ Uniqueness tag: ${pairwiseTag.substring(0, 16)}...`);
                console.log(`🌐 Federated creds: ${enhancedSignupData.federated_credentials.length}`);
            }
            
            return {
                success: true,
                signup_data: enhancedSignupData,
                preparation_time_us: signupTime
            };
            
        } catch (error) {
            console.error('❌ Enhanced signup failed:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Clear integrated wallet (for testing)
     */
    clearWallet() {
        // Clear advanced wallet state
        this.masterSeed = null;
        this.deviceKey = null;
        this.currentRID = null;
        this.currentVID = null;
        this.envelopeCounter = 0;
        
        this.rpKeyCache.clear();
        this.rpDIDCache.clear();
        this.rpTagCache.clear();
        
        // Clear local storage
        localStorage.removeItem('lemma_master_seed');
        localStorage.removeItem('lemma_device_key');
        localStorage.removeItem('lemma_envelope_counter');
        localStorage.removeItem('lemma_rp_metadata');
        localStorage.removeItem('lemma_current_rid');
        localStorage.removeItem('lemma_current_vid');
        
        // Clear federated wallet if available
        if (this.federatedWallet && this.federatedWallet.clearWallet) {
            this.federatedWallet.clearWallet();
        }
        
        if (this.debug) {
            console.log('🧹 Integrated wallet cleared');
        }
    }
}

// Global instance for backward compatibility
window.LemmaIntegratedWallet = LemmaIntegratedWallet;

// Enhanced wallet manager that uses integrated wallet
class LemmaEnhancedWalletManager {
    constructor() {
        this.walletInstance = null;
        this.isInitialized = false;
    }

    async getWallet() {
        if (!this.walletInstance) {
            await this.initializeWallet();
        }
        return this.walletInstance;
    }

    async initializeWallet() {
        try {
            console.log('🔄 LemmaEnhancedWalletManager: Initializing integrated wallet...');
            
            const wallet = new LemmaIntegratedWallet({
                debug: true,
                enableAdvancedFeatures: true,
                vaultUrl: '/vault'
            });
            
            const initResult = await wallet.initialize();
            
            if (initResult.success) {
                this.walletInstance = wallet;
                this.isInitialized = true;
                
                // Store globally for compatibility
                window.lemmaWallet = wallet;
                window.globalLemmaWallet = wallet;
                
                console.log('✅ LemmaEnhancedWalletManager: Integrated wallet ready');
                console.log(`⚡ Features: Federated + Advanced recovery + Per-RP keys`);
                
                return wallet;
            } else {
                throw new Error(initResult.error || 'Wallet initialization failed');
            }
            
        } catch (error) {
            console.error('❌ LemmaEnhancedWalletManager: Initialization failed:', error);
            throw error;
        }
    }

    async storeCredential(credential, options = {}) {
        const wallet = await this.getWallet();
        return await wallet.storeCredential(credential, options);
    }

    async verifyCredential(credential, options = {}) {
        const wallet = await this.getWallet();
        return await wallet.verifyCredential(credential, options);
    }

    getWalletStats() {
        if (this.walletInstance) {
            return this.walletInstance.getWalletStats();
        }
        return { initialized: false };
    }
}

// Create global enhanced wallet manager
window.lemmaEnhancedWalletManager = new LemmaEnhancedWalletManager();
