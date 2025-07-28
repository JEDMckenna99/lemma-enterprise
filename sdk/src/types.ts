/**
 * Lemma Verification SDK - TypeScript Definitions
 * 
 * Comprehensive type definitions for the Lemma offline credential verification system
 */

// React types (conditional - only available if React is installed)
declare global {
  namespace React {
    interface CSSProperties {
      [key: string]: any;
    }
    type ReactNode = any;
  }
}

// Core verification types
export interface VerificationResult {
  verified: boolean;
  claims: Record<string, any>;
  timing: {
    verification: number;
    unit: 'microseconds' | 'milliseconds';
  };
  networkCalls: number;
  cacheHit: boolean;
  error?: string;
}

export interface CredentialClaims {
  // Common claims
  iss?: string; // Issuer
  sub?: string; // Subject
  aud?: string; // Audience
  exp?: number; // Expiration time
  nbf?: number; // Not before
  iat?: number; // Issued at
  jti?: string; // JWT ID
  
  // Lemma-specific claims
  credentialType?: 'identity' | 'ticket' | 'package_authenticity' | 'qr_code' | string;
  verificationLevel?: 'low' | 'medium' | 'high';
  
  // Identity credential claims
  isHuman?: boolean;
  name?: string;
  email?: string;
  age?: number;
  country?: string;
  
  // Ticket credential claims
  eventName?: string;
  eventDate?: string;
  venue?: string;
  seatNumber?: string;
  ticketPrice?: number;
  
  // Package authenticity claims
  batchNumber?: string;
  serialNumber?: string;
  manufacturer?: string;
  manufacturerDID?: string;
  productName?: string;
  
  // QR code claims
  qrType?: string;
  businessName?: string;
  location?: string;
  url?: string;
  
  // Custom claims
  [key: string]: any;
}

export interface QRScanResult {
  data: string;
  verificationResult: VerificationResult;
  timestamp: number;
}

export interface LemmaConfig {
  apiKey?: string;
  wasmPath?: string;
  debug?: boolean;
  retryAttempts?: number;
  timeout?: number;
  theme?: 'light' | 'dark';
  language?: string;
  autoInit?: boolean;
  
  // Enhanced error handling configurations
  retry?: Partial<RetryConfig>;
  circuitBreaker?: Partial<CircuitBreakerConfig>;
  errorRecovery?: ErrorRecoveryStrategy[];
  errorReporting?: Partial<ErrorReportingConfig>;
}

export interface LemmaState {
  isScanning: boolean;
  isVerifying: boolean;
  lastResult: VerificationResult | null;
  networkCalls: number;
  cacheHits: number;
  initialized: boolean;
}

// Event types
export type LemmaEventType = 
  | 'ready'
  | 'error'
  | 'verification-start'
  | 'verification-complete'
  | 'verification-error'
  | 'scan-start'
  | 'scan-complete'
  | 'scan-error'
  | 'scan-stop';

export interface LemmaEvent<T = any> {
  type: LemmaEventType;
  data?: T;
  timestamp: number;
}

export type LemmaEventCallback<T = any> = (event: LemmaEvent<T>) => void;

// QR Scanner options
export interface QRScanOptions {
  facingMode?: 'environment' | 'user';
  maxScansPerSecond?: number;
  highlightScanRegion?: boolean;
  highlightCodeOutline?: boolean;
  overlay?: boolean;
  returnDetailedScanResult?: boolean;
  calculateScanRegion?: (video: HTMLVideoElement) => {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

// React component props
export interface LemmaVerifierProps {
  config?: LemmaConfig;
  onReady?: () => void;
  onError?: (error: Error) => void;
  onVerificationComplete?: (result: VerificationResult) => void;
  onScanComplete?: (result: QRScanResult) => void;
  className?: string;
  style?: React.CSSProperties;
}

export interface LemmaQRScannerProps {
  onScan?: (result: QRScanResult) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
  options?: QRScanOptions;
  className?: string;
  style?: React.CSSProperties;
  showCloseButton?: boolean;
  overlayClassName?: string;
}

export interface LemmaVerifyButtonProps {
  credentialData?: string;
  scanMode?: boolean;
  onVerification?: (result: VerificationResult) => void;
  onError?: (error: Error) => void;
  className?: string;
  style?: React.CSSProperties;
  disabled?: boolean;
  loading?: boolean;
  children?: React.ReactNode;
}

export interface LemmaResultDisplayProps {
  result: VerificationResult | null;
  loading?: boolean;
  error?: string;
  className?: string;
  style?: React.CSSProperties;
  showTiming?: boolean;
  showClaims?: boolean;
  theme?: 'light' | 'dark';
}

// Core SDK interface
export interface LemmaSDK {
  // Configuration
  config: LemmaConfig;
  state: LemmaState;
  version: string;
  
  // Core methods
  init(config?: LemmaConfig): Promise<void>;
  verify(credentialData: string): Promise<VerificationResult>;
  scanQR(options?: QRScanOptions): Promise<QRScanResult>;
  stopQRScan(): void;
  
  // Event system
  on<T = any>(event: LemmaEventType, callback: LemmaEventCallback<T>): void;
  off<T = any>(event: LemmaEventType, callback: LemmaEventCallback<T>): void;
  emit<T = any>(event: LemmaEventType, data?: T): void;
  
  // Utility methods
  validateCredential(credentialData: string): boolean;
  parseClaims(credentialData: string): CredentialClaims;
  getPerformanceMetrics(): {
    averageVerificationTime: number;
    totalVerifications: number;
    cacheHitRate: number;
    errorRate: number;
  };
  
  // Cache management
  clearCache(): void;
  getCacheSize(): number;
  setCacheEnabled(enabled: boolean): void;
}

// Error types
export class LemmaError extends Error {
  constructor(
    message: string,
    public code: string,
    public details?: any,
    public isRetryable: boolean = false,
    public retryCount: number = 0
  ) {
    super(message);
    this.name = 'LemmaError';
  }
}

export class LemmaInitializationError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'INITIALIZATION_ERROR', details, true);
  }
}

export class LemmaVerificationError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'VERIFICATION_ERROR', details, true);
  }
}

export class LemmaQRScanError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'QR_SCAN_ERROR', details, true);
  }
}

export class LemmaNetworkError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'NETWORK_ERROR', details, true);
  }
}

export class LemmaTimeoutError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'TIMEOUT_ERROR', details, true);
  }
}

export class LemmaCacheError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'CACHE_ERROR', details, false);
  }
}

export class LemmaValidationError extends LemmaError {
  constructor(message: string, details?: any) {
    super(message, 'VALIDATION_ERROR', details, false);
  }
}

// Enhanced retry configuration
export interface RetryConfig {
  maxAttempts: number;
  baseDelay: number;
  maxDelay: number;
  exponentialBase: number;
  jitter: boolean;
  retryCondition?: (error: Error) => boolean;
}

// Circuit breaker configuration
export interface CircuitBreakerConfig {
  failureThreshold: number;
  successThreshold: number;
  timeout: number;
  monitoringPeriod: number;
  enabled: boolean;
}

// Enhanced error recovery strategies
export interface ErrorRecoveryStrategy {
  name: string;
  condition: (error: Error) => boolean;
  recovery: (error: Error) => Promise<void>;
  priority: number;
}

// Error reporting configuration
export interface ErrorReportingConfig {
  enabled: boolean;
  endpoint?: string;
  apiKey?: string;
  includeStackTrace: boolean;
  includeUserAgent: boolean;
  includeUrl: boolean;
  customFields?: Record<string, any>;
}

// Utility types
export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

export type LemmaEventMap = {
  ready: void;
  error: { message: string; error: Error };
  'verification-start': void;
  'verification-complete': VerificationResult;
  'verification-error': Error;
  'scan-start': void;
  'scan-complete': QRScanResult;
  'scan-error': Error;
  'scan-stop': void;
};

// Integration helpers
export interface IntegrationExample {
  name: string;
  description: string;
  code: string;
  platform: 'vanilla' | 'react' | 'vue' | 'angular' | 'node';
  category: 'basic' | 'advanced' | 'ecommerce' | 'identity' | 'ticketing';
}

// Performance monitoring
export interface PerformanceMetrics {
  verification: {
    count: number;
    totalTime: number;
    averageTime: number;
    minTime: number;
    maxTime: number;
  };
  scanning: {
    count: number;
    successRate: number;
    averageTime: number;
  };
  cache: {
    hitRate: number;
    size: number;
    maxSize: number;
  };
  errors: {
    count: number;
    rate: number;
    categories: Record<string, number>;
  };
}

// Export default configuration
export const DEFAULT_CONFIG: Required<LemmaConfig> = {
  apiKey: '',
  wasmPath: 'https://cdn.lemma.id/pkg/',
  debug: false,
  retryAttempts: 3,
  timeout: 10000,
  theme: 'light',
  language: 'en',
  autoInit: true,
  
  // Enhanced error handling defaults
  retry: {
    maxAttempts: 3,
    baseDelay: 1000,
    maxDelay: 30000,
    exponentialBase: 2,
    jitter: true,
    retryCondition: (error: Error) => error instanceof LemmaError && (error as LemmaError).isRetryable
  },
  circuitBreaker: {
    failureThreshold: 5,
    successThreshold: 3,
    timeout: 60000,
    monitoringPeriod: 300000,
    enabled: true
  },
  errorRecovery: [],
  errorReporting: {
    enabled: false,
    includeStackTrace: false,
    includeUserAgent: true,
    includeUrl: true,
    customFields: {}
  }
};

// Export credential type guards
export const isIdentityCredential = (claims: CredentialClaims): claims is CredentialClaims & { isHuman: boolean } => {
  return claims.credentialType === 'identity' && typeof claims.isHuman === 'boolean';
};

export const isTicketCredential = (claims: CredentialClaims): claims is CredentialClaims & { eventName: string } => {
  return claims.credentialType === 'ticket' && typeof claims.eventName === 'string';
};

export const isPackageCredential = (claims: CredentialClaims): claims is CredentialClaims & { manufacturerDID: string } => {
  return claims.credentialType === 'package_authenticity' && typeof claims.manufacturerDID === 'string';
};

export const isQRCodeCredential = (claims: CredentialClaims): claims is CredentialClaims & { qrType: string } => {
  return claims.credentialType === 'qr_code' && typeof claims.qrType === 'string';
}; 