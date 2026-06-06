/**
 * isHuman Verifier SDK
 * ====================
 *
 * Lightweight client-side SDK for sites integrating with the Lemma isHuman
 * proof-of-humanity network.
 *
 * How it works:
 *   1. Serves cached per-site session presentations locally (Ed25519 + expiry + Bloom revocation)
 *   2. On a cache miss (with autoProvision), opens a Lemma-hosted popup to issue a fresh site proof
 *   3. Optionally checks site-specific PPID blocks via the isHuman API
 *   4. Returns a simple result: { human: true/false, ppid: "..." }
 *
 * Integration (two lines):
 *   <script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
 *   <script>
 *     const ih = new IsHumanVerifier({ siteId: 'your-site-id' });
 *     ih.verify().then(r => console.log(r.human, r.ppid));
 *   </script>
 *
 * Zero server calls on the verification hot path after initial Bloom sync.
 * Popup-only (Phase 2.1): one signed session presentation per tab session;
 * steady-state verify() re-validates locally with no iframe and no network calls.
 *
 * Optional `autoProvision: true` opens a Lemma-hosted popup to unlock the wallet
 * and complete IDV when no master isHuman proof is present yet.
 *
 * Attach the verified identity to your own logs:
 *   const ih = new IsHumanVerifier({ siteId: 'your-site-id' });
 *   await ih.verify({ autoProvision: true });        // once, at an entry point
 *   // Recommended for audit logs: store the bare VC (durable, offline-verifiable).
 *   const event = await ih.stamp({ action: 'post_comment' }, { includeCredential: true });
 *   // -> { action: 'post_comment', lemma: { ppid, verified, ..., credential } }
 *   // POST `event` to YOUR backend. Lemma stores none of it.
 *
 * @version 1.7.0
 */

(function () {
'use strict';

if (typeof window !== 'undefined' && window.IsHumanVerifier) {
    return;
}

const LEMMA_ORIGIN = 'https://lemma.id';
const SESSION_PRESENTATION_PREFIX = 'lemma:site-session-presentation:v1';
const DEFAULT_SESSION_TTL_SECONDS = 24 * 60 * 60;
const MIN_SESSION_TTL_SECONDS = 60;
const MAX_SESSION_TTL_SECONDS = 24 * 60 * 60;
const SESSION_STORAGE_KEY = 'ishuman_session_v1';
const SITE_VC_STORAGE_KEY = 'ishuman_site_vc:v1';
const SESSION_EXPIRY_SKEW_SECONDS = 5;
const BLOOM_SNAPSHOT_PREFIX = 'lemma:bloom-snapshot:v1';
const TRUST_LIST_PREFIX = 'lemma:issuer-trust-list:v1';
const DEFAULT_MAX_BLOOM_STALENESS_SECONDS = 900;
const TRUST_LIST_STORAGE_KEY = 'ishuman_trust_list';
// Clock skew tolerance (seconds). Browsers' clocks routinely drift by tens of
// seconds vs. the server clock; without a skew window we reject perfectly
// valid trust lists / bloom snapshots whenever generated_at_unix is slightly
// in the future. 300 s (5 min) is the conventional window for signed time
// windows in identity / OAuth specs.
const TIME_SKEW_SECONDS = 300;
const IDV_POPUP_PATH = '/wallet/ishuman-idv';
const UNLOCK_POPUP_PATH = '/wallet/popup';
const IDV_POPUP_TIMEOUT_MS = 10 * 60 * 1000;
const UNLOCK_POPUP_TIMEOUT_MS = 5 * 60 * 1000;
const PROVISIONED_STORAGE_KEY = 'ishuman_master_provisioned_v1';

function sessionCacheKey(siteId) {
    return `${SESSION_STORAGE_KEY}:${siteId || ''}`;
}

function siteVcCacheKey(siteId) {
    return `${SITE_VC_STORAGE_KEY}:${siteId || ''}`;
}

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
    if (nowSec + TIME_SKEW_SECONDS < Number(trustList.generated_at_unix)) {
        return { ok: false, reason: 'trust_list_not_yet_valid', issuers: new Map() };
    }
    if (nowSec - TIME_SKEW_SECONDS > Number(trustList.valid_until_unix)) {
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
        if (validFrom && (nowSec + TIME_SKEW_SECONDS) < validFrom) continue;
        if (validUntil && (nowSec - TIME_SKEW_SECONDS) > validUntil) continue;
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

    if (nowSec + TIME_SKEW_SECONDS < generatedAt) return { ok: false, reason: 'snapshot_not_yet_valid' };
    if (nowSec - TIME_SKEW_SECONDS > validUntil) return { ok: false, reason: 'snapshot_expired' };
    // staleness check stays strict: even with clock skew, a snapshot older
    // than max_staleness_seconds + the skew tolerance is genuinely stale.
    if (nowSec - generatedAt > maxStale + TIME_SKEW_SECONDS) return { ok: false, reason: 'snapshot_stale' };

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
        this.sessionTtlSec = Math.min(
            MAX_SESSION_TTL_SECONDS,
            Math.max(
                MIN_SESSION_TTL_SECONDS,
                Number(config.sessionTtlSec) || DEFAULT_SESSION_TTL_SECONDS,
            ),
        );

        this._bloomFilter = new Set();
        this._bloomSyncedAt = 0;
        this._bloomTrusted = false;
        this._bloomSnapshot = null;
        this._trustListTrusted = false;
        this._trustedIssuers = new Map();
        this._session = null;

        // Cross-tab site-block invalidation: when any tab on the same origin
        // posts a SITE_BLOCK_UPDATE for this site, the cached session is
        // invalidated immediately so the next verify() rechecks.
        this._setupBlockBroadcastChannel();

        this._initPromise = this._init();
    }

    _setupBlockBroadcastChannel() {
        try {
            if (typeof BroadcastChannel !== 'function') return;
            this._blockChannel = new BroadcastChannel('lemma-ishuman-blocks');
            this._blockChannel.onmessage = (event) => {
                const data = event.data || {};
                if (data.type !== 'SITE_BLOCK_UPDATE' && data.type !== 'NETWORK_REVOCATION') return;
                if (data.siteId && data.siteId !== this.siteId) return;
                if (this.debug) {
                    console.log('[isHuman] block broadcast received:', data);
                }
                this._clearSessionCache();
                if (data.type === 'NETWORK_REVOCATION') {
                    // Refresh the Bloom snapshot in the background; the next
                    // verify() will rebuild the trust state from the fresh
                    // snapshot rather than the cached one.
                    this._bloomTrusted = false;
                    this._bloomSnapshot = null;
                    this._bloomFilter = new Set();
                    this._bloomNetworkRefresh = this._syncBloom().catch(() => {});
                }
            };
        } catch { /* BroadcastChannel unavailable — non-fatal */ }
    }

    /**
     * Broadcast a site-block or network-revocation event so other tabs on
     * the same origin (using the same SDK) invalidate their cached sessions.
     * Sites can call this after triggering a block via their backend.
     */
    static broadcastBlockUpdate(payload = {}) {
        try {
            if (typeof BroadcastChannel !== 'function') return false;
            const ch = new BroadcastChannel('lemma-ishuman-blocks');
            ch.postMessage({
                type: payload.type || 'SITE_BLOCK_UPDATE',
                siteId: payload.siteId || null,
                ppid: payload.ppid || null,
                timestamp: Date.now(),
                ...payload,
            });
            ch.close();
            return true;
        } catch {
            return false;
        }
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
        if (result.human) {
            this._markProvisionedMaster();
            return result;
        }
        if (!autoProvision) {
            return result;
        }

        const popupReasons = new Set([
            'no_credential',
            'wallet_locked',
            'no_ishuman_credential',
            'site_proof_required',
            'legacy_credential_format',
            // A revoked credential is not a permanent block — it triggers a
            // fresh IDV (or fresh test verification in the demo) so the user
            // can regain access. The popup runs in 'fresh_idv' mode below.
            'revoked',
            'site_blocked',
        ]);

        if (popupReasons.has(result.reason)) {
            const needsFreshIdv = result.reason === 'revoked' || result.reason === 'site_blocked';
            // Clear the locally cached site VC so the recovered credential
            // (with a fresh credential_id, signature, and session) replaces it.
            this._clearSessionCache();
            const issued = await this._issueSiteProofViaPopup({
                freshIdv: needsFreshIdv,
                refreshReason: result.reason,
            });
            if (issued.ok) {
                this._markProvisionedMaster();
                result = await this._applyIssuedSiteProof(issued.detail, t0);
                if (!result.human) {
                    result = await this._verifyOnce(t0);
                }
            } else {
                result = this._result(false, null, issued.reason || 'idv_cancelled', t0);
            }
        }

        if (result.human) {
            this._markProvisionedMaster();
        }
        return result;
    }

    /**
     * Check verification status without opening popups (uses local session cache when valid).
     */
    async checkStatus(options = {}) {
        return this.verify({ ...options, autoProvision: false });
    }

    /**
     * Get the current user's verified PPID, or null if not verified.
     *
     * This is the simplest way to grab the site-scoped identifier at any point
     * in your flows so you can associate it with an action in YOUR OWN system.
     * By default it never opens a popup — it reads the cached session — so it's
     * safe to call inline on a hot path. Pass { autoProvision: true } if you
     * want it to trigger the Lemma popup when no proof exists yet.
     *
     * @returns {Promise<string|null>}
     */
    async getPPID(options = {}) {
        const result = await this.verify({ autoProvision: false, ...options });
        return result.human ? result.ppid : null;
    }

    /**
     * Produce a compact, self-contained "verification stamp" describing the
     * current user's isHuman status. This is the object you attach to your own
     * logs / events. Lemma stores none of this — it lives entirely in your
     * systems and you decide what to do with it.
     *
     * Shape:
     *   {
     *     verified:     boolean,       // was a valid human proof present?
     *     ppid:         string|null,   // site-scoped pseudonymous id
     *     reason:       string,        // verify() reason code
     *     siteId:       string,
     *     verifiedAt:   number,        // unix ms when this stamp was produced
     *     expiresAt:    number|null,   // credential expiry (unix seconds)
     *     credentialId: string|null,
     *     credential:   object|null,   // the bare VC — only when
     *                                  // { includeCredential: true }
     *     proof:        object|null,   // VC + signed session assertion — only
     *                                  // when { includeProof: true }
     *   }
     *
     * Choosing what evidence to store:
     *   - { includeCredential: true } (RECOMMENDED for audit logs): stores the
     *     bare verifiable credential. It is offline-verifiable and DURABLE —
     *     re-verifiable at any time until the credential expires — and smaller.
     *   - { includeProof: true }: also stores the signed session assertion,
     *     which adds replay resistance / proof-of-possession but ages out (the
     *     session assertion has an expiry + max age). Use it when you forward
     *     proofs between parties or need evidence the holder was live.
     *
     * Both are re-verifiable entirely on your backend (lemma-ishuman-verify.mjs
     * / lemma_ishuman_verify.py) with no call back to lemma.id.
     *
     * By default this does NOT open a popup. Pass { autoProvision: true } to
     * verify-then-stamp at an entry point in your flow.
     *
     * @returns {Promise<Object>}
     */
    async getVerification(options = {}) {
        const result = await this.verify({ autoProvision: false, ...options });
        const credential = result.credential || null;
        const claims = credential
            ? (credential.claims || credential.credentialSubject || {})
            : {};
        const expiresAt = parseInt(
            (credential && (credential.expiresAt || claims.expiresAt)) || '0',
            10,
        ) || null;
        const stamp = {
            verified: !!result.human,
            ppid: result.ppid || null,
            reason: result.reason,
            siteId: this.siteId,
            verifiedAt: Date.now(),
            expiresAt,
            credentialId: (credential && credential.id) || null,
        };
        if (options.includeProof) {
            stamp.proof = result.presentation || null;
        } else if (options.includeCredential) {
            stamp.credential = result.credential || null;
        }
        return stamp;
    }

    /**
     * Attach a verification stamp to an arbitrary payload, returning a new
     * object you can log, persist, or POST to your own backend. This is the
     * one-liner for "associate the verified identity with any action".
     *
     *   const event = await ih.stamp({ action: 'checkout', amount: 4200 });
     *   await fetch('/my/api/audit-log', {
     *     method: 'POST',
     *     headers: { 'Content-Type': 'application/json' },
     *     body: JSON.stringify(event),
     *   });
     *   // event === { action: 'checkout', amount: 4200, lemma: { ppid, ... } }
     *
     * The verification data is merged under `options.key` (default 'lemma').
     * Your original payload is never mutated. Nothing is sent to lemma.id.
     *
     * @param {Object} payload  your event/action object
     * @param {Object} [options] { key?: string, includeCredential?: bool, includeProof?: bool, autoProvision?: bool }
     * @returns {Promise<Object>}
     */
    async stamp(payload = {}, options = {}) {
        const verification = await this.getVerification(options);
        const key = options.key || 'lemma';
        return { ...payload, [key]: verification };
    }

    async _verifyOnce(t0) {
        if (!this._bloomTrusted || !this._trustListTrusted) {
            return this._result(false, null, 'revocation_data_untrusted', t0);
        }

        const cached = await this._verifyFromSiteVcCache(t0);
        if (cached !== null) {
            return cached;
        }

        // Popup-only (Phase 2.1): on a cache miss, signal the verify() loop to
        // issue a fresh site proof via the Lemma-hosted popup.
        return this._result(false, null, 'site_proof_required', t0);
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
     * Clean up listeners and cross-tab channels.
     */
    destroy() {
        if (this._blockChannel) {
            try { this._blockChannel.close(); } catch { /* ignore */ }
            this._blockChannel = null;
        }
        this._session = null;
    }

    // ------------------------------------------------------------------
    // Initialisation
    // ------------------------------------------------------------------

    async _init() {
        // Eagerly hydrate the Bloom snapshot + trust list from localStorage so
        // the cache-hit fast path can proceed without waiting for the network.
        // The fresh network fetch still runs (in the background) below to pick
        // up new revocations, but it no longer blocks initialisation.
        const cacheOk = await this._hydrateBloomFromCache();
        await detectWebCryptoEd25519();
        if (cacheOk) {
            this._bloomNetworkRefresh = this._syncBloom().catch(() => {});
            return;
        }
        // No usable cached snapshot — must wait for the network fetch.
        await this._syncBloom();
    }

    async _hydrateBloomFromCache() {
        try {
            const cached = JSON.parse(localStorage.getItem('ishuman_bloom') || '{}');
            const trustCached = JSON.parse(localStorage.getItem(TRUST_LIST_STORAGE_KEY) || '{}');
            if (!cached.ids || !cached.snapshot || !trustCached.trust_list) return false;
            const snapshot = cached.snapshot;
            const nowSec = Math.floor(Date.now() / 1000);
            const generatedAt = Number(snapshot.generated_at_unix || 0);
            const maxStaleness = Number(
                snapshot.max_staleness_seconds || DEFAULT_MAX_BLOOM_STALENESS_SECONDS,
            );
            if (!generatedAt || nowSec - generatedAt >= maxStaleness) return false;
            const trustListResult = await verifySignedTrustList(trustCached.trust_list);
            if (!trustListResult.ok) return false;
            const bloomCheck = await verifyBloomSnapshot(
                snapshot,
                cached.ids,
                trustListResult.issuers,
            );
            if (!bloomCheck.ok) return false;
            this._trustedIssuers = trustListResult.issuers;
            this._trustListTrusted = true;
            this._bloomFilter = new Set(cached.ids);
            this._bloomSyncedAt = cached.ts || Date.now();
            this._bloomTrusted = true;
            this._bloomSnapshot = snapshot;
            return true;
        } catch {
            return false;
        }
    }

    async _verifyFromSiteVcCache(t0) {
        const session = this._loadSessionCache();
        if (!session) return null;

        const credential = session.credential;
        if (!credential) {
            this._clearSessionCache();
            return null;
        }

        // Legacy credentials issued before the browser-canonical signature
        // (proof.signatureValueWeb) was added cannot be verified locally.
        // Treat them as a cache miss so the verifier re-issues via popup.
        if (!credential.proof || !credential.proof.signatureValueWeb) {
            if (this.debug) {
                console.warn('[isHuman] discarding cached credential without signatureValueWeb');
            }
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

        const claims = credential.claims || credential.credentialSubject || {};
        const siteSigningPubkey = claims.site_signing_pubkey || claims.siteSigningPubkey;
        if (session.session_assertion && session.session_signature && siteSigningPubkey) {
            const bloomSequence = Number(this._bloomSnapshot?.sequence_number ?? 0);
            const sessionCheck = await verifySessionAssertion(
                session.session_assertion,
                session.session_signature,
                siteSigningPubkey,
                bloomSequence,
            );
            if (sessionCheck.ok) {
                return this._result(true, credential.subject, 'session_valid', t0, null, session);
            }
        }

        return this._result(true, credential.subject, 'vc_valid', t0, null, session);
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
            // The Rust binary-concat signature in proof.signatureValue cannot
            // be reproduced in JS — only the parallel browser-canonical
            // signature (proof.signatureValueWeb) is locally verifiable.
            const sigHex = credential.proof?.signatureValueWeb;
            if (!sigHex) {
                return {
                    ok: false,
                    ppid: credential.subject,
                    reason: 'legacy_credential_format',
                };
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
        const keys = [siteVcCacheKey(this.siteId), sessionCacheKey(this.siteId)];
        for (const key of keys) {
            try {
                const raw = localStorage.getItem(key);
                if (!raw) continue;
                const parsed = JSON.parse(raw);
                if (!parsed || parsed.siteId !== this.siteId) continue;
                this._session = parsed;
                return parsed;
            } catch {
                continue;
            }
        }
        return null;
    }

    _persistSession(session) {
        this._session = session;
        const key = siteVcCacheKey(this.siteId);
        try {
            localStorage.setItem(key, JSON.stringify(session));
            localStorage.setItem(sessionCacheKey(this.siteId), JSON.stringify(session));
        } catch { /* quota exceeded — ignore */ }
    }

    _clearSessionCache(clearAll = false) {
        this._session = null;
        try {
            if (clearAll) {
                for (let i = localStorage.length - 1; i >= 0; i -= 1) {
                    const key = localStorage.key(i);
                    if (key && (key.startsWith(`${SESSION_STORAGE_KEY}:`) || key.startsWith(`${SITE_VC_STORAGE_KEY}:`))) {
                        localStorage.removeItem(key);
                    }
                }
                return;
            }
            localStorage.removeItem(siteVcCacheKey(this.siteId));
            localStorage.removeItem(sessionCacheKey(this.siteId));
        } catch { /* ignore */ }
    }

    _hasProvisionedMaster() {
        try {
            return localStorage.getItem(PROVISIONED_STORAGE_KEY) === '1';
        } catch {
            return false;
        }
    }

    _markProvisionedMaster() {
        try {
            localStorage.setItem(PROVISIONED_STORAGE_KEY, '1');
        } catch { /* ignore */ }
    }

    // ------------------------------------------------------------------
    // Bloom filter
    // ------------------------------------------------------------------

    async _syncBloom(options = {}) {
        const force = !!options.force;
        const now = Date.now();
        const snapshotAgeSec = this._bloomSnapshot
            ? Math.floor((now / 1000) - Number(this._bloomSnapshot.generated_at_unix || 0))
            : Number.MAX_SAFE_INTEGER;
        const maxAgeSec = Number(
            this._bloomSnapshot?.max_staleness_seconds || DEFAULT_MAX_BLOOM_STALENESS_SECONDS,
        );
        if (!force && this._bloomTrusted && this._bloomFilter.size && snapshotAgeSec < maxAgeSec) {
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
                    this._clearSessionCache(true);
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

    async _applyIssuedSiteProof(detail, t0) {
        const credential = detail?.credential || null;
        if (!credential) {
            return this._result(false, null, 'no_credential', t0);
        }

        // The popup just (re-)issued this credential server-side. If the
        // popup ran in fresh_idv mode after a revocation, the server cleared
        // the prior revocation rows — but our in-memory Bloom snapshot is
        // pre-reset and would still flag this credential as revoked. Force a
        // fresh /api/revocation/bloom-filter fetch before verifying.
        const wasFreshIdv = detail?.reason === 'fresh_idv_complete'
            || detail?.refresh_reason === 'revoked'
            || detail?.refresh_reason === 'site_blocked';
        if (wasFreshIdv) {
            try {
                await this._syncBloom({ force: true });
            } catch (err) {
                if (this.debug) console.warn('[isHuman] forced bloom refresh failed:', err.message);
            }
        }

        const core = await this._verifyCredentialCore(credential, t0);
        if (!core.ok) {
            return this._result(false, core.ppid, core.reason, t0, core.error);
        }

        const sessionNonce = detail?.session_nonce || '';
        const bridgeResult = {
            session_assertion: detail?.session_assertion,
            session_signature: detail?.session_signature,
            session_nonce: sessionNonce,
        };
        let sessionCheck = await this._verifySessionFromBridgeResult(bridgeResult, credential);
        // The popup signs the session_assertion against a specific Bloom
        // sequence. If that sequence drifted between popup-sign and
        // SDK-verify (e.g. another network revocation landed, or the popup
        // and the SDK saw different post-reset snapshots), one extra forced
        // refresh + retry will sync them. We do NOT fall through into a
        // fresh-IDV loop on this reason — it's a transient race, not a
        // revoked credential.
        if (!sessionCheck.ok && sessionCheck.reason === 'session_bloom_sequence_mismatch') {
            try {
                await this._syncBloom({ force: true });
            } catch { /* fall through to original failure */ }
            sessionCheck = await this._verifySessionFromBridgeResult(bridgeResult, credential);
        }
        if (!sessionCheck.ok) {
            // Don't recurse back into the popup-trigger set on a bloom
            // mismatch — it would spin into a popup loop. Surface the
            // mismatch as a distinct reason instead.
            const reason = sessionCheck.reason === 'session_bloom_sequence_mismatch'
                ? 'session_bloom_sequence_mismatch'
                : sessionCheck.reason;
            return this._result(false, credential.subject, reason, t0, sessionCheck.error);
        }

        const session = {
            siteId: this.siteId,
            credential,
            session_assertion: detail.session_assertion,
            session_signature: detail.session_signature,
            session_nonce: sessionNonce,
            bloom_sequence: Number(this._bloomSnapshot?.sequence_number ?? 0),
        };
        this._persistSession(session);

        return this._result(true, credential.subject, 'valid', t0, null, session);
    }

    _issueSiteProofViaPopup(options = {}) {
        return new Promise((resolve) => {
            const requestNonce = randomNonceB64(16);
            const sessionNonce = randomNonceB64(32);
            const bloomSequence = Number(this._bloomSnapshot?.sequence_number ?? 0);

            const popupUrl = new URL(`${this.lemmaOrigin}${this.idvPopupPath}`);
            popupUrl.searchParams.set('origin', window.location.origin);
            popupUrl.searchParams.set('site_id', this.siteId);
            // 'fresh_idv' forces the popup to run a brand-new identity check
            // (or the test-mode mock in demo) and re-issue a credential after
            // a revocation. 'site_proof' keeps the existing master and just
            // derives a fresh per-site credential.
            popupUrl.searchParams.set('issue_mode', options.freshIdv ? 'fresh_idv' : 'site_proof');
            if (options.refreshReason) {
                popupUrl.searchParams.set('refresh_reason', String(options.refreshReason));
            }
            popupUrl.searchParams.set('request_nonce', requestNonce);
            popupUrl.searchParams.set('session_nonce', sessionNonce);
            popupUrl.searchParams.set('bloom_sequence', String(bloomSequence));
            popupUrl.searchParams.set('session_ttl_sec', String(this.sessionTtlSec));

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
                if (this.debug) console.warn('[isHuman] site proof popup blocked by browser');
                resolve({ ok: false, reason: 'popup_blocked', detail: null });
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
                if (event.data?.type === 'ISHUMAN_SITE_PROOF_ISSUED') {
                    const detail = event.data.detail || {};
                    if (detail.request_nonce && detail.request_nonce !== requestNonce) {
                        if (this.debug) console.warn('[isHuman] popup request nonce mismatch');
                        return;
                    }
                    finish({ ok: true, detail });
                } else if (event.data?.type === 'ISHUMAN_IDV_CANCELLED') {
                    finish({ ok: false, reason: 'idv_cancelled', detail: event.data.detail || null });
                }
            };

            const timeoutId = setTimeout(
                () => finish({ ok: false, reason: 'idv_timeout', detail: null }),
                IDV_POPUP_TIMEOUT_MS,
            );
            window.addEventListener('message', onMessage);
        });
    }

    _unlockViaPopup() {
        return new Promise((resolve) => {
            const popupUrl = new URL(`${this.lemmaOrigin}${UNLOCK_POPUP_PATH}`);
            popupUrl.searchParams.set('origin', window.location.origin);
            popupUrl.searchParams.set('ishuman', '1');

            const width = 420;
            const height = 560;
            const left = Math.max(0, Math.round(window.screenX + (window.outerWidth - width) / 2));
            const top = Math.max(0, Math.round(window.screenY + (window.outerHeight - height) / 2));
            const popup = window.open(
                popupUrl.toString(),
                'lemma_wallet_unlock',
                `popup=yes,width=${width},height=${height},left=${left},top=${top}`,
            );

            if (!popup) {
                if (this.debug) console.warn('[isHuman] wallet unlock popup blocked by browser');
                resolve(false);
                return;
            }

            let settled = false;
            const finish = async (value, detail) => {
                if (settled) return;
                settled = true;
                window.removeEventListener('message', onMessage);
                clearTimeout(timeoutId);
                resolve(value);
            };

            const onMessage = (event) => {
                if (event.origin !== this.lemmaOrigin) return;
                if (event.data?.type === 'LEMMA_UNLOCK_SUCCESS') {
                    finish(true, event.data);
                } else if (event.data?.type === 'LEMMA_UNLOCK_CANCELLED') {
                    finish(false, null);
                }
            };

            const timeoutId = setTimeout(() => finish(false, null), UNLOCK_POPUP_TIMEOUT_MS);
            window.addEventListener('message', onMessage);
        });
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
                resolve({ ok: false, detail: null });
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
                    finish({ ok: true, detail: event.data.detail || {} });
                } else if (event.data?.type === 'ISHUMAN_IDV_CANCELLED') {
                    finish({ ok: false, detail: event.data.detail || null });
                }
            };

            const timeoutId = setTimeout(() => finish({ ok: false, detail: null }), IDV_POPUP_TIMEOUT_MS);
            window.addEventListener('message', onMessage);
        });
    }

    _result(human, ppid, reason, t0, error, presentation) {
        const timeMs = performance.now() - t0;
        if (this.debug) {
            console.log(`[isHuman] ${human ? 'PASS' : 'FAIL'} reason=${reason} time=${timeMs.toFixed(1)}ms ppid=${ppid || '-'}`);
        }
        const result = {
            human,
            ppid: ppid || null,
            reason,
            timeMs,
            error: error || null,
            credential: null,
            presentation: null,
        };
        if (human && presentation && typeof presentation === 'object') {
            const cred = presentation.credential || null;
            const assertion = presentation.session_assertion || null;
            const signature = presentation.session_signature || null;
            const nonce = presentation.session_nonce || null;
            const bloomSequence = Number.isFinite(Number(presentation.bloom_sequence))
                ? Number(presentation.bloom_sequence)
                : Number(this._bloomSnapshot?.sequence_number ?? 0);
            if (cred) {
                result.credential = cred;
                result.presentation = {
                    siteId: this.siteId,
                    credential: cred,
                    session_assertion: assertion,
                    session_signature: signature,
                    session_nonce: nonce,
                    bloom_sequence: bloomSequence,
                    issuer_did: cred.issuer || cred.issuerInfo?.did || null,
                    issuer_pubkey: cred.issuerInfo?.publicKey || null,
                };
            }
        }
        return result;
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
