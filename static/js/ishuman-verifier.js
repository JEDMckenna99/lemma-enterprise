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
const PRESENTATION_PREFIX = 'lemma:site-presentation:v1';
const MAX_PRESENTATION_STALENESS_SECONDS = 120;
const BLOOM_SNAPSHOT_PREFIX = 'lemma:bloom-snapshot:v1';
const DEFAULT_MAX_BLOOM_STALENESS_SECONDS = 900;

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

function base64urlToBytes(text) {
    const raw = String(text || '').trim();
    if (!raw) return new Uint8Array(0);
    const padded = raw.replace(/-/g, '+').replace(/_/g, '/')
        + '='.repeat((4 - (raw.length % 4)) % 4);
    const bin = atob(padded);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
    return out;
}

async function sha256Digest(message) {
    const encoder = new TextEncoder();
    const data = encoder.encode(message);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return new Uint8Array(hash);
}

async function sha256DigestBytes(data) {
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
    Object.keys(claims).sort().forEach(k => {
        const value = claims[k];
        if (value === true) {
            sorted[k] = 'true';
        } else if (value === false) {
            sorted[k] = 'false';
        } else if (Array.isArray(value) || (value && typeof value === 'object')) {
            sorted[k] = JSON.stringify(value);
        } else {
            sorted[k] = value;
        }
    });
    return JSON.stringify({
        issuer: credential.issuer,
        subject: credential.subject,
        claims: sorted,
        issuedAt: credential.issuedAt,
        expiresAt: credential.expiresAt,
    });
}

function buildPresentationPayload({ nonceB64, credentialId, timestampSec }) {
    return new TextEncoder().encode([
        PRESENTATION_PREFIX,
        String(nonceB64 || '').trim(),
        String(credentialId || '').trim(),
        String(timestampSec || ''),
    ].join('\n'));
}

function buildBloomSignatureMessage(snapshot) {
    return new TextEncoder().encode([
        BLOOM_SNAPSHOT_PREFIX,
        String(snapshot.sequence_number || ''),
        String(snapshot.content_hash || ''),
        String(snapshot.generated_at_unix || ''),
        String(snapshot.valid_until_unix || ''),
    ].join('\n'));
}

function parseIssuerPubkeyHex(snapshot) {
    const direct = String(snapshot.issuer_pubkey || '').trim();
    if (direct.length === 64) return direct;
    const did = String(snapshot.issuer_did || '');
    const fromDid = did.replace('did:lemma:', '').substring(0, 64);
    return fromDid.length === 64 ? fromDid : '';
}

async function verifyBloomSnapshot(snapshot, hashedRevokedIds) {
    if (!snapshot || typeof snapshot !== 'object') {
        return { ok: false, reason: 'snapshot_missing' };
    }

    const required = ['sequence_number', 'generated_at_unix', 'valid_until_unix', 'content_hash', 'signature'];
    for (const key of required) {
        if (snapshot[key] === undefined || snapshot[key] === null || snapshot[key] === '') {
            return { ok: false, reason: `snapshot_${key}_missing` };
        }
    }

    const nowSec = Math.floor(Date.now() / 1000);
    const generatedAt = Number(snapshot.generated_at_unix);
    const validUntil = Number(snapshot.valid_until_unix);
    const maxStale = Number(snapshot.max_staleness_seconds || DEFAULT_MAX_BLOOM_STALENESS_SECONDS);

    if (nowSec < generatedAt) return { ok: false, reason: 'snapshot_not_yet_valid' };
    if (nowSec > validUntil) return { ok: false, reason: 'snapshot_expired' };
    if (nowSec - generatedAt > maxStale) return { ok: false, reason: 'snapshot_stale' };

    const canonicalBody = JSON.stringify({
        count: hashedRevokedIds.length,
        hashed_revoked_ids: hashedRevokedIds,
    });
    const expectedHash = await sha256HexText(canonicalBody);
    if (expectedHash !== String(snapshot.content_hash || '')) {
        return { ok: false, reason: 'snapshot_content_hash_mismatch' };
    }
    if (snapshot.count === undefined || snapshot.count === null) {
        return { ok: false, reason: 'snapshot_count_missing' };
    }
    if (Number(snapshot.count) !== hashedRevokedIds.length) {
        return { ok: false, reason: 'snapshot_count_mismatch' };
    }

    const pubHex = parseIssuerPubkeyHex(snapshot);
    if (!pubHex) return { ok: false, reason: 'snapshot_issuer_pubkey_missing' };

    const messageHash = await sha256DigestBytes(buildBloomSignatureMessage(snapshot));
    const valid = await verifyEd25519(
        hexToBytes(pubHex),
        messageHash,
        base64urlToBytes(snapshot.signature),
    );
    if (!valid) return { ok: false, reason: 'snapshot_invalid_signature' };

    return { ok: true, reason: 'ok' };
}

function randomNonceB64(length = 32) {
    const bytes = crypto.getRandomValues(new Uint8Array(length));
    let str = '';
    for (let i = 0; i < bytes.length; i += 1) str += String.fromCharCode(bytes[i]);
    return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
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
        this._bloomTrusted = false;
        this._bloomSnapshot = null;
        this._messageListener = null;
        this._bridgeReadyPromise = null;
        this._resolveBridgeReady = null;

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
        let bridgeResult;
        try {
            bridgeResult = await this._requestCredentialFromBridge();
        } catch (err) {
            return this._result(false, null, 'bridge_unavailable', t0, err.message);
        }

        const credential = bridgeResult?.credential || null;
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
        if (!this._bloomTrusted) {
            return this._result(false, credential?.subject || null, 'revocation_data_untrusted', t0);
        }

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

        // Step 6 — bridge presentation signature over verifier nonce
        try {
            const claims = credential.claims || credential.credentialSubject || {};
            const siteSigningPubkey = claims.site_signing_pubkey || claims.siteSigningPubkey;
            const presentationSignature = bridgeResult?.presentation_signature || '';
            const presentationTimestamp = Number(bridgeResult?.presentation_timestamp || 0);
            const presentationNonce = bridgeResult?.presentation_nonce || '';

            if (!siteSigningPubkey) {
                return this._result(false, credential.subject, 'missing_site_signing_pubkey', t0);
            }
            if (!presentationSignature || !presentationTimestamp || !presentationNonce) {
                return this._result(false, credential.subject, 'missing_presentation_signature', t0);
            }

            const nowSec = Math.floor(Date.now() / 1000);
            if (Math.abs(nowSec - presentationTimestamp) > MAX_PRESENTATION_STALENESS_SECONDS) {
                return this._result(false, credential.subject, 'presentation_stale', t0);
            }
            if (presentationNonce !== bridgeResult.challenge_nonce) {
                return this._result(false, credential.subject, 'presentation_nonce_mismatch', t0);
            }

            const presentationPayload = buildPresentationPayload({
                nonceB64: presentationNonce,
                credentialId: credential.id || '',
                timestampSec: presentationTimestamp,
            });
            const presentationDigest = await sha256DigestBytes(presentationPayload);
            const presentationValid = await verifyEd25519(
                base64urlToBytes(siteSigningPubkey),
                presentationDigest,
                base64urlToBytes(presentationSignature),
            );

            if (!presentationValid) {
                return this._result(false, credential.subject, 'invalid_presentation_signature', t0);
            }
        } catch (err) {
            return this._result(false, credential.subject, 'presentation_verification_error', t0, err.message);
        }

        // Step 7 — site-level block check (LOCAL — no network call to lemma.id)
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

        this._bridgeReadyPromise = new Promise((resolve) => {
            this._resolveBridgeReady = resolve;
        });

        const iframe = document.createElement('iframe');
        iframe.src = `${this.lemmaOrigin}${BRIDGE_PATH}`;
        iframe.style.cssText = 'display:none;width:0;height:0;border:0;position:absolute';
        iframe.setAttribute('aria-hidden', 'true');
        document.body.appendChild(iframe);
        this._bridgeIframe = iframe;

        this._messageListener = (event) => {
            if (event.origin !== this.lemmaOrigin) return;
            if (event.data?.type === 'WALLET_BRIDGE_READY') {
                this._bridgeReady = true;
                if (this._resolveBridgeReady) this._resolveBridgeReady(event.data);
                if (this.debug) console.log('[isHuman] bridge ready', event.data);
                return;
            }
            this._handleBridgeMessage(event.data);
        };
        window.addEventListener('message', this._messageListener);

        iframe.addEventListener('load', () => {
            this._bridgeReady = true;
            if (this._resolveBridgeReady) this._resolveBridgeReady({ ready: true, source: 'iframe_load' });
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
        return new Promise(async (resolve, reject) => {
            if (!this._bridgeIframe || !this._bridgeIframe.contentWindow) {
                return reject(new Error('Bridge iframe not available'));
            }

            if (!this._bridgeReady) {
                try {
                    await Promise.race([
                        this._bridgeReadyPromise,
                        new Promise((_, timeoutReject) => setTimeout(
                            () => timeoutReject(new Error('Bridge ready timeout')),
                            BRIDGE_TIMEOUT_MS,
                        )),
                    ]);
                } catch (err) {
                    return reject(err);
                }
            }

            const requestId = `ih_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

            const timeout = setTimeout(() => {
                this._pendingRequests.delete(requestId);
                reject(new Error('Bridge timeout'));
            }, BRIDGE_TIMEOUT_MS);

            const challengeNonce = randomNonceB64(32);
            const challengeTimestamp = Date.now();
            this._pendingRequests.set(requestId, (response) => {
                clearTimeout(timeout);
                if (response.error) {
                    resolve(null);
                } else {
                    resolve({
                        ...response,
                        challenge_nonce: challengeNonce,
                    });
                }
            });
            this._bridgeIframe.contentWindow.postMessage({
                type: 'GET_CREDENTIAL',
                requestId,
                payload: {
                    siteId: this.siteId,
                    credentialType: 'isHuman',
                    nonce: challengeNonce,
                    challengeTimestamp,
                },
            }, this.lemmaOrigin);
        });
    }

    // ------------------------------------------------------------------
    // Bloom filter
    // ------------------------------------------------------------------

    async _syncBloom() {
        const now = Date.now();
        if (
            this._bloomTrusted
            && this._bloomFilter.size
            && (now - this._bloomSyncedAt) < BLOOM_SYNC_INTERVAL_MS
        ) {
            return;
        }

        try {
            const res = await fetch(`${this.lemmaOrigin}/api/revocation/bloom-filter`);
            const data = await res.json();
            const snapshot = data.snapshot || {
                sequence_number: data.sequence_number,
                generated_at_unix: data.generated_at_unix,
                valid_until_unix: data.valid_until_unix,
                content_hash: data.content_hash,
                issuer_did: data.issuer_did,
                issuer_pubkey: data.issuer_pubkey,
                signature: data.signature,
                count: data.count,
                max_staleness_seconds: data.max_bloom_staleness_seconds,
            };
            const hashedIds = Array.isArray(data.hashed_revoked_ids) ? data.hashed_revoked_ids : [];

            if (data.success && hashedIds.length >= 0 && snapshot.signature) {
                const trust = await verifyBloomSnapshot(snapshot, hashedIds);
                if (!trust.ok) {
                    this._bloomTrusted = false;
                    this._bloomSnapshot = null;
                    if (this.debug) console.warn('[isHuman] bloom snapshot rejected:', trust.reason);
                    return;
                }
                this._bloomFilter = new Set(hashedIds);
                this._bloomSyncedAt = now;
                this._bloomTrusted = true;
                this._bloomSnapshot = snapshot;
                try {
                    localStorage.setItem('ishuman_bloom', JSON.stringify({
                        ids: hashedIds,
                        ts: now,
                        snapshot,
                    }));
                } catch { /* quota exceeded — ignore */ }
            } else {
                this._bloomTrusted = false;
            }
        } catch {
            this._bloomTrusted = false;
            try {
                const cached = JSON.parse(localStorage.getItem('ishuman_bloom') || '{}');
                if (cached.ids && cached.snapshot) {
                    const trust = await verifyBloomSnapshot(cached.snapshot, cached.ids);
                    if (trust.ok) {
                        this._bloomFilter = new Set(cached.ids);
                        this._bloomSyncedAt = cached.ts || 0;
                        this._bloomTrusted = true;
                        this._bloomSnapshot = cached.snapshot;
                    }
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
