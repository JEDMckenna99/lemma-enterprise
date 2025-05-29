// Main Lemma SDK exports
export { LemmaClient } from './client';
export * from './types';
import { LemmaClient } from './client';
import { LemmaConfig } from './types';

// Express middleware (optional - only loads if Express is available)
export {
  lemmaMiddleware,
  requireLemmaVerification,
  lemmaCallbackHandler,
  isVerifiedHuman,
  getVerifiedUserId,
  lemmaAnalyticsMiddleware
} from './express';

// React components (conditional exports)
export let useLemmaVerification: any;
export let withLemmaVerification: any;
export let LemmaGate: any;

// Try to load React components if available
try {
  if (typeof window !== 'undefined') {
    // Browser environment - check if React is available
    const reactModule = require('./react');
    useLemmaVerification = reactModule.useLemmaVerification;
    withLemmaVerification = reactModule.withLemmaVerification;
    LemmaGate = reactModule.LemmaGate;
  }
} catch {
  // React not available or load failed - exports will be undefined
}

// Default export for convenience
export default LemmaClient;

// Version information
export const VERSION = '1.0.0';

/**
 * Quick setup helper for the most common use case
 * 
 * @example
 * ```javascript
 * const lemma = createLemmaClient({
 *   instanceUrl: 'https://your-lemma-instance.com',
 *   apiKey: 'your-api-key'
 * });
 * 
 * // Check verification
 * const isVerified = await lemma.verify();
 * ```
 */
export function createLemmaClient(config: LemmaConfig) {
  return new LemmaClient(config);
}

/**
 * Pre-configured clients for common Lemma instances
 */
export const LemmaInstances = {
  /**
   * Production Lemma instance
   */
  production: (apiKey?: string) => new LemmaClient({
    instanceUrl: 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com',
    apiKey
  }),
  
  /**
   * Create a client for a custom instance
   */
  custom: (instanceUrl: string, apiKey?: string) => new LemmaClient({
    instanceUrl,
    apiKey
  })
};

/**
 * Utility to check if the current environment supports Lemma
 */
export function isLemmaSupported(): boolean {
  // Check for required browser APIs
  if (typeof window !== 'undefined') {
    return !!(window.localStorage && window.fetch && window.crypto);
  }
  
  // For Node.js, check for Node.js globals and fetch availability
  try {
    return !!(typeof global !== 'undefined' && (global.fetch || global.process));
  } catch {
    return false;
  }
}

/**
 * Get recommended configuration for different environments
 */
export function getRecommendedConfig(environment: 'development' | 'staging' | 'production') {
  const baseConfig = {
    timeout: 30000,
    debug: environment !== 'production'
  };

  switch (environment) {
    case 'development':
      return {
        ...baseConfig,
        debug: true,
        timeout: 60000 // Longer timeout for development
      };
    case 'staging':
      return {
        ...baseConfig,
        debug: true
      };
    case 'production':
      return {
        ...baseConfig,
        debug: false
      };
    default:
      return baseConfig;
  }
} 