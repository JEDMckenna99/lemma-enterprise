import React, { useState, useEffect, useCallback } from 'react';
import { LemmaClient } from './client';
import {
  LemmaConfig,
  VerifiableCredential,
  VerificationResult,
  UseLemmaVerificationOptions,
  UseLemmaVerificationReturn,
  VerificationError
} from './types';

/**
 * React hook for Lemma human verification
 * 
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { isVerified, isLoading, verify, error } = useLemmaVerification({
 *     instanceUrl: 'https://your-lemma-instance.com',
 *     autoVerify: true,
 *     onSuccess: (result) => console.log('User verified!', result),
 *     onError: (error) => console.error('Verification failed:', error)
 *   });
 * 
 *   if (isLoading) return <div>Verifying...</div>;
 *   if (error) return <div>Error: {error.message}</div>;
 *   if (!isVerified) return <button onClick={verify}>Verify with Lemma</button>;
 *   
 *   return <div>Welcome, verified human! 🎉</div>;
 * }
 * ```
 */
export function useLemmaVerification(
  config: LemmaConfig & UseLemmaVerificationOptions
): UseLemmaVerificationReturn {
  const [isVerified, setIsVerified] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const [lemmaClient] = useState(() => new LemmaClient(config));

  // Check for existing verification on mount
  useEffect(() => {
    async function checkExistingVerification() {
      try {
        setIsLoading(true);
        setError(null);
        
        const hasCredential = await lemmaClient.hasCredential();
        if (hasCredential) {
          // Try to verify with existing credential
          const result = await lemmaClient.verify();
          if (result.verified) {
            setIsVerified(true);
            config.onSuccess?.(result);
          }
        } else if (config.autoVerify) {
          // Auto-verify if no credential and autoVerify is enabled
          await performVerification();
        }
      } catch (err) {
        const error = err instanceof Error ? err : new Error('Unknown error');
        setError(error);
        config.onError?.(error);
      } finally {
        setIsLoading(false);
      }
    }

    checkExistingVerification();
  }, [lemmaClient, config.autoVerify]);

  const performVerification = useCallback(async (): Promise<VerificationResult> => {
    try {
      setIsLoading(true);
      setError(null);

      const result = await lemmaClient.verify(config.redirectTo);
      
      if (result.verified) {
        setIsVerified(true);
        config.onSuccess?.(result);
      } else if (result.message !== 'Redirecting to verification...') {
        throw new VerificationError(result.message || 'Verification failed');
      }

      return result;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Unknown error');
      setError(error);
      config.onError?.(error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [lemmaClient, config.redirectTo, config.onSuccess, config.onError]);

  const clearVerification = useCallback(async (): Promise<void> => {
    try {
      await lemmaClient.clearVerification();
      setIsVerified(false);
      setError(null);
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to clear verification');
      setError(error);
    }
  }, [lemmaClient]);

  const getCredential = useCallback(async (): Promise<VerifiableCredential | null> => {
    try {
      return await lemmaClient.getStoredCredential();
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to get credential');
      setError(error);
      return null;
    }
  }, [lemmaClient]);

  return {
    isVerified,
    isLoading,
    error,
    verify: performVerification,
    clearVerification,
    getCredential
  };
}

/**
 * Higher-order component that wraps a component with Lemma verification
 * 
 * @example
 * ```tsx
 * const ProtectedComponent = withLemmaVerification(
 *   MyComponent,
 *   { instanceUrl: 'https://your-lemma-instance.com' },
 *   () => <div>Please verify to continue</div>
 * );
 * ```
 */
export function withLemmaVerification<P extends object>(
  Component: React.ComponentType<P>,
  config: LemmaConfig,
  fallback?: React.ComponentType | (() => React.ReactElement)
): React.ComponentType<P> {
  return function WrappedComponent(props: P): React.ReactElement {
    const { isVerified, isLoading, verify, error } = useLemmaVerification(config);

    if (isLoading) {
      return React.createElement('div', null, 'Verifying human status...');
    }

    if (error) {
      return React.createElement('div', null,
        React.createElement('p', null, `Verification error: ${error.message}`),
        React.createElement('button', { onClick: verify }, 'Retry')
      );
    }

    if (!isVerified) {
      if (fallback) {
        const FallbackComponent = fallback as React.ComponentType;
        return React.createElement(FallbackComponent);
      }
      
      return React.createElement('div', null,
        React.createElement('h3', null, 'Human Verification Required'),
        React.createElement('p', null, 'Please verify that you\'re human to access this content.'),
        React.createElement('button', { onClick: verify }, 'Verify with Lemma')
      );
    }

    return React.createElement(Component, props);
  };
}

/**
 * Component that automatically handles Lemma verification UI
 * 
 * @example
 * ```tsx
 * <LemmaGate
 *   config={{ instanceUrl: 'https://your-lemma-instance.com' }}
 *   onVerified={(result) => console.log('Verified!', result)}
 * >
 *   <div>This content is only visible to verified humans</div>
 * </LemmaGate>
 * ```
 */
interface LemmaGateProps {
  config: LemmaConfig;
  children: React.ReactNode;
  loadingComponent?: React.ReactNode;
  errorComponent?: (error: Error, retry: () => void) => React.ReactNode;
  verificationComponent?: (verify: () => Promise<VerificationResult>) => React.ReactNode;
  onVerified?: (result: VerificationResult) => void;
  onError?: (error: Error) => void;
}

export function LemmaGate({
  config,
  children,
  loadingComponent,
  errorComponent,
  verificationComponent,
  onVerified,
  onError
}: LemmaGateProps): React.ReactElement {
  const { isVerified, isLoading, verify, error } = useLemmaVerification({
    ...config,
    onSuccess: onVerified,
    onError
  });

  if (isLoading) {
    return loadingComponent as React.ReactElement || React.createElement('div', null, 'Verifying human status...');
  }

  if (error) {
    return errorComponent?.(error, verify) as React.ReactElement || React.createElement('div', null,
      React.createElement('p', null, `Verification error: ${error.message}`),
      React.createElement('button', { onClick: verify }, 'Retry')
    );
  }

  if (!isVerified) {
    return verificationComponent?.(verify) as React.ReactElement || React.createElement('div', null,
      React.createElement('h3', null, 'Human Verification Required'),
      React.createElement('p', null, 'Please verify that you\'re human to access this content.'),
      React.createElement('button', { onClick: verify }, 'Verify with Lemma')
    );
  }

  return React.createElement(React.Fragment, null, children);
} 