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
        
        if (this.debug) {
            console.log('🎯 Lemma Federated Wallet starting...');
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
            
            // 3. Mark as ready
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
            
            if (this.debug) {
                console.log('✅ Credential stored:', {
                    id: credentialWithMeta.id,
                    packageType: credentialWithMeta.packageType,
                    storageResults: results
                });
            }
            
            return { success: true, results };
            
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
        
        return hasCredentials;
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
            
            // Call the REAL Rust crypto engine via backend API
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
}

// Global instance for cross-tab access
window.LemmaFederatedWallet = LemmaFederatedWallet;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaFederatedWallet;
}