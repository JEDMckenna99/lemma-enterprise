/**
 * Lemma Wallet PIN Protection
 * Client-side PIN encryption/decryption for wallet security
 * 4-digit PIN provides knowledge factor for multi-factor authentication
 */

class LemmaWalletPIN {
    constructor(config = {}) {
        this.pinLength = config.pinLength || 4;
        this.autoLockMinutes = config.autoLockMinutes || 15;
        this.maxAttempts = config.maxAttempts || 3;
        this.lockoutMinutes = config.lockoutMinutes || 30;
        
        this.isLocked = true;
        this.failedAttempts = 0;
        this.lastActivity = Date.now();
        this.autoLockTimer = null;
        
        // Start auto-lock monitoring
        this.startAutoLock();
    }
    
    /**
     * Generate encryption key from PIN + browser fingerprint
     */
    async deriveKeyFromPIN(pin, salt) {
        // Get browser fingerprint for device binding
        const fingerprint = await this.getBrowserFingerprint();
        
        // Combine PIN + fingerprint
        const pinData = new TextEncoder().encode(pin + fingerprint);
        
        // Import as key material
        const keyMaterial = await crypto.subtle.importKey(
            'raw',
            pinData,
            'PBKDF2',
            false,
            ['deriveKey']
        );
        
        // Derive AES-256-GCM key
        const key = await crypto.subtle.deriveKey(
            {
                name: 'PBKDF2',
                salt: salt,
                iterations: 100000,  // Slow brute-force attacks
                hash: 'SHA-256'
            },
            keyMaterial,
            { name: 'AES-GCM', length: 256 },
            false,
            ['encrypt', 'decrypt']
        );
        
        return key;
    }
    
    /**
     * Get browser fingerprint for device binding
     */
    async getBrowserFingerprint() {
        const components = [
            navigator.userAgent,
            navigator.language,
            screen.width + 'x' + screen.height,
            screen.colorDepth,
            new Date().getTimezoneOffset(),
            !!window.sessionStorage,
            !!window.localStorage
        ];
        
        const fingerprint = components.join('|');
        const encoded = new TextEncoder().encode(fingerprint);
        const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        
        return hashHex.substring(0, 32);  // Use first 32 chars
    }
    
    /**
     * Setup PIN (first time)
     */
    async setupPIN(pin) {
        // Validate PIN
        if (!this.validatePIN(pin)) {
            throw new Error(`PIN must be exactly ${this.pinLength} digits`);
        }
        
        // Generate random salt
        const salt = crypto.getRandomValues(new Uint8Array(32));
        
        // Store salt (not secret, can be public)
        const saltBase64 = this.arrayBufferToBase64(salt);
        localStorage.setItem('lemma_wallet_salt', saltBase64);
        
        // Create PIN hash for verification (doesn't encrypt anything, just verifies PIN)
        const pinHash = await this.hashPIN(pin, salt);
        localStorage.setItem('lemma_wallet_pin_hash', pinHash);
        
        // Store key reference (for session)
        this.currentKey = null;  // Not needed for hash-based verification
        this.isLocked = false;
        this.failedAttempts = 0;
        
        console.log('✅ PIN setup complete (hash-based verification)');
        return true;
    }
    
    /**
     * Hash PIN for verification (doesn't encrypt data)
     */
    async hashPIN(pin, salt) {
        const fingerprint = await this.getBrowserFingerprint();
        const pinData = new TextEncoder().encode(pin + fingerprint);
        const saltArray = salt instanceof Uint8Array ? salt : this.base64ToArrayBuffer(salt);
        
        // Combine PIN data and salt
        const combined = new Uint8Array(pinData.length + saltArray.length);
        combined.set(pinData);
        combined.set(saltArray, pinData.length);
        
        // SHA-256 hash
        const hashBuffer = await crypto.subtle.digest('SHA-256', combined);
        return this.arrayBufferToBase64(hashBuffer);
    }
    
    /**
     * Unlock wallet with PIN (hash-based verification, doesn't decrypt anything)
     */
    async unlock(pin) {
        // Check if locked out
        if (this.isLockedOut()) {
            const remainingMinutes = this.getLockoutRemainingMinutes();
            throw new Error(`Too many failed attempts. Try again in ${remainingMinutes} minutes.`);
        }
        
        // Validate PIN format
        if (!this.validatePIN(pin)) {
            throw new Error(`PIN must be exactly ${this.pinLength} digits`);
        }
        
        // Get salt
        const saltBase64 = localStorage.getItem('lemma_wallet_salt');
        if (!saltBase64) {
            throw new Error('PIN not set up. Please set up PIN first.');
        }
        
        // Get stored PIN hash
        const storedHash = localStorage.getItem('lemma_wallet_pin_hash');
        if (!storedHash) {
            throw new Error('PIN hash not found. Please set up PIN again.');
        }
        
        const salt = this.base64ToArrayBuffer(saltBase64);
        
        // Hash the entered PIN
        const enteredHash = await this.hashPIN(pin, salt);
        
        // Compare hashes
        if (enteredHash === storedHash) {
            // CORRECT PIN ✅
            this.isLocked = false;
            this.failedAttempts = 0;
            this.updateActivity();
            
            console.log('✅ PIN verified successfully');
            return [];  // Don't return credentials (they're in IndexedDB, not localStorage)
            
        } else {
            // WRONG PIN ❌
            this.failedAttempts++;
            
            if (this.failedAttempts >= this.maxAttempts) {
                this.lockout();
                throw new Error(`Too many failed attempts. Locked for ${this.lockoutMinutes} minutes.`);
            }
            
            throw new Error(`Incorrect PIN. ${this.maxAttempts - this.failedAttempts} attempts remaining.`);
        }
    }
    
    /**
     * Save wallet (encrypt with current key)
     */
    async saveWallet(credentials) {
        if (this.isLocked || !this.currentKey) {
            throw new Error('Wallet is locked. Unlock with PIN first.');
        }
        
        // Serialize credentials
        const credentialsJson = JSON.stringify(credentials);
        const data = new TextEncoder().encode(credentialsJson);
        
        // Generate random IV
        const iv = crypto.getRandomValues(new Uint8Array(12));
        
        // Encrypt
        const encrypted = await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv: iv },
            this.currentKey,
            data
        );
        
        // Store encrypted wallet
        const walletData = {
            iv: this.arrayBufferToBase64(iv),
            data: this.arrayBufferToBase64(encrypted),
            timestamp: Date.now()
        };
        
        localStorage.setItem('lemma_wallet_encrypted', JSON.stringify(walletData));
        this.updateActivity();
        
        return true;
    }
    
    /**
     * Lock wallet
     */
    lock() {
        this.currentKey = null;
        this.isLocked = true;
        console.log('🔒 Wallet locked');
    }
    
    /**
     * Change PIN
     */
    async changePIN(oldPIN, newPIN) {
        // Unlock with old PIN
        const credentials = await this.unlock(oldPIN);
        
        // Setup new PIN
        await this.setupPIN(newPIN);
        
        // Re-encrypt wallet with new PIN
        await this.saveWallet(credentials);
        
        console.log('✅ PIN changed successfully');
        return true;
    }
    
    /**
     * Validate PIN format
     */
    validatePIN(pin) {
        const pinStr = String(pin);
        return pinStr.length === this.pinLength && /^\d+$/.test(pinStr);
    }
    
    /**
     * Check if locked out due to failed attempts
     */
    isLockedOut() {
        const lockoutUntil = localStorage.getItem('lemma_pin_lockout_until');
        if (!lockoutUntil) return false;
        
        const lockoutTime = parseInt(lockoutUntil);
        if (Date.now() < lockoutTime) {
            return true;
        }
        
        // Lockout expired
        localStorage.removeItem('lemma_pin_lockout_until');
        this.failedAttempts = 0;
        return false;
    }
    
    /**
     * Lockout after too many failed attempts
     */
    lockout() {
        const lockoutUntil = Date.now() + (this.lockoutMinutes * 60 * 1000);
        localStorage.setItem('lemma_pin_lockout_until', lockoutUntil.toString());
        console.log(`🚫 Locked out for ${this.lockoutMinutes} minutes`);
    }
    
    /**
     * Get remaining lockout time in minutes
     */
    getLockoutRemainingMinutes() {
        const lockoutUntil = localStorage.getItem('lemma_pin_lockout_until');
        if (!lockoutUntil) return 0;
        
        const remaining = parseInt(lockoutUntil) - Date.now();
        return Math.ceil(remaining / 60000);
    }
    
    /**
     * Update last activity time
     */
    updateActivity() {
        this.lastActivity = Date.now();
    }
    
    /**
     * Start auto-lock monitoring
     */
    startAutoLock() {
        // Check every minute if should auto-lock
        this.autoLockTimer = setInterval(() => {
            if (!this.isLocked) {
                const inactiveMinutes = (Date.now() - this.lastActivity) / 60000;
                if (inactiveMinutes >= this.autoLockMinutes) {
                    this.lock();
                    console.log(`🔒 Auto-locked after ${this.autoLockMinutes} minutes of inactivity`);
                }
            }
        }, 60000);  // Check every minute
        
        // Track user activity
        ['mousedown', 'keydown', 'scroll', 'touchstart'].forEach(event => {
            document.addEventListener(event, () => {
                if (!this.isLocked) {
                    this.updateActivity();
                }
            }, { passive: true });
        });
    }
    
    /**
     * Check if PIN is set up
     */
    isPINSetup() {
        return !!localStorage.getItem('lemma_wallet_salt');
    }
    
    /**
     * Reset PIN (requires email confirmation)
     */
    async resetPIN(confirmationToken) {
        // This would be called after email confirmation
        // For now, just clear PIN and allow new setup
        localStorage.removeItem('lemma_wallet_salt');
        localStorage.removeItem('lemma_wallet_encrypted');
        localStorage.removeItem('lemma_pin_lockout_until');
        
        this.isLocked = true;
        this.failedAttempts = 0;
        
        console.log('✅ PIN reset. Please set up a new PIN.');
        return true;
    }
    
    // Helper functions
    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }
    
    base64ToArrayBuffer(base64) {
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }
}

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.LemmaWalletPIN = LemmaWalletPIN;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaWalletPIN;
}

