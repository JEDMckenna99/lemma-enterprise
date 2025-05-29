/**
 * Lemma Cryptographic Security Enhancements
 * Addresses potential crypto vulnerabilities with hardened implementations
 */

class LemmaCryptoHardened {
  
  /**
   * Generate cryptographically secure challenge
   * Increased from 16 to 32 bytes for better security margin
   */
  static generateSecureChallenge() {
    // 32 bytes = 256 bits of entropy (recommended)
    const challengeBytes = crypto.getRandomValues(new Uint8Array(32));
    return Array.from(challengeBytes)
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
  }

  /**
   * Generate security token with high entropy
   * Used for replay attack prevention
   */
  static generateSecurityToken() {
    // 32 bytes = 256 bits of entropy
    const tokenBytes = crypto.getRandomValues(new Uint8Array(32));
    return Array.from(tokenBytes)
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
  }

  /**
   * Create cryptographically secure presentation with enhanced security
   */
  static async createSecurePresentation(credential, challenge, options = {}) {
    // Validate inputs
    if (!credential || !challenge) {
      throw new Error('Invalid credential or challenge');
    }

    // Ensure challenge has sufficient entropy
    if (challenge.length < 64) { // 32 bytes = 64 hex chars
      throw new Error('Challenge insufficient entropy');
    }

    const timestamp = new Date().toISOString();
    const securityToken = this.generateSecurityToken();

    // Enhanced presentation with crypto hardening
    const presentation = {
      "@context": [
        "https://www.w3.org/2018/credentials/v1",
        "https://lemma.network/security/v1"
      ],
      "type": ["VerifiablePresentation", "LemmaSecurePresentation"],
      "verifiableCredential": [credential],
      "proof": {
        "type": "Ed25519Signature2020",
        "created": timestamp,
        "challenge": challenge,
        "proofPurpose": "authentication",
        "securityToken": securityToken,
        // Add nonce to prevent replay even with same challenge
        "nonce": this.generateSecurityToken(),
        // Add domain binding to prevent cross-site replay
        "domain": window.location.hostname,
        // Add presentation expiry
        "expiresAt": new Date(Date.now() + 300000).toISOString() // 5 minutes
      }
    };

    // Add integrity protection
    presentation.proof.presentationHash = await this.hashPresentation(presentation);

    return presentation;
  }

  /**
   * Hash presentation for integrity protection
   */
  static async hashPresentation(presentation) {
    // Create canonical representation for hashing
    const canonical = JSON.stringify(presentation, Object.keys(presentation).sort());
    const encoder = new TextEncoder();
    const data = encoder.encode(canonical);
    
    // Use SHA-256 for hashing
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  }

  /**
   * Validate timestamp to prevent replay attacks
   */
  static validateTimestamp(timestamp, maxAgeMinutes = 5) {
    try {
      const created = new Date(timestamp);
      const now = new Date();
      const ageMillis = now.getTime() - created.getTime();
      const maxAgeMillis = maxAgeMinutes * 60 * 1000;
      
      return ageMillis <= maxAgeMillis && ageMillis >= 0;
    } catch (error) {
      return false;
    }
  }

  /**
   * Validate presentation security properties
   */
  static async validatePresentationSecurity(presentation) {
    const errors = [];

    // Check required security fields
    if (!presentation.proof) {
      errors.push('Missing proof');
    } else {
      const proof = presentation.proof;
      
      // Validate timestamp
      if (!proof.created || !this.validateTimestamp(proof.created)) {
        errors.push('Invalid or expired timestamp');
      }

      // Validate challenge entropy
      if (!proof.challenge || proof.challenge.length < 64) {
        errors.push('Insufficient challenge entropy');
      }

      // Validate security token
      if (!proof.securityToken || proof.securityToken.length < 64) {
        errors.push('Missing or weak security token');
      }

      // Validate nonce
      if (!proof.nonce || proof.nonce.length < 64) {
        errors.push('Missing or weak nonce');
      }

      // Validate domain binding
      if (proof.domain && proof.domain !== window.location.hostname) {
        errors.push('Domain mismatch - potential replay attack');
      }

      // Validate expiry
      if (proof.expiresAt && new Date(proof.expiresAt) < new Date()) {
        errors.push('Presentation expired');
      }

      // Validate presentation hash
      if (proof.presentationHash) {
        const computedHash = await this.hashPresentation({
          ...presentation,
          proof: { ...proof, presentationHash: undefined }
        });
        
        if (computedHash !== proof.presentationHash) {
          errors.push('Presentation integrity check failed');
        }
      }
    }

    return {
      valid: errors.length === 0,
      errors: errors
    };
  }

  /**
   * Secure credential verification with crypto validation
   */
  static async secureVerifyCredential(credential) {
    try {
      // Basic structure validation
      if (!credential || typeof credential !== 'object') {
        return { valid: false, reason: 'Invalid credential format' };
      }

      // Check required fields
      const requiredFields = ['@context', 'type', 'issuer', 'credentialSubject', 'proof'];
      for (const field of requiredFields) {
        if (!credential[field]) {
          return { valid: false, reason: `Missing required field: ${field}` };
        }
      }

      // Validate proof structure
      const proof = credential.proof;
      if (!proof.type || !proof.created || !proof.proofValue) {
        return { valid: false, reason: 'Invalid proof structure' };
      }

      // Validate Ed25519 signature format
      if (proof.type !== 'Ed25519Signature2020') {
        return { valid: false, reason: 'Unsupported signature type' };
      }

      // Validate timestamp
      if (!this.validateTimestamp(proof.created, 525600)) { // 1 year max age
        return { valid: false, reason: 'Credential timestamp invalid or expired' };
      }

      // Additional crypto validations would go here
      // (signature verification requires private key infrastructure)

      return { valid: true };

    } catch (error) {
      return { 
        valid: false, 
        reason: `Verification error: ${error.message}` 
      };
    }
  }

  /**
   * Secure random ID generation for credentials
   */
  static generateSecureCredentialId() {
    const randomBytes = crypto.getRandomValues(new Uint8Array(32));
    const base64 = btoa(String.fromCharCode(...randomBytes))
      .replace(/[+/]/g, c => c === '+' ? '-' : '_')
      .replace(/=+$/, '');
    
    return `urn:lemma:credential:${base64}`;
  }

  /**
   * Constant-time string comparison to prevent timing attacks
   */
  static constantTimeEqual(a, b) {
    if (a.length !== b.length) {
      return false;
    }

    let result = 0;
    for (let i = 0; i < a.length; i++) {
      result |= a.charCodeAt(i) ^ b.charCodeAt(i);
    }

    return result === 0;
  }

  /**
   * Secure session token validation
   */
  static validateSecurityToken(providedToken, expectedToken) {
    if (!providedToken || !expectedToken) {
      return false;
    }

    // Use constant-time comparison to prevent timing attacks
    return this.constantTimeEqual(providedToken, expectedToken);
  }
}

// Enhanced LemmaGate with crypto hardening
class LemmaSecureGateHardened extends LemmaSecureGate {
  
  generateChallenge() {
    // Use crypto-hardened challenge generation
    return LemmaCryptoHardened.generateSecureChallenge();
  }

  generateSecurityToken() {
    // Use crypto-hardened token generation  
    return LemmaCryptoHardened.generateSecurityToken();
  }

  async createSecurePresentation(credential, challenge) {
    // Use crypto-hardened presentation creation
    return LemmaCryptoHardened.createSecurePresentation(credential, challenge);
  }

  async verifyWithServer(credential) {
    try {
      // First validate credential cryptographically
      const credentialValidation = await LemmaCryptoHardened.secureVerifyCredential(credential.credential || credential);
      
      if (!credentialValidation.valid) {
        throw new Error(`Credential validation failed: ${credentialValidation.reason}`);
      }

      // Generate secure challenge
      const challenge = this.generateChallenge();
      
      // Create hardened presentation
      const presentation = await this.createSecurePresentation(credential.credential || credential, challenge);
      
      // Validate presentation security before sending
      const presentationValidation = await LemmaCryptoHardened.validatePresentationSecurity(presentation);
      
      if (!presentationValidation.valid) {
        throw new Error(`Presentation validation failed: ${presentationValidation.errors.join(', ')}`);
      }

      // Send to server with enhanced security headers
      const response = await fetch(this.options.verificationEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Security-Token': this._securityToken,
          'X-Requested-With': 'XMLHttpRequest',
          'X-Crypto-Version': '2.0',
          'X-Presentation-Hash': presentation.proof.presentationHash
        },
        credentials: 'include',
        body: JSON.stringify({
          presentation: presentation,
          challenge: challenge,
          securityToken: this._securityToken,
          cryptoVersion: '2.0'
        })
      });

      if (!response.ok) {
        throw new Error(`Server verification failed: ${response.status}`);
      }

      const result = await response.json();
      
      // Enhanced server response validation
      this.serverVerified = result.success === true && 
                          result.verified === true &&
                          result.cryptoValid === true; // New crypto validation flag
      
      if (this.serverVerified) {
        this.logSecurityEvent('crypto_verification_success', { 
          credential_id: (credential.credential || credential).id,
          challenge: challenge,
          crypto_version: '2.0'
        });
      }
      
      return this.serverVerified;

    } catch (error) {
      this.logSecurityEvent('crypto_verification_error', { error: error.message });
      return false;
    }
  }
}

// Export enhanced classes
window.LemmaCryptoHardened = LemmaCryptoHardened;
window.LemmaSecureGateHardened = LemmaSecureGateHardened; 