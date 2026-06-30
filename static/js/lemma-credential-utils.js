/**
 * Lemma Credential Utilities
 *
 * Standardizes credential claim extraction and platform identity checks.
 * Platform operators use the same lemma.id identity flow as all users;
 * operator status is an additional lemma.id-scoped permission proof.
 */

(function() {
'use strict';

if (typeof window !== 'undefined' && window.LemmaCredentialUtils) {
    return;
}

const ADMIN_PERMISSIONS = [
    'admin_access',
    'super_admin',
    'admin',
    'superadmin',
    'site_admin',
    'platform_admin',
];

const PLATFORM_SITE_CANONICAL = 'lemma.id';
const PLATFORM_SITE_ALIASES = [
    'lemma.id',
    'lemma_platform',
    'lemma-platform',
    'www.lemma.id',
];
const LEMMA_SITE_IDS = [...PLATFORM_SITE_ALIASES];

function getCredentialClaims(credential) {
    if (!credential) return {};
    return credential.claims || credential.credentialSubject || {};
}

function normalizeSiteLabel(raw) {
    return String(raw || '').trim().toLowerCase().replace(/^www\./, '').split(':')[0];
}

function isInternalSiteIdentifier(value) {
    return normalizeSiteLabel(value).startsWith('site_');
}

function canonicalPlatformSite(raw) {
    const normalized = normalizeSiteLabel(raw);
    if (!normalized) return '';
    if (PLATFORM_SITE_ALIASES.includes(normalized)) {
        return PLATFORM_SITE_CANONICAL;
    }
    return normalized;
}

function getCredentialSiteBinding(credential) {
    const claims = getCredentialClaims(credential);
    const candidates = [
        claims.siteDomain,
        claims.site_domain,
        claims.siteId,
        claims.site_id,
        claims.site,
    ];
    for (const value of candidates) {
        if (value == null || value === '') continue;
        if (isInternalSiteIdentifier(value)) continue;
        return canonicalPlatformSite(value);
    }
    return '';
}

function isPlatformSiteBinding(site) {
    const normalized = canonicalPlatformSite(site);
    return !normalized || normalized === PLATFORM_SITE_CANONICAL;
}

function isIsHumanCredential(credential) {
    if (!credential || typeof credential !== 'object') return false;
    const claims = getCredentialClaims(credential);
    if (claims.isHuman === true || String(claims.isHuman).toLowerCase() === 'true') {
        return true;
    }
    const id = String(credential.id || '');
    return id.startsWith('ishuman_master_') || id.startsWith('ishuman_site_');
}

function hasSiteSigningPubkey(credential) {
    const claims = getCredentialClaims(credential);
    return !!(claims.site_signing_pubkey || claims.siteSigningPubkey);
}

function isCompleteLemmaIdCredential(credential) {
    if (!isIsHumanCredential(credential)) return false;
    const id = String(credential?.id || '');
    if (id.startsWith('ishuman_master_')) return true;
    const site = getCredentialSiteBinding(credential);
    if (!site) return true;
    if (site === PLATFORM_SITE_CANONICAL) {
        return !hasSiteSigningPubkey(credential) || hasSiteSigningPubkey(credential);
    }
    return false;
}

function isPlatformPermissionCredential(credential) {
    const claims = getCredentialClaims(credential);
    const packageType = String(credential?.packageType || claims.packageType || claims.type || '').toLowerCase();
    const hasAccessClaims = !!(
        claims.permissionId
        || claims.permission_level
        || claims.permission_id
        || claims.accountType
        || claims.account_type
    );
    const isHumanOnPlatform = isIsHumanCredential(credential) && isPlatformSiteBinding(getCredentialSiteBinding(credential));
    return isPlatformSiteBinding(getCredentialSiteBinding(credential))
        && (packageType === 'permission' || hasAccessClaims || isHumanOnPlatform || !getCredentialSiteBinding(credential));
}

function isPlatformOperatorCredential(credential) {
    if (!isPlatformPermissionCredential(credential)) return false;
    if (isCredentialExpired(credential)) return false;
    const claims = getCredentialClaims(credential);
    return checkAdminPermission(claims) && isPlatformSiteBinding(getCredentialSiteBinding(credential));
}

function normalizeCredentialClaims(credential) {
    if (!credential) return null;

    const claims = getCredentialClaims(credential);
    const siteBinding = getCredentialSiteBinding(credential);

    return {
        siteId: siteBinding,
        permissionId: claims.permissionId || claims.permission_level ||
                     claims.permission_id || '',
        permissions: claims.permissions || '',
        type: claims.type || credential.type || '',
        email: claims.email || '',
        accountType: claims.accountType || claims.account_type || 'customer',
        expiresAt: getExpirationTimestamp(credential),
        issuedAt: getIssuanceTimestamp(credential),
        isExpired: isCredentialExpired(credential),
        isAdmin: checkAdminPermission(claims),
        isLemmaSite: isPlatformSiteBinding(siteBinding),
        isHuman: isIsHumanCredential(credential),
        isCompleteLemmaId: isCompleteLemmaIdCredential(credential),
        isPlatformOperator: isPlatformOperatorCredential(credential),
        _raw: claims,
    };
}

function getExpirationTimestamp(credential) {
    if (!credential) return null;

    const claims = getCredentialClaims(credential);
    const raw = credential.expiresAt ||
                credential.expirationDate ||
                credential.expires_at ||
                claims.expiresAt ||
                claims.expirationDate ||
                claims.expires_at;

    if (!raw) return null;
    return normalizeTimestamp(raw);
}

function getIssuanceTimestamp(credential) {
    if (!credential) return null;

    const claims = getCredentialClaims(credential);
    const raw = credential.issuedAt ||
                credential.issuanceDate ||
                credential.issued_at ||
                claims.issuedAt ||
                claims.issuanceDate ||
                claims.issued_at;

    if (!raw) return null;
    return normalizeTimestamp(raw);
}

function normalizeTimestamp(raw) {
    if (!raw) return null;

    if (typeof raw === 'string') {
        const parsed = new Date(raw).getTime();
        return Number.isNaN(parsed) ? null : parsed;
    }

    if (typeof raw === 'number') {
        if (raw < 4102444800) {
            return raw * 1000;
        }
        return raw;
    }

    return null;
}

function isCredentialExpired(credential) {
    const expiry = getExpirationTimestamp(credential);
    if (!expiry) return false;
    return expiry < Date.now();
}

function getTimeRemaining(credential) {
    const expiry = getExpirationTimestamp(credential);
    if (!expiry) return null;
    return expiry - Date.now();
}

function checkAdminPermission(claims) {
    if (!claims) return false;

    const permId = (claims.permissionId || claims.permission_level || claims.permission_id || '').toLowerCase();
    if (ADMIN_PERMISSIONS.includes(permId)) {
        return true;
    }

    const accountType = String(claims.accountType || claims.account_type || '').toLowerCase();
    return accountType === 'admin';
}

function checkIsLemmaSite(claims) {
    if (!claims) return false;
    const site = claims.siteId || claims.site || claims.site_id ||
                 claims.siteDomain || claims.site_domain || '';
    return isPlatformSiteBinding(site);
}

function hasPermission(credential, permission) {
    const normalized = normalizeCredentialClaims(credential);
    if (!normalized) return false;

    if (normalized.permissionId.toLowerCase() === permission.toLowerCase()) {
        return true;
    }

    if (normalized.permissions) {
        const perms = normalized.permissions.split(',').map((p) => p.trim().toLowerCase());
        if (perms.includes(permission.toLowerCase())) {
            return true;
        }
    }

    return false;
}

function selectBestCredentials(credentials, options = {}) {
    if (!Array.isArray(credentials)) return [];

    const {
        filterExpired = true,
        siteId = null,
        requireAdmin = false,
        platformOnly = false,
    } = options;

    let filtered = credentials.filter((cred) => {
        if (filterExpired && isCredentialExpired(cred)) {
            return false;
        }

        const normalized = normalizeCredentialClaims(cred);
        if (platformOnly && !normalized.isLemmaSite) {
            return false;
        }

        if (siteId) {
            const target = canonicalPlatformSite(siteId);
            const credSite = canonicalPlatformSite(normalized.siteId);
            if (credSite !== target && !isPlatformSiteBinding(normalized.siteId)) {
                return false;
            }
        }

        if (requireAdmin && !normalized.isAdmin) {
            return false;
        }

        return true;
    });

    filtered.sort((a, b) => {
        const aExp = getExpirationTimestamp(a) || Infinity;
        const bExp = getExpirationTimestamp(b) || Infinity;
        return bExp - aExp;
    });

    return filtered;
}

function selectPlatformCredentials(credentials, options = {}) {
    return selectBestCredentials(credentials, {
        ...options,
        platformOnly: true,
        siteId: PLATFORM_SITE_CANONICAL,
    });
}

function getBestCredential(credentials, siteId = null) {
    const valid = selectBestCredentials(credentials, { siteId });
    return valid.length > 0 ? valid[0] : null;
}

function summarizePlatformCredentials(credentials) {
    const list = Array.isArray(credentials) ? credentials : [];
    return {
        total: list.length,
        completeLemmaId: list.some((cred) => isCompleteLemmaIdCredential(cred)),
        operatorProofs: list.filter((cred) => isPlatformOperatorCredential(cred)).length,
        platformPermissions: selectPlatformCredentials(list).length,
    };
}

async function assessLemmaPlatformIdentity(wallet) {
    const result = {
        unlocked: false,
        completeLemmaId: false,
        hasOperatorProof: false,
        isOperator: false,
        credentialSummary: { total: 0, completeLemmaId: false, operatorProofs: 0, platformPermissions: 0 },
    };

    if (!wallet) return result;

    await wallet.init();
    result.unlocked = !!(wallet.isUnlocked && wallet.isUnlocked());

    let credentials = [];
    if (result.unlocked && typeof wallet.getCredentials === 'function') {
        try {
            credentials = await wallet.getCredentials();
        } catch (_) {
            credentials = [];
        }
    }

    result.credentialSummary = summarizePlatformCredentials(credentials);
    result.completeLemmaId = result.credentialSummary.completeLemmaId;
    result.hasOperatorProof = result.credentialSummary.operatorProofs > 0;

    if (result.unlocked && !result.completeLemmaId) {
        try {
            if (typeof wallet.findIsHumanMasterCredential === 'function') {
                const master = await wallet.findIsHumanMasterCredential();
                if (master) result.completeLemmaId = true;
            }
            if (!result.completeLemmaId && typeof wallet.findIsHumanSiteCredential === 'function') {
                const siteProof = await wallet.findIsHumanSiteCredential(PLATFORM_SITE_CANONICAL);
                if (siteProof) result.completeLemmaId = true;
            }
            if (!result.completeLemmaId && typeof wallet.hasIsHumanMasterInCache === 'function') {
                result.completeLemmaId = await wallet.hasIsHumanMasterInCache();
            }
        } catch (_) {
            /* wallet lookup errors should not throw through assess */
        }
    }

    result.isOperator = result.unlocked && result.completeLemmaId && result.hasOperatorProof;
    return result;
}

function debugCredential(credential, label = 'Credential') {
    const normalized = normalizeCredentialClaims(credential);
    console.log(`🔍 ${label}:`, {
        id: credential?.id,
        siteId: normalized?.siteId,
        permissionId: normalized?.permissionId,
        permissions: normalized?.permissions,
        type: normalized?.type,
        isExpired: normalized?.isExpired,
        isAdmin: normalized?.isAdmin,
        isLemmaSite: normalized?.isLemmaSite,
        isCompleteLemmaId: normalized?.isCompleteLemmaId,
        isPlatformOperator: normalized?.isPlatformOperator,
        expiresAt: normalized?.expiresAt ? new Date(normalized.expiresAt).toISOString() : null,
    });
    return normalized;
}

const LemmaCredentialUtils = {
    normalizeCredentialClaims,
    getCredentialClaims,
    getCredentialSiteBinding,
    canonicalPlatformSite,
    isPlatformSiteBinding,
    isInternalSiteIdentifier,
    isIsHumanCredential,
    isCompleteLemmaIdCredential,
    isPlatformPermissionCredential,
    isPlatformOperatorCredential,
    getExpirationTimestamp,
    getIssuanceTimestamp,
    normalizeTimestamp,
    isCredentialExpired,
    getTimeRemaining,
    checkAdminPermission,
    checkIsLemmaSite,
    hasPermission,
    selectBestCredentials,
    selectPlatformCredentials,
    getBestCredential,
    summarizePlatformCredentials,
    assessLemmaPlatformIdentity,
    debugCredential,
    ADMIN_PERMISSIONS,
    LEMMA_SITE_IDS,
    PLATFORM_SITE_CANONICAL,
    PLATFORM_SITE_ALIASES,
};

if (typeof window !== 'undefined') {
    window.LemmaCredentialUtils = LemmaCredentialUtils;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaCredentialUtils;
}

})();
