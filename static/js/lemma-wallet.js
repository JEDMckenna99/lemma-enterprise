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
 */

/** Exact-match trusted Lemma origins for bridge postMessage (no substring matching). */
function isLemmaTrustedOrigin(origin) {
    return origin === 'https://lemma.id' || origin === 'https://www.lemma.id';
}

/** Boundary-safe hostname check (mirrors server _lemma_origin_allowed). */
function isLemmaHostname(hostname) {
    const host = String(hostname || '').trim().toLowerCase().replace(/\.$/, '');
    if (!host) return false;
    if (host === 'lemma.id' || host.endsWith('.lemma.id')) return true;
    if (host === 'localhost' || host === '127.0.0.1') return true;
    return false;
}

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
const WALLET_DB_VERSION = 7;  // v7: ishuman_cache encrypted at rest; v6 added ishuman_cache store
const DEFAULT_SESSION_HOURS = 10;
const MAX_SESSION_HOURS = 10;
const DEFAULT_PROFILE_ID = 'default';
const ISHUMAN_LOCK_STORAGE_KEY = 'lemma_ishuman_lock:v1';
const ISHUMAN_LOCK_LEGACY_SESSION_KEY = 'lemma_ishuman_lock:v1'; // sessionStorage migration

// Get user's session duration preference (stored in localStorage by wallet settings page)
function getSessionDurationMs() {
    try {
        const hours = parseInt(localStorage.getItem('lemma_session_hours')) || DEFAULT_SESSION_HOURS;
        // Clamp between 1 and 24 hours for safety
        const clampedHours = Math.max(1, Math.min(MAX_SESSION_HOURS, hours));
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
    static VERSION = '2.74.0';  // v2.74: device-bound signing keys + person-root link transfer

    static DEVICE_IDB_NAMES = ['LemmaWallet', 'LemmaWalletWrap'];

    static LEMMA_STORAGE_PREFIXES = ['lemma_', 'ishuman_', '__lemma_'];

    static LEMMA_STORAGE_EXACT_KEYS = [
        'lemma_ishuman_lock:v1',
        'lemma_session_hours',
        'lemma_redirect_state',
        'lemma_log_level',
        'lemma_wallet_backups',
        'lemma_allow_sensitive_local_backup',
        'lemma_had_global_session',
        'lemma_debug_auth',
        'ishuman_idv_popup_session_id',
        'ishuman_master_provisioned_v1',
        'ishuman_bloom',
        'ishuman_trust_list',
        'lemma_register_pending_v1',
        'lemma_register_result_v1',
        'lemma_register_error_v1',
    ];

    static async deleteIndexedDbDatabase(dbName) {
        return new Promise((resolve, reject) => {
            const req = indexedDB.deleteDatabase(dbName);
            req.onsuccess = () => resolve(true);
            req.onerror = () => reject(req.error || new Error(`delete_failed:${dbName}`));
            req.onblocked = () => reject(new Error(
                'Wallet removal is blocked by another lemma.id tab. Close the other tab and try again.',
            ));
        });
    }

    static _resetWalletInstance(instance) {
        if (!instance) return;
        try { instance.stopSessionHeartbeat?.(); } catch (_) {}
        try { instance.lock?.(); } catch (_) {}
        try { instance.db?.close?.(); } catch (_) {}
        instance.db = null;
        instance._initialized = false;
        instance._verifiedSignatures?.clear?.();
        instance.session = {
            isUnlocked: false,
            unlockedAt: null,
            expiresAt: null,
            walletSecret: null,
        };
        instance._walletSigningKey = null;
        instance._signingKeyRegistered = false;
        instance._atRestKey = null;
        instance._atRestKeyReady = false;
        instance._atRestKeyRaw = null;
    }

    static async purgeAllDeviceData(options = {}) {
        const instances = Array.isArray(options.instances) ? options.instances : [];
        for (const instance of instances) {
            LemmaWallet._resetWalletInstance(instance);
        }

        const dbNames = new Set(LemmaWallet.DEVICE_IDB_NAMES);
        if (typeof indexedDB.databases === 'function') {
            try {
                const discovered = await indexedDB.databases();
                for (const db of discovered) {
                    const name = String(db?.name || '');
                    if (/^Lemma/i.test(name)) {
                        dbNames.add(name);
                    }
                }
            } catch (_) {}
        }

        for (const dbName of dbNames) {
            await LemmaWallet.deleteIndexedDbDatabase(dbName);
        }

        try {
            const keysToRemove = new Set(LemmaWallet.LEMMA_STORAGE_EXACT_KEYS);
            for (let i = 0; i < localStorage.length; i += 1) {
                const key = localStorage.key(i);
                if (!key) continue;
                if (LemmaWallet.LEMMA_STORAGE_PREFIXES.some((prefix) => key.startsWith(prefix))) {
                    keysToRemove.add(key);
                }
            }
            keysToRemove.forEach((key) => localStorage.removeItem(key));
        } catch (_) {}

        try {
            const sessionKeys = [];
            for (let i = 0; i < sessionStorage.length; i += 1) {
                const key = sessionStorage.key(i);
                if (!key) continue;
                if (LemmaWallet.LEMMA_STORAGE_PREFIXES.some((prefix) => key.startsWith(prefix))) {
                    sessionKeys.push(key);
                }
            }
            sessionKeys.forEach((key) => sessionStorage.removeItem(key));
        } catch (_) {}

        if (options.clearServiceWorker !== false && typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
            try {
                const registrations = await navigator.serviceWorker.getRegistrations();
                await Promise.all(registrations.map((registration) => registration.unregister()));
            } catch (_) {}
        }

        if (options.clearCaches !== false && typeof window !== 'undefined' && window.caches) {
            try {
                const cacheNames = await window.caches.keys();
                await Promise.all(cacheNames.map((name) => window.caches.delete(name)));
            } catch (_) {}
        }

        return { success: true, clearedDatabases: [...dbNames] };
    }
    
    constructor(options = {}) {
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
            ttlMs: 60000,  // Cache valid for 60 seconds
            pendingPromise: null  // Deduplicate concurrent requests
        };
        // Guardrail: avoid repeated network checks from rapid focus/visibility churn.
        this._lastGlobalSessionNetworkCheck = 0;
        this._minGlobalSessionCheckMs = 60000; // At most one network check per minute unless forced.
        
        // Performance: Debounce heartbeat checks
        this._lastHeartbeatCheck = 0;
        this._heartbeatDebounceMs = 2000;  // Min 2s between checks
        
        // Logging level controls SDK verbosity without affecting app-wide logs.
        // Supported levels: 'debug' | 'info' | 'warn' | 'error' | 'silent'
        this._logLevel = this._resolveLogLevel(options);
        this._debug = options.debug === true || this._logLevel === 'debug';
        this._installSdkLogGate();
        this._isClearingSession = false;
        this._walletSigningKey = null;
        this._signingKeyRegistered = false;
        /** @type {CryptoKey|null} Phase 5 PRF-derived AES-GCM key (memory only) */
        this._atRestKey = null;
        this._atRestKeyReady = false;
        /** @type {string|null} Raw PRF key material (base64url) for the 24h daily-unlock bundle */
        this._atRestKeyRaw = null;
    }
    
    /** @private Log only when debug is enabled */
    _log(...args) { if (this._debug) console.log(...args); }
    _warn(...args) { if (this._debug) console.warn(...args); }

    _resolveLogLevel(options = {}) {
        if (options.logLevel) return String(options.logLevel).toLowerCase();
        if (typeof window !== 'undefined' && window.LEMMA_LOG_LEVEL) {
            return String(window.LEMMA_LOG_LEVEL).toLowerCase();
        }
        try {
            const stored = localStorage.getItem('lemma_log_level');
            if (stored) return String(stored).toLowerCase();
        } catch (e) {
            // Ignore storage access issues and use default.
        }
        // Default to warnings/errors in production usage to reduce log overhead.
        return 'warn';
    }

    _installSdkLogGate() {
        if (typeof window === 'undefined') return;
        if (window.__lemmaSdkLogGateInstalled) return;

        const levelOrder = { debug: 10, info: 20, warn: 30, error: 40, silent: 50 };
        const minLevel = this._logLevel in levelOrder ? this._logLevel : 'warn';

        const originalLog = console.log.bind(console);
        const originalWarn = console.warn.bind(console);

        const isLemmaTagged = (args) => {
            if (!args || args.length === 0) return false;
            const first = String(args[0] ?? '');
            return first.includes('[Lemma]') || first.includes('Lemma Wallet') || first.includes('lemma.id');
        };

        const allow = (level, args) => {
            if (!isLemmaTagged(args)) return true;
            return levelOrder[level] >= levelOrder[minLevel];
        };

        console.log = (...args) => {
            if (allow('info', args)) originalLog(...args);
        };

        console.warn = (...args) => {
            if (allow('warn', args)) originalWarn(...args);
        };

        // Keep console.error untouched for operational visibility.
        window.__lemmaSdkLogGateInstalled = true;
    }

    /**
     * Set callback for when session expires (e.g., wallet locked remotely)
     * @param {Function} callback - Called when session is invalidated
     */
    onSessionExpired(callback) {
        this._onSessionExpired = callback;
    }

    /**
     * Notify host app that session expired without letting host callback
     * exceptions crash SDK internals.
     * @private
     */
    _notifySessionExpired(payload) {
        if (this._onSessionExpired && typeof this._onSessionExpired === 'function') {
            try {
                this._onSessionExpired(payload);
            } catch (e) {
                console.warn('[Lemma] onSessionExpired callback error:', e.message);
            }
        }

        try {
            window.dispatchEvent(new CustomEvent('lemma:session-expired', {
                detail: payload
            }));
        } catch (e) {
            console.warn('[Lemma] Failed to dispatch lemma:session-expired event:', e.message);
        }
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
         ${linkText}
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
                        this._autoStartHeartbeat();
                        
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
                console.log(`[Lemma]  Authorized via local lemma in ${authResult.verifyTimeMs}ms`);
                
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
                this._autoStartHeartbeat();
                
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
                            this._autoStartHeartbeat();
                        
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
                                console.log(`[Lemma]  Authorized after global sync in ${retryResult.verifyTimeMs}ms`);
                                this._setupLockEventListener();
                                this._autoStartHeartbeat();
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
                console.log(`[Lemma]  Using existing local session (source: ${this.session.source || 'unknown'})`);
                this._autoStartHeartbeat();
                
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
                    console.log('[Lemma]  Global session valid - user unlocked on another device');
                    
                    this.session = {
                        isUnlocked: true,
                        unlockedAt: globalSession.session.unlocked_at || globalSession.session.unlockedAt,
                        expiresAt: (globalSession.session.expires_at || globalSession.session.expiresAt) * 1000,
                        walletId: walletIdRecord.value,
                        walletSecret: secretRecord.secret,
                        source: 'global_sync'
                    };
                    await this._put('session', { id: 'current', ...this.session });
                    this._autoStartHeartbeat();
                    
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
     * Defensive same-origin postMessage listener for SESSION_INVALIDATED events.
     * Phase 2.1: the bridge iframe was removed, but this exact-origin guard is
     * retained so any trusted lemma.id lock signal still clears the local session.
     */
    _setupLockEventListener() {
        if (this._lockEventListenerSetup) return;
        this._lockEventListenerSetup = true;
        
        window.addEventListener('message', async (event) => {
            // Only accept messages from lemma.id
            if (!isLemmaTrustedOrigin(event.origin)) return;
            
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
     * Deprecated: cross-device global session sync was removed. Unlock is now
     * local-per-device, so this always reports no cross-device session and
     * makes no network call. Callers fall back to the local unlock flow.
     * @private
     */
    async _checkGlobalSession(walletId, options = {}) {
        return { valid: false, deprecated: true };
    }
    
    /**
     * Auto-start heartbeat on third-party sites after successful authentication.
     * Customers can optionally set onSessionExpired callback to handle sign-out.
     * @private
     */
    _autoStartHeartbeat() {
        if (this._heartbeatInterval) return; // Already running
        
        console.log('[Lemma]  Auto-starting session heartbeat (visibility + 5min backup)');
        this.startSessionHeartbeat(300000); // 5 minute backup interval (primary is tab focus)
    }

    /**
     * Check if current domain is lemma.id or localhost
     * @private
     */
    _isLemmaDomain() {
        return isLemmaHostname(window.location.hostname);
    }

    /**
     * Wallet secrets must never persist in third-party site storage.
     * Keep legacy behavior on lemma.id/local dev only.
     * @private
     */
    _canPersistWalletSecret() {
        return this._isLemmaDomain();
    }

    /**
     * Remove any accidentally persisted wallet secret on third-party origins.
     * @private
     */
    async _scrubThirdPartySecrets() {
        if (this._canPersistWalletSecret()) return;
        try {
            await this._delete('secrets', 'master');
        } catch (_) {}
        try {
            const currentSession = await this._get('session', 'current');
            if (currentSession && currentSession.walletSecret) {
                delete currentSession.walletSecret;
                await this._put('session', currentSession);
            }
        } catch (_) {}
        if (this.session && this.session.walletSecret) {
            this.session.walletSecret = null;
        }
    }

    /**
     * Resolve current wallet ID from memory or IndexedDB.
     * Some tabs may have a valid unlocked session but missing in-memory walletId,
     * which would otherwise cause remote lock SSE events to be ignored.
     * @private
     */
    async _resolveCurrentWalletId() {
        if (this.session.walletId) {
            return this.session.walletId;
        }
        try {
            const walletIdRecord = await this._get('passkey', 'walletId');
            if (walletIdRecord?.value) {
                this.session.walletId = walletIdRecord.value;
                return walletIdRecord.value;
            }
        } catch (e) {
            // Best-effort lookup only; caller handles null.
        }
        return null;
    }

    /**
     * Redirect-based unlock flow for all browsers.
     * More reliable than popups on iOS Safari which blocks popups aggressively.
     * 
     * Flow:
     * 1. Saves current URL and state in localStorage
     * 2. Redirects to lemma.id/unlock (clean, focused page)
     * 3. User unlocks with passkey
     * 4. lemma.id issues site-bound lemma_credential and redirects back
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

        // Store redirect context for return processing (lemma_credential flow).
        const redirectState = {
            returnUrl,
            state,
            timestamp: Date.now(),
            origin: window.location.origin,
        };

        try {
            localStorage.setItem('lemma_redirect_state', JSON.stringify(redirectState));
        } catch (e) {
            console.warn('[Lemma] Could not save redirect state to localStorage');
        }

        console.log('[Lemma] Redirecting to lemma.id for wallet unlock...');
        console.log('[Lemma]  Lemma credential flow (wallet_secret stays on lemma.id)');

        const params = new URLSearchParams({
            return_url: returnUrl,
            redirect_flow: '1',
        });

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

        const urlParams = new URLSearchParams(window.location.search);
        const legacyParams = ['lemma_unlocked', 'lemma_wallet_id', 'lemma_data', 'lemma_token'];
        const hadLegacyParams = legacyParams.some((name) => urlParams.has(name));

        if (hadLegacyParams) {
            legacyParams.forEach((name) => urlParams.delete(name));
            const cleanUrl = urlParams.toString()
                ? `${window.location.pathname}?${urlParams.toString()}`
                : window.location.pathname;
            window.history.replaceState({}, '', cleanUrl);
            console.warn('[Lemma] Legacy redirect unlock params ignored; use lemma_credential flow');
        }

        try {
            localStorage.removeItem('lemma_redirect_state');
        } catch (e) {}

        return null;
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
            this._notifySessionExpired({ reason: 'expired' });
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
     * Start session heartbeat (checks if the local wallet session is still valid)
     *
     * ARCHITECTURE:
     * - LOCAL ONLY: Enforces the user-chosen session expiry on this device.
     *   Checked on an interval and on tab visibility/focus changes.
     *
     * Cross-device lock/unlock detection (SSE + global-session polling) was
     * removed: unlock is local-per-device, and revocation propagates via the
     * pull-based signed Bloom snapshot (/api/revocation/bloom-filter).
     *
     * @param {number} intervalMs - Local expiry-check interval in ms (default: 300000 = 5 minutes)
     */
    startSessionHeartbeat(intervalMs = 300000) {
        // Skip only on localhost dev hosts where SSE endpoint may not exist.
        const devHost = window.location.hostname.toLowerCase();
        if (devHost === 'localhost' || devHost === '127.0.0.1') {
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

        // Heartbeat check function: enforces local session expiry only.
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

            // Local expiry (always enforced, no network)
            if (this.session.expiresAt && now > this.session.expiresAt) {
                console.log('[Lemma] Session expired');
                await this._clearSessionGracefully('expired', 'Your session has expired. Please sign in again.');
                return;
            }
        };

        // Local expiry-check interval
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
     * Deprecated: the real-time SSE event stream was removed. Wallet unlock is
     * local-per-device and revocation propagates via the pull-based signed
     * Bloom snapshot (synced by syncRevocations / the periodic sync). Retained
     * as a no-op so any external callers keep working.
     * @private
     */
    _connectSessionSSE() {
        return;
    }

    /**
     * Deprecated no-op: SSE reconnect was removed (no SSE stream).
     * @private
     */
    _reconnectSessionSSE() {
        return;
    }
    
    /**
     * Clear session gracefully with notification
     * @private
     */
    async _clearSessionGracefully(reason, message) {
        if (this._isClearingSession) {
            this._warn('[Lemma] Session clear already in progress - skipping duplicate clear');
            return;
        }

        this._isClearingSession = true;
        try {
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
                    
            // Trigger callback and event safely.
            this._notifySessionExpired({ reason, message });
        } finally {
            this._isClearingSession = false;
        }
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
            request.onblocked = () => {
                reject(new Error('Wallet database update is blocked. Close other lemma.id tabs and retry.'));
            };
            
            request.onsuccess = async () => {
                this.db = request.result;
                this.db.onversionchange = () => {
                    console.warn('[Lemma] Wallet database version changed; closing old connection');
                    this.db.close();
                    this._initialized = false;
                };
                this._initialized = true;
                await this._checkSessionState();
                if (this._isLemmaDomain()) {
                    await this._restoreIsHumanLockBundleIfValid();
                }
                this._cleanupStaleRedirectState();
                await this._processCredentialTransferToken();
                await this._scrubThirdPartySecrets();
                
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

                // v5: Wallet storage metadata (PRF/migration flags; no secrets)
                if (!db.objectStoreNames.contains('wallet_meta')) {
                    db.createObjectStore('wallet_meta', { keyPath: 'id' });
                }

                // v6/v7: isHuman presentation cache (encrypted at rest via envelope; lock-period bridge reads)
                if (!db.objectStoreNames.contains('ishuman_cache')) {
                    db.createObjectStore('ishuman_cache', { keyPath: 'id' });
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
                console.log(' Auto-syncing revocation list...');
                await this.syncRevocations();
            } else {
                console.log(` Revocation list up to date (${revInfo.count} entries, ${Math.round(revInfo.age / 60000)}min old)`);
            }
        } catch (e) {
            console.warn('Auto-sync revocations failed:', e);
        }
    }

    /**
     * Process one-time transfer tokens used to import an issued credential
     * into the current site's IndexedDB context.
     */
    async _processCredentialTransferToken() {
        try {
            const url = new URL(window.location.href);
            const transferToken = url.searchParams.get('lemma_transfer_token');
            if (!transferToken) {
                return;
            }

            this._log('[Lemma] Found credential transfer token in URL; attempting redeem');
            const redeemResp = await fetch('https://lemma.id/api/developer/credential-transfer/redeem', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    token: transferToken,
                    site_domain: window.location.hostname
                })
            });

            const redeemData = await redeemResp.json();
            if (!redeemResp.ok || !redeemData.success || !redeemData.credential) {
                const errorCode = redeemData?.error || '';
                this._warn('[Lemma] Credential transfer redeem failed:', errorCode || redeemData?.message || redeemResp.status);
                // One-time tokens may be redeemed by another tab/attempt first.
                // Treat as non-fatal and clear URL token to avoid repeated 400 loops.
                if (errorCode === 'invalid_or_expired_token') {
                    url.searchParams.delete('lemma_transfer_token');
                    window.history.replaceState({}, document.title, url.toString());
                }
                return;
            }

            await this.storeCredential(redeemData.credential);
            this._log('[Lemma] Credential transfer redeemed and stored for site:', redeemData.site_domain || window.location.hostname);

            // Remove one-time token from URL after successful import.
            url.searchParams.delete('lemma_transfer_token');
            window.history.replaceState({}, document.title, url.toString());
        } catch (e) {
            this._warn('[Lemma] Credential transfer processing failed (non-fatal):', e.message);
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
            const hashParams = new URLSearchParams((window.location.hash || '').replace(/^#/, ''));
            const lemmaCredParam = urlParams.get('lemma_credential') || hashParams.get('lemma_credential');
            const hasRedirectUnlockFlag = urlParams.get('lemma_unlocked') === '1' || hashParams.get('lemma_unlocked') === '1';
            if (hasRedirectUnlockFlag || !!lemmaCredParam) {
                console.log('[Lemma] Detected redirect return - auto-processing...');
                
                // AUTO-PROCESS redirect return to establish session immediately
                // This ensures the session is set up without requiring explicit call
                try {
                    // Check for new lemma-based redirect (privacy-preserving)
                    if (lemmaCredParam) {
                        console.log('[Lemma] Processing lemma-based redirect (no wallet_secret transferred)');
                        try {
                            const normalizeBase64 = (value) => {
                                const text = String(value || '').trim().replace(/-/g, '+').replace(/_/g, '/');
                                const pad = text.length % 4;
                                return pad ? text + '='.repeat(4 - pad) : text;
                            };
                            const decoded = atob(normalizeBase64(lemmaCredParam));
                            const credData = JSON.parse(decoded);
                            const ppid = credData.ppid || credData.lemma?.subject || credData.lemma?.claims?.ppid || null;
                            
                            if (credData.lemma && ppid) {
                                // Store the lemma in wallet
                                await this.storeCredential(credData.lemma);
                                
                                // Set session as unlocked
                                this.session = {
                                    isUnlocked: true,
                                    unlockedAt: Date.now(),
                                    expiresAt: Date.now() + getSessionDurationMs(),
                                    walletId: credData.lemma.walletId || ppid,
                                    source: 'redirect_lemma'
                                };
                                await this._put('session', { id: 'current', ...this.session });
                                
                                console.log('[Lemma]  Lemma stored + session created. PPID:', String(ppid).substring(0, 20) + '...');
                                console.log('[Lemma]  wallet_secret was NOT transferred (privacy preserved)');
                                try {
                                    const cleanupUrl = new URL(window.location.href);
                                    cleanupUrl.searchParams.delete('lemma_credential');
                                    cleanupUrl.searchParams.delete('lemma_unlocked');
                                    const cleanupHash = new URLSearchParams((cleanupUrl.hash || '').replace(/^#/, ''));
                                    cleanupHash.delete('lemma_credential');
                                    cleanupHash.delete('lemma_unlocked');
                                    cleanupHash.delete('lemma_import');
                                    cleanupUrl.hash = cleanupHash.toString() ? `#${cleanupHash.toString()}` : '';
                                    window.history.replaceState({}, document.title, cleanupUrl.toString());
                                } catch (_) {}
                                return; // Session is ready
                            }
                        } catch (parseErr) {
                            console.warn('[Lemma] Could not parse lemma_credential:', parseErr.message);
                        }
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
                console.log('[Lemma]  Session restored from IndexedDB - isUnlocked:', this.session.isUnlocked);
                
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
            if (this._isEncryptedStorageLockedError(e)) {
                console.log('[Lemma] _checkSessionState: encrypted session is locked until passkey unlock');
                return;
            }
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
    async registerPasskey(options = {}) {
        await this.init();

        if (options.isHumanIssuance) {
            await this.reconcileSessionWalletIdForIssuance();
        }

        const existingPasskeyRecord = await this._get('passkey', 'primary');
        const mustCreatePasskeyForIssuance = options.isHumanIssuance
            && !existingPasskeyRecord?.credentialId;

        // SMART CHECK (any host): if init() already restored a valid 24h
        // session, don't prompt for passkey again — the user is already
        // authenticated for the rest of the day. Pass { force: true } to
        // require an explicit re-authentication.
        // Site proof issuance always needs passkey when none exists yet (decrypt + bind).
        if (!options.force && !mustCreatePasskeyForIssuance && this.isUnlocked && this.isUnlocked()) {
            const needsAtRestKey = await this._encryptedStorageNeedsAtRestKey();
            if (!needsAtRestKey || this._atRestKey) {
                console.log('[Lemma] registerPasskey(): reusing valid restored session');
                await this._finalizeIsHumanIssuance(options);
                return {
                    success: true,
                    method: 'restored_session',
                    cached: true,
                    walletId: this.session.walletId,
                    walletSecret: this.session.walletSecret,
                    expiresAt: this.session.expiresAt
                };
            }
        }

        if (this._isLemmaDomain() && !options.force && this.isIsHumanLockValid()) {
            await this._restoreIsHumanLockBundleIfValid();
            if (this.isUnlocked && this.isUnlocked()) {
                return {
                    success: true,
                    method: 'daily_unlock_bundle',
                    cached: true,
                    walletId: this.session.walletId,
                    walletSecret: this.session.walletSecret,
                    expiresAt: this.session.expiresAt,
                };
            }
        }

        // ============================================================
        // THIRD-PARTY SITES: Use local lemma verification (v2.45.0)
        // ============================================================
        if (!this._isLemmaDomain()) {
            console.log('[Lemma] Third-party site: checking local authorization...');
            
            // Try local lemma verification first (no network calls)
            const authResult = await this.verifyLocalAuthorization();
                
            if (authResult.authorized) {
                console.log(`[Lemma]  Already authorized via local lemma in ${authResult.verifyTimeMs}ms`);
                    
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
            return await this.unlock(options);
        }
        
        // Reuse only a complete linked/handoff identity. A wallet_id left behind
        // without its wallet_secret is an orphan from an interrupted/legacy
        // clear; pairing a new secret with that old id causes a signing-key
        // conflict and must never be attempted.
        let walletId = await this._get('passkey', 'walletId');
        const storedIdentity = await this._resolveStoredWalletIdentity();
        if (storedIdentity?.walletId && storedIdentity?.walletSecret) {
            walletId = { id: 'walletId', value: storedIdentity.walletId };
            await this._put('passkey', walletId);
        } else {
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
        const rpId = this._getRpIdForWebAuthn();
        const mod = this._walletAtRest();
        let prfExtensions = {};
        if (mod?.isPrfSupported?.()) {
            prfExtensions = await mod.buildRegistrationPrfExtensions(walletId.value, rpId);
        }

        const credential = await navigator.credentials.create({
            publicKey: {
                challenge: challenge,
                rp: {
                    name: 'Lemma Wallet',
                    id: rpId
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
                extensions: prfExtensions,
                timeout: 60000
            }
        });

        // Extract and store public key locally (never sent to server)
        const publicKeyData = this._extractPublicKey(credential.response);
        
        const prfBound = await this._bindAtRestKeyFromCredential(credential, walletId.value);
        const passkeyRecord = {
            id: 'primary',
            credentialId: this._bufferToBase64url(credential.rawId),
            publicKey: publicKeyData.publicKey,
            algorithm: publicKeyData.algorithm,
            createdAt: Date.now(),
            prfEnabled: prfBound,
            prfSaltRpId: rpId,
            prfWalletId: walletId.value,
        };

        await this._put('passkey', passkeyRecord);
        console.log('[Lemma]  Passkey created locally');
        try {
            await this._registerDevicePasskeyIfPossible(passkeyRecord, walletId.value);
        } catch (err) {
            console.warn('[Lemma] Wallet passkey server binding skipped:', err?.message || err);
        }
        if (prfBound) {
            await this._migratePlaintextStores();
        }

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
            console.log(' Generated NEW wallet secret for PPID derivation');
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
        console.log(' Wallet created and auto-unlocked after passkey registration');

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
                    console.log('[Lemma]  Server notified - cross-device sync enabled');
                    this.session.serverSessionActive = true;
                    await this._put('session', { id: 'current', ...this.session });
                    } else {
                    console.warn('[Lemma] Could not signal to server:', signalResponse.status);
                    }
                } catch (e) {
                console.warn('[Lemma] Could not signal to server:', e.message);
            }
        }

        this._registerSigningKeyIfNeeded().catch((err) => {
            console.warn('[Lemma] Wallet signing key registration skipped:', err?.message || err);
        });

        await this._finalizeIsHumanIssuance(options);

        return {
            success: true,
            credentialId: passkeyRecord.credentialId,
            walletId: walletId.value,
            walletSecret: walletSecret.secret  // Return for immediate use
        };
    }

    // ========================================
    // WALLET ED25519 SIGNING (Phase 1)
    // ========================================

    _getLemmaKeys() {
        if (typeof window === 'undefined' || !window.LemmaKeys) {
            throw new Error('LemmaKeys helpers not loaded (include /static/js/lemma-keys.js)');
        }
        return window.LemmaKeys;
    }

    async _getOrCreateDeviceId() {
        let record = await this._get('secrets', 'device_meta').catch(() => null);
        if (record?.deviceId) return record.deviceId;
        const keys = this._getLemmaKeys();
        const idBytes = crypto.getRandomValues(new Uint8Array(16));
        const deviceId = 'dev_' + keys.base64urlEncode(idBytes);
        await this._put('secrets', {
            id: 'device_meta',
            deviceId,
            deviceName: (typeof navigator !== 'undefined' && navigator.userAgent) ? navigator.userAgent.slice(0, 120) : 'browser',
            createdAt: Date.now(),
        });
        return deviceId;
    }

    async _deriveWalletSigningKey() {
        if (this._walletSigningKey) return this._walletSigningKey;
        if (!this.isUnlocked || !this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to derive signing key');
        }
        const keys = this._getLemmaKeys();
        const stored = await this._get('secrets', 'device_signing').catch(() => null);
        if (stored?.privateKeyHandle && stored?.publicKeyB64) {
            this._walletSigningKey = await keys.wrapDeviceSigningKeypair(
                stored.privateKeyHandle,
                keys.base64urlDecode(stored.publicKeyB64),
            );
            this._deviceId = stored.deviceId || await this._getOrCreateDeviceId();
            return this._walletSigningKey;
        }

        const generated = await keys.generateDeviceSigningKeypair();
        const deviceId = await this._getOrCreateDeviceId();
        await this._put('secrets', {
            id: 'device_signing',
            deviceId,
            publicKeyB64: keys.base64urlEncode(generated.publicKey),
            privateKeyHandle: generated.privateKeyHandle,
            createdAt: Date.now(),
            extractable: false,
        });
        this._deviceId = deviceId;
        this._walletSigningKey = generated;
        return this._walletSigningKey;
    }

    async _persistPersonRootSeedsAtRest() {
        if (!this.session?.walletLocalSeed || !this.session?.personRootProxy) return;
        if (!this._atRestKey) return;
        const mod = this._walletAtRest();
        if (!mod?.encryptStoredValue) return;
        try {
            await this._put('secrets', {
                id: 'person_root_seeds',
                walletLocalSeed: await this._encryptStoredValue(this.session.walletLocalSeed, 'secrets', 'person_root_seeds:local'),
                personRootProxy: await this._encryptStoredValue(this.session.personRootProxy, 'secrets', 'person_root_seeds:proxy'),
                updatedAt: Date.now(),
            });
        } catch (err) {
            console.warn('[Lemma] Could not persist person-root seeds at rest:', err?.message || err);
        }
    }

    async ensureDeviceEnrollmentAfterSeedTransfer(result) {
        await this.init();
        if (!this.session?.walletLocalSeed || !this.session?.personRootProxy) {
            throw new Error('Seed transfer incomplete');
        }
        if (!this.session?.walletSecret) {
            const secretBytes = crypto.getRandomValues(new Uint8Array(32));
            const walletSecret = Array.from(secretBytes).map((b) => b.toString(16).padStart(2, '0')).join('');
            const walletId = result?.walletId || this.session?.walletId;
            await this.persistLinkedWallet({
                walletSecret,
                walletId,
                source: 'seed_transfer',
                linkedFrom: walletId || 'unknown',
            });
        }
        await this._persistPersonRootSeedsAtRest();
        this._walletSigningKey = null;
        this._signingKeyRegistered = false;
        await this._registerSigningKeyIfNeeded();
        if (result?.masterCredentialId) {
            try {
                await this.reissueMasterCredential();
            } catch (err) {
                console.warn('[Lemma] Master credential refresh after seed transfer skipped:', err?.message || err);
            }
        }
        return { success: true, walletId: this.session?.walletId || result?.walletId || null };
    }

    async _registerDevicePasskeyIfPossible(passkeyRecord, walletId) {
        if (!this._isLemmaDomain() || !passkeyRecord?.credentialId || !passkeyRecord?.publicKey) {
            return null;
        }
        const deviceId = this._deviceId || await this._getOrCreateDeviceId();
        const walletAssertion = await this.buildWalletAssertion(
            ['wallet_id', 'device_id', 'credential_id'],
            {
                wallet_id: walletId,
                device_id: deviceId,
                credential_id: passkeyRecord.credentialId,
            },
        );
        const res = await fetch('/api/wallet/register-device-passkey', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                wallet_id: walletId,
                device_id: deviceId,
                credential_id: passkeyRecord.credentialId,
                public_key: passkeyRecord.publicKey,
                attestation_format: passkeyRecord.attestationFormat || 'none',
                device_name: passkeyRecord.deviceName || null,
                wallet_assertion: walletAssertion,
            }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.success === false) {
            throw new Error(data.error || `register-device-passkey failed (${res.status})`);
        }
        return data;
    }

    async signLemmaPopEnvelope(popEnvelope) {
        const keys = this._getLemmaKeys();
        const keypair = await this._deriveWalletSigningKey();
        const canonical = keys.buildCanonicalPopPayload(popEnvelope);
        const signature = await keypair.sign(canonical);
        return {
            sig: keys.base64urlEncode(signature),
            public_key: keys.base64urlEncode(keypair.publicKey),
            agent_key_id: this._deviceId || await this._getOrCreateDeviceId(),
        };
    }

    async getWalletSigningPubkey() {
        const keypair = await this._deriveWalletSigningKey();
        const keys = this._getLemmaKeys();
        return keys.base64urlEncode(keypair.publicKey);
    }

    async _registerSigningKeyIfNeeded() {
        if (this._signingKeyRegistered) return { success: true, cached: true };
        if (!this.isUnlocked || !this.isUnlocked()) return { success: false, skipped: true };
        const walletId = this.session?.walletId;
        if (!walletId) return { success: false, skipped: true };

        // Dedupe concurrent callers (e.g. buildWalletAssertion fired from both
        // the wallet page and the IDV popup): share a single in-flight request
        // so we don't race two INSERTs against the wallet_signing_keys PK.
        if (this._registerSigningKeyInFlight) return this._registerSigningKeyInFlight;
        this._registerSigningKeyInFlight = this._registerSigningKeyNow(walletId)
            .catch(async (err) => {
                if (err?.code !== 'wallet_pubkey_mismatch') throw err;
                const replacementWalletId = await this._rotateIncompleteWalletId(walletId);
                if (!replacementWalletId) throw err;
                return this._registerSigningKeyNow(replacementWalletId);
            })
            .finally(() => {
                this._registerSigningKeyInFlight = null;
            });
        return this._registerSigningKeyInFlight;
    }

    async _rotateIncompleteWalletId(conflictingWalletId) {
        // Never silently rotate an established local identity. This recovery is
        // only for a newly-created/incomplete wallet with no isHuman master;
        // fresh IDV will bind the replacement wallet to the assigned person root.
        const localMaster = await this.findIsHumanMasterCredential().catch(() => null);
        const cachedMaster = await this.hasIsHumanMasterInCache().catch(() => false);
        if (localMaster || cachedMaster) return null;

        const replacementWalletId = this._generateId();
        const passkey = await this._get('passkey', 'primary').catch(() => null);
        if (passkey) {
            // PRF encryption salt was chosen when the passkey was created. Keep
            // it pinned even though the logical/server wallet_id is replaced.
            passkey.prfWalletId = passkey.prfWalletId || conflictingWalletId;
            await this._put('passkey', passkey);
        }
        await this._put('passkey', { id: 'walletId', value: replacementWalletId });
        this.session.walletId = replacementWalletId;
        await this._put('session', { id: 'current', ...this.session });
        this._signingKeyRegistered = false;

        try {
            await fetch('/api/wallet/signal-unlock', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    wallet_id: replacementWalletId,
                    unlocked_at: this.session.unlockedAt || Date.now(),
                    expires_at: Math.floor((this.session.expiresAt || Date.now()) / 1000),
                }),
            });
        } catch (_) {
            // Local recovery remains valid; global-session sync is best effort.
        }
        return replacementWalletId;
    }

    async _registerSigningKeyNow(walletId) {
        const keys = this._getLemmaKeys();
        const keypair = await this._deriveWalletSigningKey();
        const pubkeyB64 = keys.base64urlEncode(keypair.publicKey);
        const registerPayload = keys.buildRegisterPayload({ walletId, pubkeyB64 });
        const signature = await keypair.sign(registerPayload);

        const deviceId = this._deviceId || await this._getOrCreateDeviceId();
        const response = await fetch('/api/wallet/register-signing-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                wallet_id: walletId,
                device_id: deviceId,
                pubkey: pubkeyB64,
                signature: keys.base64urlEncode(signature),
            }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            const error = new Error(data.error || `register-signing-key failed (${response.status})`);
            error.code = data.code || '';
            throw error;
        }
        this._signingKeyRegistered = true;
        return data;
    }

    async requestWalletChallenge() {
        if (!this.isUnlocked || !this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to request challenge');
        }
        const walletId = this.session?.walletId;
        if (!walletId) throw new Error('wallet_id unavailable');

        const response = await fetch('/api/wallet/challenge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                wallet_id: walletId,
                device_id: this._deviceId || '',
            }),
        });
        const data = await response.json();
        if (!response.ok || !data.nonce) {
            throw new Error(data.error || `wallet challenge failed (${response.status})`);
        }
        return data;
    }

    async buildWalletAssertion(fieldNames, fieldValues = {}) {
        if (!this.isUnlocked || !this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to build assertion');
        }
        await this._registerSigningKeyIfNeeded();
        const deviceId = this._deviceId || await this._getOrCreateDeviceId();
        const challenge = await this.requestWalletChallenge();
        const walletId = this.session.walletId;
        const keys = this._getLemmaKeys();
        const fieldSet = new Set((fieldNames || []).map((name) => String(name || '').trim()).filter(Boolean));
        fieldSet.add('device_id');
        const mergedValues = { ...(fieldValues || {}), device_id: deviceId };
        const orderedFields = Array.from(fieldSet).map((name) => {
            const key = String(name || '').trim();
            const raw = mergedValues[key] ?? mergedValues[name] ?? '';
            return [key, raw == null ? '' : String(raw)];
        });
        const payload = keys.buildAssertionPayload({
            walletId,
            nonceB64: challenge.nonce,
            fields: orderedFields,
        });
        const keypair = await this._deriveWalletSigningKey();
        const signature = await keypair.sign(payload);
        return {
            nonce: challenge.nonce,
            signature: keys.base64urlEncode(signature),
            device_id: deviceId,
        };
    }

    _defaultSiteDomainForProof(explicitSite) {
        const raw = String(explicitSite || '').trim();
        if (raw) return raw;
        if (typeof window !== 'undefined') {
            const host = String(window.location.hostname || '').trim();
            if (host) return host;
        }
        if (this._isLemmaDomain && this._isLemmaDomain()) {
            return 'lemma.id';
        }
        return 'lemma.id';
    }

    _canonicalizeSiteDomainForProof(explicitSite) {
        return this._canonicalizeCredentialSiteValue(this._defaultSiteDomainForProof(explicitSite));
    }

    async deriveSiteSigningKeypair(siteDomain) {
        if (!this.isUnlocked || !this.isUnlocked()) {
            throw new Error('Wallet must be unlocked to derive site signing key');
        }
        const keys = this._getLemmaKeys();
        const canonicalSite = this._canonicalizeSiteDomainForProof(siteDomain);
        const secret = this.session?.walletSecret;
        if (!secret) {
            const secretRecord = await this._get('secrets', 'master');
            if (!secretRecord?.secret) throw new Error('wallet_secret unavailable');
            this.session.walletSecret = secretRecord.secret;
        }
        // v2 (Phase 1.1): post-IDV wallets derive site signing keys from the
        // person-root wallet_local_seed when present and the flag is on. Pre-IDV
        // and default deployments stay on wallet_secret (unchanged behavior).
        const useSeed = this._isHumanUsePersonRootSeeds() && this.session?.walletLocalSeed;
        const signingSecretHex = useSeed ? this.session.walletLocalSeed : this.session.walletSecret;
        const keypair = await keys.deriveSiteSigningKeypair(signingSecretHex, canonicalSite);
        return {
            keypair,
            canonicalSite,
            publicKeyB64: keys.base64urlEncode(keypair.publicKey),
        };
    }

    /**
     * v2 (Phase 1.1) feature flag. Default OFF -> existing wallet_secret path.
     */
    _isHumanUsePersonRootSeeds() {
        return (
            typeof window !== 'undefined'
            && (window.LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS === true
                || window.LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS === 'true')
        );
    }

    /**
     * Derive the wallet's X25519 encryption public key (base64url). Posted at
     * IDV start so the server can seal person-root seed envelopes to it.
     */
    async getEncryptionPublicKeyB64() {
        let secret = this.session?.walletSecret;
        if (!secret) {
            const secretRecord = await this._get('secrets', 'master');
            secret = secretRecord?.secret;
        }
        if (!secret) throw new Error('wallet_secret unavailable');
        const keys = this._getLemmaKeys();
        const { publicKey } = await keys.deriveEncryptionKeypair(secret);
        return keys.base64urlEncode(publicKey);
    }

    /**
     * Fetch + open the sealed person-root seed envelopes and stash the derived
     * wallet_local_seed / person_root_proxy in the session. No-op unless the
     * feature flag is on and the wallet is unlocked + verified.
     */
    async fetchAndStoreSeedEnvelopes() {
        if (!this._isHumanUsePersonRootSeeds()) return null;
        const walletId = this.session?.walletId;
        let secret = this.session?.walletSecret;
        if (!secret) {
            const secretRecord = await this._get('secrets', 'master');
            secret = secretRecord?.secret;
        }
        if (!walletId || !secret) return null;

        const walletAssertion = await this.buildWalletAssertion(
            ['wallet_id', 'device_id'],
            { wallet_id: walletId, device_id: this._deviceId || '' },
        );
        const res = await fetch('/api/ishuman/seed-envelope', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ wallet_id: walletId, wallet_assertion: walletAssertion }),
        });
        if (!res.ok) return null;
        const data = await res.json().catch(() => null);
        if (!data || !data.success) return null;

        const keys = this._getLemmaKeys();
        const { privateKey } = await keys.deriveEncryptionKeypair(secret);
        const toHex = (bytes) => Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
        const walletLocalSeed = await keys.openSealedEnvelope(
            privateKey, keys.base64urlDecode(data.wallet_seed_envelope),
        );
        const personRootProxy = await keys.openSealedEnvelope(
            privateKey, keys.base64urlDecode(data.person_root_proxy_envelope),
        );
        this.session.walletLocalSeed = toHex(walletLocalSeed);
        this.session.personRootProxy = toHex(personRootProxy);
        return { ok: true, seedVersion: data.seed_version };
    }

    // ========================================
    // Phase 4.2 — QR cross-device transfer
    // ========================================

    /**
     * NEW device: mint an ephemeral transfer target. Returns the QR payload to
     * display ({ transfer_id, new_device_enc_pubkey }) and keeps the transient
     * private key in memory for the later claim.
     */
    async beginDeviceTransfer() {
        const keys = this._getLemmaKeys();
        const { privateKey, publicKey } = await keys.generateEncryptionKeypair();
        const idBytes = crypto.getRandomValues(new Uint8Array(24));
        const transferId = 'transfer_' + keys.base64urlEncode(idBytes);
        this._pendingDeviceTransfer = { transferId, privateKey };
        return {
            transferId,
            newDeviceEncPubkeyB64: keys.base64urlEncode(publicKey),
            qrPayload: JSON.stringify({
                v: 1,
                transfer_id: transferId,
                new_device_enc_pubkey: keys.base64urlEncode(publicKey),
            }),
        };
    }

    /**
     * OLD device: scanned the new device's QR. Reseal the person-root seeds to
     * the new device's key and deposit the bundle under a wallet-signed,
     * key-bound, 60s one-time relay entry.
     */
    async depositDeviceTransfer({ transferId, newDeviceEncPubkeyB64, masterCredentialId } = {}) {
        if (!transferId || !newDeviceEncPubkeyB64) {
            throw new Error('transferId and newDeviceEncPubkeyB64 required');
        }
        await this.fetchAndStoreSeedEnvelopes();
        const seedHex = this.session?.walletLocalSeed;
        const proxyHex = this.session?.personRootProxy;
        if (!seedHex || !proxyHex) {
            throw new Error('seed material unavailable; cannot transfer');
        }
        const keys = this._getLemmaKeys();
        const recipientPub = keys.base64urlDecode(newDeviceEncPubkeyB64);
        const sealedSeed = await keys.sealEnvelope(recipientPub, keys.hexToBytes(seedHex));
        const sealedProxy = await keys.sealEnvelope(recipientPub, keys.hexToBytes(proxyHex));

        const walletId = this.session?.walletId;
        const body = {
            action: 'deposit',
            wallet_id: walletId,
            transfer_id: transferId,
            new_device_enc_pubkey: newDeviceEncPubkeyB64,
        };
        const walletAssertion = await this.buildWalletAssertion(
            ['transfer_id', 'new_device_enc_pubkey'],
            { transfer_id: transferId, new_device_enc_pubkey: newDeviceEncPubkeyB64 },
        );
        body.wallet_assertion = walletAssertion;
        body.bundle = {
            sealed_wallet_seed: keys.base64urlEncode(sealedSeed),
            sealed_person_root_proxy: keys.base64urlEncode(sealedProxy),
            master_credential_id: masterCredentialId || null,
        };
        const res = await fetch('/api/wallet/sync-device', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(`device transfer deposit failed: ${err.error || res.status}`);
        }
        return res.json();
    }

    /**
     * NEW device: claim a deposited transfer (one-time) and open the resealed
     * seeds with the transient private key minted in beginDeviceTransfer().
     */
    async claimDeviceTransfer(transferId) {
        const pending = this._pendingDeviceTransfer;
        const id = transferId || pending?.transferId;
        if (!id || !pending?.privateKey || pending.transferId !== id) {
            throw new Error('no matching pending device transfer');
        }
        const res = await fetch('/api/wallet/sync-device', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ action: 'claim', transfer_id: id }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(`device transfer claim failed: ${err.error || res.status}`);
        }
        const data = await res.json();
        const bundle = data.bundle || {};
        const keys = this._getLemmaKeys();
        const toHex = (bytes) => Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
        const seed = await keys.openSealedEnvelope(
            pending.privateKey, keys.base64urlDecode(bundle.sealed_wallet_seed),
        );
        const proxy = await keys.openSealedEnvelope(
            pending.privateKey, keys.base64urlDecode(bundle.sealed_person_root_proxy),
        );
        this.session = this.session || {};
        this.session.walletId = data.wallet_id || this.session.walletId;
        this.session.walletLocalSeed = toHex(seed);
        this.session.personRootProxy = toHex(proxy);
        this._pendingDeviceTransfer = null;
        return {
            ok: true,
            walletId: data.wallet_id,
            masterCredentialId: bundle.master_credential_id || null,
        };
    }

    // ========================================
    // Pull-based device link — receiver QR, phone camera sends
    // ========================================

    _parsePullTransferPayload(raw) {
        let data = String(raw || '').trim();
        if (!data) throw new Error('Invalid receive QR');
        if (/^https?:\/\//i.test(data)) {
            try {
                const url = new URL(data);
                if (url.hash && url.hash.length > 1) {
                    data = url.hash.substring(1);
                } else if (url.pathname.includes('/link/send')) {
                    throw new Error('Receive QR missing transfer data');
                }
            } catch (e) {
                if (e.message.includes('Receive QR')) throw e;
            }
        }
        if (data[0] !== '{') {
            let base64 = data.replace(/-/g, '+').replace(/_/g, '/');
            while (base64.length % 4) base64 += '=';
            data = atob(base64);
        }
        const parsed = JSON.parse(data);
        if (parsed.v !== 2 || parsed.mode !== 'pull' || !parsed.transfer_id || !parsed.recv_pubkey) {
            throw new Error('Invalid receive QR — scan the code shown on the device you are adding');
        }
        return parsed;
    }

    /**
     * RECEIVER: show QR on this device; phone scans with native camera app.
     */
    async beginLinkReceive() {
        const keys = this._getLemmaKeys();
        const { privateKey, publicKey } = await keys.generateEncryptionKeypair();
        const idBytes = crypto.getRandomValues(new Uint8Array(24));
        const transferId = 'linkrecv_' + keys.base64urlEncode(idBytes);
        this._pendingLinkReceive = { transferId, privateKey, startedAt: Date.now() };
        const payload = {
            v: 2,
            mode: 'pull',
            transfer_id: transferId,
            recv_pubkey: keys.base64urlEncode(publicKey),
        };
        const payloadB64 = btoa(JSON.stringify(payload))
            .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
        const origin = (typeof window !== 'undefined' && window.location?.origin)
            ? window.location.origin
            : 'https://lemma.id';
        const qrUrl = `${origin}/link/send#${payloadB64}`;
        const LINK_TTL_SEC = 300;
        return {
            transferId,
            qrUrl,
            qrPayload: JSON.stringify(payload),
            expiresIn: LINK_TTL_SEC,
            expiresAt: Date.now() + LINK_TTL_SEC * 1000,
        };
    }

    /**
     * RECEIVER: try to claim a deposited pull transfer (404 = not ready yet).
     */
    async tryClaimLinkReceive(transferId) {
        const pending = this._pendingLinkReceive;
        const id = transferId || pending?.transferId;
        if (!id || !pending?.privateKey || pending.transferId !== id) {
            throw new Error('No active receive session — show a new QR code');
        }
        const res = await fetch('/api/wallet/link-receive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ action: 'claim', transfer_id: id }),
        });
        if (res.status === 404) {
            return { ready: false };
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `link receive claim failed (${res.status})`);
        }
        const data = await res.json();
        const bundle = data.bundle || {};
        const keys = this._getLemmaKeys();
        let payload;

        if (bundle.sealed_wallet_seed && bundle.sealed_person_root_proxy) {
            const seed = await keys.openSealedEnvelope(
                pending.privateKey,
                keys.base64urlDecode(bundle.sealed_wallet_seed),
            );
            const proxy = await keys.openSealedEnvelope(
                pending.privateKey,
                keys.base64urlDecode(bundle.sealed_person_root_proxy),
            );
            const toHex = (bytes) => Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
            payload = {
                walletLocalSeed: toHex(seed),
                personRootProxy: toHex(proxy),
                walletId: data.wallet_id || bundle.wallet_id || null,
                profileId: bundle.profile_id || DEFAULT_PROFILE_ID,
                profileName: bundle.profile_name || 'Personal',
                ishumanCredentials: bundle.ishuman_credentials || [],
                unlockToken: bundle.unlock_token || null,
                expiresAt: bundle.expires_at || null,
            };
        } else {
            const sealedB64 = bundle.sealed_link_payload;
            if (!sealedB64) throw new Error('Invalid transfer bundle');
            const opened = await keys.openSealedEnvelope(
                pending.privateKey,
                keys.base64urlDecode(sealedB64),
            );
            payload = JSON.parse(new TextDecoder().decode(opened));
        }

        this._pendingLinkReceive = null;
        const result = await this._completeLinkFromPayload(payload);
        return { ...result, ready: true };
    }

    /**
     * RECEIVER: poll until phone sends or timeout.
     */
    async pollLinkReceive({ transferId, timeoutMs = 300000, intervalMs = 2000 } = {}) {
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            const result = await this.tryClaimLinkReceive(transferId);
            if (result.ready) return result;
            await new Promise((resolve) => setTimeout(resolve, intervalMs));
        }
        throw new Error('Timed out waiting for your phone. Scan the QR again with your camera app.');
    }

    /**
     * SENDER: phone opened /link/send after scanning receiver QR — deposit wallet.
     */
    async sendLinkDepositFromScan(scanInput) {
        await this.init();
        const parsed = this._parsePullTransferPayload(scanInput);

        await this._requireFreshPasskeyAuth({
            reason: 'Send your lemma.id to your other device',
        });

        if (!this.isUnlocked()) {
            await this.unlock({ force: true, isHumanIssuance: false });
        }

        const profile = await this.getActiveProfile();
        if (!profile?.secret && !this.session?.walletLocalSeed) {
            throw new Error('No wallet found on this device');
        }

        const walletIdRec = await this._get('passkey', 'walletId');
        const walletId = walletIdRec?.value || this.session?.walletId || null;

        await this.fetchAndStoreSeedEnvelopes();
        const seedHex = this.session?.walletLocalSeed;
        const proxyHex = this.session?.personRootProxy;
        if (!seedHex || !proxyHex) {
            throw new Error('Person-root seeds unavailable; complete IDV or use seed transfer');
        }

        let unlockToken = null;
        if (this._isLemmaDomain()) {
            try {
                const tokenRes = await fetch('/api/wallet/link-unlock-token', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                });
                if (tokenRes.ok) {
                    const tokenData = await tokenRes.json();
                    unlockToken = tokenData.unlock_token || null;
                }
            } catch (e) {
                console.warn('[Lemma] link-unlock-token unavailable for pull send:', e.message);
            }
        }

        let ishumanCredentials = [];
        try {
            await this.syncIsHumanCacheFromWallet();
            ishumanCredentials = await this.exportIsHumanCredentialsForBridge();
        } catch (e) {
            console.warn('[Lemma] Could not export isHuman credentials for pull send:', e.message);
        }

        const LINK_TTL_MS = 300000;
        const keys = this._getLemmaKeys();
        const recipientPub = keys.base64urlDecode(parsed.recv_pubkey);
        const sealedSeed = await keys.sealEnvelope(recipientPub, keys.hexToBytes(seedHex));
        const sealedProxy = await keys.sealEnvelope(recipientPub, keys.hexToBytes(proxyHex));

        const body = {
            action: 'deposit',
            wallet_id: walletId,
            transfer_id: parsed.transfer_id,
            recv_pubkey: parsed.recv_pubkey,
            bundle: {
                sealed_wallet_seed: keys.base64urlEncode(sealedSeed),
                sealed_person_root_proxy: keys.base64urlEncode(sealedProxy),
                wallet_id: walletId,
                profile_id: profile?.id || DEFAULT_PROFILE_ID,
                profile_name: profile?.name || 'Personal',
                ishuman_credentials: ishumanCredentials,
                unlock_token: unlockToken,
                expires_at: Date.now() + LINK_TTL_MS,
            },
        };
        body.wallet_assertion = await this.buildWalletAssertion(
            ['transfer_id', 'recv_pubkey'],
            { transfer_id: parsed.transfer_id, recv_pubkey: parsed.recv_pubkey },
        );

        const res = await fetch('/api/wallet/link-receive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `link send failed (${res.status})`);
        }
        return { success: true, transferId: parsed.transfer_id };
    }

    // ========================================
    // isHuman LOCK-PERIOD (issuance scope, lemma.id tab)
    // ========================================

    _isIsHumanCredentialRecord(credential) {
        if (!credential || typeof credential !== 'object') return false;
        const cl = credential.claims || credential.credentialSubject || {};
        if (cl.isHuman === true || String(cl.isHuman).toLowerCase() === 'true') return true;
        const id = String(credential.id || '');
        return id.startsWith('ishuman_master_') || id.startsWith('ishuman_site_');
    }

    _canonicalizeCredentialSiteValue(value) {
        if (value == null || value === '') return '';
        const raw = String(value).trim();
        if (raw.toLowerCase().startsWith('site_')) return '';
        try {
            return this._getLemmaKeys().canonicalizeSiteDomain(raw);
        } catch {
            return raw.toLowerCase().replace(/^www\./, '').split(':')[0];
        }
    }

    _isLemmaPlatformSiteBinding(site) {
        const normalized = String(site || '').trim().toLowerCase().replace(/^www\./, '').split(':')[0];
        return !normalized || normalized === 'lemma.id' || normalized === 'lemma_platform';
    }

    _isIsHumanMasterRecord(credential) {
        if (String(credential?.id || '').startsWith('ishuman_master_')) {
            return true;
        }
        if (!this._isIsHumanCredentialRecord(credential)) return false;
        const cl = credential.claims || credential.credentialSubject || {};
        const sites = [
            cl.siteDomain,
            cl.site_domain,
            cl.siteId,
            cl.site_id,
            cl.site,
        ]
            .map((value) => this._canonicalizeCredentialSiteValue(value))
            .filter(Boolean);
        if (!sites.length) return true;
        return sites.some((site) => this._isLemmaPlatformSiteBinding(site));
    }

    /**
     * v2 (Phase 2.2): when the bridge iframe is disabled, the persistent
     * "one passkey per day" lock bundle is also disabled. Each popup
     * invocation does its own passkey check instead, removing the
     * localStorage bundle that caused envelope_invalid / stale-state bugs.
     */
    _isHumanLockDisabled() {
        // The 24h unlock bundle is a SAME-ORIGIN localStorage feature on
        // lemma.id and is independent of the cross-origin bridge iframe. It must
        // NOT be tied to LEMMA_DISABLE_BRIDGE_IFRAME (popup-only mode): doing so
        // disabled the bundle on the IDV popup + demo page, forcing a fresh
        // passkey on every action (one before IDV, one after). Honor only a
        // dedicated opt-out so "one passkey per 24h" survives popup-only mode.
        return (
            typeof window !== 'undefined'
            && (window.LEMMA_DISABLE_DAILY_UNLOCK === true
                || window.LEMMA_DISABLE_DAILY_UNLOCK === 'true')
        );
    }

    _readIsHumanLockBundleRaw() {
        try {
            if (typeof localStorage !== 'undefined') {
                const raw = localStorage.getItem(ISHUMAN_LOCK_STORAGE_KEY);
                if (raw) return JSON.parse(raw);
            }
            if (typeof sessionStorage !== 'undefined') {
                const legacy = sessionStorage.getItem(ISHUMAN_LOCK_LEGACY_SESSION_KEY);
                if (legacy) {
                    const parsed = JSON.parse(legacy);
                    if (parsed && typeof localStorage !== 'undefined') {
                        localStorage.setItem(ISHUMAN_LOCK_STORAGE_KEY, legacy);
                        sessionStorage.removeItem(ISHUMAN_LOCK_LEGACY_SESSION_KEY);
                    }
                    return parsed;
                }
            }
        } catch {
            return null;
        }
        return null;
    }

    isIsHumanLockValid() {
        if (this._isHumanLockDisabled()) return false;
        const bundle = this._readIsHumanLockBundleRaw();
        if (!bundle || bundle.v !== 1) return false;
        const expiresAt = Number(bundle.expiresAt || 0);
        // Secret lives either in the encrypted envelope (bundle.sec) or, for a
        // legacy bundle, as plaintext (bundle.walletSecret). Either counts here;
        // the actual decryption happens in the async restore path.
        const hasSecret = !!bundle.sec || !!bundle.walletSecret;
        return expiresAt > Date.now() && hasSecret && !!bundle.walletId;
    }

    async _persistIsHumanLockBundle() {
        if (this._isHumanLockDisabled()) return;
        if (!this._isLemmaDomain()) return;
        if (!this.session?.isUnlocked || !this.session?.walletSecret) return;
        const passkey = await this._get('passkey', 'primary').catch(() => null);
        // Non-sensitive metadata stays in cleartext so isIsHumanLockValid() can
        // gate synchronously without touching crypto.
        const bundle = {
            v: 1,
            walletId: this.session.walletId,
            unlockedAt: this.session.unlockedAt || Date.now(),
            expiresAt: this.session.expiresAt,
            hasPasskey: !!(passkey && passkey.credentialId),
        };
        // Sensitive material: the wallet secret and the PRF-derived at-rest key.
        // These are wrapped with a non-extractable device key (see
        // wallet-at-rest-crypto.js) so they never sit in JS-readable storage.
        const sensitive = {
            walletSecret: this.session.walletSecret,
            atRestKeyB64: this._atRestKeyRaw || null,
        };
        try {
            const mod = this._walletAtRest();
            let wrapped = null;
            if (mod && typeof mod.wrapBundle === 'function') {
                wrapped = await mod.wrapBundle(sensitive);
            }
            if (wrapped) {
                bundle.sec = wrapped;
                bundle.secured = true;
            } else {
                console.warn('[Lemma] Unlock bundle not persisted (device wrap key unavailable); passkey required on next visit');
                return;
            }
            if (typeof localStorage !== 'undefined') {
                localStorage.setItem(ISHUMAN_LOCK_STORAGE_KEY, JSON.stringify(bundle));
            }
            console.log('[Lemma] Daily unlock bundle persisted (10h)' + (bundle.secured ? ' [encrypted]' : ''));
        } catch (e) {
            console.warn('[Lemma] Failed to persist daily unlock bundle:', e.message);
        }
    }

    _clearIsHumanLockBundle() {
        try {
            if (typeof localStorage !== 'undefined') {
                localStorage.removeItem(ISHUMAN_LOCK_STORAGE_KEY);
            }
            if (typeof sessionStorage !== 'undefined') {
                sessionStorage.removeItem(ISHUMAN_LOCK_LEGACY_SESSION_KEY);
            }
        } catch { /* ignore */ }
    }

    async _restoreIsHumanLockBundleIfValid() {
        if (this._isHumanLockDisabled()) return false;
        const bundle = this._readIsHumanLockBundleRaw();
        if (!bundle || bundle.v !== 1) return false;
        const expiresAt = Number(bundle.expiresAt || 0);
        if (expiresAt <= Date.now() || !bundle.walletId) {
            this._clearIsHumanLockBundle();
            return false;
        }

        // Recover the sensitive material. Prefer the encrypted envelope (sec),
        // unwrapped with the non-extractable device key; fall back to a legacy
        // plaintext bundle for one migration cycle.
        let walletSecret = bundle.walletSecret || null;
        let atRestKeyB64 = bundle.atRestKeyB64 || null;
        if (bundle.sec) {
            try {
                const mod = this._walletAtRest();
                const unwrapped = (mod && typeof mod.unwrapBundle === 'function')
                    ? await mod.unwrapBundle(bundle.sec)
                    : null;
                if (unwrapped) {
                    walletSecret = unwrapped.walletSecret || null;
                    atRestKeyB64 = unwrapped.atRestKeyB64 || null;
                }
            } catch (e) {
                console.warn('[Lemma] Could not unwrap unlock bundle:', e.message);
            }
        }
        if (!walletSecret) {
            // Envelope undecryptable (e.g. wrap key cleared/rotated) or empty:
            // require a fresh passkey unlock rather than proceeding without a
            // secret.
            this._clearIsHumanLockBundle();
            return false;
        }

        this.session = {
            isUnlocked: true,
            unlockedAt: Number(bundle.unlockedAt || Date.now()),
            expiresAt,
            walletId: bundle.walletId,
            walletSecret,
            source: 'daily_unlock_bundle',
        };
        this._isHumanLockRestored = true;
        // Re-import the PRF-derived at-rest key so encrypted credential
        // reads/writes work without a fresh passkey for the 24h window. This is
        // what makes "one passkey per day" cover the master storage and every
        // per-site proof derivation in the IDV popups.
        if (!this._atRestKey && atRestKeyB64) {
            try {
                const mod = this._walletAtRest();
                if (mod) {
                    const raw = new Uint8Array(mod.base64urlToBuffer(atRestKeyB64));
                    this._atRestKey = await mod.importStorageKey(raw);
                    this._atRestKeyReady = true;
                    this._atRestKeyRaw = atRestKeyB64;
                }
            } catch (e) {
                console.warn('[Lemma] Could not restore at-rest key from bundle:', e.message);
            }
        }
        // Opportunistically upgrade a legacy plaintext bundle to the encrypted
        // form now that the secret is in memory.
        if (!bundle.sec) {
            try { await this._persistIsHumanLockBundle(); } catch { /* ignore */ }
        }
        console.log('[Lemma] Daily unlock bundle restored');
        return true;
    }

    async _persistDailyUnlockIfLemmaDomain() {
        if (this._isLemmaDomain() && this.session?.isUnlocked && this.session?.walletSecret) {
            await this._persistIsHumanLockBundle();
        }
    }

    async _finalizeIsHumanIssuance(options = {}) {
        await this._persistDailyUnlockIfLemmaDomain();
        if (!options.isHumanIssuance) return;
        await this.syncIsHumanCacheFromWallet();
    }

    applySessionFromSync(incomingSession, walletSecret) {
        if (!incomingSession?.isUnlocked) return false;
        const secret = walletSecret || incomingSession.walletSecret || this.session?.walletSecret;
        if (!secret || !incomingSession.walletId) return false;
        this.session = {
            isUnlocked: true,
            unlockedAt: incomingSession.unlockedAt || Date.now(),
            expiresAt: incomingSession.expiresAt || (Date.now() + getSessionDurationMs()),
            walletId: incomingSession.walletId,
            walletSecret: secret,
            source: incomingSession.source || 'sdk_sync',
        };
        return true;
    }

    async _putIsHumanCacheRecord(credential) {
        if (!credential?.id) return false;
        const record = {
            ...credential,
            id: credential.id,
            cachedAt: Date.now(),
        };
        try {
            await this._put('ishuman_cache', record);
            return true;
        } catch (e) {
            if (this._isEncryptedStorageLockedError(e)) {
                console.warn('[Lemma] ishuman_cache persist skipped — storage key unavailable');
                return false;
            }
            throw e;
        }
    }

    async syncIsHumanCacheFromWallet() {
        if (!this.isUnlocked || !this.isUnlocked()) return { synced: 0 };
        let lemmas = [];
        try {
            lemmas = await this._getAll('lemmas');
        } catch (e) {
            if (!this._isEncryptedStorageLockedError(e)) throw e;
            return { synced: 0, skipped: 'encrypted_locked' };
        }
        let synced = 0;
        for (const cred of lemmas) {
            if (this._isIsHumanCredentialRecord(cred)) {
                await this._putIsHumanCacheRecord(cred);
                synced += 1;
            }
        }
        return { synced };
    }

    async getIsHumanCredentialsFromCache() {
        try {
            const rows = await this._getAll('ishuman_cache');
            return (rows || []).filter((row) => row && this._isIsHumanCredentialRecord(row));
        } catch {
            return [];
        }
    }

    async hasIsHumanMasterInCache() {
        const cached = await this.getIsHumanCredentialsFromCache();
        if (cached.some((credential) => this._isIsHumanMasterRecord(credential))) {
            return true;
        }
        try {
            const canonicalSite = this._canonicalizeSiteDomainForProof('lemma.id');
            return cached.some((credential) => {
                if (!this._isIsHumanCredentialRecord(credential)) return false;
                const cl = credential.claims || credential.credentialSubject || {};
                return this._canonicalizeCredentialSiteValue(this._getCredentialSiteBinding(cl)) === canonicalSite
                    && this._siteCredentialHasSigningKey(credential);
            });
        } catch {
            return false;
        }
    }

    async applyIsHumanCredentialsToCache(credentials) {
        if (!Array.isArray(credentials)) return { applied: 0 };
        let applied = 0;
        for (const cred of credentials) {
            if (cred && this._isIsHumanCredentialRecord(cred)) {
                await this._putIsHumanCacheRecord(cred);
                applied += 1;
            }
        }
        return { applied };
    }

    /**
     * Restore isHuman credentials transferred inside an encrypted device-link payload.
     * Stores in lemmas + ishuman_cache so the new device can prove humanity without re-IDV.
     */
    async _importLinkedIsHumanCredentials(credentials) {
        if (!Array.isArray(credentials) || !credentials.length) {
            return { applied: 0, masterRestored: false };
        }
        let applied = 0;
        let masterRestored = false;
        for (const cred of credentials) {
            if (!cred || !this._isIsHumanCredentialRecord(cred)) continue;
            try {
                await this.storeCredential(cred);
                applied += 1;
                if (this._isIsHumanMasterRecord(cred)) masterRestored = true;
            } catch (e) {
                console.warn('[Lemma] Could not import linked isHuman credential:', cred.id, e.message);
            }
        }
        if (!masterRestored && applied > 0) {
            masterRestored = await this.hasIsHumanMasterInCache();
        }
        return { applied, masterRestored };
    }

    async exportIsHumanCredentialsForBridge() {
        await this.syncIsHumanCacheFromWallet();
        return this.getIsHumanCredentialsFromCache();
    }

    _getCredentialSiteBinding(claims) {
        if (!claims || typeof claims !== 'object') return '';
        return claims.siteId || claims.site_id || claims.siteDomain || claims.site_domain || '';
    }

    _siteCredentialHasSigningKey(credential) {
        const cl = credential?.claims || credential?.credentialSubject || {};
        return !!(cl.site_signing_pubkey || cl.siteSigningPubkey);
    }

    _siteCredentialLocallyVerifiable(credential) {
        // ishuman-verifier.js verifies proof.signatureValueWeb only; legacy
        // wallet copies without it must be re-derived server-side.
        return !!(credential?.proof?.signatureValueWeb);
    }

    _shouldVerifyAsIsHumanCredential(credential) {
        if (!credential || typeof credential !== 'object') return false;
        const id = String(credential.id || '');
        if (id.startsWith('ishuman_master_') || id.startsWith('ishuman_site_')) return true;
        return this._isIsHumanCredentialRecord(credential);
    }

    _browserCanonicalMessage(credential) {
        const claims = credential.claims || credential.credentialSubject || {};
        const sorted = {};
        for (const key of Object.keys(claims).sort()) {
            const value = claims[key];
            if (value === true) sorted[key] = 'true';
            else if (value === false) sorted[key] = 'false';
            else if (Array.isArray(value) || (value && typeof value === 'object')) {
                sorted[key] = JSON.stringify(value);
            } else {
                sorted[key] = value;
            }
        }
        const payload = {
            issuer: credential.issuer,
            subject: credential.subject,
            claims: sorted,
        };
        if (credential.issuedAt !== undefined && credential.issuedAt !== null) {
            payload.issuedAt = credential.issuedAt;
        }
        if (credential.expiresAt !== undefined && credential.expiresAt !== null) {
            payload.expiresAt = credential.expiresAt;
        }
        return new TextEncoder().encode(JSON.stringify(payload));
    }

    async _verifyIsHumanCredentialBrowser(credential) {
        if (!this._initialized) await this.init();

        const claims = credential.claims || credential.credentialSubject || {};
        const ppid = credential.subject || claims.id || claims.ppid || claims.subject;
        const revocationStatus = await this.isRevoked(credential.id, ppid);
        if (revocationStatus.revoked) {
            const reason = revocationStatus.ppidRevoked ? 'User revoked (all devices)' : 'Credential revoked';
            return { valid: false, reason, revocationDetails: revocationStatus };
        }

        const expiredCheck = this._checkExpiration(credential);
        if (!expiredCheck.valid) {
            return { valid: false, reason: 'Expired' };
        }

        const sigHex = String(credential.proof?.signatureValueWeb || '').trim();
        if (!sigHex) {
            return { valid: false, reason: 'legacy_credential_format' };
        }

        let publicKey = credential.issuerInfo?.publicKey || null;
        if (!publicKey) {
            const storedIssuer = await this.getIssuer(credential.issuer);
            publicKey = storedIssuer?.publicKey || null;
        }
        if (!publicKey) {
            return { valid: false, reason: 'No public key available' };
        }

        try {
            const message = this._browserCanonicalMessage(credential);
            const digest = await crypto.subtle.digest('SHA-256', message);
            const cryptoKey = this._cryptoKeyCache.get(publicKey) || await (async () => {
                let publicKeyBuffer;
                if (typeof publicKey === 'string' && /^[0-9a-fA-F]{64}$/.test(publicKey)) {
                    publicKeyBuffer = new Uint8Array(32);
                    for (let i = 0; i < 32; i++) {
                        publicKeyBuffer[i] = parseInt(publicKey.substr(i * 2, 2), 16);
                    }
                } else if (typeof publicKey === 'string') {
                    publicKeyBuffer = this._base64urlToBuffer(publicKey);
                } else {
                    throw new Error('Unknown public key format');
                }
                const key = await crypto.subtle.importKey(
                    'raw',
                    publicKeyBuffer,
                    { name: 'Ed25519' },
                    false,
                    ['verify'],
                );
                this._cryptoKeyCache.set(publicKey, key);
                return key;
            })();

            let signatureBuffer;
            if (/^[0-9a-fA-F]{128}$/.test(sigHex)) {
                signatureBuffer = new Uint8Array(64);
                for (let i = 0; i < 64; i++) {
                    signatureBuffer[i] = parseInt(sigHex.substr(i * 2, 2), 16);
                }
            } else {
                signatureBuffer = this._base64urlToBuffer(sigHex);
            }

            const isValid = await crypto.subtle.verify(
                { name: 'Ed25519' },
                cryptoKey,
                signatureBuffer,
                digest,
            );
            if (!isValid) {
                return { valid: false, reason: 'Invalid signature' };
            }

            this._verifiedSignatures.add(credential.id);
            try {
                await this._put('session', {
                    id: `verified_${credential.id}`,
                    sig: sigHex,
                    issuer: credential.issuer,
                    at: Date.now(),
                });
            } catch (_) {}

            return {
                valid: true,
                issuer: credential.issuerInfo?.name || credential.issuer,
                verified: true,
                claims,
                revocationUnchecked: revocationStatus.unchecked,
                signatureCached: false,
                verifyPath: 'browser_signatureValueWeb',
            };
        } catch (e) {
            this._warn('isHuman browser signature verification error:', e.message);
            return { valid: false, reason: `Verification error: ${e.message}` };
        }
    }

    _credentialIssuedAtSeconds(credential) {
        if (!credential) return 0;
        const claims = credential.claims || credential.credentialSubject || {};
        const fromClaims = Number(claims.issuedAt || claims.issued_at || 0);
        if (Number.isFinite(fromClaims) && fromClaims > 0) return fromClaims;
        const fromTopLevel = Number(credential.issuanceDate || credential.issuedAt || 0);
        if (Number.isFinite(fromTopLevel) && fromTopLevel > 0) return fromTopLevel;
        const fromCachedAt = Number(credential.cachedAt || 0);
        return Number.isFinite(fromCachedAt) ? Math.floor(fromCachedAt / 1000) : 0;
    }

    _sortCredentialsNewestFirst(credentials) {
        return [...(credentials || [])].sort(
            (a, b) => this._credentialIssuedAtSeconds(b) - this._credentialIssuedAtSeconds(a),
        );
    }

    needsIsHumanCredentialRepair(credential) {
        if (!this._shouldVerifyAsIsHumanCredential(credential)) return false;
        return !this._siteCredentialLocallyVerifiable(credential);
    }

    async findIsHumanSiteCredential(targetSite) {
        const canonicalSite = this._canonicalizeSiteDomainForProof(targetSite);
        const allCreds = await this.exportIsHumanCredentialsForBridge();
        const matches = allCreds.filter((credential) => {
            const cl = credential.claims || credential.credentialSubject || {};
            if (!this._isIsHumanCredentialRecord(credential)) return false;
            return this._canonicalizeCredentialSiteValue(this._getCredentialSiteBinding(cl)) === canonicalSite
                && this._siteCredentialHasSigningKey(credential);
        });
        if (!matches.length) return null;
        return this._sortCredentialsNewestFirst(matches)[0];
    }

    async findIsHumanMasterCredential() {
        if (this.isUnlocked && this.isUnlocked()) {
            await this.syncIsHumanCacheFromWallet().catch(() => ({ synced: 0 }));
        }
        const cached = await this.getIsHumanCredentialsFromCache();
        const cachedMasters = cached.filter((credential) => this._isIsHumanMasterRecord(credential));
        if (cachedMasters.length) {
            return this._sortCredentialsNewestFirst(cachedMasters)[0];
        }
        if (!this.isUnlocked || !this.isUnlocked()) return null;
        let creds = [];
        try {
            creds = await this.getCredentials();
        } catch (err) {
            if (this._isEncryptedStorageLockedError(err)) return null;
            throw err;
        }
        const masters = creds.filter((credential) => this._isIsHumanMasterRecord(credential));
        if (masters.length) {
            return this._sortCredentialsNewestFirst(masters)[0];
        }
        try {
            const platformSiteProof = await this.findIsHumanSiteCredential('lemma.id');
            if (platformSiteProof) return platformSiteProof;
        } catch (_) {
            /* ignore lookup errors */
        }
        return null;
    }

    async deriveAndStoreSiteProof(targetSite, options = {}) {
        await this.ensureIsHumanIssuanceReady({ isHumanIssuance: true });
        await this.reconcileSessionWalletIdForIssuance();
        const canonicalSite = this._canonicalizeSiteDomainForProof(targetSite);
        const issueMode = (options.issueMode || 'site_proof').trim().toLowerCase();
        const forceServerDerive = issueMode === 'fresh_idv' || !!options.forceServerDerive;

        if (!forceServerDerive) {
            const existing = await this.findIsHumanSiteCredential(canonicalSite);
            if (existing && this._siteCredentialLocallyVerifiable(existing)) {
                return existing;
            }
        }

        // v2 (Phase 1.2): the master credential is an optional hint. If the
        // local copy is missing, the server falls back to our latest verified
        // record, so we omit master_credential_id rather than failing closed.
        const master = await this.findIsHumanMasterCredential();
        const masterId = master?.id || '';

        const siteKeys = await this.deriveSiteSigningKeypair(canonicalSite);
        const siteSigningPubkey = siteKeys.publicKeyB64;
        const walletId = this.session?.walletId || '';
        if (!walletId) {
            throw new Error('wallet_locked');
        }

        // Bind master_credential_id into the signed assertion only when present
        // so the wallet and server agree on the signed field set (see
        // api/ishuman.py derive_site_proof).
        const normalizedIssueMode = issueMode === 'fresh_idv' ? 'fresh_idv' : 'site_proof';
        const assertionFieldNames = masterId
            ? ['master_credential_id', 'target_site', 'site_signing_pubkey', 'issue_mode']
            : ['target_site', 'site_signing_pubkey', 'issue_mode'];
        const assertionFieldValues = {
            target_site: canonicalSite,
            site_signing_pubkey: siteSigningPubkey,
            issue_mode: normalizedIssueMode,
        };
        if (masterId) {
            assertionFieldValues.master_credential_id = masterId;
        }
        const walletAssertion = await this.buildWalletAssertion(
            assertionFieldNames,
            assertionFieldValues,
        );

        const deriveBody = {
            wallet_id: walletId,
            target_site: canonicalSite,
            site_signing_pubkey: siteSigningPubkey,
            wallet_assertion: walletAssertion,
            issue_mode: normalizedIssueMode,
        };
        if (masterId) {
            deriveBody.master_credential_id = masterId;
        }

        const deriveRes = await fetch('/api/ishuman/derive-site-proof', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(deriveBody),
        });
        const deriveData = await deriveRes.json();
        if (!deriveRes.ok || !deriveData.success || !deriveData.credential) {
            throw new Error(deriveData.error || deriveData.message || 'derivation_failed');
        }

        const derived = deriveData.credential;
        derived.packageType = derived.packageType || 'identity';
        await this.storeCredential(derived);
        await this._putIsHumanCacheRecord(derived);
        await this._finalizeIsHumanIssuance({ isHumanIssuance: true });
        return derived;
    }

    /**
     * v2 (Phase 1.3): re-fetch a freshly signed master credential for an
     * already-verified wallet without running a new IDV. Used by the recovery
     * flow when the local master copy was lost (cleared storage, new device).
     */
    async reissueMasterCredential() {
        await this.ensureIsHumanIssuanceReady({ isHumanIssuance: true });
        const walletId = this.session?.walletId || '';
        if (!walletId) {
            throw new Error('wallet_locked');
        }

        const walletAssertion = await this.buildWalletAssertion(
            ['wallet_id'],
            { wallet_id: walletId },
        );

        const res = await fetch('/api/ishuman/reissue-master', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                wallet_id: walletId,
                wallet_assertion: walletAssertion,
            }),
        });
        const data = await res.json();
        if (res.status === 403 && data.code === 'second_factor_required') {
            throw new Error('Reissue requires confirmation from another enrolled device when one is still active.');
        }
        if (!res.ok || !data.success || !data.credential) {
            throw new Error(data.error || data.message || 'reissue_failed');
        }

        const master = data.credential;
        master.packageType = master.packageType || 'identity';
        await this.storeCredential(master);
        await this._putIsHumanCacheRecord(master);
        await this._finalizeIsHumanIssuance({ isHumanIssuance: true });
        return master;
    }

    async signSiteSessionPresentation({
        credential,
        siteId,
        sessionNonce,
        bloomSequence,
        sessionTtlSec,
    }) {
        const SESSION_PRESENTATION_PREFIX = 'lemma:site-session-presentation:v1';
        const MIN_SESSION_TTL_SECONDS = 60;
        const MAX_SESSION_TTL_SECONDS = MAX_SESSION_HOURS * 60 * 60;
        const DEFAULT_SESSION_TTL_SECONDS = MAX_SESSION_HOURS * 60 * 60;

        const keys = this._getLemmaKeys();
        const canonicalSite = this._canonicalizeSiteDomainForProof(siteId);
        const siteKeys = await this.deriveSiteSigningKeypair(canonicalSite);
        const requestedTtl = Number(sessionTtlSec || DEFAULT_SESSION_TTL_SECONDS);
        const sessionTtl = Math.min(
            MAX_SESSION_TTL_SECONDS,
            Math.max(MIN_SESSION_TTL_SECONDS, requestedTtl || DEFAULT_SESSION_TTL_SECONDS),
        );
        const issuedAtUnix = Math.floor(Date.now() / 1000);
        const expiresAtUnix = issuedAtUnix + sessionTtl;
        const sessionId = keys.base64urlEncode(crypto.getRandomValues(new Uint8Array(16)));
        const assertion = {
            session_id: sessionId,
            site_id: canonicalSite,
            credential_id: credential?.id || '',
            subject: credential?.subject || '',
            session_nonce: sessionNonce,
            bloom_sequence: bloomSequence,
            issued_at_unix: issuedAtUnix,
            expires_at_unix: expiresAtUnix,
        };
        const payloadBytes = new TextEncoder().encode([
            SESSION_PRESENTATION_PREFIX,
            String(assertion.session_id || '').trim(),
            String(assertion.site_id || '').trim(),
            String(assertion.credential_id || '').trim(),
            String(assertion.subject || '').trim(),
            String(assertion.session_nonce || '').trim(),
            String(assertion.bloom_sequence ?? ''),
            String(assertion.issued_at_unix ?? ''),
            String(assertion.expires_at_unix ?? ''),
        ].join('\n'));
        const signature = await siteKeys.keypair.sign(payloadBytes);
        return {
            credential,
            session_assertion: assertion,
            session_signature: keys.base64urlEncode(signature),
        };
    }

    async issueSiteProofPackage({
        siteId,
        sessionNonce,
        bloomSequence,
        sessionTtlSec,
        issueMode,
    }) {
        // Popup handoffs must always re-derive from the server so the credential
        // is signed by the current federated issuer and includes signatureValueWeb.
        // Reusing a wallet-local copy caused untrusted_issuer after issuer rotation.
        const credential = await this.deriveAndStoreSiteProof(siteId, {
            issueMode: issueMode || 'site_proof',
            forceServerDerive: true,
        });
        return this.signSiteSessionPresentation({
            credential,
            siteId,
            sessionNonce,
            bloomSequence,
            sessionTtlSec,
        });
    }

    async hashActionBody(body) {
        const keys = this._getLemmaKeys();
        return keys.hashActionBody(body ?? {});
    }

    async signSiteActionPresentation({
        credential,
        siteId,
        action,
        method = 'POST',
        path = '',
        body = null,
        bodyHash = null,
        nonce,
        ttlSec = 60,
    }) {
        const ACTION_PRESENTATION_PREFIX = 'lemma:site-action-presentation:v1';
        const ACTION_STAMP_VERSION = 'action_stamp_v1';
        const MIN_ACTION_TTL_SECONDS = 15;
        const MAX_ACTION_TTL_SECONDS = 300;

        if (!credential || typeof credential !== 'object') {
            throw new Error('credential required');
        }
        if (!action) {
            throw new Error('action required');
        }
        if (!nonce) {
            throw new Error('nonce required');
        }

        const keys = this._getLemmaKeys();
        const canonicalSite = this._canonicalizeSiteDomainForProof(siteId);
        const siteKeys = await this.deriveSiteSigningKeypair(canonicalSite);
        const claims = credential.claims || credential.credentialSubject || {};
        const assurance = claims.assurance
            || (claims.isHuman === true || claims.isHuman === 'true' ? 'ishuman' : 'passkey');
        const resolvedBodyHash = bodyHash || await this.hashActionBody(body ?? {});
        const requestedTtl = Number(ttlSec || 60);
        const actionTtl = Math.min(
            MAX_ACTION_TTL_SECONDS,
            Math.max(MIN_ACTION_TTL_SECONDS, requestedTtl || 60),
        );
        const issuedAtUnix = Math.floor(Date.now() / 1000);
        const expiresAtUnix = issuedAtUnix + actionTtl;
        const assertion = {
            version: ACTION_STAMP_VERSION,
            site_id: canonicalSite,
            credential_id: credential?.id || '',
            subject: credential?.subject || '',
            assurance: String(assurance || '').toLowerCase(),
            action: String(action || '').trim(),
            method: String(method || 'POST').trim().toUpperCase(),
            path: String(path || '').trim(),
            body_hash: resolvedBodyHash,
            nonce: String(nonce || '').trim(),
            issued_at_unix: issuedAtUnix,
            expires_at_unix: expiresAtUnix,
        };
        const payloadBytes = new TextEncoder().encode([
            ACTION_PRESENTATION_PREFIX,
            String(assertion.version || '').trim(),
            String(assertion.site_id || '').trim(),
            String(assertion.credential_id || '').trim(),
            String(assertion.subject || '').trim(),
            String(assertion.assurance || '').trim(),
            String(assertion.action || '').trim(),
            String(assertion.method || '').trim(),
            String(assertion.path || '').trim(),
            String(assertion.body_hash || '').trim(),
            String(assertion.nonce || '').trim(),
            String(assertion.issued_at_unix ?? ''),
            String(assertion.expires_at_unix ?? ''),
        ].join('\n'));
        const signature = await siteKeys.keypair.sign(payloadBytes);
        return {
            action_assertion: assertion,
            action_signature: keys.base64urlEncode(signature),
            bodyHash: resolvedBodyHash,
        };
    }

    async ensureIsHumanIssuanceReady(options = {}) {
        await this.init();
        let forcePasskeyForEncryptedCache = false;
        const isHumanIssuance = options.isHumanIssuance !== false;
        const existingPasskeyEarly = await this._get('passkey', 'primary');
        const requirePasskeyForIssuance = !!(isHumanIssuance && !existingPasskeyEarly?.credentialId);

        if (this.isIsHumanLockValid()) {
            await this._restoreIsHumanLockBundleIfValid();
            if (this.isUnlocked && this.isUnlocked()) {
                if (await this.hasIsHumanMasterInCache()) {
                    return { ready: true, method: 'ishuman_lock_bundle_cache' };
                }
                const needsAtRestKey = await this._encryptedStorageNeedsAtRestKey();
                if (!requirePasskeyForIssuance && (!needsAtRestKey || this._atRestKey)) {
                    await this.syncIsHumanCacheFromWallet().catch(() => ({ synced: 0 }));
                    return { ready: true, method: 'ishuman_lock_bundle' };
                }
                forcePasskeyForEncryptedCache = true;
            }
        }
        if (this.isUnlocked && this.isUnlocked()) {
            const needsAtRestKey = await this._encryptedStorageNeedsAtRestKey();
            if (!requirePasskeyForIssuance) {
                if (!needsAtRestKey || this._atRestKey) {
                    await this.syncIsHumanCacheFromWallet().catch(() => ({ synced: 0 }));
                    return { ready: true, method: 'restored_session' };
                }
                if (await this.hasIsHumanMasterInCache()) {
                    return { ready: true, method: 'restored_session_cache' };
                }
            }
            forcePasskeyForEncryptedCache = true;
        }

        await this.reconcileSessionWalletIdForIssuance();

        const existingPasskey = await this._get('passkey', 'primary');
        const issuanceOpts = {
            ...options,
            isHumanIssuance,
            force: options.force || forcePasskeyForEncryptedCache,
        };

        if (existingPasskey && existingPasskey.credentialId) {
            await this.unlock(issuanceOpts);
            await this.reconcileSessionWalletIdForIssuance();
        } else {
            await this.registerPasskey(issuanceOpts);
            await this.reconcileSessionWalletIdForIssuance();
        }
        return { ready: this.isUnlocked && this.isUnlocked(), method: 'passkey' };
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

        if (this._isLemmaDomain() && !options.force) {
            if (this.isIsHumanLockValid()) {
                await this._restoreIsHumanLockBundleIfValid();
                if (this.isUnlocked && this.isUnlocked()) {
                    return {
                        success: true,
                        method: 'daily_unlock_bundle',
                        cached: true,
                        walletId: this.session.walletId,
                        walletSecret: this.session.walletSecret,
                        expiresAt: this.session.expiresAt,
                        source: 'daily_unlock_bundle',
                    };
                }
            }
        }

        // SMART CHECK (any host): if a valid 24h session was restored from
        // IndexedDB by init(), don't prompt for passkey again. This honors the
        // "one passkey per day" promise on lemma.id, not just on third-party
        // sites. Callers can pass { force: true } to require a fresh passkey
        // (e.g. for sensitive operations like exporting the wallet secret).
        if (!options.force && this.isUnlocked && this.isUnlocked()) {
            const needsAtRestKey = await this._encryptedStorageNeedsAtRestKey();
            if (!needsAtRestKey || this._atRestKey) {
                console.log('[Lemma] unlock(): reusing valid restored session, skipping passkey prompt');
                return {
                    success: true,
                    method: 'restored_session',
                    cached: true,
                    walletId: this.session.walletId,
                    walletSecret: this.session.walletSecret,
                    expiresAt: this.session.expiresAt,
                    source: this.session.source || 'local'
                };
            }
            console.log('[Lemma] unlock(): session valid but PRF key missing — refreshing passkey for decryption');
        }

        // SMART CHECK: On third-party sites, check bridge session first
        // If user already unlocked on lemma.id today, don't prompt for passkey
        if (!this._isLemmaDomain()) {
            console.log('[Lemma] Third-party site: checking local authorization...');
                
            // Try local lemma verification first (no network calls)
            const authResult = await this.verifyLocalAuthorization();

            if (authResult.authorized) {
                console.log(`[Lemma]  Already authorized via local lemma in ${authResult.verifyTimeMs}ms`);
                
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
                this._autoStartHeartbeat();

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
        let walletIdRecord = await this._get('passkey', 'walletId');
        const rpId = this._getRpIdForWebAuthn();
        const getOptions = await this._publicKeyOptionsWithPrf({
            challenge: challenge,
            rpId: rpId,
            allowCredentials: [{
                id: this._base64urlToBuffer(passkey.credentialId),
                type: 'public-key'
            }],
            userVerification: 'required',
            timeout: 60000
        }, passkey.prfWalletId || walletIdRecord?.value);

        const credential = await navigator.credentials.get({
            publicKey: getOptions
        });

        // If we get here, the browser has verified the user via biometrics
        // No need for additional local signature verification - trust the browser
        if (!credential) {
            throw new Error('Passkey authentication cancelled');
        }
        
        console.log(' Browser verified user via biometrics');

        // Reuse linked/handoff wallet id when present; only mint when truly new.
        if (!walletIdRecord?.value) {
            const storedIdentity = await this._resolveStoredWalletIdentity();
            if (storedIdentity?.walletId) {
                walletIdRecord = { id: 'walletId', value: storedIdentity.walletId };
                await this._put('passkey', walletIdRecord);
                console.log('[Lemma] Restored wallet ID from stored identity:', storedIdentity.walletId);
            } else {
                const newWalletId = this._generateId();
                walletIdRecord = { id: 'walletId', value: newWalletId };
                await this._put('passkey', walletIdRecord);
                console.log('[Lemma] Created wallet ID:', newWalletId);
            }
        }
        const walletId = walletIdRecord.value;

        const prfBound = await this._bindAtRestKeyFromCredential(credential, walletId);
        if (prfBound) {
            await this._migratePlaintextStores();
        } else {
            const meta = await this._getWalletMeta();
            if (meta.migrationComplete) {
                throw new Error('prf_required_for_encrypted_storage');
            }
        }

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
            console.log(' Generated wallet secret for legacy wallet');
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

        console.log(' Wallet unlocked successfully (local passkey verification)');

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
                    console.log(`[Lemma]  Server notified of unlock - cross-device sync enabled`);
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
        if (!this._isLemmaDomain()) {
            this.startSessionHeartbeat(300000); // 5 minute backup (primary is tab focus)
        }

        this._registerSigningKeyIfNeeded().catch((err) => {
            console.warn('[Lemma] Wallet signing key registration skipped:', err?.message || err);
        });

        await this._finalizeIsHumanIssuance(options);

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
        this._walletSigningKey = null;
        this._signingKeyRegistered = false;
        this._clearIsHumanLockBundle();
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
        // Reset global-session cache so future checks do not reuse stale "valid" state.
        this._globalSessionCache.result = null;
        this._globalSessionCache.timestamp = 0;
        this._globalSessionCache.pendingPromise = null;
        
        // Clear server session AND global session (for cross-device lock detection)
        const isLemma = this._isLemmaDomain();
        console.log('[Lemma] Lock: isLemmaDomain=', isLemma, 'walletId=', walletId);
        
        if (isLemma) {
            try {
                console.log('[Lemma] Lock: calling /api/wallet/clear-session...');
                const payload = walletId ? { wallet_id: walletId } : {};
                const response = await fetch('/api/wallet/clear-session', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        ...this._getSecureHeaders(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });
                if (response.ok) {
                    const data = await response.json();
                    console.log('[Lemma]  Wallet locked, server notified. global_session_cleared:', data.global_session_cleared);
                } else {
                    console.warn('[Lemma] Lock: clear-session returned', response.status);
                }
            } catch (e) {
                console.warn('[Lemma] Failed to clear global session:', e.message);
            }
        } else {
            // Third-party sites cannot directly manage lemma.id cookies reliably.
            // Phase 2.1: the bridge was removed, so make a best-effort direct call
            // to lemma.id (may be blocked by CORS) so cross-device signoff can propagate.
            try {
                const directResp = await fetch('https://lemma.id/api/wallet/clear-session', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(walletId ? { wallet_id: walletId } : {})
                });
                if (directResp.ok) {
                    console.log('[Lemma]  Direct lock call succeeded');
                } else {
                    console.warn('[Lemma] Direct lock returned', directResp.status);
                }
            } catch (directErr) {
                console.warn('[Lemma] Direct lock failed:', directErr.message);
            }
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

        // 24h rolling window — "unlocked today" means within the last
        // getSessionDurationMs() (default 24h), not the same calendar day.
        // The previous calendar-day check broke shortly after midnight even
        // when the session had hours of remaining TTL.
        const sessionMs = (typeof getSessionDurationMs === 'function')
            ? getSessionDurationMs()
            : DEFAULT_SESSION_HOURS * 60 * 60 * 1000;
        const unlockedAt = this.session.unlockedAt || 0;
        const isWithinRollingWindow = unlockedAt > 0 && (Date.now() - unlockedAt) < sessionMs;

        return {
            state: isWithinRollingWindow ? AUTH_STATE.UNLOCKED_TODAY : AUTH_STATE.UNLOCKED,
            authenticated: true,
            unlockedAt: this.session.unlockedAt,
            expiresAt: this.session.expiresAt,
            unlockedToday: isWithinRollingWindow,
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
        // Phase 2.1: the cross-origin bridge was removed. Cross-site session
        // sharing is popup-only now, so report no bridge session and let callers
        // fall back to the local session / unlock redirect.
        return { success: false, valid: false, disabled: true, error: 'bridge_disabled' };
    }

    /**
     * Extend session via bridge (tap-only, no full biometric)
     * Use when session is about to expire but user is still active.
     *
     * @returns {Promise<Object>} Extension result
     */
    async extendBridgeSession() {
        // Phase 2.1: bridge removed — session extension is popup-only now.
        return { success: false, disabled: true, error: 'bridge_disabled' };
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
        if (this._isLemmaDomain()) {
            return this._localFreshAuth(maxAgeMs);
        }
        
        // Phase 2.1: bridge removed — fresh auth on third-party sites is
        // popup-only; signal that it is unavailable from here.
        return { success: false, fresh: false, disabled: true, error: 'bridge_disabled' };
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
        if (this._isLemmaDomain()) {
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
        
        // Phase 2.1: bridge removed — freshness on third-party sites is
        // popup-only; report unavailable from here.
        return { success: false, authenticated: false, fresh: false, disabled: true, error: 'bridge_disabled' };
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
        if (this._isLemmaDomain()) {
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
        if (this._isLemmaDomain()) {
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
                console.log('[Lemma]  Authenticated via bridge session');
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
                console.log('[Lemma]  Redirecting to unlock...');
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
            console.log(' Offline - using cached revocation list');
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
            
            console.log(` Synced ${revocations.length} revocations`);
            return { success: true, count: revocations.length };
        } catch (e) {
            // Network error - check if we have cached data
            const cached = await this.getRevocationInfo();
            if (cached.synced) {
                console.log(` Network error - using cached revocations (${cached.count} entries, ${Math.round(cached.age / 60000)}min old)`);
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
        
        // Phase 2.1: bridge removed — third-party sites cannot revoke directly
        // against lemma.id; revocation is first-party / popup-only now.
        if (this._isThirdPartySite()) {
            return { success: false, disabled: true, error: 'bridge_disabled' };
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
                console.log(` Server revocation: ${credentialId}`, data);
            } else {
                console.warn(` Server revocation failed: ${response.status}`);
            }
        } catch (e) {
            console.warn(` Server revocation error: ${e.message}`);
        }
        
        // 3. Delete from local IndexedDB
        await this.removeCredential(credentialId);
        
        // 4. Sync revocation list locally
        await this.syncRevocations();
        
        console.log(` Credential revoked: ${credentialId}`);
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
        // Sync our own list. Phase 2.1: bridge removed, so there is no
        // cross-origin sync to forward; third-party sites sync locally only.
        const result = await this.syncRevocations();
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
        
        this._log(`[Lemma]  Verified in ${totalTime}ms`);
        
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
    _isRetriableDbError(error) {
        if (!error) return false;
        const name = String(error.name || '');
        const message = String(error.message || '').toLowerCase();
        return (
            name === 'InvalidStateError' ||
            name === 'AbortError' ||
            message.includes('database connection is closing') ||
            message.includes('connection is closing')
        );
    }

    async _reopenDb() {
        if (this._reopenDbPromise) {
            return this._reopenDbPromise;
        }
        this._reopenDbPromise = (async () => {
            try {
                if (this.db) {
                    this.db.close();
                }
            } catch (_) {
                // Ignore close errors; we are forcing a clean reopen path.
            }
            this.db = null;
            this._initialized = false;
            await this.init();
        })().finally(() => {
            this._reopenDbPromise = null;
        });
        return this._reopenDbPromise;
    }

    async _withDbRetry(operationName, operation) {
        await this.init();
        try {
            return await operation();
        } catch (error) {
            if (!this._isRetriableDbError(error)) {
                throw error;
            }
            console.warn(`[Lemma] IndexedDB ${operationName} hit closing connection; reopening and retrying once`);
            await this._reopenDb();
            return await operation();
        }
    }

    _walletAtRest() {
        return window.WalletAtRestCrypto || null;
    }

    _isSensitiveStore(storeName) {
        const stores = this._walletAtRest()?.SENSITIVE_STORES || ['secrets', 'profiles', 'session', 'lemmas'];
        return stores.includes(storeName);
    }

    _getRpIdForWebAuthn() {
        const host = (typeof window !== 'undefined' && window.location.hostname) || '';
        if (host === 'lemma.id' || host === 'www.lemma.id' || host.endsWith('.lemma.id')) {
            return 'lemma.id';
        }
        return host || 'lemma.id';
    }

    async _getWalletMeta() {
        try {
            return await this._getRaw('wallet_meta', 'storage') || { id: 'storage' };
        } catch (_) {
            return { id: 'storage' };
        }
    }

    async _setWalletMeta(patch) {
        const current = await this._getWalletMeta();
        await this._putRaw('wallet_meta', { ...current, ...patch, id: 'storage' });
    }

    async _publicKeyOptionsWithPrf(baseOptions, walletId) {
        const mod = this._walletAtRest();
        if (!mod?.isPrfSupported?.()) return baseOptions;
        const prfExt = await mod.buildAuthenticationPrfExtensions(walletId, this._getRpIdForWebAuthn());
        return {
            ...baseOptions,
            extensions: { ...(baseOptions.extensions || {}), ...prfExt },
        };
    }

    async _bindAtRestKeyFromCredential(credential, walletId) {
        const mod = this._walletAtRest();
        if (!mod) return false;
        const prfBytes = mod.extractPrfBytes(credential);
        if (!prfBytes) {
            console.warn('[Lemma] prf_unavailable: authenticator did not return PRF output');
            return false;
        }
        this._atRestKey = await mod.importStorageKey(prfBytes);
        this._atRestKeyReady = true;
        // Stash the raw 32-byte PRF key material so the daily-unlock bundle can
        // carry it for 24h. The bundle already persists walletSecret in plaintext
        // localStorage for the same window, so this does not weaken the at-rest
        // posture — it just lets ONE passkey/day cover every encrypted read/write
        // (master storage + per-site proof derivation) instead of re-prompting on
        // each fresh popup page load that lacks the in-memory CryptoKey.
        try {
            this._atRestKeyRaw = mod.bufferToBase64url(prfBytes.slice(0, 32));
        } catch (e) {
            this._atRestKeyRaw = null;
        }
        await this._setWalletMeta({
            prfEnabled: true,
            prfSaltRpId: this._getRpIdForWebAuthn(),
        });
        return true;
    }

    async _encryptStoredValue(storeName, value) {
        if (!this._isSensitiveStore(storeName)) return value;
        const mod = this._walletAtRest();
        if (!this._atRestKey || !mod) {
            if (storeName === 'ishuman_cache') {
                throw new Error('storage_key_unavailable');
            }
            const meta = await this._getWalletMeta();
            if (meta.migrationComplete) {
                throw new Error('storage_key_unavailable');
            }
            if (this._canPersistWalletSecret()) {
                return value;
            }
            throw new Error('storage_key_unavailable');
        }
        const recordId = value?.id || value?.did || 'record';
        return mod.encryptEnvelope(this._atRestKey, storeName, recordId, value);
    }

    async _decryptStoredValue(raw) {
        const mod = this._walletAtRest();
        if (!mod?.isEncryptedEnvelope(raw)) return raw;
        if (!this._atRestKey) {
            throw new Error('envelope_invalid');
        }
        return mod.decryptEnvelope(this._atRestKey, raw);
    }

    _isEncryptedStorageLockedError(error) {
        const message = String(error?.message || error || '');
        return message === 'envelope_invalid'
            || message === 'storage_key_unavailable'
            || message === 'prf_required_for_encrypted_storage';
    }

    async _encryptedStorageNeedsAtRestKey() {
        const mod = this._walletAtRest();
        if (!mod?.isEncryptedEnvelope) return false;
        if (this._atRestKey) return false;
        const stores = ['lemmas', 'secrets', 'session', 'profiles', 'ishuman_cache'];
        for (const storeName of stores) {
            const rows = await this._getAllRaw(storeName);
            if (rows.some((row) => mod.isEncryptedEnvelope(row))) {
                return true;
            }
        }
        const meta = await this._getWalletMeta();
        if (meta?.migrationComplete) {
            return true;
        }
        return false;
    }

    async _migratePlaintextStores() {
        const mod = this._walletAtRest();
        if (!this._atRestKey || !mod) return;
        const meta = await this._getWalletMeta();
        if (meta.migrationComplete) return;

        const master = await this._getRaw('secrets', 'master');
        if (master && !mod.isEncryptedEnvelope(master)) {
            await this._put('secrets', master);
        }

        for (const profile of await this._getAllRaw('profiles')) {
            if (profile && !mod.isEncryptedEnvelope(profile)) {
                await this._put('profiles', profile);
            }
        }

        for (const sess of await this._getAllRaw('session')) {
            if (sess && !mod.isEncryptedEnvelope(sess)) {
                await this._put('session', sess);
            }
        }

        for (const lemma of await this._getAllRaw('lemmas')) {
            if (lemma && !mod.isEncryptedEnvelope(lemma)) {
                await this._put('lemmas', lemma);
            }
        }

        for (const cached of await this._getAllRaw('ishuman_cache')) {
            if (cached && !mod.isEncryptedEnvelope(cached)) {
                await this._put('ishuman_cache', cached);
            }
        }

        await this._setWalletMeta({ migrationComplete: true, migratedAt: Date.now() });
        console.log('[Lemma] At-rest storage migration complete');
    }

    async _getRaw(storeName, key) {
        return this._withDbRetry(`_get(${storeName})`, () => new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        }));
    }

    async _get(storeName, key) {
        const raw = await this._getRaw(storeName, key);
        if (!raw || !this._isSensitiveStore(storeName)) return raw;
        return this._decryptStoredValue(raw);
    }

    async _getAllRaw(storeName) {
        return this._withDbRetry(`_getAll(${storeName})`, () => new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        }));
    }

    async _getAll(storeName) {
        const rows = await this._getAllRaw(storeName);
        if (!this._isSensitiveStore(storeName)) return rows;
        const mod = this._walletAtRest();
        if (!this._atRestKey && mod?.isEncryptedEnvelope && rows.some((row) => mod.isEncryptedEnvelope(row))) {
            return [];
        }
        const out = [];
        for (const row of rows) {
            if (!row) {
                out.push(row);
                continue;
            }
            try {
                out.push(await this._decryptStoredValue(row));
            } catch (err) {
                console.warn('[Lemma] Skipping undecryptable record in', storeName, err.message);
            }
        }
        return out;
    }

    async _putRaw(storeName, value) {
        return this._withDbRetry(`_put(${storeName})`, () => new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.put(value);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        }));
    }

    async _put(storeName, value) {
        const stored = await this._encryptStoredValue(storeName, value);
        return this._putRaw(storeName, stored);
    }

    async _delete(storeName, key) {
        return this._withDbRetry(`_delete(${storeName})`, () => new Promise((resolve, reject) => {
            const tx = this.db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.delete(key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        }));
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

    /**
     * Use server-issued isHuman credential subject when available (person-root backed).
     * @private
     */
    async _derivePPIDFromSiteCredential(siteId) {
        const normalizeSite = (value) => String(value || '').trim().toLowerCase()
            .replace(/^www\./, '')
            .replace(/:\d+$/, '');
        const target = normalizeSite(siteId);
        if (!target) return null;

        try {
            const lemmas = await this._getAll('lemmas');
            const candidates = lemmas.filter((lemma) => {
                const claims = lemma.claims || lemma.credentialSubject || {};
                const assurance = String(claims.assurance || (claims.isHuman ? 'ishuman' : '')).toLowerCase();
                if (assurance !== 'ishuman' && assurance !== 'passkey' && !claims.isHuman) return false;
                const lemmaSite = normalizeSite(
                    claims.siteId || claims.site_id || claims.siteDomain || claims.site_domain || claims.domain || ''
                );
                if (!lemmaSite) return false;
                return lemmaSite === target || target.endsWith('.' + lemmaSite);
            });
            candidates.sort((a, b) => Number(b.issuanceDate || b.issuedAt || 0) - Number(a.issuanceDate || a.issuedAt || 0));
            for (const lemma of candidates) {
                const claims = lemma.claims || lemma.credentialSubject || {};
                const personRoot = claims.ppidDerivation === 'person_root_v1'
                    || claims.assurance === 'passkey'
                    || claims.assurance === 'ishuman'
                    || claims.verificationMethod === 'stripe_identity'
                    || claims.verificationMethod === 'didit'
                    || claims.verificationMethod === 'passkey';
                if (!personRoot) continue;
                const ppid = lemma.subject || claims.ppid || claims.id || claims.subject;
                if (ppid && String(ppid).startsWith('did:lemma:ppid_')) {
                    return String(ppid);
                }
            }
        } catch (_) {
            return null;
        }
        return null;
    }

    /** @deprecated use _derivePPIDFromSiteCredential */
    async _derivePPIDFromIsHumanCredential(siteId) {
        return this._derivePPIDFromSiteCredential(siteId);
    }

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

        const ppidFromCredential = await this._derivePPIDFromSiteCredential(siteId);
        if (ppidFromCredential) {
            return ppidFromCredential;
        }

        // Third-party-safe path: if a valid lemma is already present for this site,
        // use its bound subject PPID and avoid wallet_secret usage entirely.
        if (!this._canPersistWalletSecret()) {
            try {
                const lemmas = await this._getAll('lemmas');
                const matching = lemmas.filter((lemma) => {
                    const claims = lemma.claims || lemma.credentialSubject || {};
                    const assurance = String(claims.assurance || (claims.isHuman ? 'ishuman' : '')).toLowerCase();
                    if (assurance !== 'ishuman' && assurance !== 'passkey' && !claims.isHuman) return false;
                    const lemmaSite = String(
                        claims.siteId || claims.site_id || claims.siteDomain || claims.site_domain || claims.domain || ''
                    ).toLowerCase().replace(/^www\./, '').replace(/:\d+$/, '');
                    return lemmaSite && (lemmaSite === siteId || siteId.endsWith('.' + lemmaSite));
                });
                if (matching.length > 0) {
                    matching.sort((a, b) => Number(b.issuanceDate || b.issuedAt || 0) - Number(a.issuanceDate || a.issuedAt || 0));
                    const best = matching[0];
                    const claims = best.claims || best.credentialSubject || {};
                    const ppid = best.subject || claims.ppid || claims.id || claims.subject;
                    if (ppid && String(ppid).startsWith('did:lemma:ppid_')) {
                        return String(ppid);
                    }
                }
            } catch (_) {}
        }
        
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
            const normalizeSite = (value) => {
                const raw = String(value || '').trim().toLowerCase();
                if (!raw) return '';
                try {
                    if (raw.includes('://')) {
                        return new URL(raw).hostname.toLowerCase();
                    }
                } catch (e) {
                    // Fall through to manual normalization.
                }
                return raw.split('/')[0].split(':')[0];
            };
            const isAdminLike = (claims) => {
                const permissionId = String(claims.permissionId || claims.permission_level || claims.permission_id || '').toLowerCase();
                const accountType = String(claims.accountType || claims.account_type || '').toLowerCase();
                return ['admin_access', 'super_admin', 'admin', 'superadmin', 'site_admin', 'platform_admin'].includes(permissionId)
                    || permissionId.includes('admin')
                    || accountType === 'admin';
            };
            const toEpoch = (lemma) => {
                const claims = lemma.claims || lemma.credentialSubject || {};
                const raw = lemma.issuanceDate || lemma.issuedAt || claims.issuedAt || claims.issuanceDate || 0;
                const asNum = Number(raw || 0);
                return Number.isFinite(asNum) ? asNum : 0;
            };
            const hostname = normalizeSite(siteId || window.location.hostname);
            
            // 1. Check for lemma-based auth (privacy-preserving - no wallet_secret needed)
            //    This handles both: stored lemmas from previous visits AND new redirect returns
            const allLemmas = await this._getAll('lemmas');
            const siteLemmas = allLemmas.filter(lemma => {
                const claims = lemma.claims || lemma.credentialSubject || {};
                const lemmaSiteId = normalizeSite(claims.siteId || claims.site || claims.site_id || claims.siteDomain || claims.site_domain || claims.domain || lemma.siteId);
                return lemmaSiteId && (lemmaSiteId === hostname || hostname.endsWith('.' + lemmaSiteId));
            });
            
            if (siteLemmas.length > 0 && this.session.isUnlocked) {
                const verifiedLemmas = [];
                for (const lemma of siteLemmas) {
                    try {
                        const verification = await this.verifyLemma(lemma);
                        if (verification.valid) {
                            verifiedLemmas.push(lemma);
                        }
                    } catch (e) {
                        // Ignore invalid/unverifiable lemmas.
                    }
                }

                if (verifiedLemmas.length > 0) {
                    verifiedLemmas.sort((a, b) => {
                        const aClaims = a.claims || a.credentialSubject || {};
                        const bClaims = b.claims || b.credentialSubject || {};
                        const aAdmin = isAdminLike(aClaims) ? 1 : 0;
                        const bAdmin = isAdminLike(bClaims) ? 1 : 0;
                        if (aAdmin !== bAdmin) return bAdmin - aAdmin;
                        const aPkg = String(a.packageType || aClaims.packageType || '').toLowerCase() === 'permission' ? 1 : 0;
                        const bPkg = String(b.packageType || bClaims.packageType || '').toLowerCase() === 'permission' ? 1 : 0;
                        if (aPkg !== bPkg) return bPkg - aPkg;
                        return toEpoch(b) - toEpoch(a);
                    });

                    const siteLemma = verifiedLemmas[0];
                    const claims = siteLemma.claims || siteLemma.credentialSubject || {};
                    const ppid = siteLemma.subject || claims.id || claims.ppid || claims.subject;
                    
                    console.log('[Lemma] Authenticated via best verified site lemma (no wallet_secret transferred)');
                    return {
                        authenticated: true,
                        ppid: ppid,
                        lemma: siteLemma,
                        needsPasskey: false,
                        message: 'Authenticated via verified lemma'
                    };
                }
            }
            
            // 2. Check if authenticated via autoAuthenticate
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

    async getWalletInfo(options = {}) {
        const lite = options.lite === true;
        await this.init();

        const passkey = await this._get('passkey', 'primary');
        const walletIdRecord = await this._get('passkey', 'walletId');
        const activeProfileRecord = await this._get('passkey', 'activeProfile');
        const lockedEncryptedStorage = { value: false };
        const readLockedSafe = async (fallback, reader) => {
            try {
                return await reader();
            } catch (error) {
                if (this._isEncryptedStorageLockedError(error)) {
                    lockedEncryptedStorage.value = true;
                    return fallback;
                }
                throw error;
            }
        };
        const issuers = lite ? [] : await this._getAll('issuers');
        const lemmas = lite ? [] : await readLockedSafe([], () => this._getAll('lemmas'));
        const secretRecord = await readLockedSafe(null, () => this._get('secrets', 'master'));
        
        // Also check profile for secret (device linking stores here)
        let secretSource = secretRecord?.source || 'stored';
        let profileSecret = null;
        if (activeProfileRecord?.value) {
            const profile = await readLockedSafe(null, () => this._get('profiles', activeProfileRecord.value));
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
            linkedFrom: secretRecord?.linkedFrom || null,
            encryptedStorageLocked: lockedEncryptedStorage.value
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
            const walletIdRecord = await this._get('passkey', 'walletId');
            const getOptions = await this._publicKeyOptionsWithPrf({
                challenge: challenge,
                rpId: this._getRpIdForWebAuthn(),
                allowCredentials: [{
                    id: this._base64urlToBuffer(passkey.credentialId),
                    type: 'public-key'
                }],
                userVerification: 'required',
                timeout: 60000
            }, passkey.prfWalletId || walletIdRecord?.value);

            const credential = await navigator.credentials.get({
                publicKey: getOptions
            });
            
            if (!credential) {
                throw new Error('Passkey verification cancelled');
            }
            
            console.log('[Lemma]  Fresh passkey verification successful');
            await this._bindAtRestKeyFromCredential(credential, walletIdRecord?.value);

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
     * Resolve wallet_id + secret already persisted via handoff, QR link, or session.
     * @private
     */
    async _resolveStoredWalletIdentity() {
        await this.init();
        let walletId = '';
        let walletSecret = '';
        let source = '';

        try {
            const walletIdRec = await this._get('passkey', 'walletId');
            walletId = walletIdRec?.value || '';
        } catch (err) {
            if (!this._isEncryptedStorageLockedError(err)) throw err;
        }

        const sess = this.session?.isUnlocked
            ? this.session
            : await this._get('session', 'current').catch((err) => {
                if (this._isEncryptedStorageLockedError(err)) return null;
                throw err;
            });
        if (sess?.walletId) {
            walletId = sess.walletId || walletId;
            walletSecret = walletSecret || sess.walletSecret || '';
            source = source || sess.source || '';
        }

        try {
            const secretRec = await this._get('secrets', 'master');
            if (secretRec?.secret) {
                walletSecret = walletSecret || secretRec.secret;
                source = source || secretRec.source || '';
                const linkedFrom = secretRec.linkedFrom || '';
                if (!walletId && String(linkedFrom).startsWith('wallet_')) {
                    walletId = linkedFrom;
                }
            }
        } catch (err) {
            if (!this._isEncryptedStorageLockedError(err)) throw err;
        }

        if (!walletSecret) {
            try {
                const activeProfileId = await this._get('passkey', 'activeProfile');
                const profileId = activeProfileId?.value || DEFAULT_PROFILE_ID;
                const profile = await this._get('profiles', profileId);
                if (profile?.secret) {
                    walletSecret = profile.secret;
                    const linkedFrom = profile.linkedFrom || '';
                    if (!walletId && String(linkedFrom).startsWith('wallet_')) {
                        walletId = linkedFrom;
                    }
                }
            } catch (err) {
                if (!this._isEncryptedStorageLockedError(err)) throw err;
            }
        }

        if (!walletId || !walletSecret) return null;
        return { walletId, walletSecret, source };
    }

    /**
     * Unlock session from persisted wallet material (no passkey prompt).
     * @private
     */
    async _unlockSessionFromStoredIdentity(identity, sourceTag = 'stored_identity') {
        if (!identity?.walletId || !identity?.walletSecret) return false;
        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + getSessionDurationMs(),
            walletId: identity.walletId,
            walletSecret: identity.walletSecret,
            source: sourceTag || identity.source || 'stored_identity',
        };
        await this._put('session', { id: 'current', ...this.session });
        const walletIdRec = await this._get('passkey', 'walletId').catch(() => null);
        if (!walletIdRec?.value || walletIdRec.value !== identity.walletId) {
            await this._put('passkey', { id: 'walletId', value: identity.walletId });
        }
        return true;
    }

    /**
     * Align live session wallet_id with IndexedDB linked/handoff identity before
     * isHuman server calls (derive-site-proof binds to verified wallet row).
     */
    async reconcileSessionWalletIdForIssuance() {
        const storedIdentity = await this._resolveStoredWalletIdentity();
        if (!storedIdentity?.walletId || !storedIdentity?.walletSecret) return false;
        if (this.session?.walletId === storedIdentity.walletId
            && this.session?.walletSecret === storedIdentity.walletSecret) {
            return false;
        }
        console.warn('[Lemma] Reconciling session wallet for isHuman issuance:', storedIdentity.walletId);
        await this._unlockSessionFromStoredIdentity(storedIdentity, 'reconciled_for_issuance');
        return true;
    }

    /**
     * Persist a linked wallet secret to IndexedDB without creating a passkey.
     * Used by QR device linking and silent IDV mobile handoff.
     *
     * @param {Object} options
     * @param {string} options.walletSecret
     * @param {string} [options.walletId]
     * @param {string} [options.profileId]
     * @param {string} [options.profileName]
     * @param {string} [options.source] - session source tag (e.g. 'link', 'idv_handoff')
     * @param {string} [options.linkedFrom] - originating wallet id for audit metadata
     * @returns {Promise<Object>} { walletId, profileId, profileName, walletSecret }
     */
    async persistLinkedWallet({
        walletSecret,
        walletId = null,
        profileId = DEFAULT_PROFILE_ID,
        profileName = 'Personal',
        source = 'link',
        linkedFrom = null,
    } = {}) {
        await this.init();

        if (!walletSecret) {
            throw new Error('walletSecret required');
        }

        const linkedProfile = {
            id: profileId,
            name: profileName,
            secret: walletSecret,
            createdAt: Date.now(),
            linkedFrom: linkedFrom || walletId || 'unknown',
            linkedAt: Date.now(),
            isDefault: profileId === DEFAULT_PROFILE_ID,
        };

        await this._put('profiles', linkedProfile);
        await this._put('secrets', {
            id: 'master',
            secret: walletSecret,
            createdAt: Date.now(),
            linkedFrom: linkedProfile.linkedFrom,
            linkedAt: Date.now(),
            activeProfileId: profileId,
        });
        await this._put('passkey', { id: 'activeProfile', value: profileId });

        if (walletId) {
            await this._put('passkey', {
                id: 'walletId',
                value: walletId,
            });
        }

        const now = Date.now();
        this.session = {
            isUnlocked: true,
            unlockedAt: now,
            expiresAt: now + getSessionDurationMs(),
            walletId: walletId,
            walletSecret: walletSecret,
            source: source,
        };
        await this._put('session', { id: 'current', ...this.session });

        return {
            walletId,
            profileId,
            profileName,
            walletSecret,
        };
    }

    /**
     * Prepare handoff credentials before start-verification (return URL params).
     * Call finalizeAndDepositIdvMobileHandoff() after session_id is known.
     */
    prepareIdvMobileHandoff() {
        const handoffId = 'handoff_' + this._generateId();
        const encryptionKey = crypto.getRandomValues(new Uint8Array(16));
        const mk = Array.from(encryptionKey)
            .map((b) => b.toString(16).padStart(2, '0'))
            .join('');
        this._pendingIdvHandoffKey = encryptionKey;
        return {
            handoffId,
            mk,
            expiresIn: 300,
        };
    }

    /**
     * SHA-256 fingerprint of the handoff AES key (server stores this, never mk).
     */
    async handoffMkFingerprint(mk) {
        const data = new TextEncoder().encode(String(mk || ''));
        const hash = await crypto.subtle.digest('SHA-256', data);
        return Array.from(new Uint8Array(hash))
            .map((b) => b.toString(16).padStart(2, '0'))
            .join('');
    }

    _idvHandoffAad(handoffId, sessionId, walletId) {
        return `idv_handoff_v1|${handoffId}|${sessionId}|${walletId}`;
    }

    /**
     * Encrypt wallet material for a pending IDV mobile handoff (no session_id yet).
     */
    async buildIdvMobileHandoffEncryptedBlob({ handoffId, walletSecret, walletId, sessionId } = {}) {
        const encryptionKey = this._pendingIdvHandoffKey;
        if (!encryptionKey || !handoffId || !walletSecret || !walletId || !sessionId) {
            throw new Error('pending handoff key, wallet fields, and sessionId required');
        }

        const HANDOFF_TTL_MS = 300000;
        const payload = JSON.stringify({
            handoffVersion: 'v1',
            walletSecret,
            walletId,
            sessionId,
            profileId: DEFAULT_PROFILE_ID,
            profileName: 'Personal',
            expiresAt: Date.now() + HANDOFF_TTL_MS,
        });
        const aad = this._idvHandoffAad(handoffId, sessionId, walletId);
        return this._encryptForLink(payload, encryptionKey, aad);
    }

    /**
     * Encrypt and deposit the handoff blob once session_id is available.
     */
    async finalizeAndDepositIdvMobileHandoff({
        handoffId,
        walletSecret,
        walletId,
        sessionId,
    } = {}) {
        const encryptionKey = this._pendingIdvHandoffKey;
        if (!encryptionKey || !handoffId || !walletSecret || !walletId || !sessionId) {
            throw new Error('pending handoff key and wallet/session fields required');
        }

        const mkHex = Array.from(encryptionKey)
            .map((b) => b.toString(16).padStart(2, '0'))
            .join('');
        const encryptedBlob = await this.buildIdvMobileHandoffEncryptedBlob({
            handoffId,
            walletSecret,
            walletId,
            sessionId,
        });
        this._pendingIdvHandoffKey = null;
        const handoffMkFingerprint = await this.handoffMkFingerprint(mkHex);
        await this.depositIdvMobileHandoff({
            handoffId,
            sessionId,
            encryptedBlob,
            walletId,
            handoffMkFingerprint,
        });
        return { handoffId, sessionId, encryptedBlob };
    }

    /**
     * Build a one-time encrypted mobile handoff for Didit IDV return.
     */
    async createIdvMobileHandoff({ walletSecret, walletId, sessionId } = {}) {
        await this.init();
        if (!walletSecret || !walletId || !sessionId) {
            throw new Error('walletSecret, walletId, and sessionId required');
        }

        const handoffId = 'handoff_' + this._generateId();
        const encryptionKey = crypto.getRandomValues(new Uint8Array(16));
        const encryptionKeyHex = Array.from(encryptionKey)
            .map((b) => b.toString(16).padStart(2, '0'))
            .join('');
        const HANDOFF_TTL_MS = 300000;

        const payload = JSON.stringify({
            handoffVersion: 'v1',
            walletSecret,
            walletId,
            sessionId,
            profileId: DEFAULT_PROFILE_ID,
            profileName: 'Personal',
            expiresAt: Date.now() + HANDOFF_TTL_MS,
        });
        const aad = this._idvHandoffAad(handoffId, sessionId, walletId);
        const encryptedBlob = await this._encryptForLink(payload, encryptionKey, aad);

        return {
            handoffId,
            mk: encryptionKeyHex,
            encryptedBlob,
            expiresIn: HANDOFF_TTL_MS / 1000,
        };
    }

    /**
     * Deposit an encrypted IDV mobile handoff blob (source popup, before Didit redirect).
     */
    async depositIdvMobileHandoff({ handoffId, sessionId, encryptedBlob, walletId, handoffMkFingerprint } = {}) {
        if (!handoffId || !sessionId || !encryptedBlob || !handoffMkFingerprint) {
            throw new Error('handoffId, sessionId, encryptedBlob, and handoffMkFingerprint required');
        }

        const resolvedWalletId = walletId || this.session?.walletId;
        if (!resolvedWalletId) {
            throw new Error('walletId required for handoff deposit');
        }

        const walletAssertion = await this.buildWalletAssertion(
            ['handoff_id', 'session_id', 'handoff_mk_fingerprint'],
            {
                handoff_id: handoffId,
                session_id: sessionId,
                handoff_mk_fingerprint: handoffMkFingerprint,
            },
        );

        const res = await fetch('/api/ishuman/idv-mobile-handoff/deposit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                wallet_id: resolvedWalletId,
                handoff_id: handoffId,
                session_id: sessionId,
                encrypted_blob: encryptedBlob,
                handoff_mk_fingerprint: handoffMkFingerprint,
                wallet_assertion: walletAssertion,
            }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(`mobile handoff deposit failed: ${err.error || res.status}`);
        }
        return res.json();
    }

    /**
     * Claim a mobile IDV handoff, decrypt, and persist wallet locally (no passkey).
     */
    async claimIdvMobileHandoff({ handoffId, mk, sessionId } = {}) {
        await this.init();
        if (!mk) {
            throw new Error('mk required');
        }
        if (!handoffId || !sessionId) {
            throw new Error('handoffId and sessionId required');
        }

        const res = await fetch('/api/ishuman/idv-mobile-handoff/claim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                handoff_id: handoffId,
                session_id: sessionId,
                mk,
            }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(`mobile handoff claim failed: ${err.error || res.status}`);
        }
        const data = await res.json();
        const claimedSessionId = data.session_id || sessionId;
        const aad = this._idvHandoffAad(handoffId, claimedSessionId, data.wallet_id);
        const payload = await this._decryptHandoffBlob(data.encrypted_blob, mk, aad);
        if (payload.sessionId && payload.sessionId !== claimedSessionId) {
            throw new Error('Handoff session mismatch');
        }
        if (payload.expiresAt && payload.expiresAt < Date.now()) {
            throw new Error('Handoff expired');
        }

        await this.persistLinkedWallet({
            walletSecret: payload.walletSecret,
            walletId: payload.walletId || data.wallet_id,
            profileId: payload.profileId,
            profileName: payload.profileName,
            source: 'idv_handoff',
            linkedFrom: payload.walletId || data.wallet_id,
        });

        return {
            walletId: payload.walletId || data.wallet_id,
            sessionId: payload.sessionId || claimedSessionId,
            walletSecret: payload.walletSecret,
        };
    }

    /**
     * Decrypt a handoff blob using the URL-supplied AES key (hex).
     * @private
     */
    async _decryptHandoffBlob(encryptedBlob, keyHex, additionalData = null) {
        if (!encryptedBlob || !keyHex) {
            throw new Error('encrypted blob and key required');
        }
        const keyBytes = new Uint8Array(
            String(keyHex).match(/.{2}/g).map((byte) => parseInt(byte, 16)),
        );
        const combined = Uint8Array.from(atob(encryptedBlob), (c) => c.charCodeAt(0));
        const iv = combined.slice(0, 12);
        const ciphertext = combined.slice(12);
        const key = await crypto.subtle.importKey(
            'raw',
            keyBytes,
            { name: 'AES-GCM' },
            false,
            ['decrypt'],
        );
        const decryptParams = { name: 'AES-GCM', iv: iv };
        if (additionalData) {
            decryptParams.additionalData = new TextEncoder().encode(additionalData);
        }
        const decrypted = await crypto.subtle.decrypt(
            decryptParams,
            key,
            ciphertext,
        );
        const decoder = new TextDecoder();
        return JSON.parse(decoder.decode(decrypted));
    }

    /**
     * Shared finish path for pull receive deposits (person-root enrollment).
     * @private
     */
    async _completeLinkFromPayload(payload) {
        if (payload.expiresAt && payload.expiresAt < Date.now()) {
            throw new Error('Link code expired. Please generate a new one on your other device.');
        }

        const hasPersonRoot = Boolean(payload.walletLocalSeed && payload.personRootProxy);
        if (!hasPersonRoot && !payload.walletSecret) {
            throw new Error('Invalid link bundle - missing person-root material');
        }

        const existingSecret = await this._get('secrets', 'master');
        const existingWalletId = await this._get('passkey', 'walletId');

        if (existingSecret?.secret && payload.walletSecret && existingSecret.secret === payload.walletSecret) {
            return {
                success: true,
                alreadyLinked: true,
                walletId: payload.walletId,
                message: 'This wallet is already on this device.',
            };
        }

        if (existingSecret?.secret) {
            console.log('[Lemma] Replacing existing wallet (backed up for recovery)');
            console.log('[Lemma]   Old wallet:', existingWalletId?.value?.substring(0, 16) + '...');
            console.log('[Lemma]   New wallet:', payload.walletId?.substring(0, 16) + '...');
            await this._backupWalletData();
            await this._clearWalletData();
        }

        const profileId = payload.profileId || DEFAULT_PROFILE_ID;
        const profileName = payload.profileName || 'Personal';

        let walletSecret = payload.walletSecret;
        if (!walletSecret) {
            const secretBytes = crypto.getRandomValues(new Uint8Array(32));
            walletSecret = Array.from(secretBytes).map((b) => b.toString(16).padStart(2, '0')).join('');
        }

        await this.persistLinkedWallet({
            walletSecret,
            walletId: payload.walletId,
            profileId,
            profileName,
            source: 'link',
            linkedFrom: payload.walletId || 'unknown',
        });

        if (hasPersonRoot) {
            this.session.walletLocalSeed = payload.walletLocalSeed;
            this.session.personRootProxy = payload.personRootProxy;
            await this._put('session', { id: 'current', ...this.session });
            await this._persistPersonRootSeedsAtRest();
        }

        this._walletSigningKey = null;
        this._signingKeyRegistered = false;
        await this._registerSigningKeyIfNeeded();

        let humanProofRestored = false;
        let credentialsImported = 0;
        if (Array.isArray(payload.ishumanCredentials) && payload.ishumanCredentials.length) {
            const imported = await this._importLinkedIsHumanCredentials(payload.ishumanCredentials);
            credentialsImported = imported.applied;
            humanProofRestored = imported.masterRestored;
            console.log(`[Lemma] Imported ${credentialsImported} isHuman credential(s) from link`);
        }

        let sessionError = null;
        let serverSessionSet = false;
        if (this._isLemmaDomain()) {
            if (payload.unlockToken && payload.walletId) {
                try {
                    const setRes = await fetch('/api/wallet/set-session', {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            wallet_id: payload.walletId,
                            unlock_token: payload.unlockToken,
                            profile_id: profileId,
                            profile_name: profileName,
                        }),
                    });
                    if (setRes.ok) {
                        serverSessionSet = true;
                        console.log('[Lemma] Server session established via link unlock token');
                    } else {
                        const errData = await setRes.json().catch(() => ({}));
                        sessionError = errData.error || 'set_session_failed';
                    }
                } catch (e) {
                    sessionError = e.message;
                    console.warn('[Lemma] set-session via link token failed:', e.message);
                }
            }

            if (!serverSessionSet) {
                try {
                    console.log('[Lemma] Signaling unlock to server after device link...');
                    const signalResponse = await fetch('/api/wallet/signal-unlock', {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            wallet_id: payload.walletId,
                            unlocked_at: this.session.unlockedAt,
                            expires_at: Math.floor(this.session.expiresAt / 1000),
                            profile_id: profileId,
                            profile_name: profileName
                        })
                    });
                    if (signalResponse.ok) {
                        console.log('[Lemma]  Server notified of linked device unlock');
                        serverSessionSet = true;
                        sessionError = null;
                    }
                } catch (e) {
                    console.warn('[Lemma] Could not signal unlock:', e.message);
                    if (!sessionError) sessionError = e.message;
                }
            }
        }

        if (!serverSessionSet && payload.walletId) {
            console.log('[Lemma] Trying global session fallback...');
            try {
                const globalSession = await this._checkGlobalSession(payload.walletId, { force: true });

                if (globalSession?.valid && globalSession?.session) {
                    console.log('[Lemma]  Global session found! Wallet was unlocked on another device.');
                    this.session = {
                        isUnlocked: true,
                        unlockedAt: globalSession.session.unlocked_at,
                        expiresAt: globalSession.session.expires_at * 1000,
                        walletId: payload.walletId,
                        walletSecret: payload.walletSecret,
                        source: 'global_session'
                    };
                    await this._put('session', { id: 'current', ...this.session });
                    sessionError = null;
                    console.log('[Lemma] Local session set from global session. User should create passkey for full cross-site auth.');
                } else {
                    console.log('[Lemma] No valid global session found.');
                }
            } catch (e) {
                console.warn('[Lemma] Global session check failed:', e.message);
            }
        }

        if (!serverSessionSet && !this.session?.isUnlocked) {
            console.warn('[Lemma]  Server session not set - user will need to create passkey for cross-site auth');
        }

        try {
            await this.fetchAndStoreSeedEnvelopes();
        } catch (e) {
            console.warn('[Lemma] seed envelope fetch after link skipped:', e.message);
        }
        
        console.log(`[Lemma] Device linked successfully with profile: ${profileName}`);
        
        let platformCredentialIssued = false;
        if (!humanProofRestored) {
            try {
                console.log('[Lemma] Restoring lemma.id role credential for linked device...');
                const ppid = await this.derivePPID('lemma.id');
                const issueResponse = await fetch(`${window.location?.origin || 'https://lemma.id'}/api/wallet-auth/restore-site-access`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ppid, site_id: 'lemma.id' })
                });
                if (issueResponse.ok) {
                    const issueData = await issueResponse.json();
                    if (issueData.success && issueData.permission_lemma) {
                        await this.storeCredential(issueData.permission_lemma);
                        platformCredentialIssued = true;
                        console.log('[Lemma]  Restored role credential issued and stored:', issueData.restored_role || 'unknown');
                    }
                }
            } catch (e) {
                console.warn('[Lemma] Could not auto-restore platform role credential:', e.message);
            }
        }
        
        let message;
        if (humanProofRestored && serverSessionSet) {
            message = `Wallet "${profileName}" linked with your human proof restored. Create a passkey on this device.`;
        } else if (humanProofRestored) {
            message = `Wallet "${profileName}" linked with human proof restored. Create a passkey for full access.`;
        } else if (serverSessionSet && platformCredentialIssued) {
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
            sessionSet: serverSessionSet,
            localSessionSet: this.session?.isUnlocked || false,
            sessionSource: this.session?.source || null,
            sessionError: sessionError,
            credentialIssued: platformCredentialIssued,
            humanProofRestored,
            credentialsImported,
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
            const allowSensitiveBackup = localStorage.getItem('lemma_allow_sensitive_local_backup') === 'true';
            const backup = {
                timestamp: Date.now(),
                walletId: await this._get('passkey', 'walletId'),
                profiles: await this._getAll('profiles'),
                issuers: await this._getAll('issuers'),
                backupMode: allowSensitiveBackup ? 'full' : 'metadata_only'
            };

            if (allowSensitiveBackup) {
                backup.secret = await this._get('secrets', 'master');
                backup.lemmas = await this._getAll('lemmas');
            }
            
            // Store backup in localStorage (survives IndexedDB clear)
            const existingBackups = JSON.parse(localStorage.getItem('lemma_wallet_backups') || '[]');
            existingBackups.unshift(backup);
            // Keep only last 3 backups
            if (existingBackups.length > 3) {
                existingBackups.pop();
            }
            localStorage.setItem('lemma_wallet_backups', JSON.stringify(existingBackups));
            
            console.log(`[Lemma] Wallet data backed up to localStorage (${backup.backupMode})`);
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
        const backupMode = backup.backupMode || 'full';
        
        // Clear current data first
        await this._clearWalletData();
        
        // Restore secret (present only for full backups)
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
        
        // Restore lemmas (present only for full backups)
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
            message: backupMode === 'full'
                ? 'Wallet restored. Create a passkey to secure it.'
                : 'Wallet metadata restored. Re-link or re-issue credentials as needed.',
            restoredAt: Date.now(),
            backupTimestamp: backup.timestamp,
            profileCount: backup.profiles?.length || 0,
            backupMode
        };
    }
    
    /**
     * Encrypt payload for device linking using AES-GCM
     */
    async _encryptForLink(payload, keyBytes, additionalData = null) {
        const encoder = new TextEncoder();
        return this._encryptLinkBytes(encoder.encode(payload), keyBytes, additionalData);
    }

    /**
     * Encrypt raw payload bytes for device linking using AES-GCM.
     */
    async _encryptLinkBytes(payloadBytes, keyBytes, additionalData = null) {
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
        const encryptParams = { name: 'AES-GCM', iv: iv };
        if (additionalData) {
            encryptParams.additionalData = new TextEncoder().encode(additionalData);
        }
        const encrypted = await crypto.subtle.encrypt(
            encryptParams,
            key,
            payloadBytes
        );
        
        // Combine IV + ciphertext and base64 encode
        const combined = new Uint8Array(iv.length + encrypted.byteLength);
        combined.set(iv, 0);
        combined.set(new Uint8Array(encrypted), iv.length);
        
        return this._arrayBufferToStandardBase64(combined);
    }

    async _prepareLinkPayloadBytes(payload) {
        const bytes = new TextEncoder().encode(payload);
        const compressed = await this._gzipBytes(bytes);
        if (compressed && compressed.byteLength < bytes.byteLength) {
            return { bytes: compressed, encoding: 'gzip' };
        }
        return { bytes, encoding: null };
    }

    async _gzipBytes(bytes) {
        if (typeof CompressionStream === 'undefined' || typeof Response === 'undefined' || typeof Blob === 'undefined') {
            return null;
        }
        try {
            const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream('gzip'));
            return new Uint8Array(await new Response(stream).arrayBuffer());
        } catch (e) {
            console.warn('[Lemma] Link payload compression unavailable:', e.message);
            return null;
        }
    }

    async _gunzipBytes(bytes) {
        if (typeof DecompressionStream === 'undefined' || typeof Response === 'undefined' || typeof Blob === 'undefined') {
            throw new Error('This browser cannot open compressed transfer links. Update your browser or generate a new transfer link from a compatible device.');
        }
        const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
        return new Uint8Array(await new Response(stream).arrayBuffer());
    }

    _arrayBufferToStandardBase64(buffer) {
        const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
        let binary = '';
        const chunkSize = 0x8000;
        for (let i = 0; i < bytes.length; i += chunkSize) {
            binary += String.fromCharCode(...bytes.slice(i, i + chunkSize));
        }
        return btoa(binary);
    }
    
    // ========================================
    // BACKWARDS COMPATIBILITY (for old templates)
    // ========================================

    /**
     * Store credential (backwards compatible alias for storeLemma)
     * Phase 2.1: bridge removed — credentials are stored locally only.
     */
    async storeCredential(credential) {
        await this.init();

        const ensureObject = (value) => {
            if (value && typeof value === 'object' && !Array.isArray(value)) return value;
            if (typeof value === 'string') {
                const text = value.trim();
                if (!text) return {};
                try {
                    return JSON.parse(text);
                } catch (_) {
                    return {};
                }
            }
            return {};
        };
        const rawClaims = ensureObject(credential?.claims);
        const rawSubject = ensureObject(credential?.credentialSubject);
        const mergedClaims = Object.keys(rawClaims).length ? rawClaims : rawSubject;
        const mergedSubject = Object.keys(rawSubject).length ? rawSubject : rawClaims;
        
        // Normalize credential format
        const lemma = {
            ...credential,
            id: credential.id || `cred_${Date.now()}`,
            issuer: credential.issuer || 'did:web:lemma.id',
            signature: credential.signature || credential.proof?.proofValue || 'legacy',
            claims: mergedClaims,
            credentialSubject: mergedSubject,
            type: credential.type || ['VerifiableCredential'],
            packageType: credential.packageType || mergedClaims.packageType || mergedSubject.packageType || 'permission',
            storedAt: Date.now()
        };
        
        const isIsHumanCredential = this._isIsHumanCredentialRecord(lemma);
        let storedInLemmas = false;

        // Store locally (encrypted lemmas when PRF available)
        try {
            await this._put('lemmas', lemma);
            storedInLemmas = true;
        } catch (e) {
            if (isIsHumanCredential && this._isEncryptedStorageLockedError(e)) {
                console.warn('[Lemma] Encrypted lemmas locked — isHuman credential cached only');
            } else {
                throw e;
            }
        }

        if (isIsHumanCredential) {
            const storedInCache = await this._putIsHumanCacheRecord(lemma);
            if (!storedInLemmas && !storedInCache) {
                throw new Error('ishuman_storage_unavailable');
            }
        }
        console.log(' Credential stored locally:', lemma.id);
        
        // Phase 2.1: the central-wallet bridge iframe was removed. Credentials
        // live in the local wallet; cross-site visibility is popup-only now.
        return { success: true, id: lemma.id };
    }
    
    /**
     * Get credentials (backwards compatible alias for getLemmas)
     * Phase 2.1: bridge removed — only local credentials are returned.
     * @param {string} type - Optional filter by packageType ('permission', 'identity', etc)
     */
    async getCredentials(type = null) {
        await this.init();
        const pickRichClaims = (...candidates) => {
            const normalized = candidates.map(c => (c && typeof c === 'object') ? c : {});
            const score = (obj) => {
                let s = 0;
                if (Object.keys(obj).length > 0) s += 1;
                if (obj.permissionId || obj.permission_level || obj.permission_id) s += 2;
                if (obj.accountType || obj.account_type) s += 2;
                if (obj.siteId || obj.site_id || obj.siteDomain || obj.site_domain) s += 2;
                if (obj.scope || obj.permissions) s += 1;
                return s;
            };
            return normalized.sort((x, y) => score(y) - score(x))[0] || {};
        };
        const normalizeCredentialRecord = (record) => {
            if (!record || typeof record !== 'object') return record;
            const nested = (record.credential && typeof record.credential === 'object')
                ? record.credential
                : ((record.lemma && typeof record.lemma === 'object')
                    ? record.lemma
                    : ((record.payload?.credential && typeof record.payload.credential === 'object')
                        ? record.payload.credential
                        : ((record.data?.credential && typeof record.data.credential === 'object')
                            ? record.data.credential
                            : null)));
            const base = nested
                ? { ...record, ...nested }
                : { ...record };
            const claims = pickRichClaims(
                base.claims,
                base.credentialSubject,
                nested?.claims,
                nested?.credentialSubject,
                base.payload?.claims,
                base.payload?.credentialSubject
            );
            const credentialSubject = pickRichClaims(
                base.credentialSubject,
                base.claims,
                nested?.credentialSubject,
                nested?.claims,
                base.payload?.credentialSubject,
                base.payload?.claims
            );
            return {
                ...base,
                claims,
                credentialSubject,
                packageType: base.packageType || claims.packageType || credentialSubject.packageType || base.type?.[1]
            };
        };

        let lemmas = (await this._getAll('lemmas')).map(normalizeCredentialRecord);
        
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
        const normalizeSite = (value) => {
            const raw = String(value || '').trim().toLowerCase();
            if (!raw) return '';
            try {
                if (raw.includes('://')) {
                    return new URL(raw).hostname.toLowerCase();
                }
            } catch (e) {
                // Fall through to manual normalization.
            }
            return raw.split('/')[0].split(':')[0];
        };
        const normalizeScope = (rawScope) => {
            if (Array.isArray(rawScope)) {
                return rawScope.map(s => String(s).trim()).filter(Boolean);
            }
            if (typeof rawScope === 'string') {
                const text = rawScope.trim();
                if (!text) return [];
                if (text.startsWith('[') && text.endsWith(']')) {
                    try {
                        const jsonLike = text.replace(/'/g, '"');
                        const parsed = JSON.parse(jsonLike);
                        if (Array.isArray(parsed)) {
                            return parsed.map(s => String(s).trim()).filter(Boolean);
                        }
                    } catch (e) {
                        // Fall back to comma parsing below.
                    }
                }
                return text.split(',').map(s => s.trim()).filter(Boolean);
            }
            return [];
        };
        const isAdminPermission = (claims) => {
            const permId = String(claims.permissionId || claims.permission_level || claims.permission_id || '').toLowerCase();
            const accountType = String(claims.accountType || claims.account_type || '').toLowerCase();
            return ['admin_access', 'super_admin', 'admin', 'superadmin', 'site_admin', 'platform_admin'].includes(permId)
                || permId.includes('admin')
                || accountType === 'admin';
        };
        
        const hasPlatformPermissionClaims = (credential) => {
            const claims = credential?.claims || credential?.credentialSubject || {};
            const site = normalizeSite(claims.siteId || claims.site || claims.site_id || claims.siteDomain || claims.site_domain || '');
            if (site !== 'lemma.id' && site !== 'lemma_platform') return false;
            return !!(
                claims.permissionId
                || claims.permission_level
                || claims.permission_id
                || claims.accountType
                || claims.account_type
            );
        };

        // 1. Get permission lemmas plus combined lemma.id isHuman+IAM master credentials.
        const permissions = (await this.getCredentials()).filter((credential) => {
            const pkgType = String(credential.packageType || credential.claims?.type || credential.type?.[1] || '').toLowerCase();
            return pkgType === 'permission'
                || pkgType === 'permissionlemma'
                || hasPlatformPermissionClaims(credential);
        });
        
        // 2. Filter for requested site
        const utils = typeof window !== 'undefined' ? window.LemmaCredentialUtils : null;
        const normalizedTargetSite = utils && typeof utils.canonicalPlatformSite === 'function'
            ? utils.canonicalPlatformSite(siteId)
            : normalizeSite(siteId);
        const sitePermissions = permissions.filter((p) => {
            let credSiteId = '';
            if (utils && typeof utils.getCredentialSiteBinding === 'function') {
                credSiteId = utils.getCredentialSiteBinding(p);
            } else {
                const claims = p.claims || p.credentialSubject || {};
                credSiteId = normalizeSite(
                    claims.siteId || claims.site || claims.site_id || claims.siteDomain || claims.site_domain || '',
                );
            }
            if (!normalizedTargetSite) return false;
            if (!credSiteId) {
                return this._shouldVerifyAsIsHumanCredential(p);
            }
            const normalizedCredSite = utils && typeof utils.canonicalPlatformSite === 'function'
                ? utils.canonicalPlatformSite(credSiteId)
                : normalizeSite(credSiteId);
            return normalizedCredSite === normalizedTargetSite;
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
        
        for (const perm of sitePermissions) {
            try {
                const verification = this._shouldVerifyAsIsHumanCredential(perm)
                    ? await this._verifyIsHumanCredentialBrowser(perm)
                    : await this.verifyLemma(perm);

                if (verification.valid) {
                    verifiedPermissions.push(perm);
                } else {
                    console.warn(`[Lemma] Permission ${perm.id} failed verification: ${verification.reason}`);
                }
            } catch (e) {
                console.warn(`[Lemma] Permission ${perm.id} verification error:`, e.message);
            }
        }
        
        const verifyTime = ((performance.now() - startTime) * 1000).toFixed(1);
        
        // Prefer the strongest verified credential for role/scope derivation.
        const rankedPermissions = [...verifiedPermissions].sort((a, b) => {
            const claimsA = a.claims || a.credentialSubject || {};
            const claimsB = b.claims || b.credentialSubject || {};
            const adminA = isAdminPermission(claimsA) ? 1 : 0;
            const adminB = isAdminPermission(claimsB) ? 1 : 0;
            if (adminA !== adminB) return adminB - adminA;
            const expA = Number(a.expirationDate || claimsA.expiresAt || 0);
            const expB = Number(b.expirationDate || claimsB.expiresAt || 0);
            return expB - expA;
        });
        const bestPermission = rankedPermissions[0] || null;
        const bestClaims = (bestPermission?.claims || bestPermission?.credentialSubject || {});
        const rawPermissionId = bestClaims.permissionId || bestClaims.permission_level || bestClaims.permission_id || '';
        const rawAliases = bestClaims.permissionAliases || bestClaims.permission_aliases || [];
        const permissionAliases = Array.isArray(rawAliases)
            ? rawAliases.map(v => String(v).trim()).filter(Boolean)
            : String(rawAliases || '').split(',').map(v => v.trim()).filter(Boolean);
        const adminLike = isAdminPermission(bestClaims) || permissionAliases.some(alias => String(alias).toLowerCase().includes('admin'));
        const normalizedPermissionId = adminLike ? 'admin_access' : rawPermissionId;

        // Extract PPID from best verified permission.
        let ppid = null;
        if (bestPermission) {
            ppid = bestPermission.subject || bestClaims.id || bestClaims.ppid;
        }
        
        return {
            hasAccess: verifiedPermissions.length > 0,
            permissions: verifiedPermissions,
            claims: bestClaims,
            // User identity
            ppid: ppid,  // The user's PPID for this site (for revocation purposes)
            // Common claim accessors
            role: adminLike ? 'admin' : (bestClaims.role || bestClaims.accountType || bestClaims.account_type || 'user'),
            scope: normalizeScope(bestClaims.scope),
            permissionId: normalizedPermissionId,
            permissionLevel: bestClaims.permission_level || rawPermissionId || null,
            permissionAliases: permissionAliases,
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

        // Check aliases (for compatibility across permission naming conventions)
        if ((perms.permissionAliases || []).some(alias =>
            alias === requiredPermission || alias.includes(requiredPermission)
        )) {
            return true;
        }
        
        return false;
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
    window.signLemmaPopEnvelope = function signLemmaPopEnvelope(popEnvelope) {
        if (typeof lemmaWalletInstance.signLemmaPopEnvelope !== 'function') {
            return Promise.resolve(null);
        }
        return lemmaWalletInstance.signLemmaPopEnvelope(popEnvelope);
    };
    
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
            const isLemmaOrigin = isLemmaHostname(window.location.hostname);
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
    if (isLemmaHostname(window.location.hostname)) {
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
    
    function isLemmaWalletDebugEnabled() {
        return typeof window !== 'undefined'
            && (window.LEMMA_WALLET_DEBUG === true || window.LEMMA_WALLET_DEBUG === 'true');
    }

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
                const type = msg.includes('') ? 'success' : 'info';
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
        if (!isLemmaWalletDebugEnabled()) {
            originalConsole.warn.apply(console, ['[Lemma] Debug panel disabled in production (set LEMMA_WALLET_DEBUG=true to enable)']);
            return;
        }
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
    
    // Auto-enable only when server explicitly enables wallet debug mode
    if (typeof window !== 'undefined' && isLemmaWalletDebugEnabled()) {
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
