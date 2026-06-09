/**
 * Phase 5 — PRF-derived keys and AES-GCM envelopes for Lemma wallet IndexedDB.
 * Loaded before lemma-wallet.js; exposes window.WalletAtRestCrypto.
 */
(function () {
    'use strict';

    const ENVELOPE_VERSION = 'enc_v1';
    const PRF_SALT_PREFIX = 'lemma:wallet:prf:v1:';
    const SENSITIVE_STORES = ['secrets', 'profiles', 'session', 'lemmas', 'ishuman_cache'];

    function isPrfSupported() {
        return typeof window !== 'undefined'
            && window.PublicKeyCredential !== undefined
            && typeof window.PublicKeyCredential === 'function';
    }

    async function buildPrfSaltBytes(walletId, rpId) {
        const material = `${PRF_SALT_PREFIX}${rpId || 'lemma.id'}:${walletId || 'unknown'}`;
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(material));
        return new Uint8Array(digest);
    }

    function bufferToBase64url(buffer) {
        const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    }

    function base64urlToBuffer(base64url) {
        const base64 = String(base64url || '').replace(/-/g, '+').replace(/_/g, '/');
        const padding = '='.repeat((4 - base64.length % 4) % 4);
        const binary = atob(base64 + padding);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }

    async function buildRegistrationPrfExtensions(walletId, rpId) {
        const salt = await buildPrfSaltBytes(walletId, rpId);
        return {
            prf: {
                eval: {
                    first: salt,
                },
            },
        };
    }

    async function buildAuthenticationPrfExtensions(walletId, rpId) {
        return buildRegistrationPrfExtensions(walletId, rpId);
    }

    function extractPrfBytes(credential) {
        if (!credential || typeof credential.getClientExtensionResults !== 'function') {
            return null;
        }
        const ext = credential.getClientExtensionResults() || {};
        const first = ext?.prf?.results?.first;
        if (!first) return null;
        if (first instanceof ArrayBuffer) return new Uint8Array(first);
        if (ArrayBuffer.isView(first)) return new Uint8Array(first.buffer, first.byteOffset, first.byteLength);
        return null;
    }

    async function importStorageKey(prfBytes) {
        if (!prfBytes || prfBytes.length < 32) {
            throw new Error('prf_output_invalid');
        }
        const raw = prfBytes.slice(0, 32);
        return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
    }

    function isEncryptedEnvelope(value) {
        return !!(value && typeof value === 'object' && value.__enc === ENVELOPE_VERSION && value.ciphertext);
    }

    async function encryptEnvelope(storageKey, storeName, recordId, plaintextObj) {
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const aad = new TextEncoder().encode(`${ENVELOPE_VERSION}:${storeName}:${recordId || ''}`);
        const plaintext = new TextEncoder().encode(JSON.stringify(plaintextObj));
        const ciphertext = await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv, additionalData: aad },
            storageKey,
            plaintext,
        );
        return {
            __enc: ENVELOPE_VERSION,
            store: storeName,
            id: recordId || null,
            iv: bufferToBase64url(iv),
            ciphertext: bufferToBase64url(ciphertext),
        };
    }

    async function decryptEnvelope(storageKey, envelope) {
        if (!isEncryptedEnvelope(envelope)) {
            throw new Error('envelope_invalid');
        }
        const iv = new Uint8Array(base64urlToBuffer(envelope.iv));
        const aad = new TextEncoder().encode(`${ENVELOPE_VERSION}:${envelope.store}:${envelope.id || ''}`);
        const ciphertext = base64urlToBuffer(envelope.ciphertext);
        const plaintext = await crypto.subtle.decrypt(
            { name: 'AES-GCM', iv, additionalData: aad },
            storageKey,
            ciphertext,
        );
        return JSON.parse(new TextDecoder().decode(plaintext));
    }

    // -----------------------------------------------------------------------
    // Device wrap key — protects the 24h unlock bundle written to localStorage.
    //
    // The daily-unlock bundle has to persist the wallet secret + at-rest key so
    // the user only does ONE passkey per day. Writing those to localStorage in
    // cleartext defeats the at-rest encryption for that window. Instead we wrap
    // the sensitive payload with a NON-EXTRACTABLE AES-GCM CryptoKey kept in a
    // dedicated IndexedDB: JS can use it to encrypt/decrypt but can never read
    // its bytes, so a full storage dump (XSS, extension, disk) yields ciphertext
    // — not the secret.
    // -----------------------------------------------------------------------

    const WRAP_DB_NAME = 'LemmaWalletWrap';
    const WRAP_DB_VERSION = 1;
    const WRAP_STORE = 'keys';
    const WRAP_KEY_ID = 'device-unlock-wrap:v1';
    const WRAP_ENVELOPE_VERSION = 'wrap_v1';

    function _openWrapDb() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open(WRAP_DB_NAME, WRAP_DB_VERSION);
            req.onupgradeneeded = () => {
                const db = req.result;
                if (!db.objectStoreNames.contains(WRAP_STORE)) {
                    db.createObjectStore(WRAP_STORE);
                }
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    function _idbGet(db, store, key) {
        return new Promise((resolve, reject) => {
            const tx = db.transaction(store, 'readonly');
            const req = tx.objectStore(store).get(key);
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    function _idbPut(db, store, key, value) {
        return new Promise((resolve, reject) => {
            const tx = db.transaction(store, 'readwrite');
            const req = tx.objectStore(store).put(value, key);
            req.onsuccess = () => resolve(true);
            req.onerror = () => reject(req.error);
        });
    }

    async function getDeviceWrapKey() {
        if (typeof indexedDB === 'undefined' || !window.crypto?.subtle) return null;
        let db;
        try {
            db = await _openWrapDb();
        } catch {
            return null;
        }
        try {
            const existing = await _idbGet(db, WRAP_STORE, WRAP_KEY_ID);
            if (existing instanceof CryptoKey) return existing;
            // extractable:false => the raw key never leaves the browser's secure
            // key store; structured-clone persists the handle, not the material.
            const key = await crypto.subtle.generateKey(
                { name: 'AES-GCM', length: 256 },
                false,
                ['encrypt', 'decrypt'],
            );
            await _idbPut(db, WRAP_STORE, WRAP_KEY_ID, key);
            return key;
        } catch {
            return null;
        } finally {
            try { db.close(); } catch { /* ignore */ }
        }
    }

    async function wrapBundle(plaintextObj) {
        const key = await getDeviceWrapKey();
        if (!key) return null;
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const data = new TextEncoder().encode(JSON.stringify(plaintextObj));
        const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, data);
        return {
            __wrap: WRAP_ENVELOPE_VERSION,
            iv: bufferToBase64url(iv),
            ciphertext: bufferToBase64url(ciphertext),
        };
    }

    async function unwrapBundle(envelope) {
        if (!envelope || envelope.__wrap !== WRAP_ENVELOPE_VERSION) return null;
        const key = await getDeviceWrapKey();
        if (!key) return null;
        const iv = new Uint8Array(base64urlToBuffer(envelope.iv));
        const ciphertext = base64urlToBuffer(envelope.ciphertext);
        const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
        return JSON.parse(new TextDecoder().decode(plaintext));
    }

    window.WalletAtRestCrypto = {
        ENVELOPE_VERSION,
        PRF_SALT_PREFIX,
        SENSITIVE_STORES,
        isPrfSupported,
        buildPrfSaltBytes,
        buildRegistrationPrfExtensions,
        buildAuthenticationPrfExtensions,
        extractPrfBytes,
        importStorageKey,
        isEncryptedEnvelope,
        encryptEnvelope,
        decryptEnvelope,
        bufferToBase64url,
        base64urlToBuffer,
        getDeviceWrapKey,
        wrapBundle,
        unwrapBundle,
    };
})();
