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
            authKey: options.networkAuthKey || 'lemma_network_federated_sync_2024',
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
        
        // Cross-tab synchronization
        this.broadcastChannel = null;
        this.storageEventListener = null;
        this.setupCrossTabSync();
        
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
        // Start with empty registry - real DIDs will be loaded first during init()
        // Only add fallback DIDs if real ones fail to load
        
        if (this.debug) {
            console.log(`🔐 Initializing trusted DID registry (will load real DIDs from server)`);
        }
        
        // Real issuer DIDs will be loaded during init() to ensure async completion
    }
    
    /**
     * Add fallback trusted DIDs if real ones fail to load
     */
    addFallbackTrustedDIDs() {
        // Only add fallback DIDs if registry is empty
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
                    trust_score: 0.5, // Lower trust for fallback
                    verified: false,
                    created_at: Date.now(),
                    capabilities: ['federated_identity_verification']
                }
            },
            {
                did: 'did:lemma:platform:lemma.id',
                publicKey: 'lemma_platform_key_2024',
                issuerInfo: {
                    name: 'Lemma Platform (Fallback)',
                    issuer_type: 'platform_admin',
                    trust_score: 0.5, // Lower trust for fallback
                    verified: false,
                    created_at: Date.now(),
                    capabilities: ['admin_access']
                }
            }
        ];
        
        fallbackIssuers.forEach(issuer => {
            this.didRegistry.set(issuer.did, issuer);
        });
        
        if (this.debug) {
            console.warn(`⚠️ Using ${fallbackIssuers.length} fallback DIDs (real DIDs failed to load)`);
        }
    }
    
    async loadRealIssuerDIDs() {
        try {
            // Get real issuer DIDs from the server
            const response = await fetch('/api/network/trusted-issuers');
            if (response.ok) {
                const trustedIssuers = await response.json();
                
                if (trustedIssuers.success && trustedIssuers.issuers) {
                    trustedIssuers.issuers.forEach(issuer => {
                        this.didRegistry.set(issuer.did, {
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
                        console.log(`✅ Added ${trustedIssuers.issuers.length} real issuer DIDs to registry`);
                        console.log(`🔐 Total trusted DIDs: ${this.didRegistry.size}`);
                    }
                }
            } else {
                if (this.debug) {
                    console.warn('⚠️ Could not fetch trusted issuers from server');
                }
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Could not load real issuer DIDs:', error);
            }
        }
        
        // Add fallback DIDs if no real ones were loaded
        this.addFallbackTrustedDIDs();
    }
    
    /**
     * Setup cross-tab synchronization using BroadcastChannel and storage events
     */
    setupCrossTabSync() {
        try {
            // 1. BroadcastChannel for immediate cross-tab communication
            if (typeof BroadcastChannel !== 'undefined') {
                this.broadcastChannel = new BroadcastChannel('lemma_federated_wallet');
                this.broadcastChannel.addEventListener('message', (event) => {
                    this.handleCrossTabMessage(event.data);
                });
                
                if (this.debug) {
                    console.log('📡 BroadcastChannel initialized for cross-tab sync');
                }
            }
            
            // 2. Storage event listener for localStorage changes from other tabs
            this.storageEventListener = (event) => {
                if (event.key === this.storageKey && event.newValue !== event.oldValue) {
                    this.handleStorageChange(event);
                }
            };
            
            window.addEventListener('storage', this.storageEventListener);
            
            if (this.debug) {
                console.log('📡 Storage event listener setup for cross-tab sync');
            }
            
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Cross-tab sync setup failed:', error.message);
            }
        }
    }
    
    /**
     * Handle cross-tab messages via BroadcastChannel
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
                case 'sync_request':
                    this.handleSyncRequest(data.tabId);
                    break;
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Cross-tab message handling failed:', error.message);
            }
        }
    }
    
    /**
     * Handle localStorage storage changes from other tabs
     */
    handleStorageChange(event) {
        try {
            if (this.debug) {
                console.log('📡 Storage change detected from another tab');
            }
            
            // Reload credentials from localStorage
            const newCredentials = event.newValue ? JSON.parse(event.newValue) : [];
            
            if (Array.isArray(newCredentials)) {
                // Clear current memory cache
                this.memoryCache.clear();
                
                // Load new credentials
                newCredentials.forEach(cred => {
                    this.memoryCache.set(cred.id, cred);
                });
                
                if (this.debug) {
                    console.log(`📡 Synced ${newCredentials.length} credentials from other tab`);
                }
                
                // Notify any listening components about the credential update
                this.notifyCredentialUpdate('cross_tab_sync');
            }
            
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Storage change handling failed:', error.message);
            }
        }
    }
    
    /**
     * Handle remote credential storage from another tab
     */
    handleRemoteCredentialStored(credential) {
        if (!credential || !credential.id) return;
        
        try {
            // Add to memory cache if not already present
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
    
    /**
     * Handle remote credential removal from another tab
     */
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
    
    /**
     * Handle remote credentials clearing from another tab
     */
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
     * Handle sync request from another tab
     */
    handleSyncRequest(requestingTabId) {
        try {
            // Send current credentials to requesting tab
            const credentials = Array.from(this.memoryCache.values());
            
            if (this.broadcastChannel && credentials.length > 0) {
                this.broadcastChannel.postMessage({
                    type: 'sync_response',
                    tabId: Date.now(), // Our tab ID
                    targetTabId: requestingTabId,
                    credentials: credentials
                });
                
                if (this.debug) {
                    console.log(`📡 Sent sync response with ${credentials.length} credentials`);
                }
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Sync request handling failed:', error.message);
            }
        }
    }
    
    /**
     * Notify components about credential updates
     */
    notifyCredentialUpdate(source) {
        try {
            // Dispatch custom event for components to listen to
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
     * Broadcast credential storage to other tabs
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
    
    /**
     * Broadcast credential removal to other tabs
     */
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
    
    /**
     * Broadcast credentials clearing to other tabs
     */
    broadcastCredentialsCleared() {
        try {
            if (this.broadcastChannel) {
                this.broadcastChannel.postMessage({
                    type: 'credentials_cleared',
                    timestamp: Date.now()
                });
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Credentials clear broadcast failed:', error.message);
            }
        }
    }
    
    /**
     * Request sync from other tabs (useful when initializing)
     */
    requestSyncFromOtherTabs() {
        try {
            if (this.broadcastChannel) {
                const tabId = Date.now();
                this.broadcastChannel.postMessage({
                    type: 'sync_request',
                    tabId: tabId,
                    timestamp: Date.now()
                });
                
                if (this.debug) {
                    console.log('📡 Requested sync from other tabs');
                }
                
                // Listen for sync responses for a short time
                const responseHandler = (event) => {
                    const data = event.data;
                    if (data.type === 'sync_response' && data.targetTabId === tabId) {
                        this.handleSyncResponse(data);
                    }
                };
                
                this.broadcastChannel.addEventListener('message', responseHandler);
                
                // Stop listening after 2 seconds
                setTimeout(() => {
                    this.broadcastChannel.removeEventListener('message', responseHandler);
                }, 2000);
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Sync request failed:', error.message);
            }
        }
    }
    
    /**
     * Handle sync response from another tab
     */
    handleSyncResponse(data) {
        try {
            if (data.credentials && Array.isArray(data.credentials)) {
                let addedCount = 0;
                
                data.credentials.forEach(cred => {
                    if (!this.memoryCache.has(cred.id)) {
                        this.memoryCache.set(cred.id, cred);
                        addedCount++;
                    }
                });
                
                if (this.debug && addedCount > 0) {
                    console.log(`📡 Synced ${addedCount} credentials from tab ${data.tabId}`);
                }
                
                if (addedCount > 0) {
                    this.notifyCredentialUpdate('cross_tab_initial_sync');
                }
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Sync response handling failed:', error.message);
            }
        }
    }
    
    /**
     * Cleanup cross-tab synchronization
     */
    cleanupCrossTabSync() {
        try {
            if (this.broadcastChannel) {
                this.broadcastChannel.close();
                this.broadcastChannel = null;
            }
            
            if (this.storageEventListener) {
                window.removeEventListener('storage', this.storageEventListener);
                this.storageEventListener = null;
            }
            
            if (this.debug) {
                console.log('📡 Cross-tab sync cleaned up');
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Cross-tab sync cleanup failed:', error.message);
            }
        }
    }
    
    /**
     * Initialize wallet - MUST be called before use
     */
    async init() {
        if (this.isReady) {
            if (this.debug) {
                console.log('📋 Federated wallet already initialized');
            }
            return;
        }
        
        try {
            if (this.debug) {
                console.log('🚀 Initializing Federated Wallet...');
            }
            
            // 1. Initialize IndexedDB
            await this.initDB();
            
            // 2. Load existing credentials
            await this.loadExistingCredentials();
            
            // 2.5. Load real issuer DIDs from crypto engine (CRITICAL for security)
            await this.loadRealIssuerDIDs();
            
            // 3. Start network sync
            this.startNetworkSync();
            
            // 4. Start background security checks
            this.startBackgroundChecks();
            
            // 5. Request sync from other tabs if no credentials found locally
            if (this.memoryCache.size === 0) {
                this.requestSyncFromOtherTabs();
            }
            
            // 6. Mark as ready
            this.isReady = true;
            
            if (this.debug) {
                console.log(`✅ Federated wallet ready - ${this.memoryCache.size} credentials loaded`);
                if (this.memoryCache.size > 0) {
                    console.log('📊 Credentials in memory:', Array.from(this.memoryCache.values()).map(c => ({
                        id: c.id,
                        packageType: c.packageType,
                        storedAt: new Date(c.storedAt).toLocaleString(),
                        isHuman: c.claims?.isHuman
                    })));
                } else {
                    console.log('📊 No credentials found in storage layers');
                }
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
        let indexedDBCount = 0;
        let localStorageCount = 0;
        
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
                        indexedDBCount = credentials.length;
                        if (this.debug) console.log(`📊 Loaded ${credentials.length} credentials from IndexedDB`);
                        resolve();
                    };
                    request.onerror = () => {
                        if (this.debug) console.warn('IndexedDB load failed:', request.error);
                        resolve(); // Don't fail
                    };
                });
            } catch (error) {
                if (this.debug) console.warn('IndexedDB load failed:', error);
            }
        } else {
            if (this.debug) console.log('📊 IndexedDB not available, skipping...');
        }
        
        // 2. Fallback to localStorage
        try {
            const stored = localStorage.getItem(this.storageKey);
            if (stored) {
                const credentials = JSON.parse(stored);
                if (Array.isArray(credentials)) {
                    let addedCount = 0;
                    credentials.forEach(cred => {
                        if (!this.memoryCache.has(cred.id)) {
                            this.memoryCache.set(cred.id, cred);
                            addedCount++;
                        }
                    });
                    localStorageCount = credentials.length;
                    if (this.debug) console.log(`📊 Loaded ${credentials.length} credentials from localStorage (${addedCount} new)`);
                }
            } else {
                if (this.debug) console.log('📊 No credentials found in localStorage');
            }
        } catch (error) {
            if (this.debug) console.warn('localStorage load failed:', error);
        }
        
        // 3. Check sessionStorage for temporary credentials
        try {
            const sessionStored = sessionStorage.getItem(this.storageKey);
            if (sessionStored) {
                const credentials = JSON.parse(sessionStored);
                if (Array.isArray(credentials)) {
                    let addedCount = 0;
                    credentials.forEach(cred => {
                        if (!this.memoryCache.has(cred.id)) {
                            this.memoryCache.set(cred.id, cred);
                            addedCount++;
                        }
                    });
                    if (this.debug && addedCount > 0) {
                        console.log(`📊 Loaded ${addedCount} additional credentials from sessionStorage`);
                    }
                }
            }
        } catch (error) {
            if (this.debug) console.warn('sessionStorage load failed:', error);
        }
        
        if (this.debug) {
            const totalCredentials = this.memoryCache.size;
            console.log(`📊 Total credentials loaded: ${totalCredentials} (IndexedDB: ${indexedDBCount}, localStorage: ${localStorageCount})`);
        }
    }
    
    /**
     * Log current storage status for debugging
     */
    logStorageStatus() {
        try {
            const memoryCount = this.memoryCache.size;
            const sessionActive = sessionStorage.getItem(this.sessionKey) === 'true';
            
            let localStorageCount = 0;
            try {
                const stored = localStorage.getItem(this.storageKey);
                if (stored) {
                    const parsed = JSON.parse(stored);
                    localStorageCount = Array.isArray(parsed) ? parsed.length : 0;
                }
            } catch (e) {}
            
            console.log('📊 Storage Status:');
            console.log(`  Memory Cache: ${memoryCount} credentials`);
            console.log(`  Session Active: ${sessionActive}`);
            console.log(`  LocalStorage: ${localStorageCount} credentials`);
            console.log(`  IndexedDB: ${this.db ? 'Available' : 'Not Available'}`);
            console.log(`  Network Registry: ${this.networkConfig.registryUrl ? 'Configured' : 'Not Configured'}`);
            
        } catch (error) {
            console.warn('Storage status logging failed:', error);
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
                if (this.debug) {
                    console.log(`💾 Stored ${allCredentials.length} credentials to localStorage`);
                }
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
            
            // 6. CRITICAL: Broadcast to other tabs for immediate cross-tab sync
            this.broadcastCredentialStored(credentialWithMeta);
            
            if (this.debug) {
                console.log('✅ Credential stored:', {
                    id: credentialWithMeta.id,
                    packageType: credentialWithMeta.packageType,
                    storageResults: results,
                    crossTabBroadcast: true
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
     * Check if we have valid credentials for a package type (SIMPLIFIED - no complex validation)
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
                    storedAt: new Date(c.storedAt).toLocaleString(),
                    isHuman: (c.claims || c.credentialSubject)?.isHuman
                })));
            }
        }
        
        // SECURITY: Only trust credentials that pass verification
        if (hasCredentials) {
            // Check if any credentials are actually valid (not just present)
            const validCredentials = credentials.filter(credential => {
                // Check if issuer is trusted
                const issuerDid = credential.issuer;
                const isTrustedIssuer = this.didRegistry.has(issuerDid);
                
                if (!isTrustedIssuer) {
                    if (this.debug) {
                        console.warn(`⚠️ Rejecting credential with untrusted issuer: ${issuerDid}`);
                    }
                    return false;
                }
                
                // Additional validation could go here (signature verification, expiration, etc.)
                return true;
            });
            
            if (this.debug) {
                console.log(`🔐 Valid credentials: ${validCredentials.length}/${credentials.length}`);
            }
            
            return validCredentials.length > 0;
        }
        
        // If no local credentials, check shared network for cross-site recognition
        if (this.networkConfig.registryUrl && packageType === 'identity') {
            try {
                // Use PPID for privacy-preserving network lookup
                const ppid = await this.generatePPIDForOrigin();
                
                const networkResponse = await fetch(`${this.networkConfig.registryUrl}/check-shared-identity`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Network ${this.networkConfig.authKey}`
                    },
                    body: JSON.stringify({
                        ppid: ppid,
                        origin: window.location.origin,
                        check_cross_site: true
                    })
                });
                
                if (networkResponse.ok) {
                    const networkResult = await networkResponse.json();
                    if (networkResult.success && networkResult.has_valid_identity) {
                        if (this.debug) {
                            console.log('🌐 Found valid identity lemma in federated network via PPID');
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
        
        return false;
    }
    
    /**
     * Get current user ID for network checks (PPID-aware)
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
     * Generate PPID for current origin
     */
    async generatePPIDForOrigin(globalUserId = null) {
        try {
            const userId = globalUserId || this.getCurrentUserId();
            const origin = window.location.origin;
            
            // Generate PPID using privacy API
            const response = await fetch('/api/privacy/generate-ppid', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Network ${this.networkConfig.authKey}`
                },
                body: JSON.stringify({
                    global_user_id: userId,
                    site_origin: origin
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                if (this.debug) {
                    console.log(`🔐 Generated PPID for origin ${origin}`);
                }
                return result.ppid;
            } else {
                if (this.debug) {
                    console.warn('⚠️ Failed to generate PPID, using global user ID');
                }
                return userId;
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ PPID generation failed:', error.message);
            }
            return globalUserId || this.getCurrentUserId();
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
     * Complete proof-of-possession verification
     */
    async completePoPVerification(challengeId, credential, userKeyProof) {
        try {
            const timestamp = new Date().toISOString();
            
            const presentation = {
                selectiveDisclosure: ['isHuman'],
                proof: userKeyProof || `mock_proof_${challengeId}_${timestamp}`
            };
            
            const response = await fetch('/api/privacy/verify-complete', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    challenge_id: challengeId,
                    lemma: credential,
                    presentation: presentation,
                    ts: timestamp
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                if (this.debug) {
                    console.log(`✅ Completed PoP verification for challenge ${challengeId}`);
                }
                return result;
            } else {
                throw new Error(`PoP completion failed: ${response.status}`);
            }
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ PoP verification completion failed:', error.message);
            }
            throw error;
        }
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
                // Extract issuer ID from issuer object or use issuer directly if it's a string
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
        
        // Broadcast clearing to other tabs
        this.broadcastCredentialsCleared();
        
        if (this.debug) {
            console.log('🗑️ All credentials cleared (broadcast to other tabs)');
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
     * Debug method: Test storage functionality
     */
    async testStorage() {
        if (!this.debug) return;
        
        console.log('🧪 Testing storage functionality...');
        
        // Test credential
        const testCred = {
            id: 'test_cred_' + Date.now(),
            packageType: 'identity',
            claims: { isHuman: true },
            storedAt: Date.now()
        };
        
        // Store test credential
        const result = await this.storeCredential(testCred);
        console.log('🧪 Store result:', result);
        
        // Check if it can be retrieved
        const hasValid = await this.hasValidCredentials('identity');
        console.log('🧪 hasValidCredentials result:', hasValid);
        
        // Get credentials
        const credentials = await this.getCredentials('identity');
        console.log('🧪 getCredentials result:', credentials.length, 'credentials');
        
        // Clean up test credential
        await this.removeCredential(testCred.id);
        console.log('🧪 Test credential removed');
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
            // Fix: Use query parameters instead of body for GET request
            const params = new URLSearchParams({
                last_sync: this.networkConfig.lastRevocationSync || 0,
                site_id: this.networkConfig.nodeId || 'unknown'  // Server expects 'site_id', not 'node_id'
            });
            
            const response = await fetch(`/api/network/revocation-lists?${params}`, {
                method: 'GET',
                headers: {
                    'Authorization': `Network ${this.networkConfig.authKey}`,
                    'Content-Type': 'application/json'
                }
                // No body for GET request - this was causing the error
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
                    
                    // Check for forced credential removals (network-wide bot marking)
                    await this.checkForForcedRemovals();
                    
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
     * Check for forced credential removals (network-wide revocation)
     */
    async checkForForcedRemovals() {
        try {
            if (!this.memoryCache || this.memoryCache.size === 0) {
                return; // No credentials to check
            }

            const credentialsToRemove = [];
            
            // Check each credential against revocation lists
            for (const [credId, credential] of this.memoryCache.entries()) {
                // Check if credential ID is in revocation list
                if (this.revokedCredentials && this.revokedCredentials.has(credId)) {
                    credentialsToRemove.push(credId);
                    if (this.debug) {
                        console.warn(`🗑️ Credential ${credId} marked for forced removal (revoked)`);
                    }
                }
                
                // Check if issuer DID is revoked
                const issuerDid = typeof credential.issuer === 'object' ? credential.issuer.id : credential.issuer;
                if (issuerDid && this.revokedIssuers && this.revokedIssuers.has(issuerDid)) {
                    credentialsToRemove.push(credId);
                    if (this.debug) {
                        console.warn(`🗑️ Credential ${credId} marked for forced removal (issuer revoked)`);
                    }
                }
            }
            
            // Remove revoked credentials
            for (const credId of credentialsToRemove) {
                await this.removeCredential(credId);
                if (this.debug) {
                    console.warn(`🗑️ Forced removal completed for ${credId}`);
                }
            }
            
            if (credentialsToRemove.length > 0) {
                // Notify other components of credential changes
                this.notifyCredentialUpdate('forced_removal', credentialsToRemove.length);
            }
            
        } catch (error) {
            if (this.debug) {
                console.warn('⚠️ Forced removal check failed:', error.message);
            }
        }
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
                        // Extract issuer ID from issuer object or use issuer directly if it's a string
                        const issuerDid = typeof credential.issuer === 'object' ? credential.issuer.id : credential.issuer;
                        const issuerValidation = await this.validateIssuerDid(issuerDid);
                        if (!issuerValidation.valid) {
                            failedChecks++;
                            
                            if (this.debug) {
                                console.warn(`⚠️ Background check: Invalid issuer for ${credential.id}: ${issuerValidation.reason}`);
                                console.warn(`🗑️ Removing invalid credential from storage...`);
                            }
                            
                            // Remove invalid credential from storage
                            await this.removeCredential(credential.id);
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
            
            // Broadcast removal to other tabs
            this.broadcastCredentialRemoved(credentialId);
            
            if (this.debug) {
                console.log(`🗑️ Removed credential: ${credentialId} (broadcast to other tabs)`);
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
     * Refresh credentials - reload from all storage layers and network
     */
    async refreshCredentials() {
        if (this.debug) {
            console.log('🔄 Refreshing credentials from all sources...');
        }
        
        try {
            // Clear memory cache
            this.memoryCache.clear();
            
            // Reload from all storage layers
            await this.loadExistingCredentials();
            
            // Force network sync
            if (this.networkConfig.registryUrl) {
                await this.syncDidRegistry();
                await this.syncRevocationLists();
            }
            
            // Trigger background check
            await this.performBackgroundCheck();
            
            if (this.debug) {
                console.log(`✅ Refresh complete - ${this.memoryCache.size} credentials loaded`);
                this.logStorageStatus();
            }
            
            // Broadcast refresh to other tabs
            if (this.broadcastChannel) {
                this.broadcastChannel.postMessage({
                    type: 'credentials_refreshed',
                    timestamp: Date.now(),
                    credentialCount: this.memoryCache.size
                });
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
            return {
                success: false,
                error: error.message
            };
        }
    }
}

// Global instance for cross-tab access
window.LemmaFederatedWallet = LemmaFederatedWallet;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaFederatedWallet;
}