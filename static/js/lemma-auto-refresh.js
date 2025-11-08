/**
 * Lemma Automatic Credential Refresh
 * ===================================
 * 
 * Automatically refreshes credentials before they expire
 * to prevent user lockouts.
 * 
 * Features:
 * - Background monitoring of credential expiry
 * - Automatic refresh when < 7 days remaining
 * - Seamless wallet update (no user action)
 * - Retry logic for failures
 * - Works across tabs (localStorage sync)
 */

class LemmaAutoRefresh {
    constructor(config = {}) {
        this.config = {
            checkInterval: config.checkInterval || 60 * 60 * 1000,  // Check every hour
            refreshThreshold: config.refreshThreshold || 7,  // Refresh if < 7 days
            earlyRefreshThreshold: config.earlyRefreshThreshold || 30,  // Allow refresh if < 30 days
            retryAttempts: config.retryAttempts || 3,
            retryDelay: config.retryDelay || 5000,  // 5 seconds
            debug: config.debug || false
        };
        
        this.isRunning = false;
        this.checkTimer = null;
        this.refreshInProgress = new Set();  // Track which credentials are being refreshed
        
        this.log('Auto-refresh initialized', this.config);
    }
    
    /**
     * Start automatic refresh monitoring
     */
    start() {
        if (this.isRunning) {
            this.log('Auto-refresh already running');
            return;
        }
        
        this.isRunning = true;
        this.log('Starting auto-refresh monitoring');
        
        // Check immediately on start
        this.checkAndRefresh();
        
        // Then check periodically
        this.checkTimer = setInterval(() => {
            this.checkAndRefresh();
        }, this.config.checkInterval);
        
        // Listen for storage changes from other tabs
        window.addEventListener('storage', (e) => {
            if (e.key === 'lemma_credentials' && e.newValue) {
                this.log('Credentials updated in another tab, rechecking...');
                this.checkAndRefresh();
            }
        });
    }
    
    /**
     * Stop automatic refresh monitoring
     */
    stop() {
        if (!this.isRunning) return;
        
        this.isRunning = false;
        
        if (this.checkTimer) {
            clearInterval(this.checkTimer);
            this.checkTimer = null;
        }
        
        this.log('Auto-refresh monitoring stopped');
    }
    
    /**
     * Check credentials and refresh if needed
     */
    async checkAndRefresh() {
        try {
            const credentials = this.getCredentials();
            
            if (!credentials || credentials.length === 0) {
                this.log('No credentials found');
                return;
            }
            
            this.log(`Checking ${credentials.length} credential(s) for refresh eligibility`);
            
            // Check each credential
            for (const credential of credentials) {
                await this.checkSingleCredential(credential);
            }
            
        } catch (error) {
            console.error('Auto-refresh check error:', error);
        }
    }
    
    /**
     * Check a single credential and refresh if needed
     */
    async checkSingleCredential(credential) {
        const credentialId = credential.id;
        
        // Skip if already refreshing
        if (this.refreshInProgress.has(credentialId)) {
            this.log(`Refresh already in progress for ${credentialId}`);
            return;
        }
        
        const claims = credential.credentialSubject || credential.claims || {};
        const expiresAt = claims.expiresAt;
        
        if (!expiresAt) {
            this.log(`Credential ${credentialId} has no expiry - skip`);
            return;
        }
        
        // Calculate time until expiry
        const expiryTime = typeof expiresAt === 'number' ? expiresAt : parseInt(expiresAt);
        const now = Math.floor(Date.now() / 1000);
        const timeUntilExpiry = expiryTime - now;
        const daysUntilExpiry = timeUntilExpiry / (24 * 60 * 60);
        
        this.log(`Credential ${credentialId} expires in ${daysUntilExpiry.toFixed(1)} days`);
        
        // Check if refresh needed
        if (daysUntilExpiry < 0) {
            console.warn(`Credential ${credentialId} has EXPIRED - user needs to re-authenticate`);
            this.notifyExpired(credential);
            return;
        }
        
        if (daysUntilExpiry < this.config.refreshThreshold) {
            this.log(`Credential ${credentialId} needs refresh (< ${this.config.refreshThreshold} days)`);
            await this.refreshCredential(credential);
        } else if (daysUntilExpiry < this.config.earlyRefreshThreshold) {
            this.log(`Credential ${credentialId} eligible for early refresh (< ${this.config.earlyRefreshThreshold} days)`);
            // Optionally refresh early (less urgent)
            // await this.refreshCredential(credential);
        } else {
            this.log(`Credential ${credentialId} OK - ${daysUntilExpiry.toFixed(0)} days remaining`);
        }
    }
    
    /**
     * Refresh a credential
     */
    async refreshCredential(credential, attempt = 1) {
        const credentialId = credential.id;
        
        // Mark as in progress
        this.refreshInProgress.add(credentialId);
        
        try {
            this.log(`🔄 Refreshing credential ${credentialId} (attempt ${attempt}/${this.config.retryAttempts})`);
            
            // Extract site_id for permission credentials
            const claims = credential.credentialSubject || credential.claims || {};
            const siteId = claims.siteId;
            const packageType = claims.packageType;
            
            // Call refresh API
            const response = await fetch('/api/credentials/refresh', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    credential: credential,
                    site_id: siteId
                })
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                this.log(`✅ Credential refreshed successfully`);
                this.log(`   Old ID: ${credentialId}`);
                this.log(`   New ID: ${result.credential.id}`);
                
                // Replace credential in wallet
                this.replaceCredential(credential, result.credential);
                
                // Notify success
                this.notifyRefreshed(credential, result.credential);
                
                return true;
            } else {
                console.error('Refresh failed:', result.error);
                
                // Retry if we have attempts left
                if (attempt < this.config.retryAttempts) {
                    this.log(`Retrying in ${this.config.retryDelay}ms...`);
                    await this.sleep(this.config.retryDelay);
                    return await this.refreshCredential(credential, attempt + 1);
                } else {
                    console.error(`Failed to refresh credential after ${this.config.retryAttempts} attempts`);
                    this.notifyRefreshFailed(credential, result.error);
                    return false;
                }
            }
            
        } catch (error) {
            console.error('Refresh error:', error);
            
            // Retry if we have attempts left
            if (attempt < this.config.retryAttempts) {
                this.log(`Retrying in ${this.config.retryDelay}ms...`);
                await this.sleep(this.config.retryDelay);
                return await this.refreshCredential(credential, attempt + 1);
            } else {
                this.notifyRefreshFailed(credential, error.message);
                return false;
            }
            
        } finally {
            // Remove from in-progress
            this.refreshInProgress.delete(credentialId);
        }
    }
    
    /**
     * Replace credential in wallet
     */
    replaceCredential(oldCredential, newCredential) {
        try {
            const credentials = this.getCredentials();
            
            // Find and replace
            const index = credentials.findIndex(c => c.id === oldCredential.id);
            
            if (index !== -1) {
                credentials[index] = newCredential;
                localStorage.setItem('lemma_credentials', JSON.stringify(credentials));
                this.log(`✅ Credential replaced in wallet`);
                
                // Trigger storage event for other tabs
                window.dispatchEvent(new StorageEvent('storage', {
                    key: 'lemma_credentials',
                    newValue: JSON.stringify(credentials),
                    url: window.location.href
                }));
            } else {
                console.warn('Old credential not found in wallet');
            }
            
        } catch (error) {
            console.error('Error replacing credential:', error);
        }
    }
    
    /**
     * Get credentials from wallet
     */
    getCredentials() {
        try {
            const credentialsJson = localStorage.getItem('lemma_credentials');
            if (!credentialsJson) return [];
            
            const credentials = JSON.parse(credentialsJson);
            return Array.isArray(credentials) ? credentials : [credentials];
        } catch (error) {
            console.error('Error reading credentials:', error);
            return [];
        }
    }
    
    /**
     * Notify that credential was refreshed
     */
    notifyRefreshed(oldCredential, newCredential) {
        // Dispatch custom event
        window.dispatchEvent(new CustomEvent('lemma:credential:refreshed', {
            detail: {
                old_credential: oldCredential,
                new_credential: newCredential,
                timestamp: Date.now()
            }
        }));
        
        // Optional: Show user notification
        if (this.config.showNotifications) {
            this.showNotification(
                'Credential Refreshed',
                'Your access credential was automatically renewed'
            );
        }
    }
    
    /**
     * Notify that credential refresh failed
     */
    notifyRefreshFailed(credential, error) {
        window.dispatchEvent(new CustomEvent('lemma:credential:refresh_failed', {
            detail: {
                credential: credential,
                error: error,
                timestamp: Date.now()
            }
        }));
        
        console.error('Automatic refresh failed - user may experience issues soon');
    }
    
    /**
     * Notify that credential expired
     */
    notifyExpired(credential) {
        window.dispatchEvent(new CustomEvent('lemma:credential:expired', {
            detail: {
                credential: credential,
                timestamp: Date.now()
            }
        }));
        
        // Show warning to user
        if (this.config.showNotifications) {
            this.showNotification(
                'Credential Expired',
                'Please sign in again to restore access',
                'warning'
            );
        }
    }
    
    /**
     * Show browser notification
     */
    showNotification(title, message, type = 'info') {
        if (!('Notification' in window)) return;
        
        if (Notification.permission === 'granted') {
            new Notification(title, {
                body: message,
                icon: '/static/logo/lemma-icon.png'
            });
        }
    }
    
    /**
     * Sleep helper
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    /**
     * Debug logging
     */
    log(...args) {
        if (this.config.debug) {
            console.log('[LemmaAutoRefresh]', ...args);
        }
    }
}

// Auto-start if configured
if (typeof window !== 'undefined') {
    window.LemmaAutoRefresh = LemmaAutoRefresh;
    
    // Auto-start on page load (if credentials exist)
    window.addEventListener('DOMContentLoaded', () => {
        const autoStart = localStorage.getItem('lemma_auto_refresh_enabled');
        
        if (autoStart !== 'false') {  // Enabled by default
            const autoRefresh = new LemmaAutoRefresh({
                debug: false,  // Set to true for debugging
                checkInterval: 60 * 60 * 1000,  // Check every hour
                refreshThreshold: 7,  // Refresh if < 7 days
                showNotifications: false  // Don't show notifications by default
            });
            
            autoRefresh.start();
            
            // Store reference globally
            window.lemmaAutoRefresh = autoRefresh;
            
            console.log('[Lemma] Auto-refresh monitoring started');
        }
    });
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaAutoRefresh;
}



