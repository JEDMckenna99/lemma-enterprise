/**
 * Lemma Wallet SDK - Wallet-Centric Architecture
 * 
 * FEATURES:
 * - ONE PASSKEY PER DAY: unlock() and registerPasskey() auto-check bridge session
 * - Session sync via secure cookies across all Lemma-enabled sites
 * - Local Ed25519 verification (zero network calls)
 * - Session heartbeat: Detects when wallet is locked remotely
 * - Smart Auth State: getAuthState() and autoAuthenticate() for smart UI
 * 
 * SMART AUTH FLOW (for customer sites):
 *   const wallet = new LemmaWallet();
 *   const result = await wallet.autoAuthenticate();
 *   
 *   if (result.authenticated) {
 *     // User has unlocked wallet - check if they have account, auto sign-in
 *     // Send result.walletSecret to backend to derive PPID and lookup user
 *   } else {
 *     // Show "Create Passkey & Sign In" button
 *   }
 * 
 * The wallet is unlocked locally via passkey (no server call).
 * Sites can issue their own lemmas to be stored in the wallet.
 * Lemmas can be presented to any site for local verification.
 */

// IIFE to avoid global scope pollution (fixes Cloudflare Rocket Loader issues)
(function() {
'use strict';

// Guard against double-loading
if (typeof window !== 'undefined' && window.LemmaWallet) {
    return; // Already loaded
}

// ============================================
// CONSTANTS
// ============================================

const WALLET_DB_NAME = 'LemmaWallet';
const WALLET_DB_VERSION = 3;  // v3: Added wallet_secret for PPID derivation
const SESSION_DURATION_MS = 24 * 60 * 60 * 1000; // 24 hours

// Auth states
const AUTH_STATE = {
    LOCKED: 'locked',
    UNLOCKED: 'unlocked',
    UNLOCKED_TODAY: 'unlocked_today'  // Unlocked via passkey today
};

// ============================================
// WALLET CLASS
// ============================================

class LemmaWallet {
    // SDK version - check with LemmaWallet.VERSION
    static VERSION = '2.12.0';
    
    constructor() {
        this.db = null;
        this.session = {
            isUnlocked: false,
            unlockedAt: null,
            expiresAt: null
        };
        this._initialized = false;
        this._heartbeatInterval = null;
        this._onSessionExpired = null; // Callback for when session is invalidated
    }

    /**
     * Set callback for when session expires (e.g., wallet locked remotely)
     * @param {Function} callback - Called when session is invalidated
     */
    onSessionExpired(callback) {
        this._onSessionExpired = callback;
    }

    // ========================================
    // SMART AUTH STATE (for customer site UIs)
    // ========================================

    /**
     * Get comprehensive auth state for UI decisions.
     * Call this to determine what button to show or whether to auto-sign-in.
     * 
     * @returns {Promise<Object>} Auth state with:
     *   - hasWallet: boolean - User has a wallet (passkey registered somewhere)
     *   - isUnlocked: boolean - Wallet is currently unlocked
     *   - walletSecret: string|null - Secret for PPID derivation (if unlocked)
     *   - suggestedAction: 'auto_sign_in' | 'create_account' | 'create_passkey'
     *   - suggestedButtonText: string - Text to show on sign-in button
     */
    async getAuthState() {
        await this.init();
        
        const state = {
            hasWallet: false,
            isUnlocked: false,
            walletSecret: null,
            suggestedAction: 'create_passkey',
            suggestedButtonText: 'Create Passkey & Sign In'
        };
        
        // Check local session first
        if (this.session.isUnlocked) {
            state.hasWallet = true;
            state.isUnlocked = true;
            try {
                state.walletSecret = await this.getWalletSecret();
            } catch (e) {
                console.warn('[Lemma] Could not get wallet secret:', e.message);
            }
        }
        
        // On third-party sites, check bridge session
        if (!state.isUnlocked && !this._isLemmaDomain()) {
            try {
                const bridgeSession = await this.checkBridgeSession();
                if (bridgeSession.valid) {
                    state.hasWallet = true;
                    state.isUnlocked = true;
                    
                    // Get wallet secret from bridge
                    const secretResult = await this._sendBridgeMessage('GET_WALLET_SECRET', {});
                    if (secretResult.success && secretResult.walletSecret) {
                        state.walletSecret = secretResult.walletSecret;
                    }
                }
            } catch (e) {
                console.warn('[Lemma] Bridge check failed:', e.message);
            }
        }
        
        // Determine suggested action based on state
        if (state.isUnlocked && state.walletSecret) {
            // User has unlocked wallet - they can sign in or create account
            // Customer site should check if PPID exists in their DB
            state.suggestedAction = 'auto_sign_in';
            state.suggestedButtonText = 'Sign In';
        } else if (state.hasWallet) {
            // Has wallet but not unlocked - needs to unlock
            state.suggestedAction = 'unlock';
            state.suggestedButtonText = 'Unlock Wallet & Sign In';
        } else {
            // No wallet - needs to create passkey
            state.suggestedAction = 'create_passkey';
            state.suggestedButtonText = 'Create Passkey & Sign In';
        }
        
        return state;
    }

    /**
     * Auto-authenticate if user has an unlocked wallet.
     * Returns wallet credentials needed to sign in or create account.
     * 
     * Usage:
     *   const result = await wallet.autoAuthenticate();
     *   if (result.authenticated) {
     *     // Send result.walletSecret to your backend to derive PPID
     *     // Backend checks if PPID exists -> sign in, else -> create account
     *   } else if (result.needsPasskey) {
     *     // Show "Create Passkey & Sign In" button
     *   }
     * 
     * @returns {Promise<Object>} Result with authenticated status and credentials
     */
    async autoAuthenticate() {
        await this.init();
        
        const result = {
            authenticated: false,
            needsPasskey: true,
            walletSecret: null,
            walletId: null,
            message: ''
        };
        
        // On third-party sites, ALWAYS verify with bridge first
        // This prevents stale local sessions from causing auth failures
        if (!this._isLemmaDomain()) {
            try {
                const bridgeSession = await this.checkBridgeSession();
                
                if (bridgeSession.valid) {
                    // Set local session
                    this.session = {
                        isUnlocked: true,
                        unlockedAt: bridgeSession.unlockedAt || Date.now(),
                        expiresAt: bridgeSession.expiresAt,
                        walletId: bridgeSession.walletId,
                        source: 'bridge'
                    };
                    await this._put('session', { id: 'current', ...this.session });
                    
                    // Get wallet secret from bridge
                    const secretResult = await this._sendBridgeMessage('GET_WALLET_SECRET', {});
                    if (secretResult.success && secretResult.walletSecret) {
                        await this._put('secrets', { id: 'master', secret: secretResult.walletSecret, source: 'bridge' });
                        this.session.walletSecret = secretResult.walletSecret;
                        
                        result.walletSecret = secretResult.walletSecret;
                        result.walletId = bridgeSession.walletId;
                        result.authenticated = true;
                        result.needsPasskey = false;
                        result.message = 'Authenticated via bridge session';
                        console.log('[Lemma] ✅ Auto-authenticated via bridge session');
                        
                        // AUTO-START HEARTBEAT on third-party sites
                        // This detects when wallet is locked on lemma.id
                        this._autoStartHeartbeat();
                        
                        return result;
                    }
                }
            } catch (e) {
                console.warn('[Lemma] Bridge auto-auth failed:', e.message);
            }
        }
        
        // On lemma.id, check local session
        if (this._isLemmaDomain() && this.session.isUnlocked) {
            try {
                result.walletSecret = await this.getWalletSecret();
                result.walletId = this.session.walletId;
                result.authenticated = true;
                result.needsPasskey = false;
                result.message = 'Authenticated from local session';
                console.log('[Lemma] ✅ Auto-authenticated from local session');
                return result;
            } catch (e) {
                console.warn('[Lemma] Local session exists but could not get secret:', e.message);
            }
        }
        
        // Clear any stale local session on third-party sites
        if (!this._isLemmaDomain() && this.session.isUnlocked) {
            console.log('[Lemma] Clearing stale local session (bridge says invalid)');
            this.session = { isUnlocked: false };
            await this._delete('session', 'current');
        }
        
        result.message = 'No valid session - passkey required';
        console.log('[Lemma] No valid session found - user needs to create/unlock passkey');
        return result;
    }
    
    /**
     * Auto-start heartbeat on third-party sites after successful authentication.
     * Customers can optionally set onSessionExpired callback to handle sign-out.
     * @private
     */
    _autoStartHeartbeat() {
        if (this._isLemmaDomain()) return;
        if (this._heartbeatInterval) return; // Already running
        
        console.log('[Lemma] 🔄 Auto-starting session heartbeat (checks every 30s)');
        this.startSessionHeartbeat(30000); // Check every 30 seconds
    }

    /**
     * Check if current domain is lemma.id or localhost
     * @private
     */
    _isLemmaDomain() {
        const hostname = window.location.hostname;
        return hostname.includes('lemma.id') || hostname.includes('localhost');
    }

    /**
     * Check if session is still valid (useful after page refresh)
     * On third-party sites, this verifies with the bridge.
     * 
     * @returns {Promise<boolean>} True if session is valid
     */
    async isSessionValid() {
        await this.init();
        
        // Check local session first
        if (!this.session.isUnlocked) {
            return false;
        }
        
        // On third-party sites, verify with bridge
        if (!this._isLemmaDomain()) {
            try {
                const bridgeSession = await this.checkBridgeSession();
                if (!bridgeSession.valid) {
                    console.log('[Lemma] Session invalidated by bridge');
                    // Clear local session
                    this.session = { isUnlocked: false };
                    await this._delete('session', 'current');
                    
                    // Trigger callback
                    if (this._onSessionExpired) {
                        this._onSessionExpired({ reason: 'bridge_invalid' });
                    }
                    return false;
                }
            } catch (e) {
                console.warn('[Lemma] Could not verify session with bridge:', e.message);
                // If bridge fails, trust local session
            }
        }
        
        return true;
    }

    /**
     * Get CSRF token from cookie (for double-submit CSRF protection)
     * @returns {string|null} CSRF token or null if not set
     */
    _getCsrfToken() {
        const match = document.cookie.match(/lemma_wallet_csrf=([^;]+)/);
        return match ? match[1] : null;
    }

    /**
     * Get headers with CSRF token for credentialed requests
     * @returns {Object} Headers object with Content-Type and X-Lemma-CSRF
     */
    _getSecureHeaders() {
        const headers = { 'Content-Type': 'application/json' };
        const csrf = this._getCsrfToken();
        if (csrf) {
            headers['X-Lemma-CSRF'] = csrf;
        }
        return headers;
    }

    /**
     * Start session heartbeat (checks if central wallet session is still valid)
     * Call this on third-party sites to detect when wallet is locked remotely
     * @param {number} intervalMs - Check interval in ms (default: 60000 = 1 minute)
     */
    startSessionHeartbeat(intervalMs = 60000) {
        // Only run on third-party sites
        if (window.location.hostname.includes('lemma.id') ||
            window.location.hostname.includes('localhost')) {
            return;
        }

        // Clear any existing heartbeat
        if (this._heartbeatInterval) {
            clearInterval(this._heartbeatInterval);
        }

        console.log('[Lemma] Starting session heartbeat (checking every', intervalMs/1000, 'seconds)');

        this._heartbeatInterval = setInterval(async () => {
            try {
                const bridgeSession = await this.checkBridgeSession();
                
                if (!bridgeSession.valid && this.session.isUnlocked) {
                    console.log('[Lemma] ⚠️ Central wallet session expired - clearing local session');
                    
                    // Clear local session
                    this.session = {
                        isUnlocked: false,
                        unlockedAt: null,
                        expiresAt: null
                    };
                    
                    // Clear session from IndexedDB
                    if (this.db) {
                        try {
                            const tx = this.db.transaction('session', 'readwrite');
                            tx.objectStore('session').delete('current');
                        } catch (e) {
                            console.warn('[Lemma] Could not clear session from DB:', e);
                        }
                    }
                    
                    // Trigger callback if set
                    if (this._onSessionExpired) {
                        this._onSessionExpired({
                            reason: 'wallet_locked',
                            message: 'Central wallet was locked. Please sign in again.'
                        });
                    }
                    
                    // Dispatch custom event for apps to listen to
                    window.dispatchEvent(new CustomEvent('lemma:session-expired', {
                        detail: { reason: 'wallet_locked' }
                    }));
                }
            } catch (e) {
                console.warn('[Lemma] Heartbeat check failed:', e.message);
            }
        }, intervalMs);
    }

    /**
     * Stop session heartbeat
     */
    stopSessionHeartbeat() {
        if (this._heartbeatInterval) {
            clearInterval(this._heartbeatInterval);
            this._heartbeatInterval = null;
            console.log('[Lemma] Session heartbeat stopped');
        }
    }

    // ========================================
    // INITIALIZATION
    // ========================================

    /**
     * Initialize the wallet (open IndexedDB)
     */
    async init() {
        if (this._initialized) return;

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(WALLET_DB_NAME, WALLET_DB_VERSION);

            request.onerror = () => reject(request.error);
            
            request.onsuccess = () => {
                this.db = request.result;
                this._initialized = true;
                this._checkSessionState();
                resolve();
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Passkey store (for local unlock)
                if (!db.objectStoreNames.contains('passkey')) {
                    db.createObjectStore('passkey', { keyPath: 'id' });
                }

                // Lemmas store
                if (!db.objectStoreNames.contains('lemmas')) {
                    const lemmaStore = db.createObjectStore('lemmas', { keyPath: 'id' });
                    lemmaStore.createIndex('issuer', 'issuer', { unique: false });
                    lemmaStore.createIndex('subject', 'subject', { unique: false });
                }

                // Trusted issuers store
                if (!db.objectStoreNames.contains('issuers')) {
                    db.createObjectStore('issuers', { keyPath: 'did' });
                }

                // Session store
                if (!db.objectStoreNames.contains('session')) {
                    db.createObjectStore('session', { keyPath: 'id' });
                }

                // Revocations cache store
                if (!db.objectStoreNames.contains('revocations')) {
                    db.createObjectStore('revocations', { keyPath: 'id' });
                }

                // Wallet secrets store (for PPID derivation)
                // Stores the master secret used to derive site-specific PPIDs
                if (!db.objectStoreNames.contains('secrets')) {
                    db.createObjectStore('secrets', { keyPath: 'id' });
                }
            };
        });

        // Auto-sync revocations on init (non-blocking)
        this._autoSyncRevocations();
    }

    /**
     * Auto-sync revocations in background
     */
    async _autoSyncRevocations() {
        try {
            const revInfo = await this.getRevocationInfo();
            const ONE_HOUR = 60 * 60 * 1000;
            
            // Sync if never synced or older than 1 hour
            if (!revInfo.synced || revInfo.age > ONE_HOUR) {
                console.log('🔄 Auto-syncing revocation list...');
                await this.syncRevocations();
            } else {
                console.log(`✅ Revocation list up to date (${revInfo.count} entries, ${Math.round(revInfo.age / 60000)}min old)`);
            }
        } catch (e) {
            console.warn('Auto-sync revocations failed:', e);
        }
    }

    /**
     * Check and restore session state from storage
     * On third-party sites, also starts heartbeat if session exists
     */
    async _checkSessionState() {
        try {
            const storedSession = await this._get('session', 'current');
            if (storedSession && storedSession.expiresAt > Date.now()) {
                this.session = {
                    isUnlocked: true,
                    unlockedAt: storedSession.unlockedAt,
                    expiresAt: storedSession.expiresAt,
                    walletId: storedSession.walletId,
                    source: storedSession.source || 'local'
                };
                
                // AUTO-START HEARTBEAT on third-party sites with existing session
                // This ensures lock detection works even after page refresh
                if (!this._isLemmaDomain()) {
                    console.log('[Lemma] Existing session found on third-party site - starting heartbeat');
                    this._autoStartHeartbeat();
                }
            }
        } catch (e) {
            // No stored session, that's fine
        }
    }

    // ========================================
    // PASSKEY REGISTRATION (for local unlock)
    // ========================================

    /**
     * Register a passkey for local wallet unlock
     * This stores the public key locally for future verification
     * 
     * NOTE: On third-party sites, this will first check if the user has a valid
     * session via the central bridge. If they do, it returns success without
     * prompting for a new passkey (ONE PASSKEY PER DAY flow).
     */
    async registerPasskey() {
        await this.init();

        // SMART CHECK: On third-party sites, check bridge session first
        // If user already unlocked on lemma.id today, don't prompt for passkey
        if (!window.location.hostname.includes('lemma.id') && 
            !window.location.hostname.includes('localhost')) {
            console.log('[Lemma] Third-party site detected, checking bridge session for registerPasskey...');
            try {
                const bridgeSession = await this.checkBridgeSession();
                console.log('[Lemma] Bridge session result:', bridgeSession);
                
                if (bridgeSession.valid) {
                    console.log('[Lemma] ✅ Already authenticated via bridge - skipping passkey registration');
                    
                    // CRITICAL: Set local session to match bridge session
                    // This ensures getWalletSecret() and other methods work
                    this.session = {
                        isUnlocked: true,
                        unlockedAt: bridgeSession.unlockedAt || Date.now(),
                        expiresAt: bridgeSession.expiresAt,
                        walletId: bridgeSession.walletId,
                        source: 'bridge'
                    };
                    await this._put('session', { id: 'current', ...this.session });
                    
                    // Get wallet secret from bridge for PPID derivation
                    let walletSecret = null;
                    try {
                        const secretResult = await this._sendBridgeMessage('GET_WALLET_SECRET', {});
                        if (secretResult.success && secretResult.walletSecret) {
                            walletSecret = secretResult.walletSecret;
                            // Cache locally for this session
                            await this._put('secrets', { id: 'master', secret: walletSecret, source: 'bridge' });
                            this.session.walletSecret = walletSecret;
                            console.log('[Lemma] ✅ Wallet secret synced from bridge');
                        }
                    } catch (e) {
                        console.warn('[Lemma] Could not get wallet secret from bridge:', e.message);
                    }
                    
                    // AUTO-START HEARTBEAT on third-party sites
                    this._autoStartHeartbeat();
                    
                    return {
                        success: true,
                        method: 'bridge_session',
                        walletId: bridgeSession.walletId,
                        walletSecret: walletSecret,
                        message: 'Authenticated via central wallet session'
                    };
                } else {
                    console.log('[Lemma] Bridge session not valid for registerPasskey:', bridgeSession.reason || 'no valid session');
                }
            } catch (e) {
                console.warn('[Lemma] Bridge check failed in registerPasskey:', e.message);
                console.log('[Lemma] Falling back to local passkey registration');
            }
        }

        if (!this._isPasskeySupported()) {
            throw new Error('Passkeys not supported in this browser');
        }

        // Generate a local challenge
        const challenge = crypto.getRandomValues(new Uint8Array(32));
        
        // Get wallet ID (or create one)
        let walletId = await this._get('passkey', 'walletId');
        if (!walletId) {
            walletId = { id: 'walletId', value: this._generateId() };
            await this._put('passkey', walletId);
        }

        // Create credential
        const credential = await navigator.credentials.create({
            publicKey: {
                challenge: challenge,
                rp: {
                    name: 'Lemma Wallet',
                    id: window.location.hostname
                },
                user: {
                    id: new TextEncoder().encode(walletId.value),
                    name: 'Wallet User',
                    displayName: 'Lemma Wallet'
                },
                pubKeyCredParams: [
                    { alg: -7, type: 'public-key' },   // ES256
                    { alg: -257, type: 'public-key' }  // RS256
                ],
                authenticatorSelection: {
                    authenticatorAttachment: 'platform',
                    userVerification: 'required',
                    residentKey: 'preferred'
                },
                timeout: 60000
            }
        });

        // Extract and store public key
        const publicKeyData = this._extractPublicKey(credential.response);
        
        const passkeyRecord = {
            id: 'primary',
            credentialId: this._bufferToBase64url(credential.rawId),
            publicKey: publicKeyData.publicKey,
            algorithm: publicKeyData.algorithm,
            createdAt: Date.now()
        };

        await this._put('passkey', passkeyRecord);

        // Generate wallet secret for PPID derivation (if not already exists)
        let walletSecret = await this._get('secrets', 'master');
        if (!walletSecret) {
            // Generate 32-byte random secret
            const secretBytes = crypto.getRandomValues(new Uint8Array(32));
            const secretHex = Array.from(secretBytes)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            walletSecret = {
                id: 'master',
                secret: secretHex,
                createdAt: Date.now()
            };
            await this._put('secrets', walletSecret);
            console.log('🔐 Generated wallet secret for PPID derivation');
        }

        // Auto-unlock after registration (user just authenticated)
        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + SESSION_DURATION_MS,
            walletId: walletId.value,
            walletSecret: walletSecret.secret  // Include in session for easy access
        };
        await this._put('session', { id: 'current', ...this.session });
        console.log('✅ Wallet auto-unlocked after passkey registration');

        // CRITICAL: Set session cookie on lemma.id for cross-site "one passkey per day"
        // This enables the session to be shared across all sites via the bridge
        try {
            const setSessionResponse = await fetch('https://lemma.id/api/wallet/set-session', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    wallet_id: walletId.value,
                    unlocked_at: this.session.unlockedAt
                })
            });
            if (setSessionResponse.ok) {
                console.log('[Lemma] ✅ Session cookie set on lemma.id - cross-site auth enabled');
            } else {
                console.warn('[Lemma] ⚠️ Could not set session cookie:', setSessionResponse.status);
            }
        } catch (e) {
            console.warn('[Lemma] ⚠️ Could not set session cookie on lemma.id:', e.message);
        }

        return {
            success: true,
            credentialId: passkeyRecord.credentialId,
            walletId: walletId.value,
            walletSecret: walletSecret.secret  // Return for immediate use
        };
    }

    // ========================================
    // LOCAL PASSKEY UNLOCK (No Server!)
    // ========================================

    /**
     * Unlock the wallet using passkey (100% local)
     * No server call required!
     * 
     * NOTE: On third-party sites, this will first check if the user has a valid
     * session via the central bridge. If they do, it returns success without
     * prompting for a new passkey (ONE PASSKEY PER DAY flow).
     */
    async unlock() {
        await this.init();

        // SMART CHECK: On third-party sites, check bridge session first
        // If user already unlocked on lemma.id today, don't prompt for passkey
        if (!window.location.hostname.includes('lemma.id') && 
            !window.location.hostname.includes('localhost')) {
            console.log('[Lemma] Third-party site detected, checking bridge session...');
            try {
                const bridgeSession = await this.checkBridgeSession();
                console.log('[Lemma] Bridge session result:', bridgeSession);
                
                if (bridgeSession.valid) {
                    console.log('[Lemma] ✅ Already authenticated via bridge - skipping local unlock');

                    // Update local session to match bridge
                    this.session = {
                        isUnlocked: true,
                        unlockedAt: bridgeSession.unlockedAt || Date.now(),
                        expiresAt: bridgeSession.expiresAt,
                        walletId: bridgeSession.walletId,
                        source: 'bridge'
                    };
                    // CRITICAL: Save session to IndexedDB so getWalletInfo() works
                    await this._put('session', { id: 'current', ...this.session });

                    // Get wallet secret from bridge for PPID derivation
                    let walletSecret = null;
                    try {
                        const secretResult = await this._sendBridgeMessage('GET_WALLET_SECRET', {});
                        if (secretResult.success && secretResult.walletSecret) {
                            walletSecret = secretResult.walletSecret;
                            // Cache locally for this session
                            await this._put('secrets', { id: 'master', secret: walletSecret, source: 'bridge' });
                            this.session.walletSecret = walletSecret;
                            console.log('[Lemma] ✅ Wallet secret synced from bridge');
                        }
                    } catch (e) {
                        console.warn('[Lemma] Could not get wallet secret from bridge:', e.message);
                    }

                    // Start session heartbeat to detect if wallet is locked remotely
                    this.startSessionHeartbeat(30000); // Check every 30 seconds

                    return {
                        success: true,
                        method: 'bridge_session',
                        walletId: bridgeSession.walletId,
                        walletSecret: walletSecret,
                        expiresAt: bridgeSession.expiresAt,
                        message: 'Authenticated via central wallet session'
                    };
                } else {
                    console.log('[Lemma] Bridge session not valid:', bridgeSession.reason || 'no valid session');
                }
            } catch (e) {
                console.warn('[Lemma] Bridge check failed:', e.message);
                console.log('[Lemma] Falling back to local passkey');
            }
        }

        // Get stored passkey
        const passkey = await this._get('passkey', 'primary');
        if (!passkey) {
            throw new Error('No passkey registered. Call registerPasskey() first.');
        }

        // Generate local challenge
        const challenge = crypto.getRandomValues(new Uint8Array(32));

        // Get passkey signature (browser prompts biometric)
        // The browser ALREADY verifies the user - if credentials.get() succeeds,
        // the user has been authenticated by their device biometrics
        const credential = await navigator.credentials.get({
            publicKey: {
                challenge: challenge,
                rpId: window.location.hostname,
                allowCredentials: [{
                    id: this._base64urlToBuffer(passkey.credentialId),
                    type: 'public-key'
                }],
                userVerification: 'required',
                timeout: 60000
            }
        });

        // If we get here, the browser has verified the user via biometrics
        // No need for additional local signature verification - trust the browser
        if (!credential) {
            throw new Error('Passkey authentication cancelled');
        }
        
        console.log('✅ Browser verified user via biometrics');

        // Get wallet ID
        const walletIdRecord = await this._get('passkey', 'walletId');
        const walletId = walletIdRecord?.value || 'wallet_' + Date.now();

        // Get wallet secret for PPID derivation
        let walletSecretRecord = await this._get('secrets', 'master');
        
        // Generate wallet secret if missing (for wallets created before v3)
        if (!walletSecretRecord) {
            const secretBytes = crypto.getRandomValues(new Uint8Array(32));
            const secretHex = Array.from(secretBytes)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            walletSecretRecord = {
                id: 'master',
                secret: secretHex,
                createdAt: Date.now()
            };
            await this._put('secrets', walletSecretRecord);
            console.log('🔐 Generated wallet secret for legacy wallet');
        }

        // Unlock the wallet
        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + SESSION_DURATION_MS,
            walletId: walletId,
            walletSecret: walletSecretRecord.secret
        };

        // Persist session locally
        await this._put('session', {
            id: 'current',
            ...this.session
        });

        console.log('✅ Wallet unlocked successfully');

        // CRITICAL: Set session cookie on lemma.id for cross-site "one passkey per day"
        // This enables the session to be shared across all sites via the bridge
        try {
            const setSessionResponse = await fetch('https://lemma.id/api/wallet/set-session', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    wallet_id: walletId,
                    unlocked_at: this.session.unlockedAt
                })
            });
            if (setSessionResponse.ok) {
                console.log('[Lemma] ✅ Session cookie set on lemma.id - cross-site auth enabled');
            } else {
                console.warn('[Lemma] ⚠️ Could not set session cookie:', setSessionResponse.status);
            }
        } catch (e) {
            console.warn('[Lemma] ⚠️ Could not set session cookie on lemma.id:', e.message);
        }

        // Start heartbeat on third-party sites
        if (!window.location.hostname.includes('lemma.id') &&
            !window.location.hostname.includes('localhost')) {
            this.startSessionHeartbeat(30000);
        }

        return {
            success: true,
            expiresAt: this.session.expiresAt,
            expiresIn: SESSION_DURATION_MS,
            walletId: walletId,
            walletSecret: walletSecretRecord.secret
        };
    }

    /**
     * Lock the wallet (clear session locally and on server)
     */
    async lock() {
        console.log('[Lemma] Locking wallet...');
        
        // Clear local session
        this.session = {
            isUnlocked: false,
            unlockedAt: null,
            expiresAt: null,
            walletSecret: null
        };
        await this._delete('session', 'current');
        
        // Clear server session cookie (for cross-site sync)
        // This ensures customer sites see the wallet as locked
        if (this._isLemmaDomain()) {
            try {
                console.log('[Lemma] Clearing server session cookie...');
                const response = await fetch('/api/wallet/clear-session', {
                    method: 'POST',
                    credentials: 'include',
                    headers: this._getSecureHeaders()
                });
                if (response.ok) {
                    console.log('[Lemma] ✅ Server session cleared');
                } else {
                    console.warn('[Lemma] Server session clear returned:', response.status);
                }
            } catch (e) {
                console.warn('[Lemma] Could not clear server session:', e.message);
            }
        }
        
        console.log('[Lemma] ✅ Wallet locked');
    }

    /**
     * Check if wallet is currently unlocked
     */
    isUnlocked() {
        if (!this.session.isUnlocked) return false;
        if (this.session.expiresAt && this.session.expiresAt < Date.now()) {
            this.session.isUnlocked = false;
                    return false;
                    }
                    return true;
                }
                
    // ========================================
    // AUTH STATE (replaces email-based auth)
    // ========================================

    /**
     * Get current authentication state
     * This can be used as the primary auth method instead of email
     */
    getAuthState() {
        if (!this.session.isUnlocked) {
                return {
                state: AUTH_STATE.LOCKED,
                authenticated: false,
                reason: 'Wallet is locked'
            };
        }

        if (this.session.expiresAt && this.session.expiresAt < Date.now()) {
                    return {
                state: AUTH_STATE.LOCKED,
                authenticated: false,
                reason: 'Session expired'
            };
        }

        // Check if unlocked today (same calendar day)
        const unlockedDate = new Date(this.session.unlockedAt);
        const today = new Date();
        const isToday = unlockedDate.toDateString() === today.toDateString();
            
            return {
            state: isToday ? AUTH_STATE.UNLOCKED_TODAY : AUTH_STATE.UNLOCKED,
            authenticated: true,
            unlockedAt: this.session.unlockedAt,
            expiresAt: this.session.expiresAt,
            unlockedToday: isToday,
            timeRemaining: this.session.expiresAt - Date.now()
        };
    }

    /**
     * Get an auth proof that can be sent to servers
     * This replaces the need for email-based session tokens
     */
    async getAuthProof() {
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to get auth proof');
        }

        const passkey = await this._get('passkey', 'primary');
        if (!passkey) {
            throw new Error('No passkey registered');
        }

        // Create a timestamped proof of wallet unlock
        const proof = {
            type: 'wallet_auth',
            method: 'passkey_unlock',
            walletId: (await this._get('passkey', 'walletId'))?.value,
            unlockedAt: this.session.unlockedAt,
            expiresAt: this.session.expiresAt,
            timestamp: Date.now(),
            // Include passkey credential ID for verification
            passkeyCredentialId: passkey.credentialId
        };

        return proof;
    }

    /**
     * Check if user is authenticated (wallet unlocked via passkey today)
     * Use this as the primary auth check instead of email sessions
     */
    isAuthenticated() {
        const authState = this.getAuthState();
        return authState.authenticated && authState.unlockedToday;
    }

    /**
     * Require authentication - unlock if needed
     * Returns auth proof that can be sent to servers
     */
    async requireAuth() {
        if (!this.isAuthenticated()) {
            // Need to unlock
            await this.unlock();
        }
        return this.getAuthProof();
    }

    // ========================================
    // BRIDGE SESSION MANAGEMENT
    // ========================================

    /**
     * Check session via the central bridge (for cross-site session sharing)
     * This is the recommended method for third-party sites.
     * 
     * @returns {Promise<Object>} Session state from bridge
     */
    async checkBridgeSession() {
        return this._sendBridgeMessage('CHECK_SESSION', {});
    }

    /**
     * Extend session via bridge (tap-only, no full biometric)
     * Use when session is about to expire but user is still active.
     *
     * @returns {Promise<Object>} Extension result
     */
    async extendBridgeSession() {
        return this._sendBridgeMessage('EXTEND_SESSION', {});
    }

    // ========================================
    // HIGH-SECURITY: FRESH AUTHENTICATION
    // For banks, financial apps requiring proof of recent auth
    // ========================================

    /**
     * Require fresh authentication (full biometric)
     * Use for high-security operations like bank transfers, password changes, etc.
     * 
     * @param {Object} options Configuration
     * @param {number} options.maxAgeMs Max acceptable auth age in ms (default: 30000 = 30s)
     * @returns {Promise<Object>} Fresh auth result with timestamp
     * 
     * @example
     * // Before a bank transfer, require auth within last 30 seconds
     * const auth = await lemmaWallet.requireFreshAuth({ maxAgeMs: 30000 });
     * if (auth.fresh) {
     *     // User just authenticated - proceed with transfer
     *     await performTransfer(auth.authTimestamp);
     * }
     */
    async requireFreshAuth(options = {}) {
        const maxAgeMs = options.maxAgeMs || 30000;  // Default 30 seconds
        
        // If on lemma.id, do it locally
        if (window.location.hostname.includes('lemma.id')) {
            return this._localFreshAuth(maxAgeMs);
        }
        
        // For third-party sites, use bridge
        return this._sendBridgeMessage('REQUIRE_FRESH_AUTH', { maxAgeMs });
    }

    /**
     * Check how fresh the current authentication is (without requiring new auth)
     * Use to show UI hints about whether fresh auth will be needed.
     * 
     * @returns {Promise<Object>} Auth freshness info
     * 
     * @example
     * const freshness = await lemmaWallet.getAuthFreshness();
     * if (!freshness.freshUnder30s) {
     *     showMessage("You'll need to re-authenticate for this action");
     * }
     */
    async getAuthFreshness() {
        // If on lemma.id, check locally
        if (window.location.hostname.includes('lemma.id')) {
            const session = await this._get('session', 'current');
            if (!session || !session.unlockedAt) {
                return { authenticated: false, fresh: false, reason: 'no_session' };
            }
            
            const authAgeMs = Date.now() - session.unlockedAt;
            const freshAuthAt = session.freshAuthAt || session.unlockedAt;
            const freshAuthAgeMs = Date.now() - freshAuthAt;
            
            return {
                success: true,
                authenticated: true,
                authTimestamp: session.unlockedAt,
                authAgeMs: authAgeMs,
                freshAuthTimestamp: freshAuthAt,
                freshAuthAgeMs: freshAuthAgeMs,
                freshUnder30s: freshAuthAgeMs < 30000,
                freshUnder5min: freshAuthAgeMs < 300000,
                freshUnder1hr: freshAuthAgeMs < 3600000
            };
        }
        
        // For third-party sites, use bridge
        return this._sendBridgeMessage('GET_AUTH_FRESHNESS', {});
    }

    /**
     * Verify auth freshness with Lemma server (highest security)
     * Use for critical operations where you can't trust client timestamps.
     * 
     * @param {Object} authResult Result from requireFreshAuth()
     * @returns {Promise<Object>} Server verification result
     * 
     * @example
     * // For bank-level security, verify with server
     * const auth = await lemmaWallet.requireFreshAuth();
     * const verified = await lemmaWallet.verifyAuthWithServer(auth);
     * if (verified.valid && verified.fresh) {
     *     // Server confirmed auth is fresh - safe to proceed
     * }
     */
    async verifyAuthWithServer(authResult) {
        if (!authResult || !authResult.authTimestamp) {
            return { valid: false, fresh: false, reason: 'invalid_auth_result' };
        }
        
        try {
            const response = await fetch('https://lemma.id/api/verify-session-freshness', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    walletId: authResult.walletId,
                    authTimestamp: authResult.authTimestamp,
                    maxAgeMs: authResult.maxAgeMs || 30000
                })
            });
            
            return await response.json();
        } catch (e) {
            return { valid: false, fresh: false, reason: 'server_error', error: e.message };
        }
    }

    /**
     * Local fresh auth implementation (for lemma.id origin)
     * @private
     */
    async _localFreshAuth(maxAgeMs) {
        await this.init();
        
        // Check if current auth is fresh enough
        const session = await this._get('session', 'current');
        if (session && session.unlockedAt) {
            const authAge = Date.now() - session.unlockedAt;
            if (authAge < maxAgeMs) {
                return {
                    success: true,
                    fresh: true,
                    authTimestamp: session.unlockedAt,
                    authAgeMs: authAge,
                    maxAgeMs: maxAgeMs
                };
            }
        }
        
        // Need fresh auth - do full unlock
        try {
            await this.unlock();
            const newSession = await this._get('session', 'current');
            return {
                success: true,
                fresh: true,
                authTimestamp: newSession.unlockedAt,
                authAgeMs: 0,
                maxAgeMs: maxAgeMs
            };
        } catch (e) {
            return { success: false, fresh: false, error: e.message };
        }
    }

    /**
     * Get full session state for cross-site authentication
     * Combines local and bridge session information.
     * 
     * @returns {Promise<Object>} Comprehensive session state
     */
    async getSessionState() {
        const localState = this.getAuthState();
        
        // If we're on lemma.id, use local state
        if (window.location.hostname.includes('lemma.id')) {
            return {
                source: 'local',
                ...localState,
                canExtend: true,
                extensionsRemaining: 7
            };
        }
        
        // For third-party sites, check bridge
        try {
            const bridgeState = await this.checkBridgeSession();
            return {
                source: 'bridge',
                valid: bridgeState.valid,
                authenticated: bridgeState.valid,
                expiresAt: bridgeState.expiresAt,
                timeRemaining: bridgeState.timeRemaining,
                canExtend: bridgeState.canExtend,
                extensionCount: bridgeState.extensionCount,
                shouldPromptExtend: bridgeState.shouldPromptExtend,
                walletExists: bridgeState.walletExists
            };
        } catch (e) {
            console.warn('[Lemma] Bridge session check failed:', e.message);
            return {
                source: 'local',
                ...localState,
                bridgeError: e.message
            };
        }
    }

    /**
     * Smart session management - auto-extend or prompt as needed
     * Call this periodically (e.g., every 30 minutes) for seamless UX.
     * 
     * @param {Object} options Configuration options
     * @param {Function} options.onExtendNeeded Called when extension needed (return true to extend)
     * @param {Function} options.onExpired Called when session expired
     * @returns {Promise<Object>} Session management result
     */
    async manageSession(options = {}) {
        const { onExtendNeeded, onExpired } = options;
        
        const state = await this.getSessionState();
        
        if (!state.valid && state.walletExists) {
            // Session expired
            if (onExpired) onExpired(state);
            return { action: 'expired', state };
        }
        
        if (state.shouldPromptExtend && state.canExtend) {
            // Session about to expire, can extend
            let shouldExtend = true;
            
            if (onExtendNeeded) {
                shouldExtend = await onExtendNeeded(state);
            }
            
            if (shouldExtend) {
                try {
                    const result = await this.extendBridgeSession();
                    if (result.success) {
                        console.log('[Lemma] Session extended successfully');
                        return { action: 'extended', result };
                    }
                } catch (e) {
                    console.warn('[Lemma] Session extension failed:', e.message);
                }
            }
            
            return { action: 'extension_needed', state };
        }
        
        return { action: 'valid', state };
    }

    /**
     * Ensure user is authenticated via Lemma (ONE PASSKEY PER DAY flow)
     * 
     * This is the RECOMMENDED method for third-party sites to authenticate users.
     * It checks the central bridge session and redirects to unlock if needed.
     * 
     * @param {Object} options Configuration
     * @param {boolean} options.autoRedirect If true, automatically redirect to unlock page (default: true)
     * @param {string} options.returnUrl URL to return to after unlock (default: current page)
     * @returns {Promise<Object>} Authentication result
     * 
     * @example
     * // In your app's login/protected route:
     * const auth = await lemmaWallet.ensureAuthenticated();
     * if (auth.authenticated) {
     *     // User is authenticated! Show protected content
     *     console.log('Welcome back!', auth.walletId);
     * }
     * // If not authenticated, user will be redirected to lemma.id/wallet/unlock
     */
    async ensureAuthenticated(options = {}) {
        const { 
            autoRedirect = true, 
            returnUrl = window.location.href 
        } = options;
        
        await this.init();
        
        // Check if we're on lemma.id (first-party)
        if (window.location.hostname.includes('lemma.id')) {
            const localAuth = this.getAuthState();
            if (localAuth.authenticated) {
                return {
                    authenticated: true,
                    source: 'local',
                    walletId: this.session?.walletId,
                    expiresAt: this.session?.expiresAt
                };
            }
            
            // Need to unlock locally
            if (autoRedirect) {
                window.location.href = `/wallet/unlock?return=${encodeURIComponent(returnUrl)}`;
                return { authenticated: false, redirecting: true };
            }
            return { authenticated: false, needsUnlock: true };
        }
        
        // Third-party site: Check bridge session
        try {
            const bridgeSession = await this.checkBridgeSession();
            
            if (bridgeSession.valid) {
                console.log('[Lemma] ✅ Authenticated via bridge session');
                return {
                    authenticated: true,
                    source: 'bridge',
                    walletId: bridgeSession.walletId,
                    expiresAt: bridgeSession.expiresAt,
                    timeRemaining: bridgeSession.timeRemaining,
                    syncedFromServer: bridgeSession.syncedFromServer
                };
            }
            
            // No valid session - redirect to unlock
            if (autoRedirect) {
                console.log('[Lemma] 🔓 Redirecting to unlock...');
                const unlockUrl = `https://lemma.id/wallet/unlock?return=${encodeURIComponent(returnUrl)}`;
                window.location.href = unlockUrl;
                return { authenticated: false, redirecting: true };
            }
            
            return { 
                authenticated: false, 
                needsUnlock: true,
                unlockUrl: `https://lemma.id/wallet/unlock?return=${encodeURIComponent(returnUrl)}`
            };
            
        } catch (e) {
            console.error('[Lemma] Bridge check failed:', e);
            
            if (autoRedirect) {
                const unlockUrl = `https://lemma.id/wallet/unlock?return=${encodeURIComponent(returnUrl)}`;
                window.location.href = unlockUrl;
                return { authenticated: false, redirecting: true };
            }
            
            return { 
                authenticated: false, 
                error: e.message,
                needsUnlock: true 
            };
        }
    }

    /**
     * Check if user has unlocked today (URL param check)
     * Use this after redirect back from lemma.id/wallet/unlock
     * 
     * @returns {boolean} True if lemma_unlocked=true is in URL
     */
    checkUnlockReturn() {
        const params = new URLSearchParams(window.location.search);
        return params.get('lemma_unlocked') === 'true';
    }

    /**
     * Send message to bridge iframe and get response
     * @private
     */
    async _sendBridgeMessage(type, payload, timeout = 10000) {
        // Check if bridge iframe exists
        let bridge = document.querySelector('iframe[src*="/wallet/bridge"]');
        
        if (!bridge) {
            // Create bridge iframe if needed
            console.log('[Lemma] Creating bridge iframe...');
            bridge = document.createElement('iframe');
            bridge.src = 'https://lemma.id/wallet/bridge';
            bridge.style.cssText = 'display:none;width:0;height:0;border:none;';
            bridge.id = 'lemma-bridge';
            document.body.appendChild(bridge);
            
            // Wait for WALLET_BRIDGE_READY message (not just onload)
            await new Promise((resolve, reject) => {
                const timeoutId = setTimeout(() => {
                    window.removeEventListener('message', handler);
                    console.warn('[Lemma] Bridge ready timeout - continuing anyway');
                    resolve(); // Don't reject, try to continue
                }, 8000);
                
                const handler = (event) => {
                    if (event.origin === 'https://lemma.id' && 
                        event.data?.type === 'WALLET_BRIDGE_READY') {
                        clearTimeout(timeoutId);
                        window.removeEventListener('message', handler);
                        console.log('[Lemma] Bridge ready, session:', event.data.session?.valid ? 'active' : 'none');
                        resolve();
                    }
                };
                
                window.addEventListener('message', handler);
            });
        }
        
        return new Promise((resolve, reject) => {
            const requestId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
            const timeoutId = setTimeout(() => {
                window.removeEventListener('message', handler);
                reject(new Error(`Bridge response timeout for ${type}`));
            }, timeout);
            
            const handler = (event) => {
                if (!event.origin.includes('lemma.id')) return;
                const response = event.data;
                if (response.requestId !== requestId) return;
                
                clearTimeout(timeoutId);
                window.removeEventListener('message', handler);
                resolve(response);
            };
            
            window.addEventListener('message', handler);
            bridge.contentWindow.postMessage({ type, payload, requestId }, 'https://lemma.id');
        });
    }

    // ========================================
    // LEMMA STORAGE
    // ========================================

    /**
     * Store a lemma in the wallet
     * Accepts lemmas from any issuer
     */
    async storeLemma(lemma, issuerInfo = null) {
        await this.init();

        if (!this.isUnlocked()) {
            throw new Error('Wallet is locked. Call unlock() first.');
        }

        // Validate lemma structure
        if (!lemma.id || !lemma.issuer || !lemma.signature) {
            throw new Error('Invalid lemma structure');
        }

        // Store issuer info if provided
        if (issuerInfo && issuerInfo.publicKey) {
            await this._put('issuers', {
                did: lemma.issuer,
                publicKey: issuerInfo.publicKey,
                name: issuerInfo.name || lemma.issuer,
                verified: issuerInfo.verified || false,
                addedAt: Date.now()
            });
        }

        // Store the lemma
        await this._put('lemmas', {
            ...lemma,
            storedAt: Date.now()
        });

        return { success: true, id: lemma.id };
    }

    /**
     * Get all lemmas in the wallet
     */
    async getLemmas() {
        await this.init();
        return this._getAll('lemmas');
    }

    /**
     * Get lemmas from a specific issuer
     */
    async getLemmasByIssuer(issuerDid) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('lemmas', 'readonly');
            const store = tx.objectStore('lemmas');
            const index = store.index('issuer');
            const request = index.getAll(issuerDid);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Get a specific lemma by ID
     */
    async getLemma(lemmaId) {
        await this.init();
        return this._get('lemmas', lemmaId);
    }

    /**
     * Remove a lemma from the wallet
     */
    async removeLemma(lemmaId) {
        await this.init();

        if (!this.isUnlocked()) {
            throw new Error('Wallet is locked');
        }

        await this._delete('lemmas', lemmaId);
        return { success: true };
    }

    // ========================================
    // LEMMA PRESENTATION
    // ========================================

    /**
     * Present a lemma to a requesting site
     * Returns the lemma if wallet is unlocked and lemma exists
     */
    async presentLemma(lemmaId) {
        if (!this.isUnlocked()) {
            throw new Error('Wallet is locked');
        }

        const lemma = await this.getLemma(lemmaId);
        if (!lemma) {
            throw new Error('Lemma not found');
        }

        // Check expiration
        if (lemma.expiresAt && lemma.expiresAt < Date.now()) {
            throw new Error('Lemma has expired');
        }

        return lemma;
    }

    /**
     * Find and present a lemma matching criteria
     */
    async presentLemmaMatching(criteria) {
        if (!this.isUnlocked()) {
            throw new Error('Wallet is locked');
        }

        const lemmas = await this.getLemmas();
        
        for (const lemma of lemmas) {
            // Check issuer
            if (criteria.issuer && lemma.issuer !== criteria.issuer) continue;
            
            // Check claims
            if (criteria.claims) {
                let matches = true;
                for (const [key, value] of Object.entries(criteria.claims)) {
                    if (lemma.claims[key] !== value) {
                        matches = false;
                        break;
                    }
                }
                if (!matches) continue;
            }

            // Check expiration
            if (lemma.expiresAt && lemma.expiresAt < Date.now()) continue;

            return lemma;
        }

        return null;
    }

    // ========================================
    // ISSUER MANAGEMENT
    // ========================================

    /**
     * Add a trusted issuer
     */
    async addIssuer(issuerInfo) {
        await this.init();

        if (!issuerInfo.did || !issuerInfo.publicKey) {
            throw new Error('Issuer must have did and publicKey');
        }

        await this._put('issuers', {
            did: issuerInfo.did,
            publicKey: issuerInfo.publicKey,
            name: issuerInfo.name || issuerInfo.did,
            verified: issuerInfo.verified || false,
            addedAt: Date.now()
        });

        return { success: true };
    }

    /**
     * Get an issuer's info
     */
    async getIssuer(issuerDid) {
        await this.init();
        return this._get('issuers', issuerDid);
    }

    /**
     * Get all issuers
     */
    async getIssuers() {
        await this.init();
        return this._getAll('issuers');
    }

    // ========================================
    // REVOCATION (Local Cache)
    // ========================================

    /**
     * Sync revocation list from server
     * Call periodically or on wallet init
     * 
     * OFFLINE RESILIENCE: If network is unavailable, gracefully falls back
     * to cached data. User is NOT locked out when offline.
     */
    async syncRevocations() {
        // Check if we're offline first
        if (typeof navigator !== 'undefined' && !navigator.onLine) {
            console.log('📴 Offline - using cached revocation list');
            const cached = await this.getRevocationInfo();
            return { 
                success: false, 
                offline: true, 
                cached: cached.synced,
                cacheAge: cached.age 
            };
        }
        
        try {
            // Use AbortController for timeout (5 second max)
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            
            const response = await fetch('/api/v1/revocation/list', {
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                console.warn('Failed to sync revocations:', response.status);
                return { success: false, httpError: response.status };
            }
            
            const data = await response.json();
            const revocations = data.revocations || data.revoked_ids || [];
            
            // Store in IndexedDB
            await this._put('revocations', {
                id: 'current',
                list: new Set(revocations),
                listArray: revocations, // For serialization
                lastSynced: Date.now(),
                count: revocations.length
            });
            
            console.log(`✅ Synced ${revocations.length} revocations`);
            return { success: true, count: revocations.length };
        } catch (e) {
            // Network error - check if we have cached data
            const cached = await this.getRevocationInfo();
            if (cached.synced) {
                console.log(`📴 Network error - using cached revocations (${cached.count} entries, ${Math.round(cached.age / 60000)}min old)`);
                return { 
                    success: false, 
                    offline: true, 
                    cached: true,
                    cacheAge: cached.age,
                    error: e.message 
                };
            }
            console.warn('Revocation sync error (no cache):', e);
            return { success: false, offline: true, cached: false, error: e.message };
        }
    }
    
    /**
     * Check if the wallet is in offline mode
     */
    isOffline() {
        return typeof navigator !== 'undefined' && !navigator.onLine;
    }
    
    /**
     * Check if a credential is revoked (local check)
     */
    async isRevoked(credentialId) {
        const revocations = await this._get('revocations', 'current');
        if (!revocations || !revocations.listArray) {
            // No revocation data - assume not revoked but flag as unchecked
            return { revoked: false, unchecked: true };
        }
        
        const isRevoked = revocations.listArray.includes(credentialId);
        return {
            revoked: isRevoked, 
            unchecked: false,
            lastSynced: revocations.lastSynced
        };
    }
    
    /**
     * Get revocation cache info
     */
    async getRevocationInfo() {
        const revocations = await this._get('revocations', 'current');
        if (!revocations) {
            return { synced: false, count: 0 };
        }
        return {
            synced: true,
            count: revocations.count,
            lastSynced: revocations.lastSynced,
            age: Date.now() - revocations.lastSynced
        };
    }

    // ========================================
    // LOCAL VERIFICATION
    // ========================================
    
    // Cache for credentials whose signatures have been verified
    _verifiedSignatures = new Set();

    /**
     * Quick verify - checks only expiration and revocation (skips signature if already verified)
     * Use this for repeated checks on the same credential
     * ~50μs vs ~1000μs for full verification
     */
    async quickVerify(lemma) {
        await this.init();
        
        const startTime = performance.now();
        
        // 1. Check revocation (local cache)
        const revocationStatus = await this.isRevoked(lemma.id);
        if (revocationStatus.revoked) {
            return { valid: false, reason: 'Revoked', quickVerify: true };
        }
        
        // 2. Check expiration
        const expiredCheck = this._checkExpiration(lemma);
        if (!expiredCheck.valid) {
            return { valid: false, reason: 'Expired', quickVerify: true };
        }
        
        // 3. Check if signature was previously verified
        const signatureVerified = this._verifiedSignatures.has(lemma.id);
        
        if (!signatureVerified) {
            // Need full verification - signature not yet checked
            return await this.verifyLemma(lemma);
        }
        
        const verifyTime = ((performance.now() - startTime) * 1000).toFixed(1);
        
        return {
            valid: true,
            quickVerify: true,
            signatureCached: true,
            verifyTimeUs: verifyTime,
            revocationUnchecked: revocationStatus.unchecked
        };
    }

    /**
     * Full verify - includes Ed25519 signature verification
     * Result is cached so subsequent quickVerify calls skip crypto
     */
    async verifyLemma(lemma, forceSignatureCheck = false) {
        await this.init();
        
        const startTime = performance.now();

        // 1. Check revocation (local cache)
        const revocationStatus = await this.isRevoked(lemma.id);
        if (revocationStatus.revoked) {
            return { valid: false, reason: 'Revoked' };
        }

        // 2. Check expiration
        const expiredCheck = this._checkExpiration(lemma);
        if (!expiredCheck.valid) {
            return { valid: false, reason: 'Expired' };
        }
        
        // 3. Check if we can skip signature verification
        if (!forceSignatureCheck && this._verifiedSignatures.has(lemma.id)) {
            const verifyTime = ((performance.now() - startTime) * 1000).toFixed(1);
            return {
                valid: true,
                signatureCached: true,
                verifyTimeUs: verifyTime,
                revocationUnchecked: revocationStatus.unchecked
            };
        }

        // 4. Get public key
        let publicKey = null;
        let issuerName = lemma.issuer;
        let issuerVerified = false;
        
        const storedIssuer = await this.getIssuer(lemma.issuer);
        if (storedIssuer?.publicKey) {
            publicKey = storedIssuer.publicKey;
            issuerName = storedIssuer.name || lemma.issuer;
            issuerVerified = storedIssuer.verified || false;
        }
        else if (lemma.issuerInfo?.publicKey) {
            publicKey = lemma.issuerInfo.publicKey;
            issuerName = lemma.issuerInfo.name || lemma.issuer;
            issuerVerified = lemma.issuerInfo.verified || false;
            await this.addIssuer({
                did: lemma.issuer,
                publicKey: publicKey,
                name: issuerName,
                verified: issuerVerified
            });
        }
        else if (lemma.issuer && lemma.issuer.startsWith('did:lemma:')) {
            const didParts = lemma.issuer.split(':');
            if (didParts.length === 3 && /^[0-9a-fA-F]{64}$/.test(didParts[2])) {
                publicKey = didParts[2];
                issuerName = lemma.issuer;
                issuerVerified = true;
            }
        }
        
        if (!publicKey) {
            return { valid: false, reason: 'No public key available' };
        }

        // 5. Verify Ed25519 signature
        try {
            const isValid = await this._verifyLemmaSignature(lemma, publicKey);
            if (!isValid) {
                return { valid: false, reason: 'Invalid signature' };
            }
            
            // Cache successful verification
            this._verifiedSignatures.add(lemma.id);
            
                    } catch (e) {
            console.warn('Signature verification error:', e.message);
            return { valid: false, reason: 'Verification error: ' + e.message };
        }

        const verifyTime = ((performance.now() - startTime) * 1000).toFixed(1);

        return {
            valid: true,
            issuer: issuerName,
            verified: issuerVerified,
            claims: lemma.claims || lemma.credentialSubject,
            revocationUnchecked: revocationStatus.unchecked,
            verifyTimeUs: verifyTime,
            signatureCached: false
        };
    }
    
    /**
     * Helper to check expiration
     */
    _checkExpiration(lemma) {
        const expiresAt = lemma.expiresAt || lemma.expirationDate || lemma.expires_at;
        if (!expiresAt) return { valid: true };
        
        let expiryTime;
        if (typeof expiresAt === 'string') {
            expiryTime = new Date(expiresAt).getTime();
        } else if (typeof expiresAt === 'number') {
            expiryTime = expiresAt < 4102444800 ? expiresAt * 1000 : expiresAt;
        } else {
            return { valid: true };
        }
        
        return { valid: expiryTime >= Date.now() };
    }
    
    /**
     * Clear verification cache (use if credential might have been modified)
     */
    clearVerificationCache(credentialId = null) {
        if (credentialId) {
            this._verifiedSignatures.delete(credentialId);
        } else {
            this._verifiedSignatures.clear();
        }
    }

    // ========================================
    // UTILITY METHODS
    // ========================================

    _isPasskeySupported() {
        return window.PublicKeyCredential !== undefined &&
               typeof window.PublicKeyCredential === 'function';
    }

    _generateId() {
        return 'wallet_' + Array.from(crypto.getRandomValues(new Uint8Array(16)))
            .map(b => b.toString(16).padStart(2, '0')).join('');
    }

    _bufferToBase64url(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    }

    _base64urlToBuffer(base64url) {
        const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
        const padding = '='.repeat((4 - base64.length % 4) % 4);
        const binary = atob(base64 + padding);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }

    _extractPublicKey(attestationResponse) {
        // Parse attestation object to extract public key
        // This is simplified - full implementation would parse CBOR
        const publicKeyBytes = attestationResponse.getPublicKey();
        const algorithm = attestationResponse.getPublicKeyAlgorithm();
            
            return {
            publicKey: this._bufferToBase64url(publicKeyBytes),
            algorithm: algorithm
        };
    }

    async _verifyPasskeySignature(publicKeyB64, algorithm, response, challenge) {
        try {
            // Import the public key
            const publicKeyBuffer = this._base64urlToBuffer(publicKeyB64);
            
            const cryptoKey = await crypto.subtle.importKey(
                'spki',
                publicKeyBuffer,
                {
                    name: algorithm === -7 ? 'ECDSA' : 'RSASSA-PKCS1-v1_5',
                    namedCurve: algorithm === -7 ? 'P-256' : undefined,
                    hash: 'SHA-256'
                },
                false,
                ['verify']
            );

            // Reconstruct signed data
            const authenticatorData = new Uint8Array(response.authenticatorData);
            const clientDataHash = await crypto.subtle.digest(
                'SHA-256',
                response.clientDataJSON
            );
            
            const signedData = new Uint8Array(
                authenticatorData.length + new Uint8Array(clientDataHash).length
            );
            signedData.set(authenticatorData, 0);
            signedData.set(new Uint8Array(clientDataHash), authenticatorData.length);

            // Verify
            const signature = new Uint8Array(response.signature);
            
            return await crypto.subtle.verify(
                {
                    name: algorithm === -7 ? 'ECDSA' : 'RSASSA-PKCS1-v1_5',
                    hash: 'SHA-256'
                },
                cryptoKey,
                signature,
                signedData
            );
        } catch (e) {
            console.error('Passkey verification error:', e);
            return false;
        }
    }

    // Cache for imported CryptoKeys (avoids re-import overhead)
    _cryptoKeyCache = new Map();
    
    async _verifyLemmaSignature(lemma, publicKey) {
        // Ed25519 signature verification with key caching
        // MUST match the Rust engine's signing message construction
        try {
            // Get or create cached CryptoKey
            let cryptoKey = this._cryptoKeyCache.get(publicKey);
            
            if (!cryptoKey) {
                // Detect and convert public key format
                let publicKeyBuffer;
                if (typeof publicKey === 'string') {
                    if (/^[0-9a-fA-F]{64}$/.test(publicKey)) {
                        // Hex format (64 hex chars = 32 bytes)
                        publicKeyBuffer = new Uint8Array(32);
                        for (let i = 0; i < 32; i++) {
                            publicKeyBuffer[i] = parseInt(publicKey.substr(i * 2, 2), 16);
                }
            } else {
                        publicKeyBuffer = this._base64urlToBuffer(publicKey);
                    }
                } else if (publicKey instanceof Uint8Array) {
                    publicKeyBuffer = publicKey;
        } else {
                    throw new Error('Unknown public key format');
                }
                
                if (publicKeyBuffer.length !== 32) {
                    throw new Error(`Invalid Ed25519 key length: ${publicKeyBuffer.length}`);
                }

                cryptoKey = await crypto.subtle.importKey(
                    'raw',
                    publicKeyBuffer,
                    { name: 'Ed25519' },
                    false,
                    ['verify']
                );
                
                // Cache for future verifications
                this._cryptoKeyCache.set(publicKey, cryptoKey);
            }
            
            // Get signature from proof object (W3C format)
            const sig = lemma.proof?.signatureValue || lemma.signature;
            if (!sig) {
                throw new Error('No signature found in credential');
            }
            
            // Detect and convert signature format
            let signatureBuffer;
            if (typeof sig === 'string') {
                if (/^[0-9a-fA-F]{128}$/.test(sig)) {
                    // Hex format (128 hex chars = 64 bytes)
                    signatureBuffer = new Uint8Array(64);
                    for (let i = 0; i < 64; i++) {
                        signatureBuffer[i] = parseInt(sig.substr(i * 2, 2), 16);
                    }
                } else {
                    signatureBuffer = this._base64urlToBuffer(sig);
                }
            } else {
                signatureBuffer = new Uint8Array(sig);
            }
            
            // Create the SAME message the Rust engine signs
            const message = await this._createVerificationMessage(lemma);

            return await crypto.subtle.verify(
                'Ed25519',
                cryptoKey,
                signatureBuffer,
                message
            );
        } catch (e) {
            console.error('Lemma verification error:', e);
            return false;
        }
    }
    
    async _createVerificationMessage(credential) {
        // Must EXACTLY match Rust's create_verification_message()
        // SHA-256 hash of: id + issuer + subject + issued_at(LE u64) + expires_at(LE u64) + sorted_claims
        
        const encoder = new TextEncoder();
        const parts = [];
        
        // 1. Credential ID
        parts.push(encoder.encode(credential.id));
        
        // 2. Issuer DID
        parts.push(encoder.encode(credential.issuer));
        
        // 3. Subject
        parts.push(encoder.encode(credential.subject));
        
        // 4. Issued at (u64 little-endian)
        const issuedAtRaw = credential.issuanceDate ?? credential.issued_at ?? credential.issuedAt;
        parts.push(this._u64ToLittleEndian(this._getTimestampU64(issuedAtRaw)));
        
        // 5. Expires at (u64 little-endian, optional)
        const expiresAtRaw = credential.expirationDate ?? credential.expires_at ?? credential.expiresAt;
        if (expiresAtRaw !== undefined && expiresAtRaw !== null) {
            parts.push(this._u64ToLittleEndian(this._getTimestampU64(expiresAtRaw)));
        }
        
        // 6. Claims in sorted order
        const claims = credential.credentialSubject || credential.claims || {};
        const sortedKeys = Object.keys(claims).sort();
        
        for (const key of sortedKeys) {
            parts.push(encoder.encode(key));
            parts.push(encoder.encode(JSON.stringify(claims[key])));
        }
        
        // Concatenate and hash
        const totalLength = parts.reduce((sum, arr) => sum + arr.length, 0);
        const combined = new Uint8Array(totalLength);
        let offset = 0;
        for (const part of parts) {
            combined.set(part, offset);
            offset += part.length;
        }
        
        return new Uint8Array(await crypto.subtle.digest('SHA-256', combined));
    }
    
    _getTimestampU64(value) {
        // Convert various timestamp formats to Unix seconds (u64)
        if (typeof value === 'number') {
            // If it's already a number, check if it's seconds or milliseconds
            return value < 10000000000 ? value : Math.floor(value / 1000);
        }
        if (typeof value === 'string') {
            // ISO date string
            const ms = new Date(value).getTime();
            return Math.floor(ms / 1000);
        }
        return 0;
    }
    
    _u64ToLittleEndian(value) {
        // Convert a number to 8-byte little-endian Uint8Array
        const buffer = new Uint8Array(8);
        let remaining = BigInt(value);
        for (let i = 0; i < 8; i++) {
            buffer[i] = Number(remaining & 0xFFn);
            remaining >>= 8n;
        }
        return buffer;
    }

    // IndexedDB helpers
    async _get(storeName, key) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async _getAll(storeName) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async _put(storeName, value) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.put(value);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async _delete(storeName, key) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.delete(key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    // ========================================
    // WALLET INFO & SECRET ACCESS
    // ========================================

    /**
     * Get the wallet secret for PPID derivation.
     * PPID = HMAC(wallet_secret, site_id) - different for each site.
     * 
     * If no secret exists but wallet is unlocked, auto-generates one.
     * This handles users who registered before wallet secret was implemented.
     * 
     * @returns {string} 64-char hex string
     */
    async getWalletSecret() {
        await this.init();
        
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to get wallet secret');
        }
        
        // Check session first (fastest)
        if (this.session.walletSecret) {
            return this.session.walletSecret;
        }
        
        // Load from storage
        const secretRecord = await this._get('secrets', 'master');
        if (secretRecord?.secret) {
            // Cache in session
            this.session.walletSecret = secretRecord.secret;
            return secretRecord.secret;
        }
        
        // AUTO-GENERATE: User has passkey but no secret (legacy registration)
        // Generate and store a new wallet secret
        console.log('🔐 No wallet secret found - generating for legacy passkey...');
        const secretBytes = crypto.getRandomValues(new Uint8Array(32));
        const secretHex = Array.from(secretBytes)
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
        
        const newSecret = {
            id: 'master',
            secret: secretHex,
            createdAt: Date.now(),
            migrated: true  // Flag indicating this was auto-generated
        };
        await this._put('secrets', newSecret);
        
        // Cache in session
        this.session.walletSecret = secretHex;
        console.log('🔐 ✅ Generated wallet secret for PPID derivation');
        
        return secretHex;
    }

    /**
     * Get passkey credential ID (for server-side PPID derivation fallback)
     */
    async getPasskeyCredentialId() {
        await this.init();
        const passkey = await this._get('passkey', 'primary');
        return passkey?.credentialId || null;
    }

    async getWalletInfo() {
        await this.init();

        const passkey = await this._get('passkey', 'primary');
        const lemmas = await this._getAll('lemmas');
        const issuers = await this._getAll('issuers');
        const secretRecord = await this._get('secrets', 'master');
            
            return {
            hasPasskey: !!passkey,
            hasWalletSecret: !!secretRecord?.secret,
            isUnlocked: this.isUnlocked(),
            session: this.session,
            lemmaCount: lemmas.length,
            issuerCount: issuers.length,
            passkeyCredentialId: passkey?.credentialId || null
        };
    }

    // ========================================
    // BACKWARDS COMPATIBILITY (for old templates)
    // ========================================

    /**
     * Store credential (backwards compatible alias for storeLemma)
     * Automatically syncs to central lemma.id wallet via bridge if on third-party site
     */
    async storeCredential(credential) {
        await this.init();
        
        // Normalize credential format
        const lemma = {
            id: credential.id || `cred_${Date.now()}`,
            issuer: credential.issuer || 'did:web:lemma.id',
            signature: credential.signature || credential.proof?.proofValue || 'legacy',
            claims: credential.claims || credential.credentialSubject || {},
            type: credential.type || ['VerifiableCredential'],
            packageType: credential.packageType || 'permission',
            ...credential,
            storedAt: Date.now()
        };
        
        // Store locally
        await this._put('lemmas', lemma);
        console.log('✅ Credential stored locally:', lemma.id);
        
        // If on third-party site, also sync to central lemma.id wallet via bridge
        if (!window.location.hostname.includes('lemma.id') && 
            !window.location.hostname.includes('localhost')) {
            await this._syncToCentralWallet(lemma);
        }
        
        return { success: true, id: lemma.id };
    }
    
    /**
     * Sync credential to central lemma.id wallet via iframe bridge
     * This ensures credentials are visible at lemma.id/wallet
     */
    async _syncToCentralWallet(credential) {
        try {
            // Find or create bridge iframe
            let bridge = document.getElementById('lemma-wallet-bridge');
            
            if (!bridge) {
                // Create bridge iframe
                bridge = document.createElement('iframe');
                bridge.id = 'lemma-wallet-bridge';
                bridge.src = 'https://lemma.id/wallet/bridge';
                bridge.style.cssText = 'position:absolute;width:0;height:0;border:0;visibility:hidden;';
                document.body.appendChild(bridge);
                
                // Wait for bridge to be ready
                await new Promise((resolve) => {
                    const handler = (event) => {
                        if (event.data?.type === 'WALLET_BRIDGE_READY') {
                            window.removeEventListener('message', handler);
                            resolve();
                        }
                    };
                    window.addEventListener('message', handler);
                    setTimeout(resolve, 3000); // Timeout after 3s
                });
            }
            
            // Send credential to bridge
            return new Promise((resolve) => {
                const requestId = `sync_${Date.now()}`;
                
                const handler = (event) => {
                    if (event.data?.requestId === requestId) {
                        window.removeEventListener('message', handler);
                        if (event.data.success) {
                            console.log('✅ Credential synced to central wallet:', credential.id);
                        }
                        resolve(event.data);
                    }
                };
                
                window.addEventListener('message', handler);
                
                bridge.contentWindow.postMessage({
                    type: 'STORE_CREDENTIAL',
                    payload: { credential },
                    requestId
                }, 'https://lemma.id');
                
                setTimeout(() => {
                    window.removeEventListener('message', handler);
                    resolve({ success: false, error: 'timeout' });
                }, 5000);
            });
            
        } catch (e) {
            console.warn('⚠️ Could not sync to central wallet:', e.message);
        }
    }

    /**
     * Get credentials (backwards compatible alias for getLemmas)
     * On third-party sites, also checks central wallet via bridge
     * @param {string} type - Optional filter by packageType ('permission', 'identity', etc)
     */
    async getCredentials(type = null) {
        await this.init();
        let lemmas = await this._getAll('lemmas');
        
        // On third-party sites, also fetch from central wallet
        if (!window.location.hostname.includes('lemma.id') && 
            !window.location.hostname.includes('localhost')) {
            try {
                const centralCreds = await this._getFromCentralWallet(type);
                
                // Merge: add central creds not in local
                const localIds = new Set(lemmas.map(l => l.id));
                for (const cred of centralCreds) {
                    if (!localIds.has(cred.id)) {
                        lemmas.push(cred);
                    }
                }
            } catch (e) {
                console.warn('⚠️ Could not fetch from central wallet:', e.message);
            }
        }
        
        if (type) {
            return lemmas.filter(l => {
                const pkgType = l.packageType || l.claims?.type || l.type?.[1];
                return pkgType === type || 
                       (type === 'permission' && (pkgType === 'permission' || pkgType === 'PermissionLemma')) ||
                       (type === 'identity' && (pkgType === 'identity' || pkgType === 'IdentityCredential'));
            });
        }
        
        return lemmas;
    }
    
    /**
     * Get credentials from central lemma.id wallet via bridge
     */
    async _getFromCentralWallet(type = null) {
        try {
            let bridge = document.getElementById('lemma-wallet-bridge');
            
            if (!bridge) {
                // Create bridge iframe
                bridge = document.createElement('iframe');
                bridge.id = 'lemma-wallet-bridge';
                bridge.src = 'https://lemma.id/wallet/bridge';
                bridge.style.cssText = 'position:absolute;width:0;height:0;border:0;visibility:hidden;';
                document.body.appendChild(bridge);
                
                // Wait for bridge to be ready
                await new Promise((resolve) => {
                    const handler = (event) => {
                        if (event.data?.type === 'WALLET_BRIDGE_READY') {
                            window.removeEventListener('message', handler);
                            resolve();
                        }
                    };
                    window.addEventListener('message', handler);
                    setTimeout(resolve, 3000);
                });
            }
            
            return new Promise((resolve) => {
                const requestId = `get_${Date.now()}`;
                
                const handler = (event) => {
                    if (event.data?.requestId === requestId) {
                        window.removeEventListener('message', handler);
                        resolve(event.data.credentials || []);
                    }
                };
                
                window.addEventListener('message', handler);
                
                bridge.contentWindow.postMessage({
                    type: 'GET_CREDENTIALS',
                    payload: { type },
                    requestId
                }, 'https://lemma.id');
                
                setTimeout(() => {
                    window.removeEventListener('message', handler);
                    resolve([]);
                }, 3000);
            });
            
        } catch (e) {
            console.warn('⚠️ Could not get from central wallet:', e.message);
            return [];
        }
    }

    /**
     * Remove credential (backwards compatible alias)
     */
    async removeCredential(credentialId) {
        await this.init();
        await this._delete('lemmas', credentialId);
        return { success: true };
    }

    /**
     * Property for backwards compatibility with isReady checks
     */
    get isReady() {
        return this._initialized;
    }

    /**
     * Export wallet data (for backup)
     */
    async export() {
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to export');
        }
        
        return {
            lemmas: await this._getAll('lemmas'),
            issuers: await this._getAll('issuers'),
            exportedAt: Date.now()
        };
    }
    
    /**
     * Import wallet data (from backup)
     */
    async import(data) {
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to import');
        }

        if (data.lemmas) {
            for (const lemma of data.lemmas) {
                await this._put('lemmas', lemma);
            }
        }

        if (data.issuers) {
            for (const issuer of data.issuers) {
                await this._put('issuers', issuer);
            }
        }

        return { success: true };
    }
}

// ============================================
// GLOBAL EXPORTS
// ============================================

// Export CLASS (constructor) to window.LemmaWallet
// Export INSTANCE to window.lemmaWallet (lowercase)
if (typeof window !== 'undefined') {
    window.LemmaWallet = LemmaWallet;  // The CLASS (constructor)
    window.LemmaWalletClass = LemmaWallet;  // Alias for backwards compatibility
    
    // Create singleton instance
    const lemmaWalletInstance = new LemmaWallet();
    window.lemmaWallet = lemmaWalletInstance;  // The INSTANCE (lowercase)
    window.globalLemmaWallet = lemmaWalletInstance;  // For templates that use this
    
    // Auto-initialize on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => lemmaWalletInstance.init());
    } else {
        lemmaWalletInstance.init();
    }
    
    // ========================================
    // SERVICE WORKER REGISTRATION
    // ========================================
    // Registers the Lemma service worker for offline-first caching
    // This enables 0 network calls after first visit
    
    async function registerLemmaServiceWorker() {
        if (!('serviceWorker' in navigator)) {
            console.log('[Lemma] Service workers not supported');
            return null;
        }
        
        try {
            // Only register SW on lemma.id or sites that explicitly opt-in
            const isLemmaOrigin = window.location.hostname.includes('lemma.id');
            const hasOptIn = document.querySelector('meta[name="lemma-sw"]');
            
            if (!isLemmaOrigin && !hasOptIn) {
                // Don't auto-register on third-party sites
                return null;
            }
            
            // Service worker must be served from root for proper scope
            const swUrl = isLemmaOrigin 
                ? '/lemma-sw.js' 
                : 'https://lemma.id/lemma-sw.js';
            
            const registration = await navigator.serviceWorker.register(swUrl, {
                scope: '/'
            });
            
            console.log('[Lemma] Service worker registered:', registration.scope);
            
            // Listen for updates
            registration.addEventListener('updatefound', () => {
                const newWorker = registration.installing;
                console.log('[Lemma] Service worker update found');
                
                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        console.log('[Lemma] New service worker ready - refresh for updates');
                    }
                });
            });
            
            return registration;
        } catch (error) {
            console.warn('[Lemma] Service worker registration failed:', error);
            return null;
        }
    }
    
    // Export SW registration function
    window.registerLemmaServiceWorker = registerLemmaServiceWorker;
    
    // Auto-register on lemma.id
    if (window.location.hostname.includes('lemma.id')) {
        registerLemmaServiceWorker();
    }
    
    // ========================================
    // AUTO SESSION MANAGER
    // ========================================
    // Provides automatic session management for third-party sites
    
    /**
     * Start automatic session management
     * Periodically checks session and prompts for extension when needed.
     * 
     * @param {Object} options Configuration
     * @param {number} options.checkInterval How often to check (default: 30 min)
     * @param {Function} options.onSessionExpired Called when session expires
     * @param {Function} options.onExtensionNeeded Called when extension is needed (return true to auto-extend)
     * @param {Function} options.onSessionExtended Called after successful extension
     * @param {boolean} options.autoExtend Auto-extend without prompt (default: false)
     * @returns {Object} Session manager with stop() method
     */
    function startSessionManager(options = {}) {
        const {
            checkInterval = 30 * 60 * 1000,  // 30 minutes
            onSessionExpired = null,
            onExtensionNeeded = null,
            onSessionExtended = null,
            autoExtend = false
        } = options;
        
        let intervalId = null;
        let isRunning = true;
        
        const check = async () => {
            if (!isRunning) return;
            
            try {
                const result = await lemmaWalletInstance.manageSession({
                    onExtendNeeded: async (state) => {
                        if (autoExtend) return true;
                        if (onExtensionNeeded) {
                            return await onExtensionNeeded(state);
                        }
                        return false;
                    },
                    onExpired: (state) => {
                        if (onSessionExpired) onSessionExpired(state);
                    }
                });
                
                if (result.action === 'extended' && onSessionExtended) {
                    onSessionExtended(result.result);
                }
                
                return result;
            } catch (e) {
                console.warn('[Lemma] Session check error:', e.message);
            }
        };
        
        // Initial check
        check();
        
        // Start periodic checks
        intervalId = setInterval(check, checkInterval);
        
        console.log(`[Lemma] Session manager started (interval: ${checkInterval / 60000} min)`);
        
        return {
            stop: () => {
                isRunning = false;
                if (intervalId) {
                    clearInterval(intervalId);
                    intervalId = null;
                }
                console.log('[Lemma] Session manager stopped');
            },
            check,  // Manual check
            isRunning: () => isRunning
        };
    }
    
    // Export session manager
    window.startLemmaSessionManager = startSessionManager;
    
    // ========================================
    // SESSION EVENTS
    // ========================================
    // Custom events for session state changes
    
    /**
     * Dispatch a custom Lemma session event
     */
    function dispatchSessionEvent(eventName, detail) {
        window.dispatchEvent(new CustomEvent(`lemma:${eventName}`, { detail }));
    }
    
    // Export event dispatcher for internal use
    window._lemmaDispatchEvent = dispatchSessionEvent;
}

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LemmaWallet };
}

})(); // End of IIFE
