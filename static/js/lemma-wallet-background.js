/**
 * Lemma Background Wallet - Silent Operation
 * Minimal wallet that operates entirely in the background without UI
 */

class LemmaBackgroundWallet {
    constructor() {
        this.dbName = 'lemma_wallet_bg';
        this.dbVersion = 1;
        this.credentialStore = 'credentials';
        this.initialized = false;
        this.db = null;
        
        // Initialize immediately
        this.init();
    }
    
    /**
     * Initialize the wallet database silently
     */
    async init() {
        if (this.initialized) return Promise.resolve();
        
        try {
            this.db = await this.openDatabase();
            this.initialized = true;
            return Promise.resolve();
        } catch (error) {
            console.error('Background wallet initialization failed:', error);
            return Promise.reject(error);
        }
    }
    
    /**
     * Open IndexedDB database
     */
    openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(this.credentialStore)) {
                    db.createObjectStore(this.credentialStore, { keyPath: 'id' });
                }
            };
        });
    }
    
    /**
     * Store credential silently
     */
    async storeCredential(credential) {
        await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.credentialStore], 'readwrite');
            const store = transaction.objectStore(this.credentialStore);
            
            const credentialWithId = {
                id: credential.id || this.generateId(),
                credential: credential,
                timestamp: Date.now()
            };
            
            const request = store.put(credentialWithId);
            request.onsuccess = () => resolve(credentialWithId);
            request.onerror = () => reject(request.error);
        });
    }
    
    /**
     * Get credentials silently
     */
    async getCredentials() {
        await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.credentialStore], 'readonly');
            const store = transaction.objectStore(this.credentialStore);
            const request = store.getAll();
            
            request.onsuccess = () => {
                const credentials = request.result.map(item => item.credential);
                resolve(credentials);
            };
            request.onerror = () => reject(request.error);
        });
    }
    
    /**
     * Background verification - no UI, just verification
     */
    async verifyInBackground(domain = window.location.hostname) {
        try {
            const credentials = await this.getCredentials();
            if (!credentials || credentials.length === 0) {
                return { verified: false, reason: 'no_credentials' };
            }
            
            // Get challenge
            const challengeResponse = await fetch('/api/generate-challenge');
            const { challenge } = await challengeResponse.json();
            
            // Create presentation
            const presentation = {
                credential: credentials[0],
                challenge: challenge,
                domain: domain
            };
            
            // Verify with server
            const verifyResponse = await fetch('/api/verify-human', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': await this.getCSRFToken()
                },
                body: JSON.stringify({ presentation })
            });
            
            const result = await verifyResponse.json();
            return {
                verified: result.success || false,
                reason: result.verified ? 'success' : 'verification_failed'
            };
            
        } catch (error) {
            return { verified: false, reason: 'error', error: error.message };
        }
    }
    
    /**
     * Get CSRF token
     */
    async getCSRFToken() {
        try {
            const response = await fetch('/api/generate-csrf-token');
            const data = await response.json();
            return data.csrf_token;
        } catch (error) {
            return null;
        }
    }
    
    /**
     * Generate unique ID
     */
    generateId() {
        return 'cred_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    /**
     * Remove credential (for shield widget compatibility)
     */
    async removeCredential(credentialId) {
        await this.init();
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.credentialStore], 'readwrite');
            const store = transaction.objectStore(this.credentialStore);
            
            const request = store.delete(credentialId);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }
    
    /**
     * Get all credentials (alias for getCredentials for compatibility)
     */
    async getAllCredentials() {
        return await this.getCredentials();
    }
    
    /**
     * Get first credential (for compatibility)
     */
    async getFirstCredential() {
        const credentials = await this.getCredentials();
        return credentials && credentials.length > 0 ? credentials[0] : null;
    }
    
    /**
     * Check verification status (compatibility method)
     */
    async checkVerification(userId) {
        const hasCredentials = await this.hasValidCredentials();
        return {
            verified: hasCredentials,
            reason: hasCredentials ? 'credentials_found' : 'no_credentials'
        };
    }
    
    /**
     * Start verification (compatibility method - redirect to verification flow)
     */
    async startVerification(userId, options = {}) {
        // For background wallet, we just return instructions to show the shield
        return {
            action: 'show_shield',
            message: 'Please complete verification through the shield interface'
        };
    }
    
    /**
     * Check if user has valid credentials
     */
    async hasValidCredentials() {
        const credentials = await this.getCredentials();
        return credentials && credentials.length > 0;
    }
}

/**
 * Background Verification Manager
 * Handles automatic verification without user interaction
 */
class BackgroundVerificationManager {
    constructor() {
        this.wallet = new LemmaBackgroundWallet();
        this.verificationCallbacks = [];
        this.autoVerifyEnabled = true;
    }
    
    /**
     * Add verification callback
     */
    onVerification(callback) {
        this.verificationCallbacks.push(callback);
    }
    
    /**
     * Perform background verification
     */
    async performVerification() {
        if (!this.autoVerifyEnabled) return;
        
        const result = await this.wallet.verifyInBackground();
        
        // Notify all callbacks
        this.verificationCallbacks.forEach(callback => {
            try {
                callback(result);
            } catch (error) {
                console.error('Verification callback error:', error);
            }
        });
        
        return result;
    }
    
    /**
     * Auto-verify when page loads
     */
    async autoVerify() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.performVerification());
        } else {
            await this.performVerification();
        }
    }
    
    /**
     * Enable/disable auto verification
     */
    setAutoVerify(enabled) {
        this.autoVerifyEnabled = enabled;
    }
}

// Initialize background wallet automatically
window.lemmaBackgroundWallet = new LemmaBackgroundWallet();
window.lemmaBackgroundVerifier = new BackgroundVerificationManager();

// For compatibility with existing code expecting lemmaWallet
if (!window.lemmaWallet) {
    window.lemmaWallet = window.lemmaBackgroundWallet;
    console.log('🎯 Background wallet set as primary lemmaWallet instance');
}

// Prevent old wallet initialization by marking as already initialized
window.lemmaWalletInitialized = true;
document.cookie = "lemma_wallet_enabled=false; max-age=31536000; path=/; samesite=Lax";

// Auto-verify on page load
document.addEventListener('DOMContentLoaded', () => {
    window.lemmaBackgroundVerifier.autoVerify();
});

// Export for external use
window.LemmaBackgroundWallet = LemmaBackgroundWallet;
window.BackgroundVerificationManager = BackgroundVerificationManager; 