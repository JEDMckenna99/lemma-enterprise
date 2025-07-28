/**
 * Lemma Verification SDK - TypeScript Declarations
 * 
 * Comprehensive type definitions for enhanced developer experience
 * Provides IntelliSense, auto-completion, and type checking
 */

declare namespace Lemma {
  // Core configuration
  interface Config {
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

  // Verification result with enhanced type safety
  interface VerificationResult<T = Record<string, any>> {
    verified: boolean;
    claims: T;
    timing: {
      verification: number;
      unit: 'microseconds' | 'milliseconds';
    };
    networkCalls: number;
    cacheHit: boolean;
    error?: string;
    signature?: {
      algorithm: 'Ed25519' | 'ECDSA';
      valid: boolean;
      keyId?: string;
    };
    revocation?: {
      checked: boolean;
      revoked: boolean;
      reason?: string;
    };
  }

  // Credential-specific claim types
  interface IdentityCredentialClaims {
    credentialType: 'identity';
    isHuman: boolean;
    name?: string;
    email?: string;
    age?: number;
    country?: string;
    verificationLevel: 'low' | 'medium' | 'high';
    verificationDate: string;
    providerId?: string;
  }

  interface TicketCredentialClaims {
    credentialType: 'ticket';
    eventName: string;
    eventDate: string;
    venue: string;
    seatNumber?: string;
    ticketPrice?: number;
    ticketId: string;
    validFrom?: string;
    validUntil?: string;
    transferable?: boolean;
  }

  interface PackageCredentialClaims {
    credentialType: 'package_authenticity';
    batchNumber: string;
    serialNumber: string;
    manufacturer: string;
    manufacturerDID: string;
    productName: string;
    productionDate?: string;
    expirationDate?: string;
    certificationBody?: string;
  }

  interface QRCodeCredentialClaims {
    credentialType: 'qr_code';
    qrType: string;
    businessName: string;
    location: string;
    url?: string;
    validityPeriod?: string;
    metadata?: Record<string, any>;
  }

  // Union type for all credential claims
  type CredentialClaims = 
    | IdentityCredentialClaims
    | TicketCredentialClaims
    | PackageCredentialClaims
    | QRCodeCredentialClaims;

  // QR Scanner configuration
  interface QRScanOptions {
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

  // QR scan result
  interface QRScanResult {
    data: string;
    verificationResult: VerificationResult;
    timestamp: number;
    scanRegion?: {
      x: number;
      y: number;
      width: number;
      height: number;
    };
    quality?: number;
  }

  // Enhanced error handling types
  interface RetryConfig {
    maxAttempts: number;
    baseDelay: number;
    maxDelay: number;
    exponentialBase: number;
    jitter: boolean;
    retryCondition?: (error: Error) => boolean;
  }

  interface CircuitBreakerConfig {
    failureThreshold: number;
    successThreshold: number;
    timeout: number;
    monitoringPeriod: number;
    enabled: boolean;
  }

  interface ErrorRecoveryStrategy {
    name: string;
    condition: (error: Error) => boolean;
    recovery: (error: Error) => Promise<void>;
    priority: number;
  }

  interface ErrorReportingConfig {
    enabled: boolean;
    endpoint?: string;
    apiKey?: string;
    includeStackTrace: boolean;
    includeUserAgent: boolean;
    includeUrl: boolean;
    customFields?: Record<string, any>;
  }

  // Event system
  type EventType = 
    | 'ready'
    | 'error'
    | 'verification-start'
    | 'verification-complete'
    | 'verification-error'
    | 'scan-start'
    | 'scan-complete'
    | 'scan-error'
    | 'scan-stop';

  interface Event<T = any> {
    type: EventType;
    data?: T;
    timestamp: number;
  }

  type EventCallback<T = any> = (event: Event<T>) => void;

  // SDK State
  interface State {
    isScanning: boolean;
    isVerifying: boolean;
    lastResult: VerificationResult | null;
    networkCalls: number;
    cacheHits: number;
    initialized: boolean;
    errorCount: number;
    lastError?: Error;
  }

  // Performance metrics
  interface PerformanceMetrics {
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

  // Main SDK interface
  interface SDK {
    // Configuration
    config: Config;
    state: State;
    version: string;
    
    // Core methods
    init(config?: Config): Promise<void>;
    verify<T = CredentialClaims>(credentialData: string): Promise<VerificationResult<T>>;
    scanQR(options?: QRScanOptions): Promise<QRScanResult>;
    stopQRScan(): void;
    
    // Event system
    on<T = any>(event: EventType, callback: EventCallback<T>): void;
    off<T = any>(event: EventType, callback: EventCallback<T>): void;
    emit<T = any>(event: EventType, data?: T): void;
    
    // Utility methods
    validateCredential(credentialData: string): boolean;
    parseClaims<T = CredentialClaims>(credentialData: string): T;
    getPerformanceMetrics(): PerformanceMetrics;
    
    // Cache management
    clearCache(): void;
    getCacheSize(): number;
    setCacheEnabled(enabled: boolean): void;
    
    // Error handling
    getErrorStatus(): {
      circuitBreaker: any;
      errorQueue: number;
      lastError?: Error;
    };
  }

  // Error classes
  class LemmaError extends Error {
    code: string;
    details?: any;
    isRetryable: boolean;
    retryCount: number;
    
    constructor(message: string, code: string, details?: any, isRetryable?: boolean, retryCount?: number);
  }

  class InitializationError extends LemmaError {
    constructor(message: string, details?: any);
  }

  class VerificationError extends LemmaError {
    constructor(message: string, details?: any);
  }

  class QRScanError extends LemmaError {
    constructor(message: string, details?: any);
  }

  class NetworkError extends LemmaError {
    constructor(message: string, details?: any);
  }

  class TimeoutError extends LemmaError {
    constructor(message: string, details?: any);
  }

  class CacheError extends LemmaError {
    constructor(message: string, details?: any);
  }

  class ValidationError extends LemmaError {
    constructor(message: string, details?: any);
  }

  // Type guards for credential claims
  function isIdentityCredential(claims: CredentialClaims): claims is IdentityCredentialClaims;
  function isTicketCredential(claims: CredentialClaims): claims is TicketCredentialClaims;
  function isPackageCredential(claims: CredentialClaims): claims is PackageCredentialClaims;
  function isQRCodeCredential(claims: CredentialClaims): claims is QRCodeCredentialClaims;

  // React component types (if React is available)
  namespace React {
    interface VerifierProps {
      config?: Config;
      onReady?: () => void;
      onError?: (error: Error) => void;
      onVerificationComplete?: (result: VerificationResult) => void;
      onScanComplete?: (result: QRScanResult) => void;
      className?: string;
      style?: Record<string, any>;
    }

    interface QRScannerProps {
      onScan?: (result: QRScanResult) => void;
      onError?: (error: Error) => void;
      onClose?: () => void;
      options?: QRScanOptions;
      className?: string;
      style?: Record<string, any>;
      showCloseButton?: boolean;
      overlayClassName?: string;
    }

    interface VerifyButtonProps {
      credentialData?: string;
      scanMode?: boolean;
      onVerification?: (result: VerificationResult) => void;
      onError?: (error: Error) => void;
      className?: string;
      style?: Record<string, any>;
      disabled?: boolean;
      loading?: boolean;
      children?: any;
    }

    interface ResultDisplayProps {
      result: VerificationResult | null;
      loading?: boolean;
      error?: string;
      className?: string;
      style?: Record<string, any>;
      showTiming?: boolean;
      showClaims?: boolean;
      theme?: 'light' | 'dark';
    }
  }
}

// Global variable declarations
declare global {
  // Window object extensions
  interface Window {
    Lemma: typeof Lemma;
    LemmaSDK: Lemma.SDK;
    lemma_wasm?: any;
    lemma_config?: Lemma.Config;
  }

  // HTML element extensions for data attributes
  interface HTMLElement {
    dataset: DOMStringMap & {
      lemmaVerify?: string;
      lemmaCredentialType?: string;
      lemmaApiKey?: string;
      lemmaConfig?: string;
      lemmaDebug?: string;
      lemmaTheme?: string;
      lemmaAutoInit?: string;
    };
  }

  // Custom events
  interface WindowEventMap {
    'lemma:ready': CustomEvent<{ version: string; config: Lemma.Config }>;
    'lemma:error': CustomEvent<{ error: Error; context: string }>;
    'lemma:verification-complete': CustomEvent<{ result: Lemma.VerificationResult }>;
    'lemma:scan-complete': CustomEvent<{ result: Lemma.QRScanResult }>;
  }
}

// Module augmentation for popular libraries
declare module '@lemma/verification-sdk' {
  export = Lemma;
}

// CDN script loading
declare module 'https://cdn.lemma.id/js/lemma-auto.min.js' {
  export = Lemma;
}

// Export main SDK class
export declare class LemmaSDK implements Lemma.SDK {
  config: Lemma.Config;
  state: Lemma.State;
  version: string;
  
  constructor(config?: Lemma.Config);
  
  init(config?: Lemma.Config): Promise<void>;
  verify<T = Lemma.CredentialClaims>(credentialData: string): Promise<Lemma.VerificationResult<T>>;
  scanQR(options?: Lemma.QRScanOptions): Promise<Lemma.QRScanResult>;
  stopQRScan(): void;
  
  on<T = any>(event: Lemma.EventType, callback: Lemma.EventCallback<T>): void;
  off<T = any>(event: Lemma.EventType, callback: Lemma.EventCallback<T>): void;
  emit<T = any>(event: Lemma.EventType, data?: T): void;
  
  validateCredential(credentialData: string): boolean;
  parseClaims<T = Lemma.CredentialClaims>(credentialData: string): T;
  getPerformanceMetrics(): Lemma.PerformanceMetrics;
  
  clearCache(): void;
  getCacheSize(): number;
  setCacheEnabled(enabled: boolean): void;
  
  getErrorStatus(): {
    circuitBreaker: any;
    errorQueue: number;
    lastError?: Error;
  };
}

// Default export
export default LemmaSDK;

// Named exports
export {
  Lemma,
  LemmaSDK as SDK
};

// Type exports
export type LemmaConfig = Lemma.Config;
export type VerificationResult = Lemma.VerificationResult;
export type CredentialClaims = Lemma.CredentialClaims;
export type IdentityCredentialClaims = Lemma.IdentityCredentialClaims;
export type TicketCredentialClaims = Lemma.TicketCredentialClaims;
export type PackageCredentialClaims = Lemma.PackageCredentialClaims;
export type QRCodeCredentialClaims = Lemma.QRCodeCredentialClaims;
export type QRScanOptions = Lemma.QRScanOptions;
export type QRScanResult = Lemma.QRScanResult;
export type PerformanceMetrics = Lemma.PerformanceMetrics;
export type EventType = Lemma.EventType;
export type EventCallback = Lemma.EventCallback;
export type State = Lemma.State; 