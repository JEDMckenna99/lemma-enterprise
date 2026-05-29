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
            if (noble.etc && typeof noble.etc.sha512Sync !== 'function') {
                noble.etc.sha512Async = async (...messages) => {
                    const total = messages.reduce((sum, msg) => sum + msg.length, 0);
                    const merged = new Uint8Array(total);
                    let offset = 0;
                    for (const msg of messages) {
                        merged.set(msg, offset);
                        offset += msg.length;
                    }
                    const digest = await crypto.subtle.digest('SHA-512', merged);
                    return new Uint8Array(digest);
                };
            }
            const publicKey = await noble.getPublicKeyAsync(seedBytes);
            const signer = typeof noble.signAsync === 'function'
                ? noble.signAsync.bind(noble)
                : noble.sign.bind(noble);
            return {
                publicKey,
                async sign(messageBytes) {
                    const digest = await sha256Bytes(messageBytes);
                    return signer(digest, seedBytes);
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

    // ------------------------------------------------------------------
    // v2 (Phase 1.1): X25519 sealed-envelope open for person-root seeds.
    // Construction (validated against api/seed_envelope.py):
    //   shared = x25519(recipient_priv, ephemeral_pub)
    //   key    = HKDF-SHA256(shared, salt=32 zero bytes,
    //                        info="lemma.id/seed-envelope/v1"||ephPub||recipientPub)
    //   plain  = AES-256-GCM-open(key, nonce, ciphertext, aad=ephPub)
    // Wire: version(1) || ephemeral_pub(32) || nonce(12) || ciphertext(+tag)
    // ------------------------------------------------------------------
    const ENC_KEY_INFO = 'wallet-enc-key-v1';
    const SEAL_INFO = 'lemma.id/seed-envelope/v1';
    const ENVELOPE_VERSION = 1;
    let _nobleX25519 = null;

    async function loadNobleX25519() {
        if (_nobleX25519) return _nobleX25519;
        if (typeof window !== 'undefined' && window.x25519) {
            _nobleX25519 = window.x25519;
            return _nobleX25519;
        }
        const mod = await import('https://cdn.jsdelivr.net/npm/@noble/curves@1.6.0/ed25519/+esm');
        _nobleX25519 = mod.x25519;
        return _nobleX25519;
    }

    async function hkdfRaw(ikmBytes, saltBytes, infoBytes, length) {
        const keyMaterial = await crypto.subtle.importKey(
            'raw', ikmBytes, 'HKDF', false, ['deriveBits'],
        );
        const bits = await crypto.subtle.deriveBits(
            { name: 'HKDF', hash: 'SHA-256', salt: saltBytes, info: infoBytes },
            keyMaterial,
            length * 8,
        );
        return new Uint8Array(bits);
    }

    async function deriveEncryptionKeypair(walletSecretHex) {
        const ikm = hexToBytes(walletSecretHex);
        const seed = await hkdfSha256(ikm, WALLET_SIGNING_KEY_DOMAIN, ENC_KEY_INFO, 32);
        const x = await loadNobleX25519();
        const publicKey = x.getPublicKey(seed);
        return { privateKey: seed, publicKey };
    }

    // Fresh, ephemeral X25519 keypair (e.g. a new device proposing a transfer
    // target key). Not derived from any wallet secret.
    async function generateEncryptionKeypair() {
        const x = await loadNobleX25519();
        const privateKey = crypto.getRandomValues(new Uint8Array(32));
        const publicKey = x.getPublicKey(privateKey);
        return { privateKey, publicKey };
    }

    function _concatBytes(...chunks) {
        const total = chunks.reduce((n, c) => n + c.length, 0);
        const out = new Uint8Array(total);
        let off = 0;
        for (const c of chunks) { out.set(c, off); off += c.length; }
        return out;
    }

    async function sealEnvelope(recipientPubBytes, plaintextBytes) {
        const recipientPub = recipientPubBytes instanceof Uint8Array
            ? recipientPubBytes : new Uint8Array(recipientPubBytes);
        if (recipientPub.length !== 32) {
            throw new Error('recipient pubkey must be 32 bytes');
        }
        const x = await loadNobleX25519();
        const ephPriv = crypto.getRandomValues(new Uint8Array(32));
        const ephPub = x.getPublicKey(ephPriv);
        const shared = x.getSharedSecret(ephPriv, recipientPub);

        const info = _concatBytes(new TextEncoder().encode(SEAL_INFO), ephPub, recipientPub);
        const key = await hkdfRaw(shared, new Uint8Array(32), info, 32);

        const aesKey = await crypto.subtle.importKey('raw', key, { name: 'AES-GCM' }, false, ['encrypt']);
        const nonce = crypto.getRandomValues(new Uint8Array(12));
        const ct = new Uint8Array(await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv: nonce, additionalData: ephPub },
            aesKey,
            plaintextBytes,
        ));
        return _concatBytes(new Uint8Array([ENVELOPE_VERSION]), ephPub, nonce, ct);
    }

    async function openSealedEnvelope(privateKeyBytes, blobBytes) {
        const blob = blobBytes instanceof Uint8Array ? blobBytes : new Uint8Array(blobBytes);
        if (!blob.length || blob[0] !== ENVELOPE_VERSION) {
            throw new Error('unsupported envelope version');
        }
        if (blob.length < 1 + 32 + 12 + 16) {
            throw new Error('envelope too short');
        }
        const ephPub = blob.subarray(1, 33);
        const nonce = blob.subarray(33, 45);
        const ciphertext = blob.subarray(45);

        const x = await loadNobleX25519();
        const recipientPub = x.getPublicKey(privateKeyBytes);
        const shared = x.getSharedSecret(privateKeyBytes, ephPub);

        const info = _concatBytes(new TextEncoder().encode(SEAL_INFO), ephPub, recipientPub);
        const key = await hkdfRaw(shared, new Uint8Array(32), info, 32);

        const aesKey = await crypto.subtle.importKey('raw', key, { name: 'AES-GCM' }, false, ['decrypt']);
        const plain = await crypto.subtle.decrypt(
            { name: 'AES-GCM', iv: nonce, additionalData: ephPub },
            aesKey,
            ciphertext,
        );
        return new Uint8Array(plain);
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
        deriveEncryptionKeypair,
        generateEncryptionKeypair,
        sealEnvelope,
        openSealedEnvelope,
    };

    if (typeof window !== 'undefined') {
        window.LemmaKeys = LemmaKeys;
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = LemmaKeys;
    }
})();
