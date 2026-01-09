/**
 * Lemma Credential Utilities
 * 
 * Standardizes credential claim extraction across all credential formats.
 * Handles the various ways credentials can be structured.
 */

(function() {
'use strict';

// Guard against double-loading
if (typeof window !== 'undefined' && window.LemmaCredentialUtils) {
    return;
}

// ============================================
// CONSTANTS
// ============================================

const ADMIN_PERMISSIONS = [
    'admin_access', 
    'super_admin', 
    'admin', 
    'superadmin', 
    'site_admin',
    'platform_admin'
];

const LEMMA_SITE_IDS = [
    'lemma.id',
    'lemma_platform',
    'lemma-platform'
];

// ============================================
// CREDENTIAL NORMALIZATION
// ============================================

/**
 * Normalize credential claims to a standard format
 * Handles all known credential structures
 */
function normalizeCredentialClaims(credential) {
    if (!credential) return null;
    
    const claims = credential.claims || credential.credentialSubject || {};
    
    return {
        // Site identification (multiple possible field names)
        siteId: claims.siteId || claims.site || claims.site_id || 
                claims.siteDomain || claims.site_domain || '',
        
        // Permission identification (multiple possible field names)
        permissionId: claims.permissionId || claims.permission_level || 
                     claims.permission_id || '',
        
        // Permissions string (e.g., "read,write,access")
        permissions: claims.permissions || '',
        
        // Type field (fallback for permission identification)
        type: claims.type || credential.type || '',
        
        // User info
        email: claims.email || '',
        accountType: claims.accountType || claims.account_type || 'customer',
        
        // Timestamps
        expiresAt: getExpirationTimestamp(credential),
        issuedAt: getIssuanceTimestamp(credential),
        
        // Computed properties
        isExpired: isCredentialExpired(credential),
        isAdmin: checkAdminPermission(claims),
        isLemmaSite: checkIsLemmaSite(claims),
        
        // Original claims for reference
        _raw: claims
    };
}

// ============================================
// EXPIRATION HANDLING
// ============================================

/**
 * Get expiration timestamp in milliseconds
 * Handles: ISO strings, Unix seconds, Unix milliseconds
 */
function getExpirationTimestamp(credential) {
    if (!credential) return null;
    
    const claims = credential.claims || credential.credentialSubject || {};
    
    // Check all possible field names
    const raw = credential.expiresAt || 
                credential.expirationDate || 
                credential.expires_at ||
                claims.expiresAt ||
                claims.expirationDate ||
                claims.expires_at;
    
    if (!raw) return null;
    
    return normalizeTimestamp(raw);
}

/**
 * Get issuance timestamp in milliseconds
 */
function getIssuanceTimestamp(credential) {
    if (!credential) return null;
    
    const claims = credential.claims || credential.credentialSubject || {};
    
    const raw = credential.issuedAt || 
                credential.issuanceDate || 
                credential.issued_at ||
                claims.issuedAt ||
                claims.issuanceDate ||
                claims.issued_at;
    
    if (!raw) return null;
    
    return normalizeTimestamp(raw);
}

/**
 * Normalize timestamp to milliseconds
 * Handles ISO strings, Unix seconds, Unix milliseconds
 */
function normalizeTimestamp(raw) {
    if (!raw) return null;
    
    // ISO string
    if (typeof raw === 'string') {
        const parsed = new Date(raw).getTime();
        return isNaN(parsed) ? null : parsed;
    }
    
    // Number - determine if seconds or milliseconds
    if (typeof raw === 'number') {
        // If less than year 2100 in seconds (4102444800), it's probably seconds
        // This handles timestamps like 1767908306 (seconds) vs 1767908306000 (ms)
        if (raw < 4102444800) {
            return raw * 1000;
        }
        return raw;
    }
    
    return null;
}

/**
 * Check if credential is expired
 */
function isCredentialExpired(credential) {
    const expiry = getExpirationTimestamp(credential);
    if (!expiry) return false; // No expiry = never expires
    return expiry < Date.now();
}

/**
 * Get time remaining until expiration (in ms)
 * Returns null if no expiry, negative if expired
 */
function getTimeRemaining(credential) {
    const expiry = getExpirationTimestamp(credential);
    if (!expiry) return null;
    return expiry - Date.now();
}

// ============================================
// PERMISSION CHECKING
// ============================================

/**
 * Check if claims indicate admin permission
 * Uses strict matching - no loose .includes() checks
 */
function checkAdminPermission(claims) {
    if (!claims) return false;
    
    const permId = (claims.permissionId || claims.permission_level || claims.permission_id || '').toLowerCase();
    
    // Check explicit admin permissions
    if (ADMIN_PERMISSIONS.includes(permId)) {
        return true;
    }
    
    // Check account type
    if (claims.accountType === 'admin' || claims.account_type === 'admin') {
        return true;
    }
    
    return false;
}

/**
 * Check if credential is for lemma.id platform
 */
function checkIsLemmaSite(claims) {
    if (!claims) return false;
    
    const siteId = (claims.siteId || claims.site || claims.site_id || 
                   claims.siteDomain || claims.site_domain || '').toLowerCase();
    
    return LEMMA_SITE_IDS.some(id => siteId === id || siteId.includes('lemma'));
}

/**
 * Check if credential has specific permission
 */
function hasPermission(credential, permission) {
    const normalized = normalizeCredentialClaims(credential);
    if (!normalized) return false;
    
    // Check permissionId
    if (normalized.permissionId.toLowerCase() === permission.toLowerCase()) {
        return true;
    }
    
    // Check permissions string (e.g., "read,write,access")
    if (normalized.permissions) {
        const perms = normalized.permissions.split(',').map(p => p.trim().toLowerCase());
        if (perms.includes(permission.toLowerCase())) {
            return true;
        }
    }
    
    return false;
}

// ============================================
// CREDENTIAL SELECTION
// ============================================

/**
 * Filter and sort credentials, returning valid ones
 * Filters out expired, sorts by expiration (longest-lived first)
 */
function selectBestCredentials(credentials, options = {}) {
    if (!Array.isArray(credentials)) return [];
    
    const {
        filterExpired = true,
        siteId = null,
        requireAdmin = false
    } = options;
    
    let filtered = credentials.filter(cred => {
        // Filter expired
        if (filterExpired && isCredentialExpired(cred)) {
            return false;
        }
        
        const normalized = normalizeCredentialClaims(cred);
        
        // Filter by site
        if (siteId) {
            const credSiteId = normalized.siteId.toLowerCase();
            const targetSiteId = siteId.toLowerCase();
            if (credSiteId !== targetSiteId && !LEMMA_SITE_IDS.includes(credSiteId)) {
                return false;
            }
        }
        
        // Filter admin only
        if (requireAdmin && !normalized.isAdmin) {
            return false;
        }
        
        return true;
    });
    
    // Sort by expiration (longest-lived first)
    filtered.sort((a, b) => {
        const aExp = getExpirationTimestamp(a) || Infinity;
        const bExp = getExpirationTimestamp(b) || Infinity;
        return bExp - aExp;
    });
    
    return filtered;
}

/**
 * Get the best credential for a site
 */
function getBestCredential(credentials, siteId = null) {
    const valid = selectBestCredentials(credentials, { siteId });
    return valid.length > 0 ? valid[0] : null;
}

// ============================================
// DEBUG HELPERS
// ============================================

/**
 * Log credential details for debugging
 */
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
        expiresAt: normalized?.expiresAt ? new Date(normalized.expiresAt).toISOString() : null
    });
    return normalized;
}

// ============================================
// EXPORTS
// ============================================

const LemmaCredentialUtils = {
    // Normalization
    normalizeCredentialClaims,
    
    // Timestamps
    getExpirationTimestamp,
    getIssuanceTimestamp,
    normalizeTimestamp,
    isCredentialExpired,
    getTimeRemaining,
    
    // Permissions
    checkAdminPermission,
    checkIsLemmaSite,
    hasPermission,
    
    // Selection
    selectBestCredentials,
    getBestCredential,
    
    // Debug
    debugCredential,
    
    // Constants
    ADMIN_PERMISSIONS,
    LEMMA_SITE_IDS
};

if (typeof window !== 'undefined') {
    window.LemmaCredentialUtils = LemmaCredentialUtils;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaCredentialUtils;
}

})();
