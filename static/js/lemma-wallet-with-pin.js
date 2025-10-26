/**
 * Lemma Wallet with PIN Integration
 * Extends the existing encrypted wallet with optional PIN protection
 * 
 * Usage:
 *   const wallet = new LemmaWalletWithPIN({ usePIN: true });
 *   await wallet.init();
 */

class LemmaWalletWithPIN {
    constructor(config = {}) {
        this.usePIN = config.usePIN !== false;  // Default: true
        this.autoSetupPIN = config.autoSetupPIN !== false;  // Prompt for PIN on first use
        
        // Initialize PIN manager
        this.pinManager = new LemmaWalletPIN({
            pinLength: 4,
            autoLockMinutes: 15,
            maxAttempts: 3,
            lockoutMinutes: 30
        });
        
        // Initialize PIN UI
        this.pinUI = new LemmaPINUI(this.pinManager);
        
        console.log(`🔐 Wallet initialized with PIN ${this.usePIN ? 'enabled' : 'disabled'}`);
    }
    
    /**
     * Initialize wallet
     */
    async init() {
        // Check if PIN is set up
        const pinSetup = this.pinManager.isPINSetup();
        
        if (this.usePIN && !pinSetup && this.autoSetupPIN) {
            // First time - prompt for PIN setup
            console.log('📝 First time wallet access - setting up PIN');
            try {
                await this.pinUI.showPINSetup({ allowSkip: false });
                console.log('✅ PIN setup complete');
            } catch (error) {
                console.error('❌ PIN setup failed:', error);
                throw error;
            }
        } else if (this.usePIN && pinSetup) {
            // PIN exists - unlock wallet
            console.log('🔒 Wallet is locked - prompting for PIN');
            try {
                await this.pinUI.showPINEntry('Enter your PIN to access your wallet');
                console.log('✅ Wallet unlocked');
            } catch (error) {
                console.error('❌ Failed to unlock wallet:', error);
                throw error;
            }
        }
        
        return true;
    }
    
    /**
     * Store credential (auto-encrypts with PIN if enabled)
     */
    async storeCredential(credential) {
        if (this.usePIN && this.pinManager.isLocked) {
            // Wallet locked - need PIN
            await this.pinUI.showPINEntry('Enter PIN to store credential');
        }
        
        // Get current credentials
        const credentials = await this.getCredentials();
        
        // Add new credential
        credentials.push({
            ...credential,
            storedAt: new Date().toISOString(),
            id: credential.id || this.generateCredentialId()
        });
        
        // Save (auto-encrypts if PIN enabled)
        if (this.usePIN) {
            await this.pinManager.saveWallet(credentials);
        } else {
            // Fallback to standard encrypted storage
            localStorage.setItem('lemma_wallet_credentials', JSON.stringify(credentials));
        }
        
        console.log('✅ Credential stored securely');
        return true;
    }
    
    /**
     * Get all credentials (decrypts with PIN if needed)
     */
    async getCredentials(type = null) {
        if (this.usePIN && this.pinManager.isLocked) {
            // Wallet locked - need PIN
            await this.pinUI.showPINEntry('Enter PIN to access credentials');
        }
        
        let credentials;
        
        if (this.usePIN && !this.pinManager.isLocked) {
            // Get from PIN-encrypted wallet
            const encryptedWallet = localStorage.getItem('lemma_wallet_encrypted');
            if (!encryptedWallet) {
                credentials = [];
            } else {
                // Already unlocked, decrypt
                const walletData = JSON.parse(encryptedWallet);
                const iv = this.pinManager.base64ToArrayBuffer(walletData.iv);
                const encryptedData = this.pinManager.base64ToArrayBuffer(walletData.data);
                
                const decrypted = await crypto.subtle.decrypt(
                    { name: 'AES-GCM', iv: iv },
                    this.pinManager.currentKey,
                    encryptedData
                );
                
                credentials = JSON.parse(new TextDecoder().decode(decrypted));
            }
        } else {
            // Get from standard storage
            const stored = localStorage.getItem('lemma_wallet_credentials');
            credentials = stored ? JSON.parse(stored) : [];
        }
        
        // Filter by type if requested
        if (type) {
            credentials = credentials.filter(cred => 
                cred.claims?.packageType === type
            );
        }
        
        return credentials;
    }
    
    /**
     * Lock wallet (clear key from memory)
     */
    lock() {
        if (this.usePIN) {
            this.pinManager.lock();
            console.log('🔒 Wallet locked');
        }
    }
    
    /**
     * Check if wallet is locked
     */
    isLocked() {
        if (!this.usePIN) return false;
        return this.pinManager.isLocked;
    }
    
    /**
     * Get credential count without unlocking
     */
    getCredentialCount() {
        const encryptedWallet = localStorage.getItem('lemma_wallet_encrypted');
        if (!encryptedWallet) {
            // Try standard storage
            const stored = localStorage.getItem('lemma_wallet_credentials');
            return stored ? JSON.parse(stored).length : 0;
        }
        
        // Can't count without decrypting, return "locked" indicator
        return '🔒';
    }
    
    /**
     * Generate credential ID
     */
    generateCredentialId() {
        return 'cred_' + Array.from(crypto.getRandomValues(new Uint8Array(16)))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }
}

// Integration with existing encrypted wallet
if (typeof window !== 'undefined') {
    window.LemmaWalletWithPIN = LemmaWalletWithPIN;
    
    // Auto-initialize if configured
    document.addEventListener('DOMContentLoaded', async () => {
        // Check if site wants PIN protection
        const usePIN = window.LEMMA_USE_PIN !== false;  // Default true
        
        if (usePIN && typeof LemmaWalletPIN !== 'undefined') {
            console.log('🔐 PIN protection enabled for wallet');
            
            // Replace global wallet with PIN-protected version if exists
            if (window.lemmaWallet && !window.lemmaWallet.pinProtected) {
                const pinWallet = new LemmaWalletWithPIN({ usePIN: true });
                
                // Mark as PIN-protected to avoid double initialization
                pinWallet.pinProtected = true;
                
                // Optionally replace global wallet
                // window.lemmaWallet = pinWallet;
            }
        }
    });
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaWalletWithPIN;
}

