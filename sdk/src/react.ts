/**
 * Lemma React Hooks
 * 
 * React integration for Lemma wallet and verification SDK.
 * Provides hooks for authentication, session management, and credential verification.
 * 
 * @example
 * ```tsx
 * import { useLemma, useLemmaSession } from '@lemma/verification-sdk/react';
 * 
 * function App() {
 *   const { wallet, isUnlocked, unlock } = useLemma();
 *   const { session, extendSession } = useLemmaSession();
 *   
 *   return (
 *     <div>
 *       {isUnlocked ? 'Wallet unlocked!' : <button onClick={unlock}>Unlock</button>}
 *     </div>
 *   );
 * }
 * ```
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';

// Types
export interface LemmaWalletState {
    isUnlocked: boolean;
    hasPasskey: boolean;
    isLoading: boolean;
    error: Error | null;
    walletId: string | null;
}

export interface LemmaSessionState {
    valid: boolean;
    authenticated: boolean;
    expiresAt: number | null;
    timeRemaining: number | null;
    canExtend: boolean;
    extensionCount: number;
    shouldPromptExtend: boolean;
}

export interface UseLemmaOptions {
    autoInit?: boolean;
    debug?: boolean;
    onUnlock?: () => void;
    onLock?: () => void;
    onError?: (error: Error) => void;
}

export interface UseLemmaSessionOptions {
    autoManage?: boolean;
    checkInterval?: number;
    autoExtend?: boolean;
    onSessionExpired?: () => void;
    onExtensionNeeded?: (state: LemmaSessionState) => boolean | Promise<boolean>;
}

/**
 * Main Lemma wallet hook
 * Provides wallet state and authentication methods.
 */
export function useLemma(options: UseLemmaOptions = {}) {
    const {
        autoInit = true,
        debug = false,
        onUnlock,
        onLock,
        onError
    } = options;

    const [state, setState] = useState<LemmaWalletState>({
        isUnlocked: false,
        hasPasskey: false,
        isLoading: true,
        error: null,
        walletId: null
    });

    const walletRef = useRef<any>(null);

    // Initialize wallet
    useEffect(() => {
        if (!autoInit) return;

        const init = async () => {
            try {
                // Get wallet instance from window
                const wallet = (window as any).lemmaWallet || (window as any).globalLemmaWallet;
                
                if (!wallet) {
                    throw new Error('Lemma wallet not loaded. Include lemma-wallet.js first.');
                }

                walletRef.current = wallet;
                await wallet.init();

                const info = await wallet.getWalletInfo?.() || {
                    hasPasskey: false,
                    isUnlocked: wallet.isUnlocked?.() || false
                };

                setState({
                    isUnlocked: info.isUnlocked,
                    hasPasskey: info.hasPasskey,
                    isLoading: false,
                    error: null,
                    walletId: info.walletId || null
                });

                if (debug) {
                    console.log('[useLemma] Initialized:', info);
                }
            } catch (error) {
                const err = error instanceof Error ? error : new Error(String(error));
                setState(prev => ({ ...prev, isLoading: false, error: err }));
                onError?.(err);
            }
        };

        init();
    }, [autoInit, debug, onError]);

    // Unlock wallet
    const unlock = useCallback(async () => {
        if (!walletRef.current) {
            throw new Error('Wallet not initialized');
        }

        setState(prev => ({ ...prev, isLoading: true, error: null }));

        try {
            const result = await walletRef.current.unlock();
            
            setState(prev => ({
                ...prev,
                isUnlocked: true,
                isLoading: false,
                walletId: result.walletId || prev.walletId
            }));

            onUnlock?.();
            return result;
        } catch (error) {
            const err = error instanceof Error ? error : new Error(String(error));
            setState(prev => ({ ...prev, isLoading: false, error: err }));
            onError?.(err);
            throw err;
        }
    }, [onUnlock, onError]);

    // Lock wallet
    const lock = useCallback(async () => {
        if (!walletRef.current) return;

        await walletRef.current.lock?.();
        setState(prev => ({ ...prev, isUnlocked: false }));
        onLock?.();
    }, [onLock]);

    // Register passkey
    const registerPasskey = useCallback(async () => {
        if (!walletRef.current) {
            throw new Error('Wallet not initialized');
        }

        setState(prev => ({ ...prev, isLoading: true, error: null }));

        try {
            const result = await walletRef.current.registerPasskey();
            
            setState(prev => ({
                ...prev,
                hasPasskey: true,
                isUnlocked: true,
                isLoading: false,
                walletId: result.walletId || prev.walletId
            }));

            onUnlock?.();
            return result;
        } catch (error) {
            const err = error instanceof Error ? error : new Error(String(error));
            setState(prev => ({ ...prev, isLoading: false, error: err }));
            onError?.(err);
            throw err;
        }
    }, [onUnlock, onError]);

    // Get credentials
    const getCredentials = useCallback(async (type?: string) => {
        if (!walletRef.current) {
            throw new Error('Wallet not initialized');
        }
        return walletRef.current.getCredentials?.(type) || walletRef.current.getLemmas?.();
    }, []);

    // Store credential
    const storeCredential = useCallback(async (credential: any) => {
        if (!walletRef.current) {
            throw new Error('Wallet not initialized');
        }
        return walletRef.current.storeCredential?.(credential) || walletRef.current.storeLemma?.(credential);
    }, []);

    // Verify credential
    const verifyCredential = useCallback(async (credential: any) => {
        if (!walletRef.current) {
            throw new Error('Wallet not initialized');
        }
        return walletRef.current.verifyCredential?.(credential) || walletRef.current.verifyLemma?.(credential);
    }, []);

    return {
        // State
        ...state,
        wallet: walletRef.current,
        
        // Methods
        unlock,
        lock,
        registerPasskey,
        getCredentials,
        storeCredential,
        verifyCredential
    };
}

/**
 * Session management hook
 * Provides session state and extension methods for cross-site authentication.
 */
export function useLemmaSession(options: UseLemmaSessionOptions = {}) {
    const {
        autoManage = false,
        checkInterval = 30 * 60 * 1000, // 30 minutes
        autoExtend = false,
        onSessionExpired,
        onExtensionNeeded
    } = options;

    const [session, setSession] = useState<LemmaSessionState>({
        valid: false,
        authenticated: false,
        expiresAt: null,
        timeRemaining: null,
        canExtend: true,
        extensionCount: 0,
        shouldPromptExtend: false
    });

    const [isExtending, setIsExtending] = useState(false);
    const managerRef = useRef<any>(null);

    // Check session state
    const checkSession = useCallback(async () => {
        const wallet = (window as any).lemmaWallet || (window as any).globalLemmaWallet;
        
        if (!wallet?.getSessionState) {
            return session;
        }

        try {
            const state = await wallet.getSessionState();
            
            const newSession: LemmaSessionState = {
                valid: state.valid || state.authenticated || false,
                authenticated: state.authenticated || false,
                expiresAt: state.expiresAt || null,
                timeRemaining: state.timeRemaining || null,
                canExtend: state.canExtend ?? true,
                extensionCount: state.extensionCount || 0,
                shouldPromptExtend: state.shouldPromptExtend || false
            };

            setSession(newSession);
            return newSession;
        } catch (error) {
            console.warn('[useLemmaSession] Check failed:', error);
            return session;
        }
    }, [session]);

    // Extend session
    const extendSession = useCallback(async () => {
        const wallet = (window as any).lemmaWallet || (window as any).globalLemmaWallet;
        
        if (!wallet?.extendBridgeSession) {
            throw new Error('Session extension not available');
        }

        setIsExtending(true);

        try {
            const result = await wallet.extendBridgeSession();
            
            if (result.success) {
                setSession(prev => ({
                    ...prev,
                    expiresAt: result.expiresAt,
                    extensionCount: result.extensionCount,
                    canExtend: result.extensionsRemaining > 0,
                    shouldPromptExtend: false
                }));
            }

            return result;
        } finally {
            setIsExtending(false);
        }
    }, []);

    // Auto-manage session
    useEffect(() => {
        if (!autoManage) return;

        const startManager = (window as any).startLemmaSessionManager;
        
        if (!startManager) {
            console.warn('[useLemmaSession] Session manager not available');
            return;
        }

        managerRef.current = startManager({
            checkInterval,
            autoExtend,
            onSessionExpired: () => {
                setSession(prev => ({ ...prev, valid: false, authenticated: false }));
                onSessionExpired?.();
            },
            onExtensionNeeded: async (state: any) => {
                const newSession: LemmaSessionState = {
                    valid: state.valid || false,
                    authenticated: state.authenticated || false,
                    expiresAt: state.expiresAt || null,
                    timeRemaining: state.timeRemaining || null,
                    canExtend: state.canExtend ?? true,
                    extensionCount: state.extensionCount || 0,
                    shouldPromptExtend: true
                };
                setSession(newSession);

                if (onExtensionNeeded) {
                    return onExtensionNeeded(newSession);
                }
                return autoExtend;
            }
        });

        // Initial check
        checkSession();

        return () => {
            managerRef.current?.stop?.();
        };
    }, [autoManage, checkInterval, autoExtend, onSessionExpired, onExtensionNeeded, checkSession]);

    // Time remaining countdown
    const formattedTimeRemaining = useMemo(() => {
        if (!session.timeRemaining) return null;
        
        const minutes = Math.floor(session.timeRemaining / 60000);
        const hours = Math.floor(minutes / 60);
        
        if (hours > 0) {
            return `${hours}h ${minutes % 60}m`;
        }
        return `${minutes}m`;
    }, [session.timeRemaining]);

    return {
        session,
        isExtending,
        formattedTimeRemaining,
        checkSession,
        extendSession,
        stopManager: () => managerRef.current?.stop?.()
    };
}

/**
 * Credential verification hook
 * Provides methods for verifying credentials with caching.
 */
export function useLemmaVerification() {
    const [isVerifying, setIsVerifying] = useState(false);
    const [lastResult, setLastResult] = useState<any>(null);
    const [error, setError] = useState<Error | null>(null);

    const verify = useCallback(async (credential: any) => {
        const wallet = (window as any).lemmaWallet || (window as any).globalLemmaWallet;
        
        if (!wallet) {
            throw new Error('Lemma wallet not available');
        }

        setIsVerifying(true);
        setError(null);

        try {
            const result = await (wallet.verifyLemma?.(credential) || wallet.verifyCredential?.(credential));
            setLastResult(result);
            return result;
        } catch (err) {
            const error = err instanceof Error ? err : new Error(String(err));
            setError(error);
            throw error;
        } finally {
            setIsVerifying(false);
        }
    }, []);

    const quickVerify = useCallback(async (credential: any) => {
        const wallet = (window as any).lemmaWallet || (window as any).globalLemmaWallet;
        
        if (!wallet?.quickVerify) {
            return verify(credential);
        }

        setIsVerifying(true);
        setError(null);

        try {
            const result = await wallet.quickVerify(credential);
            setLastResult(result);
            return result;
        } catch (err) {
            const error = err instanceof Error ? err : new Error(String(err));
            setError(error);
            throw error;
        } finally {
            setIsVerifying(false);
        }
    }, [verify]);

    return {
        isVerifying,
        lastResult,
        error,
        verify,
        quickVerify,
        clearResult: () => setLastResult(null),
        clearError: () => setError(null)
    };
}

// Default export
export default {
    useLemma,
    useLemmaSession,
    useLemmaVerification
};
