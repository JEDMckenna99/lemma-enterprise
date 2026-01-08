/**
 * Lemma IAM SDK - Wallet-First Identity and Access Management
 * 
 * ARCHITECTURE:
 * - PRIMARY: Wallet-first authentication (decentralized, offline-capable)
 * - FALLBACK: OAuth flow for API authorization (centralized, for server-to-server)
 * 
 * Wallet-first means:
 * - User's credentials stored in browser wallet (encrypted with passkey)
 * - Verification happens locally (no server call needed)
 * - Lemma.id only contacted for issuance and revocation
 * 
 * OAuth is used for:
 * - Server-to-server API access
 * - When the site needs to call Lemma APIs on user's behalf
 */

class LemmaIAM {
    constructor(config) {
        this.apiKey = config.apiKey;
        this.siteId = config.siteId;
        this.baseUrl = config.baseUrl || 'https://lemma.id';
        this.clientId = config.clientId;
        this.redirectUri = config.redirectUri;
        this.debug = config.debug || false;
        
        // Wallet reference
        this.wallet = null;
        this.walletReady = false;
        
        // Initialize wallet
        this._initWallet();
    }

    // ============================================
    // WALLET INITIALIZATION
    // ============================================

    async _initWallet() {
        try {
            // Wait for global wallet if it exists
            let attempts = 0;
            while (!window.globalLemmaWallet && attempts < 20) {
                await new Promise(r => setTimeout(r, 100));
                attempts++;
            }
            
            this.wallet = window.globalLemmaWallet;
            if (this.wallet) {
                await this.wallet.init();
                this.walletReady = true;
                this.log('✅ Wallet initialized');
            } else {
                this.log('⚠️ No wallet found - OAuth-only mode');
            }
        } catch (error) {
            this.log('Wallet init failed, OAuth-only mode:', error);
        }
    }

    async ensureWallet() {
        if (!this.walletReady) {
            await this._initWallet();
        }
        return this.wallet;
    }

    // ============================================
    // PRIMARY: WALLET-FIRST AUTHENTICATION
    // ============================================

    /**
     * Sign in using wallet (preferred method)
     * 1. Check if wallet has permission for this site
     * 2. If yes, verify locally and authenticate
     * 3. If no, request permission from Lemma
     * 
     * @returns {Promise<{success: boolean, user: object, method: string}>}
     */
    async signIn() {
        this.log('🔐 Starting wallet-first sign in...');
        
        const wallet = await this.ensureWallet();
        if (!wallet) {
            this.log('No wallet - falling back to OAuth');
            return this.signInWithOAuth();
        }
        
        try {
            // Check if wallet is unlocked
            const info = await wallet.getWalletInfo();
            
            if (!info.isUnlocked) {
                this.log('Wallet locked, requesting unlock...');
                const unlocked = await wallet.unlock();
                if (!unlocked) {
                    return { success: false, error: 'Wallet unlock cancelled' };
                }
            }
            
            // Check for existing permission for this site
            const existingPermission = await this._getExistingPermission();
            
            if (existingPermission) {
                this.log('✅ Found existing permission, verifying locally...');
                return await this._authenticateWithPermission(existingPermission);
            }
            
            // No existing permission - request one
            this.log('No permission found, requesting from Lemma...');
            return await this._requestPermission();
            
        } catch (error) {
            this.log('Wallet auth failed:', error);
            return { success: false, error: error.message, method: 'wallet' };
        }
    }

    async _getExistingPermission() {
        try {
            const permissions = await this.wallet.getCredentials('permission');
            
            // Find permission for this site
            return permissions.find(p => {
                const claims = p.claims || p.credentialSubject || {};
                const siteId = claims.siteId || claims.site;
                return siteId === this.siteId;
            });
        } catch (e) {
            this.log('Error checking permissions:', e);
            return null;
        }
    }

    async _authenticateWithPermission(permission) {
        const startTime = performance.now();
        
        try {
            // Verify permission locally
            const isValid = await this._verifyPermissionLocally(permission);
            
            if (!isValid) {
                this.log('Permission invalid or revoked');
                // Remove invalid permission and request new one
                await this.wallet.removeCredential(permission.id);
                return await this._requestPermission();
            }
            
            const verificationTime = performance.now() - startTime;
            
            // Get user info from wallet session
            const session = await this.wallet.getSession();
            
            return {
                success: true,
                user: {
                    did: permission.subject || permission.credentialSubject?.id,
                    email: session?.email,
                    permissions: this._extractPermissions(permission)
                },
                permission: permission,
                method: 'wallet',
                verificationTime: verificationTime,
                offline: true  // No server call needed!
            };
            
        } catch (error) {
            this.log('Permission verification failed:', error);
            return { success: false, error: error.message, method: 'wallet' };
        }
    }

    async _verifyPermissionLocally(permission) {
        // Check expiration
        if (permission.expirationDate) {
            const expiry = typeof permission.expirationDate === 'number' 
                ? permission.expirationDate * 1000 
                : new Date(permission.expirationDate).getTime();
            
            if (Date.now() > expiry) {
                this.log('Permission expired');
                return false;
            }
        }
        
        // TODO: Check revocation against local bloom filter
        // For now, assume valid if not expired
        
        // TODO: Verify signature using issuer public key from wallet
        // This would use Web Crypto API
        
        return true;
    }

    async _requestPermission() {
        try {
            const walletId = this.wallet.session?.walletId || 'wallet_' + Date.now();
            
            // Request permission from Lemma
            const response = await fetch(`${this.baseUrl}/api/wallet-auth/issue`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    site_id: this.siteId,
                    wallet_id: walletId
                })
            });
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error || 'Failed to get permission');
            }
            
            // Store permission in wallet
            await this.wallet.storeCredential(result.permission_lemma);
            this.log('✅ Permission stored in wallet');
            
            return {
                success: true,
                user: {
                    did: result.user.id,
                    email: result.user.email,
                    isNew: result.user.isNew
                },
                permission: result.permission_lemma,
                method: 'wallet',
                offline: false  // Server was contacted for issuance
            };
            
        } catch (error) {
            this.log('Permission request failed:', error);
            throw error;
        }
    }

    _extractPermissions(permission) {
        const claims = permission.claims || permission.credentialSubject || {};
        const scope = claims.scope || claims.permissions || '';
        
        if (typeof scope === 'string') {
            return scope.split(',').map(s => s.trim()).filter(Boolean);
        }
        return Array.isArray(scope) ? scope : [];
    }

    // ============================================
    // FALLBACK: OAUTH FLOW (for API authorization)
    // ============================================

    /**
     * Sign in with OAuth (fallback, or for API access)
     * Use this when:
     * - Wallet is not available
     * - You need server-to-server API access
     * - Site requires traditional OAuth tokens
     */
    signInWithOAuth(options = {}) {
        const params = new URLSearchParams({
            client_id: this.clientId,
            redirect_uri: this.redirectUri,
            scope: options.scope || 'profile permissions',
            state: options.state || this._generateState(),
            response_type: 'code'
        });

        const authUrl = `${this.baseUrl}/oauth/authorize?${params.toString()}`;
        
        this.log('Redirecting to OAuth:', authUrl);
        
        if (typeof window !== 'undefined') {
            window.location.href = authUrl;
        }
        
        return authUrl;
    }

    /**
     * Handle OAuth callback - exchange code for tokens
     */
    async handleOAuthCallback(code, state) {
        try {
            const response = await fetch(`${this.baseUrl}/oauth/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    grant_type: 'authorization_code',
                    code: code,
                    client_id: this.clientId,
                    client_secret: this.clientSecret,
                })
            });

            const tokenData = await response.json();
            
            if (tokenData.access_token) {
                this.accessToken = tokenData.access_token;
                
                return {
                    success: true,
                    user: { did: tokenData.user_did },
                    accessToken: tokenData.access_token,
                    method: 'oauth'
                };
            }
            
            throw new Error(tokenData.error || 'Failed to obtain access token');
            
        } catch (error) {
            this.log('OAuth callback error:', error);
            return { success: false, error: error.message, method: 'oauth' };
        }
    }

    // ============================================
    // PERMISSION VERIFICATION
    // ============================================

    /**
     * Verify user has access to a resource
     * Tries local verification first, then server fallback
     */
    async verifyAccess(resource, action = 'read') {
        const startTime = performance.now();
        
        try {
            // Try wallet-first (local) verification
            if (this.walletReady) {
                const permission = await this._getExistingPermission();
                
                if (permission) {
                    const isValid = await this._verifyPermissionLocally(permission);
                    
                    if (isValid) {
                        const permissions = this._extractPermissions(permission);
                        const hasAccess = this._checkAccess(permissions, resource, action);
                        
                    return {
                            success: true,
                            hasAccess: hasAccess,
                            method: 'local',
                            verificationTime: performance.now() - startTime,
                            offline: true
                    };
                    }
                }
            }

            // Fallback to server verification
            return await this._verifyAccessServer(resource, action, startTime);
            
        } catch (error) {
            this.log('Access verification error:', error);
            return { 
                success: false, 
                hasAccess: false, 
                error: error.message,
                verificationTime: performance.now() - startTime
            };
        }
    }

    _checkAccess(permissions, resource, action) {
        // Check for wildcard
        if (permissions.includes('*:*') || permissions.includes('*')) {
            return true;
        }
        
        // Check specific permission
        const needed = `${resource}:${action}`;
        const resourceWildcard = `${resource}:*`;
        const actionWildcard = `*:${action}`;
        
        return permissions.some(p => 
            p === needed || 
            p === resourceWildcard || 
            p === actionWildcard ||
            p === resource  // Simple permission without action
        );
    }

    async _verifyAccessServer(resource, action, startTime) {
        if (!this.accessToken && !this.apiKey) {
            return {
                success: false, 
                hasAccess: false, 
                error: 'No authentication available' 
            };
        }
        
        const response = await fetch(`${this.baseUrl}/oauth/verify-access`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': this.accessToken ? `Bearer ${this.accessToken}` : '',
                'X-API-Key': this.apiKey || ''
            },
            body: JSON.stringify({
                site_id: this.siteId,
                resource: resource,
                action: action
            })
        });

        const result = await response.json();

        return {
            success: true,
            hasAccess: result.has_access,
            method: 'server',
            verificationTime: performance.now() - startTime,
            offline: false
        };
    }

    /**
     * Check if user has specific permission
     */
    async hasPermission(permission) {
        const existing = await this._getExistingPermission();
        if (!existing) return false;
        
        const permissions = this._extractPermissions(existing);
        return this._checkAccess(permissions, permission, '*');
    }

    // ============================================
    // MIDDLEWARE & FRAMEWORK INTEGRATION
    // ============================================

    /**
     * Express.js middleware - protect routes with permissions
     */
    requirePermission(resource, action = 'read') {
        return async (req, res, next) => {
            try {
                const accessResult = await this.verifyAccess(resource, action);
                
                if (!accessResult.hasAccess) {
                    return res.status(403).json({ 
                        error: 'Insufficient permissions',
                        required: { resource, action },
                        verificationTime: accessResult.verificationTime
                    });
                }

                req.lemmaVerification = accessResult;
                next();
                
            } catch (error) {
                return res.status(500).json({ 
                    error: 'Permission verification failed',
                    details: error.message 
                });
            }
        };
    }

    /**
     * React Hook for permission-based rendering
     */
    usePermission(resource, action = 'read') {
        const [state, setState] = React.useState({
            hasAccess: false,
            loading: true,
            verificationTime: null
        });

        React.useEffect(() => {
            this.verifyAccess(resource, action).then(result => {
                setState({
                    hasAccess: result.hasAccess,
                    loading: false,
                    verificationTime: result.verificationTime,
                    method: result.method
                });
            });
        }, [resource, action]);

        return state;
    }

    // ============================================
    // SIGN OUT
    // ============================================

    async signOut() {
        try {
            // Clear OAuth token
            this.accessToken = null;
            
            // Lock wallet (doesn't delete credentials)
            if (this.wallet) {
                await this.wallet.lock();
            }
            
            return { success: true };
        } catch (error) {
            return { success: false, error: error.message };
            }
    }

    // ============================================
    // UTILITIES
    // ============================================

    _generateState() {
        return Math.random().toString(36).substring(2, 15) + 
               Math.random().toString(36).substring(2, 15);
    }

    log(...args) {
        if (this.debug) {
            console.log('[LemmaIAM]', ...args);
        }
    }
}

// Export for different environments
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaIAM;
} else if (typeof window !== 'undefined') {
    window.LemmaIAM = LemmaIAM;
}

/**
 * Usage Examples:
 * 
 * // Initialize SDK
 * const lemma = new LemmaIAM({
 *     siteId: 'your_site_id',
 *     clientId: 'lemma_oauth_your_site_id',  // For OAuth fallback
 *     redirectUri: 'https://yoursite.com/auth/callback',
 *     debug: true
 * });
 * 
 * // WALLET-FIRST: Sign in (preferred)
 * const result = await lemma.signIn();
 * if (result.success) {
 *     console.log('Signed in:', result.user);
 *     console.log('Method:', result.method);  // 'wallet' or 'oauth'
 *     console.log('Offline:', result.offline);  // true if no server call needed
 * }
 * 
 * // Check permissions (local verification, ~1ms)
 * const access = await lemma.verifyAccess('/admin', 'read');
 * console.log('Has access:', access.hasAccess);
 * console.log('Verification time:', access.verificationTime, 'ms');
 * 
 * // React component
 * function AdminPanel() {
 *     const { hasAccess, loading, method } = lemma.usePermission('/admin', 'read');
 *     
 *     if (loading) return <div>Checking permissions...</div>;
 *     if (!hasAccess) return <div>Access denied</div>;
 *     
 *     return <div>Admin content ({method} verification)</div>;
 * }
 * 
 * // Express middleware
 * app.get('/admin/users', lemma.requirePermission('/admin/users', 'read'), (req, res) => {
 *     console.log('Verified in:', req.lemmaVerification.verificationTime, 'ms');
 *     res.json({ users: [...] });
 * });
 */
