/**
 * isHuman Verifier SDK
 * ====================
 *
 * Lightweight client-side SDK for sites integrating with the Lemma isHuman
 * proof-of-humanity network.
 *
 * How it works:
 *   1. Embeds a hidden iframe pointing at lemma.id/wallet/bridge
 *   2. Asks the wallet bridge for the user's isHuman credential for this site
 *   3. Verifies the credential locally (Ed25519 + expiry + Bloom revocation)
 *   4. Optionally checks site-specific PPID blocks via the isHuman API
 *   5. Returns a simple result: { human: true/false, ppid: "..." }
 *
 * Integration (two lines):
 *   <script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
 *   <script>
 *     const ih = new IsHumanVerifier({ siteId: 'your-site-id' });
 *     ih.verify().then(r => console.log(r.human, r.ppid));
 *   </script>
 *
 * Zero server calls on the verification hot path after initial Bloom sync.
 *
 * @version 1.0.0
 */

(function () {
'use strict';

if (typeof window !== 'undefined' && window.IsHumanVerifier) {
    return;
}

const LEMMA_ORIGIN = 'https://lemma.id';
const BRIDGE_PATH = '/wallet/bridge';
const BLOOM_SYNC_INTERVAL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days
const BRIDGE_TIMEOUT_MS = 8000;

// ========================================================================
// Hex / crypto helpers (self-contained — no dependency on LemmaVerifier)
// ========================================================================

const _hexCache = new Map();
const _sha256HexCache = new Map();

function hexToBytes(hex) {
    if (!hex) return new Uint8Array(0);
    if (_hexCache.has(hex)) return _hexCache.get(hex);
    const len = hex.length / 2;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    if (_hexCache.size < 512) _hexCache.set(hex, bytes);
    return bytes;
}

async function sha256Digest(message) {
    const encoder = new TextEncoder();
    const data = encoder.encode(message);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return new Uint8Array(hash);
}

async function sha256HexText(value) {
    const text = String(value || '');
    if (!text) return '';
    if (_sha256HexCache.has(text)) return _sha256HexCache.get(text);

    const digest = await sha256Digest(text);
    const hex = Array.from(digest).map((b) => b.toString(16).padStart(2, '0')).join('');
    if (_sha256HexCache.size < 1024) _sha256HexCache.set(text, hex);
    return hex;
}

function canonicalMessage(credential) {
    const claims = credential.claims || credential.credentialSubject || {};
    const sorted = {};
    Object.keys(claims).sort().forEach(k => { sorted[k] = claims[k]; });
    return JSON.stringify({
        issuer: credential.issuer,
        subject: credential.subject,
        claims: sorted,
        issuedAt: credential.issuedAt,
        expiresAt: credential.expiresAt,
    });
}

// ========================================================================
// Ed25519 verification (WebCrypto → noble fallback)
// ========================================================================

let _webCryptoEd25519 = null; // null = untested, true/false after test

async function detectWebCryptoEd25519() {
    if (_webCryptoEd25519 !== null) return _webCryptoEd25519;
    try {
        const testKey = new Uint8Array(32);
        await crypto.subtle.importKey(
            'raw', testKey,
            { name: 'Ed25519', namedCurve: 'Ed25519' },
            false, ['verify'],
        );
        _webCryptoEd25519 = true;
    } catch {
        _webCryptoEd25519 = false;
    }
    return _webCryptoEd25519;
}

let _nobleEd25519 = null;

async function loadNobleEd25519() {
    if (_nobleEd25519) return _nobleEd25519;
    if (typeof window.ed25519 !== 'undefined') {
        _nobleEd25519 = window.ed25519;
        return _nobleEd25519;
    }
    try {
        _nobleEd25519 = await import('https://cdn.jsdelivr.net/npm/@noble/ed25519@2.0.0/+esm');
        return _nobleEd25519;
    } catch {
        return null;
    }
}

async function verifyEd25519(publicKeyBytes, messageBytes, signatureBytes) {
    if (await detectWebCryptoEd25519()) {
        const key = await crypto.subtle.importKey(
            'raw', publicKeyBytes,
            { name: 'Ed25519', namedCurve: 'Ed25519' },
            false, ['verify'],
        );
        return crypto.subtle.verify('Ed25519', key, signatureBytes, messageBytes);
    }

    // WASM backend (if loaded by LemmaVerifier on same page)
    if (window.lemmaWasm && window.lemmaWasm.verify_signature_bytes) {
        return window.lemmaWasm.verify_signature_bytes(publicKeyBytes, messageBytes, signatureBytes);
    }

    const noble = await loadNobleEd25519();
    if (noble) {
        return noble.verify(signatureBytes, messageBytes, publicKeyBytes);
    }

    throw new Error('No Ed25519 backend available');
}

// ========================================================================
// IsHumanVerifier
// ========================================================================

class IsHumanVerifier {
    /**
     * @param {Object} config
     * @param {string}  config.siteId     — your registered site identifier
     * @param {string}  [config.lemmaOrigin] — override for dev (default https://lemma.id)
     * @param {boolean} [config.debug]    — enable console logging
     * @param {Function} [config.isBlockedLocally] — optional sync/async callback: (ppid) => bool.
     *        Sites should use their own database to check PPID blocks rather
     *        than round-tripping to lemma.id.  This keeps verification fully local.
     */
    constructor(config = {}) {
        this.siteId = config.siteId || window.location.hostname;
        this.lemmaOrigin = config.lemmaOrigin || LEMMA_ORIGIN;
        this.debug = !!config.debug;
        this.isBlockedLocally = config.isBlockedLocally || null;

        this._bridgeReady = false;
        this._bridgeIframe = null;
        this._pendingRequests = new Map();
        this._bloomFilter = new Set();
        this._bloomSyncedAt = 0;
        this._messageListener = null;

        this._initPromise = this._init();
    }

    // ------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------

    /**
     * Verify the current user's isHuman credential.
     *
     * @returns {Promise<{human: boolean, ppid: string|null, reason: string, timeMs: number}>}
     */
    async verify() {
        const t0 = performance.now();
        await this._initPromise;

        // Step 1 — ask the wallet bridge for an isHuman credential
        let credential;
        try {
            credential = await this._requestCredentialFromBridge();
        } catch (err) {
            return this._result(false, null, 'bridge_unavailable', t0, err.message);
        }

        if (!credential) {
            return this._result(false, null, 'no_credential', t0);
        }

        // Step 2 — check isHuman claim
        const claims = credential.claims || credential.credentialSubject || {};
        if (!claims.isHuman) {
            return this._result(false, null, 'not_ishuman', t0);
        }

        // Step 3 — expiry
        const expiresAt = parseInt(credential.expiresAt || claims.expiresAt || '0', 10);
        if (expiresAt && Math.floor(Date.now() / 1000) >= expiresAt) {
            return this._result(false, credential.subject, 'expired', t0);
        }

        // Step 4 — revocation membership (SHA-256 hashed IDs/PPIDs/wallet IDs)
        if (this._bloomFilter.size) {
            const revocationCandidates = [];
            if (credential.id) revocationCandidates.push(credential.id);
            if (credential.subject) revocationCandidates.push(credential.subject);
            if (claims.walletId || claims.wallet_id) {
                revocationCandidates.push(claims.walletId || claims.wallet_id);
            }

            for (const candidate of revocationCandidates) {
                const candidateHash = await sha256HexText(candidate);
                if (candidateHash && this._bloomFilter.has(candidateHash)) {
                    return this._result(false, credential.subject, 'revoked', t0);
                }
            }
        }

        // Step 5 — Ed25519 signature
        try {
            const sigHex = credential.proof?.signatureValue;
            if (!sigHex) {
                return this._result(false, credential.subject, 'missing_signature', t0);
            }

            const issuerDid = credential.issuer || '';
            const pubKeyHex = issuerDid.replace('did:lemma:', '').substring(0, 64);

            const messageHash = await sha256Digest(canonicalMessage(credential));
            const valid = await verifyEd25519(
                hexToBytes(pubKeyHex),
                messageHash,
                hexToBytes(sigHex),
            );

            if (!valid) {
                return this._result(false, credential.subject, 'invalid_signature', t0);
            }
        } catch (err) {
            return this._result(false, credential.subject, 'verification_error', t0, err.message);
        }

        // Step 6 — site-level block check (LOCAL — no network call to lemma.id)
        // Sites manage their own block lists.  The optional callback lets the
        // site check its own database without breaking the local-first model.
        if (this.isBlockedLocally && credential.subject) {
            try {
                const blocked = await Promise.resolve(this.isBlockedLocally(credential.subject));
                if (blocked) {
                    return this._result(false, credential.subject, 'site_blocked', t0);
                }
            } catch {
                // Non-fatal — site block check failure should not reject valid credentials
            }
        }

        return this._result(true, credential.subject, 'valid', t0);
    }

    /**
     * Force a Bloom filter re-sync.
     */
    async syncRevocations() {
        return this._syncBloom();
    }

    /**
     * Destroy the bridge iframe and clean up listeners.
     */
    destroy() {
        if (this._messageListener) {
            window.removeEventListener('message', this._messageListener);
        }
        if (this._bridgeIframe && this._bridgeIframe.parentNode) {
            this._bridgeIframe.parentNode.removeChild(this._bridgeIframe);
        }
        this._bridgeReady = false;
    }

    // ------------------------------------------------------------------
    // Initialisation
    // ------------------------------------------------------------------

    async _init() {
        this._setupBridge();
        await this._syncBloom();
        await detectWebCryptoEd25519();
    }

    _setupBridge() {
        if (this._bridgeIframe) return;

        const iframe = document.createElement('iframe');
        iframe.src = `${this.lemmaOrigin}${BRIDGE_PATH}`;
        iframe.style.cssText = 'display:none;width:0;height:0;border:0;position:absolute';
        iframe.setAttribute('aria-hidden', 'true');
        document.body.appendChild(iframe);
        this._bridgeIframe = iframe;

        this._messageListener = (event) => {
            if (event.origin !== this.lemmaOrigin) return;
            this._handleBridgeMessage(event.data);
        };
        window.addEventListener('message', this._messageListener);

        iframe.addEventListener('load', () => {
            this._bridgeReady = true;
            if (this.debug) console.log('[isHuman] bridge iframe loaded');
        });
    }

    // ------------------------------------------------------------------
    // Bridge communication
    // ------------------------------------------------------------------

    _handleBridgeMessage(data) {
        if (!data || !data.requestId) return;
        const resolver = this._pendingRequests.get(data.requestId);
        if (resolver) {
            this._pendingRequests.delete(data.requestId);
            resolver(data);
        }
    }

    _requestCredentialFromBridge() {
        return new Promise((resolve, reject) => {
            if (!this._bridgeIframe || !this._bridgeIframe.contentWindow) {
                return reject(new Error('Bridge iframe not available'));
            }

            const requestId = `ih_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

            const timeout = setTimeout(() => {
                this._pendingRequests.delete(requestId);
                reject(new Error('Bridge timeout'));
            }, BRIDGE_TIMEOUT_MS);

            this._pendingRequests.set(requestId, (response) => {
                clearTimeout(timeout);
                if (response.error) {
                    resolve(null);
                } else {
                    resolve(response.credential || null);
                }
            });

            this._bridgeIframe.contentWindow.postMessage({
                type: 'GET_CREDENTIAL',
                requestId,
                siteId: this.siteId,
                credentialType: 'isHuman',
            }, this.lemmaOrigin);
        });
    }

    // ------------------------------------------------------------------
    // Bloom filter
    // ------------------------------------------------------------------

    async _syncBloom() {
        const now = Date.now();
        if (this._bloomFilter.size && (now - this._bloomSyncedAt) < BLOOM_SYNC_INTERVAL_MS) {
            return;
        }

        try {
            const res = await fetch(`${this.lemmaOrigin}/api/revocation/bloom-filter`);
            const data = await res.json();
            if (data.success && data.hashed_revoked_ids) {
                this._bloomFilter = new Set(data.hashed_revoked_ids);
                this._bloomSyncedAt = now;
                try {
                    localStorage.setItem('ishuman_bloom', JSON.stringify({
                        ids: data.hashed_revoked_ids,
                        ts: now,
                    }));
                } catch { /* quota exceeded — ignore */ }
            }
        } catch {
            try {
                const cached = JSON.parse(localStorage.getItem('ishuman_bloom') || '{}');
                if (cached.ids) {
                    this._bloomFilter = new Set(cached.ids);
                    this._bloomSyncedAt = cached.ts || 0;
                }
            } catch { /* ignore */ }
        }
    }

    // ------------------------------------------------------------------
    // Result helper
    // ------------------------------------------------------------------

    _result(human, ppid, reason, t0, error) {
        const timeMs = performance.now() - t0;
        if (this.debug) {
            console.log(`[isHuman] ${human ? 'PASS' : 'FAIL'} reason=${reason} time=${timeMs.toFixed(1)}ms ppid=${ppid || '-'}`);
        }
        return { human, ppid: ppid || null, reason, timeMs, error: error || null };
    }
}

// ========================================================================
// Export
// ========================================================================

window.IsHumanVerifier = IsHumanVerifier;

if (typeof module !== 'undefined' && module.exports) {
    module.exports = IsHumanVerifier;
}

})();
