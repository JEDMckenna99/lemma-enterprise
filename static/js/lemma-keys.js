/**
 * Lemma wallet signing-key helpers (HKDF + Ed25519 assertions).
 * Loaded before lemma-wallet.js; exposes window.LemmaKeys.
 */
(function () {
    'use strict';

    if (typeof window !== 'undefined' && window.LemmaKeys) {
        return;
    }

    const WALLET_SIGNING_KEY_DOMAIN = 'lemma:hkdf:v1';
    const WALLET_SIGNING_KEY_INFO = 'wallet-signing-key-v1';
    const ASSERTION_PREFIX = 'lemma:wallet-assertion:v1';
    const REGISTER_PREFIX = 'lemma:register-signing-key:v1';
    const SITE_SIGNING_KEY_INFO_PREFIX = 'site-signing-key-v1:';

    let _webCryptoEd25519 = null;
    let _nobleEd25519 = null;

    function base64urlEncode(bytes) {
        const bin = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
        let str = '';
        for (let i = 0; i < bin.length; i += 1) str += String.fromCharCode(bin[i]);
        return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
    }

    function base64urlDecode(text) {
        const padded = String(text || '').replace(/-/g, '+').replace(/_/g, '/')
            + '='.repeat((4 - (String(text || '').length % 4)) % 4);
        const raw = atob(padded);
        const out = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
        return out;
    }

    function hexToBytes(hex) {
        const clean = String(hex || '').trim();
        if (!clean || clean.length % 2 !== 0) {
            throw new Error('wallet_secret must be hex');
        }
        const out = new Uint8Array(clean.length / 2);
        for (let i = 0; i < out.length; i += 1) {
            out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
        }
        return out;
    }

    async function hkdfSha256(ikmBytes, salt, info, length) {
        const keyMaterial = await crypto.subtle.importKey(
            'raw',
            ikmBytes,
            'HKDF',
            false,
            ['deriveBits'],
        );
        const bits = await crypto.subtle.deriveBits(
            {
                name: 'HKDF',
                hash: 'SHA-256',
                salt: new TextEncoder().encode(salt),
                info: new TextEncoder().encode(info),
            },
            keyMaterial,
            length * 8,
        );
        return new Uint8Array(bits);
    }

    async function detectWebCryptoEd25519() {
        if (_webCryptoEd25519 !== null) return _webCryptoEd25519;
        try {
            const testKey = new Uint8Array(32);
            await crypto.subtle.importKey(
                'raw',
                testKey,
                { name: 'Ed25519', namedCurve: 'Ed25519' },
                false,
                ['sign'],
            );
            _webCryptoEd25519 = true;
        } catch {
            _webCryptoEd25519 = false;
        }
        return _webCryptoEd25519;
    }

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

    async function sha256Bytes(messageBytes) {
        const digest = await crypto.subtle.digest('SHA-256', messageBytes);
        return new Uint8Array(digest);
    }

    async function ed25519FromSeed(seedBytes) {
        const noble = await loadNobleEd25519();
        if (noble) {
            const publicKey = await noble.getPublicKeyAsync(seedBytes);
            return {
                publicKey,
                async sign(messageBytes) {
                    const digest = await sha256Bytes(messageBytes);
                    return noble.sign(digest, seedBytes);
                },
            };
        }

        throw new Error('No Ed25519 backend available (load @noble/ed25519)');
    }

    async function deriveWalletSigningKeypair(walletSecretHex) {
        const ikm = hexToBytes(walletSecretHex);
        const seed = await hkdfSha256(
            ikm,
            WALLET_SIGNING_KEY_DOMAIN,
            WALLET_SIGNING_KEY_INFO,
            32,
        );
        return ed25519FromSeed(seed);
    }

    function canonicalizeSiteDomain(siteDomain) {
        const input = String(siteDomain || '').trim().toLowerCase();
        if (!input) {
            throw new Error('site domain required');
        }
        let host = input;
        try {
            if (host.includes('://')) {
                host = new URL(host).hostname.toLowerCase();
            }
        } catch {
            host = input;
        }
        host = host.split('/')[0].split(':')[0].replace(/^www\./, '').trim();
        if (!host || host === 'unknown') {
            throw new Error('invalid site domain');
        }
        return host;
    }

    async function deriveSiteSigningKeypair(walletSecretHex, siteDomain) {
        const ikm = hexToBytes(walletSecretHex);
        const canonicalDomain = canonicalizeSiteDomain(siteDomain);
        const seed = await hkdfSha256(
            ikm,
            WALLET_SIGNING_KEY_DOMAIN,
            `${SITE_SIGNING_KEY_INFO_PREFIX}${canonicalDomain}`,
            32,
        );
        return ed25519FromSeed(seed);
    }

    function buildAssertionPayload({ walletId, nonceB64, fields }) {
        const lines = [
            ASSERTION_PREFIX,
            String(walletId || '').trim(),
            String(nonceB64 || '').trim(),
        ];
        const ordered = Array.isArray(fields) ? fields : Object.entries(fields || {});
        if (ordered.length && Array.isArray(ordered[0])) {
            for (const [name, value] of ordered) {
                const key = String(name || '').trim();
                lines.push(`${key}=${value == null ? '' : String(value)}`);
            }
        } else {
            for (const [name, value] of Object.entries(fields || {})) {
                const key = String(name || '').trim();
                lines.push(`${key}=${value == null ? '' : String(value)}`);
            }
        }
        return new TextEncoder().encode(lines.join('\n'));
    }

    function buildRegisterPayload({ walletId, pubkeyB64 }) {
        const lines = [
            REGISTER_PREFIX,
            String(walletId || '').trim(),
            String(pubkeyB64 || '').trim(),
        ];
        return new TextEncoder().encode(lines.join('\n'));
    }

    const LemmaKeys = {
        WALLET_SIGNING_KEY_DOMAIN,
        WALLET_SIGNING_KEY_INFO,
        SITE_SIGNING_KEY_INFO_PREFIX,
        hkdfSha256,
        deriveWalletSigningKeypair,
        deriveSiteSigningKeypair,
        canonicalizeSiteDomain,
        buildAssertionPayload,
        buildRegisterPayload,
        base64urlEncode,
        base64urlDecode,
        hexToBytes,
    };

    if (typeof window !== 'undefined') {
        window.LemmaKeys = LemmaKeys;
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = LemmaKeys;
    }
})();
