/**
 * Lemma SDK TypeScript Example
 * 
 * This example demonstrates the enhanced TypeScript developer experience
 * with comprehensive type safety, IntelliSense, and auto-completion.
 */

import { Lemma } from '../src/index';
import type {
  LemmaConfig,
  VerificationResult,
  CredentialClaims,
  PerformanceMetrics,
  LemmaEventType,
  LemmaEventCallback
} from '../src/types';

// Type-safe configuration with IntelliSense
const config: LemmaConfig = {
  apiKey: 'your-api-key',
  debug: true,
  theme: 'dark', // Auto-completion: 'light' | 'dark'
  retryAttempts: 3,
  timeout: 10000,
  
  // Enhanced error handling with type safety
  retry: {
    maxAttempts: 5,
    baseDelay: 1000,
    maxDelay: 30000,
    exponentialBase: 2,
    jitter: true
  },
  
  circuitBreaker: {
    failureThreshold: 5,
    successThreshold: 3,
    timeout: 60000,
    monitoringPeriod: 300000,
    enabled: true
  },
  
  errorReporting: {
    enabled: true,
    endpoint: 'https://api.lemma.id/errors',
    includeStackTrace: true,
    includeUserAgent: true,
    includeUrl: true
  }
};

// Initialize SDK with type safety
const lemma = new Lemma(config);

// Type-safe event handlers
const onReady: LemmaEventCallback = (event: any) => {
  console.log('SDK ready:', event.timestamp);
  console.log('Version:', lemma.version);
  console.log('State:', lemma.state);
};

const onError: LemmaEventCallback<Error> = (event: any) => {
  console.error('SDK error:', event.data?.message);
  console.error('Error code:', (event.data as any)?.code);
  console.error('Retryable:', (event.data as any)?.isRetryable);
};

const onVerificationComplete: LemmaEventCallback<VerificationResult> = (event: any) => {
  const result = event.data!;
  console.log('Verification result:', result);
  console.log('Verified:', result.verified);
  console.log('Timing:', result.timing);
  console.log('Cache hit:', result.cacheHit);
  console.log('Network calls:', result.networkCalls);
  
  // Type-safe access to claims
  if (result.claims) {
    console.log('Claims type:', result.claims.credentialType);
    console.log('Claims:', result.claims);
  }
};

// Register event listeners with type safety
lemma.on('ready', onReady);
lemma.on('error', onError);
lemma.on('verification-complete', onVerificationComplete);

// Type-safe credential verification examples
async function demonstrateVerification() {
  try {
    // Initialize SDK
    await lemma.init();
    
    // Identity credential verification with type safety
    const identityCredential = '{"credentialType":"identity","isHuman":true,"name":"John Doe","email":"john@example.com","age":30,"verificationLevel":"high"}';
    
    // Generic verification (auto-inferred types)
    const identityResult = await lemma.verify(identityCredential);
    
    // Explicitly typed verification for better IntelliSense
    const typedIdentityResult = await lemma.verify<IdentityCredentialClaims>(identityCredential);
    
    // Type-safe claim access with IntelliSense
    if (typedIdentityResult.verified && typedIdentityResult.claims) {
      console.log('User is human:', typedIdentityResult.claims.isHuman);
      console.log('User name:', typedIdentityResult.claims.name);
      console.log('User age:', typedIdentityResult.claims.age);
      console.log('Verification level:', typedIdentityResult.claims.verificationLevel);
    }
    
    // Ticket credential verification
    const ticketCredential = '{"credentialType":"ticket","eventName":"Concert 2024","eventDate":"2024-06-15","venue":"Madison Square Garden","seatNumber":"A12","ticketPrice":150,"ticketId":"TKT-001"}';
    
    const ticketResult = await lemma.verify<TicketCredentialClaims>(ticketCredential);
    
    if (ticketResult.verified && ticketResult.claims) {
      console.log('Event:', ticketResult.claims.eventName);
      console.log('Date:', ticketResult.claims.eventDate);
      console.log('Venue:', ticketResult.claims.venue);
      console.log('Seat:', ticketResult.claims.seatNumber);
      console.log('Price:', ticketResult.claims.ticketPrice);
    }
    
    // Package authenticity verification
    const packageCredential = '{"credentialType":"package_authenticity","batchNumber":"B001","serialNumber":"S12345","manufacturer":"ACME Corp","manufacturerDID":"did:example:123","productName":"Widget Pro"}';
    
    const packageResult = await lemma.verify<PackageCredentialClaims>(packageCredential);
    
    if (packageResult.verified && packageResult.claims) {
      console.log('Product:', packageResult.claims.productName);
      console.log('Manufacturer:', packageResult.claims.manufacturer);
      console.log('Batch:', packageResult.claims.batchNumber);
      console.log('Serial:', packageResult.claims.serialNumber);
    }
    
    // QR code credential verification
    const qrCredential = '{"credentialType":"qr_code","qrType":"menu","businessName":"Restaurant XYZ","location":"New York","url":"https://menu.restaurant.com"}';
    
    const qrResult = await lemma.verify<QRCodeCredentialClaims>(qrCredential);
    
    if (qrResult.verified && qrResult.claims) {
      console.log('QR Type:', qrResult.claims.qrType);
      console.log('Business:', qrResult.claims.businessName);
      console.log('Location:', qrResult.claims.location);
      console.log('URL:', qrResult.claims.url);
    }
    
    // Performance metrics with type safety
    const metrics: PerformanceMetrics = lemma.getPerformanceMetrics();
    console.log('Performance metrics:', metrics);
    console.log('Average verification time:', metrics.verification.averageTime);
    console.log('Cache hit rate:', metrics.cache.hitRate);
    console.log('Error rate:', metrics.errors.rate);
    
    // QR scanning with type safety
    const qrScanResult = await lemma.scanQR({
      facingMode: 'environment',
      maxScansPerSecond: 5,
      highlightScanRegion: true,
      overlay: true
    });
    
    console.log('QR scan result:', qrScanResult);
    console.log('Scanned data:', qrScanResult.data);
    console.log('Verification result:', qrScanResult.verificationResult);
    
  } catch (error) {
    console.error('Verification failed:', error);
    
    // Type-safe error handling
    if (error instanceof Error) {
      console.error('Error message:', error.message);
      console.error('Error name:', error.name);
      
      // Check for Lemma-specific errors
      if ('code' in error) {
        console.error('Error code:', (error as any).code);
        console.error('Error details:', (error as any).details);
        console.error('Is retryable:', (error as any).isRetryable);
        console.error('Retry count:', (error as any).retryCount);
      }
    }
  }
}

// Utility functions with type safety
function isIdentityCredential(claims: any): claims is IdentityCredentialClaims {
  return claims && claims.credentialType === 'identity' && typeof claims.isHuman === 'boolean';
}

function isTicketCredential(claims: any): claims is TicketCredentialClaims {
  return claims && claims.credentialType === 'ticket' && typeof claims.eventName === 'string';
}

function isPackageCredential(claims: any): claims is PackageCredentialClaims {
  return claims && claims.credentialType === 'package_authenticity' && typeof claims.manufacturerDID === 'string';
}

function isQRCodeCredential(claims: any): claims is QRCodeCredentialClaims {
  return claims && claims.credentialType === 'qr_code' && typeof claims.qrType === 'string';
}

// Type-safe credential processing
async function processCredential(credentialData: string): Promise<void> {
  try {
    const result = await lemma.verify(credentialData);
    
    if (result.verified && result.claims) {
      // Type-safe claim processing using type guards
      if (isIdentityCredential(result.claims)) {
        console.log('Processing identity credential');
        console.log('User verified:', result.claims.isHuman);
        console.log('Verification level:', result.claims.verificationLevel);
      } else if (isTicketCredential(result.claims)) {
        console.log('Processing ticket credential');
        console.log('Event:', result.claims.eventName);
        console.log('Date:', result.claims.eventDate);
      } else if (isPackageCredential(result.claims)) {
        console.log('Processing package credential');
        console.log('Product:', result.claims.productName);
        console.log('Manufacturer:', result.claims.manufacturer);
      } else if (isQRCodeCredential(result.claims)) {
        console.log('Processing QR code credential');
        console.log('QR Type:', result.claims.qrType);
        console.log('Business:', result.claims.businessName);
      }
    }
  } catch (error) {
    console.error('Failed to process credential:', error);
  }
}

// Advanced error handling with type safety
async function advancedErrorHandling() {
  try {
    // This will trigger error handling mechanisms
    await lemma.verify('invalid-credential-data');
  } catch (error) {
    console.error('Caught error:', error);
    
    // Get error status with type safety
    const errorStatus = lemma.getErrorStatus();
    console.log('Circuit breaker state:', errorStatus.circuitBreaker);
    console.log('Error queue size:', errorStatus.errorQueue);
    console.log('Last error:', errorStatus.lastError);
  }
}

// Export functions for use in other modules
export {
  demonstrateVerification,
  processCredential,
  advancedErrorHandling,
  isIdentityCredential,
  isTicketCredential,
  isPackageCredential,
  isQRCodeCredential
};

// Run demonstration
if (require.main === module) {
  demonstrateVerification()
    .then(() => console.log('TypeScript example completed successfully'))
    .catch(error => console.error('TypeScript example failed:', error));
}

// Export SDK instance for external use
export { lemma };
export default lemma; 