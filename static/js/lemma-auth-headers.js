/**
 * Attach X-Lemma-Proof and optional X-Lemma-PoP for proof-required platform routes.
 */
(function initLemmaAuthHeaders(global) {
    'use strict';

    function parseScope(claims) {
        const raw = (claims && (claims.scope || claims.permissions || claims.permission)) || ['read', 'admin'];
        if (typeof raw === 'string') {
            return raw.split(/[,;]/).map(function(part) { return part.trim(); }).filter(Boolean);
        }
        if (Array.isArray(raw)) {
            return raw.map(function(item) { return String(item).trim(); }).filter(Boolean);
        }
        return ['read'];
    }

    function randomToken(size) {
        var bytes = new Uint8Array(size || 16);
        if (global.crypto && global.crypto.getRandomValues) {
            global.crypto.getRandomValues(bytes);
        } else {
            for (var i = 0; i < bytes.length; i += 1) {
                bytes[i] = Math.floor(Math.random() * 256);
            }
        }
        var binary = '';
        for (var j = 0; j < bytes.length; j += 1) {
            binary += String.fromCharCode(bytes[j]);
        }
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }

    function sha256Hex(text) {
        if (!global.crypto || !global.crypto.subtle) {
            return Promise.resolve('');
        }
        var encoder = new TextEncoder();
        return global.crypto.subtle.digest('SHA-256', encoder.encode(String(text || ''))).then(function(buffer) {
            return Array.from(new Uint8Array(buffer)).map(function(b) {
                return b.toString(16).padStart(2, '0');
            }).join('');
        });
    }

    global.buildLemmaProofFromCredential = function buildLemmaProofFromCredential(credential, options) {
        if (!credential || typeof credential !== 'object') {
            return null;
        }
        var claims = credential.claims || credential.credentialSubject || {};
        var subject = credential.subject || credential.sub || claims.subject || claims.sub;
        if (!subject) {
            return null;
        }
        var now = Math.floor(Date.now() / 1000);
        var rootProofId = String(credential.id || ('root_' + randomToken(12)));
        var rootGrantId = String(claims.root_grant_id || ('rgr_' + randomToken(12)));
        var aud = (options && options.aud)
            || claims.siteId
            || claims.site_id
            || (global.location && global.location.hostname)
            || 'lemma.id';
        var rootProof = {
            proof_id: rootProofId,
            parent_proof_id: null,
            root_type: 'permission_vc',
            root_grant_id: rootGrantId,
            subject_ppid: subject,
            scope: parseScope(claims),
            aud: aud,
            issued_at: now - 60,
            expires_at: now + (30 * 24 * 3600),
            issuer: credential.issuer,
            subject: subject,
            claims: claims,
            proof: credential.proof,
            id: rootProofId
        };
        return {
            version: 'authz_profile_v2',
            policy_version: 'authz_profile_v2',
            root_proof: rootProof,
            proof_id: rootProofId,
            root_grant_id: rootGrantId
        };
    };

    global.buildLemmaPopEnvelope = function buildLemmaPopEnvelope(method, path, bodyText, proofPayload) {
        var now = Math.floor(Date.now() / 1000);
        var proofId = String((proofPayload && proofPayload.proof_id) || '');
        return {
            nonce: randomToken(12),
            proof_id: proofId,
            iat: now,
            exp: now + 60,
            method: String(method || 'GET').toUpperCase(),
            path: String(path || '/'),
            body_hash: '',
            aud: (global.location && global.location.hostname) || 'lemma.id'
        };
    };

    global.attachLemmaProofHeaders = function attachLemmaProofHeaders(headers, requestContext) {
        var out = Object.assign({}, headers || {});
        var credential = global.lemmaCredentialForHeader
            || (typeof global.buildLemmaCredentialForHeader === 'function'
                ? global.buildLemmaCredentialForHeader(global.lemmaCredential)
                : global.lemmaCredential);
        var proof = global.buildLemmaProofFromCredential(credential, requestContext);
        if (proof) {
            out['X-Lemma-Proof'] = JSON.stringify(proof);
        }
        if (requestContext && requestContext.method && requestContext.path) {
            var pop = global.buildLemmaPopEnvelope(
                requestContext.method,
                requestContext.path,
                requestContext.body,
                proof
            );
            out['X-Lemma-PoP'] = JSON.stringify(pop);
        }
        return out;
    };

    global.attachLemmaProofHeadersAsync = function attachLemmaProofHeadersAsync(headers, requestContext) {
        var out = global.attachLemmaProofHeaders(headers, requestContext);
        var body = requestContext && requestContext.body != null ? String(requestContext.body) : '';
        if (!global.crypto || !global.crypto.subtle || !out['X-Lemma-PoP']) {
            return Promise.resolve(out);
        }
        return sha256Hex(body).then(function(bodyHash) {
            if (!bodyHash) {
                return out;
            }
            try {
                var pop = JSON.parse(out['X-Lemma-PoP']);
                pop.body_hash = bodyHash;
                out['X-Lemma-PoP'] = JSON.stringify(pop);
            } catch (_) {
                /* keep envelope without body hash */
            }
            return out;
        });
    };

    function installWrappers() {
        var priorGetHeaders = global.getLemmaAuthHeaders;
        if (typeof priorGetHeaders === 'function' && !priorGetHeaders.__lemmaProofWrapped) {
            global.getLemmaAuthHeaders = function getLemmaAuthHeaders(extraHeaders, requestContext) {
                var base = priorGetHeaders(extraHeaders);
                return global.attachLemmaProofHeaders(base, requestContext);
            };
            global.getLemmaAuthHeaders.__lemmaProofWrapped = true;
        }

        var priorGetHeadersAsync = global.getLemmaAuthHeadersAsync;
        if (typeof priorGetHeadersAsync === 'function' && !priorGetHeadersAsync.__lemmaProofWrapped) {
            global.getLemmaAuthHeadersAsync = async function getLemmaAuthHeadersAsync(extraHeaders, requestContext) {
                var base = await priorGetHeadersAsync(extraHeaders);
                return global.attachLemmaProofHeadersAsync(base, requestContext);
            };
            global.getLemmaAuthHeadersAsync.__lemmaProofWrapped = true;
        }
    }

    if (global.document && global.document.readyState === 'loading') {
        global.document.addEventListener('DOMContentLoaded', installWrappers);
    } else {
        installWrappers();
    }
}(window));
