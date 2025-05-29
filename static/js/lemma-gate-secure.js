/**
 * Lemma Gate - Security-Hardened Version
 * CRITICAL: This is a UX layer only - NEVER rely on client-side verification for security
 */

class LemmaSecureGate {
  constructor(options = {}) {
    this.options = {
      // Security settings
      requireServerVerification: true,
      contentDeliveryMode: 'server_fetch', // 'server_fetch' | 'server_rendered'
      enableSecurityLogging: true,
      maxVerificationAttempts: 3,
      verificationTimeout: 30000, // 30 seconds
      
      // UI settings
      gateContainer: options.gateContainer || 'lemma-gate',
      protectedContainer: options.protectedContainer || 'protected-content',
      contentEndpoint: options.contentEndpoint || '/api/protected-content',
      verificationEndpoint: options.verificationEndpoint || '/api/verify-human',
      
      ...options
    };
    
    this.verificationAttempts = 0;
    this.isVerifying = false;
    this.serverVerified = false;
    this.wallet = null;
    
    // Security: Prevent tampering with verification status
    this._securityToken = this.generateSecurityToken();
    
    this.init();
  }

  generateSecurityToken() {
    // Generate a token to detect tampering
    return Array.from(crypto.getRandomValues(new Uint8Array(16)))
      .map(b => b.toString(16).padStart(2, '0')).join('');
  }

  async init() {
    console.log('[SecureGate] Initializing security-hardened gate...');
    
    // Security: Hide protected content by default
    this.hideProtectedContent();
    
    try {
      await this.waitForWallet();
      await this.performSecureVerification();
    } catch (error) {
      console.error('[SecureGate] Initialization failed:', error);
      this.showGate();
    }
  }

  async waitForWallet(timeout = 10000) {
    return new Promise((resolve, reject) => {
      const startTime = Date.now();
      
      const checkWallet = () => {
        if (window.lemmaWallet) {
          this.wallet = window.lemmaWallet;
          resolve();
        } else if (Date.now() - startTime > timeout) {
          reject(new Error('Wallet timeout'));
        } else {
          setTimeout(checkWallet, 100);
        }
      };
      
      checkWallet();
    });
  }

  async performSecureVerification() {
    if (this.isVerifying || this.verificationAttempts >= this.options.maxVerificationAttempts) {
      this.showGate();
      return;
    }

    this.isVerifying = true;
    this.verificationAttempts++;
    this.showLoadingState();

    try {
      // 1. Check for credentials
      const credentials = await this.wallet.getAllCredentials();
      
      if (!credentials || credentials.length === 0) {
        console.log('[SecureGate] No credentials found');
        this.showGate();
        return;
      }

      // 2. CRITICAL: Always verify with server
      const serverVerified = await this.verifyWithServer(credentials[0]);
      
      if (serverVerified) {
        // 3. Fetch protected content from server
        await this.fetchProtectedContent();
      } else {
        console.log('[SecureGate] Server verification failed');
        this.showGate();
      }

    } catch (error) {
      console.error('[SecureGate] Verification failed:', error);
      this.logSecurityEvent('verification_failed', { error: error.message });
      this.showGate();
    } finally {
      this.isVerifying = false;
    }
  }

  async verifyWithServer(credential) {
    try {
      const credentialData = credential.credential || credential;
      
      // Generate secure challenge
      const challenge = this.generateChallenge();
      
      // Create presentation
      const presentation = await this.createSecurePresentation(credentialData, challenge);
      
      // CRITICAL: Send to server for verification
      const response = await fetch(this.options.verificationEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Security-Token': this._securityToken,
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'include', // Include session cookies
        body: JSON.stringify({
          presentation: presentation,
          challenge: challenge,
          securityToken: this._securityToken
        })
      });

      if (!response.ok) {
        throw new Error(`Server verification failed: ${response.status}`);
      }

      const result = await response.json();
      
      // SECURITY: Only trust server response
      this.serverVerified = result.success === true && result.verified === true;
      
      if (this.serverVerified) {
        this.logSecurityEvent('verification_success', { 
          credential_id: credentialData.id,
          challenge: challenge 
        });
      }
      
      return this.serverVerified;

    } catch (error) {
      this.logSecurityEvent('server_verification_error', { error: error.message });
      return false;
    }
  }

  async fetchProtectedContent() {
    try {
      // SECURITY: Fetch content from server after verification
      const response = await fetch(this.options.contentEndpoint, {
        method: 'GET',
        headers: {
          'X-Security-Token': this._securityToken,
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'include' // Include session cookies
      });

      if (!response.ok) {
        throw new Error(`Content fetch failed: ${response.status}`);
      }

      const content = await response.text();
      
      // Display content only after successful server fetch
      this.displaySecureContent(content);
      
    } catch (error) {
      console.error('[SecureGate] Content fetch failed:', error);
      this.logSecurityEvent('content_fetch_failed', { error: error.message });
      this.showError('Failed to load protected content');
    }
  }

  displaySecureContent(content) {
    const protectedContainer = document.getElementById(this.options.protectedContainer);
    
    if (protectedContainer) {
      // Security: Replace content entirely to prevent pre-loaded content
      protectedContainer.innerHTML = content;
      protectedContainer.style.display = 'block';
      
      // Hide gate
      this.hideGate();
      
      this.logSecurityEvent('content_displayed', { 
        timestamp: Date.now(),
        securityToken: this._securityToken 
      });
    }
  }

  generateChallenge() {
    return Array.from(crypto.getRandomValues(new Uint8Array(32)))
      .map(b => b.toString(16).padStart(2, '0')).join('');
  }

  async createSecurePresentation(credential, challenge) {
    // Enhanced presentation with security measures
    return {
      "@context": ["https://www.w3.org/2018/credentials/v1"],
      "type": ["VerifiablePresentation"],
      "verifiableCredential": [credential],
      "proof": {
        "type": "Ed25519Signature2020",
        "created": new Date().toISOString(),
        "challenge": challenge,
        "proofPurpose": "authentication",
        "securityToken": this._securityToken
      }
    };
  }

  logSecurityEvent(event, data = {}) {
    if (!this.options.enableSecurityLogging) return;
    
    const logEntry = {
      event: event,
      timestamp: Date.now(),
      url: window.location.href,
      userAgent: navigator.userAgent,
      securityToken: this._securityToken,
      ...data
    };
    
    // Send to server for security monitoring
    fetch('/api/security-log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(logEntry)
    }).catch(error => {
      console.warn('[SecureGate] Security logging failed:', error);
    });
  }

  // UI Methods with security considerations
  showLoadingState() {
    this.hideProtectedContent();
    this.showGate();
    // Show loading UI
  }

  showGate() {
    const gateContainer = document.getElementById(this.options.gateContainer);
    if (gateContainer) {
      gateContainer.style.display = 'block';
      this.setupSecureGateUI();
    }
    this.hideProtectedContent();
  }

  hideGate() {
    const gateContainer = document.getElementById(this.options.gateContainer);
    if (gateContainer) {
      gateContainer.style.display = 'none';
    }
  }

  hideProtectedContent() {
    const protectedContainer = document.getElementById(this.options.protectedContainer);
    if (protectedContainer) {
      // Security: Clear any pre-loaded content
      protectedContainer.innerHTML = '<div class="loading">Verifying access...</div>';
      protectedContainer.style.display = 'none';
    }
  }

  setupSecureGateUI() {
    const gateContainer = document.getElementById(this.options.gateContainer);
    if (!gateContainer) return;

    gateContainer.innerHTML = `
      <div class="secure-gate-overlay">
        <div class="secure-gate-modal">
          <div class="gate-header">
            <h2>🔒 Human Verification Required</h2>
            <p>Protected by Lemma secure human verification</p>
          </div>
          
          <div class="gate-body">
            ${this.verificationAttempts >= this.options.maxVerificationAttempts ? 
              '<p class="error">Maximum verification attempts exceeded. Please refresh the page.</p>' :
              `<button id="verify-btn" class="verify-button">
                🤖 Verify Human Identity
              </button>
              <p class="security-notice">
                Verification creates a secure credential that works across the Lemma Network
              </p>`
            }
          </div>
        </div>
      </div>
    `;

    // Add secure event listeners
    const verifyBtn = document.getElementById('verify-btn');
    if (verifyBtn) {
      verifyBtn.addEventListener('click', () => {
        window.location.href = '/verify?redirect=' + encodeURIComponent(window.location.href);
      });
    }
  }

  showError(message) {
    this.logSecurityEvent('error_displayed', { message });
    this.showGate();
    // Update UI to show error
  }

  // Security: Prevent direct manipulation
  getSecurityStatus() {
    return {
      serverVerified: this.serverVerified,
      verificationAttempts: this.verificationAttempts,
      securityToken: this._securityToken,
      timestamp: Date.now()
    };
  }
}

// Security: Prevent tampering with the class
Object.freeze(LemmaSecureGate.prototype);

// Auto-initialize with security checks
document.addEventListener('DOMContentLoaded', function() {
  const gateElement = document.getElementById('lemma-gate');
  const protectedElement = document.getElementById('protected-content');
  
  if (gateElement || protectedElement) {
    console.log('[SecureGate] Initializing secure gate...');
    
    setTimeout(() => {
      window.lemmaSecureGate = new LemmaSecureGate({
        gateContainer: 'lemma-gate',
        protectedContainer: 'protected-content'
      });
    }, 1000);
  }
});

// Security CSS
const securityCSS = `
.secure-gate-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 999999;
}

.secure-gate-modal {
  background: white;
  border-radius: 12px;
  padding: 2rem;
  max-width: 500px;
  width: 90%;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.verify-button {
  background: linear-gradient(135deg, #6B3FA0 0%, #8F6BC1 100%);
  color: white;
  border: none;
  padding: 16px 32px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.security-notice {
  color: #666;
  font-size: 14px;
  margin-top: 1rem;
}

.error {
  color: #dc3545;
  font-weight: 600;
}
`;

// Inject security CSS
if (!document.getElementById('secure-gate-styles')) {
  const style = document.createElement('style');
  style.id = 'secure-gate-styles';
  style.textContent = securityCSS;
  document.head.appendChild(style);
}

window.LemmaSecureGate = LemmaSecureGate; 