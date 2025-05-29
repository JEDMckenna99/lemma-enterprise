import axios, { AxiosInstance, AxiosError } from 'axios';
import {
  LemmaConfig,
  VerifiableCredential,
  VerifiablePresentation,
  VerificationResult,
  Challenge,
  LemmaWalletCredential,
  NetworkStatus,
  VerificationMetrics,
  LemmaError,
  VerificationError,
  NetworkError,
  ConfigurationError
} from './types';

export class LemmaClient {
  private config: Required<LemmaConfig>;
  private http: AxiosInstance;
  private storageKey = 'lemma_credentials';

  constructor(config: LemmaConfig) {
    // Validate required config
    if (!config.instanceUrl) {
      throw new ConfigurationError('instanceUrl is required');
    }

    // Set defaults
    this.config = {
      instanceUrl: config.instanceUrl.replace(/\/$/, ''), // Remove trailing slash
      apiKey: config.apiKey || '',
      timeout: config.timeout || 30000,
      debug: config.debug || false
    };

    // Create HTTP client
    this.http = axios.create({
      baseURL: this.config.instanceUrl,
      timeout: this.config.timeout,
      headers: {
        'Content-Type': 'application/json',
        ...(this.config.apiKey && { 'X-API-Key': this.config.apiKey })
      }
    });

    // Add response interceptor for error handling
    this.http.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        this.log('HTTP Error:', error.message);
        throw new NetworkError(
          `Request failed: ${error.message}`,
          { status: error.response?.status, data: error.response?.data }
        );
      }
    );
  }

  private log(...args: any[]): void {
    if (this.config.debug) {
      console.log('[Lemma SDK]', ...args);
    }
  }

  /**
   * Check if user has a stored Lemma credential
   */
  async hasCredential(): Promise<boolean> {
    try {
      const credential = await this.getStoredCredential();
      return credential !== null;
    } catch {
      return false;
    }
  }

  /**
   * Get stored credential from browser storage
   */
  async getStoredCredential(): Promise<VerifiableCredential | null> {
    try {
      if (typeof window === 'undefined' || !window.localStorage) {
        return null;
      }

      const stored = localStorage.getItem(this.storageKey);
      if (!stored) {
        return null;
      }

      const parsed = JSON.parse(stored) as LemmaWalletCredential;
      
      // Check if credential is expired
      if (parsed.credential.expirationDate) {
        const expiry = new Date(parsed.credential.expirationDate);
        if (expiry < new Date()) {
          this.log('Credential expired, removing from storage');
          localStorage.removeItem(this.storageKey);
          return null;
        }
      }

      return parsed.credential;
    } catch (error) {
      this.log('Error retrieving stored credential:', error);
      return null;
    }
  }

  /**
   * Store credential in browser storage
   */
  private async storeCredential(credential: VerifiableCredential): Promise<void> {
    try {
      if (typeof window === 'undefined' || !window.localStorage) {
        throw new Error('Browser storage not available');
      }

      const walletCredential: LemmaWalletCredential = {
        credential,
        storedAt: Date.now(),
        lastUsed: Date.now()
      };

      localStorage.setItem(this.storageKey, JSON.stringify(walletCredential));
      this.log('Credential stored successfully');
    } catch (error) {
      this.log('Error storing credential:', error);
      throw new Error(`Failed to store credential: ${error}`);
    }
  }

  /**
   * Generate a verification challenge
   */
  async generateChallenge(): Promise<Challenge> {
    try {
      const response = await this.http.get('/api/generate-challenge');
      return response.data;
    } catch (error) {
      throw new NetworkError('Failed to generate challenge');
    }
  }

  /**
   * Verify a user with Lemma
   * If no credential exists, redirects to verification flow
   */
  async verify(redirectTo?: string): Promise<VerificationResult> {
    try {
      this.log('Starting verification process');

      // Check for existing credential
      let credential = await this.getStoredCredential();
      
      if (!credential) {
        // No credential found, redirect to verification
        const verificationUrl = `${this.config.instanceUrl}/verify`;
        if (typeof window !== 'undefined') {
          window.location.href = verificationUrl;
          // Return pending result since we're redirecting
          return {
            success: false,
            verified: false,
            message: 'Redirecting to verification...'
          };
        } else {
          throw new VerificationError('No credential found and cannot redirect in server environment');
        }
      }

      // Generate challenge for presentation
      const challenge = await this.generateChallenge();
      
      // Create verification presentation
      const presentation = await this.createPresentation(credential, challenge.challenge);
      
      // Verify with server
      const result = await this.verifyPresentation(presentation, challenge.challenge);
      
      if (result.verified) {
        // Update last used timestamp
        await this.storeCredential(credential);
      }

      return result;
    } catch (error) {
      this.log('Verification failed:', error);
      if (error instanceof LemmaError) {
        throw error;
      }
      throw new VerificationError(`Verification failed: ${error}`);
    }
  }

  /**
   * Create a verifiable presentation from a credential
   */
  private async createPresentation(
    credential: VerifiableCredential, 
    challenge: string
  ): Promise<VerifiablePresentation> {
    try {
      const response = await this.http.post('/api/presentation', {
        credential,
        challenge
      });
      return response.data.presentation;
    } catch (error) {
      throw new NetworkError('Failed to create presentation');
    }
  }

  /**
   * Verify a presentation with the server
   */
  async verifyPresentation(
    presentation: VerifiablePresentation, 
    challenge: string
  ): Promise<VerificationResult> {
    try {
      const response = await this.http.post('/api/verify-presentation', {
        presentation,
        challenge
      });
      return response.data;
    } catch (error) {
      throw new NetworkError('Failed to verify presentation');
    }
  }

  /**
   * Clear stored verification credential
   */
  async clearVerification(): Promise<void> {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        localStorage.removeItem(this.storageKey);
        this.log('Verification cleared');
      }
    } catch (error) {
      this.log('Error clearing verification:', error);
    }
  }

  /**
   * Get network status information
   */
  async getNetworkStatus(): Promise<NetworkStatus> {
    try {
      const response = await this.http.get('/api/network/status');
      return response.data;
    } catch (error) {
      throw new NetworkError('Failed to get network status');
    }
  }

  /**
   * Get verification metrics for analytics
   */
  async getMetrics(): Promise<VerificationMetrics> {
    try {
      const response = await this.http.get('/api/analytics/metrics');
      return response.data;
    } catch (error) {
      throw new NetworkError('Failed to get metrics');
    }
  }

  /**
   * Check health of Lemma instance
   */
  async health(): Promise<{ status: string; version?: string }> {
    try {
      const response = await this.http.get('/api/health');
      return response.data;
    } catch (error) {
      throw new NetworkError('Health check failed');
    }
  }

  /**
   * Import a credential from JSON (for cross-device use)
   */
  async importCredential(credentialJson: string): Promise<void> {
    try {
      const credential = JSON.parse(credentialJson) as VerifiableCredential;
      
      // Basic validation
      if (!credential.credentialSubject?.isHuman) {
        throw new VerificationError('Invalid credential: missing isHuman claim');
      }

      await this.storeCredential(credential);
      this.log('Credential imported successfully');
    } catch (error) {
      if (error instanceof VerificationError) {
        throw error;
      }
      throw new VerificationError(`Failed to import credential: ${error}`);
    }
  }

  /**
   * Export credential as JSON (for backup/transfer)
   */
  async exportCredential(): Promise<string | null> {
    try {
      const credential = await this.getStoredCredential();
      if (!credential) {
        return null;
      }
      return JSON.stringify(credential, null, 2);
    } catch (error) {
      this.log('Error exporting credential:', error);
      return null;
    }
  }
} 