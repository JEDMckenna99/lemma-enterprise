/**
 * Lemma Federated Wallet - Rock-Solid Cross-Tab Credential Persistence
 * ==================================================================
 * 
 * Solves the core issue: Verify once, access everywhere across all tabs.
 * Focus: PERSISTENCE and RELIABILITY over complexity.
 */

class LemmaFederatedWallet {
    constructor(options = {}) {
        this.debug = options.debug || false;
        this.storageKey = 'lemma_credentials';
        this.sessionKey = 'lemma_session_active';
        this.dbName = 'lemma_wallet_db';
        this.dbVersion = 1;
        this.isReady = false;
        
        // Storage layers (redundant for reliability)
        this.db = null;
        this.memoryCache = new Map();
        
        // Network registry configuration
        this.networkConfig = {
            registryUrl: options.networkRegistryUrl || '',
            authKey: options.networkAuthKey || 'lemma_network_master_key_2024',
            syncInterval: options.syncInterval || (5 * 60 * 1000), // 5 minutes
            lastDidSync: 0,
            lastRevocationSync: 0
        };
        
        // Background security check configuration
        this.securityConfig = {
            enabled: options.backgroundChecks !== false, // Default enabled
            securityLevel: options.securityLevel || 'medium', // 'low', 'medium', 'high', 'critical'
            checkInterval: this.getCheckIntervalForLevel(options.securityLevel || 'medium'),
            customInterval: options.customCheckInterval || null,
            checkOnEvents: options.checkOnEvents || ['entry', 'checkout', 'sensitive_action'],
            maxConsecutiveFailures: options.maxFailures || 3,
            gracePeriod: options.gracePeriod || (24 * 60 * 60 * 1000), // 24 hours
            lastBackgroundCheck: 0,
            consecutiveFailures: 0,
            activeIntervalId: null
        };
        
        // Network registry cache
        this.didRegistry = new Map();
        this.revocationBloomFilter = new Set();
        
        // Initialize with trusted DIDs (bootstrap for existing system)
        this.initializeTrustedDIDs();
        
        if (this.debug) {
            console.log('🎯 Lemma Federated Wallet starting with network sync...');
            console.log(`🛡️ Security level: ${this.securityConfig.securityLevel}, check interval: ${this.securityConfig.checkInterval / 1000}s`);
        }
    }
    
    /**
     * Get background check interval for security level
     */
    getCheckIntervalForLevel(level) {
        const intervals = {
            'low': 30 * 60 * 1000,        // 30 minutes - Basic sites
            'medium': 5 * 60 * 1000,      // 5 minutes - E-commerce  
            'high': 2 * 60 * 1000,        // 2 minutes - Financial services
            'critical': 60 * 1000,        // 1 minute - Banks, high-security
            'realtime': 10 * 1000         // 10 seconds - Ultra-high security
        };
        return intervals[level] || intervals['medium'];
    }
    
    /**
     * Initialize trusted DIDs for bootstrap (fixes existing credential validation)
     */
    initializeTrustedDIDs() {
        // Bootstrap with known trusted issuers
        const trustedIssuers = [
            {
                did: 'did:lemma:identity_network',
                publicKey: 'lemma_identity_network_key_2024',
                issuerInfo: {
                    name: 'Lemma Identity Network',
                    issuer_type: 'identity_kyc_provider',
                    trust_score: 0.95,
                    verified: true,
                    created_at: Date.now(),
                    capabilities: ['stripe_identity_verification', 'kyc_verification']
                }
            },
            {
                did: 'did:lemma:stripe_identity',
                publicKey: 'lemma_stripe_integration_key_2024', 
                issuerInfo: {
                    name: 'Lemma Stripe Identity Integration',
                    issuer_type: 'third_party_kyc',
                    trust_score: 0.90,
                    verified: true,
                    created_at: Date.now(),
                    capabilities: ['stripe_identity_verification']
                }
            },

        ];
        
        // Add to DID registry
        trustedIssuers.forEach(issuer => {
            this.didRegistry.set(issuer.did, issuer);
        });
        
        if (this.debug) {
            console.log(`🔐 Initialized ${trustedIssuers.length} trusted DIDs:`, trustedIssuers.map(i => i.did));
        }
    }
    
    /**
     * Initialize wallet - MUST be called before use
     */
    async init() {
        if (this.isReady) return;
        
        try {
            // 1. Initialize IndexedDB
            await this.initDB();
            
            // 2. Load existing credentials
            await this.loadExistingCredentials();
            
            // 3. Start network sync
            this.startNetworkSync();
            
            // 4. Start background security checks
            this.startBackgroundChecks();
            
            // 5. Mark as ready
            this.isReady = true;
            
            if (this.debug) {
                console.log(`✅ Federated wallet ready - ${this.memoryCache.size} credentials loaded`);
                this.logStorageStatus();
            }
            
        } catch (error) {
            console.error('❌ Wallet init failed:', error);
            // Fallback to localStorage only
            this.isReady = true;
        }
    }
    
    /**
     * Initialize IndexedDB
     */
    async initDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = () => {
                console.warn('IndexedDB failed, falling back to localStorage');
                resolve(); // Don't reject - we can work with localStorage
            };
            
            request.onsuccess = (event) => {
                this.db = event.target.result;
                if (this.debug) console.log('📊 IndexedDB ready');
                resolve();
            };
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains('credentials')) {
                    const store = db.createObjectStore('credentials', { keyPath: 'id' });
                    store.createIndex('packageType', 'packageType', { unique: false });
                    store.createIndex('storedAt', 'storedAt', { unique: false });
                }
            };
        });
    }
    
    /**
     * Load existing credentials from all storage layers
     */
    async loadExistingCredentials() {
        // 1. Try IndexedDB first
        if (this.db) {
            try {
                const transaction = this.db.transaction(['credentials'], 'readonly');
                const store = transaction.objectStore('credentials');
                const request = store.getAll();
                
                await new Promise((resolve, reject) => {
                    request.onsuccess = () => {
                        const credentials = request.result || [];
                        credentials.forEach(cred => {
                            this.memoryCache.set(cred.id, cred);
                        });
                        if (this.debug) console.log(`📊 Loaded ${credentials.length} from IndexedDB`);
                        resolve();
                    };
                    request.onerror = () => resolve(); // Don't fail
                });
            } catch (error) {
                if (this.debug) console.warn('IndexedDB load failed:', error);
            }
        }
        
        // 2. Fallback to localStorage
        try {
            const stored = localStorage.getItem(this.storageKey);
            if (stored) {
                const credentials = JSON.parse(stored);
                if (Array.isArray(credentials)) {
                    credentials.forEach(cred => {
                        if (!this.memoryCache.has(cred.id)) {
                            this.memoryCache.set(cred.id, cred);
                        }
                    });
                    if (this.debug) console.log(`📊 Loaded ${credentials.length} from localStorage`);
                }
            }
        } catch (error) {
            if (this.debug) console.warn('localStorage load failed:', error);
        }
    }
    
    /**
     * Store a credential with maximum redundancy
     */
    async storeCredential(credential) {
        await this.init(); // Ensure initialized
        
        const credentialWithMeta = {
            ...credential,
            storedAt: Date.now(),
            lastVerified: Date.now(),
            networkShared: true,
            version: 1
        };
        
        const results = {
            memory: false,
            indexedDB: false,
            localStorage: false
        };
        
        try {
            // 1. Store in memory (immediate access)
            this.memoryCache.set(credentialWithMeta.id, credentialWithMeta);
            results.memory = true;
            
            // 2. Store in IndexedDB (persistent across sessions)
            if (this.db) {
                try {
                    const transaction = this.db.transaction(['credentials'], 'readwrite');
                    const store = transaction.objectStore('credentials');
                    await new Promise((resolve, reject) => {
                        const request = store.put(credentialWithMeta);
                        request.onsuccess = () => {
                            results.indexedDB = true;
                            resolve();
                        };
                        request.onerror = () => resolve(); // Don't fail
                    });
                } catch (error) {
                    if (this.debug) console.warn('IndexedDB store failed:', error);
                }
            }
            
            // 3. Store in localStorage (backup)
            try {
                const allCredentials = Array.from(this.memoryCache.values());
                localStorage.setItem(this.storageKey, JSON.stringify(allCredentials));
                results.localStorage = true;
            } catch (error) {
                if (this.debug) console.warn('localStorage store failed:', error);
            }
            
            // 4. Set session marker
            sessionStorage.setItem(this.sessionKey, 'true');
            
            // 5. CRITICAL: Share to federated network for cross-site recognition
            let networkShared = false;
            if (this.networkConfig.registryUrl && credentialWithMeta.packageType === 'identity') {
                try {
                    const networkResponse = await fetch(`${this.networkConfig.registryUrl}/add-identity-lemma`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Network ${this.networkConfig.authKey}`
                        },
                        body: JSON.stringify({
                            type: 'identity_lemma',
                            timestamp: Date.now(),
                            data: {
                                lemma_id: credentialWithMeta.id,
                                lemma_data: credentialWithMeta,
                                user_id: credentialWithMeta.subject?.id?.replace('did:lemma:federated:user:', '') || 
                                         credentialWithMeta.id.replace('cred_fed_', ''),
                                network_scope: 'federated',
                                cross_site_valid: true
                            }
                        })
                    });
                    
                    if (networkResponse.ok) {
                        networkShared = true;
                        if (this.debug) {
                            console.log('🌐 Identity lemma shared to federated network for cross-site recognition');
                        }
                    } else {
                        if (this.debug) {
                            console.warn('⚠️ Failed to share to network:', networkResponse.status);
                        }
                    }
                } catch (error) {
                    if (this.debug) {
                        console.warn('⚠️ Network sharing failed:', error.message);
                    }
                }
            }
            
            if (this.debug) {
                console.log('✅ Credential stored:', {
                    id: credentialWithMeta.id,
                    packageType: credentialWithMeta.packageType,
                    storageResults: results
                });
            }
            
            return { 
                success: true, 
                results,
                credentialId: credentialWithMeta.id,
                networkShared: networkShared,
                layers: Object.keys(results).filter(k => results[k])
            };
            
        } catch (error) {
            console.error('❌ Store credential failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Check if we have valid credentials for a package type
     */
    async hasValidCredentials(packageType = 'identity') {
        await this.init(); // Ensure initialized
        
        const credentials = this.getCredentialsSync(packageType);
        const hasCredentials = credentials.length > 0;
        
        if (this.debug) {
            console.log(`🔍 hasValidCredentials(${packageType}): ${hasCredentials ? 'YES' : 'NO'}`);
            if (hasCredentials) {
                console.log('📋 Found credentials:', credentials.map(c => ({
                    id: c.id,
                    packageType: c.packageType,
                    storedAt: new Date(c.storedAt).toLocaleString()
                })));
            }
        }
        
        // If no local credentials, check shared network for cross-site recognition
        if (!hasCredentials && this.networkConfig.registryUrl && packageType === 'identity') {
            try {
                const networkResponse = await fetch(`${this.networkConfig.registryUrl}/check-shared-identity`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Network ${this.networkConfig.authKey}`
                    },
                    body: JSON.stringify({
                        user_id: this.getCurrentUserId(),
                        check_cross_site: true
                    })
                });
                
                if (networkResponse.ok) {
                    const networkResult = await networkResponse.json();
                    if (networkResult.success && networkResult.has_valid_identity) {
                        if (this.debug) {
                            console.log('🌐 Found valid identity lemma in federated network');
                        }
                        return true;
                    }
                }
            } catch (error) {
                if (this.debug) {
                    console.warn('⚠️ Network identity check failed:', error.message);
                }
            }
        }
        
        return hasCredentials;
    }
    
    /**
     * Get current user ID for network checks
     */
    getCurrentUserId() {
        // Try to get from stored credentials
        for (const credential of this.memoryCache.values()) {
            if (credential.subject?.id) {
                return credential.subject.id.replace('did:lemma:federated:user:', '');
            }
        }
        
        // Fallback to session-based ID
        return sessionStorage.getItem('lemma_user_id') || 
               localStorage.getItem('lemma_user_id') ||
               'anonymous_' + Date.now();
    }
    
    /**
     * Get credentials synchronously from memory cache
     */
    getCredentialsSync(packageType = 'identity') {
        const credentials = Array.from(this.memoryCache.values())
            .filter(cred => cred.packageType === packageType)
            .filter(cred => {
                // Check if expired (30 days default)
                const maxAge = 30 * 24 * 60 * 60 * 1000; // 30 days
                const age = Date.now() - cred.storedAt;
                return age < maxAge;
            });
            
        return credentials;
    }
    
    /**
     * Get credentials (async for API compatibility)
     */
    async getCredentials(packageType = 'identity') {
        await this.init();
        return this.getCredentialsSync(packageType);
    }
    
    /**
     * Verify a credential using the REAL Lemma Crypto Engine (Backend)
     * 🔐 Ed25519 Signatures → Cryptographic authenticity verification
     * 🔒 OPRF → Privacy-preserving evaluation  
     * 🌸 Bloom Filters → Efficient revocation checking
     * ⚡ ZKP → Zero-knowledge proofs with selective disclosure
     */
    async verifyCredential(credential) {
        const startTime = performance.now();
        
        try {
            if (this.debug) {
                console.log(`🔐 Verifying credential ${credential.id} using REAL Lemma Crypto Engine (Ed25519 + OPRF + Bloom + ZKP)...`);
            }
            
            // Step 1: Check network revocation status first (fast local check)
            const isRevoked = await this.isCredentialRevoked(credential);
            if (isRevoked) {
                const verificationTime = (performance.now() - startTime) * 1000;
                
                if (this.debug) {
                    console.log(`🚫 Credential ${credential.id} is REVOKED - blocked by network revocation list`);
                }
                
                return {
                    success: false,
                    verified: false,
                    confidence: 0.0,
                    verification_time_us: 0,
                    client_time_us: verificationTime,
                    offline: true, // Using local revocation cache
                    engine: 'network_revocation_check',
                    revoked: true,
                    reason: 'credential_revoked_in_network'
                };
            }
            
            // Step 2: Validate issuer DID (if configured)
            if (credential.issuer) {
                const issuerValidation = await this.validateIssuerDid(credential.issuer);
                if (!issuerValidation.valid) {
                    const verificationTime = (performance.now() - startTime) * 1000;
                    
                    if (this.debug) {
                        console.log(`⚠️ Credential ${credential.id} has invalid issuer: ${credential.issuer}`);
                    }
                    
                    return {
                        success: false,
                        verified: false,
                        confidence: 0.0,
                        verification_time_us: 0,
                        client_time_us: verificationTime,
                        offline: true,
                        engine: 'network_did_validation',
                        reason: issuerValidation.reason
                    };
                }
                
                if (this.debug) {
                    console.log(`✅ Issuer DID validated: ${credential.issuer} (trust: ${issuerValidation.trustScore})`);
                }
            }
            
            // Step 3: Call the REAL Rust crypto engine via backend API
            const response = await fetch('/api/sdk/check-credentials', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer demo-integration-key-12345'
                },
                body: JSON.stringify({
                    credentials: [credential],
                    enableRustEngine: true,
                    requireFullCrypto: true // Force full cryptographic verification
                })
            });
            
            if (!response.ok) {
                throw new Error(`Rust Engine API failed: ${response.status}`);
            }
            
            const result = await response.json();
            const verificationTime = (performance.now() - startTime) * 1000; // Convert to microseconds
            
            if (this.debug) {
                const ageHours = Math.round((Date.now() - (credential.storedAt || 0)) / (1000 * 60 * 60));
                console.log(`✅ REAL CRYPTO ENGINE verification complete: ${result.verified ? 'VALID' : 'INVALID'} (${verificationTime.toFixed(2)}µs client + ${(result.verification_time_us || 0).toFixed(2)}µs engine)`, {
                    engineVerified: result.verified,
                    engineConfidence: result.confidence,
                    engineTimeUs: result.verification_time_us,
                    cryptoComponents: ['Ed25519', 'OPRF', 'Bloom', 'ZKP'],
                    credentialId: credential.id,
                    age: `${ageHours}h`
                });
            }
            
            return {
                success: true,
                verified: result.verified || false,
                confidence: result.confidence || 0.0,
                verification_time_us: result.verification_time_us || 0,
                client_time_us: verificationTime,
                offline: false, // This uses the real engine (not fake offline)
                engine: 'rust_crypto_engine',
                cryptoComponents: ['Ed25519', 'OPRF', 'Bloom', 'ZKP'],
                details: result.details || {}
            };
            
        } catch (error) {
            const verificationTime = (performance.now() - startTime) * 1000;
            
            if (this.debug) {
                console.error(`❌ REAL CRYPTO ENGINE verification failed for ${credential.id}:`, error.message);
            }
            
            // SECURITY: No fallback to fake validation - if crypto engine fails, credential is invalid
            return {
                success: false,
                verified: false,
                confidence: 0.0,
                verification_time_us: 0,
                client_time_us: verificationTime,
                offline: false,
                engine: 'rust_crypto_engine_failed',
                error: error.message,
                security_note: 'No fallback - crypto engine verification required'
            };
        }
    }
    
    /**
     * Clear all credentials (for testing/debugging)
     */
    async clearAll() {
        this.memoryCache.clear();
        
        if (this.db) {
            try {
                const transaction = this.db.transaction(['credentials'], 'readwrite');
                const store = transaction.objectStore('credentials');
                store.clear();
            } catch (error) {
                console.warn('IndexedDB clear failed:', error);
            }
        }
        
        try {
            localStorage.removeItem(this.storageKey);
            sessionStorage.removeItem(this.sessionKey);
        } catch (error) {
            console.warn('Storage clear failed:', error);
        }
        
        if (this.debug) {
            console.log('🗑️ All credentials cleared');
        }
    }
    
    /**
     * Debug: Log storage status
     */
    logStorageStatus() {
        if (!this.debug) return;
        
        console.log('📊 Storage Status:', {
            memoryCredentials: this.memoryCache.size,
            indexedDBAvailable: !!this.db,
            localStorageAvailable: typeof localStorage !== 'undefined',
            sessionActive: sessionStorage.getItem(this.sessionKey) === 'true'
        });
        
        // List all credentials
        Array.from(this.memoryCache.values()).forEach(cred => {
            const age = Date.now() - cred.storedAt;
            const ageHours = Math.round(age / (1000 * 60 * 60));
            console.log(`  📄 ${cred.id} (${cred.packageType}) - ${ageHours}h old`);
        });
    }
    
    /**
     * Sync DID registry from network
     */
    async syncDidRegistry() {
        if (!this.networkConfig.registryUrl) return false;
        
        try {
            const response = await fetch('/api/network/did-registry', {
                method: 'GET',
                headers: {
                    'Authorization': `Network ${this.networkConfig.authKey}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                
                if (data.success && data.needs_update) {
                    // Update local DID registry cache
                    Object.entries(data.registry).forEach(([did, issuerInfo]) => {
                        this.didRegistry.set(did, {
                            ...issuerInfo,
                            lastUpdated: Date.now()
                        });
                    });
                    
                    this.networkConfig.lastDidSync = Date.now();
                    
                    if (this.debug) {
                        console.log(`📋 DID registry synced: ${Object.keys(data.registry).length} issuers`);
                    }
                    
                    return true;
                }
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ DID registry sync failed:', error.message);
            }
        }
        
        return false;
    }
    
    /**
     * Sync revocation lists from network
     */
    async syncRevocationLists() {
        if (!this.networkConfig.registryUrl) return false;
        
        try {
            const response = await fetch('/api/network/revocation-lists', {
                method: 'GET',
                headers: {
                    'Authorization': `Network ${this.networkConfig.authKey}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    last_sync: this.networkConfig.lastRevocationSync
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                
                if (data.success && data.has_updates) {
                    // Update local revocation bloom filter
                    Object.keys(data.revocation_updates).forEach(credentialId => {
                        this.revocationBloomFilter.add(credentialId);
                    });
                    
                    // Update OPRF bloom filter entries
                    Object.keys(data.bloom_filter_updates).forEach(oprfEval => {
                        this.revocationBloomFilter.add(oprfEval);
                    });
                    
                    this.networkConfig.lastRevocationSync = data.sync_timestamp;
                    
                    if (this.debug) {
                        console.log(`🚫 Revocation lists synced: ${Object.keys(data.revocation_updates).length} updates`);
                    }
                    
                    return true;
                }
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Revocation list sync failed:', error.message);
            }
        }
        
        return false;
    }
    
    /**
     * Check if a credential is revoked using network data
     */
    async isCredentialRevoked(credential) {
        // Check local bloom filter first (fast)
        if (this.revocationBloomFilter.has(credential.id)) {
            if (this.debug) {
                console.log(`🚫 Credential ${credential.id} is revoked (bloom filter hit)`);
            }
            return true;
        }
        
        // For OPRF-based checking, we'd need the OPRF evaluation
        // This is a simplified version
        const oprfEval = `oprf_${credential.id}_${Math.floor(credential.issued_at / 86400)}`;
        if (this.revocationBloomFilter.has(oprfEval)) {
            if (this.debug) {
                console.log(`🚫 Credential ${credential.id} is revoked (OPRF bloom filter hit)`);
            }
            return true;
        }
        
        return false;
    }
    
    /**
     * Validate issuer DID using network registry
     */
    async validateIssuerDid(issuerDid) {
        const issuerInfo = this.didRegistry.get(issuerDid);
        
        if (!issuerInfo) {
            if (this.debug) {
                console.warn(`⚠️ Unknown issuer DID: ${issuerDid}`);
                console.log(`📋 Known DIDs (${this.didRegistry.size}):`, Array.from(this.didRegistry.keys()));
            }
            return {
                valid: false,
                reason: 'unknown_issuer',
                trustScore: 0
            };
        }
        
        if (this.debug) {
            console.log(`✅ Valid issuer DID: ${issuerDid} (${issuerInfo.issuerInfo?.name || issuerInfo.name})`);
        }
        
        return {
            valid: issuerInfo.issuerInfo?.verified !== false, // Default to true if not specified
            trustScore: issuerInfo.issuerInfo?.trust_score || issuerInfo.trust_score || 0.5,
            issuerName: issuerInfo.issuerInfo?.name || issuerInfo.name,
            issuerType: issuerInfo.issuerInfo?.issuer_type || issuerInfo.issuer_type
        };
    }
    
    /**
     * Start background network sync
     */
    startNetworkSync() {
        if (!this.networkConfig.registryUrl) {
            if (this.debug) {
                console.log('📡 Network sync disabled - no registry URL configured');
            }
            return;
        }
        
        // Initial sync
        this.syncDidRegistry();
        this.syncRevocationLists();
        
        // Schedule periodic syncs
        setInterval(() => {
            this.syncDidRegistry();
            this.syncRevocationLists();
        }, this.networkConfig.syncInterval);
        
        if (this.debug) {
            console.log(`📡 Network sync started - interval: ${this.networkConfig.syncInterval / 1000}s`);
        }
    }
    
    /**
     * Start background credential checks based on security level
     */
    startBackgroundChecks() {
        if (!this.securityConfig.enabled) {
            if (this.debug) {
                console.log('🛡️ Background security checks disabled');
            }
            return;
        }
        
        // Use custom interval if specified, otherwise use security level interval
        const checkInterval = this.securityConfig.customInterval || this.securityConfig.checkInterval;
        
        // Initial check
        this.performBackgroundCheck();
        
        // Schedule recurring checks
        this.securityConfig.activeIntervalId = setInterval(() => {
            this.performBackgroundCheck();
        }, checkInterval);
        
        if (this.debug) {
            const intervalSeconds = checkInterval / 1000;
            console.log(`🛡️ Background security checks started - level: ${this.securityConfig.securityLevel}, interval: ${intervalSeconds}s`);
        }
    }
    
    /**
     * Stop background credential checks
     */
    stopBackgroundChecks() {
        if (this.securityConfig.activeIntervalId) {
            clearInterval(this.securityConfig.activeIntervalId);
            this.securityConfig.activeIntervalId = null;
            
            if (this.debug) {
                console.log('🛡️ Background security checks stopped');
            }
        }
    }
    
    /**
     * Perform a background credential check (silent, non-intrusive)
     */
    async performBackgroundCheck() {
        if (!this.securityConfig.enabled) return;
        
        const startTime = performance.now();
        
        try {
            // Get all credentials for background checking
            const credentials = Array.from(this.memoryCache.values());
            
            if (credentials.length === 0) {
                if (this.debug) {
                    console.log('🛡️ Background check: No credentials to verify');
                }
                return { success: true, credentialsChecked: 0 };
            }
            
            let validCredentials = 0;
            let revokedCredentials = 0;
            let failedChecks = 0;
            
            for (const credential of credentials) {
                try {
                    // Step 1: Fast local revocation check (bloom filter - ~0.1µs)
                    const isRevoked = await this.isCredentialRevoked(credential);
                    if (isRevoked) {
                        revokedCredentials++;
                        
                        // Remove revoked credential immediately
                        await this.removeCredential(credential.id);
                        
                        if (this.debug) {
                            console.warn(`🚫 Background check: Removed revoked credential ${credential.id}`);
                        }
                        
                        // Trigger security event
                        this.triggerSecurityEvent('credential_revoked', {
                            credentialId: credential.id,
                            detectedAt: Date.now(),
                            source: 'background_check'
                        });
                        
                        continue;
                    }
                    
                    // Step 2: Fast DID validation (local registry - ~0.1µs)
                    if (credential.issuer) {
                        const issuerValidation = await this.validateIssuerDid(credential.issuer);
                        if (!issuerValidation.valid) {
                            failedChecks++;
                            
                            if (this.debug) {
                                console.warn(`⚠️ Background check: Invalid issuer for ${credential.id}: ${issuerValidation.reason}`);
                            }
                            continue;
                        }
                    }
                    
                    // Step 3: Check credential age and validity
                    const now = Date.now();
                    if (credential.expires_at && credential.expires_at * 1000 < now) {
                        // Remove expired credential
                        await this.removeCredential(credential.id);
                        
                        if (this.debug) {
                            console.warn(`⏰ Background check: Removed expired credential ${credential.id}`);
                        }
                        continue;
                    }
                    
                    validCredentials++;
                    
                } catch (error) {
                    failedChecks++;
                    if (this.debug) {
                        console.warn(`❌ Background check failed for ${credential.id}:`, error.message);
                    }
                }
            }
            
            const checkTime = (performance.now() - startTime);
            this.securityConfig.lastBackgroundCheck = Date.now();
            
            // Reset consecutive failures on successful check
            if (failedChecks === 0) {
                this.securityConfig.consecutiveFailures = 0;
            } else {
                this.securityConfig.consecutiveFailures++;
            }
            
            if (this.debug) {
                console.log(`🛡️ Background check complete: ${validCredentials} valid, ${revokedCredentials} revoked, ${failedChecks} failed (${checkTime.toFixed(2)}ms)`);
            }
            
            return {
                success: true,
                credentialsChecked: credentials.length,
                validCredentials,
                revokedCredentials,
                failedChecks,
                checkTimeMs: checkTime
            };
            
        } catch (error) {
            this.securityConfig.consecutiveFailures++;
            
            if (this.debug) {
                console.error('❌ Background security check failed:', error);
            }
            
            return {
                success: false,
                error: error.message,
                consecutiveFailures: this.securityConfig.consecutiveFailures
            };
        }
    }
    
    /**
     * Trigger background check on specific events
     */
    async checkOnEvent(eventType = 'unknown') {
        if (!this.securityConfig.enabled) return;
        
        if (!this.securityConfig.checkOnEvents.includes(eventType)) {
            return; // Event not configured for checking
        }
        
        if (this.debug) {
            console.log(`🛡️ Event-triggered security check: ${eventType}`);
        }
        
        const result = await this.performBackgroundCheck();
        
        // For sensitive events, may want stricter handling
        if (eventType === 'checkout' || eventType === 'sensitive_action') {
            if (!result.success || result.revokedCredentials > 0) {
                this.triggerSecurityEvent('security_check_failed', {
                    eventType,
                    result,
                    timestamp: Date.now()
                });
                
                return { 
                    passed: false, 
                    reason: 'security_check_failed',
                    details: result 
                };
            }
        }
        
        return { passed: true, details: result };
    }
    
    /**
     * Update security configuration
     */
    updateSecurityConfig(newConfig) {
        const oldLevel = this.securityConfig.securityLevel;
        
        // Update configuration
        Object.assign(this.securityConfig, newConfig);
        
        // Recalculate interval if security level changed
        if (newConfig.securityLevel && newConfig.securityLevel !== oldLevel) {
            this.securityConfig.checkInterval = this.getCheckIntervalForLevel(newConfig.securityLevel);
        }
        
        // Restart background checks with new configuration
        if (this.securityConfig.enabled) {
            this.stopBackgroundChecks();
            this.startBackgroundChecks();
        }
        
        if (this.debug) {
            console.log(`🛡️ Security config updated: level=${this.securityConfig.securityLevel}, interval=${this.securityConfig.checkInterval / 1000}s`);
        }
    }
    
    /**
     * Get current security status
     */
    getSecurityStatus() {
        const now = Date.now();
        const timeSinceLastCheck = now - this.securityConfig.lastBackgroundCheck;
        
        return {
            enabled: this.securityConfig.enabled,
            securityLevel: this.securityConfig.securityLevel,
            checkInterval: this.securityConfig.checkInterval,
            lastCheck: this.securityConfig.lastBackgroundCheck,
            timeSinceLastCheck,
            consecutiveFailures: this.securityConfig.consecutiveFailures,
            isHealthy: this.securityConfig.consecutiveFailures < this.securityConfig.maxConsecutiveFailures,
            nextCheckIn: this.securityConfig.checkInterval - (timeSinceLastCheck % this.securityConfig.checkInterval)
        };
    }
    
    /**
     * Trigger security event (can be overridden by sites for custom handling)
     */
    triggerSecurityEvent(eventType, details) {
        const event = {
            type: eventType,
            timestamp: Date.now(),
            details,
            securityLevel: this.securityConfig.securityLevel
        };
        
        if (this.debug) {
            console.warn(`🚨 Security event: ${eventType}`, details);
        }
        
        // Dispatch custom event for sites to listen to
        if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('lemma-security-event', { 
                detail: event 
            }));
        }
        
        // Site-specific security event handler (can be overridden)
        if (typeof this.onSecurityEvent === 'function') {
            this.onSecurityEvent(event);
        }
    }
    
    /**
     * Remove a credential from all storage layers
     */
    async removeCredential(credentialId) {
        try {
            // Remove from memory cache
            this.memoryCache.delete(credentialId);
            
            // Remove from IndexedDB
            if (this.db) {
                const transaction = this.db.transaction(['credentials'], 'readwrite');
                const store = transaction.objectStore('credentials');
                store.delete(credentialId);
            }
            
            // Update localStorage
            const allCredentials = Array.from(this.memoryCache.values());
            localStorage.setItem(this.storageKey, JSON.stringify(allCredentials));
            
            if (this.debug) {
                console.log(`🗑️ Removed credential: ${credentialId}`);
            }
            
            return true;
        } catch (error) {
            if (this.debug) {
                console.error(`❌ Failed to remove credential ${credentialId}:`, error);
            }
            return false;
        }
    }
}

// Global instance for cross-tab access
window.LemmaFederatedWallet = LemmaFederatedWallet;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaFederatedWallet;
}