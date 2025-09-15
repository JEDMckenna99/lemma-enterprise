/**
 * Lemma Wallet Manager - Centralized Wallet Handling
 * Prevents multiple wallet instances and ensures consistent behavior
 */

class LemmaWalletManager {
    constructor() {
        this.walletInstance = null;
        this.initPromise = null;
        this.isInitializing = false;
    }
    
    /**
     * Get or create the global wallet instance (singleton pattern)
     */
    async getWallet() {
        // Return existing instance if available
        if (this.walletInstance && this.walletInstance.isReady) {
            return this.walletInstance;
        }
        
        // Check for existing global instances
        if (window.lemmaWallet && window.lemmaWallet.isReady) {
            this.walletInstance = window.lemmaWallet;
            return this.walletInstance;
        }
        
        if (window.globalLemmaWallet && window.globalLemmaWallet.isReady) {
            this.walletInstance = window.globalLemmaWallet;
            return this.walletInstance;
        }
        
        // If already initializing, wait for that to complete
        if (this.isInitializing && this.initPromise) {
            return await this.initPromise;
        }
        
        // Initialize new wallet
        this.isInitializing = true;
        this.initPromise = this.initializeWallet();
        
        try {
            this.walletInstance = await this.initPromise;
            return this.walletInstance;
        } finally {
            this.isInitializing = false;
            this.initPromise = null;
        }
    }
    
    /**
     * Initialize a new wallet instance
     */
    async initializeWallet() {
        try {
            console.log('🔄 LemmaWalletManager: Initializing new wallet instance...');
            
            const wallet = new LemmaFederatedWallet({
                debug: true,
                networkRegistryUrl: 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/network/sync',
                networkAuthKey: 'lemma_network_federated_sync_2024',
                syncInterval: 30000, // 30 seconds
                enableLocalCrypto: true  // Enable local WASM verification
            });
            
            await wallet.init();
            
            // Initialize local crypto if available
            await this.initializeLocalCrypto(wallet);
            
            // Store in all global locations to prevent multiple instances
            window.lemmaWallet = wallet;
            window.globalLemmaWallet = wallet;
            this.walletInstance = wallet;
            
            console.log('✅ LemmaWalletManager: Wallet initialized and stored globally');
            
            return wallet;
            
        } catch (error) {
            console.error('❌ LemmaWalletManager: Wallet initialization failed:', error);
            throw error;
        }
    }
    
    /**
     * Initialize local crypto verification capability
     */
    async initializeLocalCrypto(wallet) {
        try {
            // Try to load WASM crypto engine
            if (typeof WebAssembly !== 'undefined') {
                console.log('🔐 Attempting to load local WASM crypto...');
                
                // Load from CDN if available
                const cryptoModule = await import('/crypto/lemma-unified-crypto.js').catch(() => null);
                
                if (cryptoModule && cryptoModule.LemmaUnifiedCrypto) {
                    wallet.localCrypto = new cryptoModule.LemmaUnifiedCrypto();
                    await wallet.localCrypto.init();
                    
                    console.log('✅ Local WASM crypto verification enabled');
                    console.log('⚡ Expected performance: 5-15μs local verification');
                    
                    // Add local verification method to wallet
                    wallet.verifyLocalCrypto = async function(credential) {
                        const start = performance.now();
                        const result = await this.localCrypto.verify(credential);
                        const time = (performance.now() - start) * 1000;
                        
                        return {
                            verified: result.verified,
                            verification_time_us: time,
                            method: 'local_wasm',
                            offline: true
                        };
                    };
                    
                } else {
                    console.warn('⚠️ WASM crypto module not available, using API verification');
                }
            } else {
                console.warn('⚠️ WebAssembly not supported, using API verification');
            }
        } catch (error) {
            console.warn('⚠️ Local crypto initialization failed:', error.message);
            console.log('🔄 Falling back to API verification');
        }
    }
    
    /**
     * Store credential with duplicate prevention
     */
    async storeCredential(credential, options = {}) {
        try {
            const wallet = await this.getWallet();
            
            // Check for duplicates
            if (!options.allowDuplicates) {
                const existingCredentials = await wallet.getCredentials(credential.packageType || 'permission');
                const isDuplicate = existingCredentials.some(cred => {
                    // Check by ID
                    if (cred.id === credential.id) return true;
                    
                    // Check by claims (same site, email, permission) - handle both claims and credentialSubject
                    const credClaims = credential.claims || credential.credentialSubject;
                    const existingClaims = cred.claims || cred.credentialSubject;
                    if (credClaims && existingClaims) {
                        return (
                            existingClaims.siteId === credClaims.siteId &&
                            existingClaims.email === credClaims.email &&
                            existingClaims.permissionId === credClaims.permissionId
                        );
                    }
                    
                    return false;
                });
                
                if (isDuplicate) {
                    console.log('ℹ️ LemmaWalletManager: Credential already exists, skipping storage');
                    return {
                        success: true,
                        duplicate: true,
                        message: 'Credential already exists in wallet'
                    };
                }
            }
            
            // Store the credential
            console.log('💾 LemmaWalletManager: Storing credential in unified wallet...');
            const result = await wallet.storeCredential(credential);
            
            if (result.success) {
                console.log('✅ LemmaWalletManager: Credential stored successfully');
                console.log('📊 Storage layers:', result.layers);
                console.log('🌐 Network shared:', result.networkShared);
                
                // Broadcast to other tabs/windows
                this.broadcastCredentialUpdate(credential);
            }
            
            return result;
            
        } catch (error) {
            console.error('❌ LemmaWalletManager: Storage error:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    /**
     * Get credentials from the unified wallet
     */
    async getCredentials(packageType) {
        try {
            const wallet = await this.getWallet();
            return await wallet.getCredentials(packageType);
        } catch (error) {
            console.error('❌ LemmaWalletManager: Get credentials error:', error);
            return [];
        }
    }
    
    /**
     * Broadcast credential updates to other tabs/windows
     */
    broadcastCredentialUpdate(credential) {
        try {
            // Use BroadcastChannel if available
            if (typeof BroadcastChannel !== 'undefined') {
                const channel = new BroadcastChannel('lemma_wallet_updates');
                channel.postMessage({
                    type: 'credential_added',
                    credential: credential,
                    timestamp: Date.now()
                });
            }
            
            // Also use localStorage event for broader compatibility
            const updateEvent = {
                type: 'credential_update',
                credential: credential,
                timestamp: Date.now()
            };
            
            localStorage.setItem('lemma_wallet_update_event', JSON.stringify(updateEvent));
            
            // Clear the event after a moment to trigger storage event
            setTimeout(() => {
                localStorage.removeItem('lemma_wallet_update_event');
            }, 100);
            
        } catch (error) {
            console.warn('⚠️ LemmaWalletManager: Broadcast error:', error);
        }
    }
    
    /**
     * Listen for credential updates from other tabs/windows
     */
    setupCrossBrowserSync() {
        try {
            // BroadcastChannel listener
            if (typeof BroadcastChannel !== 'undefined') {
                const channel = new BroadcastChannel('lemma_wallet_updates');
                channel.addEventListener('message', (event) => {
                    if (event.data.type === 'credential_added') {
                        console.log('📡 LemmaWalletManager: Received credential update from another tab');
                        this.handleCredentialUpdate(event.data.credential);
                    }
                });
            }
            
            // Storage event listener
            window.addEventListener('storage', (event) => {
                if (event.key === 'lemma_wallet_update_event' && event.newValue) {
                    try {
                        const updateData = JSON.parse(event.newValue);
                        if (updateData.type === 'credential_update') {
                            console.log('📡 LemmaWalletManager: Received credential update via storage event');
                            this.handleCredentialUpdate(updateData.credential);
                        }
                    } catch (error) {
                        console.warn('⚠️ LemmaWalletManager: Storage event parsing error:', error);
                    }
                }
            });
            
        } catch (error) {
            console.warn('⚠️ LemmaWalletManager: Cross-browser sync setup error:', error);
        }
    }
    
    /**
     * Handle credential updates from other tabs/windows
     */
    async handleCredentialUpdate(credential) {
        try {
            if (this.walletInstance && this.walletInstance.isReady) {
                // Check if we need to update our local wallet
                const existingCredentials = await this.walletInstance.getCredentials(credential.packageType || 'permission');
                const exists = existingCredentials.some(cred => cred.id === credential.id);
                
                if (!exists) {
                    console.log('🔄 LemmaWalletManager: Adding credential from cross-browser sync');
                    await this.walletInstance.storeCredential(credential);
                }
            }
        } catch (error) {
            console.warn('⚠️ LemmaWalletManager: Handle update error:', error);
        }
    }
}

// Create global wallet manager instance
window.lemmaWalletManager = window.lemmaWalletManager || new LemmaWalletManager();

// Set up cross-browser sync on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.lemmaWalletManager.setupCrossBrowserSync();
    });
} else {
    window.lemmaWalletManager.setupCrossBrowserSync();
}

// Convenience functions for easy access
window.getLemmaWallet = () => window.lemmaWalletManager.getWallet();
window.storeLemmaCredential = (credential, options) => window.lemmaWalletManager.storeCredential(credential, options);
window.getLemmaCredentials = (packageType) => window.lemmaWalletManager.getCredentials(packageType);
