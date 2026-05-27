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
 * Phase 6: one signed session presentation per tab session; steady-state verify()
 * re-validates locally with no bridge round-trip and no network calls.
 *
 * Optional `autoProvision: true` opens a Lemma-hosted popup to unlock the wallet
 * and complete IDV when no master isHuman proof is present yet.
 *
 * @version 1.2.0
 */

(function () {
'use strict';

if (typeof window !== 'undefined' && window.IsHumanVerifier) {
    return;
}

const LEMMA_ORIGIN = 'https://lemma.id';
const BRIDGE_PATH = '/wallet/bridge';
const BRIDGE_TIMEOUT_MS = 8000;
const PRESENTATION_PREFIX = 'lemma:site-presentation:v1';
const MAX_PRESENTATION_STALENESS_SECONDS = 120;
const SESSION_PRESENTATION_PREFIX = 'lemma:site-session-presentation:v1';
const DEFAULT_SESSION_TTL_SECONDS = 300;
const MIN_SESSION_TTL_SECONDS = 60;
const MAX_SESSION_TTL_SECONDS = 900;
const SESSION_STORAGE_KEY = 'ishuman_session_v1';
const SESSION_EXPIRY_SKEW_SECONDS = 5;
const BLOOM_SNAPSHOT_PREFIX = 'lemma:bloom-snapshot:v1';
const TRUST_LIST_PREFIX = 'lemma:issuer-trust-list:v1';
const DEFAULT_MAX_BLOOM_STALENESS_SECONDS = 900;
const TRUST_LIST_STORAGE_KEY = 'ishuman_trust_list';
const IDV_POPUP_PATH = '/wallet/ishuman-idv';
const IDV_POPUP_TIMEOUT_MS = 10 * 60 * 1000;
const PROVISIONABLE_REASONS = new Set([
    'no_credential',
    'no_ishuman_credential',
    'wallet_locked',
]);

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

function buildSessionPresentationPayload({
    sessionId,
    siteId,
    credentialId,
    subject,
    sessionNonceB64,
    bloomSequence,
    issuedAtUnix,
    expiresAtUnix,
}) {
    return new TextEncoder().encode([
        SESSION_PRESENTATION_PREFIX,
        String(sessionId || '').trim(),
        String(siteId || '').trim(),
        String(credentialId || '').trim(),
        String(subject || '').trim(),
        String(sessionNonceB64 || '').trim(),
        String(bloomSequence ?? ''),
        String(issuedAtUnix ?? ''),
        String(expiresAtUnix ?? ''),
    ].join('\n'));
}

async function verifySessionAssertion(assertion, signatureB64, sitePubkeyB64, expectedBloomSequence) {
    if (!assertion || typeof assertion !== 'object') {
        return { ok: false, reason: 'session_assertion_missing' };
    }
    const required = [
        'session_id',
        'site_id',
        'credential_id',
        'subject',
        'session_nonce',
        'bloom_sequence',
        'issued_at_unix',
        'expires_at_unix',
    ];
    for (const key of required) {
        if (assertion[key] === undefined || assertion[key] === null || assertion[key] === '') {
            return { ok: false, reason: `session_${key}_missing` };
        }
    }

    const nowSec = Math.floor(Date.now() / 1000);
    const expiresAt = Number(assertion.expires_at_unix);
    if (nowSec >= expiresAt - SESSION_EXPIRY_SKEW_SECONDS) {
        return { ok: false, reason: 'session_expired' };
    }
    if (Number(assertion.bloom_sequence) !== Number(expectedBloomSequence)) {
        return { ok: false, reason: 'session_bloom_sequence_mismatch' };
    }

    const payload = buildSessionPresentationPayload({
        sessionId: assertion.session_id,
        siteId: assertion.site_id,
        credentialId: assertion.credential_id,
        subject: assertion.subject,
        sessionNonceB64: assertion.session_nonce,
        bloomSequence: assertion.bloom_sequence,
        issuedAtUnix: assertion.issued_at_unix,
        expiresAtUnix: assertion.expires_at_unix,
    });
    const digest = await sha256DigestBytes(payload);
    const valid = await verifyEd25519(
        base64urlToBytes(sitePubkeyB64),
        digest,
        base64urlToBytes(signatureB64),
    );
    if (!valid) return { ok: false, reason: 'invalid_session_signature' };
    return { ok: true, reason: 'ok' };
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

function buildTrustListSignatureMessage(trustList) {
    return new TextEncoder().encode([
        TRUST_LIST_PREFIX,
        String(trustList.version || ''),
        String(trustList.content_hash || ''),
        String(trustList.generated_at_unix || ''),
        String(trustList.valid_until_unix || ''),
    ].join('\n'));
}

function normalizeDid(did) {
    return String(did || '')
        .trim()
        .split('#', 1)[0]
        .split('?', 1)[0]
        .replace(/\/+$/, '')
        .toLowerCase();
}

function extractDidPubkeyHex(did) {
    const text = String(did || '').trim();
    if (!text.startsWith('did:lemma:')) return '';
    const maybeHex = text.replace('did:lemma:', '').substring(0, 64).toLowerCase();
    if (maybeHex.length !== 64) return '';
    return /^[0-9a-f]+$/.test(maybeHex) ? maybeHex : '';
}

function computeTrustListContentHash(issuers) {
    const canonicalEntries = (Array.isArray(issuers) ? issuers : []).map((row) => ({
        did: String(row?.did || '').trim(),
        pubkey: String(row?.pubkey || '').trim().toLowerCase(),
        key_id: String(row?.key_id || '').trim(),
        status: String(row?.status || 'active').trim().toLowerCase(),
        valid_from_unix: Number(row?.valid_from_unix || 0),
        valid_until_unix: Number(row?.valid_until_unix || 0),
        priority: Number(row?.priority || 0),
    }));
    // Match api/issuer_trust_list.py json.dumps(..., sort_keys=True, separators=(",", ":"))
    const canonical = JSON.stringify(
        canonicalEntries.map((entry) => {
            const sorted = {};
            for (const key of Object.keys(entry).sort()) {
                sorted[key] = entry[key];
            }
            return sorted;
        }),
    );
    return sha256HexText(canonical);
}

async function verifySignedTrustList(trustList) {
    if (!trustList || typeof trustList !== 'object') {
        return { ok: false, reason: 'trust_list_missing', issuers: new Map() };
    }
    const required = [
        'version',
        'generated_at_unix',
        'valid_until_unix',
        'content_hash',
        'signer_pubkey',
        'signature',
        'issuers',
    ];
    for (const key of required) {
        if (trustList[key] === undefined || trustList[key] === null || trustList[key] === '') {
            return { ok: false, reason: `trust_list_${key}_missing`, issuers: new Map() };
        }
    }
    const nowSec = Math.floor(Date.now() / 1000);
    if (nowSec < Number(trustList.generated_at_unix)) {
        return { ok: false, reason: 'trust_list_not_yet_valid', issuers: new Map() };
    }
    if (nowSec > Number(trustList.valid_until_unix)) {
        return { ok: false, reason: 'trust_list_expired', issuers: new Map() };
    }
    if (!Array.isArray(trustList.issuers) || trustList.issuers.length === 0) {
        return { ok: false, reason: 'trust_list_issuers_missing', issuers: new Map() };
    }

    const expectedHash = await computeTrustListContentHash(trustList.issuers);
    if (expectedHash !== String(trustList.content_hash || '')) {
        return { ok: false, reason: 'trust_list_content_hash_mismatch', issuers: new Map() };
    }

    let trustValid = false;
    try {
        trustValid = await verifyEd25519(
            hexToBytes(String(trustList.signer_pubkey || '').toLowerCase()),
            await sha256DigestBytes(buildTrustListSignatureMessage(trustList)),
            base64urlToBytes(String(trustList.signature || '')),
        );
    } catch {
        return { ok: false, reason: 'trust_list_malformed', issuers: new Map() };
    }
    if (!trustValid) {
        return { ok: false, reason: 'trust_list_invalid_signature', issuers: new Map() };
    }

    const issuers = new Map();
    for (const row of trustList.issuers) {
        const did = normalizeDid(row?.did || '');
        const pubkey = String(row?.pubkey || '').trim().toLowerCase();
        const status = String(row?.status || 'active').toLowerCase();
        const validFrom = Number(row?.valid_from_unix || 0);
        const validUntil = Number(row?.valid_until_unix || 0);
        if (!did || pubkey.length !== 64 || !/^[0-9a-f]+$/.test(pubkey)) continue;
        if (status === 'revoked') continue;
        if (validFrom && nowSec < validFrom) continue;
        if (validUntil && nowSec > validUntil) continue;
        if (!issuers.has(did)) issuers.set(did, new Set());
        issuers.get(did).add(pubkey);
    }
    if (!issuers.size) {
        return { ok: false, reason: 'trust_list_no_active_issuers', issuers };
    }
    return { ok: true, reason: 'ok', issuers };
}

function parseIssuerPubkeyHex(snapshot) {
    const direct = String(snapshot.issuer_pubkey || '').trim();
    if (direct.length === 64) return direct;
    const did = String(snapshot.issuer_did || '');
    const fromDid = did.replace('did:lemma:', '').substring(0, 64);
    return fromDid.length === 64 ? fromDid : '';
}

async function verifyBloomSnapshot(snapshot, hashedRevokedIds, trustedIssuers) {
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
    const issuerDid = normalizeDid(snapshot.issuer_did || '');
    const trustedKeys = trustedIssuers?.get(issuerDid);
    if (!issuerDid || !trustedKeys || !trustedKeys.has(pubHex.toLowerCase())) {
        return { ok: false, reason: 'snapshot_issuer_untrusted' };
    }

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
     * @param {boolean} [config.autoProvision] — open Lemma IDV popup when no master proof exists.
     * @param {string}  [config.idvPopupPath] — override popup path (default /wallet/ishuman-idv).
     */
    constructor(config = {}) {
        this.siteId = config.siteId || window.location.hostname;
        this.lemmaOrigin = config.lemmaOrigin || LEMMA_ORIGIN;
        this.debug = !!config.debug;
        this.isBlockedLocally = config.isBlockedLocally || null;
        this.autoProvision = !!config.autoProvision;
        this.idvPopupPath = config.idvPopupPath || IDV_POPUP_PATH;

        this._bridgeReady = false;
        this._bridgeIframe = null;
        this._pendingRequests = new Map();
        this._bloomFilter = new Set();
        this._bloomSyncedAt = 0;
        this._bloomTrusted = false;
        this._bloomSnapshot = null;
        this._trustListTrusted = false;
        this._trustedIssuers = new Map();
        this._session = null;
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
    async verify(options = {}) {
        const t0 = performance.now();
        await this._initPromise;

        const autoProvision = options.autoProvision ?? this.autoProvision;
        let result = await this._verifyOnce(t0);
        if (!result.human && autoProvision && PROVISIONABLE_REASONS.has(result.reason)) {
            const provisioned = await this._provisionViaPopup();
            if (provisioned) {
                this.invalidateSession();
                result = await this._verifyOnce(t0);
            } else if (result.reason === 'no_credential') {
                result = this._result(false, null, 'idv_cancelled', t0);
            }
        }
        return result;
    }

    async _verifyOnce(t0) {
        if (!this._bloomTrusted || !this._trustListTrusted) {
            return this._result(false, null, 'revocation_data_untrusted', t0);
        }

        const cached = await this._verifyFromCachedSession(t0);
        if (cached !== null) {
            return cached;
        }

        let bridgeResult;
        try {
            bridgeResult = await this._requestSessionFromBridge();
        } catch (err) {
            return this._result(false, null, 'bridge_unavailable', t0, err.message);
        }

        if (bridgeResult?.use_legacy_presentation) {
            return this._verifyWithLegacyPresentation(bridgeResult, t0);
        }

        const bridgeReason = this._mapBridgeError(bridgeResult?.error);
        const credential = bridgeResult?.credential || null;
        if (!credential) {
            return this._result(false, null, bridgeReason || 'no_credential', t0);
        }

        const core = await this._verifyCredentialCore(credential, t0);
        if (!core.ok) {
            return this._result(false, core.ppid, core.reason, t0, core.error);
        }

        const sessionCheck = await this._verifySessionFromBridgeResult(bridgeResult, credential);
        if (!sessionCheck.ok) {
            return this._result(false, credential.subject, sessionCheck.reason, t0, sessionCheck.error);
        }

        this._persistSession({
            siteId: this.siteId,
            credential,
            session_assertion: bridgeResult.session_assertion,
            session_signature: bridgeResult.session_signature,
            session_nonce: bridgeResult.session_nonce,
            bloom_sequence: Number(this._bloomSnapshot?.sequence_number ?? 0),
        });

        return this._result(true, credential.subject, 'valid', t0);
    }

    /**
     * Clear cached session presentation (e.g. on site logout).
     */
    invalidateSession() {
        this._clearSessionCache();
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
        this._session = null;
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
                if (event.source && event.source !== this._bridgeIframe?.contentWindow) return;
                this._bridgeReady = true;
                if (this._resolveBridgeReady) this._resolveBridgeReady(event.data);
                if (this.debug) console.log('[isHuman] bridge ready', event.data);
                return;
            }
            this._handleBridgeMessage(event.data, event);
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

    _handleBridgeMessage(data, event) {
        if (!data || !data.requestId) return;
        if (event?.source && event.source !== this._bridgeIframe?.contentWindow) return;
        const pending = this._pendingRequests.get(data.requestId);
        if (!pending) return;
        const expectedType = pending.expectedType;
        if (expectedType && data.type && data.type !== expectedType) return;
        this._pendingRequests.delete(data.requestId);
        pending.resolver(data);
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
            this._pendingRequests.set(requestId, {
                expectedType: 'GET_CREDENTIAL_response',
                resolver: (response) => {
                    clearTimeout(timeout);
                    if (response.error) {
                        resolve(null);
                    } else {
                        resolve({
                            ...response,
                            challenge_nonce: challengeNonce,
                        });
                    }
                },
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

    _requestSessionFromBridge() {
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

            const sessionNonce = randomNonceB64(32);
            const bloomSequence = Number(this._bloomSnapshot?.sequence_number ?? 0);
            this._pendingRequests.set(requestId, {
                expectedType: 'GET_SESSION_PRESENTATION_response',
                resolver: async (response) => {
                    clearTimeout(timeout);
                    const errText = String(response.error || '');
                    if (errText.includes('Unknown message type')) {
                        try {
                            const legacy = await this._requestCredentialFromBridge();
                            resolve({ use_legacy_presentation: true, ...legacy });
                        } catch (legacyErr) {
                            reject(legacyErr);
                        }
                        return;
                    }
                    if (response.error || response.success === false) {
                        resolve({ error: errText || response.error || 'bridge_error' });
                        return;
                    }
                    resolve({
                        ...response,
                        session_nonce: sessionNonce,
                    });
                },
            });
            this._bridgeIframe.contentWindow.postMessage({
                type: 'GET_SESSION_PRESENTATION',
                requestId,
                payload: {
                    siteId: this.siteId,
                    credentialType: 'isHuman',
                    sessionNonce,
                    bloomSequence,
                    sessionTtlSec: DEFAULT_SESSION_TTL_SECONDS,
                },
            }, this.lemmaOrigin);
        });
    }

    async _verifyFromCachedSession(t0) {
        const session = this._loadSessionCache();
        if (!session) return null;

        const credential = session.credential;
        if (!credential) {
            this._clearSessionCache();
            return null;
        }

        const claims = credential.claims || credential.credentialSubject || {};
        const siteSigningPubkey = claims.site_signing_pubkey || claims.siteSigningPubkey;
        if (!siteSigningPubkey) {
            this._clearSessionCache();
            return null;
        }

        const bloomSequence = Number(this._bloomSnapshot?.sequence_number ?? 0);
        const sessionCheck = await verifySessionAssertion(
            session.session_assertion,
            session.session_signature,
            siteSigningPubkey,
            bloomSequence,
        );
        if (!sessionCheck.ok) {
            this._clearSessionCache();
            return null;
        }

        const core = await this._verifyCredentialCore(credential, t0);
        if (!core.ok) {
            this._clearSessionCache();
            return this._result(false, core.ppid, core.reason, t0, core.error);
        }

        const blocked = await this._checkSiteBlocked(credential.subject);
        if (blocked) {
            return this._result(false, credential.subject, 'site_blocked', t0);
        }

        return this._result(true, credential.subject, 'session_valid', t0);
    }

    async _verifyWithLegacyPresentation(bridgeResult, t0) {
        const credential = bridgeResult?.credential || null;
        if (!credential) {
            return this._result(false, null, 'no_credential', t0);
        }

        const core = await this._verifyCredentialCore(credential, t0);
        if (!core.ok) {
            return this._result(false, core.ppid, core.reason, t0, core.error);
        }

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

        const blocked = await this._checkSiteBlocked(credential.subject);
        if (blocked) {
            return this._result(false, credential.subject, 'site_blocked', t0);
        }

        return this._result(true, credential.subject, 'valid', t0);
    }

    async _verifySessionFromBridgeResult(bridgeResult, credential) {
        try {
            const claims = credential.claims || credential.credentialSubject || {};
            const siteSigningPubkey = claims.site_signing_pubkey || claims.siteSigningPubkey;
            if (!siteSigningPubkey) {
                return { ok: false, reason: 'missing_site_signing_pubkey' };
            }

            const assertion = bridgeResult?.session_assertion;
            const signature = bridgeResult?.session_signature || '';
            if (!assertion || !signature) {
                return { ok: false, reason: 'missing_session_presentation' };
            }

            if (assertion.session_nonce !== bridgeResult.session_nonce) {
                return { ok: false, reason: 'session_nonce_mismatch' };
            }

            const bloomSequence = Number(this._bloomSnapshot?.sequence_number ?? 0);
            const sessionCheck = await verifySessionAssertion(
                assertion,
                signature,
                siteSigningPubkey,
                bloomSequence,
            );
            if (!sessionCheck.ok) {
                return { ok: false, reason: sessionCheck.reason };
            }

            const blocked = await this._checkSiteBlocked(credential.subject);
            if (blocked) {
                return { ok: false, reason: 'site_blocked' };
            }

            return { ok: true, reason: 'ok' };
        } catch (err) {
            return { ok: false, reason: 'session_verification_error', error: err.message };
        }
    }

    async _verifyCredentialCore(credential, t0) {
        const claims = credential.claims || credential.credentialSubject || {};
        if (!claims.isHuman) {
            return { ok: false, ppid: null, reason: 'not_ishuman' };
        }

        const expiresAt = parseInt(credential.expiresAt || claims.expiresAt || '0', 10);
        if (expiresAt && Math.floor(Date.now() / 1000) >= expiresAt) {
            return { ok: false, ppid: credential.subject, reason: 'expired' };
        }

        if (!this._bloomTrusted) {
            return { ok: false, ppid: credential?.subject || null, reason: 'revocation_data_untrusted' };
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
                    return { ok: false, ppid: credential.subject, reason: 'revoked' };
                }
            }
        }

        try {
            const sigHex = credential.proof?.signatureValue;
            if (!sigHex) {
                return { ok: false, ppid: credential.subject, reason: 'missing_signature' };
            }

            const issuerDid = normalizeDid(credential.issuer || credential.issuerInfo?.did || '');
            const trustedKeys = this._trustedIssuers.get(issuerDid);
            if (!issuerDid || !trustedKeys || trustedKeys.size === 0) {
                return { ok: false, ppid: credential.subject, reason: 'untrusted_issuer' };
            }

            const messageHash = await sha256Digest(canonicalMessage(credential));
            let valid = false;
            for (const pubKeyHex of trustedKeys) {
                valid = await verifyEd25519(
                    hexToBytes(pubKeyHex),
                    messageHash,
                    hexToBytes(sigHex),
                );
                if (valid) break;
            }
            if (!valid) {
                return { ok: false, ppid: credential.subject, reason: 'invalid_signature' };
            }
        } catch (err) {
            return { ok: false, ppid: credential.subject, reason: 'verification_error', error: err.message };
        }

        return { ok: true, ppid: credential.subject, reason: 'ok' };
    }

    async _checkSiteBlocked(ppid) {
        if (!this.isBlockedLocally || !ppid) return false;
        try {
            return !!(await Promise.resolve(this.isBlockedLocally(ppid)));
        } catch {
            return false;
        }
    }

    _loadSessionCache() {
        if (this._session && this._session.siteId === this.siteId) {
            return this._session;
        }
        try {
            const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!parsed || parsed.siteId !== this.siteId) return null;
            this._session = parsed;
            return parsed;
        } catch {
            return null;
        }
    }

    _persistSession(session) {
        this._session = session;
        try {
            sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
        } catch { /* quota exceeded — ignore */ }
    }

    _clearSessionCache() {
        this._session = null;
        try {
            sessionStorage.removeItem(SESSION_STORAGE_KEY);
        } catch { /* ignore */ }
    }

    // ------------------------------------------------------------------
    // Bloom filter
    // ------------------------------------------------------------------

    async _syncBloom() {
        const now = Date.now();
        const snapshotAgeSec = this._bloomSnapshot
            ? Math.floor((now / 1000) - Number(this._bloomSnapshot.generated_at_unix || 0))
            : Number.MAX_SAFE_INTEGER;
        const maxAgeSec = Number(
            this._bloomSnapshot?.max_staleness_seconds || DEFAULT_MAX_BLOOM_STALENESS_SECONDS,
        );
        if (this._bloomTrusted && this._bloomFilter.size && snapshotAgeSec < maxAgeSec) {
            return;
        }

        const prevSequence = this._bloomSnapshot?.sequence_number;

        try {
            const res = await fetch(`${this.lemmaOrigin}/api/revocation/bloom-filter`);
            const data = await res.json();
            const trustList = data.trust_list || null;
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
                const trustListResult = await verifySignedTrustList(trustList);
                if (!trustListResult.ok) {
                    this._bloomTrusted = false;
                    this._trustListTrusted = false;
                    this._bloomSnapshot = null;
                    this._trustedIssuers = new Map();
                    if (this.debug) console.warn('[isHuman] trust list rejected:', trustListResult.reason);
                    return;
                }
                this._trustedIssuers = trustListResult.issuers;
                this._trustListTrusted = true;
                const trust = await verifyBloomSnapshot(snapshot, hashedIds, this._trustedIssuers);
                if (!trust.ok) {
                    this._bloomTrusted = false;
                    this._bloomSnapshot = null;
                    if (this.debug) console.warn('[isHuman] bloom snapshot rejected:', trust.reason);
                    return;
                }
                const newSequence = snapshot.sequence_number;
                if (
                    prevSequence !== undefined
                    && prevSequence !== null
                    && newSequence !== undefined
                    && newSequence !== null
                    && Number(prevSequence) !== Number(newSequence)
                ) {
                    this._clearSessionCache();
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
                    localStorage.setItem(TRUST_LIST_STORAGE_KEY, JSON.stringify({
                        trust_list: trustList,
                        ts: now,
                    }));
                } catch { /* quota exceeded — ignore */ }
            } else {
                this._bloomTrusted = false;
                this._trustListTrusted = false;
            }
        } catch {
            this._bloomTrusted = false;
            this._trustListTrusted = false;
            try {
                const cached = JSON.parse(localStorage.getItem('ishuman_bloom') || '{}');
                const trustCached = JSON.parse(localStorage.getItem(TRUST_LIST_STORAGE_KEY) || '{}');
                if (cached.ids && cached.snapshot && trustCached.trust_list) {
                    const trustListResult = await verifySignedTrustList(trustCached.trust_list);
                    if (trustListResult.ok) {
                        const trust = await verifyBloomSnapshot(
                            cached.snapshot,
                            cached.ids,
                            trustListResult.issuers,
                        );
                        if (trust.ok) {
                            this._trustedIssuers = trustListResult.issuers;
                            this._trustListTrusted = true;
                            this._bloomFilter = new Set(cached.ids);
                            this._bloomSyncedAt = cached.ts || 0;
                            this._bloomTrusted = true;
                            this._bloomSnapshot = cached.snapshot;
                        }
                    }
                }
            } catch { /* ignore */ }
        }
    }

    // ------------------------------------------------------------------
    // Result helper
    // ------------------------------------------------------------------

    _mapBridgeError(errorText) {
        const err = String(errorText || '').trim().toLowerCase();
        if (!err) return 'no_credential';
        if (err.includes('no_ishuman_credential')) return 'no_credential';
        if (err.includes('wallet_locked')) return 'wallet_locked';
        if (err.includes('derivation')) return 'derivation_failed';
        return 'no_credential';
    }

    _provisionViaPopup() {
        return new Promise((resolve) => {
            const popupUrl = new URL(`${this.lemmaOrigin}${this.idvPopupPath}`);
            popupUrl.searchParams.set('origin', window.location.origin);
            popupUrl.searchParams.set('site_id', this.siteId);

            const width = 480;
            const height = 640;
            const left = Math.max(0, Math.round(window.screenX + (window.outerWidth - width) / 2));
            const top = Math.max(0, Math.round(window.screenY + (window.outerHeight - height) / 2));
            const popup = window.open(
                popupUrl.toString(),
                'lemma_ishuman_idv',
                `popup=yes,width=${width},height=${height},left=${left},top=${top}`,
            );

            if (!popup) {
                if (this.debug) console.warn('[isHuman] IDV popup blocked by browser');
                resolve(false);
                return;
            }

            let settled = false;
            const finish = (value) => {
                if (settled) return;
                settled = true;
                window.removeEventListener('message', onMessage);
                clearTimeout(timeoutId);
                resolve(value);
            };

            const onMessage = (event) => {
                if (event.origin !== this.lemmaOrigin) return;
                if (event.data?.type === 'ISHUMAN_IDV_COMPLETE') {
                    finish(true);
                } else if (event.data?.type === 'ISHUMAN_IDV_CANCELLED') {
                    finish(false);
                }
            };

            const timeoutId = setTimeout(() => finish(false), IDV_POPUP_TIMEOUT_MS);
            window.addEventListener('message', onMessage);
        });
    }

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
