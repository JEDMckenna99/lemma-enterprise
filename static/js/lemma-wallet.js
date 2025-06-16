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
 * Lemma Wallet UI - Minimal UI for the wallet
 * Provides a non-intrusive UI for managing credentials
 */
class LemmaWalletUI {
    /**
     * Initialize the wallet UI
     * @param {LemmaWallet} wallet - The wallet instance
     */
    constructor(wallet) {
        this.wallet = wallet;
        this.initializedUI = false;
    }
    
    /**
     * Initialize the wallet UI
     */
    async init() {
        if (this.initializedUI) return;
        
        // Create the wallet UI container
        this.createWalletIcon();
        this.initializedUI = true;
    }
    
    /**
     * Create a minimal wallet icon in the corner of the screen
     */
    createWalletIcon() {
        // Create the wallet icon
        const icon = document.createElement('div');
        icon.className = 'lemma-wallet-icon';
        icon.innerHTML = `
            <div class="lemma-wallet-icon-inner">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
                    <path fill="currentColor" d="M21,18v1c0,1.1-0.9,2-2,2H5c-1.1,0-2-0.9-2-2V5c0-1.1,0.9-2,2-2h14c1.1,0,2,0.9,2,2v1h-9c-1.1,0-2,0.9-2,2v8c0,1.1,0.9,2,2,2H21z M12,16h10V8H12V16z M16,13.5c-0.8,0-1.5-0.7-1.5-1.5s0.7-1.5,1.5-1.5s1.5,0.7,1.5,1.5S16.8,13.5,16,13.5z"/>
                </svg>
            </div>
        `;
        
        // Add styles for the wallet icon
        const style = document.createElement('style');
        style.textContent = `
            .lemma-wallet-icon {
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: 48px;
                height: 48px;
                border-radius: 50%;
                background-color: #6B3FA0;
                color: white;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
                cursor: pointer;
                z-index: 9999;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0.8;
            }
            
            .lemma-wallet-icon:hover {
                transform: scale(1.1);
                opacity: 1;
            }
            
            .lemma-wallet-icon-inner {
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .lemma-wallet-panel {
                position: fixed;
                bottom: 80px;
                right: 20px;
                width: 320px;
                max-height: 480px;
                background-color: white;
                border-radius: 12px;
                box-shadow: 0 5px 20px rgba(0, 0, 0, 0.2);
                z-index: 9998;
                overflow: hidden;
                display: none;
                flex-direction: column;
            }
            
            .lemma-wallet-panel-header {
                padding: 16px;
                background-color: #6B3FA0;
                color: white;
                font-weight: bold;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .lemma-wallet-panel-close {
                cursor: pointer;
                font-size: 20px;
            }
            
            .lemma-wallet-panel-content {
                padding: 16px;
                overflow-y: auto;
                flex: 1;
            }
            
            .lemma-wallet-credential {
                border: 1px solid #eee;
                border-radius: 8px;
                margin-bottom: 12px;
                padding: 12px;
                cursor: pointer;
                transition: all 0.2s ease;
            }
            
            .lemma-wallet-credential:hover {
                box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
            }
            
            .lemma-wallet-credential-title {
                font-weight: bold;
                margin-bottom: 4px;
            }
            
            .lemma-wallet-credential-issuer {
                font-size: 0.9em;
                color: #666;
                margin-bottom: 4px;
            }
            
            .lemma-wallet-credential-date {
                font-size: 0.8em;
                color: #999;
            }
            
            .lemma-wallet-actions {
                padding: 12px 16px;
                border-top: 1px solid #eee;
                display: flex;
                justify-content: flex-end;
                gap: 8px;
            }
            
            .lemma-wallet-button {
                padding: 8px 12px;
                border-radius: 4px;
                border: none;
                font-size: 14px;
                cursor: pointer;
                background-color: #f0f0f0;
                color: #333;
            }
            
            .lemma-wallet-button.primary {
                background-color: #6B3FA0;
                color: white;
            }
            
            @media (max-width: 480px) {
                .lemma-wallet-panel {
                    width: calc(100% - 40px);
                    max-height: 70vh;
                }
            }
        `;
        
        document.head.appendChild(style);
        document.body.appendChild(icon);
        
        // Create the wallet panel
        const panel = document.createElement('div');
        panel.className = 'lemma-wallet-panel';
        panel.innerHTML = `
            <div class="lemma-wallet-panel-header">
                <div>Lemma Wallet</div>
                <div class="lemma-wallet-panel-close">&times;</div>
            </div>
            <div class="lemma-wallet-panel-content">
                <div class="lemma-wallet-credential-list"></div>
            </div>
            <div class="lemma-wallet-actions">
                <button class="lemma-wallet-button" id="lemma-wallet-export">Export</button>
                <button class="lemma-wallet-button" id="lemma-wallet-import">Import</button>
            </div>
        `;
        
        document.body.appendChild(panel);
        
        // Add event listeners
        icon.addEventListener('click', () => this.togglePanel());
        panel.querySelector('.lemma-wallet-panel-close').addEventListener('click', () => this.togglePanel());
        panel.querySelector('#lemma-wallet-export').addEventListener('click', () => this.exportCredentials());
        panel.querySelector('#lemma-wallet-import').addEventListener('click', () => this.importCredentials());
    }
    
    /**
     * Toggle the wallet panel visibility
     */
    async togglePanel() {
        const panel = document.querySelector('.lemma-wallet-panel');
        
        if (panel.style.display === 'flex') {
            panel.style.display = 'none';
        } else {
            panel.style.display = 'flex';
            await this.refreshCredentialList();
        }
    }
    
    /**
     * Refresh the credential list in the panel
     */
    async refreshCredentialList() {
        const listElement = document.querySelector('.lemma-wallet-credential-list');
        listElement.innerHTML = '';
        
        try {
            const credentials = await this.wallet.getAllCredentials();
            
            if (credentials.length === 0) {
                listElement.innerHTML = '<p>No credentials found in your wallet.</p>';
                return;
            }
            
            for (const walletCred of credentials) {
                const credential = walletCred.credential;
                const metadata = walletCred.wallet_metadata;
                
                const credElement = document.createElement('div');
                credElement.className = 'lemma-wallet-credential';
                credElement.dataset.id = credential.id;
                
                credElement.innerHTML = `
                    <div class="lemma-wallet-credential-title">
                        ${metadata.display_name || 'Credential'}
                    </div>
                    <div class="lemma-wallet-credential-issuer">
                        ${credential.issuer || 'Unknown Issuer'}
                    </div>
                    <div class="lemma-wallet-credential-date">
                        Issued: ${new Date(credential.issuanceDate).toLocaleDateString()}
                    </div>
                `;
                
                credElement.addEventListener('click', () => this.showCredentialDetails(credential.id));
                
                listElement.appendChild(credElement);
            }
        } catch (error) {
            console.error('Failed to refresh credential list:', error);
            listElement.innerHTML = '<p>Error loading credentials. Please try again.</p>';
        }
    }
    
    /**
     * Show credential details in a modal
     * @param {string} id - The ID of the credential to show
     */
    async showCredentialDetails(id) {
        try {
            const walletCred = await this.wallet.getCredential(id);
            if (!walletCred) {
                alert('Credential not found');
                return;
            }
            
            const credential = walletCred.credential;
            const metadata = walletCred.wallet_metadata;
            
            // Create a modal for credential details
            const modal = document.createElement('div');
            modal.className = 'lemma-wallet-modal';
            modal.innerHTML = `
                <div class="lemma-wallet-modal-content">
                    <div class="lemma-wallet-modal-header">
                        <div>${metadata.display_name || 'Credential Details'}</div>
                        <div class="lemma-wallet-modal-close">&times;</div>
                    </div>
                    <div class="lemma-wallet-modal-body">
                        <div class="lemma-wallet-detail-item">
                            <div class="lemma-wallet-detail-label">ID</div>
                            <div class="lemma-wallet-detail-value">${credential.id}</div>
                        </div>
                        <div class="lemma-wallet-detail-item">
                            <div class="lemma-wallet-detail-label">Issuer</div>
                            <div class="lemma-wallet-detail-value">${credential.issuer}</div>
                        </div>
                        <div class="lemma-wallet-detail-item">
                            <div class="lemma-wallet-detail-label">Issued Date</div>
                            <div class="lemma-wallet-detail-value">${new Date(credential.issuanceDate).toLocaleString()}</div>
                        </div>
                        <div class="lemma-wallet-detail-item">
                            <div class="lemma-wallet-detail-label">Expiry Date</div>
                            <div class="lemma-wallet-detail-value">${credential.expirationDate ? new Date(credential.expirationDate).toLocaleString() : 'Never'}</div>
                        </div>
                        <div class="lemma-wallet-detail-item">
                            <div class="lemma-wallet-detail-label">Subject ID</div>
                            <div class="lemma-wallet-detail-value">${credential.credentialSubject?.id || 'Unknown'}</div>
                        </div>
                        <div class="lemma-wallet-detail-item">
                            <div class="lemma-wallet-detail-label">Type</div>
                            <div class="lemma-wallet-detail-value">${Array.isArray(credential.type) ? credential.type.join(', ') : credential.type}</div>
                        </div>
                    </div>
                    <div class="lemma-wallet-modal-actions">
                        <button class="lemma-wallet-button" id="lemma-wallet-delete">Delete</button>
                        <button class="lemma-wallet-button primary" id="lemma-wallet-close-detail">Close</button>
                    </div>
                </div>
            `;
            
            // Add modal styles
            const style = document.createElement('style');
            style.textContent = `
                .lemma-wallet-modal {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background-color: rgba(0, 0, 0, 0.5);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 10000;
                }
                
                .lemma-wallet-modal-content {
                    width: 90%;
                    max-width: 480px;
                    background-color: white;
                    border-radius: 12px;
                    overflow: hidden;
                    display: flex;
                    flex-direction: column;
                }
                
                .lemma-wallet-modal-header {
                    padding: 16px;
                    background-color: #6B3FA0;
                    color: white;
                    font-weight: bold;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                
                .lemma-wallet-modal-close {
                    cursor: pointer;
                    font-size: 20px;
                }
                
                .lemma-wallet-modal-body {
                    padding: 16px;
                    max-height: 60vh;
                    overflow-y: auto;
                }
                
                .lemma-wallet-detail-item {
                    margin-bottom: 12px;
                }
                
                .lemma-wallet-detail-label {
                    font-weight: bold;
                    margin-bottom: 4px;
                    color: #666;
                }
                
                .lemma-wallet-detail-value {
                    word-break: break-all;
                }
                
                .lemma-wallet-modal-actions {
                    padding: 12px 16px;
                    border-top: 1px solid #eee;
                    display: flex;
                    justify-content: flex-end;
                    gap: 8px;
                }
            `;
            
            document.head.appendChild(style);
            document.body.appendChild(modal);
            
            // Add event listeners
            modal.querySelector('.lemma-wallet-modal-close').addEventListener('click', () => modal.remove());
            modal.querySelector('#lemma-wallet-close-detail').addEventListener('click', () => modal.remove());
            modal.querySelector('#lemma-wallet-delete').addEventListener('click', async () => {
                if (confirm('Are you sure you want to delete this credential?')) {
                    await this.wallet.deleteCredential(id);
                    modal.remove();
                    this.refreshCredentialList();
                }
            });
        } catch (error) {
            console.error('Failed to show credential details:', error);
            alert('Error showing credential details');
        }
    }
    
    /**
     * Export credentials to a file
     */
    async exportCredentials() {
        try {
            // For simplicity, we'll export all credentials regardless of holder
            const credentials = await this.wallet.getAllCredentials();
            
            if (credentials.length === 0) {
                alert('No credentials to export');
                return;
            }
            
            const bundle = {
                format: 'lemma-wallet-export',
                version: '1.0',
                created_at: new Date().toISOString(),
                credentials: credentials,
                metadata: {
                    credential_count: credentials.length,
                    export_date: new Date().toISOString()
                }
            };
            
            // Convert to JSON and create download link
            const jsonStr = JSON.stringify(bundle, null, 2);
            const blob = new Blob([jsonStr], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = `lemma-credentials-${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            
            // Clean up
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 0);
        } catch (error) {
            console.error('Failed to export credentials:', error);
            alert('Error exporting credentials');
        }
    }
    
    /**
     * Import credentials from a file
     */
    async importCredentials() {
        // Create a file input
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'application/json';
        
        input.addEventListener('change', async (event) => {
            const file = event.target.files[0];
            if (!file) return;
            
            try {
                const reader = new FileReader();
                
                reader.onload = async (e) => {
                    try {
                        const bundle = JSON.parse(e.target.result);
                        
                        if (bundle.format !== 'lemma-wallet-export') {
                            alert('Invalid credential export format');
                            return;
                        }
                        
                        const credentials = await this.wallet.importCredentials(bundle);
                        
                        alert(`Successfully imported ${credentials.length} credential(s)`);
                        this.refreshCredentialList();
                    } catch (error) {
                        console.error('Failed to parse import file:', error);
                        alert('Error parsing import file: ' + error.message);
                    }
                };
                
                reader.readAsText(file);
            } catch (error) {
                console.error('Failed to import credentials:', error);
                alert('Error importing credentials');
            }
        });
        
        input.click();
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