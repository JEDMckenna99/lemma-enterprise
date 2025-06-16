/**
 * Lemma shield API Client - Clean API-Driven Implementation
 * Enhanced with enterprise security controls and configurable protection levels
 * 
 * This client handles all shield functionality through centralized API endpoints.
 * All verification logic, session management, and security is handled server-side.
 * 
 * Perfect Flow:
 * 1. Call API to check status with security level
 * 2. If has credentials → API handles background verification automatically
 * 3. If no credentials → Show shield → Direct to verification flow
 * 4. Support for credential revocation and re-verification
 * 
 * Usage:
 * const shield = new LemmashieldAPI({
 *   protectedContent: '#protected-content',
 *   securityLevel: 'standard', // basic, standard, high, maximum
 *   onVerified: () => console.log('User verified!'),
 *   onRevoked: () => console.log('Credential revoked!'),
 *   onError: (error) => console.error('shield error:', error)
 * });
 */

class LemmashieldAPI {
    constructor(options = {}) {
        this.options = {
            // UI Elements
            protectedContent: options.protectedContent || '#protected-content',
            shieldContainer: options.shieldContainer || '#lemma-shield-overlay',
            
            // Security Configuration
            securityLevel: options.securityLevel || 'standard',
            autoCheckInterval: options.autoCheckInterval || 30000, // 30 seconds
            
            // API Configuration
            apiBase: options.apiBase || '',
            
            // Callbacks
            onVerified: options.onVerified || (() => {}),
            onRevoked: options.onRevoked || (() => {}),
            onReverificationRequired: options.onReverificationRequired || (() => {}),
            onError: options.onError || ((error) => console.error('Lemma shield Error:', error)),
            onStatusChange: options.onStatusChange || (() => {}),
            
            // Advanced Options
            enableBackgroundChecks: options.enableBackgroundChecks !== false,
            showDetailedErrors: options.showDetailedErrors || false,
            retryAttempts: options.retryAttempts || 3,
            retryDelay: options.retryDelay || 1000
        };
        
        this.state = {
            initialized: false,
            checking: false,
            verified: false,
            credentialId: null,
            securityLevel: this.options.securityLevel,
            lastCheck: 0,
            checkInterval: null,
            retryCount: 0
        };
        
        this.config = null;
        this.wallet = null;
        
        // Initialize the shield
        this.init();
    }
    
    async init() {
        try {
            console.log('🔐 Initializing Lemma shield API with security level:', this.state.securityLevel);
            
            // Load shield configuration
            await this.loadConfig();
            
            // Wait for wallet to be available
            await this.waitForWallet();
            
            // Perform initial status check
            await this.checkStatus();
            
            // Set up background checking if enabled
            if (this.options.enableBackgroundChecks) {
                this.startBackgroundChecks();
            }
            
            this.state.initialized = true;
            console.log('✅ Lemma shield API initialized successfully');
            
        } catch (error) {
            console.error('❌ Failed to initialize Lemma shield API:', error);
            this.options.onError(error);
        }
    }
    
    async loadConfig() {
        try {
            const response = await fetch(`${this.options.apiBase}/api/shield/config?security_level=${this.state.securityLevel}`);
            if (!response.ok) {
                throw new Error(`Config load failed: ${response.status}`);
            }
            
            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Failed to load configuration');
            }
            
            this.config = result.config;
            console.log('📋 shield configuration loaded:', this.config);
            
        } catch (error) {
            console.error('❌ Failed to load shield configuration:', error);
            throw error;
        }
    }
    
    async waitForWallet() {
        return new Promise((resolve, reject) => {
            let attempts = 0;
            const maxAttempts = 50; // 5 seconds max wait
            
            const checkWallet = () => {
                if (window.lemmaWallet) {
                    this.wallet = window.lemmaWallet;
                    console.log('💳 Lemma wallet found');
                    resolve();
                    return;
                }
                
                attempts++;
                if (attempts >= maxAttempts) {
                    console.log('⚠️ Wallet not available after waiting');
                    reject(new Error('Wallet not available'));
                    return;
                }
                
                setTimeout(checkWallet, 100);
            };
            
            checkWallet();
        });
    }
    
    async checkStatus() {
        if (this.state.checking) {
            return;
        }
        
        this.state.checking = true;
        this.state.lastCheck = Date.now();
        
        try {
            const response = await fetch(`${this.options.apiBase}/api/shield/status?security_level=${this.state.securityLevel}`, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error(`Status check failed: ${response.status}`);
            }
            
            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Status check failed');
            }
            
            await this.handleStatusResult(result);
            
        } catch (error) {
            console.error('❌ Status check error:', error);
            await this.handleError(error);
        } finally {
            this.state.checking = false;
        }
    }
    
    async handleStatusResult(result) {
        const { shield_action, data, message } = result;
        
        console.log(`🔍 shield status: ${shield_action}`, data);
        
        switch (shield_action) {
            case 'allow_access':
                await this.handleAllowAccess(data);
                break;
                
            case 'check_credentials':
                await this.handleCheckCredentials(data);
                break;
                
            case 'verify_did':
                await this.handleVerifyDID(data);
                break;
                
            case 'check_revocation':
                await this.handleCheckRevocation(data);
                break;
                
            case 'require_reverification':
                await this.handleRequireReverification(data);
                break;
                
            case 'credential_revoked':
                await this.handleCredentialRevoked(data);
                break;
                
            default:
                console.warn('⚠️ Unknown shield action:', shield_action);
                await this.showshield();
        }
        
        this.options.onStatusChange(shield_action, data);
    }
    
    async handleAllowAccess(data) {
        this.state.verified = true;
        this.state.credentialId = data.credential_id;
        
        console.log('✅ Access allowed - user verified');
        this.hideshield();
        this.showProtectedContent();
        this.options.onVerified(data);
    }
    
    async handleCheckCredentials(data) {
        console.log('🔍 Checking user credentials...');
        
        if (!this.wallet) {
            console.log('❌ No wallet available - showing shield');
            await this.showshield();
            return;
        }
        
        try {
            const credentials = await this.wallet.getCredentials();
            if (!credentials || credentials.length === 0) {
                console.log('❌ No credentials found - showing shield');
                await this.showshield();
                return;
            }
            
            // Verify credentials with the API
            await this.verifyCredentials(credentials);
            
        } catch (error) {
            console.error('❌ Credential check failed:', error);
            await this.showshield();
        }
    }
    
    async handleVerifyDID(data) {
        console.log('🔍 DID verification required...');
        
        try {
            const credentials = await this.wallet.getCredentials();
            if (!credentials || credentials.length === 0) {
                await this.showshield();
                return;
            }
            
            // Perform background DID verification
            await this.verifyCredentials(credentials, { background_did_check: true });
            
        } catch (error) {
            console.error('❌ DID verification failed:', error);
            await this.handleRequireReverification(data);
        }
    }
    
    async handleCheckRevocation(data) {
        console.log('🔍 Revocation check required...');
        
        try {
            const credentials = await this.wallet.getCredentials();
            if (!credentials || credentials.length === 0) {
                await this.showshield();
                return;
            }
            
            // Perform background revocation check
            await this.verifyCredentials(credentials, { background_revocation_check: true });
            
        } catch (error) {
            console.error('❌ Revocation check failed:', error);
            await this.handleRequireReverification(data);
        }
    }
    
    async handleRequireReverification(data) {
        console.log('⚠️ Re-verification required:', data.reason);
        
        this.state.verified = false;
        this.hideProtectedContent();
        
        // Show re-verification shield
        await this.showshield({
            title: 'Re-verification Required',
            message: `Your verification has expired. Please verify again to continue.`,
            reason: data.reason,
            isReverification: true
        });
        
        this.options.onReverificationRequired(data);
    }
    
    async handleCredentialRevoked(data) {
        console.log('❌ Credential has been revoked:', data.revocation_reason);
        
        this.state.verified = false;
        this.state.credentialId = null;
        
        // Clear revoked credential from wallet
        if (this.wallet && data.credential_id) {
            try {
                await this.wallet.removeCredential(data.credential_id);
            } catch (error) {
                console.error('Failed to remove revoked credential:', error);
            }
        }
        
        this.hideProtectedContent();
        
        // Show revocation notice
        await this.showshield({
            title: 'Credential Revoked',
            message: `Your verification credential has been revoked: ${data.revocation_reason}`,
            reason: data.revocation_reason,
            isRevoked: true
        });
        
        this.options.onRevoked(data);
    }
    
    async verifyCredentials(credentials, options = {}) {
        try {
            // Generate challenge
            const challengeResponse = await fetch(`${this.options.apiBase}/api/shield/challenge`, {
                method: 'GET',
                credentials: 'same-origin'
            });
            
            if (!challengeResponse.ok) {
                throw new Error('Failed to generate challenge');
            }
            
            const challengeResult = await challengeResponse.json();
            if (!challengeResult.success) {
                throw new Error(challengeResult.error || 'Challenge generation failed');
            }
            
            // Verify credentials with API
            const verifyResponse = await fetch(`${this.options.apiBase}/api/shield/verify-credentials`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    credentials: credentials,
                    challenge: challengeResult.challenge,
                    domain: window.location.hostname,
                    security_level: this.state.securityLevel,
                    force_reverification: options.force_reverification || false,
                    background_did_check: options.background_did_check || false,
                    background_revocation_check: options.background_revocation_check || false
                })
            });
            
            if (!verifyResponse.ok) {
                const errorResult = await verifyResponse.json();
                throw new Error(errorResult.error || 'Verification failed');
            }
            
            const result = await verifyResponse.json();
            if (!result.success) {
                throw new Error(result.error || 'Verification failed');
            }
            
            // Handle successful verification
            await this.handleAllowAccess(result.data);
            
        } catch (error) {
            console.error('❌ Credential verification failed:', error);
            throw error;
        }
    }
    
    async showshield(options = {}) {
        console.log('🚪 Showing Lemma shield');
        
        this.hideProtectedContent();
        
        const shieldContainer = document.querySelector(this.options.shieldContainer);
        if (!shieldContainer) {
            // Create shield container if it doesn't exist
            this.createshieldContainer(options);
        } else {
            // Update existing shield
            this.updateshieldContent(shieldContainer, options);
        }
        
        // Show the shield
        const shield = document.querySelector(this.options.shieldContainer);
        if (shield) {
            shield.style.display = 'flex';
            shield.classList.add('lemma-shield-visible');
        }
    }
    
    createshieldContainer(options = {}) {
        const shield = document.createElement('div');
        shield.id = this.options.shieldContainer.replace('#', '');
        shield.className = 'lemma-shield-overlay';
        
        const title = options.title || 'Human Verification Required';
        const message = options.message || 'Please verify that you are human to access this content.';
        const isReverification = options.isReverification || false;
        const isRevoked = options.isRevoked || false;
        
        shield.innerHTML = `
            <div class="lemma-shield-modal">
                <div class="lemma-shield-header">
                    <h2>${title}</h2>
                    ${isRevoked ? '<div class="lemma-shield-status revoked">Credential Revoked</div>' : ''}
                    ${isReverification ? '<div class="lemma-shield-status reverify">Re-verification Required</div>' : ''}
                </div>
                <div class="lemma-shield-content">
                    <p>${message}</p>
                    <div class="lemma-shield-security-info">
                        <strong>Security Level:</strong> ${this.state.securityLevel.toUpperCase()}
                        ${this.config ? `<br><small>Session timeout: ${Math.round(this.config.settings.session_timeout / 3600)}h</small>` : ''}
                    </div>
                </div>
                <div class="lemma-shield-actions">
                    ${isRevoked ? 
                        '<button class="lemma-shield-btn primary" onclick="window.location.reload()">Get New Verification</button>' :
                        '<button class="lemma-shield-btn primary" id="lemma-verify-btn">Verify Human</button>'
                    }
                    <button class="lemma-shield-btn secondary" id="lemma-shield-close">Close</button>
                </div>
            </div>
        `;
        
        // Add styles
        this.addshieldStyles();
        
        // Add event listeners
        this.addshieldEventListeners(shield, options);
        
        document.body.appendChild(shield);
    }
    
    updateshieldContent(shieldContainer, options = {}) {
        const title = options.title || 'Human Verification Required';
        const message = options.message || 'Please verify that you are human to access this content.';
        
        const header = shieldContainer.querySelector('.lemma-shield-header h2');
        const content = shieldContainer.querySelector('.lemma-shield-content p');
        
        if (header) header.textContent = title;
        if (content) content.textContent = message;
    }
    
    addshieldEventListeners(shield, options = {}) {
        const verifyBtn = shield.querySelector('#lemma-verify-btn');
        const closeBtn = shield.querySelector('#lemma-shield-close');
        
        if (verifyBtn) {
            verifyBtn.addEventListener('click', async () => {
                await this.startVerification(options);
            });
        }
        
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                this.hideshield();
            });
        }
        
        // Close on overlay click
        shield.addEventListener('click', (e) => {
            if (e.target === shield) {
                this.hideshield();
            }
        });
    }
    
    async startVerification(options = {}) {
        try {
            const response = await fetch(`${this.options.apiBase}/api/shield/start-verification`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    return_url: window.location.href,
                    security_level: this.state.securityLevel,
                    force_reverification: options.isReverification || false
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to start verification');
            }
            
            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Verification start failed');
            }
            
            // Redirect to verification
            window.location.href = result.verification_url;
            
        } catch (error) {
            console.error('❌ Failed to start verification:', error);
            this.options.onError(error);
        }
    }
    
    hideshield() {
        const shield = document.querySelector(this.options.shieldContainer);
        if (shield) {
            shield.style.display = 'none';
            shield.classList.remove('lemma-shield-visible');
        }
    }
    
    showProtectedContent() {
        const content = document.querySelector(this.options.protectedContent);
        if (content) {
            content.style.display = 'block';
            content.classList.add('lemma-content-visible');
        }
    }
    
    hideProtectedContent() {
        const content = document.querySelector(this.options.protectedContent);
        if (content) {
            content.style.display = 'none';
            content.classList.remove('lemma-content-visible');
        }
    }
    
    startBackgroundChecks() {
        if (this.state.checkInterval) {
            clearInterval(this.state.checkInterval);
        }
        
        this.state.checkInterval = setInterval(async () => {
            if (!this.state.checking && this.state.initialized) {
                await this.checkStatus();
            }
        }, this.options.autoCheckInterval);
        
        console.log(`🔄 Background checks started (every ${this.options.autoCheckInterval / 1000}s)`);
    }
    
    stopBackgroundChecks() {
        if (this.state.checkInterval) {
            clearInterval(this.state.checkInterval);
            this.state.checkInterval = null;
            console.log('⏹️ Background checks stopped');
        }
    }
    
    async handleError(error) {
        this.state.retryCount++;
        
        if (this.state.retryCount < this.options.retryAttempts) {
            console.log(`🔄 Retrying... (${this.state.retryCount}/${this.options.retryAttempts})`);
            setTimeout(() => {
                this.checkStatus();
            }, this.options.retryDelay * this.state.retryCount);
        } else {
            console.error('❌ Max retries reached, showing shield');
            this.state.retryCount = 0;
            await this.showshield({
                title: 'Verification Error',
                message: 'Unable to verify your status. Please try again.',
                error: this.options.showDetailedErrors ? error.message : undefined
            });
        }
        
        this.options.onError(error);
    }
    
    addshieldStyles() {
        if (document.getElementById('lemma-shield-styles')) {
            return; // Styles already added
        }
        
        const styles = document.createElement('style');
        styles.id = 'lemma-shield-styles';
        styles.textContent = `
            .lemma-shield-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.8);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            
            .lemma-shield-modal {
                background: white;
                border-radius: 12px;
                padding: 32px;
                max-width: 480px;
                width: 90%;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                text-align: center;
            }
            
            .lemma-shield-header h2 {
                margin: 0 0 16px 0;
                color: #1a1a1a;
                font-size: 24px;
                font-weight: 600;
            }
            
            .lemma-shield-status {
                display: inline-block;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                margin-bottom: 16px;
            }
            
            .lemma-shield-status.revoked {
                background: #fee;
                color: #c53030;
                border: 1px solid #fed7d7;
            }
            
            .lemma-shield-status.reverify {
                background: #fff3cd;
                color: #856404;
                border: 1px solid #ffeaa7;
            }
            
            .lemma-shield-content p {
                margin: 0 0 24px 0;
                color: #4a5568;
                font-size: 16px;
                line-height: 1.5;
            }
            
            .lemma-shield-security-info {
                background: #f7fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 16px;
                margin: 16px 0;
                font-size: 14px;
                color: #2d3748;
            }
            
            .lemma-shield-actions {
                display: flex;
                gap: 12px;
                justify-content: center;
                margin-top: 24px;
            }
            
            .lemma-shield-btn {
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                min-width: 120px;
            }
            
            .lemma-shield-btn.primary {
                background: #635bff;
                color: white;
            }
            
            .lemma-shield-btn.primary:hover {
                background: #5a52ff;
                transform: translateY(-1px);
            }
            
            .lemma-shield-btn.secondary {
                background: #f7fafc;
                color: #4a5568;
                border: 1px solid #e2e8f0;
            }
            
            .lemma-shield-btn.secondary:hover {
                background: #edf2f7;
            }
            
            @media (max-width: 640px) {
                .lemma-shield-modal {
                    padding: 24px;
                    margin: 16px;
                }
                
                .lemma-shield-actions {
                    flex-direction: column;
                }
            }
        `;
        
        document.head.appendChild(styles);
    }
    
    // Public API methods
    
    async setSecurityLevel(level) {
        if (!['basic', 'standard', 'high', 'maximum'].includes(level)) {
            throw new Error('Invalid security level');
        }
        
        this.state.securityLevel = level;
        await this.loadConfig();
        await this.checkStatus();
        
        console.log(`🔒 Security level changed to: ${level}`);
    }
    
    async forceRecheck() {
        console.log('🔄 Forcing status recheck...');
        await this.checkStatus();
    }
    
    getStatus() {
        return {
            initialized: this.state.initialized,
            verified: this.state.verified,
            credentialId: this.state.credentialId,
            securityLevel: this.state.securityLevel,
            lastCheck: this.state.lastCheck,
            config: this.config
        };
    }
    
    destroy() {
        this.stopBackgroundChecks();
        this.hideshield();
        
        // Remove shield container
        const shield = document.querySelector(this.options.shieldContainer);
        if (shield) {
            shield.remove();
        }
        
        // Remove styles
        const styles = document.getElementById('lemma-shield-styles');
        if (styles) {
            styles.remove();
        }
        
        console.log('🗑️ Lemma shield API destroyed');
    }
}

// Auto-initialize if data-lemma-shield attribute is present
document.addEventListener('DOMContentLoaded', () => {
    const shieldElements = document.querySelectorAll('[data-lemma-shield]');
    
    shieldElements.forEach(element => {
        const securityLevel = element.getAttribute('data-security-level') || 'standard';
        const protectedContent = element.getAttribute('data-protected-content') || element;
        
        new LemmashieldAPI({
            protectedContent: protectedContent,
            securityLevel: securityLevel,
            onVerified: () => {
                console.log('✅ Auto-initialized Lemma shield: User verified');
            },
            onError: (error) => {
                console.error('❌ Auto-initialized Lemma shield error:', error);
            }
        });
    });
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmashieldAPI;
}

// Global access
window.LemmashieldAPI = LemmashieldAPI; 
