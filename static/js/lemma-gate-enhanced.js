/**
 * Lemma Gate Enhanced with Crypto Hardening
 * Integrates with crypto-hardened backend for maximum security
 * Implements User Trust Protocol for comprehensive user verification
 */

class LemmaGateEnhanced {
  constructor(options = {}) {
    this.options = {
      // API endpoints
      verificationEndpoint: options.verificationEndpoint || '/api/v2/verify-human',
      challengeEndpoint: options.challengeEndpoint || '/api/v2/generate-challenge',
      statusEndpoint: options.statusEndpoint || '/api/v2/crypto-status',
      securityLogEndpoint: options.securityLogEndpoint || '/api/v2/security-log',
      
      // Security settings
      cryptoVersion: '2.0',
      requireEnhancedSecurity: options.requireEnhancedSecurity !== false,
      maxRetries: options.maxRetries || 3,
      retryDelay: options.retryDelay || 1000,
      
      // UI settings
      containerSelector: options.containerSelector || '.lemma-gate-container',
      showSecurityDetails: options.showSecurityDetails !== false,
      autoDetectCredentials: options.autoDetectCredentials !== false,
      
      // Callbacks
      onVerificationSuccess: options.onVerificationSuccess || null,
      onVerificationFailure: options.onVerificationFailure || null,
      onSecurityEvent: options.onSecurityEvent || null,
      
      ...options
    };

    // State
    this.isInitialized = false;
    this.isVerifying = false;
    this.verificationResult = null;
    this.securityStatus = null;
    this._securityToken = null;
    this._currentChallenge = null;

    // Initialize
    this.init();
  }

  async init() {
    try {
      // Check crypto status
      await this.checkCryptoStatus();
      
      // Auto-detect existing credentials if enabled
      if (this.options.autoDetectCredentials) {
        await this.autoDetectAndVerify();
      }

      this.isInitialized = true;
      this.logSecurityEvent('gate_initialized', {
        crypto_version: this.options.cryptoVersion,
        enhanced_security: this.options.requireEnhancedSecurity
      });

    } catch (error) {
      this.logSecurityEvent('gate_initialization_failed', { error: error.message }, 'ERROR');
      console.error('Lemma Gate Enhanced initialization failed:', error);
    }
  }

  async checkCryptoStatus() {
    /**Check and validate server crypto capabilities */
    try {
      const response = await fetch(this.options.statusEndpoint, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'X-Crypto-Version': this.options.cryptoVersion
        }
      });

      if (!response.ok) {
        throw new Error(`Crypto status check failed: ${response.status}`);
      }

      this.securityStatus = await response.json();
      
      // Validate crypto compatibility
      if (!this.securityStatus.status || 
          !this.securityStatus.status.supportedVersions.includes(this.options.cryptoVersion)) {
        throw new Error(`Crypto version ${this.options.cryptoVersion} not supported`);
      }

      this.logSecurityEvent('crypto_status_verified', {
        supported_versions: this.securityStatus.status.supportedVersions,
        security_features: this.securityStatus.status.securityFeatures
      });

      return this.securityStatus;

    } catch (error) {
      this.logSecurityEvent('crypto_status_check_failed', { error: error.message }, 'ERROR');
      throw error;
    }
  }

  async autoDetectAndVerify() {
    /**Auto-detect Lemma credentials and verify if found */
    try {
      // Check for Lemma wallet
      if (window.lemmaWallet) {
        const credentials = await window.lemmaWallet.getAllCredentials();
        
        if (credentials && credentials.length > 0) {
          const credential = credentials[0]; // Use first credential
          this.logSecurityEvent('credential_auto_detected', { 
            credential_id: credential.id 
          });
          
          // Attempt automatic verification
          const verified = await this.verifyCredential(credential);
          
          if (verified) {
            this.showSuccessState();
            return true;
          }
        }
      }

      // Check browser storage as fallback
      const storedCredential = localStorage.getItem('lemma_credential');
      if (storedCredential) {
        try {
          const credential = JSON.parse(storedCredential);
          const verified = await this.verifyCredential(credential);
          
          if (verified) {
            this.showSuccessState();
            return true;
          }
        } catch (error) {
          this.logSecurityEvent('stored_credential_invalid', { error: error.message }, 'WARNING');
        }
      }

      // No valid credentials found
      this.showGateModal();
      return false;

    } catch (error) {
      this.logSecurityEvent('auto_detection_failed', { error: error.message }, 'ERROR');
      this.showGateModal();
      return false;
    }
  }

  async verifyCredential(credential) {
    /**Verify a credential using enhanced crypto */
    if (this.isVerifying) {
      return false;
    }

    this.isVerifying = true;

    try {
      // Generate secure challenge
      const challengeResponse = await fetch(this.options.challengeEndpoint, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'X-Crypto-Version': this.options.cryptoVersion,
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'include'
      });

      if (!challengeResponse.ok) {
        throw new Error(`Challenge generation failed: ${challengeResponse.status}`);
      }

      const challengeData = await challengeResponse.json();
      
      if (!challengeData.success || !challengeData.challenge) {
        throw new Error('Invalid challenge response');
      }

      this._currentChallenge = challengeData.challenge;

      // Create enhanced presentation using crypto hardening
      const presentation = await this.createEnhancedPresentation(credential, challengeData.challenge);

      // Verify with server
      const verified = await this.verifyWithServer(presentation, challengeData.challenge);

      if (verified) {
        this.verificationResult = {
          verified: true,
          credential_id: credential.id,
          crypto_version: this.options.cryptoVersion,
          timestamp: new Date().toISOString()
        };

        this.logSecurityEvent('credential_verification_success', this.verificationResult);
        
        if (this.options.onVerificationSuccess) {
          this.options.onVerificationSuccess(this.verificationResult);
        }

        return true;
      } else {
        throw new Error('Server verification failed');
      }

    } catch (error) {
      this.logSecurityEvent('credential_verification_failed', { 
        error: error.message,
        credential_id: credential?.id
      }, 'ERROR');

      if (this.options.onVerificationFailure) {
        this.options.onVerificationFailure(error);
      }

      return false;

    } finally {
      this.isVerifying = false;
    }
  }

  async createEnhancedPresentation(credential, challenge) {
    /**Create enhanced presentation with crypto hardening */
    try {
      // Use crypto-hardened presentation creation
      if (window.LemmaCryptoHardened) {
        return await window.LemmaCryptoHardened.createSecurePresentation(credential, challenge, {
          domain: window.location.hostname,
          cryptoVersion: this.options.cryptoVersion
        });
      } 
      
      // Fallback to basic presentation
      const timestamp = new Date().toISOString();
      
      return {
        "@context": [
          "https://www.w3.org/2018/credentials/v1",
          "https://lemma.network/security/v1"
        ],
        "type": ["VerifiablePresentation", "LemmaEnhancedPresentation"],
        "verifiableCredential": [credential],
        "proof": {
          "type": "Ed25519Signature2020",
          "created": timestamp,
          "challenge": challenge,
          "proofPurpose": "authentication",
          "cryptoVersion": this.options.cryptoVersion,
          "domain": window.location.hostname
        }
      };

    } catch (error) {
      this.logSecurityEvent('presentation_creation_failed', { error: error.message }, 'ERROR');
      throw error;
    }
  }

  async verifyWithServer(presentation, challenge) {
    /**Verify presentation with enhanced server */
    try {
      // Generate security token for this request
      this._securityToken = this.generateSecurityToken();

      const verificationData = {
        presentation: presentation,
        challenge: challenge,
        securityToken: this._securityToken,
        cryptoVersion: this.options.cryptoVersion
      };

      // Calculate presentation hash for integrity
      let presentationHash = '';
      if (window.LemmaCryptoHardened) {
        presentationHash = await window.LemmaCryptoHardened.hashPresentation(presentation);
      }

      const response = await fetch(this.options.verificationEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Crypto-Version': this.options.cryptoVersion,
          'X-Security-Token': this._securityToken,
          'X-Requested-With': 'XMLHttpRequest',
          'X-Presentation-Hash': presentationHash
        },
        credentials: 'include',
        body: JSON.stringify(verificationData)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`Verification failed: ${response.status} - ${errorData.error || 'Unknown error'}`);
      }

      const result = await response.json();

      // Enhanced validation of server response
      if (!result.success || !result.verified) {
        this.logSecurityEvent('server_verification_rejected', {
          errors: result.errors || [],
          security_level: result.securityLevel
        }, 'WARNING');
        return false;
      }

      // Validate crypto features
      if (this.options.requireEnhancedSecurity && !result.cryptoValid) {
        this.logSecurityEvent('enhanced_security_required', {
          crypto_valid: result.cryptoValid,
          crypto_version: result.cryptoVersion
        }, 'WARNING');
        return false;
      }

      this.logSecurityEvent('server_verification_success', {
        crypto_version: result.cryptoVersion,
        security_level: result.securityLevel,
        verification_time: result.verificationTime
      });

      return true;

    } catch (error) {
      this.logSecurityEvent('server_verification_error', { error: error.message }, 'ERROR');
      return false;
    }
  }

  generateSecurityToken() {
    /**Generate secure token for request authentication */
    const tokenBytes = new Uint8Array(32);
    crypto.getRandomValues(tokenBytes);
    return Array.from(tokenBytes)
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
  }

  showGateModal() {
    /**Display verification gate modal */
    const container = document.querySelector(this.options.containerSelector) || document.body;
    
    const modal = document.createElement('div');
    modal.className = 'lemma-gate-modal enhanced';
    modal.innerHTML = `
      <div class="lemma-gate-overlay"></div>
      <div class="lemma-gate-content">
        <div class="lemma-gate-header">
          <h2>🔒 Enhanced User Trust Protocol Verification Required</h2>
          <p>This content requires verified user access with enhanced security.</p>
        </div>
        
        ${this.options.showSecurityDetails ? `
        <div class="lemma-security-features">
          <h3>Enhanced Security Features:</h3>
          <ul>
            <li>✅ 256-bit cryptographic challenges</li>
            <li>✅ Multi-layer replay attack protection</li>
            <li>✅ Domain binding validation</li>
            <li>✅ Real-time integrity checking</li>
            <li>✅ Hardware-backed security when available</li>
          </ul>
        </div>
        ` : ''}
        
        <div class="lemma-gate-actions">
          <button class="lemma-verify-btn enhanced" onclick="window.location.href='/verify'">
            🚀 Get Enhanced User Verification
          </button>
          <p class="lemma-crypto-info">
            User Trust Protocol Version: ${this.options.cryptoVersion} | 
            Security Level: Enhanced
          </p>
        </div>
        
        <div class="lemma-gate-footer">
          <p>Powered by <strong>Lemma User Trust Protocol</strong></p>
        </div>
      </div>
    `;

    container.appendChild(modal);
    
    // Add enhanced styling
    this.addEnhancedStyling();
    
    this.logSecurityEvent('gate_modal_displayed', {
      crypto_version: this.options.cryptoVersion,
      enhanced_features: this.options.showSecurityDetails
    });
  }

  showSuccessState() {
    /**Display successful verification state */
    const containers = document.querySelectorAll(this.options.containerSelector);
    
    containers.forEach(container => {
      const successBanner = document.createElement('div');
      successBanner.className = 'lemma-verification-success enhanced';
      successBanner.innerHTML = `
        <div class="success-content">
          <h3>✅ Enhanced User Trust Protocol Verification Successful</h3>
          <p>You have been verified with <strong>Enhanced Security (User Trust Protocol v${this.options.cryptoVersion})</strong></p>
          <div class="verification-details">
            <span class="crypto-badge">🔐 User Trust Protocol v${this.options.cryptoVersion}</span>
            <span class="security-badge">🛡️ Enhanced Security</span>
          </div>
        </div>
      `;

      container.prepend(successBanner);
    });

    this.logSecurityEvent('success_state_displayed', {
      crypto_version: this.options.cryptoVersion
    });
  }

  addEnhancedStyling() {
    /**Add enhanced CSS styles for crypto v2.0 UI */
    if (document.getElementById('lemma-enhanced-styles')) {
      return; // Already added
    }

    const styles = document.createElement('style');
    styles.id = 'lemma-enhanced-styles';
    styles.textContent = `
      .lemma-gate-modal.enhanced .lemma-gate-content {
        border: 2px solid #28a745;
        box-shadow: 0 8px 32px rgba(40, 167, 69, 0.2);
      }
      
      .lemma-gate-header h2 {
        color: #28a745;
        font-weight: 600;
      }
      
      .lemma-security-features {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 15px;
        border-radius: 8px;
        margin: 15px 0;
        border-left: 4px solid #28a745;
      }
      
      .lemma-security-features h3 {
        color: #28a745;
        margin-bottom: 10px;
        font-size: 14px;
        font-weight: 600;
      }
      
      .lemma-security-features ul {
        margin: 0;
        padding-left: 0;
        list-style: none;
      }
      
      .lemma-security-features li {
        padding: 3px 0;
        font-size: 12px;
        color: #495057;
      }
      
      .lemma-verify-btn.enhanced {
        background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
        border: none;
        color: white;
        padding: 12px 24px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 14px;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(40, 167, 69, 0.3);
      }
      
      .lemma-verify-btn.enhanced:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(40, 167, 69, 0.4);
      }
      
      .lemma-crypto-info {
        font-size: 11px;
        color: #6c757d;
        margin-top: 10px;
        font-family: 'Monaco', 'Menlo', monospace;
      }
      
      .lemma-verification-success.enhanced {
        background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
        color: white;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(40, 167, 69, 0.3);
      }
      
      .success-content h3 {
        margin: 0 0 8px 0;
        font-size: 16px;
      }
      
      .success-content p {
        margin: 0 0 10px 0;
        font-size: 14px;
      }
      
      .verification-details {
        display: flex;
        gap: 10px;
      }
      
      .crypto-badge, .security-badge {
        background: rgba(255, 255, 255, 0.2);
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 500;
      }
    `;

    document.head.appendChild(styles);
  }

  async logSecurityEvent(eventType, data = {}, level = 'INFO') {
    /**Log security events to server */
    try {
      const eventData = {
        event: eventType,
        data: {
          ...data,
          timestamp: new Date().toISOString(),
          user_agent: navigator.userAgent,
          url: window.location.href,
          crypto_version: this.options.cryptoVersion
        }
      };

      // Also log to console in development
      if (window.location.hostname === 'localhost' || window.location.hostname.includes('127.0.0.1')) {
        console.log(`[LEMMA SECURITY] ${eventType}:`, eventData.data);
      }

      // Get CSRF token from meta tag or cookie
      let csrfToken = '';
      const metaTag = document.querySelector('meta[name="csrf-token"]');
      if (metaTag) {
        csrfToken = metaTag.getAttribute('content');
      } else {
        // Try to get from cookie
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
          const [name, value] = cookie.trim().split('=');
          if (name === '_csrf_token') {
            csrfToken = value;
            break;
          }
        }
      }

      // Prepare headers
      const headers = {
        'Content-Type': 'application/json',
        'X-Crypto-Version': this.options.cryptoVersion
      };

      // Add CSRF token if available
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }

      // Send to server (non-blocking)
      fetch(this.options.securityLogEndpoint, {
        method: 'POST',
        headers: headers,
        credentials: 'include',
        body: JSON.stringify(eventData)
      }).catch(error => {
        console.warn('Security logging failed:', error);
      });

      // Call user callback if provided
      if (this.options.onSecurityEvent) {
        this.options.onSecurityEvent(eventType, eventData.data, level);
      }

    } catch (error) {
      console.warn('Security event logging failed:', error);
    }
  }

  // Public API methods
  async refresh() {
    /**Refresh verification status */
    if (!this.isInitialized) {
      await this.init();
    } else {
      await this.autoDetectAndVerify();
    }
  }

  getVerificationResult() {
    /**Get current verification result */
    return this.verificationResult;
  }

  getSecurityStatus() {
    /**Get current security status */
    return this.securityStatus;
  }

  destroy() {
    /**Clean up gate instance */
    const modals = document.querySelectorAll('.lemma-gate-modal.enhanced');
    modals.forEach(modal => modal.remove());

    const banners = document.querySelectorAll('.lemma-verification-success.enhanced');
    banners.forEach(banner => banner.remove());

    this.logSecurityEvent('gate_destroyed');
  }
}

// Auto-initialize on page load if data-lemma-enhanced attribute is present
document.addEventListener('DOMContentLoaded', () => {
  const enhancedElements = document.querySelectorAll('[data-lemma-enhanced="true"]');
  
  if (enhancedElements.length > 0) {
    window.lemmaGateEnhanced = new LemmaGateEnhanced({
      containerSelector: '[data-lemma-enhanced="true"]',
      autoDetectCredentials: true,
      showSecurityDetails: true
    });
  }
});

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = LemmaGateEnhanced;
}

// Global access
window.LemmaGateEnhanced = LemmaGateEnhanced; 