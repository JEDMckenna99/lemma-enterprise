// Core Lemma SDK Types
export interface LemmaConfig {
  /** Lemma instance URL */
  instanceUrl: string;
  /** API key for authentication */
  apiKey?: string;
  /** Timeout for verification requests in milliseconds */
  timeout?: number;
  /** Enable debug logging */
  debug?: boolean;
}

export interface VerifiableCredential {
  "@context": string[];
  id: string;
  type: string[];
  issuer: string | { id: string };
  issuanceDate: string;
  expirationDate?: string;
  credentialSubject: {
    id: string;
    isHuman: boolean;
    [key: string]: any;
  };
  proof: {
    type: string;
    created: string;
    verificationMethod: string;
    proofPurpose: string;
    jws: string;
  };
}

export interface VerifiablePresentation {
  "@context": string[];
  id: string;
  type: string[];
  holder: string;
  verifiableCredential: VerifiableCredential[];
  proof: {
    type: string;
    created: string;
    verificationMethod: string;
    proofPurpose: string;
    challenge: string;
    jws: string;
  };
}

export interface VerificationResult {
  success: boolean;
  verified: boolean;
  isHuman?: boolean;
  message?: string;
  details?: {
    credentialValid: boolean;
    signatureValid: boolean;
    notExpired: boolean;
    notRevoked: boolean;
    challengeMatched: boolean;
  };
}

export interface Challenge {
  challenge: string;
  expiresAt: number;
}

export interface LemmaWalletCredential {
  credential: VerifiableCredential;
  storedAt: number;
  lastUsed?: number;
}

export interface NetworkStatus {
  siteCount: number;
  verificationCount: number;
  agentCount: number;
  lastUpdated: string;
}

// React Hook Types
export interface UseLemmaVerificationOptions {
  /** Auto-verify on component mount */
  autoVerify?: boolean;
  /** Redirect URL after successful verification */
  redirectTo?: string;
  /** Callback on verification success */
  onSuccess?: (result: VerificationResult) => void;
  /** Callback on verification failure */
  onError?: (error: Error) => void;
}

export interface UseLemmaVerificationReturn {
  /** Current verification status */
  isVerified: boolean;
  /** Loading state */
  isLoading: boolean;
  /** Error state */
  error: Error | null;
  /** Trigger manual verification */
  verify: () => Promise<VerificationResult>;
  /** Clear current verification */
  clearVerification: () => void;
  /** Get stored credential */
  getCredential: () => Promise<VerifiableCredential | null>;
}

// Express Middleware Types
export interface LemmaMiddlewareOptions {
  /** Require verification for this route */
  required?: boolean;
  /** Redirect URL for unverified users */
  redirectTo?: string;
  /** Custom error handler */
  onError?: (req: any, res: any, next: any, error: Error) => void;
}

// Enhanced Express Request interface
export interface LemmaRequest {
  lemma?: {
    isVerified: boolean;
    credential?: VerifiableCredential;
    userId?: string;
  };
  // Express-specific properties
  headers: { [key: string]: string | string[] | undefined };
  cookies?: { [key: string]: string };
  session?: any;
  query: { [key: string]: string | string[] | undefined };
  body: any;
  ip?: string;
  path: string;
  secure: boolean;
}

// Analytics Types
export interface VerificationMetrics {
  totalVerifications: number;
  uniqueUsers: number;
  tokenReuseRate: number;
  captchaSecondsSaved: number;
  averageVerificationTime: number;
  failureRate: number;
}

export interface SiteUsage {
  domain: string;
  verificationsToday: number;
  verificationsThisMonth: number;
  uniqueUsersToday: number;
  uniqueUsersThisMonth: number;
  lastVerification: string;
}

// Error Types
export class LemmaError extends Error {
  constructor(
    message: string,
    public code: string,
    public details?: any
  ) {
    super(message);
    this.name = 'LemmaError';
  }
}

export class VerificationError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'VERIFICATION_ERROR', details);
    this.name = 'VerificationError';
  }
}

export class NetworkError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'NETWORK_ERROR', details);
    this.name = 'NetworkError';
  }
}

export class ConfigurationError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'CONFIGURATION_ERROR', details);
    this.name = 'ConfigurationError';
  }
} 