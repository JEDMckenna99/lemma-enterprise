/**
 * Lemma Wallet - Minimal Client-Side SSI Wallet
 * Provides a low-friction way to store and manage Lemma credentials
 */

// Prevent redeclaration if already loaded
if (typeof window.LemmaWallet === 'undefined') {

class LemmaWallet {
    /**
     * Initialize the Lemma wallet
     */
    constructor() {
        this.dbName = 'lemma_wallet';
        this.dbVersion = 1;
        this.credentialStore = 'credentials';
        this.metadataStore = 'metadata';
        this.initialized = false;
        
        // OPRF client
        this.oprfClient = null;
        
        // Initialize the wallet
        this.init();
    }
    
    /**
     * Initialize the wallet database
     * @returns {Promise} Promise that resolves when the database is ready
     */
    async init() {
        if (this.initialized) return Promise.resolve();
        
        try {
            this.db = await this.openDatabase();
            this.initialized = true;
            console.log('Lemma wallet initialized');
            return Promise.resolve();
        } catch (error) {
            console.error('Failed to initialize Lemma wallet:', error);
            return Promise.reject(error);
        }
    }
    
    /**
     * Open the IndexedDB database
     * @returns {Promise} Promise that resolves with the database
     */
    openDatabase() {
        return new Promise((resolve, reject) => {
            if (!window.indexedDB) {
                reject(new Error('Your browser does not support IndexedDB, which is required for the wallet'));
                return;
            }
            
            const request = window.indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = (event) => {
                console.error('IndexedDB error:', event.target.error);
                reject(new Error('Failed to open wallet database: ' + event.target.error));
            };
            
            request.onsuccess = (event) => {
                console.log('IndexedDB connection opened successfully');
                resolve(event.target.result);
            };
            
            request.onupgradeneeded = (event) => {
                console.log('IndexedDB upgrade needed, creating stores');
                const db = event.target.result;
                
                // Create credential store
                if (!db.objectStoreNames.contains(this.credentialStore)) {
                    const credentialStore = db.createObjectStore(this.credentialStore, { keyPath: 'id' });
                    credentialStore.createIndex('by_holder', 'wallet_metadata.holder_id', { unique: false });
                    credentialStore.createIndex('by_fingerprint', 'wallet_metadata.fingerprint', { unique: true });
                }
                
                // Create metadata store
                if (!db.objectStoreNames.contains(this.metadataStore)) {
                    const metadataStore = db.createObjectStore(this.metadataStore, { keyPath: 'key' });
                }
            };
        });
    }
    
    /**
     * Store a credential in the wallet
     * @param {Object} credential - The credential to store
     * @returns {Promise} Promise that resolves when the credential is stored
     */
    async storeCredential(credential) {
        await this.init();
        
        console.log('Attempting to store credential:', credential);
        
        // Attempt to fix credential format if it doesn't match expected structure
        let walletCredential = credential;
        
        // If this is a raw credential, format it for wallet storage
        if (!credential.credential && !credential.wallet_metadata) {
            console.log('Converting raw credential to wallet format');
            // Try to determine the user ID from the credential
            let userId = 'unknown';
            if (credential.credentialSubject && credential.credentialSubject.id) {
                userId = credential.credentialSubject.id.replace('did:user:', '');
            }
            
            walletCredential = {
                credential: credential,
                wallet_metadata: {
                    added_at: new Date().toISOString(),
                    holder_id: userId,
                    status: "active",
                    display_name: "Lemma Human Verification",
                    fingerprint: credential.id || `fingerprint-${Date.now()}`
                }
            };
        }
        
        // Validate the credential has required fields
        if (!walletCredential.credential) {
            console.error('Invalid credential format - missing credential property', walletCredential);
            throw new Error('Invalid credential format for wallet storage: missing credential property');
        }
        
        if (!walletCredential.wallet_metadata) {
            console.error('Invalid credential format - missing wallet_metadata property', walletCredential);
            throw new Error('Invalid credential format for wallet storage: missing wallet_metadata property');
        }
        
        // Use the credential ID as the store key
        const id = walletCredential.credential.id;
        if (!id) {
            console.error('Credential must have an ID', walletCredential.credential);
            throw new Error('Credential must have an ID');
        }
        
        walletCredential.id = id;
        
        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction([this.credentialStore], 'readwrite');
                const store = transaction.objectStore(this.credentialStore);
                
                console.log('Storing credential with ID:', id);
                const request = store.put(walletCredential);
                
                request.onsuccess = () => {
                    console.log('Successfully stored credential:', id);
                    resolve(walletCredential);
                };
                
                request.onerror = (event) => {
                    console.error('Failed to store credential:', event.target.error);
                    reject(new Error('Failed to store credential: ' + event.target.error));
                };
            } catch (error) {
                console.error('Exception during credential storage:', error);
                reject(error);
            }
        });
    }
    
    /**
     * Get a credential from the wallet by ID
     * @param {string} id - The ID of the credential to retrieve
     * @returns {Promise} Promise that resolves with the credential
     */
    async getCredential(id) {
        await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.credentialStore], 'readonly');
            const store = transaction.objectStore(this.credentialStore);
            
            const request = store.get(id);
            
            request.onsuccess = (event) => {
                resolve(event.target.result);
            };
            
            request.onerror = (event) => {
                reject(new Error('Failed to retrieve credential: ' + event.target.errorCode));
            };
        });
    }
    
    /**
     * Get all credentials for a specific holder
     * @param {string} holderId - The ID of the credential holder
     * @returns {Promise} Promise that resolves with an array of credentials
     */
    async getCredentialsByHolder(holderId) {
        await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.credentialStore], 'readonly');
            const store = transaction.objectStore(this.credentialStore);
            const index = store.index('by_holder');
            
            const request = index.getAll(holderId);
            
            request.onsuccess = (event) => {
                resolve(event.target.result);
            };
            
            request.onerror = (event) => {
                reject(new Error('Failed to retrieve credentials: ' + event.target.errorCode));
            };
        });
    }
    
    /**
     * Get all credentials in the wallet
     * @returns {Promise} Promise that resolves with an array of all credentials
     */
    async getAllCredentials() {
        await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.credentialStore], 'readonly');
            const store = transaction.objectStore(this.credentialStore);
            
            const request = store.getAll();
            
            request.onsuccess = (event) => {
                resolve(event.target.result);
            };
            
            request.onerror = (event) => {
                reject(new Error('Failed to retrieve all credentials: ' + event.target.errorCode));
            };
        });
    }
    
    /**
     * Delete a credential from the wallet
     * @param {string} id - The ID of the credential to delete
     * @returns {Promise} Promise that resolves when the credential is deleted
     */
    async deleteCredential(id) {
        await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.credentialStore], 'readwrite');
            const store = transaction.objectStore(this.credentialStore);
            
            const request = store.delete(id);
            
            request.onsuccess = () => {
                resolve(true);
            };
            
            request.onerror = (event) => {
                reject(new Error('Failed to delete credential: ' + event.target.errorCode));
            };
        });
    }
    
    /**
     * Export all credentials for a holder as a bundle
     * @param {string} holderId - The ID of the credential holder
     * @returns {Promise} Promise that resolves with the export bundle
     */
    async exportCredentials(holderId) {
        const credentials = await this.getCredentialsByHolder(holderId);
        
        const bundle = {
            format: 'lemma-wallet-export',
            version: '1.0',
            created_at: new Date().toISOString(),
            credentials: credentials,
            metadata: {
                credential_count: credentials.length,
                export_date: new Date().toISOString(),
                holder_id: holderId
            }
        };
        
        return bundle;
    }
    
    /**
     * Import credentials from an export bundle
     * @param {Object} bundle - The export bundle to import
     * @returns {Promise} Promise that resolves with an array of imported credentials
     */
    async importCredentials(bundle) {
        if (bundle.format !== 'lemma-wallet-export') {
            throw new Error('Invalid export bundle format');
        }
        
        const credentials = bundle.credentials || [];
        const importedCredentials = [];
        
        for (const credential of credentials) {
            await this.storeCredential(credential);
            importedCredentials.push(credential);
        }
        
        return importedCredentials;
    }
    
    /**
     * Store wallet metadata
     * @param {string} key - The metadata key
     * @param {*} value - The metadata value
     * @returns {Promise} Promise that resolves when the metadata is stored
     */
    async storeMetadata(key, value) {
        await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.metadataStore], 'readwrite');
            const store = transaction.objectStore(this.metadataStore);
            
            const request = store.put({ key, value });
            
            request.onsuccess = () => {
                resolve(value);
            };
            
            request.onerror = (event) => {
                reject(new Error('Failed to store metadata: ' + event.target.errorCode));
            };
        });
    }
    
    /**
     * Get wallet metadata
     * @param {string} key - The metadata key
     * @returns {Promise} Promise that resolves with the metadata value
     */
    async getMetadata(key) {
        await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.metadataStore], 'readonly');
            const store = transaction.objectStore(this.metadataStore);
            
            const request = store.get(key);
            
            request.onsuccess = (event) => {
                resolve(event.target.result ? event.target.result.value : null);
            };
            
            request.onerror = (event) => {
                reject(new Error('Failed to retrieve metadata: ' + event.target.errorCode));
            };
        });
    }
    
    /**
     * Initialize OPRF client for revocation checking
     * @param {Object} options - OPRF client options
     * @returns {Promise} Promise that resolves when the OPRF client is initialized
     */
    async initOPRF(options = {}) {
        if (!window.LemmaOPRFClient) {
            console.error('LemmaOPRFClient not found. Make sure to include lemma-oprf-client.js');
            return Promise.reject(new Error('LemmaOPRFClient not available'));
        }
        
        try {
            const defaultOptions = {
                serverUrl: '/oprfeval',
                pubkeyEndpoint: '/pubkey',
                cascadeEndpoint: '/cascade/'
            };
            
            const clientOptions = { ...defaultOptions, ...options };
            this.oprfClient = new LemmaOPRFClient(clientOptions);
            
            // Initialize the OPRF client
            await this.oprfClient.initialize();
            
            // Store the OPRF client state in metadata
            await this.storeMetadata('oprf_initialized', true);
            await this.storeMetadata('oprf_epoch', this.oprfClient.epoch);
            
            console.log('OPRF client initialized successfully');
            return Promise.resolve(this.oprfClient);
        } catch (error) {
            console.error('Failed to initialize OPRF client:', error);
            return Promise.reject(error);
        }
    }
    
    /**
     * Check the revocation status of a credential and update its witness
     * @param {string} credentialId - The ID of the credential to check
     * @returns {Promise} Promise that resolves with the revocation status
     */
    async checkRevocationStatus(credentialId) {
        // Ensure OPRF client is initialized
        if (!this.oprfClient) {
            try {
                await this.initOPRF();
            } catch (error) {
                console.error('Failed to initialize OPRF client:', error);
                return { error: 'OPRF client not available', revoked: false };
            }
        }
        
        try {
            // Check revocation status
            const result = await this.oprfClient.checkRevocationStatus(credentialId);
            
            // If the credential has a valid witness, update it in storage
            if (result.witness && !result.revoked) {
                const credential = await this.getCredential(credentialId);
                if (credential) {
                    // Update the witness
                    if (!credential.wallet_metadata.revocation_data) {
                        credential.wallet_metadata.revocation_data = {};
                    }
                    
                    credential.wallet_metadata.revocation_data.witness = result.witness;
                    credential.wallet_metadata.revocation_data.last_checked = new Date().toISOString();
                    credential.wallet_metadata.revocation_data.revoked = result.revoked;
                    
                    // Store the updated credential
                    await this.storeCredential(credential);
                    console.log(`Updated revocation witness for credential ${credentialId}`);
                }
            }
            
            return result;
        } catch (error) {
            console.error(`Failed to check revocation status for credential ${credentialId}:`, error);
            return { error: error.message, revoked: false };
        }
    }
    
    /**
     * Verify a revocation witness without connecting to the server
     * @param {string} credentialId - The ID of the credential to verify
     * @param {Object} cascade - The cascade bundle to check against (if not provided, will be fetched)
     * @returns {Promise} Promise that resolves with the verification result
     */
    async verifyWitness(credentialId, cascade = null) {
        // Ensure OPRF client is initialized
        if (!this.oprfClient) {
            try {
                await this.initOPRF();
            } catch (error) {
                console.error('Failed to initialize OPRF client:', error);
                return { error: 'OPRF client not available', valid: false };
            }
        }
        
        try {
            // Get the credential
            const credential = await this.getCredential(credentialId);
            if (!credential) {
                return { error: 'Credential not found', valid: false };
            }
            
            // Check if credential has a witness
            if (!credential.wallet_metadata.revocation_data || 
                !credential.wallet_metadata.revocation_data.witness) {
                return { error: 'No revocation witness available', valid: false };
            }
            
            const witness = credential.wallet_metadata.revocation_data.witness;
            
            // If cascade not provided, fetch it
            if (!cascade) {
                const response = await fetch(`${this.oprfClient.cascadeEndpoint}${witness.epoch}`);
                if (!response.ok) {
                    throw new Error(`Failed to fetch cascade: ${response.status}`);
                }
                cascade = await response.json();
            }
            
            // Verify the witness
            const isValid = this.oprfClient.verifyWitness(witness, cascade);
            
            return {
                valid: isValid,
                witness: witness,
                epoch: witness.epoch
            };
        } catch (error) {
            console.error(`Failed to verify witness for credential ${credentialId}:`, error);
            return { error: error.message, valid: false };
        }
    }
    
    /**
     * Create a basic Verifiable Presentation
     * @param {Object} credential - The credential to create a presentation for
     * @param {string} challenge - The challenge to sign
     * @returns {Promise} Promise that resolves with the presentation
     */
    async createPresentation(credential, challenge) {
        // Check if this is a wallet credential object or raw credential
        const rawCredential = credential.credential || credential;
        
        try {
            const response = await fetch('/api/presentation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    credential: rawCredential,
                    challenge: challenge
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('Failed to create presentation:', error);
            throw error;
        }
    }

    /**
     * Create a presentation that includes a revocation witness
     * @param {Object} credential - The credential to create a presentation for
     * @param {string} challenge - The challenge to sign
     * @returns {Promise} Promise that resolves with the presentation
     */
    async createPresentationWithWitness(credential, challenge) {
        // Check if this is a wallet credential object or raw credential
        const rawCredential = credential.credential || credential;
        const credentialId = rawCredential.id;
        
        // Make sure we have a revocation witness
        try {
            // Check credential revocation status to update witness if needed
            await this.checkRevocationStatus(credentialId);
            
            // Get the updated credential with witness
            const updatedCredential = await this.getCredential(credentialId);
            
            // Create the presentation normally (assumes this method exists elsewhere)
            const presentation = await fetch('/api/presentation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    credential: updatedCredential.credential,
                    challenge: challenge
                })
            }).then(res => res.json());
            
            // Attach the revocation witness if available
            if (updatedCredential.wallet_metadata.revocation_data && 
                updatedCredential.wallet_metadata.revocation_data.witness) {
                presentation.revocationWitness = updatedCredential.wallet_metadata.revocation_data.witness;
            }
            
            return presentation;
        } catch (error) {
            console.error('Failed to create presentation with witness:', error);
            // Fall back to creating a regular presentation without witness
            return fetch('/api/presentation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    credential: rawCredential,
                    challenge: challenge
                })
            }).then(res => res.json());
        }
    }
}

/**
 * Lemma Wallet UI - REMOVED: Background wallet only, no visual components
 * All wallet operations happen in background during flow 1 (store) and flow 2 (offline->online check)
 */
class LemmaWalletUI {
    /**
     * Initialize the wallet UI - NO-OP (visual wallet removed)
     * @param {LemmaWallet} wallet - The wallet instance
     */
    constructor(wallet) {
        this.wallet = wallet;
        this.initializedUI = true; // Always consider "initialized" since no UI
        console.log('🚫 WALLET UI: Visual wallet components removed - operating in background only');
    }
    
    /**
     * Initialize the wallet UI - NO-OP (background only)
     */
    async init() {
        // NO-OP: Visual wallet removed, operating in background only
        console.log('🚫 WALLET UI: init() called but visual components disabled - background wallet active');
        return;
    }
    
    /**
     * Create wallet icon - REMOVED (background only)
     */
    createWalletIcon() {
        // NO-OP: Visual wallet icon removed - wallet operates in background only
        console.log('🚫 WALLET UI: createWalletIcon() disabled - no visual components');
        return;
    }
    
    /**
     * Toggle wallet panel - REMOVED (background only)
     */
    async togglePanel() {
        // NO-OP: Visual wallet panel removed - wallet operates in background only
        console.log('🚫 WALLET UI: togglePanel() disabled - no visual components');
        return;
    }
    
    /**
     * Refresh credential list - REMOVED (background only)
     */
    async refreshCredentialList() {
        // NO-OP: Visual credential list removed - wallet operates in background only
        console.log('🚫 WALLET UI: refreshCredentialList() disabled - background wallet active');
        return;
    }
    
    /**
     * Show credential details in a modal
     * @param {string} id - The ID of the credential to show
     */
    async showCredentialDetails(id) {
        // NO-OP: Visual credential details removed - wallet operates in background only
        console.log('🚫 WALLET UI: showCredentialDetails() disabled - background wallet only');
        return;
    }
    
    /**
     * Export credentials - REMOVED (background only)
     */
    async exportCredentials() {
        // NO-OP: Visual export functionality removed - wallet operates in background only
        console.log('🚫 WALLET UI: exportCredentials() disabled - background wallet only');
        return;
    }
    
    /**
     * Import credentials - REMOVED (background only)
     */
    async importCredentials() {
        // NO-OP: Visual import functionality removed - wallet operates in background only
        console.log('🚫 WALLET UI: importCredentials() disabled - background wallet only');
        return;
    }
}

// Export classes to global scope for external use (only if not already defined)
if (typeof window.LemmaWallet === 'undefined') {
    window.LemmaWallet = LemmaWallet;
}
if (typeof window.LemmaWalletUI === 'undefined') {
    window.LemmaWalletUI = LemmaWalletUI;
}

} // End of redeclaration guard

// Initialize the wallet when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', () => {
    // Check if the wallet should be initialized
    const shouldInitWallet = document.cookie.includes('lemma_wallet_enabled=true');
    
    if (shouldInitWallet) {
        console.log('Initializing Lemma wallet');
        // Only initialize if classes are available
        if (typeof window.LemmaWallet !== 'undefined' && typeof window.LemmaWalletUI !== 'undefined') {
            const wallet = new window.LemmaWallet();
            const walletUI = new window.LemmaWalletUI(wallet);
            walletUI.init();
            
            // Store the wallet instances in the window object for debugging
            window.lemmaWallet = wallet;
            window.lemmaWalletUI = walletUI;
        } else {
            console.error('LemmaWallet or LemmaWalletUI classes not available');
        }
    }
}); 