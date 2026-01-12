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
    static VERSION = '2.0.0';
    
    constructor(config) {
        this.apiKey = config.apiKey;
        this.siteId = config.siteId;
        this.baseUrl = config.baseUrl || 'https://lemma.id';
        this.clientId = config.clientId;
        this.redirectUri = config.redirectUri;
        this.debug = config.debug || false;
        
        // Central wallet option - stores credentials in lemma.id wallet instead of locally
        // This ensures all user permissions are visible in the lemma.id/wallet page
        // DEFAULT: true - credentials stored via bridge so they appear at lemma.id/wallet
        this.useCentralWallet = config.useCentralWallet !== false;
        
        // Remote config (fetched from server - allows auto-updates)
        this.remoteConfig = null;
        this.configLoaded = false;
        
        // Wallet reference
        this.wallet = null;
        this.walletReady = false;
        
        // Initialize: fetch remote config, then wallet
        this._init();
    }
    
    // ============================================
    // REMOTE CONFIGURATION (Auto-Update Support)
    // ============================================
    
    async _init() {
        // Fetch remote config first (enables server-side feature flags)
        await this._loadRemoteConfig();
        
        // Then initialize wallet
        await this._initWallet();
    }
    
    /**
     * Load remote configuration from server
     * Allows pushing updates to all SDK instances without code changes
     */
    async _loadRemoteConfig() {
        try {
            const response = await fetch(
                `${this.baseUrl}/api/sdk/config?site_id=${encodeURIComponent(this.siteId)}&sdk_version=${LemmaIAM.VERSION}`,
                { method: 'GET', headers: { 'Accept': 'application/json' } }
            );
            
            if (response.ok) {
                const data = await response.json();
                this.remoteConfig = data.config;
                this.configLoaded = true;
                
                // Apply remote config settings
                this._applyRemoteConfig();
                
                this.log('📡 Remote config loaded:', this.remoteConfig?.version);
            }
        } catch (e) {
            // Config fetch failed - continue with defaults (offline-friendly)
            this.log('⚠️ Remote config unavailable, using defaults');
        }
    }
    
    /**
     * Apply remote configuration to SDK behavior
     */
    _applyRemoteConfig() {
        if (!this.remoteConfig) return;
        
        const { features, settings, announcements } = this.remoteConfig;
        
        // Apply feature flags
        if (features) {
            // Server can override useCentralWallet for all sites
            if (features.centralWallet !== undefined && !this.useCentralWallet) {
                // Only enable, don't disable if user explicitly set it
                // this.useCentralWallet = features.centralWallet;
            }
        }
        
        // Apply settings
        if (settings) {
            if (settings.debugMode !== undefined) {
                // Server can enable debug for troubleshooting
                this.debug = this.debug || settings.debugMode;
            }
        }
        
        // Show announcements (optional)
        if (announcements && announcements.length > 0 && this.debug) {
            announcements.forEach(a => {
                if (!this._hasSeenAnnouncement(a.id)) {
                    console.log(`📢 Lemma: ${a.message}`);
                    this._markAnnouncementSeen(a.id);
                }
            });
        }
    }
    
    _hasSeenAnnouncement(id) {
        try {
            const seen = JSON.parse(localStorage.getItem('lemma_announcements_seen') || '[]');
            return seen.includes(id);
        } catch { return false; }
    }
    
    _markAnnouncementSeen(id) {
        try {
            const seen = JSON.parse(localStorage.getItem('lemma_announcements_seen') || '[]');
            seen.push(id);
            localStorage.setItem('lemma_announcements_seen', JSON.stringify(seen));
        } catch {}
    }
    
    /**
     * Get current feature flags (from remote config)
     */
    getFeatures() {
        return this.remoteConfig?.features || {
            centralWallet: true,
            bridgeEnabled: true,
            offlineVerification: true
        };
    }
    
    /**
     * Check if a specific feature is enabled
     */
    isFeatureEnabled(featureName) {
        return this.getFeatures()[featureName] ?? false;
    }

    // ============================================
    // WALLET INITIALIZATION
    // ============================================

    async _initWallet() {
        try {
            // If useCentralWallet is enabled, use the cross-origin wallet bridge
            if (this.useCentralWallet) {
                this.log('🌉 Using central wallet bridge...');
                await this._initWalletBridge();
                return;
            }
            
            // Wait for global wallet if it exists (local wallet mode)
            let attempts = 0;
            while (!window.globalLemmaWallet && attempts < 20) {
                await new Promise(r => setTimeout(r, 100));
                attempts++;
            }
            
            this.wallet = window.globalLemmaWallet;
            if (this.wallet) {
                await this.wallet.init();
                this.walletReady = true;
                this.log('✅ Local wallet initialized');
            } else {
                this.log('⚠️ No local wallet found - trying bridge...');
                // Fallback to bridge if no local wallet
                await this._initWalletBridge();
            }
        } catch (error) {
            this.log('Wallet init failed:', error);
            // Try bridge as fallback
            await this._initWalletBridge();
        }
    }
    
    // ============================================
    // CROSS-ORIGIN WALLET BRIDGE
    // ============================================
    
    /**
     * Initialize the wallet bridge iframe for cross-origin storage
     * This allows storing credentials in the central lemma.id wallet
     * from any third-party site.
     */
    async _initWalletBridge() {
        return new Promise((resolve) => {
            // Check if bridge already exists
            if (this._bridgeIframe && this._bridgeReady) {
                this.walletReady = true;
                resolve(true);
                return;
            }
            
            // Create hidden iframe for wallet bridge
            this._bridgeIframe = document.createElement('iframe');
            this._bridgeIframe.src = `${this.baseUrl}/wallet/bridge`;
            this._bridgeIframe.style.cssText = 'position:absolute;width:0;height:0;border:0;visibility:hidden;';
            this._bridgeIframe.id = 'lemma-wallet-bridge';
            
            // Set up message listener
            this._bridgeCallbacks = {};
            this._bridgeReady = false;
            
            const messageHandler = (event) => {
                // Validate origin
                if (!event.origin.includes('lemma')) {
                    // Allow localhost for development
                    if (!event.origin.includes('localhost') && !event.origin.includes('127.0.0.1')) {
                        return;
                    }
                }
                
                const { type, requestId, ...data } = event.data || {};
                
                // Handle bridge ready notification
                if (type === 'WALLET_BRIDGE_READY') {
                    this._bridgeReady = true;
                    this.walletReady = true;
                    this.log('✅ Wallet bridge ready');
                    resolve(true);
                    return;
                }
                
                // Handle response to our requests
                if (type && type.endsWith('_response') && requestId && this._bridgeCallbacks[requestId]) {
                    this._bridgeCallbacks[requestId](data);
                    delete this._bridgeCallbacks[requestId];
                }
            };
            
            window.addEventListener('message', messageHandler);
            this._bridgeMessageHandler = messageHandler;
            
            // Add iframe to document
            document.body.appendChild(this._bridgeIframe);
            
            // Timeout after 5 seconds
            setTimeout(() => {
                if (!this._bridgeReady) {
                    this.log('⚠️ Wallet bridge timeout - falling back to local');
                    resolve(false);
                }
            }, 5000);
        });
    }
    
    /**
     * Send a message to the wallet bridge and wait for response
     */
    async _bridgeSend(type, payload = {}) {
        if (!this._bridgeIframe || !this._bridgeReady) {
            throw new Error('Wallet bridge not initialized');
        }
        
        return new Promise((resolve, reject) => {
            const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            
            // Set up callback
            this._bridgeCallbacks[requestId] = (response) => {
                if (response.success) {
                    resolve(response);
                } else {
                    reject(new Error(response.error || 'Bridge request failed'));
                }
            };
            
            // Send message to bridge
            this._bridgeIframe.contentWindow.postMessage({
                type,
                payload,
                requestId
            }, this.baseUrl);
            
            // Timeout after 10 seconds
            setTimeout(() => {
                if (this._bridgeCallbacks[requestId]) {
                    delete this._bridgeCallbacks[requestId];
                    reject(new Error('Bridge request timeout'));
                }
            }, 10000);
        });
    }
    
    /**
     * Store credential via bridge (for central wallet storage)
     */
    async _storeCredentialViaBridge(credential) {
        this.log('🌉 Storing credential via bridge...');
        const result = await this._bridgeSend('STORE_CREDENTIAL', { credential });
        this.log('✅ Credential stored in central wallet:', result.credentialId);
        return result;
    }
    
    /**
     * Get credentials via bridge (from central wallet)
     */
    async _getCredentialsViaBridge(type = null, siteId = null) {
        const result = await this._bridgeSend('GET_CREDENTIALS', { type, siteId });
        return result.credentials || [];
    }
    
    /**
     * Create a wallet proxy that uses the bridge
     * This allows the rest of the SDK to work transparently
     */
    _createBridgeWalletProxy() {
        const sdk = this;
        return {
            async storeCredential(credential) {
                return sdk._storeCredentialViaBridge(credential);
            },
            async getCredentials(type) {
                return sdk._getCredentialsViaBridge(type);
            },
            async removeCredential(credentialId) {
                return sdk._bridgeSend('REMOVE_CREDENTIAL', { credentialId });
            },
            async verifyCredential(credential) {
                return sdk._bridgeSend('VERIFY_CREDENTIAL', { credential });
            },
            async getWalletInfo() {
                return sdk._bridgeSend('WALLET_STATUS');
            },
            async unlock() {
                const result = await sdk._bridgeSend('WALLET_UNLOCK');
                return result.success;
            },
            async getSession() {
                return null; // Session managed separately
            },
            session: null
        };
    }

    async ensureWallet() {
        if (!this.walletReady) {
            await this._initWallet();
        }
        
        // If using bridge, return a proxy wallet
        if (this.useCentralWallet && this._bridgeReady) {
            return this._createBridgeWalletProxy();
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
        this.log(`   Mode: ${this.useCentralWallet ? 'Central Wallet (bridge)' : 'Local Wallet'}`);
        
        // Get the wallet (either local or bridge proxy)
        this.wallet = await this.ensureWallet();
        if (!this.wallet) {
            this.log('No wallet available - falling back to OAuth');
            return this.signInWithOAuth();
        }
        
        try {
            // Check if wallet is unlocked
            const info = await this.wallet.getWalletInfo();
            
            if (!info.isUnlocked) {
                this.log('Wallet locked, requesting unlock...');
                const unlocked = await this.wallet.unlock();
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
            const walletId = this.wallet?.session?.walletId || 'wallet_' + Date.now();
            
            // Request permission from Lemma API
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
            
            // Store permission in wallet (this.wallet is either local or bridge proxy)
            // The bridge proxy will store it in the central lemma.id wallet
            await this.wallet.storeCredential(result.permission_lemma);
            
            const storageType = this.useCentralWallet ? 'central wallet (via bridge)' : 'local wallet';
            this.log(`✅ Permission stored in ${storageType}`);
            
            return {
                success: true,
                user: {
                    did: result.user?.id || result.ppid,
                    email: result.user?.email,
                    isNew: result.user?.isNew || !result.user?.existing
                },
                permission: result.permission_lemma,
                method: 'wallet',
                centralWallet: this.useCentralWallet,
                offline: false  // Server was contacted for issuance
            };
            
        } catch (error) {
            this.log('Permission request failed:', error);
            throw error;
        }
    }
    
    /**
     * Check if we're using central wallet mode
     */
    isCentralWalletMode() {
        return this.useCentralWallet && this._bridgeReady;
    }
    
    /**
     * Get info about where credentials are stored
     */
    getStorageInfo() {
        if (this.useCentralWallet && this._bridgeReady) {
            return {
                mode: 'central',
                location: 'lemma.id wallet (via bridge)',
                viewAt: `${this.baseUrl}/wallet`
            };
        }
        return {
            mode: 'local', 
            location: 'This site\'s browser storage',
            viewAt: null
        };
    }
    
    /**
     * Handle callback after permission flow (kept for backwards compatibility)
     * With the bridge approach, this is no longer needed but kept for legacy support
     */
    async handleCentralWalletCallback() {
        // With the bridge approach, no callback handling is needed
        // The permission is stored directly via postMessage
        return {
            success: true,
            method: 'bridge',
            message: 'Using bridge mode - no callback needed'
        };
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
