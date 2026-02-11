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
 *     // User proved possession of their wallet via passkey
 *     // Derive their PPID (site-specific identifier) - NO network call!
 *     const ppid = await wallet.derivePPID('yoursite.com');
 *     
 *     // Send ppid to YOUR backend to sign-in or create account
 *     const response = await fetch('/api/auth', {
 *       method: 'POST',
 *       body: JSON.stringify({ ppid })
 *     });
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
const WALLET_DB_VERSION = 4;  // v4: Added profiles for multiple identities
const DEFAULT_SESSION_HOURS = 24;
const DEFAULT_PROFILE_ID = 'default';

// Get user's session duration preference (stored in localStorage by wallet settings page)
function getSessionDurationMs() {
    try {
        const hours = parseInt(localStorage.getItem('lemma_session_hours')) || DEFAULT_SESSION_HOURS;
        // Clamp between 1 and 24 hours for safety
        const clampedHours = Math.max(1, Math.min(24, hours));
        return clampedHours * 60 * 60 * 1000;
    } catch (e) {
        return DEFAULT_SESSION_HOURS * 60 * 60 * 1000;
    }
}

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
    // v2.32.0: Redirect-only architecture - removed popup flow for simpler, consistent UX
    static VERSION = '2.50.0';  // Sub-5ms verification: pre-hydrated caches, debug-gated logging, no bridge
    
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
        
        // Performance: Cache for global session checks (avoid redundant API calls)
        this._globalSessionCache = {
            result: null,
            timestamp: 0,
            ttlMs: 5000,  // Cache valid for 5 seconds
            pendingPromise: null  // Deduplicate concurrent requests
        };
        
        // Performance: Debounce heartbeat checks
        this._lastHeartbeatCheck = 0;
        this._heartbeatDebounceMs = 2000;  // Min 2s between checks
        
        // Performance: Debug logging (set LemmaWallet.DEBUG = true to enable)
        this._debug = false;
    }
    
    /** @private Log only when debug is enabled */
    _log(...args) { if (this._debug) console.log(...args); }
    _warn(...args) { if (this._debug) console.warn(...args); }

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
     * v2.45.0: On third-party sites, uses local lemma verification (no wallet_secret needed)
     * 
     * @returns {Promise<Object>} Auth state with:
     *   - hasWallet: boolean - User has a wallet (passkey registered somewhere)
     *   - isUnlocked: boolean - Wallet is currently unlocked
     *   - walletSecret: string|null - Secret for PPID derivation (only on lemma.id)
     *   - ppid: string|null - PPID from local lemma (on third-party sites)
     *   - suggestedAction: 'auto_sign_in' | 'create_account' | 'redirect'
     *   - suggestedButtonText: string - Text to show on sign-in button
     */
    async getAuthState() {
        await this.init();
        
        const state = {
            hasWallet: false,
            isUnlocked: false,
            walletSecret: null,
            ppid: null,
            suggestedAction: 'redirect',
            suggestedButtonText: 'Sign In with Lemma',
            // Device linking info
            canLinkDevice: false,
            linkDeviceUrl: 'https://lemma.id/link'
        };
        
        // ============================================================
        // THIRD-PARTY SITES: Use local lemma verification (no network)
        // ============================================================
        if (!this._isLemmaDomain()) {
            const authResult = await this.verifyLocalAuthorization();
            
            if (authResult.authorized) {
                state.hasWallet = true;
                state.isUnlocked = true;
                state.ppid = authResult.ppid;
                state.suggestedAction = 'auto_sign_in';
                state.suggestedButtonText = 'Sign In';
                return state;
            }
            
            // Not authorized - determine why
            if (authResult.reason === 'wallet_locked' || authResult.reason === 'session_expired') {
                state.hasWallet = true;  // They have a wallet, just locked
                state.suggestedAction = 'redirect';
                state.suggestedButtonText = 'Unlock Wallet';
            } else {
                // No lemma for this site
                state.suggestedAction = 'redirect';
                state.suggestedButtonText = 'Sign In with Lemma';
            }
            
            return state;
        }
        
        // ============================================================
        // LEMMA.ID: Full session with wallet_secret
        // ============================================================
        
        // Check local session first
        if (this.session.isUnlocked) {
            state.hasWallet = true;
            state.isUnlocked = true;
            try {
                state.walletSecret = await this.getWalletSecret();
            } catch (e) {
                console.warn('[Lemma] Could not get wallet secret:', e.message);
            }
            
            if (state.walletSecret) {
            state.suggestedAction = 'auto_sign_in';
            state.suggestedButtonText = 'Sign In';
            state.canLinkDevice = true;
            state.canAddDevice = true;
                return state;
            }
        }
        
        // Check if user has a wallet (even if locked)
        try {
            const walletIdRecord = await this._get('passkey', 'walletId');
            if (walletIdRecord?.value) {
                state.hasWallet = true;
            state.suggestedAction = 'unlock';
            state.suggestedButtonText = 'Unlock Wallet';
            state.canAddDevice = true;
        } else {
                // No wallet - offer create or link
            state.suggestedAction = 'create_passkey';
            state.suggestedButtonText = 'Create Passkey';
            state.canLinkDevice = true;
            state.linkDeviceText = 'Already have a wallet on another device?';
            }
        } catch (e) {
            console.warn('[Lemma] Could not check wallet status:', e.message);
        }
        
        return state;
    }

    /**
     * Get HTML snippet for "Link existing wallet" option.
     * Customer sites can inject this below their sign-in button.
     * 
     * Usage:
     *   const linkHtml = await wallet.getLinkDeviceHtml();
     *   if (linkHtml) {
     *     document.getElementById('lemma-link-container').innerHTML = linkHtml;
     *   }
     * 
     * @param {Object} options - Customization options
     * @param {string} options.text - Custom text (default: "Already have a wallet on another device?")
     * @param {string} options.linkText - Custom link text (default: "Link this device")
     * @param {string} options.className - Custom CSS class for styling
     * @returns {string|null} HTML string or null if link option shouldn't be shown
     */
    async getLinkDeviceHtml(options = {}) {
        const state = await this.getAuthState();
        
        // Don't show if user is already signed in or can't link
        if (state.isUnlocked || !state.canLinkDevice) {
            return null;
        }
        
        const text = options.text || 'Already have a wallet on another device?';
        const linkText = options.linkText || 'Link this device';
        const className = options.className || 'lemma-link-device';
        const url = state.linkDeviceUrl || 'https://lemma.id/link';
        
        return `<div class="${className}" style="margin-top: 12px; text-align: center; font-size: 0.85rem;">
    <span style="color: #6b7280;">${text}</span>
    <a href="${url}" target="_blank" rel="noopener" style="color: #667eea; margin-left: 4px; text-decoration: none; font-weight: 500;">
        🔗 ${linkText}
    </a>
</div>`;
    }

    /**
     * Auto-authenticate if user has an unlocked wallet.
     * 
     * If authenticated=true, the user has PROVEN possession of their wallet via passkey.
     * This is cryptographic proof - no password, no call to lemma.id needed.
     * 
     * Usage:
     *   const result = await wallet.autoAuthenticate();
     *   if (result.authenticated) {
     *     // User proved they own their wallet! Derive their site-specific PPID:
     *     const ppid = await wallet.derivePPID(window.location.hostname);
     *     
     *     // Send PPID to YOUR backend - this is the user's ID for your site
     *     // If ppid exists in your DB -> sign in
     *     // If ppid doesn't exist -> create new account
     *     await fetch('/api/auth', { method: 'POST', body: JSON.stringify({ ppid }) });
     *   } else if (result.needsPasskey) {
     *     // Show "Create Passkey & Sign In" button
     *   }
     * 
     * @returns {Promise<Object>} Result with authenticated status
     */
    async autoAuthenticate() {
        await this.init();
        
        const result = {
            authenticated: false,
            needsPasskey: true,
            needsRedirect: false,
            walletSecret: null,
            walletId: null,
            ppid: null,
            message: ''
        };
        
        // ============================================================
        // SIMPLIFIED LOCAL-FIRST ARCHITECTURE (v2.45.0)
        // ============================================================
        // On lemma.id: Check local session + wallet_secret
        // On third-party sites: Check local session + verify local lemmas
        //
        // Benefits:
        // - ~15ms verification (NO network calls on third-party sites!)
        // - More private (wallet_secret never leaves lemma.id)
        // - Simpler code (local verification only)
        // ============================================================
        
        // ============================================================
        // THIRD-PARTY SITES: Check session + lemmas
        // ============================================================
        if (!this._isLemmaDomain()) {
            console.log('[Lemma] Third-party site: checking authorization...');
            
            // CRITICAL: Check for redirect return FIRST
            // User may be returning from lemma.id after unlock
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('lemma_unlocked') === '1' || urlParams.get('lemma_token')) {
                console.log('[Lemma] Detected redirect return - processing...');
                try {
                    const redirectResult = await this.checkRedirectReturn();
                    if (redirectResult.success && redirectResult.authenticated) {
                        console.log('[Lemma] Redirect processed - auto-issuing lemma...');
                        
                        // Start listening for lock events
                        this._setupLockEventListener();
                        
                        // Auto-issue a lemma for this site (wallet_secret stays in SDK)
                        const siteId = window.location.hostname;
                        const issueResult = await this._autoIssueLemma(siteId);
                        
                        if (issueResult.success) {
                            return {
                                authenticated: true,
                                needsPasskey: false,
                                needsRedirect: false,
                                ppid: issueResult.ppid,
                                claims: issueResult.claims,
                                lemma: issueResult.lemma,
                                walletId: redirectResult.walletId,
                                message: 'Authorized via redirect + verified lemma',
                                source: 'redirect'
                            };
                        }
                        
                        // Issuance failed — still return authenticated with PPID
                        // (user proved passkey possession, just no lemma yet)
                        console.warn('[Lemma] Lemma issuance failed after redirect, deriving PPID only');
                        const ppid = await this.derivePPID(siteId);
                        return {
                            authenticated: true,
                            needsPasskey: false,
                            needsRedirect: false,
                            ppid: ppid,
                            walletId: redirectResult.walletId,
                            message: 'Authenticated via redirect (lemma issuance pending)',
                            source: 'redirect'
                        };
                    }
                } catch (e) {
                    console.warn('[Lemma] Redirect processing failed:', e.message);
                }
            }
            
            // Try local authorization (checks session + lemmas)
            const authResult = await this.verifyLocalAuthorization();
            
            if (authResult.authorized) {
                console.log(`[Lemma] ✅ Authorized via local lemma in ${authResult.verifyTimeMs}ms`);
                
                result.authenticated = true;
                result.needsPasskey = false;
                result.needsRedirect = false;
                result.ppid = authResult.ppid;
                result.claims = authResult.claims;
                result.lemma = authResult.lemma;
                result.message = 'Authorized via local lemma verification';
                result.verifyTimeMs = authResult.verifyTimeMs;
                
                // Start listening for lock events from bridge
                this._setupLockEventListener();
                
                return result;
            }
            
            // Not authorized via lemma - if session is valid, auto-issue a lemma
            // via lemma.id API. The wallet_secret stays in the SDK (only PPID is sent).
            if (this.session.isUnlocked) {
                const hasSecret = this.session.walletSecret || await this._get('secrets', 'master').then(r => r?.secret).catch(() => null);
                
                if (hasSecret) {
                    // Ensure getWalletSecret() will work for derivePPID()
                    if (!this.session.walletSecret && hasSecret !== true) {
                        this.session.walletSecret = hasSecret;
                    }
                    
                    const siteId = window.location.hostname;
                    console.log(`[Lemma] No lemma for ${siteId} - requesting issuance (wallet_secret stays local)`);
                    
                    const issueResult = await this._autoIssueLemma(siteId);
                    
                    if (issueResult.success) {
                        console.log(`[Lemma] Lemma issued and verified for ${siteId}`);
                        
                        this._setupLockEventListener();
                        
                        return {
                            authenticated: true,
                            needsPasskey: false,
                            needsRedirect: false,
                            ppid: issueResult.ppid,
                            claims: issueResult.claims,
                            lemma: issueResult.lemma,
                            walletId: this.session.walletId,
                            message: 'Authorized via auto-issued and verified lemma',
                            source: 'auto_issued'
                        };
                    }
                    
                    console.warn(`[Lemma] Auto-issue failed: ${issueResult.error}`);
                }
            }
            
            // ============================================================
            // FAST PATH: If wallet is locked, check global session (ONE API call)
            // If unlocked remotely, set local session and retry local verification.
            // No bridge iframe, no postMessage, no session-sync cookies.
            // ============================================================
            if (authResult.reason === 'wallet_locked' || authResult.reason === 'session_expired') {
                try {
                    const walletIdRecord = await this._get('passkey', 'walletId');
                    const walletId = walletIdRecord?.value;
                    
                    if (walletId) {
                        console.log('[Lemma] Wallet locked - checking global session (single API call)...');
                        const globalSession = await this._checkGlobalSession(walletId);
                        
                        if (globalSession.valid) {
                            console.log('[Lemma] Global session valid - syncing locally...');
                            const gs = globalSession.session || globalSession;
                            this.session = {
                                isUnlocked: true,
                                unlockedAt: gs.unlocked_at || gs.unlockedAt || Date.now(),
                                expiresAt: (gs.expires_at || gs.expiresAt) * 1000,
                                walletId: walletId,
                                source: 'global_sync'
                            };
                            await this._put('session', { id: 'current', ...this.session });
                            
                            // Retry local verification with updated session
                            const retryResult = await this.verifyLocalAuthorization();
                            if (retryResult.authorized) {
                                console.log(`[Lemma] ✅ Authorized after global sync in ${retryResult.verifyTimeMs}ms`);
                                this._setupLockEventListener();
                                return {
                                    authenticated: true,
                                    needsPasskey: false,
                                    needsRedirect: false,
                                    ppid: retryResult.ppid,
                                    claims: retryResult.claims,
                                    lemma: retryResult.lemma,
                                    walletId: walletId,
                                    message: 'Authorized via local lemma + global session sync',
                                    verifyTimeMs: retryResult.verifyTimeMs,
                                    source: 'global_sync'
                                };
                            }
                        }
                    }
                } catch (e) {
                    console.warn('[Lemma] Global session check failed:', e.message);
                }
                
                console.log('[Lemma] Wallet locked/expired - redirect to unlock');
                result.needsRedirect = true;
                result.needsPasskey = false;
                result.message = authResult.message;
                return result;
            }

            if (authResult.reason === 'no_lemma') {
                console.log('[Lemma] No lemma for this site - redirect to sign in');
                result.needsRedirect = true;
                result.needsPasskey = false;
                result.message = 'Sign in with Lemma to access this site';
                return result;
            }

            // Verification failed (signature/revoked/etc)
            console.log(`[Lemma] Authorization failed: ${authResult.reason}`);
            result.needsRedirect = true;
            result.message = authResult.message;
            return result;
        }
        
        // ============================================================
        // LEMMA.ID: Full session with wallet_secret
        // ============================================================
        console.log('[Lemma] On lemma.id: checking full session');
        
        // STEP 1: Check for valid local session with wallet_secret
        if (this.session.isUnlocked && this.session.expiresAt && Date.now() < this.session.expiresAt) {
            let walletSecret = this.session.walletSecret;
            if (!walletSecret) {
                try {
                    const secretRecord = await this._get('secrets', 'master');
                    walletSecret = secretRecord?.secret;
                } catch (e) {}
            }
            
            if (walletSecret) {
                console.log(`[Lemma] ✅ Using existing local session (source: ${this.session.source || 'unknown'})`);
                
                result.walletSecret = walletSecret;
                result.walletId = this.session.walletId;
                result.authenticated = true;
                result.needsPasskey = false;
                result.message = 'Authenticated via existing session';
                
                return result;
            }
        }
        
        // STEP 2: Check for cross-device global session (linked devices)
        // Only needed on lemma.id where we need the wallet_secret
        try {
            const walletIdRecord = await this._get('passkey', 'walletId');
            const secretRecord = await this._get('secrets', 'master');
            
            if (walletIdRecord?.value && secretRecord?.secret) {
                console.log('[Lemma] Checking global session (cross-device sync)...');
                const globalSession = await this._checkGlobalSession(walletIdRecord.value);
                
                if (globalSession.valid) {
                    console.log('[Lemma] ✅ Global session valid - user unlocked on another device');
                    
                    this.session = {
                        isUnlocked: true,
                        unlockedAt: globalSession.session.unlocked_at || globalSession.session.unlockedAt,
                        expiresAt: (globalSession.session.expires_at || globalSession.session.expiresAt) * 1000,
                        walletId: walletIdRecord.value,
                        walletSecret: secretRecord.secret,
                        source: 'global_sync'
                    };
                    await this._put('session', { id: 'current', ...this.session });
                    
                    result.walletSecret = secretRecord.secret;
                    result.walletId = walletIdRecord.value;
                        result.authenticated = true;
                        result.needsPasskey = false;
                    result.crossDevice = true;
                    result.message = 'Authenticated via cross-device session sync';
                        
                        return result;
                    }
                }
            } catch (e) {
            console.warn('[Lemma] Global session check failed:', e.message);
        }
        
        // STEP 3: No valid session - need passkey unlock
        console.log('[Lemma] No valid session - passkey unlock required');
        result.authenticated = false;
        result.needsPasskey = true;
        result.needsRedirect = false;
        result.message = 'Unlock wallet with passkey';
                return result;
    }
    
    /**
     * Set up listener for lock events from bridge iframe
     * When user locks on lemma.id, third-party sites should know immediately
     * Listens for SESSION_INVALIDATED events from the bridge
     */
    _setupLockEventListener() {
        if (this._lockEventListenerSetup) return;
        this._lockEventListenerSetup = true;
        
        window.addEventListener('message', async (event) => {
            // Only accept messages from lemma.id
            if (!event.origin.includes('lemma.id')) return;
            
            // Handle session invalidation (lock) events
            if (event.data?.type === 'SESSION_INVALIDATED') {
                console.log('[Lemma] Received lock event from bridge - clearing local session');
                this.session = {
                    isUnlocked: false,
                    unlockedAt: null,
                    expiresAt: null,
                    walletSecret: null
                };
                await this._delete('session', 'current');
                
                // Dispatch event for app to handle
                window.dispatchEvent(new CustomEvent('lemma-wallet-locked', {
                    detail: { 
                        reason: event.data.reason || 'remote_lock', 
                        message: 'Wallet was locked',
                        instant: event.data.instant
                    }
                }));
            }
        });
        
        console.log('[Lemma] Lock event listener active (local-only verification mode)');
    }
    
    /**
     * Ensure the user has a credential for this site.
     * 
     * Call this after autoAuthenticate() to gracefully handle new devices.
     * If the user is authenticated but has no credential for your site,
     * this will call your issuer callback to request one.
     * 
     * @param {Object} options - Configuration options
     * @param {string} options.siteId - Your site identifier (e.g., 'example.com')
     * @param {string} options.issuerDid - Your issuer DID (e.g., 'did:web:example.com')
     * @param {Function} options.onRequestCredential - Async callback to request credential from your backend
     *   Called with: { ppid, walletId, siteId } - should return { credential } or throw
     * @param {string[]} options.requiredTypes - Optional: credential types to look for (default: ['VerifiableCredential'])
     * 
     * @returns {Promise<Object>} { hasCredential, credential, issued, ppid }
     * 
     * @example
     * const wallet = new LemmaWallet();
     * const auth = await wallet.autoAuthenticate();
     * 
     * if (auth.authenticated) {
     *     const result = await wallet.ensureCredential({
     *         siteId: 'example.com',
     *         issuerDid: 'did:web:example.com',
     *         onRequestCredential: async ({ ppid }) => {
     *             // Call YOUR backend to issue a credential
     *             const resp = await fetch('/api/issue-credential', {
     *                 method: 'POST',
     *                 body: JSON.stringify({ ppid })
     *             });
     *             return await resp.json();
     *         }
     *     });
     *     
     *     if (result.hasCredential) {
     *         console.log('User has credential:', result.credential);
     *     }
     * }
     */
    async ensureCredential(options = {}) {
        await this.init();
        
        const {
            siteId = window.location.hostname,
            issuerDid = `did:web:${window.location.hostname}`,
            onRequestCredential,
            requiredTypes = ['VerifiableCredential']
        } = options;
        
        const result = {
            hasCredential: false,
            credential: null,
            issued: false,
            ppid: null,
            siteId: siteId
        };
        
        // Must be authenticated
        if (!this.isUnlocked()) {
            console.warn('[Lemma] ensureCredential: wallet not unlocked');
            return result;
        }
        
        // Derive PPID for this site
        try {
            result.ppid = await this.derivePPID(siteId);
        } catch (e) {
            console.error('[Lemma] ensureCredential: could not derive PPID:', e.message);
            return result;
        }
        
        // Check for existing credential from this issuer
        const credentials = await this.getCredentials();
        const existingCred = credentials.find(c => {
            // Match by issuer DID
            if (c.issuer === issuerDid) return true;
            // Match by site ID in claims
            const claims = c.claims || c.credentialSubject || {};
            if (claims.siteId === siteId || claims.site === siteId || claims.site_id === siteId) return true;
            return false;
        });
        
        if (existingCred) {
            console.log('[Lemma] ensureCredential: found existing credential from', issuerDid);
            result.hasCredential = true;
            result.credential = existingCred;
            return result;
        }
        
        // No credential found - request one if callback provided
        if (!onRequestCredential) {
            console.log('[Lemma] ensureCredential: no credential found and no onRequestCredential callback');
            return result;
        }
        
        console.log('[Lemma] ensureCredential: requesting credential for new device...');
        
        try {
            const issueResult = await onRequestCredential({
                ppid: result.ppid,
                walletId: this.session.walletId,
                siteId: siteId
            });
            
            if (issueResult && issueResult.credential) {
                // Store the new credential
                await this.storeCredential(issueResult.credential);
                result.hasCredential = true;
                result.credential = issueResult.credential;
                result.issued = true;
                console.log('[Lemma] ensureCredential: credential issued and stored');
            } else if (issueResult && (issueResult.permission_lemma || issueResult.lemma)) {
                // Handle alternative response formats
                const cred = issueResult.permission_lemma || issueResult.lemma;
                await this.storeCredential(cred);
                result.hasCredential = true;
                result.credential = cred;
                result.issued = true;
                console.log('[Lemma] ensureCredential: credential issued and stored (alt format)');
            }
        } catch (e) {
            console.error('[Lemma] ensureCredential: failed to request credential:', e.message);
        }
        
        return result;
    }
    
    /**
     * Convenience method: Authenticate and ensure credential in one call.
     * 
     * Combines autoAuthenticate() + ensureCredential() for simpler integration.
     * 
     * @param {Object} options - Same as ensureCredential options
     * @returns {Promise<Object>} Combined result with auth and credential info
     * 
     * @example
     * const wallet = new LemmaWallet();
     * const result = await wallet.authenticateWithCredential({
     *     siteId: 'example.com',
     *     issuerDid: 'did:web:example.com',
     *     onRequestCredential: async ({ ppid }) => {
     *         const resp = await fetch('/api/issue-credential', { 
     *             method: 'POST',
     *             body: JSON.stringify({ ppid }) 
     *         });
     *         return await resp.json();
     *     }
     * });
     * 
     * if (result.authenticated && result.hasCredential) {
     *     // User is authenticated AND has a credential for your site
     *     console.log('Ready to go!', result.credential);
     * } else if (result.authenticated) {
     *     // Authenticated but credential issuance failed
     *     console.log('Auth OK but no credential');
     * } else {
     *     // Not authenticated - show sign in
     *     console.log('Please sign in');
     * }
     */
    async authenticateWithCredential(options = {}) {
        const authResult = await this.autoAuthenticate();
        
        if (!authResult.authenticated) {
            return {
                ...authResult,
                hasCredential: false,
                credential: null,
                issued: false
            };
        }
        
        const credResult = await this.ensureCredential(options);
        
        return {
            ...authResult,
            ...credResult
        };
    }
    
    /**
     * Check if this wallet has an active session on any device (cross-device sync).
     * @private
     */
    async _checkGlobalSession(walletId, options = {}) {
        const now = Date.now();
        const cache = this._globalSessionCache;
        const forceRefresh = options.force === true;
        
        // Return cached result if fresh (unless force refresh)
        if (!forceRefresh && cache.result && (now - cache.timestamp) < cache.ttlMs) {
            console.log('[Lemma] 🔍 Using cached global session (age:', now - cache.timestamp, 'ms)');
            return cache.result;
        }
        
        // Deduplicate concurrent requests
        if (cache.pendingPromise && !forceRefresh) {
            console.log('[Lemma] 🔍 Waiting for pending global session check...');
            return cache.pendingPromise;
        }
        
        // Make the actual request
        cache.pendingPromise = (async () => {
        try {
            console.log('[Lemma] 🔍 Checking global session for wallet:', walletId?.substring(0, 8) + '...');
            const response = await fetch('https://lemma.id/api/wallet/global-session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ wallet_id: walletId })
            });
            
            console.log('[Lemma] 🔍 Global session response status:', response.status);
            
            if (!response.ok) {
                console.log('[Lemma] 🔍 Global session not OK, returning invalid');
                    const result = { valid: false };
                    cache.result = result;
                    cache.timestamp = now;
                    return result;
            }
            
            const data = await response.json();
            console.log('[Lemma] 🔍 Global session result:', JSON.stringify(data));
                
                // Cache the result
                cache.result = data;
                cache.timestamp = now;
            return data;
        } catch (e) {
            console.warn('[Lemma] Global session API error:', e.message);
            return { valid: false };
            } finally {
                cache.pendingPromise = null;
        }
        })();
        
        return cache.pendingPromise;
    }
    
    /**
     * Auto-start heartbeat on third-party sites after successful authentication.
     * Customers can optionally set onSessionExpired callback to handle sign-out.
     * @private
     */
    _autoStartHeartbeat() {
        if (this._isLemmaDomain()) return;
        if (this._heartbeatInterval) return; // Already running
        
        console.log('[Lemma] 🔄 Auto-starting session heartbeat (visibility + 5min backup)');
        this.startSessionHeartbeat(300000); // 5 minute backup interval (primary is tab focus)
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
     * Redirect-based unlock flow for all browsers.
     * More reliable than popups on iOS Safari which blocks popups aggressively.
     * 
     * Flow:
     * 1. Saves current URL and state (including encryption key)
     * 2. Redirects to lemma.id/unlock (clean, focused page)
     * 3. User unlocks with passkey
     * 4. Wallet data encrypted client-side, returned in URL
     * 5. SDK detects return and completes auth
     * 
     * @param {Object} options Configuration
     * @param {string} options.returnUrl URL to return to (default: current URL)
     * @param {string} options.state Optional state to preserve across redirect
     * @returns {void} This method redirects, so it doesn't return
     */
    unlockWithRedirect(options = {}) {
        const returnUrl = options.returnUrl || window.location.href;
        const state = options.state || {};
        
        // Generate a random encryption key for secure client-side token exchange
        // This key never touches lemma.id servers - all encryption happens client-side
        const encKeyBytes = crypto.getRandomValues(new Uint8Array(32));
        const encKeyBase64 = this._arrayBufferToBase64(encKeyBytes);
        
        // Store state for when we return (including encryption key)
        const redirectState = {
            returnUrl,
            state,
            timestamp: Date.now(),
            origin: window.location.origin,
            encKey: encKeyBase64  // Store key to decrypt the response
        };
        
        try {
            localStorage.setItem('lemma_redirect_state', JSON.stringify(redirectState));
        } catch (e) {
            // Fallback to URL-encoded state in the redirect
            console.warn('[Lemma] Could not save redirect state to localStorage');
        }
        
        console.log('[Lemma] Redirecting to lemma.id for wallet unlock...');
        console.log('[Lemma] 🔐 Using client-side encryption (wallet secret never touches server)');
        
        // Build the redirect URL with encryption key
        // PRIVACY: The enc_key is only used by client-side JavaScript on lemma.id
        // The server never sees or stores the wallet secret
        const params = new URLSearchParams({
            return_url: returnUrl,
            redirect_flow: '1',
            enc_key: encKeyBase64  // Pass key for client-side encryption
        });
        
        // Add custom state if provided
        if (Object.keys(state).length > 0) {
            params.set('state', btoa(JSON.stringify(state)));
        }
        
        this._showRedirectOverlay('Connecting to Lemma...');
        window.location.href = `https://lemma.id/unlock?${params.toString()}`;
    }

    /**
     * Show a full-page overlay during redirects to prevent blank page flash.
     * Uses inline styles and z-index:2147483647 to work on any site.
     * @param {string} message - Text to display
     * @private
     */
    _showRedirectOverlay(message) {
        try {
            const overlay = document.createElement('div');
            overlay.id = 'lemma-redirect-overlay';
            overlay.setAttribute('style',
                'position:fixed;top:0;left:0;width:100%;height:100%;' +
                'background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);' +
                'z-index:2147483647;display:flex;flex-direction:column;' +
                'align-items:center;justify-content:center;opacity:0;' +
                'transition:opacity 200ms ease-in;'
            );
            overlay.innerHTML =
                '<div style="width:40px;height:40px;border:3px solid rgba(255,255,255,0.3);' +
                'border-radius:50%;border-top-color:#fff;animation:lemma-spin 0.8s linear infinite;' +
                'margin-bottom:16px;"></div>' +
                '<div style="color:#fff;font-family:-apple-system,BlinkMacSystemFont,sans-serif;' +
                'font-size:1.1rem;font-weight:500;">' + (message || 'Connecting to Lemma...') + '</div>';

            const style = document.createElement('style');
            style.textContent = '@keyframes lemma-spin{to{transform:rotate(360deg)}}';
            overlay.appendChild(style);

            document.body.appendChild(overlay);
            requestAnimationFrame(() => {
                requestAnimationFrame(() => { overlay.style.opacity = '1'; });
            });
        } catch (e) {
            // Non-critical UI enhancement; don't block redirect
        }
    }

    /**
     * Clean up stale redirect state from localStorage.
     * Prevents localStorage pollution from abandoned redirect flows.
     * @private
     */
    _cleanupStaleRedirectState() {
        try {
            const stateJson = localStorage.getItem('lemma_redirect_state');
            if (stateJson) {
                const state = JSON.parse(stateJson);
                if (Date.now() - state.timestamp > 10 * 60 * 1000) {
                    localStorage.removeItem('lemma_redirect_state');
                    console.log('[Lemma] Cleaned up stale redirect state');
                }
            }
        } catch (e) {
            // If we can't parse it, remove it
            try { localStorage.removeItem('lemma_redirect_state'); } catch (_) {}
        }
    }

    /**
     * Check if we're returning from a redirect-based unlock.
     * Call this on page load to complete the redirect flow.
     *
     * @returns {Promise<Object|null>} Auth result if returning from redirect, null otherwise
     */
    async checkRedirectReturn() {
        await this.init();
        
        // Check URL params for redirect flow completion
        const urlParams = new URLSearchParams(window.location.search);
        const isRedirectReturn = urlParams.get('lemma_unlocked') === '1';
        const encryptedData = urlParams.get('lemma_data');  // Client-side encrypted wallet data
        const legacyToken = urlParams.get('lemma_token');   // Legacy server-side token (deprecated)
            
        // Retrieve saved redirect state (contains decryption key)
        let savedState = null;
        try {
            const stateJson = localStorage.getItem('lemma_redirect_state');
            if (stateJson) {
                savedState = JSON.parse(stateJson);
                // Only valid if recent (within 10 minutes)
                if (Date.now() - savedState.timestamp > 10 * 60 * 1000) {
                    localStorage.removeItem('lemma_redirect_state');
                    savedState = null;
                }
            }
        } catch (e) {
            savedState = null;
        }
        
        if (!isRedirectReturn && !savedState) {
            return null;
        }
                    
        // Clear the redirect state AFTER we've read it
        try {
            localStorage.removeItem('lemma_redirect_state');
        } catch (e) {}
        
        // Clean up URL (remove lemma params)
        if (isRedirectReturn) {
            urlParams.delete('lemma_unlocked');
            urlParams.delete('lemma_wallet_id');
            urlParams.delete('lemma_data');
            urlParams.delete('lemma_token');
            const cleanUrl = urlParams.toString() 
                ? `${window.location.pathname}?${urlParams.toString()}`
                : window.location.pathname;
            window.history.replaceState({}, '', cleanUrl);
        }
        
        // PRIVACY-FIRST: Client-side encrypted data (no server involvement)
        // The wallet secret was encrypted by lemma.id's client-side JavaScript
        // using a key we generated and stored locally. Server never sees the secret.
        if (encryptedData && savedState?.encKey) {
            try {
                const decrypted = await this._decryptRedirectData(encryptedData, savedState.encKey);
                
                if (decrypted && decrypted.wallet_secret) {
                    // Store the wallet secret locally
                    await this._put('secrets', { id: 'master', secret: decrypted.wallet_secret, source: 'redirect_encrypted' });
                    
                    // Store wallet_id for heartbeat cross-device checks
                    if (decrypted.wallet_id) {
                        await this._put('passkey', { id: 'walletId', value: decrypted.wallet_id });
                    }
                    
                    // Set up local session
                        this.session = {
                            isUnlocked: true,
                        unlockedAt: Date.now(),
                        expiresAt: Date.now() + getSessionDurationMs(),
                        walletId: decrypted.wallet_id,
                        walletSecret: decrypted.wallet_secret,
                        source: 'redirect'
                        };
                        await this._put('session', { id: 'current', ...this.session });

                    // IMPORTANT: Sync session to bridge so it can serve future requests
                    // The bridge has a separate IndexedDB and needs the wallet_id for global-session checks
                    await this._syncSessionToBridge(this.session, decrypted.wallet_secret);

                    this._autoStartHeartbeat();

                    return {
                        success: true,
                        authenticated: true,
                        walletId: decrypted.wallet_id,
                        walletSecret: decrypted.wallet_secret,
                        message: 'Authenticated via encrypted redirect (privacy-preserving)'
                    };
                } else {
                    console.warn('[Lemma] Decryption succeeded but no wallet secret');
                }
            } catch (e) {
                console.warn('[Lemma] Client-side decryption failed:', e.message);
                        }
                    }
                    
        // LEGACY FALLBACK: Server-side token exchange (deprecated, for old SDK compatibility)
        if (legacyToken) {
            console.log('[Lemma] Using legacy server-side token exchange (deprecated)...');
            try {
                const response = await fetch('https://lemma.id/api/wallet/exchange-redirect-token', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: legacyToken })
                });
                
                const data = await response.json();
                
                if (data.success && data.wallet_secret) {
                    console.log('[Lemma] ✅ Legacy token exchange successful');

                    await this._put('secrets', { id: 'master', secret: data.wallet_secret, source: 'redirect_token' });

                    this.session = {
                        isUnlocked: true,
                        unlockedAt: Date.now(),
                        expiresAt: Date.now() + getSessionDurationMs(),
                        walletId: data.wallet_id,
                        walletSecret: data.wallet_secret,
                        source: 'redirect'
                    };
                    await this._put('session', { id: 'current', ...this.session });

                    // Sync session to bridge
                    await this._syncSessionToBridge(this.session, data.wallet_secret);

                    this._autoStartHeartbeat();

                    return {
                        success: true,
                        authenticated: true,
                        walletId: data.wallet_id,
                        walletSecret: data.wallet_secret,
                        message: 'Authenticated via legacy redirect token'
                    };
                }
            } catch (e) {
                console.warn('[Lemma] Legacy token exchange error:', e.message);
            }
        }
                    
        // Fallback: Check bridge session and issue lemma via bridge
        // (works on desktop, may fail on mobile Safari)
        const session = await this.checkBridgeSession();
        
        if (session.valid) {
            console.log('[Lemma] Redirect: bridge session valid - requesting lemma issuance...');
            
            const siteId = window.location.hostname;
            try {
                const issueResult = await this._sendBridgeMessage('ISSUE_LEMMA', { siteId });
                if (issueResult?.success && issueResult.lemma) {
                    await this.storeCredential(issueResult.lemma);
                    
                    return {
                        success: true,
                        authenticated: true,
                        walletId: session.walletId,
                        ppid: issueResult.ppid,
                        lemma: issueResult.lemma,
                        message: 'Authenticated via bridge-issued lemma'
                    };
                }
            } catch (e) {
                console.warn('[Lemma] Bridge ISSUE_LEMMA failed:', e.message);
            }
            
            // Bridge issuance failed but session is valid
            return {
                success: true,
                authenticated: true,
                walletId: session.walletId,
                message: 'Authenticated via bridge session (lemma pending)'
            };
        }
        
        console.log('[Lemma] Redirect return but could not establish session');
        return {
                            success: false,
            authenticated: false,
            message: 'Session not established after redirect'
        };
    }
    
    /**
     * Decrypt wallet data received from redirect (client-side encryption).
     * Uses AES-GCM with a key we generated before redirect.
     * @private
     */
    async _decryptRedirectData(encryptedBase64, keyBase64) {
        try {
            // Decode the encrypted data
            const encryptedBytes = this._base64ToArrayBuffer(encryptedBase64);
            
            // Format: nonce (12 bytes) + ciphertext + authTag (16 bytes, appended by AES-GCM)
            const nonce = encryptedBytes.slice(0, 12);
            const ciphertext = encryptedBytes.slice(12);
            
            // Import the key
            const keyBytes = this._base64ToArrayBuffer(keyBase64);
            const key = await crypto.subtle.importKey(
                'raw',
                keyBytes,
                { name: 'AES-GCM' },
                false,
                ['decrypt']
            );
            
            // Decrypt
            const decryptedBytes = await crypto.subtle.decrypt(
                { name: 'AES-GCM', iv: nonce },
                key,
                ciphertext
            );
            
            // Parse JSON
            const decryptedText = new TextDecoder().decode(decryptedBytes);
            return JSON.parse(decryptedText);
        } catch (e) {
            console.error('[Lemma] Decryption error:', e);
            throw new Error('Failed to decrypt redirect data: ' + e.message);
        }
    }
    
    /**
     * Convert base64 string to ArrayBuffer
     * @private
     */
    _base64ToArrayBuffer(base64) {
        // Handle URL-safe base64
        const standardBase64 = base64.replace(/-/g, '+').replace(/_/g, '/');
        const padding = standardBase64.length % 4;
        const paddedBase64 = padding ? standardBase64 + '='.repeat(4 - padding) : standardBase64;
        
        const binary = atob(paddedBase64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes;
    }
    
    /**
     * Convert ArrayBuffer to base64 string
     * @private
     */
    _arrayBufferToBase64(buffer) {
        const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        // Use URL-safe base64
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }
    
    /**
     * Unlock wallet using redirect flow.
     * This is now the primary and only unlock method (v2.32.0).
     * Provides consistent UX across all platforms (mobile + desktop).
     * 
     * @param {Object} options Configuration
     * @param {string} options.returnUrl URL to return to after unlock
     * @param {Object} options.state Optional state to preserve
     * @returns {Object} Always returns { redirecting: true }
     */
    async smartUnlock(options = {}) {
        console.log('[Lemma] Using redirect-based unlock');
        this.unlockWithRedirect(options);
        // This doesn't return - page redirects
        return { redirecting: true };
    }

    /**
     * Check if session is still valid (useful after page refresh)
     * Simplified: trusts local session if not expired (no bridge check needed).
     * 
     * @returns {Promise<boolean>} True if session is valid
     */
    async isSessionValid() {
        await this.init();
        
        // Check local session exists
        if (!this.session.isUnlocked) {
            return false;
        }
        
        // Check if session has expired locally
        if (this.session.expiresAt && Date.now() > this.session.expiresAt) {
            console.log('[Lemma] Session expired locally');
            this.session = { isUnlocked: false };
            await this._delete('session', 'current');
            if (this._onSessionExpired) {
                this._onSessionExpired({ reason: 'expired' });
            }
            return false;
        }
        
        // SIMPLIFIED (v2.31.0): Trust local sessions without bridge verification
        // Sessions were established via:
        // - redirect (client-side encryption - most secure)
        // - global_sync (cross-device)
        // - bridge/popup (legacy, still valid if not expired)
        // All are verified at creation time, no need to re-verify with bridge.
        console.log(`[Lemma] Session valid (source: ${this.session.source || 'local'}, expires: ${new Date(this.session.expiresAt).toISOString()})`);
        return true;
    }
    
    /**
     * DEPRECATED: Legacy bridge validation method.
     * Kept for backward compatibility but no longer used in main flow.
     * @private
     */
    async _legacyBridgeValidation() {
        if (!this._isLemmaDomain()) {
            try {
                const bridgeSession = await this.checkBridgeSession();
                if (!bridgeSession.valid) {
                    console.log('[Lemma] Session invalidated by bridge (legacy check)');
                    this.session = { isUnlocked: false };
                    await this._delete('session', 'current');
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
     * Start session heartbeat (checks if wallet session is still valid)
     * 
     * ARCHITECTURE (v2.33.0):
     * - PRIMARY: SSE stream for instant cross-device lock/unlock detection (~0ms latency)
     * - FALLBACK: Polling at 5-minute intervals if SSE is unavailable
     * - LOCAL: Expiry check on visibility change (always enforced, no network)
     * 
     * The SSE connection to /api/events/revocations receives both credential
     * revocation events and session invalidation events from the same stream.
     * This eliminates the need for 60-second polling heartbeats.
     * 
     * @param {number} intervalMs - Fallback poll interval in ms (default: 300000 = 5 minutes)
     */
    startSessionHeartbeat(intervalMs = 300000) {
        // Only run on third-party sites
        if (window.location.hostname.includes('lemma.id') ||
            window.location.hostname.includes('localhost')) {
            return;
        }

        // Clear any existing heartbeat
        if (this._heartbeatInterval) {
            clearInterval(this._heartbeatInterval);
        }

        // Clear any existing visibility listener
        if (this._visibilityHandler) {
            document.removeEventListener('visibilitychange', this._visibilityHandler);
        }

        // Close any existing SSE connection
        if (this._sessionEventSource) {
            this._sessionEventSource.close();
            this._sessionEventSource = null;
        }

        // ---- SSE: instant cross-device detection ----
        this._connectSessionSSE();

        // Heartbeat check function (reused for fallback interval and visibility)
        const performHeartbeatCheck = async () => {
            // Skip if no local session
            if (!this.session.isUnlocked) return;
            
            // Debounce: Skip if checked recently (prevents rapid-fire on focus/visibility)
            const now = Date.now();
            if ((now - this._lastHeartbeatCheck) < this._heartbeatDebounceMs) {
                console.log('[Lemma] Heartbeat debounced (last check:', now - this._lastHeartbeatCheck, 'ms ago)');
                return;
            }
            this._lastHeartbeatCheck = now;
            
            // Check 1: Local expiry (always enforced)
            if (this.session.expiresAt && now > this.session.expiresAt) {
                console.log('[Lemma] Session expired');
                await this._clearSessionGracefully('expired', 'Your session has expired. Please sign in again.');
                return;
            }
            
            // Check 2: Cross-device lock detection via global session API (fallback only)
            // If SSE is connected, skip polling — SSE delivers lock events instantly
            if (this._sessionEventSource && this._sessionEventSource.readyState === EventSource.OPEN) {
                return;
            }
            
            try {
                let walletId = this.session.walletId;
                
                if (!walletId) {
                    const walletIdRecord = await this._get('passkey', 'walletId');
                    if (walletIdRecord?.value) {
                        this.session.walletId = walletIdRecord.value;
                        walletId = walletIdRecord.value;
                    }
                }
                
                if (walletId) {
                    const sessionSource = this.session.source;
                    const localOnlySources = ['local', 'passkey', 'local_passkey'];
                    const skipGlobalCheck = localOnlySources.includes(sessionSource);

                    if (!skipGlobalCheck) {
                        console.log('[Lemma] Fallback: checking global session (SSE not connected, source:', sessionSource, ')');
                        const globalSession = await this._checkGlobalSession(walletId);

                        if (!globalSession.valid) {
                            console.log('[Lemma] Wallet locked remotely (detected via fallback poll).');
                            await this._clearSessionGracefully('wallet_locked', 'Your wallet was locked on another device.');
                            return;
                        }
                    }
                }
            } catch (e) {
                // Network issues shouldn't cause sign-out - fail silently
            }
        };
        
        // Fallback polling interval (only fires when SSE is down)
        this._heartbeatInterval = setInterval(performHeartbeatCheck, intervalMs);
        
        // INSTANT CHECK: When user returns to tab, check local expiry immediately
        this._visibilityHandler = async () => {
            if (document.visibilityState === 'visible' && this.session.isUnlocked) {
                await performHeartbeatCheck();
            }
        };
        document.addEventListener('visibilitychange', this._visibilityHandler);
        
        // Clear any previous startup timer before creating a new one
        if (this._heartbeatStartupTimer) {
            clearTimeout(this._heartbeatStartupTimer);
        }
        // Run an immediate check on startup
        this._heartbeatStartupTimer = setTimeout(async () => {
            this._heartbeatStartupTimer = null;
            await performHeartbeatCheck();
        }, 2000);
        
        // Also check on window focus (backup for visibility API)
        // Remove previous handler first to prevent duplicates
        if (this._focusHandler) {
            window.removeEventListener('focus', this._focusHandler);
        }
        this._focusHandler = async () => {
            if (this.session.isUnlocked) {
                console.log('[Lemma] Window focused - checking session');
                await performHeartbeatCheck();
            }
        };
        window.addEventListener('focus', this._focusHandler);
    }

    /**
     * Connect to SSE event stream for instant session invalidation detection.
     * Listens for session_invalidated and session_restored events.
     * Automatically reconnects with exponential backoff on failure.
     * @private
     */
    _connectSessionSSE() {
        if (typeof EventSource === 'undefined') {
            console.warn('[Lemma] EventSource not supported - using fallback polling');
            return;
        }

        this._sseReconnectAttempts = this._sseReconnectAttempts || 0;

        try {
            this._sessionEventSource = new EventSource('https://lemma.id/api/events/revocations');

            this._sessionEventSource.addEventListener('session_invalidated', async (event) => {
                try {
                    const data = JSON.parse(event.data);
                    const walletId = this.session.walletId;

                    // Only react if this event is for our wallet
                    if (!walletId || data.wallet_id !== walletId) return;

                    console.log('[Lemma] SSE: wallet locked remotely (instant detection)');
                    await this._clearSessionGracefully('wallet_locked', 'Your wallet was locked on another device.');
                } catch (e) {
                    console.warn('[Lemma] SSE: failed to process session_invalidated event:', e.message);
                }
            });

            this._sessionEventSource.addEventListener('session_restored', (event) => {
                try {
                    const data = JSON.parse(event.data);
                    const walletId = this.session.walletId;

                    if (!walletId || data.wallet_id !== walletId) return;

                    console.log('[Lemma] SSE: wallet unlocked on another device');
                    // Dispatch event for apps that want to react to remote unlock
                    window.dispatchEvent(new CustomEvent('lemma:session-restored', {
                        detail: { wallet_id: data.wallet_id, expires_at: data.expires_at }
                    }));
                } catch (e) {
                    console.warn('[Lemma] SSE: failed to process session_restored event:', e.message);
                }
            });

            this._sessionEventSource.addEventListener('connected', () => {
                this._sseReconnectAttempts = 0;
                console.log('[Lemma] SSE: connected to event stream (instant lock detection active)');
            });

            this._sessionEventSource.addEventListener('error', () => {
                if (this._sessionEventSource && this._sessionEventSource.readyState === EventSource.CLOSED) {
                    // Connection lost — reconnect with backoff
                    this._reconnectSessionSSE();
                }
            });

        } catch (e) {
            console.warn('[Lemma] SSE: failed to connect, using fallback polling:', e.message);
        }
    }

    /**
     * Reconnect SSE with exponential backoff (max 5 attempts, max 30s delay).
     * After max attempts, falls back to polling-only mode.
     * @private
     */
    _reconnectSessionSSE() {
        const maxAttempts = 5;
        if (this._sseReconnectAttempts >= maxAttempts) {
            console.warn('[Lemma] SSE: max reconnect attempts reached, using fallback polling only');
            return;
        }

        this._sseReconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(2, this._sseReconnectAttempts), 30000);

        console.log(`[Lemma] SSE: reconnecting in ${delay}ms (attempt ${this._sseReconnectAttempts}/${maxAttempts})`);
        setTimeout(() => {
            if (this.session.isUnlocked) {
                this._connectSessionSSE();
            }
        }, delay);
    }
    
    /**
     * Clear session gracefully with notification
     * @private
     */
    async _clearSessionGracefully(reason, message) {
                    // Clear local session
                    this.session = {
                        isUnlocked: false,
                        unlockedAt: null,
                        expiresAt: null
                    };
                    
                    // Clear session from IndexedDB
        await this._delete('session', 'current');
        
        // Stop heartbeat, SSE, timers, and visibility listeners
        if (this._heartbeatInterval) {
            clearInterval(this._heartbeatInterval);
            this._heartbeatInterval = null;
        }
        if (this._heartbeatStartupTimer) {
            clearTimeout(this._heartbeatStartupTimer);
            this._heartbeatStartupTimer = null;
        }
        if (this._sessionEventSource) {
            this._sessionEventSource.close();
            this._sessionEventSource = null;
        }
        if (this._visibilityHandler) {
            document.removeEventListener('visibilitychange', this._visibilityHandler);
            this._visibilityHandler = null;
        }
        if (this._focusHandler) {
            window.removeEventListener('focus', this._focusHandler);
            this._focusHandler = null;
                    }
                    
        // Trigger callback if set (for customer sites to handle)
                    if (this._onSessionExpired) {
            this._onSessionExpired({ reason, message });
                    }
                    
                    // Dispatch custom event for apps to listen to
                    window.dispatchEvent(new CustomEvent('lemma:session-expired', {
            detail: { reason, message }
                    }));
    }

    /**
     * Stop session heartbeat and SSE connection
     */
    stopSessionHeartbeat() {
        if (this._heartbeatInterval) {
            clearInterval(this._heartbeatInterval);
            this._heartbeatInterval = null;
        }
        if (this._sessionEventSource) {
            this._sessionEventSource.close();
            this._sessionEventSource = null;
        }
        console.log('[Lemma] Session heartbeat and SSE stopped');
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
            
            request.onsuccess = async () => {
                this.db = request.result;
                this._initialized = true;
                await this._checkSessionState();
                this._cleanupStaleRedirectState();
                
                // Pre-hydrate verification caches (non-blocking, parallel reads)
                // This ensures verifyLocalAuthorization() hits memory, not IndexedDB
                this._hydrateVerificationCache();
                
                resolve();
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                const oldVersion = event.oldVersion;

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
                
                // v4: Profiles store for multiple wallet identities
                if (!db.objectStoreNames.contains('profiles')) {
                    db.createObjectStore('profiles', { keyPath: 'id' });
                }
            };
        });

        // Auto-sync revocations on init (non-blocking)
        this._autoSyncRevocations();
    }
    
    /**
     * Pre-hydrate verification caches into memory during init.
     * Loads revocation list + signature verification cache in parallel.
     * After this, verifyLocalAuthorization() is pure in-memory lookups.
     * @private
     */
    async _hydrateVerificationCache() {
        try {
            // Parallel reads — single IndexedDB open, multiple stores
            const [revocations, allLemmas] = await Promise.all([
                this._get('revocations', 'current').catch(() => null),
                this._getAll('lemmas').catch(() => [])
            ]);
            
            // Hydrate revocation cache
            if (revocations?.listArray) {
                this._revocationCache.set = new Set(revocations.listArray);
                this._revocationCache.lastSynced = revocations.lastSynced;
            }
            
            // Build site → lemma ID mapping for instant lookups
            if (!this._siteToLemmaId) this._siteToLemmaId = {};
            for (const lemma of allLemmas) {
                const claims = lemma.claims || lemma.credentialSubject || {};
                const siteId = claims.siteId || claims.site_id || claims.domain || lemma.siteId;
                if (siteId) {
                    // Keep most recent per site
                    const existing = this._siteToLemmaId[siteId];
                    if (!existing) {
                        this._siteToLemmaId[siteId] = lemma.id;
                    }
                }
            }
            
            // Hydrate signature verification cache from persisted entries
            if (!this._verifiedSignatures) this._verifiedSignatures = new Set();
            for (const lemma of allLemmas) {
                try {
                    const cached = await this._get('session', `verified_${lemma.id}`);
                    if (cached && cached.sig === (lemma.proof?.signatureValue || lemma.signature)) {
                        this._verifiedSignatures.add(lemma.id);
                    }
                } catch (_) {}
            }
            
            this._log('[Lemma] Verification cache hydrated:',
                `${allLemmas.length} lemmas,`,
                `${this._verifiedSignatures.size} pre-verified,`,
                `${this._revocationCache.set?.size || 0} revocations`
            );
        } catch (e) {
            // Non-fatal — verification will still work, just slower on first call
            this._warn('[Lemma] Cache hydration failed (non-fatal):', e.message);
        }
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
            // Check if returning from redirect-based unlock
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('lemma_unlocked') === '1') {
                console.log('[Lemma] Detected redirect return - auto-processing...');
                
                // AUTO-PROCESS redirect return to establish session immediately
                // This ensures the session is set up without requiring explicit call
                try {
                    // Check for new lemma-based redirect (privacy-preserving)
                    const lemmaCredParam = urlParams.get('lemma_credential');
                    if (lemmaCredParam) {
                        console.log('[Lemma] Processing lemma-based redirect (no wallet_secret transferred)');
                        try {
                            const credData = JSON.parse(atob(lemmaCredParam));
                            
                            if (credData.lemma && credData.ppid) {
                                // Store the lemma in wallet
                                await this.storeCredential(credData.lemma);
                                
                                // Set session as unlocked
                                this.session = {
                                    isUnlocked: true,
                                    unlockedAt: Date.now(),
                                    expiresAt: Date.now() + (24 * 60 * 60 * 1000),
                                    walletId: credData.lemma.walletId || credData.ppid,
                                    source: 'redirect_lemma'
                                };
                                await this._put('session', { id: 'current', ...this.session });
                                
                                console.log('[Lemma] ✅ Lemma stored + session created. PPID:', credData.ppid?.substring(0, 20) + '...');
                                console.log('[Lemma] ✅ wallet_secret was NOT transferred (privacy preserved)');
                                return; // Session is ready
                            }
                        } catch (parseErr) {
                            console.warn('[Lemma] Could not parse lemma_credential:', parseErr.message);
                        }
                    }
                    
                    // Legacy fallback: try old checkRedirectReturn (encrypted wallet_secret)
                    const redirectResult = await this.checkRedirectReturn();
                    if (redirectResult?.authenticated) {
                        console.log('[Lemma] ✅ Redirect returned authenticated (legacy flow)');
                        
                        const walletSecret = redirectResult.walletSecret || this.session.walletSecret;
                        const walletId = redirectResult.walletId || this.session.walletId;
                        
                        if (walletSecret) {
                            this.session = {
                                isUnlocked: true,
                                unlockedAt: Date.now(),
                                expiresAt: Date.now() + (24 * 60 * 60 * 1000),
                                walletId: walletId,
                                walletSecret: walletSecret,
                                source: 'redirect'
                            };
                            await this._put('session', { id: 'current', ...this.session });
                            await this._put('secrets', { id: 'master', secret: walletSecret, source: 'redirect' });
                            console.log('[Lemma] ✅ Session created from legacy redirect');
                            return;
                        }
                    } else {
                        console.warn('[Lemma] Redirect processing did not authenticate');
                    }
                } catch (e) {
                    console.error('[Lemma] Failed to process redirect:', e);
                }
            }
            
            const storedSession = await this._get('session', 'current');
            
            // DEBUG: Log what we found in IndexedDB
            console.log('[Lemma] _checkSessionState: stored session:', storedSession ? {
                isUnlocked: storedSession.isUnlocked,
                expiresAt: storedSession.expiresAt,
                expired: storedSession.expiresAt ? storedSession.expiresAt < Date.now() : 'no expiry',
                hasSecret: !!storedSession.walletSecret,
                source: storedSession.source
            } : 'none');
            
            if (storedSession && storedSession.expiresAt > Date.now()) {
                this.session = {
                    isUnlocked: true,
                    unlockedAt: storedSession.unlockedAt,
                    expiresAt: storedSession.expiresAt,
                    walletId: storedSession.walletId,
                    walletSecret: storedSession.walletSecret,
                    source: storedSession.source || 'local'
                };
                console.log('[Lemma] ✅ Session restored from IndexedDB - isUnlocked:', this.session.isUnlocked);
                
                // AUTO-START HEARTBEAT on third-party sites with existing session
                // This ensures lock detection works even after page refresh
                if (!this._isLemmaDomain()) {
                    console.log('[Lemma] Existing session found on third-party site - starting heartbeat');
                    this._autoStartHeartbeat();
                }
            } else if (storedSession && storedSession.expiresAt <= Date.now()) {
                console.log('[Lemma] Session expired - was valid until:', new Date(storedSession.expiresAt).toISOString());
            }
        } catch (e) {
            console.warn('[Lemma] _checkSessionState error:', e);
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

        // ============================================================
        // THIRD-PARTY SITES: Use local lemma verification (v2.45.0)
        // ============================================================
        if (!window.location.hostname.includes('lemma.id') && 
            !window.location.hostname.includes('localhost')) {
            console.log('[Lemma] Third-party site: checking local authorization...');
            
            // Try local lemma verification first (no network calls)
            const authResult = await this.verifyLocalAuthorization();
                
            if (authResult.authorized) {
                console.log(`[Lemma] ✅ Already authorized via local lemma in ${authResult.verifyTimeMs}ms`);
                    
                // Set local session
                    this.session = {
                        isUnlocked: true,
                    unlockedAt: Date.now(),
                    expiresAt: Date.now() + getSessionDurationMs(),
                    walletId: authResult.lemma?.walletId,
                    source: 'local_lemma'
                    };
                    await this._put('session', { id: 'current', ...this.session });
                    
                // Start listening for lock events
                this._setupLockEventListener();
                    
                    return {
                        success: true,
                    method: 'local_lemma',
                    ppid: authResult.ppid,
                    lemma: authResult.lemma,
                    message: 'Authorized via local lemma verification'
                    };
            }
            
            // Not authorized - return status (developer decides whether to redirect)
            console.log(`[Lemma] Not authorized (${authResult.reason}) - developer should handle redirect`);
            return {
                success: false,
                needsRedirect: true,
                reason: authResult.reason,
                message: 'User needs to sign in via lemma.id',
                redirectUrl: `https://lemma.id/unlock?return=${encodeURIComponent(window.location.href)}`
            };
        }

        if (!this._isPasskeySupported()) {
            throw new Error('Passkeys not supported in this browser');
        }

        // CHECK FOR EXISTING PASSKEY FIRST
        // If user already has a passkey on this device, authenticate with it instead of creating a new one
        const existingPasskey = await this._get('passkey', 'primary');
        if (existingPasskey && existingPasskey.credentialId) {
            console.log('[Lemma] Existing passkey found - authenticating instead of creating new');
            return await this.unlock();
        }
        
        // Get wallet ID (or create one)
        let walletId = await this._get('passkey', 'walletId');
        if (!walletId) {
            walletId = { id: 'walletId', value: this._generateId() };
            await this._put('passkey', walletId);
        }

        // ============================================================
        // LOCAL-ONLY PASSKEY REGISTRATION
        // ============================================================
        // The passkey is created and verified 100% locally.
        // Server only tracks lock/unlock state for cross-device sync.
        // Security comes from HSM-signed lemmas, not passkey verification.
        // ============================================================
        
        console.log('[Lemma] Creating local passkey (privacy-preserving design)');
        const challenge = crypto.getRandomValues(new Uint8Array(32));
        
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
                    userVerification: 'required',
                    residentKey: 'preferred'
                },
                timeout: 60000
            }
        });

        // Extract and store public key locally (never sent to server)
        const publicKeyData = this._extractPublicKey(credential.response);
        
        const passkeyRecord = {
            id: 'primary',
            credentialId: this._bufferToBase64url(credential.rawId),
            publicKey: publicKeyData.publicKey,
            algorithm: publicKeyData.algorithm,
            createdAt: Date.now()
        };

        await this._put('passkey', passkeyRecord);
        console.log('[Lemma] ✅ Passkey created locally (server never sees it)');

        // Get wallet secret for PPID derivation
        // CRITICAL: Check multiple sources for the secret (profiles, secrets, session)
        // This handles the case where secret was stored via device linking
        let walletSecret = await this._get('secrets', 'master');
        
        // Fallback: Check profiles (device linking stores secret here)
        if (!walletSecret?.secret) {
            const activeProfileId = await this._get('passkey', 'activeProfile');
            const profileId = activeProfileId?.value || DEFAULT_PROFILE_ID;
            const profile = await this._get('profiles', profileId);
            if (profile?.secret) {
                console.log('[Lemma] Found wallet secret in profile (from device link)');
                walletSecret = { id: 'master', secret: profile.secret, source: 'profile' };
                // Sync to secrets/master for consistency
                await this._put('secrets', { ...walletSecret, linkedFrom: profile.linkedFrom });
            }
        }
        
        // Only generate new secret if NONE found anywhere
        if (!walletSecret?.secret) {
            console.warn('[Lemma] No existing wallet secret found - generating new one');
            console.warn('[Lemma] This should NOT happen if device was linked!');
            
            // Generate 32-byte random secret
            const secretBytes = crypto.getRandomValues(new Uint8Array(32));
            const secretHex = Array.from(secretBytes)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            walletSecret = {
                id: 'master',
                secret: secretHex,
                createdAt: Date.now(),
                source: 'generated'
            };
            await this._put('secrets', walletSecret);
            console.log('🔐 Generated NEW wallet secret for PPID derivation');
        } else {
            console.log('[Lemma] Using existing wallet secret (source:', walletSecret.source || 'stored', ')');
        }

        // Auto-unlock after registration (user just authenticated via biometrics)
        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + getSessionDurationMs(),
            walletId: walletId.value,
            walletSecret: walletSecret.secret
        };
        await this._put('session', { id: 'current', ...this.session });
        console.log('✅ Wallet created and auto-unlocked after passkey registration');

        // Signal to server for cross-device sync (simple state update)
        if (this._isLemmaDomain()) {
                try {
                    const activeProfile = await this.getActiveProfile();
                console.log('[Lemma] Signaling new wallet unlock to server...');
                const signalResponse = await fetch('/api/wallet/signal-unlock', {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            wallet_id: walletId.value,
                            unlocked_at: this.session.unlockedAt,
                        expires_at: Math.floor(this.session.expiresAt / 1000),
                            profile_id: activeProfile.id,
                        profile_name: activeProfile.name
                        })
                    });
                if (signalResponse.ok) {
                    console.log('[Lemma] ✅ Server notified - cross-device sync enabled');
                    this.session.serverSessionActive = true;
                    await this._put('session', { id: 'current', ...this.session });
                    } else {
                    console.warn('[Lemma] Could not signal to server:', signalResponse.status);
                    }
                } catch (e) {
                console.warn('[Lemma] Could not signal to server:', e.message);
            }
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
    async unlock(options = {}) {
        await this.init();

        // SMART CHECK: On third-party sites, check bridge session first
        // If user already unlocked on lemma.id today, don't prompt for passkey
        if (!window.location.hostname.includes('lemma.id') && 
            !window.location.hostname.includes('localhost')) {
            console.log('[Lemma] Third-party site: checking local authorization...');
                
            // Try local lemma verification first (no network calls)
            const authResult = await this.verifyLocalAuthorization();

            if (authResult.authorized) {
                console.log(`[Lemma] ✅ Already authorized via local lemma in ${authResult.verifyTimeMs}ms`);
                
                // Set local session
                    this.session = {
                        isUnlocked: true,
                    unlockedAt: Date.now(),
                    expiresAt: Date.now() + getSessionDurationMs(),
                    walletId: authResult.lemma?.walletId,
                    source: 'local_lemma'
                    };
                    await this._put('session', { id: 'current', ...this.session });

                // Start listening for lock events
                this._setupLockEventListener();

                    return {
                        success: true,
                    method: 'local_lemma',
                    ppid: authResult.ppid,
                    lemma: authResult.lemma,
                    expiresAt: this.session.expiresAt,
                    message: 'Authorized via local lemma verification'
                };
            }
            
            // Not authorized - return status (developer decides whether to redirect)
            console.log(`[Lemma] Not authorized (${authResult.reason}) - developer should handle redirect`);
            return {
                success: false,
                needsRedirect: true,
                reason: authResult.reason,
                message: 'User needs to sign in via lemma.id',
                redirectUrl: `https://lemma.id/unlock?return=${encodeURIComponent(window.location.href)}`
            };
        }

        // ============================================================
        // LOCAL-ONLY PASSKEY VERIFICATION
        // ============================================================
        // The passkey is verified 100% locally by the browser.
        // After successful local verification, we signal the server.
        // Security comes from HSM-signed lemmas, not passkey verification.
        // ============================================================
        
        // Get stored passkey
        const passkey = await this._get('passkey', 'primary');
        if (!passkey) {
            // On lemma.id, throw error (user should create passkey)
            // On third-party sites, this shouldn't happen (handled above)
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

        // Get wallet ID (create and store if missing)
        let walletIdRecord = await this._get('passkey', 'walletId');
        if (!walletIdRecord?.value) {
            const newWalletId = 'wallet_' + this._generateId();
            walletIdRecord = { id: 'walletId', value: newWalletId };
            await this._put('passkey', walletIdRecord);
            console.log('[Lemma] Created wallet ID:', newWalletId);
        }
        const walletId = walletIdRecord.value;

        // Get wallet secret for PPID derivation
        // CRITICAL: Check multiple sources (device linking stores in profiles)
        let walletSecretRecord = await this._get('secrets', 'master');
        
        // Fallback: Check profiles (device linking stores secret here)
        if (!walletSecretRecord?.secret) {
            const activeProfileId = await this._get('passkey', 'activeProfile');
            const profileId = activeProfileId?.value || DEFAULT_PROFILE_ID;
            const profile = await this._get('profiles', profileId);
            if (profile?.secret) {
                console.log('[Lemma] Found wallet secret in profile (from device link)');
                walletSecretRecord = { id: 'master', secret: profile.secret, source: 'profile' };
                // Sync to secrets/master for consistency
                await this._put('secrets', { ...walletSecretRecord, linkedFrom: profile.linkedFrom });
            }
        }
        
        // Only generate wallet secret if NONE found (legacy wallets before v3)
        if (!walletSecretRecord?.secret) {
            console.warn('[Lemma] No wallet secret found - generating new one');
            console.warn('[Lemma] If device was linked, this is a BUG - secret should exist!');
            
            const secretBytes = crypto.getRandomValues(new Uint8Array(32));
            const secretHex = Array.from(secretBytes)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            walletSecretRecord = {
                id: 'master',
                secret: secretHex,
                createdAt: Date.now(),
                source: 'generated_legacy'
            };
            await this._put('secrets', walletSecretRecord);
            console.log('🔐 Generated wallet secret for legacy wallet');
        } else {
            console.log('[Lemma] Using existing wallet secret (source:', walletSecretRecord.source || 'stored', ')');
        }

        // Unlock the wallet (simple local state)
        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + getSessionDurationMs(),
            walletId: walletId,
            walletSecret: walletSecretRecord.secret
        };

        // Persist session locally
        await this._put('session', {
            id: 'current',
            ...this.session
        });

        console.log('✅ Wallet unlocked successfully (local passkey verification)');

        // Signal to server that wallet is unlocked (for cross-device sync)
        // This is a simple state update - no cryptographic verification needed
        // Security comes from HSM-signed lemmas, not this signal
        if (this._isLemmaDomain()) {
            try {
                const activeProfile = await this.getActiveProfile();
                console.log('[Lemma] Signaling unlock to server for cross-device sync...');
                const signalResponse = await fetch('/api/wallet/signal-unlock', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        wallet_id: walletId,
                        unlocked_at: this.session.unlockedAt,
                        expires_at: Math.floor(this.session.expiresAt / 1000),
                        profile_id: activeProfile.id,
                        profile_name: activeProfile.name
                    })
                });
                if (signalResponse.ok) {
                    const result = await signalResponse.json();
                    console.log(`[Lemma] ✅ Server notified of unlock - cross-device sync enabled`);
                    // Store that we have a server session for this wallet
                    this.session.serverSessionActive = true;
                    await this._put('session', { id: 'current', ...this.session });
                } else {
                    console.warn('[Lemma] Could not signal unlock to server:', signalResponse.status);
                }
            } catch (e) {
                console.warn('[Lemma] Could not signal unlock:', e.message);
                // Non-fatal - local unlock still works, just no cross-device sync
            }
        }

        // Start heartbeat on third-party sites
        if (!window.location.hostname.includes('lemma.id') &&
            !window.location.hostname.includes('localhost')) {
            this.startSessionHeartbeat(300000); // 5 minute backup (primary is tab focus)
        }

        return {
            success: true,
            expiresAt: this.session.expiresAt,
            expiresIn: getSessionDurationMs(),
            walletId: walletId,
            walletSecret: walletSecretRecord.secret
        };
    }
    // NOTE: unlockWithServerSession() has been REMOVED
    // Passkeys are now verified 100% locally. Server only stores lock/unlock state.
    // Security comes from HSM-signed lemmas, not server passkey verification.

    /**
     * Lock the wallet (clear session locally and on server)
     */
    async lock() {
        console.log('[Lemma] Locking wallet...');
        
        // Capture wallet_id before clearing session
        // Try session first, then IndexedDB as fallback
        let walletId = this.session.walletId;
        console.log('[Lemma] Lock: wallet_id from session:', walletId);
        
        if (!walletId) {
            try {
                const walletIdRecord = await this._get('passkey', 'walletId');
                walletId = walletIdRecord?.value;
                console.log('[Lemma] Lock: wallet_id from IndexedDB:', walletId);
            } catch (e) {
                console.warn('[Lemma] Lock: could not get wallet_id from IndexedDB:', e.message);
            }
        }
        
        // Clear local session
        this.session = {
            isUnlocked: false,
            unlockedAt: null,
            expiresAt: null,
            walletSecret: null
        };
        await this._delete('session', 'current');
        console.log('[Lemma] Lock: local session cleared');
        
        // Stop heartbeat, SSE, and visibility listeners
        if (this._heartbeatInterval) {
            clearInterval(this._heartbeatInterval);
            this._heartbeatInterval = null;
        }
        if (this._sessionEventSource) {
            this._sessionEventSource.close();
            this._sessionEventSource = null;
        }
        if (this._visibilityHandler) {
            document.removeEventListener('visibilitychange', this._visibilityHandler);
            this._visibilityHandler = null;
        }
        if (this._focusHandler) {
            window.removeEventListener('focus', this._focusHandler);
            this._focusHandler = null;
        }
        
        // Clear server session AND global session (for cross-device lock detection)
        const isLemma = this._isLemmaDomain();
        console.log('[Lemma] Lock: isLemmaDomain=', isLemma, 'walletId=', walletId);
        
        if (isLemma && walletId) {
            try {
                console.log('[Lemma] Lock: calling /api/wallet/clear-session...');
                const response = await fetch('/api/wallet/clear-session', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        ...this._getSecureHeaders(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ wallet_id: walletId })
                });
                if (response.ok) {
                    const data = await response.json();
                    console.log('[Lemma] ✅ Wallet locked, server notified. global_session_cleared:', data.global_session_cleared);
                } else {
                    console.warn('[Lemma] Lock: clear-session returned', response.status);
                }
            } catch (e) {
                console.warn('[Lemma] Failed to clear global session:', e.message);
            }
        } else if (!isLemma) {
            console.log('[Lemma] Wallet locked locally (not on lemma.id)');
        } else {
            console.warn('[Lemma] Lock: no wallet_id available to clear global session');
        }
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
     * Get basic authentication state (internal use)
     * For public API, use the async getAuthState() method
     */
    _getBasicAuthState() {
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
        const authState = this._getBasicAuthState();
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
        const localState = this._getBasicAuthState();
        
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
     * // If not authenticated, user will be redirected to lemma.id/unlock
     */
    async ensureAuthenticated(options = {}) {
        const { 
            autoRedirect = true, 
            returnUrl = window.location.href 
        } = options;
        
        await this.init();
        
        // Check if we're on lemma.id (first-party)
        if (window.location.hostname.includes('lemma.id')) {
            const localAuth = this._getBasicAuthState();
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
                const unlockUrl = `https://lemma.id/unlock?return=${encodeURIComponent(returnUrl)}`;
                window.location.href = unlockUrl;
                return { authenticated: false, redirecting: true };
            }
            
            return { 
                authenticated: false, 
                needsUnlock: true,
                unlockUrl: `https://lemma.id/unlock?return=${encodeURIComponent(returnUrl)}`
            };
            
        } catch (e) {
            console.error('[Lemma] Bridge check failed:', e);
            
            if (autoRedirect) {
                const unlockUrl = `https://lemma.id/unlock?return=${encodeURIComponent(returnUrl)}`;
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
     * Use this after redirect back from lemma.id/unlock
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
    async _sendBridgeMessage(type, payload, timeout = 5000) {
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
            // 5s timeout to handle slower connections + SW cache misses
            this._bridgeReady = false;
            await new Promise((resolve) => {
                const timeoutId = setTimeout(() => {
                    window.removeEventListener('message', handler);
                    if (!this._bridgeReady) {
                        console.warn('[Lemma] Bridge ready timeout (5s) - bridge may not have loaded');
                    }
                    resolve();
                }, 5000);

                const handler = (event) => {
                    if (event.origin === 'https://lemma.id' &&
                        event.data?.type === 'WALLET_BRIDGE_READY') {
                        this._bridgeReady = true;
                        clearTimeout(timeoutId);
                        window.removeEventListener('message', handler);
                        console.log('[Lemma] Bridge ready, session:', event.data.session?.valid ? 'active' : 'none');
                        resolve();
                    }
                };

                window.addEventListener('message', handler);
            });

            // Set up persistent listener for instant session invalidation (via BroadcastChannel)
            // This enables instant lock detection when user locks wallet in another tab
            this._setupSessionInvalidationListener();
            
            // If bridge didn't signal ready, set up a background listener
            // so it can become ready later (e.g., slow network)
            if (!this._bridgeReady) {
                const lateHandler = (event) => {
                    if (event.origin === 'https://lemma.id' &&
                        event.data?.type === 'WALLET_BRIDGE_READY') {
                        this._bridgeReady = true;
                        window.removeEventListener('message', lateHandler);
                        console.log('[Lemma] Bridge became ready (late load)');
                    }
                };
                window.addEventListener('message', lateHandler);
            }
        }
        
        // If bridge never signaled ready, don't attempt postMessage
        // (it would fail with origin mismatch since iframe is still at about:blank)
        if (!this._bridgeReady) {
            throw new Error('Bridge not ready (still loading or blocked)');
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
            
            // Guard: Ensure bridge contentWindow is accessible before posting
            if (bridge.contentWindow) {
                try {
                    bridge.contentWindow.postMessage({ type, payload, requestId }, 'https://lemma.id');
                } catch (e) {
                    console.warn('[Lemma] Bridge postMessage failed:', e.message);
                    clearTimeout(timeoutId);
                    window.removeEventListener('message', handler);
                    reject(new Error('Bridge not ready'));
                }
            } else {
                console.warn('[Lemma] Bridge contentWindow not available');
                clearTimeout(timeoutId);
                window.removeEventListener('message', handler);
                reject(new Error('Bridge not ready'));
            }
        });
    }

    /**
     * Set up persistent listener for session invalidation messages from bridge
     * This enables instant lock detection via BroadcastChannel (same-device sync)
     * @private
     */
    _setupSessionInvalidationListener() {
        // Only set up once
        if (this._sessionInvalidationListenerActive) return;
        this._sessionInvalidationListenerActive = true;

        const handler = (event) => {
            // Only accept messages from lemma.id
            if (!event.origin.includes('lemma.id')) return;

            const { type, walletId, reason, instant } = event.data || {};

            if (type === 'SESSION_INVALIDATED') {
                console.log(`[Lemma] Session invalidated via bridge (instant: ${instant}, reason: ${reason})`);

                // Clear in-memory session immediately
                if (this.session) {
                    this.session.isUnlocked = false;
                    this.session.expiresAt = 0;
                    this.session.walletSecret = null;
                }

                // CRITICAL: Clear IndexedDB session so it doesn't persist across reloads
                // This ensures the lock signal truly invalidates the cached session
                // NOTE: We only clear the SESSION, not the secrets. The secrets remain
                // so re-authentication is faster. The bridge will refuse to provide
                // them anyway when locked, so this is safe.
                (async () => {
                    try {
                        await this._delete('session', 'current');
                        console.log('[Lemma] IndexedDB session cleared (lock propagated)');
                    } catch (e) {
                        console.warn('[Lemma] Failed to clear IndexedDB session:', e.message);
                    }
                })();

                // Emit event for app to handle (e.g., show login prompt, redirect)
                this._emitSessionEvent('session_invalidated', {
                    walletId,
                    reason,
                    instant: !!instant
                });
            } else if (type === 'SESSION_RESTORED') {
                console.log(`[Lemma] Session restored via bridge (instant: ${instant})`);

                // Emit event for app to refresh state
                this._emitSessionEvent('session_restored', {
                    walletId,
                    instant: !!instant
                });
            }
        };

        window.addEventListener('message', handler);
        console.log('[Lemma] Session invalidation listener active (instant lock detection enabled)');
    }

    /**
     * Emit session-related events for apps to listen to
     * @private
     */
    _emitSessionEvent(eventName, detail) {
        // Dispatch custom event on window for apps to listen
        const event = new CustomEvent(`lemma:${eventName}`, { detail });
        window.dispatchEvent(event);

        // Also call registered callback if any
        if (this._sessionCallbacks && this._sessionCallbacks[eventName]) {
            this._sessionCallbacks[eventName](detail);
        }
    }

    /**
     * Register callback for session events
     * @param {string} eventName - 'session_invalidated' or 'session_restored'
     * @param {Function} callback - Function to call when event occurs
     */
    onSessionEvent(eventName, callback) {
        if (!this._sessionCallbacks) {
            this._sessionCallbacks = {};
        }
        this._sessionCallbacks[eventName] = callback;
    }

    /**
     * Sync session to the bridge iframe
     * This is critical for cross-site unlock to work - the bridge has a separate
     * IndexedDB (lemma.id origin) and needs the wallet_id to check global sessions.
     * @private
     */
    async _syncSessionToBridge(session, walletSecret) {
        if (this._isLemmaDomain()) {
            // On lemma.id, bridge isn't needed
            return;
        }

        try {
            console.log('[Lemma] Syncing session to bridge...');
            const result = await this._sendBridgeMessage('SET_LOCAL_SESSION', {
                session: {
                    isUnlocked: session.isUnlocked,
                    unlockedAt: session.unlockedAt,
                    expiresAt: session.expiresAt,
                    walletId: session.walletId
                },
                walletSecret: walletSecret
            }, 5000);

            if (result?.success) {
                console.log('[Lemma] ✅ Session synced to bridge');
            } else {
                console.warn('[Lemma] Bridge session sync failed:', result?.error);
            }
        } catch (e) {
            console.warn('[Lemma] Bridge session sync error:', e.message);
        }
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

    // In-memory cache for issuer public keys (avoids IndexedDB reads)
    _issuerCache = new Map();
    
    /**
     * Get an issuer's info (cached for fast verification)
     */
    async getIssuer(issuerDid) {
        // Check memory cache first (FAST PATH)
        if (this._issuerCache.has(issuerDid)) {
            return this._issuerCache.get(issuerDid);
        }
        
        await this.init();
        const issuer = await this._get('issuers', issuerDid);
        
        // Cache for future lookups
        if (issuer) {
            this._issuerCache.set(issuerDid, issuer);
        }
        
        return issuer;
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
     * 
     * Checks THREE things:
     * 1. Is the credential_id in the Bloom filter? (device-level revocation)
     * 2. Is the PPID in the Bloom filter? (user-level revocation - all devices, one site)
     * 3. Is the wallet_id in the Bloom filter? (wallet-level revocation - all devices, ALL sites)
     * 
     * @param {string} credentialId - The credential ID to check
     * @param {string} ppid - Optional PPID from credential claims (for user-level revocation)
     */
    // In-memory cache for revocation list (avoids IndexedDB reads)
    _revocationCache = { set: null, lastSynced: null, walletId: null };
    
    async isRevoked(credentialId, ppid = null) {
        // Use in-memory cache if available (FAST PATH - no IndexedDB)
        if (!this._revocationCache.set) {
            const revocations = await this._get('revocations', 'current');
            if (!revocations || !revocations.listArray) {
                return { revoked: false, unchecked: true };
            }
            // Convert array to Set for O(1) lookups
            this._revocationCache.set = new Set(revocations.listArray);
            this._revocationCache.lastSynced = revocations.lastSynced;
        }
        
        // Cache wallet ID (doesn't change during session)
        if (!this._revocationCache.walletId) {
            this._revocationCache.walletId = this.walletId || this.session?.walletId || await this._getWalletId();
        }
        
        const revokedSet = this._revocationCache.set;
        
        // O(1) Set lookups instead of O(n) Array.includes()
        const credentialRevoked = revokedSet.has(credentialId);
        const ppidRevoked = ppid ? revokedSet.has(ppid) : false;
        const walletId = this._revocationCache.walletId;
        const walletRevoked = walletId ? revokedSet.has(walletId) : false;
        
        const isRevoked = credentialRevoked || ppidRevoked || walletRevoked;
        
        // Determine revocation reason (most severe first)
        let reason = null;
        if (isRevoked) {
            if (walletRevoked) {
                reason = 'wallet_revoked';  // Most severe: ALL sites compromised
            } else if (ppidRevoked) {
                reason = 'user_revoked';    // Site-level: user banned from site
            } else {
                reason = 'credential_revoked';  // Device-level: one credential
            }
        }
        
        return {
            revoked: isRevoked,
            credentialRevoked: credentialRevoked,
            ppidRevoked: ppidRevoked,
            walletRevoked: walletRevoked,
            unchecked: false,
            lastSynced: this._revocationCache.lastSynced,
            reason: reason
        };
    }
    
    /**
     * Invalidate revocation cache (call when SSE pushes new revocation)
     */
    invalidateRevocationCache() {
        this._revocationCache = { set: null, lastSynced: null, walletId: this._revocationCache.walletId };
        console.log('[Lemma] Revocation cache invalidated');
    }
    
    /**
     * Get wallet ID from IndexedDB
     */
    async _getWalletId() {
        try {
            const secrets = await this._get('secrets', 'master');
            return secrets?.walletId || null;
        } catch (e) {
            return null;
        }
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
    
    /**
     * Revoke a credential - adds to bloom filter AND deletes locally
     * This ensures the credential is invalidated across ALL sites.
     * 
     * Flow:
     * 1. Calls server API to add credential ID to revocation list (bloom filter)
     * 2. Server publishes event to trigger sync on all sites
     * 3. Deletes credential from local IndexedDB
     * 4. Syncs local revocation list
     * 
     * @param {string} credentialId - ID of credential to revoke
     * @param {string} reason - Reason for revocation (optional)
     * @returns {Object} Result with revoked, serverRevoked, addedToBloomFilter flags
     */
    async revokeCredential(credentialId, reason = 'user_requested') {
        await this.init();
        
        if (!credentialId) {
            return { success: false, error: 'credentialId required' };
        }
        
        // On third-party sites, use bridge
        if (this._isThirdPartySite()) {
            try {
                const result = await this._sendBridgeMessage('REVOKE_CREDENTIAL', {
                    credentialId,
                    reason
                });
                
                if (result.success) {
                    console.log(`🚨 Credential revoked: ${credentialId}`);
                    console.log(`   Server revoked: ${result.serverRevoked}`);
                    console.log(`   Bloom filter: ${result.addedToBloomFilter}`);
                }
                
                return result;
            } catch (e) {
                console.error('Bridge revoke failed:', e);
                return { success: false, error: e.message };
            }
        }
        
        // On lemma.id, revoke directly
        let serverRevoked = false;
        
        // 1. Get credential info for site targeting
        const credentials = await this.getCredentials();
        const credential = credentials.find(c => c.id === credentialId);
        let siteId = null;
        let credType = 'permission';
        
        if (credential) {
            const claims = credential.claims || credential.credentialSubject || {};
            siteId = claims.siteId || claims.site_id || null;
            credType = credential.packageType || 'permission';
        }
        
        // 2. Call server API to add to revocation list
        try {
            const response = await fetch('/api/wallet/revoke', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    credential_id: credentialId,
                    credential_type: credType,
                    site_domain: siteId,
                    reason: reason
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                serverRevoked = data.success;
                console.log(`✅ Server revocation: ${credentialId}`, data);
            } else {
                console.warn(`⚠️ Server revocation failed: ${response.status}`);
            }
        } catch (e) {
            console.warn(`⚠️ Server revocation error: ${e.message}`);
        }
        
        // 3. Delete from local IndexedDB
        await this.removeCredential(credentialId);
        
        // 4. Sync revocation list locally
        await this.syncRevocations();
        
        console.log(`🚨 Credential revoked: ${credentialId}`);
        return {
            success: true,
            revoked: true,
            serverRevoked: serverRevoked,
            credentialId: credentialId,
            addedToBloomFilter: serverRevoked,
            locallyDeleted: true,
            sitesShouldSync: true
        };
    }
    
    /**
     * Force all sites to sync their revocation lists
     * Call this after revoking to ensure propagation
     */
    async triggerRevocationSync() {
        // Sync our own list
        const result = await this.syncRevocations();
        
        // On third-party sites, also tell the bridge to sync
        if (this._isThirdPartySite()) {
            try {
                await this._sendBridgeMessage('SYNC_REVOCATIONS', {});
            } catch (e) {
                console.warn('Bridge sync failed:', e);
            }
        }
        
        return result;
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
        
        // Extract PPID for user-level revocation check
        // W3C structure: subject is at top level, claims are in credentialSubject
        const claims = lemma.claims || lemma.credentialSubject || {};
        // Check top-level subject field first (W3C standard), then fallback to claims
        const ppid = lemma.subject || claims.id || claims.ppid || claims.subject || claims.userPpid;
        
        // 1. Check revocation (local cache) - checks BOTH credential_id AND ppid
        const revocationStatus = await this.isRevoked(lemma.id, ppid);
        if (revocationStatus.revoked) {
            const reason = revocationStatus.ppidRevoked ? 'User revoked (all devices)' : 'Credential revoked';
            return { valid: false, reason: reason, quickVerify: true, revocationDetails: revocationStatus };
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
        // Skip init() — caller (verifyLocalAuthorization) already initialized
        if (!this._initialized) await this.init();
        
        const startTime = performance.now();
        
        // Extract PPID for user-level revocation check
        // W3C structure: subject is at top level, claims are in credentialSubject
        const claims = lemma.claims || lemma.credentialSubject || {};
        // Check top-level subject field first (W3C standard), then fallback to claims
        const ppid = lemma.subject || claims.id || claims.ppid || claims.subject || claims.userPpid;

        // 1. Check revocation (local cache) - checks BOTH credential_id AND ppid
        const revocationStatus = await this.isRevoked(lemma.id, ppid);
        if (revocationStatus.revoked) {
            const reason = revocationStatus.ppidRevoked ? 'User revoked (all devices)' : 'Credential revoked';
            return { valid: false, reason: reason, revocationDetails: revocationStatus };
        }

        // 2. Check expiration
        const expiredCheck = this._checkExpiration(lemma);
        if (!expiredCheck.valid) {
            return { valid: false, reason: 'Expired' };
        }
        
        // 3. Check if we can skip signature verification (in-memory + persisted cache)
        if (!forceSignatureCheck) {
            // Fast: in-memory cache (same page session)
            if (this._verifiedSignatures.has(lemma.id)) {
                const verifyTime = ((performance.now() - startTime) * 1000).toFixed(1);
                return {
                    valid: true,
                    signatureCached: true,
                    verifyTimeUs: verifyTime,
                    revocationUnchecked: revocationStatus.unchecked
                };
            }
            
            // Medium: IndexedDB persisted cache (survives page reload)
            try {
                const cached = await this._get('session', `verified_${lemma.id}`);
                if (cached && cached.sig === (lemma.proof?.signatureValue || lemma.signature)) {
                    // Signature hasn't changed — trust the cached result
                    this._verifiedSignatures.add(lemma.id);
                    const verifyTime = ((performance.now() - startTime) * 1000).toFixed(1);
                    return {
                        valid: true,
                        signatureCached: true,
                        verifyTimeUs: verifyTime,
                        revocationUnchecked: revocationStatus.unchecked,
                        issuer: cached.issuer
                    };
                }
            } catch (_) {}
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
            
            // Cache successful verification (in-memory + persisted)
            this._verifiedSignatures.add(lemma.id);
            try {
                await this._put('session', {
                    id: `verified_${lemma.id}`,
                    sig: lemma.proof?.signatureValue || lemma.signature,
                    issuer: issuerName,
                    at: Date.now()
                });
            } catch (_) {}
            
                    } catch (e) {
            this._warn('Signature verification error:', e.message);
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

    // ========================================
    // INTERNAL LEMMA ISSUANCE
    // ========================================
    // When a user has a valid session but no lemma for the current site,
    // the SDK requests issuance from lemma.id's API internally.
    // The wallet_secret NEVER leaves the SDK — only the derived PPID
    // is sent to lemma.id, which returns an HSM-signed credential.
    // ========================================

    /**
     * Request lemma issuance from lemma.id for the current site.
     * The wallet_secret stays in the browser — only the site-specific PPID is sent.
     * 
     * @param {string} siteId - The site to issue a lemma for
     * @returns {Promise<Object>} { success, ppid, lemma } or { success: false, error }
     * @private
     */
    async _autoIssueLemma(siteId) {
        try {
            // Derive PPID locally — wallet_secret stays in the SDK
            const ppid = await this.derivePPID(siteId);
            
            console.log(`[Lemma] Requesting lemma issuance for ${siteId} (PPID-only, no secret transmitted)`);
            
            const response = await fetch('https://lemma.id/api/wallet-auth/issue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    site_id: siteId,
                    ppid: ppid
                })
            });
            
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                console.warn(`[Lemma] Lemma issuance failed: ${response.status}`, err);
                return { success: false, error: err.error || 'issuance_failed' };
            }
            
            const result = await response.json();
            
            if (result.success && result.permission_lemma) {
                // Store the issued lemma locally
                await this.storeCredential(result.permission_lemma);
                
                // Verify the lemma we just received (Ed25519 signature check)
                const verification = await this.verifyLemma(result.permission_lemma);
                if (!verification.valid) {
                    console.error('[Lemma] Issued lemma failed verification:', verification.reason);
                    return { success: false, error: 'verification_failed' };
                }
                
                console.log(`[Lemma] Lemma issued and verified for ${siteId}`);
                return {
                    success: true,
                    ppid: ppid,
                    lemma: result.permission_lemma,
                    claims: result.permission_lemma.claims || result.permission_lemma.credentialSubject || {}
                };
            }
            
            return { success: false, error: result.error || 'no_lemma_returned' };
        } catch (e) {
            console.warn('[Lemma] Auto-issue failed:', e.message);
            return { success: false, error: e.message };
        }
    }

    // ========================================
    // SIMPLIFIED THIRD-PARTY VERIFICATION
    // ========================================
    // For third-party sites: Just check local session + verify local lemmas
    // NO network calls, NO wallet_secret fetching
    // ~15ms total, 100% local
    // ========================================

    /**
     * Verify authorization for the current site using local lemmas.
     * This is the SIMPLIFIED flow for third-party sites.
     * 
     * Flow:
     * 1. Check local session state (is wallet unlocked?)
     * 2. Get lemmas for this site from IndexedDB
     * 3. Verify HSM signature (WASM)
     * 4. Return result - NO network calls!
     * 
     * @param {Object} options - Optional configuration
     * @param {string} options.permission - Required permission type (default: 'login')
     * @param {string} options.siteId - Override site ID (default: current hostname)
     * @returns {Promise<Object>} { authorized, reason, lemma, verifyTimeMs }
     */
    async verifyLocalAuthorization(options = {}) {
        const startTime = performance.now();
        // Skip init() if already initialized (hot path optimization)
        if (!this._initialized) await this.init();
        
        const permission = options.permission || 'login';
        const siteId = options.siteId || window.location.hostname;
        
        // STEP 1: Check local session state (in-memory, ~0ms)
        if (!this.session.isUnlocked) {
            return {
                authorized: false,
                reason: 'wallet_locked',
                message: 'Wallet must be unlocked to access this site',
                verifyTimeMs: (performance.now() - startTime).toFixed(1)
            };
        }
        
        if (this.session.expiresAt && Date.now() > this.session.expiresAt) {
            return {
                authorized: false,
                reason: 'session_expired',
                message: 'Session has expired - please unlock wallet again',
                verifyTimeMs: (performance.now() - startTime).toFixed(1)
            };
        }
        
        // STEP 2: Find lemma for this site (fast path: check cached ID first)
        let lemma = null;
        const cachedLemmaId = this._siteToLemmaId?.[siteId];
        
        if (cachedLemmaId) {
            // Fast path: direct ID lookup (~2ms vs ~10ms for getAll+filter)
            lemma = await this._get('lemmas', cachedLemmaId);
        }
        
        if (!lemma) {
            // Slow path: scan all lemmas (first visit to this site in this session)
            const allLemmas = await this._getAll('lemmas');
            
            const siteLemmas = allLemmas.filter(l => {
                const claims = l.claims || l.credentialSubject || {};
                const lemmaSiteId = claims.siteId || claims.site_id || claims.domain || l.siteId;
                const lemmaPermission = claims.permission || claims.permissions || l.permission;
                
                const siteMatches = lemmaSiteId === siteId || 
                                   siteId.endsWith('.' + lemmaSiteId) ||
                                   lemmaSiteId === '*';
                const permissionMatches = !permission || 
                                          lemmaPermission === permission ||
                                          (Array.isArray(lemmaPermission) && lemmaPermission.includes(permission));
                
                return siteMatches && permissionMatches;
            });
            
            if (siteLemmas.length === 0) {
                return {
                    authorized: false,
                    reason: 'no_lemma',
                    message: `No authorization found for this site. Please sign in via lemma.id.`,
                    verifyTimeMs: (performance.now() - startTime).toFixed(1)
                };
            }
            
            // Most recent first
            siteLemmas.sort((a, b) => (b.issuedAt || b.storedAt || 0) - (a.issuedAt || a.storedAt || 0));
            lemma = siteLemmas[0];
            
            // Cache the mapping for instant lookup next time
            if (!this._siteToLemmaId) this._siteToLemmaId = {};
            this._siteToLemmaId[siteId] = lemma.id;
        }
        
        // STEP 3: Verify the lemma (signature cached across page loads)
        const verification = await this.verifyLemma(lemma);
        
        const totalTime = (performance.now() - startTime).toFixed(1);
        
        if (!verification.valid) {
            this._log(`[Lemma] Lemma verification failed: ${verification.reason}`);
            return {
                authorized: false,
                reason: 'verification_failed',
                message: verification.reason,
                verifyTimeMs: totalTime
            };
        }
        
        // Extract PPID from lemma for the site to use
        const claims = lemma.claims || lemma.credentialSubject || {};
        const ppid = lemma.subject || claims.id || claims.ppid || claims.subject;
        
        this._log(`[Lemma] ✅ Verified in ${totalTime}ms`);
        
        return {
            authorized: true,
            ppid: ppid,
            lemma: lemma,
            claims: claims,
            issuer: verification.issuer,
            verifyTimeMs: totalTime,
            signatureCached: verification.signatureCached
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
    
    _prepareAuthenticationOptions(options) {
        return {
            ...options,
            challenge: this._base64urlToBuffer(options.challenge),
            allowCredentials: (options.allowCredentials || []).map(cred => ({
                ...cred,
                id: this._base64urlToBuffer(cred.id)
            }))
        };
    }
    
    _serializeCredential(credential) {
        const response = credential.response;
        const serialized = {
            id: credential.id,
            rawId: this._bufferToBase64url(credential.rawId),
            type: credential.type,
            response: {
                clientDataJSON: this._bufferToBase64url(response.clientDataJSON),
            }
        };
        
        if (response.attestationObject) {
            serialized.response.attestationObject = this._bufferToBase64url(response.attestationObject);
            if (typeof response.getPublicKeyAlgorithm === 'function') {
                serialized.response.publicKeyAlgorithm = response.getPublicKeyAlgorithm();
            }
        }
        
        if (response.authenticatorData) {
            serialized.response.authenticatorData = this._bufferToBase64url(response.authenticatorData);
            serialized.response.signature = this._bufferToBase64url(response.signature);
            if (response.userHandle) {
                serialized.response.userHandle = this._bufferToBase64url(response.userHandle);
            }
        }
        
        if (credential.response.getTransports) {
            serialized.transports = credential.response.getTransports();
        }
        
        return serialized;
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
            this._warn('Lemma verification error:', e);
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
     * Now profile-aware: returns the secret from the active profile.
     * 
     * @param {string} profileId - Optional specific profile ID (defaults to active)
     * @returns {string} 64-char hex string
     */
    async getWalletSecret(profileId = null) {
        await this.init();
        
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to get wallet secret');
        }
        
        // If specific profile requested, get that profile's secret
        if (profileId) {
            const profile = await this._get('profiles', profileId);
            if (profile?.secret) {
                return profile.secret;
            }
            throw new Error('Profile not found');
        }
        
        // Check session cache for active profile secret
        if (this.session.walletSecret) {
            return this.session.walletSecret;
        }
        
        // Get active profile (creates default if needed)
        const activeProfile = await this.getActiveProfile();
        if (activeProfile?.secret) {
            // Cache in session
            this.session.walletSecret = activeProfile.secret;
            this.session.activeProfileId = activeProfile.id;
            return activeProfile.secret;
        }
        
        // Fallback to legacy secrets/master (should not happen with profile system)
        const secretRecord = await this._get('secrets', 'master');
        if (secretRecord?.secret) {
            this.session.walletSecret = secretRecord.secret;
            return secretRecord.secret;
        }
        
        throw new Error('No wallet secret found');
    }

    /**
     * Get passkey credential ID (for server-side PPID derivation fallback)
     */
    async getPasskeyCredentialId() {
        await this.init();
        const passkey = await this._get('passkey', 'primary');
        return passkey?.credentialId || null;
    }

    /**
     * Derive the user's PPID (Pairwise Pseudonymous Identifier) for a specific site.
     * 
     * PPID = did:lemma:ppid_<HMAC-SHA256(wallet_secret, site_id)>
     * 
     * This is the user's IDENTITY for that site - different for every site.
     * The PPID can be used to:
     * - Look up the user in your database (sign-in)
     * - Create a new user record (first-time sign-up)
     * - Verify the user has access (possession of wallet = authenticated)
     * 
     * NO NETWORK CALL to lemma.id - this is pure client-side cryptography.
     * 
     * @param {string} siteId - Your site domain (e.g., 'example.com' or window.location.hostname)
     * @returns {Promise<string>} The user's PPID for your site: did:lemma:ppid_<hash>
     * 
     * @example
     * const wallet = new LemmaWallet();
     * const result = await wallet.autoAuthenticate();
     * if (result.authenticated) {
     *     const ppid = await wallet.derivePPID('example.com');
     *     // Send ppid to your backend: POST /api/auth { ppid }
     *     // Backend checks if ppid exists -> sign in, else -> create account
     * }
     */
    async derivePPID(siteId) {
        await this.init();
        
        if (!this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to derive PPID');
        }
        
        if (!siteId) {
            // Default to current hostname if not specified
            siteId = window.location.hostname;
        }
        
        // Normalize site ID (lowercase, remove www prefix, remove port)
        siteId = siteId.toLowerCase()
            .replace(/^www\./, '')
            .replace(/:\d+$/, '');
        
        // Get wallet secret
        const walletSecret = await this.getWalletSecret();
        
        // Derive PPID using HMAC-SHA256
        const ppidHash = await this._hmacSha256(walletSecret, siteId);
        
        return `did:lemma:ppid_${ppidHash}`;
    }
    
    /**
     * Get authenticated user's PPID for your site - the complete sign-in flow.
     * 
     * This is the simplest way to authenticate users:
     * 1. Checks if wallet is unlocked (user proved possession via passkey)
     * 2. Derives their site-specific PPID (their identity for YOUR site)
     * 
     * NO CALL TO LEMMA.ID - pure client-side cryptographic authentication.
     * 
     * @param {string} siteId - Your site domain (default: current hostname)
     * @returns {Promise<Object>} { authenticated, ppid?, needsPasskey?, error? }
     * 
     * @example
     * const wallet = new LemmaWallet();
     * const result = await wallet.getAuthenticatedPPID();
     * 
     * if (result.authenticated) {
     *     // result.ppid is the user's identity for your site
     *     // Send to YOUR backend: POST /api/auth { ppid: result.ppid }
     *     // Backend: find user by ppid or create new account
     * } else if (result.needsPasskey) {
     *     // Show sign-in button
     * }
     */
    async getAuthenticatedPPID(siteId = null) {
        try {
            await this.init();
            const hostname = siteId || window.location.hostname;
            
            // 1. Check for lemma-based auth (privacy-preserving - no wallet_secret needed)
            //    This handles both: stored lemmas from previous visits AND new redirect returns
            const allLemmas = await this._getAll('lemmas');
            const siteLemma = allLemmas.find(lemma => {
                const claims = lemma.claims || lemma.credentialSubject || {};
                const lemmaSiteId = claims.siteId || claims.site_id || claims.domain || lemma.siteId;
                return lemmaSiteId === hostname || hostname.endsWith('.' + lemmaSiteId);
            });
            
            if (siteLemma && this.session.isUnlocked) {
                // Verify the lemma signature
                const verification = await this.verifyLemma(siteLemma);
                if (verification.valid) {
                    const claims = siteLemma.claims || siteLemma.credentialSubject || {};
                    const ppid = siteLemma.subject || claims.id || claims.ppid || claims.subject;
                    
                    console.log('[Lemma] ✅ Authenticated via stored lemma (no wallet_secret transferred)');
                    return {
                        authenticated: true,
                        ppid: ppid,
                        lemma: siteLemma,
                        needsPasskey: false,
                        message: 'Authenticated via verified lemma'
                    };
                }
            }
            
            // 2. Legacy: check redirect with wallet_secret (backwards compatibility)
            const redirectResult = await this.checkRedirectReturn();
            if (redirectResult?.authenticated && redirectResult.walletSecret) {
                console.log('[Lemma] Authenticated via legacy redirect (wallet_secret)');
                
                const ppidHash = await this._hmacSha256(redirectResult.walletSecret, hostname);
                const ppid = `did:lemma:ppid_${ppidHash}`;
                
                return {
                    authenticated: true,
                    ppid: ppid,
                    needsPasskey: false,
                    message: 'Authenticated via redirect'
                };
            }
            
            // 3. Check if authenticated via autoAuthenticate
            const authResult = await this.autoAuthenticate();
            
            const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
            
            if (!authResult.authenticated) {
                // Check if redirect is needed (mobile Safari storage partitioning)
                if (authResult.needsRedirect) {
                    return {
                        authenticated: false,
                        needsPasskey: false,
                        needsRedirect: true,
                        ppid: null,
                        message: 'Tap Sign In to authenticate (mobile browser)'
                    };
                }
                
                // Check if popup flow is needed (desktop fallback)
                if (authResult.needsPopup) {
                    return {
                        authenticated: false,
                        needsPasskey: false,
                        needsPopup: true,
                        needsRedirect: isMobile, // Suggest redirect for mobile
                        hasSession: true,
                        ppid: null,
                        message: isMobile 
                            ? 'Tap to sign in (mobile browser - redirect recommended)'
                            : authResult.message || 'Tap to sign in'
                    };
                }
                
                return {
                    authenticated: false,
                    needsPasskey: authResult.needsPasskey,
                    needsRedirect: isMobile && authResult.needsPasskey, // Suggest redirect for mobile passkey
                    ppid: null,
                    message: authResult.message
                };
            }
            
            // Derive PPID for this site
            // autoAuthenticate now returns ppid directly (no walletSecret exposure)
            let ppid = authResult.ppid;
            if (!ppid) {
                ppid = await this.derivePPID(siteId || window.location.hostname);
            }
            
            return {
                authenticated: true,
                ppid: ppid,
                needsPasskey: false,
                message: 'Authenticated - PPID derived for your site'
            };
        } catch (e) {
            return {
                authenticated: false,
                ppid: null,
                needsPasskey: true,
                error: e.message
            };
        }
    }

    /**
     * HMAC-SHA256 using Web Crypto API
     * @private
     */
    async _hmacSha256(secret, message) {
        // Convert hex secret to bytes
        const secretBytes = new Uint8Array(
            secret.match(/.{1,2}/g).map(byte => parseInt(byte, 16))
        );
        
        // Import key
        const key = await crypto.subtle.importKey(
            'raw',
            secretBytes,
            { name: 'HMAC', hash: 'SHA-256' },
            false,
            ['sign']
        );
        
        // Sign (HMAC)
        const encoder = new TextEncoder();
        const signature = await crypto.subtle.sign(
            'HMAC',
            key,
            encoder.encode(message)
        );
        
        // Convert to hex
        return Array.from(new Uint8Array(signature))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }

    async getWalletInfo() {
        await this.init();

        const passkey = await this._get('passkey', 'primary');
        const lemmas = await this._getAll('lemmas');
        const issuers = await this._getAll('issuers');
        const secretRecord = await this._get('secrets', 'master');
        const walletIdRecord = await this._get('passkey', 'walletId');
        const activeProfileRecord = await this._get('passkey', 'activeProfile');
        
        // Also check profile for secret (device linking stores here)
        let secretSource = secretRecord?.source || 'stored';
        let profileSecret = null;
        if (activeProfileRecord?.value) {
            const profile = await this._get('profiles', activeProfileRecord.value);
            profileSecret = profile?.secret;
            if (profileSecret && !secretRecord?.secret) {
                secretSource = 'profile_only';
            }
        }
        
        const hasPasskey = !!passkey;
        const hasWalletSecret = !!(secretRecord?.secret || profileSecret);
            
        return {
            hasPasskey,
            hasWalletSecret,
            // hasWallet: true if either passkey (native) or secret (linked device) exists
            hasWallet: hasPasskey || hasWalletSecret,
            isUnlocked: this.isUnlocked(),
            session: this.session,
            walletId: walletIdRecord?.value || null,
            lemmaCount: lemmas.length,
            issuerCount: issuers.length,
            passkeyCredentialId: passkey?.credentialId || null,
            secretSource: secretSource,
            linkedFrom: secretRecord?.linkedFrom || null
        };
    }
    
    /**
     * Get debug info for cross-device troubleshooting.
     * Returns fingerprints (hashes) of secrets for safe comparison without exposing actual values.
     */
    async getDebugState() {
        await this.init();
        
        const secretRecord = await this._get('secrets', 'master');
        const walletIdRecord = await this._get('passkey', 'walletId');
        const activeProfileRecord = await this._get('passkey', 'activeProfile');
        const profiles = await this._getAll('profiles');
        
        // Create fingerprints for safe comparison
        const fingerprint = async (str) => {
            if (!str) return null;
            const data = new TextEncoder().encode(str);
            const hash = await crypto.subtle.digest('SHA-256', data);
            return Array.from(new Uint8Array(hash)).slice(0, 8)
                .map(b => b.toString(16).padStart(2, '0')).join('');
        };
        
        const secretFingerprint = await fingerprint(secretRecord?.secret);
        const profileSecrets = {};
        for (const profile of profiles) {
            profileSecrets[profile.id] = {
                name: profile.name,
                fingerprint: await fingerprint(profile.secret),
                linkedFrom: profile.linkedFrom,
                linkedAt: profile.linkedAt
            };
        }
        
        return {
            walletId: walletIdRecord?.value,
            secretFingerprint: secretFingerprint,  // Compare this between devices!
            secretSource: secretRecord?.source,
            secretLinkedFrom: secretRecord?.linkedFrom,
            secretLinkedAt: secretRecord?.linkedAt,
            activeProfileId: activeProfileRecord?.value,
            profiles: profileSecrets,
            // If devices are properly linked, secretFingerprint should MATCH
            debugNote: 'If secretFingerprint differs between devices, linking failed!'
        };
    }

    // ========================================
    // WALLET PROFILES (Multiple Identities)
    // ========================================

    /**
     * Get the active profile. Creates default profile if none exists.
     * @returns {Object} { id, name, secret, createdAt, isDefault }
     */
    async getActiveProfile() {
        await this.init();
        
        // Get active profile ID from settings
        const activeProfileSetting = await this._get('passkey', 'activeProfile');
        const activeProfileId = activeProfileSetting?.value || DEFAULT_PROFILE_ID;
        
        // Get the profile
        let profile = await this._get('profiles', activeProfileId);
        
        // If no profile exists, migrate from legacy or create default
        if (!profile) {
            profile = await this._migrateOrCreateDefaultProfile();
        }
        
        return profile;
    }
    
    /**
     * Migrate existing wallet secret to default profile, or create new default profile
     * @private
     */
    async _migrateOrCreateDefaultProfile() {
        // Check for existing wallet secret (legacy single-wallet)
        const existingSecret = await this._get('secrets', 'master');
        
        let profile;
        if (existingSecret?.secret) {
            // Migrate existing wallet to default profile
            console.log('[Lemma] Migrating existing wallet to default profile');
            profile = {
                id: DEFAULT_PROFILE_ID,
                name: 'Personal',
                secret: existingSecret.secret,
                createdAt: existingSecret.createdAt || Date.now(),
                isDefault: true,
                migratedFrom: 'legacy'
            };
        } else {
            // Create new default profile with new secret
            console.log('[Lemma] Creating new default profile');
            const secretBytes = crypto.getRandomValues(new Uint8Array(32));
            const secretHex = Array.from(secretBytes)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            profile = {
                id: DEFAULT_PROFILE_ID,
                name: 'Personal',
                secret: secretHex,
                createdAt: Date.now(),
                isDefault: true
            };
        }
        
        await this._put('profiles', profile);
        
        // Also keep secrets/master in sync for backward compatibility
        await this._put('secrets', {
            id: 'master',
            secret: profile.secret,
            createdAt: profile.createdAt,
            activeProfileId: profile.id
        });
        
        // Set as active profile
        await this._put('passkey', { id: 'activeProfile', value: profile.id });
        
        return profile;
    }
    
    /**
     * List all profiles
     * @returns {Array} List of profile objects
     */
    async listProfiles() {
        await this.init();
        
        let profiles = await this._getAll('profiles');
        
        // If no profiles exist, create default
        if (!profiles || profiles.length === 0) {
            const defaultProfile = await this._migrateOrCreateDefaultProfile();
            profiles = [defaultProfile];
        }
        
        // Get active profile ID
        const activeProfileSetting = await this._get('passkey', 'activeProfile');
        const activeProfileId = activeProfileSetting?.value || DEFAULT_PROFILE_ID;
        
        // Mark which one is active
        return profiles.map(p => ({
            ...p,
            isActive: p.id === activeProfileId
        }));
    }
    
    /**
     * Create a new profile
     * @param {string} name - Display name for the profile (e.g., "Work", "Personal")
     * @returns {Object} The created profile
     */
    async createProfile(name) {
        await this.init();
        
        if (!name || name.trim().length === 0) {
            throw new Error('Profile name is required');
        }
        
        // Generate profile ID from name
        const id = name.toLowerCase().replace(/[^a-z0-9]/g, '_').substring(0, 20) + 
                   '_' + Date.now().toString(36);
        
        // Check if profile with this name already exists
        const existing = await this._getAll('profiles');
        if (existing.some(p => p.name.toLowerCase() === name.toLowerCase())) {
            throw new Error('A profile with this name already exists');
        }
        
        // Generate new secret for this profile
        const secretBytes = crypto.getRandomValues(new Uint8Array(32));
        const secretHex = Array.from(secretBytes)
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
        
        const profile = {
            id: id,
            name: name.trim(),
            secret: secretHex,
            createdAt: Date.now(),
            isDefault: false
        };
        
        await this._put('profiles', profile);
        console.log(`[Lemma] Created profile: ${name}`);
        
        return profile;
    }
    
    /**
     * Switch to a different profile
     * @param {string} profileId - ID of the profile to switch to
     * @returns {Object} The new active profile
     */
    async switchProfile(profileId) {
        await this.init();
        
        const profile = await this._get('profiles', profileId);
        if (!profile) {
            throw new Error('Profile not found');
        }
        
        // Update active profile setting
        await this._put('passkey', { id: 'activeProfile', value: profileId });
        
        // Update secrets/master for backward compatibility
        await this._put('secrets', {
            id: 'master',
            secret: profile.secret,
            createdAt: profile.createdAt,
            activeProfileId: profileId
        });
        
        // Clear cached wallet secret in session
        if (this.session) {
            this.session.walletSecret = profile.secret;
            this.session.activeProfileId = profileId;
        }
        
        // Update server session with new profile (if unlocked on lemma.id)
        if (this.isUnlocked() && this._isLemmaDomain()) {
            try {
                const walletId = await this._get('passkey', 'walletId');
                await fetch('/api/wallet/signal-unlock', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        wallet_id: walletId?.value || this.session.walletId,
                        unlocked_at: this.session.unlockedAt,
                        expires_at: Math.floor(this.session.expiresAt / 1000),
                        profile_id: profile.id,
                        profile_name: profile.name
                    })
                });
                console.log(`[Lemma] Server session updated for profile: ${profile.name}`);
            } catch (e) {
                console.warn('[Lemma] Could not update server session:', e.message);
            }
        }
        
        console.log(`[Lemma] Switched to profile: ${profile.name}`);
        
        return { ...profile, isActive: true };
    }
    
    /**
     * Rename a profile
     * @param {string} profileId - ID of the profile to rename
     * @param {string} newName - New name for the profile
     * @returns {Object} The updated profile
     */
    async renameProfile(profileId, newName) {
        await this.init();
        
        if (!newName || newName.trim().length === 0) {
            throw new Error('Profile name is required');
        }
        
        const profile = await this._get('profiles', profileId);
        if (!profile) {
            throw new Error('Profile not found');
        }
        
        // Check if another profile has this name
        const existing = await this._getAll('profiles');
        if (existing.some(p => p.id !== profileId && p.name.toLowerCase() === newName.toLowerCase())) {
            throw new Error('A profile with this name already exists');
        }
        
        profile.name = newName.trim();
        profile.updatedAt = Date.now();
        
        await this._put('profiles', profile);
        console.log(`[Lemma] Renamed profile to: ${newName}`);
        
        return profile;
    }
    
    /**
     * Delete a profile
     * @param {string} profileId - ID of the profile to delete
     * @returns {boolean} Success
     */
    async deleteProfile(profileId) {
        await this.init();
        
        // Cannot delete default profile
        if (profileId === DEFAULT_PROFILE_ID) {
            throw new Error('Cannot delete the default profile');
        }
        
        const profile = await this._get('profiles', profileId);
        if (!profile) {
            throw new Error('Profile not found');
        }
        
        // Check if this is the active profile
        const activeProfileSetting = await this._get('passkey', 'activeProfile');
        const activeProfileId = activeProfileSetting?.value || DEFAULT_PROFILE_ID;
        
        if (profileId === activeProfileId) {
            // Switch to default before deleting
            await this.switchProfile(DEFAULT_PROFILE_ID);
        }
        
        // Delete the profile
        await this._delete('profiles', profileId);
        console.log(`[Lemma] Deleted profile: ${profile.name}`);
        
        return true;
    }
    
    /**
     * Get extended wallet info including profile information
     * @returns {Object} Extended wallet info with profile data
     */
    async getWalletInfoWithProfiles() {
        await this.init();
        
        const baseInfo = await this.getWalletInfo();
        const profiles = await this.listProfiles();
        const activeProfile = await this.getActiveProfile();
        
        return {
            ...baseInfo,
            profiles: profiles,
            activeProfile: activeProfile,
            profileCount: profiles.length
        };
    }

    // ========================================
    // DEVICE LINKING (wallet_secret transfer)
    // ========================================

    /**
     * Require fresh passkey authentication (not cached session).
     * Used for sensitive operations like device linking to ensure user presence.
     * 
     * SECURITY: This forces a NEW WebAuthn assertion regardless of session state.
     * Even if user unlocked 5 minutes ago, they must re-authenticate.
     * 
     * @param {Object} options - { reason: string } for UI prompt context
     * @returns {Object} { success: boolean, walletId: string, timestamp: number }
     * @throws Error if passkey auth fails or is cancelled
     */
    async _requireFreshPasskeyAuth(options = {}) {
        await this.init();
        
        const reason = options.reason || 'Verify your identity';
        console.log(`[Lemma] Fresh passkey auth required: ${reason}`);
        
        // Get stored passkey - must exist
        const passkey = await this._get('passkey', 'primary');
        if (!passkey || !passkey.credentialId) {
            throw new Error('No passkey registered on this device. Cannot verify identity.');
        }
        
        // Generate fresh challenge (never reused)
        const challenge = crypto.getRandomValues(new Uint8Array(32));
        
        try {
            // Force biometric/PIN verification - userVerification: 'required'
            const credential = await navigator.credentials.get({
                publicKey: {
                    challenge: challenge,
                    rpId: window.location.hostname,
                    allowCredentials: [{
                        id: this._base64urlToBuffer(passkey.credentialId),
                        type: 'public-key'
                    }],
                    userVerification: 'required',  // MUST verify user (FaceID/TouchID/PIN)
                    timeout: 60000
                }
            });
            
            if (!credential) {
                throw new Error('Passkey verification cancelled');
            }
            
            console.log('[Lemma] ✅ Fresh passkey verification successful');
            
            const walletIdRecord = await this._get('passkey', 'walletId');
            
            return {
                success: true,
                walletId: walletIdRecord?.value || null,
                timestamp: Date.now(),
                method: 'fresh_passkey'
            };
        } catch (e) {
            console.error('[Lemma] Fresh passkey auth failed:', e.message);
            
            // Provide helpful error messages
            if (e.name === 'NotAllowedError') {
                throw new Error('Passkey verification was cancelled or timed out. Please try again.');
            } else if (e.name === 'SecurityError') {
                throw new Error('Passkey verification failed - security error. Ensure you are on a secure (HTTPS) connection.');
            }
            
            throw new Error(`Identity verification failed: ${e.message}`);
        }
    }

    /**
     * Generate a link code for adding another device.
     * The code contains the encrypted wallet_secret and expires in 60 seconds.
     * 
     * SECURITY:
     * - REQUIRES FRESH PASSKEY AUTH (not cached session) - proves user presence
     * - One-time use code
     * - 60 second expiry
     * - Encrypted with a random key embedded in the code
     * - Device-to-device transfer, no server involved
     * 
     * @param {string} profileId - Optional specific profile to link (defaults to active)
     * @returns {Object} { code: string, qrData: string, expiresAt: number, expiresIn: number, profileName: string }
     */
    async generateLinkCode(profileId = null) {
        try {
            console.log('[Lemma] generateLinkCode: starting...');
            await this.init();
            console.log('[Lemma] generateLinkCode: init complete, db:', !!this.db);
            
            // SECURITY: Require FRESH passkey verification before generating link code
            // This ensures user is physically present and deliberately creating a link
            // Even if wallet was unlocked hours ago, user must re-verify NOW
            console.log('[Lemma] generateLinkCode: requiring fresh passkey verification...');
            const freshAuth = await this._requireFreshPasskeyAuth({
                reason: 'Verify your identity to link another device'
            });
            
            if (!freshAuth.success) {
                throw new Error('Identity verification required to generate link code');
            }
            console.log('[Lemma] generateLinkCode: fresh passkey verified at', new Date(freshAuth.timestamp).toISOString());
            
            // Get the profile to link (specific or active)
            const profile = profileId 
                ? await this._get('profiles', profileId)
                : await this.getActiveProfile();
            
            if (!profile) {
                throw new Error('Profile not found');
            }
            
            const walletSecret = profile.secret;
            console.log('[Lemma] generateLinkCode: walletSecret obtained for profile:', profile.name);
            if (!walletSecret) {
                throw new Error('No wallet secret found');
            }
            
            const walletId = await this._get('passkey', 'walletId');
            console.log('[Lemma] generateLinkCode: walletId:', walletId);
            
            // Generate a random encryption key (16 bytes = 128 bits)
            const encryptionKey = crypto.getRandomValues(new Uint8Array(16));
            const encryptionKeyHex = Array.from(encryptionKey)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            console.log('[Lemma] generateLinkCode: encryption key generated');
            
            // Create payload to encrypt (includes profile info for v2)
            // Note: No unlock token needed - linked device uses signal-unlock
            const payload = JSON.stringify({
                walletSecret: walletSecret,
                walletId: walletId?.value || null,
                profileId: profile.id,
                profileName: profile.name,
                createdAt: Date.now(),
                expiresAt: Date.now() + 60000 // 60 seconds
            });
            console.log('[Lemma] generateLinkCode: payload created for profile:', profile.name);
            
            // Encrypt payload using AES-GCM
            const encryptedPayload = await this._encryptForLink(payload, encryptionKey);
            console.log('[Lemma] generateLinkCode: payload encrypted, length:', encryptedPayload?.length);
            
            // Generate a short numeric code (6 digits) for manual entry
            // This is derived from the encryption key for consistency
            const shortCode = this._deriveShortCode(encryptionKey);
            console.log('[Lemma] generateLinkCode: shortCode:', shortCode);
            
            // QR data contains everything needed to link (self-contained, no local storage needed)
            const qrData = JSON.stringify({
                v: 1, // version
                k: encryptionKeyHex, // encryption key
                p: encryptedPayload, // encrypted payload
                e: Date.now() + 60000 // expiry
            });
            console.log('[Lemma] generateLinkCode: qrData created, length:', qrData.length);
            
            // Create a URL that opens the link page with the code pre-filled
            // This makes scanning work properly on mobile devices
            // Use URL-safe base64 (replace + with -, / with _) to avoid URL encoding issues
            const qrDataBase64 = btoa(qrData).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
            console.log('[Lemma] generateLinkCode: base64 encoded (URL-safe), length:', qrDataBase64.length);
            const qrUrl = `https://lemma.id/link#${qrDataBase64}`;
            console.log('[Lemma] generateLinkCode: qrUrl created, length:', qrUrl.length);
            
            console.log(`[Lemma] Link code generated for profile "${profile.name}" - expires in 60 seconds`);
            
            return {
                shortCode: shortCode,
                qrData: qrData,        // Raw JSON for manual paste
                qrUrl: qrUrl,          // URL for QR code scanning
                expiresAt: Date.now() + 60000,
                expiresIn: 60,
                profileId: profile.id,
                profileName: profile.name
            };
        } catch (e) {
            console.error('[Lemma] generateLinkCode ERROR:', e);
            console.error('[Lemma] generateLinkCode ERROR stack:', e.stack);
            throw e;
        }
    }
    
    /**
     * Link this device to an existing wallet using a link code.
     * This transfers the wallet_secret from another device.
     * 
     * Smart conflict resolution:
     * - Same wallet: Returns success (already linked)
     * - Orphaned wallet (no passkey): Auto-replaces
     * - Different active wallet: Returns conflict for user decision
     * 
     * @param {Object} options - { qrData } or { shortCode }, plus optional { replaceExisting: true }
     * @returns {Object} { success, conflict?, walletId?, needsPasskey?, message }
     */
    async linkDevice(options) {
        await this.init();
        
        // First, decrypt the payload to see what wallet we're linking
        let payload;
        
        if (options.qrData) {
            // Full QR code data
            const normalizedQrData = this._normalizeLinkInput(options.qrData);
            payload = await this._decryptLinkQR(normalizedQrData);
        } else if (options.shortCode) {
            // Short code - need to look up from bridge or prompt QR scan
            throw new Error('Short code linking requires scanning QR on the source device. Please use QR scan.');
        } else {
            throw new Error('Either qrData or shortCode required');
        }
        
        // Validate payload
        if (!payload.walletSecret) {
            throw new Error('Invalid link code - no wallet secret');
        }
        
        if (payload.expiresAt && payload.expiresAt < Date.now()) {
            throw new Error('Link code expired. Please generate a new one on your other device.');
        }
        
        // Check for existing wallet
        const existingSecret = await this._get('secrets', 'master');
        const existingWalletId = await this._get('passkey', 'walletId');
        
        if (existingSecret?.secret) {
            // Same wallet - already linked
            if (existingSecret.secret === payload.walletSecret) {
                console.log('[Lemma] ✅ Wallet already linked to this device');
                return {
                    success: true,
                    alreadyLinked: true,
                    walletId: payload.walletId,
                    message: 'This wallet is already on this device.'
                };
            }
            
            // Different wallet - auto-replace with backup (simplest UX)
            // User can recover old wallet from backup if needed
            console.log('[Lemma] 🔄 Replacing existing wallet (backed up for recovery)');
            console.log('[Lemma]    Old wallet:', existingWalletId?.value?.substring(0, 16) + '...');
            console.log('[Lemma]    New wallet:', payload.walletId?.substring(0, 16) + '...');
            
            // Backup before clearing (stored in localStorage)
                await this._backupWalletData();
                await this._clearWalletData();
        }
        
        // Create or update profile with the linked wallet secret
        const profileId = payload.profileId || DEFAULT_PROFILE_ID;
        const profileName = payload.profileName || 'Personal';
        
        const linkedProfile = {
            id: profileId,
            name: profileName,
            secret: payload.walletSecret,
            createdAt: Date.now(),
            linkedFrom: payload.walletId || 'unknown',
            linkedAt: Date.now(),
            isDefault: profileId === DEFAULT_PROFILE_ID
        };
        
        await this._put('profiles', linkedProfile);
        
        // Also store in secrets/master for backward compatibility
        await this._put('secrets', {
            id: 'master',
            secret: payload.walletSecret,
            createdAt: Date.now(),
            linkedFrom: payload.walletId || 'unknown',
            linkedAt: Date.now(),
            activeProfileId: profileId
        });
        
        // Set as active profile
        await this._put('passkey', { id: 'activeProfile', value: profileId });
        
        // Store wallet ID if provided
        if (payload.walletId) {
            await this._put('passkey', {
                id: 'walletId',
                value: payload.walletId
            });
        }
        
        // Set up local session after device linking
        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + getSessionDurationMs(),
            walletId: payload.walletId,
            walletSecret: payload.walletSecret,
            source: 'link'
        };
        await this._put('session', { id: 'current', ...this.session });
        console.log('[Lemma] ✅ Local session set after linking');
        
        // Signal to server that this device is now unlocked (if on lemma.id)
        let serverSessionSet = false;
        if (this._isLemmaDomain()) {
            try {
                console.log('[Lemma] Signaling unlock to server after device link...');
                const signalResponse = await fetch('/api/wallet/signal-unlock', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        wallet_id: payload.walletId,
                        unlocked_at: now,
                        expires_at: Math.floor(this.session.expiresAt / 1000),
                        profile_id: profileId,
                        profile_name: profileName
                    })
                });
                if (signalResponse.ok) {
                    console.log('[Lemma] ✅ Server notified of linked device unlock');
                    serverSessionSet = true;
                }
            } catch (e) {
                console.warn('[Lemma] Could not signal unlock:', e.message);
            }
        }

        // Check if there's a valid global session (source device might have unlocked)
        // This handles the case where the QR was scanned after the unlock token expired
        // but the source device still has a valid session
        if (!serverSessionSet && payload.walletId) {
            console.log('[Lemma] Trying global session fallback...');
            try {
                const globalSession = await this._checkGlobalSession(payload.walletId, { force: true });

                if (globalSession?.valid && globalSession?.session) {
                    console.log('[Lemma] ✅ Global session found! Wallet was unlocked on another device.');

                    // We have a valid global session - set local session state
                    // The user will still need to create a passkey on this device,
                    // but they can use the wallet immediately
                    this.session = {
                        isUnlocked: true,
                        unlockedAt: globalSession.session.unlocked_at,
                        expiresAt: globalSession.session.expires_at * 1000,
                        walletId: payload.walletId,
                        walletSecret: payload.walletSecret,
                        source: 'global_session'
                    };
                    await this._put('session', { id: 'current', ...this.session });

                    // Note: serverSessionSet stays false because we don't have a cookie on this device
                    // The user will need to create a passkey to get their own session cookie
                    sessionError = null; // Clear error - we found a workaround
                    console.log('[Lemma] Local session set from global session. User should create passkey for full cross-site auth.');
                } else {
                    console.log('[Lemma] No valid global session found.');
                }
            } catch (e) {
                console.warn('[Lemma] Global session check failed:', e.message);
            }
        }

        if (!serverSessionSet && !this.session?.isUnlocked) {
            console.warn('[Lemma] ⚠️ Server session not set - user will need to create passkey for cross-site auth');
        }
        
        console.log(`[Lemma] Device linked successfully with profile: ${profileName}`);
        
        // AUTO-ISSUE: Request lemma.id platform credential for linked device
        // This ensures the new device has a valid signed credential, not just identity
        let platformCredentialIssued = false;
        try {
            console.log('[Lemma] Requesting lemma.id platform credential for linked device...');
            
            const issueResponse = await fetch('https://lemma.id/api/wallet-auth/platform-login', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    wallet_secret: payload.walletSecret,
                    wallet_id: payload.walletId
                })
            });
            
            if (issueResponse.ok) {
                const issueData = await issueResponse.json();
                if (issueData.success && issueData.permission_lemma) {
                    // Store the issued credential
                    await this.storeCredential(issueData.permission_lemma);
                    platformCredentialIssued = true;
                    console.log('[Lemma] ✅ Platform credential issued and stored for linked device');
                }
            }
        } catch (e) {
            console.warn('[Lemma] Could not auto-issue platform credential:', e.message);
            // Non-fatal - user can request credential later
        }
        
        // Build appropriate message based on session state
        let message;
        if (serverSessionSet && platformCredentialIssued) {
            message = `Wallet "${profileName}" linked with full access! Create a passkey to secure it.`;
        } else if (serverSessionSet) {
            message = `Wallet "${profileName}" linked! Create a passkey to secure it.`;
        } else if (this.session?.isUnlocked) {
            message = `Wallet "${profileName}" linked! Create a passkey on this device for full cross-site access.`;
        } else {
            message = `Wallet "${profileName}" linked locally. Create a passkey to enable cross-site authentication.`;
        }

        return {
            success: true,
            walletId: payload.walletId,
            profileId: profileId,
            profileName: profileName,
            needsPasskey: true,
            sessionSet: serverSessionSet,  // FIXED: Accurately reflects if server session cookie was set
            localSessionSet: this.session?.isUnlocked || false,  // Whether local session is active
            sessionSource: this.session?.source || null,  // 'link' or 'global_session'
            sessionError: sessionError,  // Error message if session setup failed
            credentialIssued: platformCredentialIssued,
            message: message
        };
    }
    
    /**
     * Backup current wallet data to localStorage before replacement.
     * Allows recovery if user made a mistake.
     * @private
     */
    async _backupWalletData() {
        try {
            const backup = {
                timestamp: Date.now(),
                secret: await this._get('secrets', 'master'),
                walletId: await this._get('passkey', 'walletId'),
                profiles: await this._getAll('profiles'),
                lemmas: await this._getAll('lemmas'),
                issuers: await this._getAll('issuers')
            };
            
            // Store backup in localStorage (survives IndexedDB clear)
            const existingBackups = JSON.parse(localStorage.getItem('lemma_wallet_backups') || '[]');
            existingBackups.unshift(backup);
            // Keep only last 3 backups
            if (existingBackups.length > 3) {
                existingBackups.pop();
            }
            localStorage.setItem('lemma_wallet_backups', JSON.stringify(existingBackups));
            
            console.log('[Lemma] Wallet data backed up to localStorage');
            return backup;
        } catch (e) {
            console.warn('[Lemma] Backup failed:', e.message);
            return null;
        }
    }
    
    /**
     * Clear all wallet data from IndexedDB stores.
     * Used when replacing an existing wallet during device linking.
     * @private
     */
    async _clearWalletData() {
        try {
            // Clear all stores (including profiles)
            const stores = ['secrets', 'passkey', 'lemmas', 'issuers', 'session', 'revocations', 'profiles'];
            
            for (const storeName of stores) {
                try {
                    const tx = this.db.transaction(storeName, 'readwrite');
                    const store = tx.objectStore(storeName);
                    await new Promise((resolve, reject) => {
                        const request = store.clear();
                        request.onsuccess = () => resolve();
                        request.onerror = () => reject(request.error);
                    });
                } catch (e) {
                    console.warn(`[Lemma] Could not clear store ${storeName}:`, e.message);
                }
            }
            
            // Clear session state
            this.session = {
                isUnlocked: false,
                unlockedAt: null,
                expiresAt: null,
                walletSecret: null
            };
            
            console.log('[Lemma] Wallet data cleared');
            return true;
        } catch (e) {
            console.error('[Lemma] Clear wallet data failed:', e);
            throw new Error('Failed to clear existing wallet data');
        }
    }
    
    /**
     * Get list of wallet backups (for recovery UI)
     * @returns {Array} List of backup objects with timestamps
     */
    getWalletBackups() {
        try {
            return JSON.parse(localStorage.getItem('lemma_wallet_backups') || '[]');
        } catch (e) {
            return [];
        }
    }
    
    /**
     * Restore wallet from a backup
     * @param {number} backupIndex - Index of backup to restore (0 = most recent)
     * @returns {Object} { success, message }
     */
    async restoreWalletFromBackup(backupIndex = 0) {
        await this.init();
        
        const backups = this.getWalletBackups();
        if (!backups[backupIndex]) {
            throw new Error('Backup not found');
        }
        
        const backup = backups[backupIndex];
        
        // Clear current data first
        await this._clearWalletData();
        
        // Restore secret
        if (backup.secret) {
            await this._put('secrets', backup.secret);
        }
        
        // Restore wallet ID
        if (backup.walletId) {
            await this._put('passkey', backup.walletId);
        }
        
        // Restore profiles
        if (backup.profiles) {
            for (const profile of backup.profiles) {
                await this._put('profiles', profile);
            }
        }
        
        // Restore lemmas
        if (backup.lemmas) {
            for (const lemma of backup.lemmas) {
                await this._put('lemmas', lemma);
            }
        }
        
        // Restore issuers
        if (backup.issuers) {
            for (const issuer of backup.issuers) {
                await this._put('issuers', issuer);
            }
        }
        
        console.log('[Lemma] Wallet restored from backup');
        
        return {
            success: true,
            needsPasskey: true,
            message: 'Wallet restored. Create a passkey to secure it.',
            restoredAt: Date.now(),
            backupTimestamp: backup.timestamp,
            profileCount: backup.profiles?.length || 0
        };
    }
    
    /**
     * Encrypt payload for device linking using AES-GCM
     */
    async _encryptForLink(payload, keyBytes) {
        // Import key
        const key = await crypto.subtle.importKey(
            'raw',
            keyBytes,
            { name: 'AES-GCM' },
            false,
            ['encrypt']
        );
        
        // Generate random IV
        const iv = crypto.getRandomValues(new Uint8Array(12));
        
        // Encrypt
        const encoder = new TextEncoder();
        const encrypted = await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv: iv },
            key,
            encoder.encode(payload)
        );
        
        // Combine IV + ciphertext and base64 encode
        const combined = new Uint8Array(iv.length + encrypted.byteLength);
        combined.set(iv, 0);
        combined.set(new Uint8Array(encrypted), iv.length);
        
        return btoa(String.fromCharCode(...combined));
    }
    
    /**
     * Normalize link input to raw QR JSON data.
     * Accepts full URL, hash-only base64, or raw JSON.
     */
    _normalizeLinkInput(linkInput) {
        if (!linkInput || typeof linkInput !== 'string') {
            throw new Error('Invalid link code');
        }
        
        let data = linkInput.trim();
        
        // If a full URL was pasted, extract the hash
        if (/^https?:\/\//i.test(data)) {
            try {
                const url = new URL(data);
                if (url.hash && url.hash.length > 1) {
                    data = url.hash.substring(1);
                }
            } catch (e) {
                // Fall through - treat as raw input
            }
        }
        
        // If not JSON, try base64url decode to JSON
        if (data && data[0] !== '{') {
            let base64 = data.replace(/-/g, '+').replace(/_/g, '/');
            while (base64.length % 4) base64 += '=';
            
            try {
                const decoded = atob(base64);
                JSON.parse(decoded);
                return decoded;
            } catch (e) {
                // Fall through - let JSON.parse throw in _decryptLinkQR
            }
        }
        
        return data;
    }
    
    /**
     * Decrypt QR data from device linking
     */
    async _decryptLinkQR(qrData) {
        const data = JSON.parse(qrData);
        
        if (data.v !== 1) {
            throw new Error('Unsupported link code version');
        }
        
        if (data.e && data.e < Date.now()) {
            throw new Error('Link code expired');
        }
        
        // Convert hex key to bytes
        const keyBytes = new Uint8Array(
            data.k.match(/.{2}/g).map(byte => parseInt(byte, 16))
        );
        
        // Decode base64 payload
        const combined = Uint8Array.from(atob(data.p), c => c.charCodeAt(0));
        
        // Extract IV and ciphertext
        const iv = combined.slice(0, 12);
        const ciphertext = combined.slice(12);
        
        // Import key
        const key = await crypto.subtle.importKey(
            'raw',
            keyBytes,
            { name: 'AES-GCM' },
            false,
            ['decrypt']
        );
        
        // Decrypt
        const decrypted = await crypto.subtle.decrypt(
            { name: 'AES-GCM', iv: iv },
            key,
            ciphertext
        );
        
        const decoder = new TextDecoder();
        return JSON.parse(decoder.decode(decrypted));
    }
    
    /**
     * Derive a 6-digit short code from encryption key
     */
    _deriveShortCode(keyBytes) {
        // Use first 4 bytes to derive a 6-digit number
        const num = (keyBytes[0] << 16) | (keyBytes[1] << 8) | keyBytes[2];
        return String(num % 1000000).padStart(6, '0');
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
     * Get verified permissions for a specific site.
     * 
     * IDEAL FLOW:
     * 1. SDK detects wallet is unlocked
     * 2. Read lemmas from IndexedDB
     * 3. Verify each lemma's Ed25519 signature locally (no network)
     * 4. Check revocation status (cached bloom filter)
     * 5. Return verified claims the user has access to
     * 
     * @param {string} siteId - The site to check permissions for
     * @returns {Promise<Object>} Verified permissions with claims
     */
    async getVerifiedPermissions(siteId) {
        await this.init();
        
        const startTime = performance.now();
        
        // 1. Get all permission lemmas from IndexedDB
        const permissions = await this.getCredentials('permission');
        
        // 2. Filter for requested site
        const sitePermissions = permissions.filter(p => {
            const claims = p.claims || p.credentialSubject || {};
            const credSiteId = claims.siteId || claims.site || claims.site_id || '';
            return credSiteId === siteId || 
                   credSiteId.includes(siteId) || 
                   siteId.includes(credSiteId);
        });
        
        if (sitePermissions.length === 0) {
            return {
                hasAccess: false,
                permissions: [],
                claims: {},
                reason: 'No permissions found for this site'
            };
        }
        
        // 3. Verify each permission locally (Ed25519 + revocation check)
        const verifiedPermissions = [];
        const allClaims = {};
        
        for (const perm of sitePermissions) {
            try {
                const verification = await this.verifyLemma(perm);
                
                if (verification.valid) {
                    verifiedPermissions.push(perm);
                    
                    // Extract claims
                    const claims = perm.claims || perm.credentialSubject || {};
                    for (const [key, value] of Object.entries(claims)) {
                        // Aggregate claims (later lemmas override earlier)
                        allClaims[key] = value;
                    }
                } else {
                    console.warn(`[Lemma] Permission ${perm.id} failed verification: ${verification.reason}`);
                }
            } catch (e) {
                console.warn(`[Lemma] Permission ${perm.id} verification error:`, e.message);
            }
        }
        
        const verifyTime = ((performance.now() - startTime) * 1000).toFixed(1);
        
        // Extract PPID from first verified permission (should be same across all)
        let ppid = null;
        if (verifiedPermissions.length > 0) {
            const firstPerm = verifiedPermissions[0];
            const firstClaims = firstPerm.claims || firstPerm.credentialSubject || {};
            ppid = firstPerm.subject || firstClaims.id || firstClaims.ppid;
        }
        
        return {
            hasAccess: verifiedPermissions.length > 0,
            permissions: verifiedPermissions,
            claims: allClaims,
            // User identity
            ppid: ppid,  // The user's PPID for this site (for revocation purposes)
            // Common claim accessors
            role: allClaims.role || allClaims.accountType || 'user',
            scope: (allClaims.scope || '').split(',').filter(Boolean),
            permissionId: allClaims.permissionId,
            // Performance metrics
            verified: verifiedPermissions.length,
            total: sitePermissions.length,
            verifyTimeUs: verifyTime
        };
    }
    
    /**
     * Check if user has a specific permission for a site.
     * 
     * @param {string} siteId - The site to check
     * @param {string} requiredPermission - Permission to check (e.g., 'admin', 'write')
     * @returns {Promise<boolean>} True if user has verified permission
     */
    async hasPermission(siteId, requiredPermission) {
        const perms = await this.getVerifiedPermissions(siteId);
        
        if (!perms.hasAccess) return false;
        
        // Check scope array
        if (perms.scope.includes(requiredPermission) || 
            perms.scope.includes(`${requiredPermission}:*`) ||
            perms.scope.includes('*')) {
            return true;
        }
        
        // Check role
        if (perms.role === requiredPermission || perms.role === 'admin') {
            return true;
        }
        
        // Check permissionId
        if (perms.permissionId === requiredPermission || 
            perms.permissionId?.includes(requiredPermission)) {
            return true;
        }
        
        return false;
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
    
    // ========================================
    // ON-PAGE DEBUG PANEL
    // ========================================
    // Mobile-friendly debug panel for troubleshooting without devtools
    // Enable via: ?lemma_debug=1 OR LemmaWallet.enableDebug()
    
    let debugPanel = null;
    let debugEnabled = false;
    const debugLogs = [];
    const MAX_DEBUG_LOGS = 100;
    
    function createDebugPanel() {
        if (debugPanel) return debugPanel;
        
        // Create panel container
        debugPanel = document.createElement('div');
        debugPanel.id = 'lemma-debug-panel';
        debugPanel.innerHTML = `
            <style>
                #lemma-debug-panel {
                    position: fixed;
                    bottom: 0;
                    left: 0;
                    right: 0;
                    height: 200px;
                    background: rgba(0, 0, 0, 0.95);
                    color: #00ff00;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 11px;
                    z-index: 999999;
                    display: flex;
                    flex-direction: column;
                    border-top: 2px solid #00ff00;
                    transition: transform 0.3s ease;
                }
                #lemma-debug-panel.minimized {
                    transform: translateY(160px);
                }
                #lemma-debug-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 6px 10px;
                    background: #111;
                    border-bottom: 1px solid #333;
                    cursor: pointer;
                    user-select: none;
                }
                #lemma-debug-header span {
                    font-weight: bold;
                    color: #00ff00;
                }
                #lemma-debug-header button {
                    background: #333;
                    color: #fff;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 3px;
                    cursor: pointer;
                    font-size: 10px;
                    margin-left: 6px;
                }
                #lemma-debug-header button:hover {
                    background: #555;
                }
                #lemma-debug-logs {
                    flex: 1;
                    overflow-y: auto;
                    padding: 8px;
                    line-height: 1.4;
                }
                .lemma-log-entry {
                    padding: 2px 0;
                    border-bottom: 1px solid #222;
                    word-break: break-all;
                }
                .lemma-log-entry.info { color: #00bfff; }
                .lemma-log-entry.warn { color: #ffcc00; }
                .lemma-log-entry.error { color: #ff4444; }
                .lemma-log-entry.success { color: #00ff00; }
                .lemma-log-time {
                    color: #888;
                    margin-right: 6px;
                }
            </style>
            <div id="lemma-debug-header">
                <span>Lemma Debug Panel</span>
                <div>
                    <button onclick="window._lemmaDebugClear()">Clear</button>
                    <button onclick="window._lemmaDebugCopy()">Copy</button>
                    <button id="lemma-debug-toggle" onclick="window._lemmaDebugToggle()">_</button>
                    <button onclick="window._lemmaDebugClose()">X</button>
                </div>
            </div>
            <div id="lemma-debug-logs"></div>
        `;
        
        document.body.appendChild(debugPanel);
        
        // Add existing logs
        debugLogs.forEach(log => addLogToPanel(log));
        
        return debugPanel;
    }
    
    function addLogToPanel(log) {
        if (!debugPanel) return;
        const logsContainer = debugPanel.querySelector('#lemma-debug-logs');
        if (!logsContainer) return;
        
        const entry = document.createElement('div');
        entry.className = `lemma-log-entry ${log.type}`;
        const timeSpan = document.createElement('span');
        timeSpan.className = 'lemma-log-time';
        timeSpan.textContent = log.time;
        entry.appendChild(timeSpan);
        entry.appendChild(document.createTextNode(log.message || ''));
        logsContainer.appendChild(entry);
        logsContainer.scrollTop = logsContainer.scrollHeight;
    }
    
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
    
    function logToDebug(message, type = 'info') {
        const time = new Date().toLocaleTimeString();
        const log = { time, message, type };
        
        debugLogs.push(log);
        if (debugLogs.length > MAX_DEBUG_LOGS) {
            debugLogs.shift();
        }
        
        if (debugEnabled && debugPanel) {
            addLogToPanel(log);
        }
    }
    
    // Intercept console methods for [Lemma] messages
    const originalConsole = {
        log: console.log,
        warn: console.warn,
        error: console.error
    };
    
    function interceptConsole() {
        console.log = function(...args) {
            originalConsole.log.apply(console, args);
            const msg = args.join(' ');
            if (msg.includes('[Lemma]') || msg.includes('Lemma')) {
                const type = msg.includes('✅') ? 'success' : 'info';
                logToDebug(msg, type);
            }
        };
        
        console.warn = function(...args) {
            originalConsole.warn.apply(console, args);
            const msg = args.join(' ');
            if (msg.includes('[Lemma]') || msg.includes('Lemma')) {
                logToDebug(msg, 'warn');
            }
        };
        
        console.error = function(...args) {
            originalConsole.error.apply(console, args);
            const msg = args.join(' ');
            if (msg.includes('[Lemma]') || msg.includes('Lemma')) {
                logToDebug(msg, 'error');
            }
        };
    }
    
    // Debug panel control functions
    window._lemmaDebugClear = function() {
        debugLogs.length = 0;
        if (debugPanel) {
            const logsContainer = debugPanel.querySelector('#lemma-debug-logs');
            if (logsContainer) logsContainer.innerHTML = '';
        }
    };
    
    window._lemmaDebugCopy = function() {
        const text = debugLogs.map(l => `[${l.time}] ${l.message}`).join('\n');
        navigator.clipboard.writeText(text).then(() => {
            logToDebug('Logs copied to clipboard', 'success');
        }).catch(() => {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            logToDebug('Logs copied to clipboard', 'success');
        });
    };
    
    window._lemmaDebugToggle = function() {
        if (debugPanel) {
            debugPanel.classList.toggle('minimized');
            const btn = debugPanel.querySelector('#lemma-debug-toggle');
            btn.textContent = debugPanel.classList.contains('minimized') ? '+' : '_';
        }
    };
    
    window._lemmaDebugClose = function() {
        if (debugPanel) {
            debugPanel.remove();
            debugPanel = null;
        }
        debugEnabled = false;
    };
    
    /**
     * Enable the on-page debug panel
     * Shows all Lemma SDK logs in a mobile-friendly panel
     */
    function enableDebug() {
        if (debugEnabled) return;
        debugEnabled = true;
        interceptConsole();
        
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', createDebugPanel);
        } else {
            createDebugPanel();
        }
        
        logToDebug('Debug panel enabled - Lemma SDK v' + (LemmaWallet.VERSION || 'unknown'), 'success');
        logToDebug('URL: ' + window.location.href, 'info');
        logToDebug('User Agent: ' + navigator.userAgent.substring(0, 80) + '...', 'info');
    }
    
    // Export debug function
    window.enableLemmaDebug = enableDebug;
    LemmaWallet.enableDebug = enableDebug;
    
    // Auto-enable if URL param is set
    if (typeof window !== 'undefined') {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('lemma_debug') === '1' || urlParams.get('lemma_debug') === 'true') {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', enableDebug);
            } else {
                enableDebug();
            }
        }
    }
}

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { LemmaWallet };
}

})(); // End of IIFE
