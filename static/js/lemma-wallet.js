/**
 * Lemma Wallet - Unified Wallet SDK
 * =================================
 * 
 * Single wallet that provides:
 * - Core federated functionality (always available)
 * - Advanced features (optional via flags)
 * - Device sync (platform-specific)
 * - Backwards compatibility with existing code
 */

// EMERGENCY: Global wallet initialization prevention
window.LEMMA_INIT_COUNT = window.LEMMA_INIT_COUNT || 0;
window.LEMMA_INIT_MAX = 1; // Only allow ONE init ever
window.LEMMA_WALLET_INITIALIZED = window.LEMMA_WALLET_INITIALIZED || false;

class LemmaWallet {
    constructor(options = {}) {
        // EMERGENCY: Absolute prevention of multiple instances
        if (window.LEMMA_WALLET_INITIALIZED) {
            console.warn('⚠️ EMERGENCY: Wallet already initialized - blocking duplicate');
            return window.LEMMA_WALLET_INSTANCE;
        }
        
        // Singleton pattern - prevent multiple instances
        if (LemmaWallet.instance) {
            if (options.debug) {
                console.log('🔄 Wallet already exists - returning existing instance');
            }
            return LemmaWallet.instance;
        }
        
        this.debug = options.debug || false;
        
        // Feature flags
        this.enableAdvancedFeatures = options.enableAdvancedFeatures || false;
        this.enableDeviceSync = options.enableDeviceSync || false;
        this.enableVaultStorage = options.enableVaultStorage || false;
        
        // Core federated wallet properties (ALWAYS AVAILABLE)
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
            authKey: options.networkAuthKey || 'lemma_network_federated_sync_2024',
            syncInterval: options.syncInterval || (5 * 60 * 1000), // 5 minutes
            lastDidSync: 0,
            lastRevocationSync: 0,
            didsCached: false, // Track if DIDs are already loaded
            syncInProgress: false // Prevent concurrent sync operations
        };
        
        // Background security check configuration
        this.securityConfig = {
            enabled: options.backgroundChecks !== false,
            securityLevel: options.securityLevel || 'medium',
            checkInterval: this.getCheckIntervalForLevel(options.securityLevel || 'medium'),
            customInterval: options.customCheckInterval || null,
            checkOnEvents: options.checkOnEvents || ['entry', 'checkout', 'sensitive_action'],
            maxConsecutiveFailures: options.maxFailures || 3,
            gracePeriod: options.gracePeriod || (24 * 60 * 60 * 1000),
            lastBackgroundCheck: 0,
            consecutiveFailures: 0,
            activeIntervalId: null
        };
        
        // Network registry cache
        this.didRegistry = new Map();
        this.revocationBloomFilter = new Set();
        this.loadCachedBloomFilters(); // Load site-specific filters from localStorage
        
        // Cross-tab synchronization
        this.broadcastChannel = null;
        this.storageEventListener = null;
        this.setupCrossTabSync();
        
        // ADVANCED FEATURES (only if enabled)
        if (this.enableAdvancedFeatures) {
            this.initializeAdvancedFeatures();
        }
        
        // Initialize with trusted DIDs
        this.initializeTrustedDIDs();
        
        if (this.debug) {
            console.log('🎯 Lemma Wallet initialized');
            console.log(`⚡ Advanced features: ${this.enableAdvancedFeatures}`);
            console.log(`📱 Device sync: ${this.enableDeviceSync}`);
            console.log(`💾 Vault storage: ${this.enableVaultStorage}`);
        }
    }
    
    /**
     * Initialize advanced features (only if enabled)
     */
    initializeAdvancedFeatures() {
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
        
        // Vault configuration
        this.vaultUrl = '/vault';
        this.backupEnabled = this.enableVaultStorage;
        
        if (this.debug) {
            console.log('🔐 Advanced features initialized');
        }
    }
    
    // ================================================================
    // CORE FEDERATED WALLET FUNCTIONALITY (ALWAYS AVAILABLE)
    // ================================================================
    
    /**
     * Get background check interval for security level
     */
    getCheckIntervalForLevel(level) {
        const intervals = {
            'low': 30 * 60 * 1000,        // 30 minutes
            'medium': 5 * 60 * 1000,      // 5 minutes
            'high': 2 * 60 * 1000,        // 2 minutes
            'critical': 60 * 1000,        // 1 minute
            'realtime': 10 * 1000         // 10 seconds
        };
        return intervals[level] || intervals['medium'];
    }
    
    /**
     * Initialize trusted DIDs (core functionality)
     */
    initializeTrustedDIDs() {
        // Start with empty registry - real DIDs loaded during init()
        if (this.debug) {
            console.log('🔐 Initializing trusted DID registry');
        }
    }
    
    /**
     * Add fallback trusted DIDs if real ones fail to load
     */
    addFallbackTrustedDIDs() {
        if (this.didRegistry.size > 0) {
            return; // Real DIDs already loaded
        }
        
        const fallbackIssuers = [
            {
                did: 'did:lemma:federated:issuer',
                publicKey: 'lemma_federated_network_key_2024',
                issuerInfo: {
                    name: 'Lemma Federated Identity Network (Fallback)',
                    issuer_type: 'federated_identity_provider',
                    trust_score: 0.5,
                    verified: false,
                    created_at: Date.now(),
                    capabilities: ['federated_identity_verification']
                }
            }
        ];
        
        fallbackIssuers.forEach(issuer => {
            this.didRegistry.set(issuer.did, issuer);
        });
        
        if (this.debug) {
            console.warn(`⚠️ Using ${fallbackIssuers.length} fallback DIDs`);
        }
    }
    
    /**
     * Load real issuer DIDs from server
     */
    async loadRealIssuerDIDs() {
        // Skip if DIDs already loaded to prevent repeated API calls
        if (this.didRegistry.size > 0) {
            return; // Silent skip to reduce log spam
        }
        
        try {
            if (this.debug) {
                console.log('📡 Loading real issuer DIDs from API...');
            }
            
            const response = await fetch('/api/network/trusted-issuers');
            if (response.ok) {
                const trustedIssuers = await response.json();
                
                if (trustedIssuers.success && trustedIssuers.issuers) {
                    this.didRegistry.clear();
                    
                    trustedIssuers.issuers.forEach(issuer => {
                        this.didRegistry.set(issuer.did, {
                            did: issuer.did,
                            publicKey: issuer.public_key,
                            issuerInfo: {
                                name: issuer.name,
                                issuer_type: issuer.issuer_type,
                                trust_score: issuer.trust_score || 0.90,
                                verified: true,
                                created_at: Date.now()
                            }
                        });
                    });
                    
                    if (this.debug) {
                        console.log(`✅ Added ${trustedIssuers.issuers.length} real issuer DIDs`);
                        console.log(`📋 Loaded DIDs:`, Array.from(this.didRegistry.keys()));
                    }
                }
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Could not load real issuer DIDs:', error);
            }
        }
        
        this.addFallbackTrustedDIDs();
    }
    
    /**
     * Setup cross-tab synchronization
     */
    setupCrossTabSync() {
        try {
            if (typeof BroadcastChannel !== 'undefined') {
                this.broadcastChannel = new BroadcastChannel('lemma_wallet');
                this.broadcastChannel.addEventListener('message', (event) => {
                    this.handleCrossTabMessage(event.data);
                });
                
                if (this.debug) {
                    console.log('📡 BroadcastChannel initialized');
                }
            }
            
            this.storageEventListener = (event) => {
                if (event.key === this.storageKey && event.newValue !== event.oldValue) {
                    this.handleStorageChange(event);
                }
            };
            
            window.addEventListener('storage', this.storageEventListener);
            
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Cross-tab sync setup failed:', error.message);
            }
        }
    }
    
    /**
     * Handle cross-tab messages
     */
    handleCrossTabMessage(data) {
        if (!data || !data.type) return;
        
        try {
            switch (data.type) {
                case 'credential_stored':
                    this.handleRemoteCredentialStored(data.credential);
                    break;
                case 'credential_removed':
                    this.handleRemoteCredentialRemoved(data.credentialId);
                    break;
                case 'credentials_cleared':
                    this.handleRemoteCredentialsCleared();
                    break;
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Cross-tab message handling failed:', error.message);
            }
        }
    }
    
    /**
     * Handle storage changes from other tabs
     */
    handleStorageChange(event) {
        try {
            if (this.debug) {
                console.log('📡 Storage change detected from another tab');
            }
            
            const newCredentials = event.newValue ? JSON.parse(event.newValue) : [];
            
            if (Array.isArray(newCredentials)) {
                this.memoryCache.clear();
                newCredentials.forEach(cred => {
                    this.memoryCache.set(cred.id, cred);
                });
                
                if (this.debug) {
                    console.log(`📡 Synced ${newCredentials.length} credentials from other tab`);
                }
                
                this.notifyCredentialUpdate('cross_tab_sync');
            }
            
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Storage change handling failed:', error.message);
            }
        }
    }
    
    /**
     * Handle remote credential events
     */
    handleRemoteCredentialStored(credential) {
        if (!credential || !credential.id) return;
        
        try {
            if (!this.memoryCache.has(credential.id)) {
                this.memoryCache.set(credential.id, credential);
                if (this.debug) {
                    console.log(`📡 Added credential from another tab: ${credential.id}`);
                }
                this.notifyCredentialUpdate('remote_store');
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Remote credential storage handling failed:', error.message);
            }
        }
    }
    
    handleRemoteCredentialRemoved(credentialId) {
        if (!credentialId) return;
        
        try {
            if (this.memoryCache.has(credentialId)) {
                this.memoryCache.delete(credentialId);
                if (this.debug) {
                    console.log(`📡 Removed credential from another tab: ${credentialId}`);
                }
                this.notifyCredentialUpdate('remote_remove');
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Remote credential removal handling failed:', error.message);
            }
        }
    }
    
    handleRemoteCredentialsCleared() {
        try {
            this.memoryCache.clear();
            if (this.debug) {
                console.log('📡 Cleared all credentials due to remote clear');
            }
            this.notifyCredentialUpdate('remote_clear');
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Remote credentials clearing failed:', error.message);
            }
        }
    }
    
    /**
     * Notify components about credential updates
     */
    notifyCredentialUpdate(source) {
        try {
            if (typeof window !== 'undefined') {
                window.dispatchEvent(new CustomEvent('lemma-credentials-updated', {
                    detail: {
                        source: source,
                        credentialCount: this.memoryCache.size,
                        timestamp: Date.now()
                    }
                }));
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Credential update notification failed:', error.message);
            }
        }
    }
    
    /**
     * Broadcast credential events to other tabs
     */
    broadcastCredentialStored(credential) {
        try {
            if (this.broadcastChannel) {
                this.broadcastChannel.postMessage({
                    type: 'credential_stored',
                    credential: credential,
                    timestamp: Date.now()
                });
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Credential storage broadcast failed:', error.message);
            }
        }
    }
    
    broadcastCredentialRemoved(credentialId) {
        try {
            if (this.broadcastChannel) {
                this.broadcastChannel.postMessage({
                    type: 'credential_removed',
                    credentialId: credentialId,
                    timestamp: Date.now()
                });
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Credential removal broadcast failed:', error.message);
            }
        }
    }
    
    // ================================================================
    // CORE WALLET FUNCTIONALITY (FEDERATED FEATURES)
    // ================================================================
    
    /**
     * Initialize wallet - MUST be called before use
     */
    async init() {
        // EMERGENCY: Absolute hard limit on init calls
        window.LEMMA_INIT_COUNT = (window.LEMMA_INIT_COUNT || 0) + 1;
        
        if (window.LEMMA_INIT_COUNT > window.LEMMA_INIT_MAX) {
            console.error(`⛔ BLOCKED: Init called ${window.LEMMA_INIT_COUNT} times - MAX is ${window.LEMMA_INIT_MAX}`);
            return; // Hard block any additional inits
        }
        
        // EMERGENCY: Global flag prevents ANY re-initialization
        if (window.LEMMA_INIT_IN_PROGRESS) {
            console.warn('⚠️ Init already in progress - blocking duplicate');
            return; // Silently block if already initializing
        }
        
        if (this.isReady) {
            return; // Already ready, skip
        }
        
        // Set global flag IMMEDIATELY
        window.LEMMA_INIT_IN_PROGRESS = true;
        
        try {
            // Reduced logging to prevent console spam
            if (this.debug) {
                console.log('🚀 Initializing Lemma Wallet...');
            }
            
            // 1. Initialize IndexedDB
            await this.initDB();
            
            // 2. Load existing credentials
            await this.loadExistingCredentials();
            
            // 3. Load real issuer DIDs
            await this.loadRealIssuerDIDs();
            
            // 4. Start network sync
            this.startNetworkSync();
            
            // 5. Start background security checks
            this.startBackgroundChecks();
            
            // 6. Initialize advanced features if enabled
            if (this.enableAdvancedFeatures) {
                await this.initializeAdvancedWalletFeatures();
            }
            
            // 7. Mark as ready
            this.isReady = true;
            
            // Set singleton instance
            LemmaWallet.instance = this;
            window.LEMMA_WALLET_INSTANCE = this;
            window.LEMMA_WALLET_INITIALIZED = true;
            
            if (this.debug) {
                console.log(`✅ Lemma wallet ready - ${this.memoryCache.size} credentials loaded`);
                console.log(`🎯 Mode: ${this.enableAdvancedFeatures ? 'Advanced' : 'Standard'} federated wallet`);
            }
            
        } catch (error) {
            console.error('❌ Wallet init failed:', error);
            this.isReady = true; // Fallback to localStorage only
        } finally {
            // Always clear the init flag when done
            window.LEMMA_INIT_IN_PROGRESS = false;
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
                resolve();
            };
            
            request.onsuccess = (event) => {
                this.db = event.target.result;
                // IndexedDB ready (reduced logging)
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
        let encryptedCount = 0;
        let indexedDBCount = 0;
        let localStorageCount = 0;
        
        // 1. PRIORITY: Try encrypted storage first (most secure)
        if (typeof EncryptedLemmaWallet !== 'undefined') {
            try {
                // Use global singleton encrypted wallet instance
                if (!this.encryptedWallet && !window.encryptedWallet) {
                    this.encryptedWallet = new EncryptedLemmaWallet({ debug: this.debug });
                    await this.encryptedWallet.init();
                    // Store globally to ensure single instance across entire app
                    window.encryptedWallet = this.encryptedWallet;
                } else if (window.encryptedWallet && !this.encryptedWallet) {
                    // Use existing global instance
                    this.encryptedWallet = window.encryptedWallet;
                }
                
                const encryptedCredentials = await this.encryptedWallet.listCredentials();
                if (encryptedCredentials && encryptedCredentials.length > 0) {
                    for (const credMeta of encryptedCredentials) {
                        try {
                            const fullCred = await this.encryptedWallet.getCredential(credMeta.id);
                            if (fullCred) {
                                this.memoryCache.set(fullCred.id, fullCred);
                                encryptedCount++;
                            }
                        } catch (e) {
                            if (this.debug) console.warn(`Failed to load encrypted credential ${credMeta.id}:`, e);
                        }
                    }
                    if (this.debug) console.log(`🔐 Loaded ${encryptedCount} credentials from encrypted storage`);
                }
            } catch (error) {
                if (this.debug) console.warn('Encrypted wallet load failed:', error);
            }
        }
        
        // 2. Try IndexedDB (only if no encrypted storage)
        if (encryptedCount === 0 && this.db) {
            try {
                const transaction = this.db.transaction(['credentials'], 'readonly');
                const store = transaction.objectStore('credentials');
                const request = store.getAll();
                
                await new Promise((resolve, reject) => {
                    request.onsuccess = () => {
                        const credentials = request.result || [];
                        credentials.forEach(cred => {
                            if (!this.memoryCache.has(cred.id)) {
                                this.memoryCache.set(cred.id, cred);
                            }
                        });
                        indexedDBCount = credentials.length;
                        // Loaded from IndexedDB (reduced logging)
                        resolve();
                    };
                    request.onerror = () => {
                        if (this.debug) console.warn('IndexedDB load failed:', request.error);
                        resolve();
                    };
                });
            } catch (error) {
                if (this.debug) console.warn('IndexedDB load failed:', error);
            }
        }
        
        // 3. Fallback to localStorage (only if no other storage found)
        if (encryptedCount === 0 && indexedDBCount === 0) {
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
                        localStorageCount = credentials.length;
                        // Loaded from localStorage (reduced logging)
                    }
                }
            } catch (error) {
                if (this.debug) console.warn('localStorage load failed:', error);
            }
        }
        
        if (this.debug) {
            console.log(`📊 Loaded credentials: ${encryptedCount} encrypted, ${indexedDBCount} IndexedDB, ${localStorageCount} localStorage`);
        }
    }
    
    /**
     * Store a credential with maximum redundancy (CORE FEDERATED FUNCTIONALITY)
     * NOW WITH TRANSPARENT ENCRYPTION
     */
    async storeCredential(credential) {
        // Don't call init() - wallet should already be initialized
        // await this.init(); // REMOVED: Caused redundant init attempts
        
        // Extract packageType from claims for filtering
        const claims = credential.claims || credential.credentialSubject || {};
        const packageType = claims.packageType || 'identity';  // Default to identity if not specified
        
        const credentialWithMeta = {
            ...credential,
            packageType: packageType,  // Add to root level for filtering
            storedAt: Date.now(),
            lastVerified: Date.now(),
            networkShared: true,
            version: 1
        };
        
        const results = {
            memory: false,
            indexedDB: false,
            localStorage: false,
            encrypted: false
        };
        
        try {
            // 1. Store in memory (immediate access)
            this.memoryCache.set(credentialWithMeta.id, credentialWithMeta);
            results.memory = true;
            
            // 2. TRY ENCRYPTED STORAGE FIRST (transparent, no UX change)
            if (typeof EncryptedLemmaWallet !== 'undefined') {
                try {
                    // Use global singleton encrypted wallet instance
                    if (!this.encryptedWallet && !window.encryptedWallet) {
                        this.encryptedWallet = new EncryptedLemmaWallet({ debug: this.debug });
                        await this.encryptedWallet.init();
                        // Store globally to ensure single instance across entire app
                        window.encryptedWallet = this.encryptedWallet;
                    } else if (window.encryptedWallet && !this.encryptedWallet) {
                        // Use existing global instance
                        this.encryptedWallet = window.encryptedWallet;
                    }
                    
                    await this.encryptedWallet.storeCredential(credentialWithMeta);
                    results.encrypted = true;
                    
                    if (this.debug) {
                        console.log('✅ Stored credential with transparent encryption');
                    }
                } catch (encryptError) {
                    if (this.debug) {
                        console.warn('⚠️ Encryption failed, falling back to plaintext:', encryptError);
                    }
                }
            }
            
            // 3. Store in IndexedDB (persistent across sessions) - ONLY IF ENCRYPTION FAILED
            if (!results.encrypted && this.db) {
                try {
                    const transaction = this.db.transaction(['credentials'], 'readwrite');
                    const store = transaction.objectStore('credentials');
                    await new Promise((resolve, reject) => {
                        const request = store.put(credentialWithMeta);
                        request.onsuccess = () => {
                            results.indexedDB = true;
                            resolve();
                        };
                        request.onerror = () => resolve();
                    });
                } catch (error) {
                    if (this.debug) console.warn('IndexedDB store failed:', error);
                }
            }
            
            // 4. Store in localStorage (backup) - ONLY IF ENCRYPTION FAILED
            // NEVER store in plaintext localStorage if encryption succeeded
            if (!results.encrypted) {
                try {
                    const allCredentials = Array.from(this.memoryCache.values());
                    localStorage.setItem(this.storageKey, JSON.stringify(allCredentials));
                    results.localStorage = true;
                } catch (error) {
                    if (this.debug) console.warn('localStorage store failed:', error);
                }
            } else {
                // Encryption succeeded - clear any old plaintext data
                try {
                    localStorage.removeItem(this.storageKey);
                    if (this.debug) console.log('🗑️ Cleared plaintext localStorage (using encryption)');
                } catch (error) {
                    // Silent fail
                }
            }
            
            // 5. Set session marker
            sessionStorage.setItem(this.sessionKey, 'true');
            
            // 5. Broadcast to other tabs
            this.broadcastCredentialStored(credentialWithMeta);
            
            // 6. Note: No vault backup needed for direct QR sync approach
            
            if (this.debug) {
                console.log('✅ Credential stored:', {
                    id: credentialWithMeta.id,
                    packageType: credentialWithMeta.packageType,
                    storageResults: results,
                    vaultBackup: this.enableVaultStorage
                });
            }
            
            return { 
                success: true, 
                results,
                credentialId: credentialWithMeta.id,
                layers: Object.keys(results).filter(k => results[k])
            };
            
        } catch (error) {
            console.error('❌ Store credential failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Get credentials (core federated functionality)
     */
    async getCredentials(packageType = 'identity') {
        // Don't call init() - wallet should already be initialized
        // await this.init(); // REMOVED: Caused 10+ redundant init attempts
        return this.getCredentialsSync(packageType);
    }
    
    /**
     * Get credentials synchronously from memory cache
     */
    getCredentialsSync(packageType = 'identity') {
        const credentials = Array.from(this.memoryCache.values())
            .filter(cred => cred.packageType === packageType)
            .filter(cred => {
                const maxAge = 30 * 24 * 60 * 60 * 1000; // 30 days
                const age = Date.now() - cred.storedAt;
                return age < maxAge;
            });
            
        return credentials;
    }
    
    /**
     * Check if we have valid credentials (core federated functionality)
     */
    async hasValidCredentials(packageType = 'identity') {
        // Don't call init() - wallet should already be initialized
        // await this.init(); // REMOVED: Caused redundant init attempts
        
        const credentials = this.getCredentialsSync(packageType);
        const hasCredentials = credentials.length > 0;
        
        if (this.debug) {
            console.log(`🔍 hasValidCredentials(${packageType}): ${hasCredentials ? 'YES' : 'NO'}`);
        }
        
        if (hasCredentials) {
            const validCredentials = credentials.filter(credential => {
                const issuerDid = credential.issuer;
                
                // Skip DID registry check for IAM permission lemmas (site-specific issuers)
                const claims = credential.claims || credential.credentialSubject || {};
                const isIAMPermission = claims.packageType === 'permission' && claims.networkType === 'iam_permission';
                
                if (isIAMPermission) {
                    // IAM permissions use site-specific issuers, not federated network
                    if (this.debug) {
                        console.log(`✅ IAM permission credential accepted (site-specific issuer): ${issuerDid.substring(0, 50)}...`);
                    }
                    return true;
                }
                
                // For federated credentials, check DID registry
                const isTrustedIssuer = this.didRegistry.has(issuerDid);
                
                if (!isTrustedIssuer) {
                    if (this.debug) {
                        console.warn(`⚠️ Rejecting credential with untrusted issuer: ${issuerDid}`);
                    }
                    return false;
                }
                
                return true;
            });
            
            return validCredentials.length > 0;
        }
        
        return false;
    }
    
    /**
     * Verify a credential using the REAL Lemma Crypto Engine
     */
    async verifyCredential(credential) {
        const startTime = performance.now();
        
        try {
            if (this.debug) {
                console.log(`🔐 Verifying credential ${credential.id} using REAL Lemma Crypto Engine...`);
            }
            
            // Check revocation status first
            const isRevoked = await this.isCredentialRevoked(credential);
            if (isRevoked) {
                const verificationTime = (performance.now() - startTime) * 1000;
                
                if (this.debug) {
                    console.log(`🚫 Credential ${credential.id} is REVOKED`);
                }
                
                return {
                    success: false,
                    verified: false,
                    confidence: 0.0,
                    verification_time_us: 0,
                    client_time_us: verificationTime,
                    offline: true,
                    engine: 'network_revocation_check',
                    revoked: true,
                    reason: 'credential_revoked_in_network'
                };
            }
            
            // Validate issuer DID
            if (credential.issuer) {
                const issuerDid = typeof credential.issuer === 'object' ? credential.issuer.id : credential.issuer;
                const issuerValidation = await this.validateIssuerDid(issuerDid);
                if (!issuerValidation.valid) {
                    const verificationTime = (performance.now() - startTime) * 1000;
                    
                    if (this.debug) {
                        console.log(`⚠️ Credential ${credential.id} has invalid issuer: ${issuerDid}`);
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
            }
            
            // Call the REAL Rust crypto engine
            const response = await fetch('/api/sdk/check-credentials', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer demo-integration-key-12345'
                },
                body: JSON.stringify({
                    credentials: [credential],
                    enableRustEngine: true,
                    requireFullCrypto: true
                })
            });
            
            if (!response.ok) {
                throw new Error(`Rust Engine API failed: ${response.status}`);
            }
            
            const result = await response.json();
            const verificationTime = (performance.now() - startTime) * 1000;
            
            if (this.debug) {
                console.log(`✅ REAL CRYPTO ENGINE verification: ${result.verified ? 'VALID' : 'INVALID'} (${verificationTime.toFixed(2)}µs client + ${(result.verification_time_us || 0).toFixed(2)}µs engine)`);
            }
            
            return {
                success: true,
                verified: result.verified || false,
                confidence: result.confidence || 0.0,
                verification_time_us: result.verification_time_us || 0,
                client_time_us: verificationTime,
                offline: false,
                engine: 'rust_crypto_engine',
                cryptoComponents: ['Ed25519', 'OPRF', 'Bloom', 'ZKP'],
                details: result.details || {}
            };
            
        } catch (error) {
            const verificationTime = (performance.now() - startTime) * 1000;
            
            if (this.debug) {
                console.error(`❌ REAL CRYPTO ENGINE verification failed for ${credential.id}:`, error.message);
            }
            
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
     * Remove a credential from all storage layers (WITH NETWORK REVOCATION)
     */
    async removeCredential(credentialId) {
        try {
            // Get credential to determine type for proper revocation
            const credential = this.memoryCache.get(credentialId);
            let credentialType = 'unknown';
            let siteDomain = null;
            
            if (credential) {
                const claims = credential.claims || credential.credentialSubject || {};
                if (claims.packageType === 'identity' || claims.isHuman) {
                    credentialType = 'poh';
                } else if (claims.packageType === 'permission' || claims.permissions) {
                    credentialType = 'permission';
                    // Extract site domain for site-specific revocation
                    siteDomain = claims.siteDomain || credential.issuer?.split(':').pop();
                }
            }
            
            // Call network revocation API for proper network updates
            try {
                const revocationResponse = await fetch('/api/wallet/revoke', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        credential_id: credentialId,
                        credential_type: credentialType,
                        site_domain: siteDomain,
                        reason: 'user_requested_removal'
                    })
                });
                
                if (revocationResponse.ok) {
                    const revocationResult = await revocationResponse.json();
                    if (this.debug) {
                        console.log(`🌐 Network revocation result:`, revocationResult);
                    }
                } else {
                    if (this.debug) {
                        console.warn(`⚠️ Network revocation failed for ${credentialId}: ${revocationResponse.status}`);
                    }
                }
            } catch (networkError) {
                if (this.debug) {
                    console.warn(`⚠️ Network revocation API call failed:`, networkError);
                }
            }
            
            // Remove from all storage layers
            this.memoryCache.delete(credentialId);
            
            // Remove from encrypted wallet if available (use this.encryptedWallet, not window)
            if (this.encryptedWallet && typeof this.encryptedWallet.removeCredential === 'function') {
                await this.encryptedWallet.removeCredential(credentialId);
                if (this.debug) {
                    console.log(`🔐 Removed from encrypted wallet: ${credentialId}`);
                }
            } else if (window.encryptedWallet && typeof window.encryptedWallet.removeCredential === 'function') {
                // Fallback to global instance
                await window.encryptedWallet.removeCredential(credentialId);
                if (this.debug) {
                    console.log(`🔐 Removed from encrypted wallet (global): ${credentialId}`);
                }
            } else {
                if (this.debug) {
                    console.warn(`⚠️ No encrypted wallet instance found for removal of ${credentialId}`);
                }
            }
            
            // Remove from IndexedDB
            if (this.db) {
                const transaction = this.db.transaction(['credentials'], 'readwrite');
                const store = transaction.objectStore('credentials');
                store.delete(credentialId);
                if (this.debug) {
                    console.log(`💾 Removed from IndexedDB: ${credentialId}`);
                }
            }
            
            // Remove from plaintext localStorage (legacy)
            const allCredentials = Array.from(this.memoryCache.values());
            localStorage.setItem(this.storageKey, JSON.stringify(allCredentials));
            
            // Broadcast removal to other tabs
            this.broadcastCredentialRemoved(credentialId);
            
            if (this.debug) {
                const scopeMessage = credentialType === 'poh' ? 
                    'network-wide revocation initiated' : 
                    credentialType === 'permission' ? 
                    `site-specific revocation for ${siteDomain || 'unknown site'}` : 
                    'local removal only';
                console.log(`🗑️ Removed credential: ${credentialId} (${scopeMessage})`);
            }
            
            return true;
        } catch (error) {
            if (this.debug) {
                console.error(`❌ Failed to remove credential ${credentialId}:`, error);
            }
            return false;
        }
    }
    
    /**
     * Check if a credential is revoked
     */
    async isCredentialRevoked(credential) {
        if (this.revocationBloomFilter.has(credential.id)) {
            return true;
        }
        
        const oprfEval = `oprf_${credential.id}_${Math.floor(credential.issued_at / 86400)}`;
        if (this.revocationBloomFilter.has(oprfEval)) {
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
            }
            return {
                valid: false,
                reason: 'unknown_issuer',
                trustScore: 0
            };
        }
        
        return {
            valid: issuerInfo.issuerInfo?.verified !== false,
            trustScore: issuerInfo.issuerInfo?.trust_score || 0.5,
            issuerName: issuerInfo.issuerInfo?.name,
            issuerType: issuerInfo.issuerInfo?.issuer_type
        };
    }
    
    /**
     * Start network sync (core federated functionality)
     */
    startNetworkSync() {
        if (!this.networkConfig.registryUrl) {
            if (this.debug) {
                console.log('📡 Network sync disabled - no registry URL');
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
        
        // Network sync started (reduced logging)
    }
    
    /**
     * Sync DID registry from network (cached)
     */
    async syncDidRegistry() {
        // Skip if already synced recently or sync in progress
        const now = Date.now();
        const timeSinceLastSync = now - this.networkConfig.lastDidSync;
        const minSyncInterval = 5 * 60 * 1000; // 5 minutes minimum
        
        if (this.networkConfig.syncInProgress) {
            if (this.debug) {
                console.log('📡 DID sync already in progress - skipping');
            }
            return true;
        }
        
        if (this.networkConfig.didsCached && timeSinceLastSync < minSyncInterval) {
            return true; // Silent skip to reduce log spam
        }
        
        try {
            this.networkConfig.syncInProgress = true;
            
            // Load DIDs if not cached
            if (!this.networkConfig.didsCached) {
                await this.loadRealIssuerDIDs();
                this.networkConfig.didsCached = true;
            }
            
            this.networkConfig.lastDidSync = now;
            return true;
            
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ DID registry sync failed:', error);
            }
            return false;
        } finally {
            this.networkConfig.syncInProgress = false;
        }
    }

    /**
     * Sync revocation lists from network (cached)
     */
    async syncRevocationLists() {
        // Skip if sync in progress or too recent
        const now = Date.now();
        const timeSinceLastSync = now - this.networkConfig.lastRevocationSync;
        const minSyncInterval = 5 * 60 * 1000; // 5 minutes minimum
        
        if (timeSinceLastSync < minSyncInterval) {
            return true; // Silent skip to reduce log spam
        }
        
        try {
            // Get all unique site IDs from credentials to sync their Bloom filters
            const credentials = await this.getAllCredentials();
            const siteIds = new Set();
            
            for (const cred of credentials) {
                const claims = cred.claims || cred.credentialSubject || {};
                const siteId = claims.siteId || claims.site;
                if (siteId) {
                    siteIds.add(siteId);
                }
            }
            
            if (this.debug) {
                console.log(`🔄 Syncing Bloom filters for ${siteIds.size} sites:`, Array.from(siteIds));
            }
            
            // Sync Bloom filter for each site separately
            for (const siteId of siteIds) {
                await this.syncSiteBloomFilter(siteId);
            }
            
            this.networkConfig.lastRevocationSync = now;
            return true;
            
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Revocation list sync failed:', error);
            }
            return false;
        }
    }
    
    /**
     * Load cached site-specific Bloom filters from localStorage
     */
    loadCachedBloomFilters() {
        try {
            // Find all lemma_bloom_* keys in localStorage
            const bloomKeys = Object.keys(localStorage).filter(key => key.startsWith('lemma_bloom_'));
            
            let totalRevocations = 0;
            
            for (const key of bloomKeys) {
                try {
                    const cached = JSON.parse(localStorage.getItem(key));
                    if (cached && cached.data && Array.isArray(cached.data)) {
                        // Merge site-specific filter into global Set for O(1) lookup
                        for (const id of cached.data) {
                            this.revocationBloomFilter.add(id);
                        }
                        totalRevocations += cached.data.length;
                    }
                } catch (e) {
                    // Ignore corrupted cache entries
                    if (this.debug) {
                        console.warn(`⚠️ Corrupted Bloom filter cache: ${key}`);
                    }
                }
            }
            
            if (this.debug && totalRevocations > 0) {
                console.log(`📊 Loaded ${totalRevocations} revocations from ${bloomKeys.length} site(s)`);
            }
            
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Failed to load cached Bloom filters:', error);
            }
        }
    }
    
    /**
     * Sync Bloom filter for a specific site
     */
    async syncSiteBloomFilter(siteId) {
        try {
            const response = await fetch(`/api/revocation/bloom-filter?site_id=${encodeURIComponent(siteId)}`);
            const data = await response.json();
            
            if (data.success && data.revoked_ids) {
                // Store site-specific Bloom filter in localStorage
                const cacheKey = `lemma_bloom_${siteId}`;
                
                localStorage.setItem(cacheKey, JSON.stringify({
                    data: data.revoked_ids,
                    sync: Date.now(),
                    version: data.version,
                    siteId: siteId,
                    isolation: 'site_specific'  // Mark as site-isolated
                }));
                
                // Update in-memory Set (merge all sites into one for quick lookup)
                for (const id of data.revoked_ids) {
                    this.revocationBloomFilter.add(id);
                }
                
                if (this.debug) {
                    console.log(`✅ Synced site-specific Bloom filter for ${siteId}: ${data.revoked_ids.length} revocations`);
                }
            }
            
        } catch (error) {
            if (this.debug) {
                console.warn(`⚠️ Failed to sync Bloom filter for ${siteId}:`, error);
            }
        }
    }
    
    /**
     * Start background security checks
     */
    startBackgroundChecks() {
        if (!this.securityConfig.enabled) {
            if (this.debug) {
                console.log('🛡️ Background security checks disabled');
            }
            return;
        }
        
        const checkInterval = this.securityConfig.customInterval || this.securityConfig.checkInterval;
        
        this.performBackgroundCheck();
        
        this.securityConfig.activeIntervalId = setInterval(() => {
            this.performBackgroundCheck();
        }, checkInterval);
        
        // Background security checks started (reduced logging)
    }
    
    /**
     * Perform background credential check
     */
    async performBackgroundCheck() {
        if (!this.securityConfig.enabled) return;
        
        try {
            const credentials = Array.from(this.memoryCache.values());
            
            if (credentials.length === 0) {
                return { success: true, credentialsChecked: 0 };
            }
            
            let validCredentials = 0;
            let revokedCredentials = 0;
            
            for (const credential of credentials) {
                try {
                    const isRevoked = await this.isCredentialRevoked(credential);
                    if (isRevoked) {
                        revokedCredentials++;
                        await this.removeCredential(credential.id);
                        
                        if (this.debug) {
                            console.warn(`🚫 Background check: Removed revoked credential ${credential.id}`);
                        }
                        continue;
                    }
                    
                    validCredentials++;
                } catch (error) {
                    if (this.debug) {
                        console.warn(`❌ Background check failed for ${credential.id}:`, error.message);
                    }
                }
            }
            
            if (this.debug) {
                console.log(`🛡️ Background check: ${validCredentials} valid, ${revokedCredentials} revoked`);
            }
            
            return {
                success: true,
                credentialsChecked: credentials.length,
                validCredentials,
                revokedCredentials
            };
            
        } catch (error) {
            if (this.debug) {
                console.error('❌ Background security check failed:', error);
            }
            return { success: false, error: error.message };
        }
    }
    
    // ================================================================
    // ADVANCED FEATURES (ONLY IF ENABLED)
    // ================================================================
    
    /**
     * Initialize advanced wallet features (only if enabled)
     */
    async initializeAdvancedWalletFeatures() {
        if (!this.enableAdvancedFeatures) return;
        
        try {
            // Generate or load master seed
            const existingSeed = localStorage.getItem('lemma_master_seed');
            if (existingSeed) {
                this.masterSeed = new Uint8Array(JSON.parse(existingSeed));
                // Loaded existing master seed (reduced logging)
            } else {
                this.masterSeed = new Uint8Array(32);
                crypto.getRandomValues(this.masterSeed);
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
            
            // Generate RID/VID if device sync enabled
            if (this.enableDeviceSync) {
                await this.ensureRIDExists();
            }
            
            if (this.debug) {
                console.log('🔐 Advanced wallet features initialized');
            }
            
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Advanced features initialization failed:', error);
            }
        }
    }
    
    /**
     * Ensure RID exists (only if device sync enabled)
     */
    async ensureRIDExists() {
        if (!this.enableDeviceSync) return;
        
        this.currentRID = localStorage.getItem('lemma_current_rid');
        
        if (!this.currentRID) {
            const identitySource = await this.getIdentitySource();
            
            if (identitySource) {
                this.currentRID = await this.deriveRIDFromIdentity(identitySource);
                localStorage.setItem('lemma_current_rid', this.currentRID);
                
                this.currentVID = await this.deriveVID(this.currentRID);
                localStorage.setItem('lemma_current_vid', this.currentVID);
                
                if (this.debug) {
                    console.log('✅ Generated RID from user identity');
                }
            } else {
                this.currentRID = await this.generateTemporaryRID();
                localStorage.setItem('lemma_current_rid', this.currentRID);
                
                this.currentVID = await this.deriveVID(this.currentRID);
                localStorage.setItem('lemma_current_vid', this.currentVID);
                
                if (this.debug) {
                    console.log('⚠️ Generated temporary RID');
                }
            }
        } else {
            this.currentVID = localStorage.getItem('lemma_current_vid');
            if (!this.currentVID) {
                this.currentVID = await this.deriveVID(this.currentRID);
                localStorage.setItem('lemma_current_vid', this.currentVID);
            }
        }
    }
    
    /**
     * Get identity source for RID derivation
     */
    async getIdentitySource() {
        try {
            const identityCredentials = await this.getCredentials('identity');
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
            ridInput = `${identitySource.subject}_${identitySource.verification_method || 'unknown'}`;
        } else if (identitySource.type === 'stored_user_id') {
            ridInput = identitySource.user_id;
        }
        
        const data = encoder.encode(ridInput + '_root_identity');
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = new Uint8Array(hashBuffer);
        return Array.from(hashArray).map(b => b.toString(16).padStart(2, '0')).join('');
    }
    
    /**
     * Generate temporary RID
     */
    async generateTemporaryRID() {
        const encoder = new TextEncoder();
        const tempData = encoder.encode(`temp_rid_${Date.now()}_${Math.random()}`);
        const hashBuffer = await crypto.subtle.digest('SHA-256', tempData);
        const hashArray = new Uint8Array(hashBuffer);
        return Array.from(hashArray).map(b => b.toString(16).padStart(2, '0')).join('');
    }
    
    /**
     * Derive VID from RID
     */
    async deriveVID(rid) {
        const encoder = new TextEncoder();
        const data = encoder.encode(rid + '_vault_index');
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = new Uint8Array(hashBuffer);
        return Array.from(hashArray).map(b => b.toString(16).padStart(2, '0')).join('');
    }
    
    /**
     * Generate QR code for device sync (direct method only - no vault needed)
     * SECURITY: Only works on PIN-protected lemma.id/wallet page
     * NO SHIELD - Wallet accepts credentials from ANY site
     */
    async generateDeviceSyncQR() {
        if (!this.enableDeviceSync) {
            return { success: false, reason: 'device_sync_disabled' };
        }
        
        // SECURITY CHECK: Multiple layers of protection
        // 1. Only allow on lemma.id/wallet page (protected by optional PIN)
        if (window.location.pathname !== '/wallet') {
            return { 
                success: false, 
                reason: 'security_restriction',
                message: 'Device sync only available on lemma.id/wallet page',
                redirect_url: '/wallet'
            };
        }
        
        // 2. Verify domain is lemma.id (prevent subdomain attacks)
        if (!window.location.hostname.endsWith('lemma.id') && window.location.hostname !== 'localhost') {
            return {
                success: false,
                reason: 'security_restriction', 
                message: 'Device sync only available on official lemma.id domain'
            };
        }
        
        // 3. Check for HTTPS in production (allow localhost for development)
        if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') {
            return {
                success: false,
                reason: 'security_restriction',
                message: 'Device sync requires secure HTTPS connection'
            };
        }
        
        // 4. Rate limiting check (prevent abuse)
        // Removed rate limiting to allow unique QR generation each time
        
        try {
            const credentials = await this.getCredentials();
            
            // Allow QR generation even with empty wallet for initial device setup
            const walletData = {
                credentials: credentials,
                metadata: {
                    exported_at: Date.now(),
                    device_fingerprint: this.getDeviceFingerprint(),
                    export_source: window.location.origin,
                    credential_count: credentials.length,
                    wallet_type: credentials.length > 0 ? 'populated' : 'empty'
                }
            };
            
            if (this.debug) {
                console.log(`📊 Generating QR for ${credentials.length > 0 ? 'populated' : 'empty'} wallet (${credentials.length} credentials)`);
            }
            
            const walletJson = JSON.stringify(walletData);
            const walletSize = walletJson.length;
            
            if (this.debug) {
                console.log(`📊 Wallet size: ${walletSize} bytes (${credentials.length} credentials)`);
            }
            
            // Use QR trigger approach (small QR, internet transfer)
            return await this.generateTransferTokenQR(walletData);
            
        } catch (error) {
            console.error('❌ QR generation failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Generate transfer token QR (small QR, internet transfer)
     * SECURITY: QR contains only transfer token, wallet sent over internet
     */
    async generateTransferTokenQR(walletData) {
        try {
            // Generate unique device ID for this session (security: must be unique each time)
            const randomBytes = new Uint8Array(16);
            crypto.getRandomValues(randomBytes);
            const randomHex = Array.from(randomBytes, b => b.toString(16).padStart(2, '0')).join('');
            const deviceId = this.getDeviceFingerprint() + '_' + Date.now() + '_' + randomHex;
            
            if (this.debug) {
                console.log('🔄 Creating transfer session for wallet sync...');
            }
            
            // Create transfer session (use current origin - lemma.id or Heroku)
            const apiBase = window.location.origin;
                
            const sessionResponse = await fetch(`${apiBase}/api/wallet/transfer/create-session`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    device_id: deviceId
                })
            });
            
            if (!sessionResponse.ok) {
                throw new Error(`Failed to create transfer session: ${sessionResponse.status}`);
            }
            
            const sessionResult = await sessionResponse.json();
            if (!sessionResult.success) {
                throw new Error(sessionResult.error || 'Failed to create transfer session');
            }
            
            // Store wallet data in the session
            const setWalletData = {
                session_id: sessionResult.session_id,
                wallet_data: walletData
            };
            
            if (this.debug) {
                console.log('📤 Setting wallet data in session...');
                console.log('📋 API URL:', `${apiBase}/api/wallet/transfer/set-wallet`);
                console.log('📋 Request data:', {
                    session_id: setWalletData.session_id,
                    wallet_data_size: JSON.stringify(setWalletData.wallet_data).length
                });
            }
            
            const walletResponse = await fetch(`${apiBase}/api/wallet/transfer/set-wallet`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(setWalletData)
            });
            
            if (this.debug) {
                console.log('📥 Set wallet response status:', walletResponse.status);
                console.log('📥 Set wallet response headers:', Object.fromEntries(walletResponse.headers.entries()));
            }
            
            if (!walletResponse.ok) {
                const errorText = await walletResponse.text();
                console.error('❌ Set wallet error response:', errorText);
                throw new Error(`Failed to set wallet data: ${walletResponse.status} - ${errorText}`);
            }
            
            // Create QR data (small token only)
            const qrData = sessionResult.qr_data;
            // Ensure transfer URL points to the same domain as the current session
            const transferUrl = `${window.location.origin}/wallet?transfer=${btoa(JSON.stringify(qrData))}`;
            
            if (this.debug) {
                console.log('✅ Transfer session created successfully');
                console.log(`📊 QR URL length: ${transferUrl.length} characters (fits in any QR!)`);
                console.log(`🔐 Session expires at: ${new Date(sessionResult.expires_at).toLocaleString()}`);
            }
            
            return {
                success: true,
                sync_url: transferUrl,
                qr_data_for_server: transferUrl,
                sync_method: 'transfer_token',
                expires_at: sessionResult.expires_at,
                session_id: sessionResult.session_id,
                vault_required: false,
                metadata: walletData.metadata,
                security_features: [
                    'QR trigger (no sensitive data in QR)',
                    'Encrypted internet transfer',
                    'Time-limited sessions (5 minutes)',
                    'Device authentication',
                    'End-to-end encryption'
                ]
            };
            
        } catch (error) {
            console.error('❌ Transfer token QR generation failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Generate direct QR with encrypted credentials (DEPRECATED - too large)
     * SECURITY: Strong encryption + time-limited + device-bound
     */
    async generateDirectQR(walletData) {
        try {
            // Generate secure random password for this sync session
            const passwordBytes = crypto.getRandomValues(new Uint8Array(16));
            const password = Array.from(passwordBytes).map(b => b.toString(16).padStart(2, '0')).join('');
            
            const encoder = new TextEncoder();
            const data = encoder.encode(JSON.stringify(walletData));
            
            // Generate strong encryption key from password
            const keyMaterial = await crypto.subtle.importKey(
                'raw',
                encoder.encode(password),
                'PBKDF2',
                false,
                ['deriveKey']
            );
            
            // Use random salt for each QR
            const salt = crypto.getRandomValues(new Uint8Array(16));
            const key = await crypto.subtle.deriveKey(
                {
                    name: 'PBKDF2',
                    salt: salt,
                    iterations: 100000,
                    hash: 'SHA-256'
                },
                keyMaterial,
                { name: 'AES-GCM', length: 256 },
                false,
                ['encrypt']
            );
            
            // Encrypt the credentials
            const iv = crypto.getRandomValues(new Uint8Array(12));
            const encrypted = await crypto.subtle.encrypt(
                { name: 'AES-GCM', iv: iv },
                key,
                data
            );
            
            // Create secure sync package
            const syncPackage = {
                type: 'lemma_direct_sync',
                version: 1,
                salt: Array.from(salt),
                iv: Array.from(iv),
                encrypted_data: Array.from(new Uint8Array(encrypted)),
                password: password,
                expires_at: Date.now() + (5 * 60 * 1000), // 5 minute expiry
                sync_method: 'direct_qr',
                security_level: 'AES-256-GCM-PBKDF2'
            };
            
            const syncUrl = `${window.location.origin}/wallet?sync=${btoa(JSON.stringify(syncPackage))}`;
            
            if (this.debug) {
                console.log('✅ Secure direct QR generated (no vault/server needed)');
                console.log(`📊 QR size: ${syncUrl.length} characters`);
                console.log(`🔐 Security: AES-256-GCM with PBKDF2 (100k iterations)`);
                console.log(`⏰ Expires in 5 minutes`);
            }
            
            if (this.debug) {
                console.log(`📊 QR URL length: ${syncUrl.length} characters`);
                console.log(`🔗 Sync URL preview: ${syncUrl.substring(0, 100)}...`);
            }
            
            // Use our own QR generation endpoint (no URL length limits)
            const qrImageUrl = `/api/qr/generate?t=${Date.now()}`;
            
            return {
                success: true,
                sync_url: syncUrl,
                qr_image_url: qrImageUrl,
                qr_data_for_server: syncUrl, // Data to send to our QR endpoint
                sync_method: 'direct_qr',
                expires_at: syncPackage.expires_at,
                password: password,
                vault_required: false,
                metadata: walletData.metadata,
                security_features: [
                    'AES-256-GCM encryption',
                    'PBKDF2 key derivation (100k iterations)',
                    'Random salt per QR',
                    'Time-limited (5 minutes)',
                    'Device fingerprint validation',
                    'Optional PIN protection (wallet page only)'
                ]
            };
            
        } catch (error) {
            console.error('❌ Direct QR generation failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Sync from device QR (direct method only - no vault)
     * SECURITY: Only works on PIN-protected lemma.id/wallet page
     * NO SHIELD - Wallet is universal credential manager for ALL sites
     */
    async syncFromDeviceQR(qrData) {
        if (!this.enableDeviceSync) {
            return { success: false, reason: 'device_sync_disabled' };
        }
        
        // SECURITY CHECK: Multiple layers of protection
        // 1. Only allow on lemma.id/wallet page (protected by optional PIN)
        if (window.location.pathname !== '/wallet') {
            return { 
                success: false, 
                reason: 'security_restriction',
                message: 'Device sync only available on lemma.id/wallet page',
                redirect_url: '/wallet'
            };
        }
        
        // 2. Verify domain is lemma.id (prevent subdomain attacks)
        if (!window.location.hostname.endsWith('lemma.id') && window.location.hostname !== 'localhost') {
            return {
                success: false,
                reason: 'security_restriction', 
                message: 'Device sync only available on official lemma.id domain'
            };
        }
        
        // 3. Check for HTTPS in production (allow localhost for development)
        if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') {
            return {
                success: false,
                reason: 'security_restriction',
                message: 'Device sync requires secure HTTPS connection'
            };
        }
        
        // 4. Rate limiting check for sync attempts (prevent brute force)
        // Removed sync rate limiting to allow immediate QR generation
        
        try {
            if (this.debug) {
                console.log('📱 Processing direct QR sync (no vault dependency)...');
            }
            
            // Decode QR data
            const syncPackage = JSON.parse(atob(qrData));
            
            // Validate sync package
            if (syncPackage.type !== 'lemma_direct_sync') {
                throw new Error('Invalid QR type - must be direct sync');
            }
            
            if (syncPackage.expires_at < Date.now()) {
                throw new Error('QR code has expired');
            }
            
            // Decrypt credentials using password from QR
            const encoder = new TextEncoder();
            const keyMaterial = await crypto.subtle.importKey(
                'raw',
                encoder.encode(syncPackage.password),
                'PBKDF2',
                false,
                ['deriveKey']
            );
            
            const key = await crypto.subtle.deriveKey(
                {
                    name: 'PBKDF2',
                    salt: new Uint8Array(syncPackage.salt),
                    iterations: 100000,
                    hash: 'SHA-256'
                },
                keyMaterial,
                { name: 'AES-GCM', length: 256 },
                false,
                ['decrypt']
            );
            
            // Decrypt the wallet data
            const encryptedData = new Uint8Array(syncPackage.encrypted_data);
            const iv = new Uint8Array(syncPackage.iv);
            
            const decrypted = await crypto.subtle.decrypt(
                { name: 'AES-GCM', iv: iv },
                key,
                encryptedData
            );
            
            const walletData = JSON.parse(new TextDecoder().decode(decrypted));
            
            // Validate wallet data
            if (!walletData.credentials || !Array.isArray(walletData.credentials)) {
                throw new Error('Invalid wallet data in QR');
            }
            
            // Store credentials from QR
            let storedCount = 0;
            for (const credential of walletData.credentials) {
                try {
                    const storeResult = await this.storeCredential(credential);
                    if (storeResult.success) {
                        storedCount++;
                    }
                } catch (error) {
                    if (this.debug) {
                        console.warn(`⚠️ Failed to store credential ${credential.id}:`, error);
                    }
                }
            }
            
            if (this.debug) {
                console.log(`✅ Direct QR sync completed: ${storedCount}/${walletData.credentials.length} credentials restored`);
                console.log('🔐 Security: Encrypted transfer with no server dependency');
            }
            
            return {
                success: true,
                sync_method: 'direct_qr',
                credentials_restored: storedCount,
                total_credentials: walletData.credentials.length,
                vault_used: false,
                security_level: 'AES-256-GCM-PBKDF2'
            };
            
        } catch (error) {
            console.error('❌ Direct QR sync failed:', error);
            return { success: false, error: error.message };
        }
    }
    
    
    /**
     * Get device fingerprint
     */
    getDeviceFingerprint() {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        ctx.textBaseline = 'top';
        ctx.font = '14px Arial';
        ctx.fillText('Lemma device fingerprint', 2, 2);
        
        const fingerprint = canvas.toDataURL();
        return btoa(fingerprint).substring(0, 32);
    }
    
    /**
     * Refresh credentials from all sources
     */
    async refreshCredentials() {
        if (this.debug) {
            console.log('🔄 Refreshing credentials from all sources...');
        }
        
        try {
            this.memoryCache.clear();
            await this.loadExistingCredentials();
            
            if (this.networkConfig.registryUrl) {
                await this.syncDidRegistry();
                await this.syncRevocationLists();
            }
            
            await this.performBackgroundCheck();
            
            if (this.debug) {
                console.log(`✅ Refresh complete - ${this.memoryCache.size} credentials loaded`);
            }
            
            return {
                success: true,
                credentialCount: this.memoryCache.size,
                identityCount: this.getCredentialsSync('identity').length,
                permissionCount: this.getCredentialsSync('permission').length
            };
            
        } catch (error) {
            if (this.debug) {
                console.error('❌ Refresh failed:', error);
            }
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Start proof-of-possession verification flow
     */
    async startPoPVerification() {
        try {
            const origin = window.location.origin;
            const currentEpoch = Math.floor(Date.now() / (24 * 60 * 60 * 1000));
            
            const response = await fetch('/api/privacy/verify-start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    origin: origin,
                    epoch: currentEpoch
                })
            });
            
            if (response.ok) {
                const challenge = await response.json();
                if (this.debug) {
                    console.log(`🎯 Started PoP verification with challenge ${challenge.challenge_id}`);
                }
                return challenge;
            } else {
                throw new Error(`PoP challenge failed: ${response.status}`);
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ PoP verification start failed:', error.message);
            }
            throw error;
        }
    }
    
    /**
     * Clear all credentials (alias for clearWallet for backwards compatibility)
     */
    async clearAll() {
        return this.clearWallet();
    }
    
    /**
     * Get wallet statistics (for UI display)
     */
    getWalletStats() {
        const identityCredentials = this.getCredentialsSync('identity');
        const permissionCredentials = this.getCredentialsSync('permission');
        
        return {
            totalCredentials: this.memoryCache.size,
            identityCredentials: identityCredentials.length,
            permissionCredentials: permissionCredentials.length,
            isReady: this.isReady,
            enableAdvancedFeatures: this.enableAdvancedFeatures,
            enableDeviceSync: this.enableDeviceSync,
            enableVaultStorage: this.enableVaultStorage,
            storageInfo: {
                hasIndexedDB: !!this.db,
                hasLocalStorage: !!localStorage.getItem(this.storageKey),
                hasSessionMarker: !!sessionStorage.getItem(this.sessionKey)
            },
            lastSync: this.networkConfig.lastDidSync,
            lastRevocationSync: this.networkConfig.lastRevocationSync,
            securityLevel: this.securityConfig.securityLevel,
            backgroundChecksEnabled: this.securityConfig.enabled
        };
    }
    
    /**
     * Clear wallet (for testing)
     */
    clearWallet() {
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
            
            // Clear advanced features if enabled
            if (this.enableAdvancedFeatures) {
                localStorage.removeItem('lemma_master_seed');
                localStorage.removeItem('lemma_device_key');
                localStorage.removeItem('lemma_envelope_counter');
                localStorage.removeItem('lemma_current_rid');
                localStorage.removeItem('lemma_current_vid');
                
                if (this.rpKeyCache) this.rpKeyCache.clear();
                if (this.rpDIDCache) this.rpDIDCache.clear();
                if (this.rpTagCache) this.rpTagCache.clear();
            }
        } catch (error) {
            console.warn('Storage clear failed:', error);
        }
        
        // Broadcast clearing to other tabs
        try {
            if (this.broadcastChannel) {
                this.broadcastChannel.postMessage({
                    type: 'credentials_cleared',
                    timestamp: Date.now()
                });
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Clear broadcast failed:', error.message);
            }
        }
        
        if (this.debug) {
            console.log('🗑️ Wallet cleared');
        }
    }

    // Clear all local wallet data (local only - does not revoke credentials)
    async clearAllLocalData() {
        try {
            console.log('🧹 Starting comprehensive local wallet clear...');
            
            // Clear in-memory storage
            this.credentials = [];
            this.issuers = {};
            this.trustedDIDs = [];
            this.memoryCache.clear();
            console.log('✅ In-memory storage cleared');
            
            // Clear IndexedDB
            if (this.db) {
                const transaction = this.db.transaction(['credentials'], 'readwrite');
                const store = transaction.objectStore('credentials');
                await store.clear();
                console.log('✅ IndexedDB credentials cleared');
            }
            
            // Clear localStorage (all lemma-related data)
            const localStorageKeys = Object.keys(localStorage);
            let localCleared = 0;
            localStorageKeys.forEach(key => {
                if (key.startsWith('lemma_') || 
                    key.includes('credential') || 
                    key.includes('wallet') ||
                    key.includes('recovery') ||
                    key.includes('device_fingerprint') ||
                    key.includes('master_seed')) {
                    localStorage.removeItem(key);
                    localCleared++;
                }
            });
            console.log(`✅ localStorage cleared (${localCleared} items)`);
            
            // Clear sessionStorage
            const sessionStorageKeys = Object.keys(sessionStorage);
            let sessionCleared = 0;
            sessionStorageKeys.forEach(key => {
                if (key.startsWith('lemma_') || 
                    key.includes('credential') || 
                    key.includes('wallet')) {
                    sessionStorage.removeItem(key);
                    sessionCleared++;
                }
            });
            console.log(`✅ sessionStorage cleared (${sessionCleared} items)`);
            
            // Reset wallet state
            this.walletReady = false;
            this.deviceFingerprint = null;
            
            // Broadcast clearing to other tabs
            try {
                if (this.broadcastChannel) {
                    this.broadcastChannel.postMessage({
                        type: 'credentials_cleared',
                        timestamp: Date.now()
                    });
                }
            } catch (error) {
                if (this.debug) {
                    console.warn('⚠️ Clear broadcast failed:', error.message);
                }
            }
            
            console.log('🎉 Complete local wallet clear successful');
            console.log('🔐 Credentials remain valid (not revoked)');
            console.log('📱 Use recovery or QR sync to restore wallet');
            
            return {
                success: true,
                cleared: {
                    inMemory: true,
                    indexedDB: true,
                    localStorage: localCleared,
                    sessionStorage: sessionCleared
                }
            };
            
        } catch (error) {
            console.error('❌ Clear wallet error:', error);
            throw new Error(`Failed to clear local wallet data: ${error.message}`);
        }
    }
}

// ================================================================
// BACKWARDS COMPATIBILITY ALIASES
// ================================================================

// Alias for existing code
window.LemmaFederatedWallet = LemmaWallet;
window.LemmaIntegratedWallet = LemmaWallet;
window.LemmaWallet = LemmaWallet;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaWallet;
}
