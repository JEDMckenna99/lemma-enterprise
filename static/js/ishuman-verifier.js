/**
 * Proof Verifier SDK
 * ==================
 *
 * Lightweight client-side SDK for sites integrating with the lemma.id private
 * proof layer, including passkey continuity and optional isHuman assurance.
 *
 * How it works:
 *   1. Serves cached per-site session presentations locally (Ed25519 + expiry + Bloom revocation)
 *   2. On a cache miss (with autoProvision), opens a Lemma-hosted popup to issue a fresh site proof
 *   3. Optionally checks site-specific PPID blocks via the isHuman API
 *   4. Returns a simple result: { human: true/false, ppid: "..." }
 *
 * Integration (two lines):
 *   <script src="https://lemma.id/sdk/proof-verifier.js"></script>
 *   <script>
 *     const verifier = new ProofVerifier({ siteId: 'your-site-id' });
 *     verifier.verify().then(r => console.log(r.human, r.ppid));
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
 *   const verifier = new ProofVerifier({ siteId: 'your-site-id' });
 *   await verifier.verify({ autoProvision: true }); // once, at an entry point
 *   // Recommended for audit logs: store the bare VC (durable, offline-verifiable).
 *   const event = await verifier.stamp({ action: 'post_comment' }, { includeCredential: true });
 *   // -> { action: 'post_comment', lemma: { ppid, verified, ..., credential } }
 *   // POST `event` to YOUR backend. Lemma stores none of it.
 *
 * @version 1.9.2
 */

(function () {
'use strict';

if (typeof window !== 'undefined' && (window.ProofVerifier || window.IsHumanVerifier)) {
    const ExistingVerifier = window.ProofVerifier || window.IsHumanVerifier;
    window.ProofVerifier = ExistingVerifier;
    window.IsHumanVerifier = ExistingVerifier;
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
const BROWSER_CANONICAL_V2 = 'browser_canonical_v2';
/** Sync with docs/cryptographic/NETWORK_ROOT_PUBKEYS.json */
const DEFAULT_NETWORK_ROOT_PUBKEYS_HEX = [
    '3782cf10beea1dcc9a88127a5dbb71c6cba30c1c8c63327a83b8f09867d6a6c2',
];
const IDV_POPUP_PATH = '/wallet/ishuman-idv';
const UNLOCK_POPUP_PATH = '/wallet/popup';
const IDV_POPUP_TIMEOUT_MS = 10 * 60 * 1000;
const UNLOCK_POPUP_TIMEOUT_MS = 5 * 60 * 1000;
const POPUP_CHANNEL_NAME = 'lemma-ishuman-popup';
const POPUP_WINDOW_NAMES = {
    idv: 'lemma_ishuman_idv',
    unlock: 'lemma_wallet_unlock',
};
const PROVISIONED_STORAGE_KEY = 'ishuman_master_provisioned_v1';
const ACTION_STAMP_VERSION = 'action_stamp_v1';
const DEFAULT_ACTION_TTL_SECONDS = 60;

/** @type {{ idv: PopupFlowState, unlock: PopupFlowState }} */
const _popupFlows = {
    idv: { promise: null, popup: null },
    unlock: { promise: null, popup: null },
};
/** @type {BroadcastChannel|null} */
let _popupChannel = null;

function isMobileLikeUserAgent(ua) {
    return /iPhone|iPad|iPod|Android|Mobi/i.test(String(ua || ''));
}

const DEMO_LOGICAL_SITE_IDS = new Set([
    'tickets-demo.lemma.id',
    'trials-demo.lemma.id',
]);

function sessionCacheKey(siteId) {
    return `${SESSION_STORAGE_KEY}:${siteId || ''}`;
}

function siteVcCacheKey(siteId) {
    return `${SITE_VC_STORAGE_KEY}:${siteId || ''}`;
}

// ========================================================================
// Hex / crypto helpers (self-contained, no dependency on LemmaVerifier)
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

function canonicalJsonStringify(value) {
    if (value === null || typeof value !== 'object') {
        return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
        return `[${value.map((item) => canonicalJsonStringify(item)).join(',')}]`;
    }
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJsonStringify(value[key])}`).join(',')}}`;
}

async function hashActionBody(body) {
    const canonical = canonicalJsonStringify(body ?? {});
    return sha256HexText(canonical);
}

const ACTION_COMMITMENT_PREFIX = 'lemma:action-commitment:v1';

async function buildActionCommitment({
    serverNonce,
    siteId,
    action,
    method = 'POST',
    path = '',
    bodyHash = '',
}) {
    const lines = [
        ACTION_COMMITMENT_PREFIX,
        String(serverNonce || '').trim(),
        String(siteId || '').trim(),
        String(action || '').trim(),
        String(method || 'POST').trim().toUpperCase(),
        String(path || '').trim(),
        String(bodyHash || '').trim().toLowerCase(),
    ];
    return sha256HexText(lines.join('\n'));
}

function resolveNetworkRootPubkeys(override) {
    if (Array.isArray(override) && override.length) {
        return override.map((p) => String(p).trim().toLowerCase()).filter((p) => p.length === 64);
    }
    return DEFAULT_NETWORK_ROOT_PUBKEYS_HEX.slice();
}

function signerPubkeyIsPinned(signerPubkey, networkRootPubkeys) {
    const normalized = String(signerPubkey || '').trim().toLowerCase();
    if (!normalized || normalized.length !== 64) return false;
    const pins = resolveNetworkRootPubkeys(networkRootPubkeys);
    if (!pins.length) return true;
    return pins.includes(normalized);
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
    const payload = {
        issuer: credential.issuer,
        subject: credential.subject,
        claims: sorted,
    };
    const credentialId = String(credential.id || '').trim();
    if (credentialId) payload.id = credentialId;
    if (credential.issuedAt !== undefined && credential.issuedAt !== null) {
        payload.issuedAt = credential.issuedAt;
    }
    if (credential.expiresAt !== undefined && credential.expiresAt !== null) {
        payload.expiresAt = credential.expiresAt;
    }
    return JSON.stringify(payload);
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

async function verifySessionAssertion(assertion, signatureB64, sitePubkeyB64, expectedBloomSequence, expectedSiteId) {
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

    if (expectedSiteId) {
        const boundSite = String(assertion.site_id || '').trim().toLowerCase()
            .replace(/^www\./, '').split('/')[0].split(':')[0];
        const expected = String(expectedSiteId || '').trim().toLowerCase()
            .replace(/^www\./, '').split('/')[0].split(':')[0];
        if (boundSite && expected && boundSite !== expected) {
            return { ok: false, reason: 'session_site_id_mismatch' };
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

async function verifySignedTrustList(trustList, networkRootPubkeys) {
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
    if (!signerPubkeyIsPinned(trustList.signer_pubkey, networkRootPubkeys)) {
        return { ok: false, reason: 'trust_list_signer_not_pinned', issuers: new Map() };
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

function _getPopupChannel() {
    if (_popupChannel) return _popupChannel;
    try {
        if (typeof BroadcastChannel === 'function') {
            _popupChannel = new BroadcastChannel(POPUP_CHANNEL_NAME);
        }
    } catch { /* non-fatal */ }
    return _popupChannel;
}

function _broadcastPopupSupersede(flowKind, popupToken) {
    const ch = _getPopupChannel();
    if (!ch) return;
    try {
        ch.postMessage({
            type: 'ISHUMAN_POPUP_SUPERSEDE',
            flow: flowKind,
            token: popupToken,
            ts: Date.now(),
        });
    } catch { /* non-fatal */ }
}

function _safeClosePopup(popup) {
    try {
        if (popup && !popup.closed) popup.close();
    } catch { /* cross-origin or user gesture */ }
}

function _safeFocusPopup(popup) {
    try {
        if (popup && !popup.closed) popup.focus();
    } catch { /* non-fatal */ }
}

/**
 * Open (or focus) a Lemma popup with single-flight dedup, cross-tab supersede,
 * parent-side timeout, and close detection.
 *
 * @param {'idv'|'unlock'} flowKind
 * @param {(popupToken: string) => string} buildUrl
 * @param {number} timeoutMs
 * @param {(event: MessageEvent, ctx: { finish: Function, state: { gotMessage: boolean } }) => void} onMessage
 */
function _openManagedLemmaPopup(flowKind, buildUrl, timeoutMs, onMessage) {
    const flow = _popupFlows[flowKind];
    if (flow.promise) {
        _safeFocusPopup(flow.popup);
        return flow.promise;
    }

    flow.promise = new Promise((resolve) => {
        const popupToken = randomNonceB64(12);
        _broadcastPopupSupersede(flowKind, popupToken);

        const popupUrl = buildUrl(popupToken);
        const windowName = POPUP_WINDOW_NAMES[flowKind] || `lemma_popup_${flowKind}`;
        const width = flowKind === 'unlock' ? 420 : 480;
        const height = flowKind === 'unlock' ? 560 : 640;
        const left = Math.max(0, Math.round(window.screenX + (window.outerWidth - width) / 2));
        const top = Math.max(0, Math.round(window.screenY + (window.outerHeight - height) / 2));
        const popup = window.open(
            popupUrl,
            windowName,
            `popup=yes,width=${width},height=${height},left=${left},top=${top}`,
        );
        flow.popup = popup;

        if (!popup) {
            flow.promise = null;
            flow.popup = null;
            resolve(flowKind === 'unlock' ? false : { ok: false, blocked: true });
            return;
        }

        let settled = false;
        const state = { gotMessage: false };

        const finish = (value) => {
            if (settled) return;
            settled = true;
            window.removeEventListener('message', messageHandler);
            clearTimeout(timeoutId);
            clearInterval(closedTimer);
            flow.promise = null;
            flow.popup = null;
            resolve(value);
        };

        const messageHandler = (event) => {
            onMessage(event, finish, state);
        };

        const timeoutId = setTimeout(() => {
            _safeClosePopup(popup);
            if (flowKind === 'unlock') {
                finish(false);
                return;
            }
            finish({ ok: false, reason: 'idv_timeout', detail: null });
        }, timeoutMs);

        const closedTimer = setInterval(() => {
            if (settled || !popup.closed) return;
            if (state.gotMessage) {
                if (flowKind === 'unlock') {
                    finish(false);
                    return;
                }
                finish({ ok: false, reason: 'idv_timeout', detail: null });
                return;
            }
            if (flowKind === 'unlock') {
                finish(false);
                return;
            }
            finish({ ok: false, reason: 'popup_closed', detail: null });
        }, 500);

        window.addEventListener('message', messageHandler);
    });

    return flow.promise;
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
        _nobleEd25519 = await import(new URL('/static/js/vendor/noble-ed25519.mjs', window.location.origin).href);
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
// ProofVerifier
// ========================================================================

class ProofVerifier {
    /**
     * @param {Object} config
     * @param {string}  config.siteId, your registered site identifier
     * @param {string}  [config.lemmaOrigin], override for dev (default https://lemma.id)
     * @param {boolean} [config.debug], enable console logging
     * @param {Function} [config.isBlockedLocally], optional sync/async callback returning
     *        boolean or { blocked, doubt_required }. Sites should resolve this
     *        from their own backend state rather than exposing a site API key.
     * @param {boolean} [config.autoProvision], open Lemma IDV popup when no master proof exists.
     * @param {string}  [config.requiredAssurance], minimum assurance: ``passkey`` or ``ishuman`` (default).
     * @param {string}  [config.idvPopupPath], override popup path (default /wallet/ishuman-idv).
     */
    constructor(config = {}) {
        const rawSiteId = config.siteId || (typeof window !== 'undefined' ? window.location.hostname : '');
        this.siteId = this._canonicalizeSiteId(rawSiteId);
        this.lemmaOrigin = config.lemmaOrigin || LEMMA_ORIGIN;
        this.debug = !!config.debug;
        this.isBlockedLocally = config.isBlockedLocally || null;
        this.autoProvision = !!config.autoProvision;
        this.requiredAssurance = (config.requiredAssurance || 'ishuman').toLowerCase();
        this.networkRootPubkeys = config.networkRootPubkeys || null;
        this.idvPopupPath = config.idvPopupPath || IDV_POPUP_PATH;
        this.sessionTtlSec = Math.min(
            MAX_SESSION_TTL_SECONDS,
            Math.max(
                MIN_SESSION_TTL_SECONDS,
                Number(config.sessionTtlSec) || DEFAULT_SESSION_TTL_SECONDS,
            ),
        );
        this.strictSession = config.strictSession !== false;

        this._warnSiteIdHostnameMismatch();

        this._bloomFilter = new Set();
        this._bloomSyncedAt = 0;
        this._bloomTrusted = false;
        this._bloomSnapshot = null;
        this._trustListTrusted = false;
        this._trustedIssuers = new Map();
        this._session = null;
        this._redirectReturnResult = null;

        // Cross-tab site-block invalidation: when any tab on the same origin
        // posts a SITE_BLOCK_UPDATE for this site, the cached session is
        // invalidated immediately so the next verify() rechecks.
        this._setupBlockBroadcastChannel();

        this._initPromise = this._init();
    }

    /** Whether WebAuthn passkeys are available in this browser context. */
    static passkeySupported() {
        return typeof window !== 'undefined'
            && typeof window.PublicKeyCredential !== 'undefined';
    }

    /**
     * Map internal verify reasons to stable developer-facing SDK outcomes.
     * See docs/ERROR_CODES.md — SDK stable outcomes.
     */
    _normalizePublicSdkReason(reason, detail = null) {
        const code = String(detail?.code || detail?.error || '').trim();
        if (code === 'derive_site_proof_rate_limited') return 'rate_limited';
        switch (String(reason || '').trim()) {
            case 'popup_closed':
            case 'redirect_started':
                return 'popup_blocked';
            case 'idv_cancelled':
                return 'user_cancelled';
            default:
                return reason || 'not_verified';
        }
    }

    _credentialAssurance(credential) {
        const claims = credential?.claims || credential?.credentialSubject || {};
        if (claims.assurance) {
            return String(claims.assurance).toLowerCase();
        }
        if (claims.isHuman === true || claims.isHuman === 'true') {
            return 'ishuman';
        }
        return null;
    }

    _assuranceMeetsPolicy(assurance, requiredAssurance) {
        const required = String(requiredAssurance || 'ishuman').toLowerCase();
        const actual = String(assurance || '').toLowerCase();
        if (!actual) return false;
        if (required === 'passkey') return actual === 'passkey' || actual === 'ishuman';
        return actual === 'ishuman';
    }

    _canonicalizeSiteDomain(siteDomain) {
        const input = String(siteDomain || '').trim().toLowerCase();
        if (!input) return '';
        let host = input;
        try {
            if (host.includes('://')) {
                host = new URL(host).hostname.toLowerCase();
            }
        } catch {
            host = input;
        }
        return host.split('/')[0].split(':')[0].replace(/^www\./, '').trim();
    }

    _canonicalizeSiteId(siteId) {
        const raw = String(siteId || '').trim();
        if (!raw) throw new Error('siteId required');
        if (raw.toLowerCase().startsWith('site_')) {
            throw new Error('internal_site_id_not_allowed');
        }
        const host = this._canonicalizeSiteDomain(raw);
        if (!host || host === 'unknown') throw new Error('invalid_hostname');
        return host;
    }

    _warnSiteIdHostnameMismatch() {
        try {
            if (typeof window === 'undefined' || !window.location?.hostname) return;
            const configured = this._canonicalizeSiteDomain(this.siteId);
            if (DEMO_LOGICAL_SITE_IDS.has(configured)) return;
            const runtime = this._canonicalizeSiteDomain(window.location.hostname);
            if (configured && runtime && configured !== runtime) {
                console.warn(
                    `[isHuman] siteId "${this.siteId}" canonicalizes to "${configured}" ` +
                    `but window.location.hostname is "${window.location.hostname}" (${runtime}). ` +
                    'PPID derivation and site-block APIs require matching hostnames.',
                );
            }
        } catch { /* non-fatal */ }
    }

    _setupBlockBroadcastChannel() {
        try {
            if (typeof BroadcastChannel !== 'function') return;
            this._blockChannel = new BroadcastChannel('lemma-ishuman-blocks');
            this._blockChannel.onmessage = (event) => {
                const data = event.data || {};
                if (data.type !== 'SITE_BLOCK_UPDATE' && data.type !== 'REVOCATION_SNAPSHOT_UPDATE') return;
                if (data.siteId && data.siteId !== this.siteId) return;
                if (this.debug) {
                    console.log('[isHuman] block broadcast received:', data);
                }
                this._clearSessionCache();
                if (data.type === 'REVOCATION_SNAPSHOT_UPDATE') {
                    // Refresh the signed revocation snapshot in the background;
                    // the next verify() rebuilds trust state from the fresh copy.
                    this._bloomTrusted = false;
                    this._bloomSnapshot = null;
                    this._bloomFilter = new Set();
                    this._bloomNetworkRefresh = this._syncBloom().catch(() => {});
                }
            };
        } catch { /* BroadcastChannel unavailable, non-fatal */ }
    }

    /**
     * Broadcast a site-block or revocation-snapshot event so other tabs on
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
        this._activeRequiredAssurance = (
            options.requiredAssurance || this.requiredAssurance || 'ishuman'
        ).toLowerCase();
        await this._initPromise;
        if (this._redirectReturnResult) {
            const redirected = this._redirectReturnResult;
            this._redirectReturnResult = null;
            if (redirected.human) {
                this._markProvisionedMaster();
            }
            return redirected;
        }

        // Explicit site-doubt flow. A relying site must deliberately request
        // this ceremony; a persistent site ban never selects it automatically.
        if (options.freshIdv === true) {
            this._clearSessionCache();
            const issued = await this._issueSiteProofViaPopup({
                freshIdv: true,
                refreshReason: 'site_doubt',
            });
            if (!issued.ok) {
                return this._result(false, null, issued.reason || 'idv_cancelled', t0);
            }
            this._markProvisionedMaster();
            return this._applyIssuedSiteProof(issued.detail, t0);
        }

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
            // Stale cached credentials after issuer rotation, re-issue via popup.
            'untrusted_issuer',
            // Monthly site VC expiry: renew via daily-unlock popup (passkey only
            // when the lock bundle is missing or stale).
            'expired',
            // A revoked credential is not a permanent block, it triggers a
            // fresh IDV (or fresh test verification in the demo) so the user
            // can regain access. The popup runs in 'fresh_idv' mode below.
            'revoked',
        ]);

        if (popupReasons.has(result.reason)) {
            const needsFreshIdv = result.reason === 'revoked';
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
                    // Keep the concrete apply failure (e.g. session_bloom_sequence_mismatch)
                    // instead of masking it as site_proof_required on a cache miss.
                }
            } else if (issued.reason === 'popup_closed' && !options._retriedAfterPopupClose) {
                result = await this._verifyOnce(t0);
                if (result.human) {
                    this._markProvisionedMaster();
                } else {
                    result = this._result(false, null, 'popup_closed', t0);
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
     * Verify and return a backend-safe presentation bundle (recommended for signup).
     *
     * @returns {Promise<{ok: boolean, presentation: object|null, ppid: string|null, reason: string, timeMs: number}>}
     */
    async verifyForBackend(options = {}) {
        const requiredAssurance = (options.requiredAssurance || this.requiredAssurance || 'ishuman').toLowerCase();
        if (requiredAssurance === 'passkey' && !ProofVerifier.passkeySupported()) {
            return {
                ok: false,
                human: false,
                presentation: null,
                ppid: null,
                assurance: null,
                reason: 'passkey_unsupported',
                timeMs: 0,
            };
        }
        const result = await this.verify({ ...options, requiredAssurance });
        let presentation = result.presentation || null;
        const assurance = result.assurance || null;
        const cacheHit = result.reason === 'valid'
            || result.reason === 'session_valid'
            || result.reason === 'vc_valid';
        if (!presentation?.credential && cacheHit && result.ppid) {
            const session = this._loadSessionCache();
            if (session?.credential) {
                presentation = {
                    siteId: this.siteId,
                    credential: session.credential,
                    session_assertion: session.session_assertion,
                    session_signature: session.session_signature,
                    session_nonce: session.session_nonce,
                    bloom_sequence: Number(
                        session.bloom_sequence ?? this._bloomSnapshot?.sequence_number ?? 0,
                    ),
                };
            }
        }
        const meetsPolicy = this._assuranceMeetsPolicy(assurance, requiredAssurance);
        const ok = !!(meetsPolicy && presentation?.credential);
        const publicReason = ok
            ? result.reason
            : this._normalizePublicSdkReason(result.reason, result.detail || null);
        return {
            ok,
            human: ok,
            presentation: ok ? presentation : null,
            ppid: ok ? result.ppid : null,
            assurance,
            reason: publicReason,
            timeMs: result.timeMs,
        };
    }

    /** Run deliberate fresh IDV for a temporary site doubt. */
    async verifyFreshForBackend(options = {}) {
        return this.verifyForBackend({ ...options, autoProvision: true, freshIdv: true });
    }

    /**
     * Get the current user's verified PPID, or null if not verified.
     *
     * This is the simplest way to grab the site-scoped identifier at any point
     * in your flows so you can associate it with an action in YOUR OWN system.
     * By default it never opens a popup, it reads the cached session, so it's
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
     * logs / events. Lemma stores none of this, it lives entirely in your
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
     *     credential:   object|null,   // the bare VC, only when
     *                                  // { includeCredential: true }
     *     proof:        object|null,   // VC + signed session assertion, only
     *                                  // when { includeProof: true }
     *   }
     *
     * Choosing what evidence to store:
     *   - { includeCredential: true } (RECOMMENDED for audit logs): stores the
     *     bare verifiable credential. It is offline-verifiable and DURABLE,      *     re-verifiable at any time until the credential expires, and smaller.
     *   - { includeProof: true }: also stores the signed session assertion,
     *     which adds replay resistance / proof-of-possession but ages out (the
     *     session assertion has an expiry + max age). Use it when you forward
     *     proofs between parties or need evidence the holder was live.
     *
     * Both are re-verifiable entirely on your backend (proof-verifier.mjs
     * / proof-verifier.py) with no call back to lemma.id.
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

    /**
     * Attach an action-bound cryptographic stamp to a server request payload.
     * Verifies (optionally provisions) the site credential, then signs the
     * action fields with the wallet's site-private key via Lemma popup or a
     * co-located unlocked LemmaWallet when present.
     *
     * @param {Object} payload   business payload (also used for body hash unless options.body set)
     * @param {Object} [options] { action, method, path, body, nonce, ttlSec, key, requiredAssurance, autoProvision }
     * @returns {Promise<Object>}
     */
    async stampAction(payload = {}, options = {}) {
        const key = options.key || 'lemma';
        const action = String(options.action || payload.action || '').trim();
        const method = String(options.method || 'POST').trim().toUpperCase();
        const path = String(options.path || '').trim();
        const body = options.body !== undefined ? options.body : payload;
        const ttlSec = Number(options.ttlSec || DEFAULT_ACTION_TTL_SECONDS);
        const requiredAssurance = (options.requiredAssurance || this.requiredAssurance || 'ishuman').toLowerCase();
        const requireFreshPasskey = !!options.requireFreshPasskey;
        const serverNonce = String(options.serverNonce || '').trim();

        if (!action) {
            return { ...payload, [key]: { verified: false, reason: 'action_required' } };
        }
        if (requireFreshPasskey && !serverNonce) {
            return { ...payload, [key]: { verified: false, reason: 'server_nonce_required' } };
        }

        await this._initPromise;
        const cachedSession = this._loadSessionCache();
        const hasCachedCredential = !!cachedSession?.credential;

        const bodyHash = await hashActionBody(body);
        const nonce = String(options.nonce || randomNonceB64(16)).trim();
        const actionCommitment = requireFreshPasskey
            ? await buildActionCommitment({
                serverNonce,
                siteId: this.siteId,
                action,
                method,
                path,
                bodyHash,
            })
            : '';

        let backend = null;
        let credential = null;
        let ppid = null;
        let assurance = null;

        if (hasCachedCredential) {
            backend = await this.verifyForBackend({
                ...options,
                autoProvision: options.autoProvision ?? true,
                requiredAssurance,
            });
            if (!backend.ok || !backend.presentation?.credential) {
                return {
                    ...payload,
                    [key]: {
                        verified: false,
                        reason: backend.reason || 'not_verified',
                    },
                };
            }
            credential = backend.presentation.credential;
            ppid = backend.ppid;
            assurance = backend.assurance;
        }

        const signParams = {
            credential,
            siteId: this.siteId,
            action,
            method,
            path,
            bodyHash,
            nonce,
            ttlSec,
            requireFreshPasskey,
            serverNonce,
            actionCommitment,
        };

        let signed = null;
        if (hasCachedCredential && credential) {
            signed = await this._trySignActionLocally(signParams);
            if (!signed) {
                signed = await this._signActionViaPopup({ ...signParams, requiredAssurance });
            }
        } else {
            // First visit: one lemma.id ceremony derives site proof + signs the action.
            signed = await this._signActionViaPopup({ ...signParams, requiredAssurance });
            if (signed?.reason === 'redirect_started') {
                return {
                    ...payload,
                    [key]: { verified: false, reason: 'redirect_started' },
                };
            }
            if (signed?.credential) {
                credential = signed.credential;
                ppid = credential.subject || null;
                assurance = this._credentialAssurance(credential) || requiredAssurance;
                if (signed.session_assertion && signed.session_signature) {
                    const applied = await this._applyIssuedSiteProof({
                        credential: signed.credential,
                        session_assertion: signed.session_assertion,
                        session_signature: signed.session_signature,
                        session_nonce: signed.session_nonce || '',
                        request_nonce: signed.request_nonce || '',
                    }, performance.now());
                    if (applied.human) {
                        this._markProvisionedMaster();
                    }
                }
            }
        }

        if (!signed?.action_assertion) {
            return {
                ...payload,
                [key]: {
                    verified: false,
                    reason: signed?.reason || 'action_sign_failed',
                },
            };
        }

        if (!credential) {
            return {
                ...payload,
                [key]: {
                    verified: false,
                    reason: 'no_credential_after_sign',
                },
            };
        }

        const assertion = signed.action_assertion;
        return {
            ...payload,
            [key]: {
                version: ACTION_STAMP_VERSION,
                verified: true,
                siteId: this.siteId,
                ppid,
                credentialId: credential.id || null,
                assurance,
                action,
                method,
                path,
                bodyHash,
                nonce,
                issuedAtUnix: assertion.issued_at_unix,
                expiresAtUnix: assertion.expires_at_unix,
                credential,
                action_assertion: assertion,
                action_signature: signed.action_signature,
                fresh_passkey_attestation: signed.fresh_passkey_attestation || null,
            },
        };
    }

    async _trySignActionLocally(signParams) {
        if (typeof LemmaWallet === 'undefined') return null;
        try {
            const wallet = (typeof window !== 'undefined' && window.globalLemmaWallet)
                ? window.globalLemmaWallet
                : new LemmaWallet({ lemmaOrigin: this.lemmaOrigin });
            if (!window.globalLemmaWallet) {
                await wallet.init();
            }
            if (!wallet.isUnlocked || !wallet.isUnlocked()) {
                return null;
            }
            if (typeof wallet.signSiteActionPresentation !== 'function') {
                return null;
            }
            return await wallet.signSiteActionPresentation(signParams);
        } catch (err) {
            if (this.debug) console.warn('[isHuman] local action sign failed:', err.message);
            return null;
        }
    }

    _signActionViaPopup(signParams) {
        const requestNonce = randomNonceB64(16);
        const popupUrl = new URL(`${this.lemmaOrigin}${this.idvPopupPath}`);
        popupUrl.searchParams.set('origin', window.location.origin);
        popupUrl.searchParams.set('site_id', this.siteId);
        popupUrl.searchParams.set('issue_mode', 'action_sign');
        popupUrl.searchParams.set('request_nonce', requestNonce);
        popupUrl.searchParams.set('action', signParams.action);
        popupUrl.searchParams.set('action_method', signParams.method);
        popupUrl.searchParams.set('action_path', signParams.path);
        popupUrl.searchParams.set('body_hash', signParams.bodyHash);
        popupUrl.searchParams.set('action_nonce', signParams.nonce);
        popupUrl.searchParams.set('action_ttl_sec', String(signParams.ttlSec || DEFAULT_ACTION_TTL_SECONDS));
        if (signParams.requireFreshPasskey) {
            popupUrl.searchParams.set('require_fresh_passkey', '1');
            popupUrl.searchParams.set('server_nonce', signParams.serverNonce || '');
            popupUrl.searchParams.set('action_commitment', signParams.actionCommitment || '');
        }
        const requiredAssurance = String(signParams.requiredAssurance || '').trim().toLowerCase();
        if (requiredAssurance === 'passkey' || requiredAssurance === 'ishuman') {
            popupUrl.searchParams.set('required_assurance', requiredAssurance);
        }
        const actionSessionNonce = randomNonceB64(32);
        popupUrl.searchParams.set('session_nonce', actionSessionNonce);
        popupUrl.searchParams.set('bloom_sequence', String(this._bloomSnapshot?.sequence_number ?? 0));
        popupUrl.searchParams.set('session_ttl_sec', String(this.sessionTtlSec));

        if (this._isMobileLike()) {
            popupUrl.searchParams.set('flow_mode', 'redirect');
            popupUrl.searchParams.set('redirect_return', window.location.href);
            window.location.assign(popupUrl.toString());
            return Promise.resolve({ ok: false, reason: 'redirect_started' });
        }

        return _openManagedLemmaPopup(
            'idv',
            (popupToken) => {
                const url = new URL(popupUrl.toString());
                url.searchParams.set('popup_token', popupToken);
                return url.toString();
            },
            IDV_POPUP_TIMEOUT_MS,
            (event, finish, state) => {
                if (event.origin !== this.lemmaOrigin) return;
                if (event.data?.type === 'ISHUMAN_ACTION_SIGNED') {
                    state.gotMessage = true;
                    const detail = event.data.detail || {};
                    if (detail.request_nonce && detail.request_nonce !== requestNonce) {
                        if (this.debug) console.warn('[isHuman] action sign request nonce mismatch');
                        return;
                    }
                    finish({ ok: true, ...detail });
                } else if (event.data?.type === 'ISHUMAN_IDV_CANCELLED') {
                    state.gotMessage = true;
                    finish({ ok: false, reason: 'idv_cancelled', detail: event.data.detail || null });
                }
            },
        ).then((result) => {
            if (result?.blocked) {
                popupUrl.searchParams.set('flow_mode', 'redirect');
                popupUrl.searchParams.set('redirect_return', window.location.href);
                window.location.assign(popupUrl.toString());
                return { ok: false, reason: 'redirect_started' };
            }
            return result;
        });
    }

    async _verifyOnce(t0, options = {}) {
        if (!this._bloomTrusted || !this._trustListTrusted) {
            await this._syncBloom({ force: true });
        }
        if (!this._bloomTrusted || !this._trustListTrusted) {
            return this._result(false, null, 'revocation_data_untrusted', t0);
        }

        const cached = await this._verifyFromSiteVcCache(t0);
        if (cached !== null) {
            const recoverable = new Set(['untrusted_issuer', 'invalid_signature']);
            if (!cached.human && recoverable.has(cached.reason) && !options.retriedTrust) {
                await this._syncBloom({ force: true });
                return this._verifyOnce(t0, { retriedTrust: true });
            }
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
        await this._hydrateBloomFromCache();
        await detectWebCryptoEd25519();
        // Refresh from the network in the background; block only when we have no
        // trusted local snapshot to verify against.
        this._bloomNetworkRefresh = this._syncBloom({ force: true }).catch(() => {});
        if (!this._bloomTrusted || !this._trustListTrusted) {
            await this._bloomNetworkRefresh;
        }
        this._redirectReturnResult = await this._consumeRedirectReturnIfPresent(performance.now());
    }

    async _consumeRedirectReturnIfPresent(t0) {
        if (typeof window === 'undefined') return null;
        const params = new URLSearchParams(window.location.search);
        if (params.get('lemma_ishuman_return') !== '1') return null;
        const redirectKind = (params.get('redirect_kind') || 'site_proof').trim().toLowerCase();
        if (redirectKind === 'action_sign') {
            return null;
        }
        const requestNonce = (params.get('request_nonce') || '').trim();
        if (!requestNonce) {
            return this._result(false, null, 'redirect_return_missing_nonce', t0);
        }

        try {
            const res = await fetch(`${this.lemmaOrigin}/api/ishuman/site-proof-redirect/claim`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'omit',
                body: JSON.stringify({ request_nonce: requestNonce }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                return this._result(false, null, data.error || 'redirect_proof_not_found', t0);
            }

            params.delete('lemma_ishuman_return');
            params.delete('request_nonce');
            const cleanQuery = params.toString();
            const cleanUrl = `${window.location.pathname}${cleanQuery ? `?${cleanQuery}` : ''}${window.location.hash || ''}`;
            window.history.replaceState({}, '', cleanUrl);

            return this._applyIssuedSiteProof({
                credential: data.credential,
                session_assertion: data.session_assertion,
                session_signature: data.session_signature,
                session_nonce: data.session_nonce,
                request_nonce: requestNonce,
                ppid_convergence: data.ppid_convergence || null,
            }, t0);
        } catch (err) {
            return this._result(false, null, 'redirect_return_failed', t0, err);
        }
    }

    /**
     * Claim a redirect-deposited action-sign bundle after mobile/same-tab return.
     * Cleans redirect query params from the URL on success.
     */
    async claimRedirectActionSign() {
        if (typeof window === 'undefined') return null;
        const params = new URLSearchParams(window.location.search);
        if (params.get('lemma_ishuman_return') !== '1') return null;
        if ((params.get('redirect_kind') || '').trim().toLowerCase() !== 'action_sign') return null;
        const requestNonce = (params.get('request_nonce') || '').trim();
        if (!requestNonce) return null;

        try {
            const res = await fetch(`${this.lemmaOrigin}/api/ishuman/action-sign-redirect/claim`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'omit',
                body: JSON.stringify({ request_nonce: requestNonce }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                return { ok: false, reason: data.error || 'redirect_action_sign_not_found' };
            }

            params.delete('lemma_ishuman_return');
            params.delete('request_nonce');
            params.delete('redirect_kind');
            const cleanQuery = params.toString();
            const cleanUrl = `${window.location.pathname}${cleanQuery ? `?${cleanQuery}` : ''}${window.location.hash || ''}`;
            window.history.replaceState({}, '', cleanUrl);

            const signResult = data.sign_result || {};
            if (signResult.credential && signResult.session_assertion && signResult.session_signature) {
                const applied = await this._applyIssuedSiteProof({
                    credential: signResult.credential,
                    session_assertion: signResult.session_assertion,
                    session_signature: signResult.session_signature,
                    session_nonce: signResult.session_nonce || '',
                    request_nonce: signResult.request_nonce || requestNonce,
                }, performance.now());
                if (applied.human) {
                    this._markProvisionedMaster();
                }
            }
            return { ok: true, signResult, siteId: data.site_id || this.siteId };
        } catch (err) {
            return { ok: false, reason: 'redirect_action_sign_failed', error: err };
        }
    }

    _isMobileLike() {
        if (typeof navigator === 'undefined') return false;
        return isMobileLikeUserAgent(navigator.userAgent);
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
            const trustListResult = await verifySignedTrustList(trustCached.trust_list, this.networkRootPubkeys);
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
            // Stale issuer keys / legacy formats should re-issue via popup, not
            // surface a hard deny on customer demo sites.
            if (core.reason === 'untrusted_issuer'
                || core.reason === 'invalid_signature'
                || core.reason === 'legacy_credential_format') {
                return null;
            }
            return this._result(false, core.ppid, core.reason, t0, core.error);
        }

        const policy = this._activeRequiredAssurance || this.requiredAssurance || 'ishuman';
        const cachedAssurance = this._credentialAssurance(credential);
        if (!this._assuranceMeetsPolicy(cachedAssurance, policy)) {
            if (this.debug) {
                console.warn(
                    `[isHuman] cached assurance ${cachedAssurance || '-'} does not match `
                    + `policy ${policy}; re-issuing at requested tier`,
                );
            }
            return null;
        }

        const siteDecision = await this._checkSiteDecision(credential.subject);
        if (siteDecision.blocked) {
            return this._result(false, credential.subject, 'site_blocked', t0);
        }
        if (siteDecision.doubtRequired) {
            return this._result(false, credential.subject, 'doubt_required', t0);
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
                this.siteId,
            );
            if (sessionCheck.ok) {
                return this._result(true, credential.subject, 'session_valid', t0, null, session);
            }
            if (this.strictSession) {
                this._clearSessionCache();
                return this._result(false, credential.subject, sessionCheck.reason, t0);
            }
        } else if (this.strictSession && siteSigningPubkey) {
            this._clearSessionCache();
            return this._result(false, credential.subject, 'session_assertion_required', t0);
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
                this.siteId,
            );
            if (!sessionCheck.ok) {
                return { ok: false, reason: sessionCheck.reason };
            }

            const siteDecision = await this._checkSiteDecision(credential.subject);
            if (siteDecision.blocked) {
                return { ok: false, reason: 'site_blocked' };
            }
            if (siteDecision.doubtRequired) {
                return { ok: false, reason: 'doubt_required' };
            }

            return { ok: true, reason: 'ok' };
        } catch (err) {
            return { ok: false, reason: 'session_verification_error', error: err.message };
        }
    }

    async _verifyCredentialCore(credential, t0) {
        const claims = credential.claims || credential.credentialSubject || {};
        const assurance = this._credentialAssurance(credential);
        if (!assurance) {
            return { ok: false, ppid: null, reason: 'not_ishuman', assurance: null };
        }
        if (assurance !== 'passkey' && assurance !== 'ishuman') {
            return { ok: false, ppid: null, reason: 'invalid_assurance', assurance };
        }

        const boundSite = this._canonicalizeSiteDomain(
            claims.siteId || claims.site_id || claims.siteDomain || '',
        );
        const expectedSite = this._canonicalizeSiteDomain(this.siteId);
        if (boundSite && expectedSite && boundSite !== expectedSite) {
            return { ok: false, ppid: credential.subject, reason: 'site_id_mismatch' };
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
            // be reproduced in JS, only the parallel browser-canonical
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

    async _checkSiteDecision(ppid) {
        if (!this.isBlockedLocally || !ppid) return { blocked: false, doubtRequired: false };
        try {
            const decision = await Promise.resolve(this.isBlockedLocally(ppid));
            if (decision && typeof decision === 'object') {
                return {
                    blocked: !!decision.blocked,
                    doubtRequired: !!(decision.doubt_required || decision.doubtRequired),
                };
            }
            return { blocked: !!decision, doubtRequired: false };
        } catch {
            return { blocked: true, doubtRequired: false };
        }
    }

    async _checkSiteBlocked(ppid) {
        return (await this._checkSiteDecision(ppid)).blocked;
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
        } catch { /* quota exceeded, ignore */ }
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
            // Never let the browser HTTP cache satisfy a trust refresh. The
            // signed snapshot has a strict staleness bound, and some browsers
            // can retain an older response beyond its Cache-Control max-age.
            // The endpoint maintains its own short server-side cache.
            const res = await fetch(`${this.lemmaOrigin}/api/revocation/bloom-filter`, {
                cache: 'no-store',
                credentials: 'omit',
            });
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
                const trustListResult = await verifySignedTrustList(trustList, this.networkRootPubkeys);
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
                } catch { /* quota exceeded, ignore */ }
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
                    const trustListResult = await verifySignedTrustList(trustCached.trust_list, this.networkRootPubkeys);
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
        // the prior revocation rows, but our in-memory Bloom snapshot is
        // pre-reset and would still flag this credential as revoked. Force a
        // fresh /api/revocation/bloom-filter fetch before verifying.
        const wasFreshIdv = detail?.reason === 'fresh_idv_complete'
            || detail?.refresh_reason === 'revoked'
            || detail?.refresh_reason === 'site_doubt';
        if (wasFreshIdv) {
            try {
                await this._syncBloom({ force: true });
            } catch (err) {
                if (this.debug) console.warn('[isHuman] forced bloom refresh failed:', err.message);
            }
        }

        let core = await this._verifyCredentialCore(credential, t0);
        if (!core.ok && (core.reason === 'untrusted_issuer' || core.reason === 'invalid_signature')) {
            try {
                await this._syncBloom({ force: true });
            } catch { /* fall through */ }
            core = await this._verifyCredentialCore(credential, t0);
        }
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
        // fresh-IDV loop on this reason, it's a transient race, not a
        // revoked credential.
        if (!sessionCheck.ok && sessionCheck.reason === 'session_bloom_sequence_mismatch') {
            try {
                await this._syncBloom({ force: true });
            } catch { /* fall through to original failure */ }
            sessionCheck = await this._verifySessionFromBridgeResult(bridgeResult, credential);
        }
        if (!sessionCheck.ok) {
            // Don't recurse back into the popup-trigger set on a bloom
            // mismatch, it would spin into a popup loop. Surface the
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
            ppid_convergence: detail?.ppid_convergence || credential?.ppidConvergence || null,
        };
        this._persistSession(session);

        return this._result(true, credential.subject, 'valid', t0, null, session);
    }

    _issueSiteProofViaPopup(options = {}) {
        const requestNonce = randomNonceB64(16);
        const sessionNonce = randomNonceB64(32);
        const bloomSequence = Number(this._bloomSnapshot?.sequence_number ?? 0);

        const popupUrl = new URL(`${this.lemmaOrigin}${this.idvPopupPath}`);
        popupUrl.searchParams.set('origin', window.location.origin);
        popupUrl.searchParams.set('site_id', this.siteId);
        popupUrl.searchParams.set('issue_mode', options.freshIdv ? 'fresh_idv' : 'site_proof');
        if (options.refreshReason) {
            popupUrl.searchParams.set('refresh_reason', String(options.refreshReason));
        }
        if (options.requireFreshPasskey === true) {
            popupUrl.searchParams.set('require_fresh_passkey', '1');
        }
        popupUrl.searchParams.set('request_nonce', requestNonce);
        popupUrl.searchParams.set('session_nonce', sessionNonce);
        popupUrl.searchParams.set('bloom_sequence', String(bloomSequence));
        popupUrl.searchParams.set('session_ttl_sec', String(this.sessionTtlSec));
        popupUrl.searchParams.set('redirect_return', window.location.href);
        const requiredAssurance = this._activeRequiredAssurance || this.requiredAssurance || 'ishuman';
        if (requiredAssurance === 'passkey' || requiredAssurance === 'ishuman') {
            popupUrl.searchParams.set('required_assurance', requiredAssurance);
        }

        const useRedirect = this._isMobileLike();
        if (useRedirect) {
            popupUrl.searchParams.set('flow_mode', 'redirect');
            window.location.assign(popupUrl.toString());
            return new Promise(() => {});
        }

        return _openManagedLemmaPopup(
            'idv',
            (popupToken) => {
                const url = new URL(popupUrl.toString());
                url.searchParams.set('popup_token', popupToken);
                return url.toString();
            },
            IDV_POPUP_TIMEOUT_MS,
            (event, finish, state) => {
                if (event.origin !== this.lemmaOrigin) return;
                if (event.data?.type === 'ISHUMAN_SITE_PROOF_ISSUED') {
                    state.gotMessage = true;
                    const detail = event.data.detail || {};
                    if (detail.request_nonce && detail.request_nonce !== requestNonce) {
                        if (this.debug) console.warn('[isHuman] popup request nonce mismatch');
                        return;
                    }
                    finish({ ok: true, detail });
                } else if (event.data?.type === 'ISHUMAN_IDV_CANCELLED') {
                    state.gotMessage = true;
                    finish({ ok: false, reason: 'idv_cancelled', detail: event.data.detail || null });
                }
            },
        ).then((result) => {
            if (result?.blocked) {
                if (this.debug) console.warn('[isHuman] site proof popup blocked, falling back to redirect');
                popupUrl.searchParams.set('flow_mode', 'redirect');
                window.location.assign(popupUrl.toString());
                return { ok: false, reason: 'redirect_started', detail: null };
            }
            return result;
        });
    }

    _unlockViaPopup() {
        const popupUrl = new URL(`${this.lemmaOrigin}${this.idvPopupPath}`);
        popupUrl.searchParams.set('origin', window.location.origin);
        popupUrl.searchParams.set('site_id', this.siteId || 'lemma.id');
        popupUrl.searchParams.set('issue_mode', 'unlock');

        return _openManagedLemmaPopup(
            'unlock',
            (popupToken) => {
                const url = new URL(popupUrl.toString());
                url.searchParams.set('popup_token', popupToken);
                return url.toString();
            },
            UNLOCK_POPUP_TIMEOUT_MS,
            (event, finish, state) => {
                if (event.origin !== this.lemmaOrigin) return;
                if (event.data?.type === 'LEMMA_UNLOCK_SUCCESS' || event.data?.type === 'ISHUMAN_UNLOCK_SUCCESS') {
                    state.gotMessage = true;
                    finish(true);
                } else if (event.data?.type === 'LEMMA_UNLOCK_CANCELLED' || event.data?.type === 'ISHUMAN_IDV_CANCELLED') {
                    state.gotMessage = true;
                    finish(false);
                }
            },
        ).then((result) => {
            if (result === false && this.debug) {
                // blocked popup is indistinguishable from cancel/timeout here
            }
            return result === true;
        });
    }

    _provisionViaPopup() {
        const popupUrl = new URL(`${this.lemmaOrigin}${this.idvPopupPath}`);
        popupUrl.searchParams.set('origin', window.location.origin);
        popupUrl.searchParams.set('site_id', this.siteId);

        return _openManagedLemmaPopup(
            'idv',
            (popupToken) => {
                const url = new URL(popupUrl.toString());
                url.searchParams.set('popup_token', popupToken);
                return url.toString();
            },
            IDV_POPUP_TIMEOUT_MS,
            (event, finish, state) => {
                if (event.origin !== this.lemmaOrigin) return;
                if (event.data?.type === 'ISHUMAN_IDV_COMPLETE') {
                    state.gotMessage = true;
                    finish({ ok: true, detail: event.data.detail || {} });
                } else if (event.data?.type === 'ISHUMAN_IDV_CANCELLED') {
                    state.gotMessage = true;
                    finish({ ok: false, detail: event.data.detail || null, reason: 'idv_cancelled' });
                }
            },
        );
    }

    _result(human, ppid, reason, t0, error, presentation) {
        const timeMs = performance.now() - t0;
        let assurance = null;
        if (presentation?.credential) {
            assurance = this._credentialAssurance(presentation.credential);
        }
        const policy = this._activeRequiredAssurance || this.requiredAssurance || 'ishuman';
        const credentialVerified = !!human;
        let verified = credentialVerified;
        if (credentialVerified && assurance) {
            verified = this._assuranceMeetsPolicy(assurance, policy);
        }
        human = verified;
        if (this.debug) {
            console.log(
                `[isHuman] ${human ? 'PASS' : 'FAIL'} reason=${reason} assurance=${assurance || '-'} `
                + `time=${timeMs.toFixed(1)}ms ppid=${ppid || '-'}`,
            );
        }
        const result = {
            human,
            assurance,
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
                    ppid_convergence: presentation?.ppid_convergence || null,
                };
            }
        }
        return result;
    }
}

// ========================================================================
// Export
// ========================================================================

window.ProofVerifier = ProofVerifier;
// Backward compatibility for integrations using the original isHuman-tier name.
window.IsHumanVerifier = ProofVerifier;

if (typeof module !== 'undefined' && module.exports) {
    module.exports = ProofVerifier;
}

})();
