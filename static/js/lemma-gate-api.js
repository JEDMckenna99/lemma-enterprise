/**
 * Lemma Gate API Client - Clean API-Driven Implementation
 * Enhanced with enterprise security controls and configurable protection levels
 * 
 * This client handles all gate functionality through centralized API endpoints.
 * All verification logic, session management, and security is handled server-side.
 * 
 * Perfect Flow:
 * 1. Call API to check status with security level
 * 2. If has credentials → API handles background verification automatically
 * 3. If no credentials → Show gate → Direct to verification flow
 * 4. Support for credential revocation and re-verification
 * 
 * Usage:
 * const gate = new LemmaGateAPI({
 *   protectedContent: '#protected-content',
 *   securityLevel: 'standard', // basic, standard, high, maximum
 *   onVerified: () => console.log('User verified!'),
 *   onRevoked: () => console.log('Credential revoked!'),
 *   onError: (error) => console.error('Gate error:', error)
 * });
 */

class LemmaGateAPI {
    constructor(options = {}) {
        this.options = {
            // UI Elements
            protectedContent: options.protectedContent || '#protected-content',
            gateContainer: options.gateContainer || '#lemma-gate-overlay',
            
            // Security Configuration
            securityLevel: options.securityLevel || 'standard',
            autoCheckInterval: options.autoCheckInterval || 30000, // 30 seconds
            
            // API Configuration
            apiBase: options.apiBase || '',
            
            // Callbacks
            onVerified: options.onVerified || (() => {}),
            onRevoked: options.onRevoked || (() => {}),
            onReverificationRequired: options.onReverificationRequired || (() => {}),
            onError: options.onError || ((error) => console.error('Lemma Gate Error:', error)),
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
        
        // Initialize the gate
        this.init();
    }
    
    async init() {
        try {
            console.log('🔐 Initializing Lemma Gate API with security level:', this.state.securityLevel);
            
            // Load gate configuration
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
            console.log('✅ Lemma Gate API initialized successfully');
            
        } catch (error) {
            console.error('❌ Failed to initialize Lemma Gate API:', error);
            this.options.onError(error);
        }
    }
    
    async loadConfig() {
        try {
            const response = await fetch(`${this.options.apiBase}/api/gate/config?security_level=${this.state.securityLevel}`);
            if (!response.ok) {
                throw new Error(`Config load failed: ${response.status}`);
            }
            
            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Failed to load configuration');
            }
            
            this.config = result.config;
            console.log('📋 Gate configuration loaded:', this.config);
            
        } catch (error) {
            console.error('❌ Failed to load gate configuration:', error);
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
            const response = await fetch(`${this.options.apiBase}/api/gate/status?security_level=${this.state.securityLevel}`, {
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
        const { gate_action, data, message } = result;
        
        console.log(`🔍 Gate status: ${gate_action}`, data);
        
        switch (gate_action) {
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
                console.warn('⚠️ Unknown gate action:', gate_action);
                await this.showGate();
        }
        
        this.options.onStatusChange(gate_action, data);
    }
    
    async handleAllowAccess(data) {
        this.state.verified = true;
        this.state.credentialId = data.credential_id;
        
        console.log('✅ Access allowed - user verified');
        this.hideGate();
        this.showProtectedContent();
        this.options.onVerified(data);
    }
    
    async handleCheckCredentials(data) {
        console.log('🔍 Checking user credentials...');
        
        if (!this.wallet) {
            console.log('❌ No wallet available - showing gate');
            await this.showGate();
            return;
        }
        
        try {
            const credentials = await this.wallet.getCredentials();
            if (!credentials || credentials.length === 0) {
                console.log('❌ No credentials found - showing gate');
                await this.showGate();
                return;
            }
            
            // Verify credentials with the API
            await this.verifyCredentials(credentials);
            
        } catch (error) {
            console.error('❌ Credential check failed:', error);
            await this.showGate();
        }
    }
    
    async handleVerifyDID(data) {
        console.log('🔍 DID verification required...');
        
        try {
            const credentials = await this.wallet.getCredentials();
            if (!credentials || credentials.length === 0) {
                await this.showGate();
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
                await this.showGate();
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
        
        // Show re-verification gate
        await this.showGate({
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
        await this.showGate({
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
            const challengeResponse = await fetch(`${this.options.apiBase}/api/gate/challenge`, {
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
            const verifyResponse = await fetch(`${this.options.apiBase}/api/gate/verify-credentials`, {
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
    
    async showGate(options = {}) {
        console.log('🚪 Showing Lemma Gate');
        
        this.hideProtectedContent();
        
        const gateContainer = document.querySelector(this.options.gateContainer);
        if (!gateContainer) {
            // Create gate container if it doesn't exist
            this.createGateContainer(options);
        } else {
            // Update existing gate
            this.updateGateContent(gateContainer, options);
        }
        
        // Show the gate
        const gate = document.querySelector(this.options.gateContainer);
        if (gate) {
            gate.style.display = 'flex';
            gate.classList.add('lemma-gate-visible');
        }
    }
    
    createGateContainer(options = {}) {
        const gate = document.createElement('div');
        gate.id = this.options.gateContainer.replace('#', '');
        gate.className = 'lemma-gate-overlay';
        
        const title = options.title || 'Human Verification Required';
        const message = options.message || 'Please verify that you are human to access this content.';
        const isReverification = options.isReverification || false;
        const isRevoked = options.isRevoked || false;
        
        gate.innerHTML = `
            <div class="lemma-gate-modal">
                <div class="lemma-gate-header">
                    <h2>${title}</h2>
                    ${isRevoked ? '<div class="lemma-gate-status revoked">Credential Revoked</div>' : ''}
                    ${isReverification ? '<div class="lemma-gate-status reverify">Re-verification Required</div>' : ''}
                </div>
                <div class="lemma-gate-content">
                    <p>${message}</p>
                    <div class="lemma-gate-security-info">
                        <strong>Security Level:</strong> ${this.state.securityLevel.toUpperCase()}
                        ${this.config ? `<br><small>Session timeout: ${Math.round(this.config.settings.session_timeout / 3600)}h</small>` : ''}
                    </div>
                </div>
                <div class="lemma-gate-actions">
                    ${isRevoked ? 
                        '<button class="lemma-gate-btn primary" onclick="window.location.reload()">Get New Verification</button>' :
                        '<button class="lemma-gate-btn primary" id="lemma-verify-btn">Verify Human</button>'
                    }
                    <button class="lemma-gate-btn secondary" id="lemma-gate-close">Close</button>
                </div>
            </div>
        `;
        
        // Add styles
        this.addGateStyles();
        
        // Add event listeners
        this.addGateEventListeners(gate, options);
        
        document.body.appendChild(gate);
    }
    
    updateGateContent(gateContainer, options = {}) {
        const title = options.title || 'Human Verification Required';
        const message = options.message || 'Please verify that you are human to access this content.';
        
        const header = gateContainer.querySelector('.lemma-gate-header h2');
        const content = gateContainer.querySelector('.lemma-gate-content p');
        
        if (header) header.textContent = title;
        if (content) content.textContent = message;
    }
    
    addGateEventListeners(gate, options = {}) {
        const verifyBtn = gate.querySelector('#lemma-verify-btn');
        const closeBtn = gate.querySelector('#lemma-gate-close');
        
        if (verifyBtn) {
            verifyBtn.addEventListener('click', async () => {
                await this.startVerification(options);
            });
        }
        
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                this.hideGate();
            });
        }
        
        // Close on overlay click
        gate.addEventListener('click', (e) => {
            if (e.target === gate) {
                this.hideGate();
            }
        });
    }
    
    async startVerification(options = {}) {
        try {
            const response = await fetch(`${this.options.apiBase}/api/gate/start-verification`, {
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
    
    hideGate() {
        const gate = document.querySelector(this.options.gateContainer);
        if (gate) {
            gate.style.display = 'none';
            gate.classList.remove('lemma-gate-visible');
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
            console.error('❌ Max retries reached, showing gate');
            this.state.retryCount = 0;
            await this.showGate({
                title: 'Verification Error',
                message: 'Unable to verify your status. Please try again.',
                error: this.options.showDetailedErrors ? error.message : undefined
            });
        }
        
        this.options.onError(error);
    }
    
    addGateStyles() {
        if (document.getElementById('lemma-gate-styles')) {
            return; // Styles already added
        }
        
        const styles = document.createElement('style');
        styles.id = 'lemma-gate-styles';
        styles.textContent = `
            .lemma-gate-overlay {
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
            
            .lemma-gate-modal {
                background: white;
                border-radius: 12px;
                padding: 32px;
                max-width: 480px;
                width: 90%;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                text-align: center;
            }
            
            .lemma-gate-header h2 {
                margin: 0 0 16px 0;
                color: #1a1a1a;
                font-size: 24px;
                font-weight: 600;
            }
            
            .lemma-gate-status {
                display: inline-block;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                margin-bottom: 16px;
            }
            
            .lemma-gate-status.revoked {
                background: #fee;
                color: #c53030;
                border: 1px solid #fed7d7;
            }
            
            .lemma-gate-status.reverify {
                background: #fff3cd;
                color: #856404;
                border: 1px solid #ffeaa7;
            }
            
            .lemma-gate-content p {
                margin: 0 0 24px 0;
                color: #4a5568;
                font-size: 16px;
                line-height: 1.5;
            }
            
            .lemma-gate-security-info {
                background: #f7fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 16px;
                margin: 16px 0;
                font-size: 14px;
                color: #2d3748;
            }
            
            .lemma-gate-actions {
                display: flex;
                gap: 12px;
                justify-content: center;
                margin-top: 24px;
            }
            
            .lemma-gate-btn {
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                min-width: 120px;
            }
            
            .lemma-gate-btn.primary {
                background: #635bff;
                color: white;
            }
            
            .lemma-gate-btn.primary:hover {
                background: #5a52ff;
                transform: translateY(-1px);
            }
            
            .lemma-gate-btn.secondary {
                background: #f7fafc;
                color: #4a5568;
                border: 1px solid #e2e8f0;
            }
            
            .lemma-gate-btn.secondary:hover {
                background: #edf2f7;
            }
            
            @media (max-width: 640px) {
                .lemma-gate-modal {
                    padding: 24px;
                    margin: 16px;
                }
                
                .lemma-gate-actions {
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
        this.hideGate();
        
        // Remove gate container
        const gate = document.querySelector(this.options.gateContainer);
        if (gate) {
            gate.remove();
        }
        
        // Remove styles
        const styles = document.getElementById('lemma-gate-styles');
        if (styles) {
            styles.remove();
        }
        
        console.log('🗑️ Lemma Gate API destroyed');
    }
}

// Auto-initialize if data-lemma-gate attribute is present
document.addEventListener('DOMContentLoaded', () => {
    const gateElements = document.querySelectorAll('[data-lemma-gate]');
    
    gateElements.forEach(element => {
        const securityLevel = element.getAttribute('data-security-level') || 'standard';
        const protectedContent = element.getAttribute('data-protected-content') || element;
        
        new LemmaGateAPI({
            protectedContent: protectedContent,
            securityLevel: securityLevel,
            onVerified: () => {
                console.log('✅ Auto-initialized Lemma Gate: User verified');
            },
            onError: (error) => {
                console.error('❌ Auto-initialized Lemma Gate error:', error);
            }
        });
    });
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaGateAPI;
}

// Global access
window.LemmaGateAPI = LemmaGateAPI; 