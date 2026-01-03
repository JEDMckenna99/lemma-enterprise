/**
 * Lemma IAM User Management SDK
 * ============================
 * 
 * Complete user management interface that customer sites can integrate
 * into their own platforms or use the hosted version on lemma.id
 * 
 * Features:
 * - Add/remove users from site
 * - Issue permission lemmas to user wallets (client-side storage)
 * - Manage roles and permissions
 * - View user access status
 * - Revoke permissions
 * 
 * Usage:
 * const userManager = new LemmaIAMUserManager({
 *   apiKey: 'your-site-api-key',
 *   siteId: 'your-site-id',
 *   apiBase: 'https://lemma.id'
 * });
 */

class LemmaIAMUserManager {
    constructor(options = {}) {
        this.config = {
            apiKey: options.apiKey || '',
            siteId: options.siteId || '',
            apiBase: options.apiBase || 'https://lemma.id',
            debug: options.debug || false
        };

        this.state = {
            users: [],
            permissions: [],
            loading: false,
            initialized: false
        };

        // Initialize wallet for permission lemma operations
        this.wallet = null;
        this.initializeWallet();
    }

    async initializeWallet() {
        try {
            // Load the federated wallet for permission lemma operations
            const { LemmaFederatedWallet } = await import('/static/js/lemma-federated-wallet.js');
            this.wallet = new LemmaFederatedWallet({
                debug: this.config.debug,
                networkRegistryUrl: this.config.apiBase
            });
            await this.wallet.init();
            
            if (this.config.debug) {
                console.log('✅ Lemma IAM User Manager wallet initialized');
            }
        } catch (error) {
            console.error('❌ Failed to initialize wallet:', error);
        }
    }

    /**
     * Render the complete user management interface
     */
    renderUserManagement(containerId) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error('Container not found:', containerId);
            return;
        }

        container.innerHTML = `
            <div class="lemma-iam-container">
                <!-- Header -->
                <div class="lemma-iam-header">
                    <h2>User Management</h2>
                    <p>Manage users and permissions for ${this.config.siteId}</p>
                </div>

                <!-- Admin Access Check -->
                <div id="admin-access-check" style="text-align: center; padding: 20px;">
                    Checking admin permissions...
                </div>

                <!-- User Management Interface (hidden until admin access verified) -->
                <div id="user-management-interface" style="display: none;">
                    <!-- Add User Section -->
                    <div class="lemma-iam-section">
                        <h3>Add New User</h3>
                        <p style="color: #666; margin-bottom: 12px; font-size: 0.9rem;">
                            Users are identified by their DID (from their passkey-unlocked wallet)
                        </p>
                        <div class="add-user-form">
                            <input type="text" id="newUserDID" placeholder="User DID (did:lemma:user:...)" class="lemma-input">
                            <select id="newUserRole" class="lemma-select">
                                <option value="user">User</option>
                                <option value="moderator">Moderator</option>
                                <option value="admin">Admin</option>
                            </select>
                            <button onclick="this.parentNode.parentNode.parentNode.userManager.addUser()" class="lemma-btn-primary">
                                Add User
                            </button>
                        </div>
                        <p style="color: #888; margin-top: 12px; font-size: 0.8rem;">
                            Or <a href="#" onclick="this.parentNode.parentNode.userManager.inviteUser(); return false;">generate an invite link</a> for new users
                        </p>
                    </div>

                    <!-- Users List -->
                    <div class="lemma-iam-section">
                        <div class="section-header">
                            <h3>Site Users</h3>
                            <button onclick="this.parentNode.parentNode.parentNode.userManager.refreshUsers()" class="lemma-btn-secondary">
                                Refresh
                            </button>
                        </div>
                        <div id="usersList">
                            <div style="padding: 20px; text-align: center; color: #666;">
                                Loading users...
                            </div>
                        </div>
                    </div>

                    <!-- Permissions Management -->
                    <div class="lemma-iam-section">
                        <h3>Permission Templates</h3>
                        <div id="permissionsList">
                            <div style="padding: 20px; text-align: center; color: #666;">
                                Loading permissions...
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <style>
            .lemma-iam-container {
                max-width: 1000px;
                margin: 0 auto;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }

            .lemma-iam-header {
                text-align: center;
                margin-bottom: 32px;
                padding-bottom: 16px;
                border-bottom: 1px solid #e5e7eb;
            }

            .lemma-iam-header h2 {
                margin: 0 0 8px 0;
                color: #111827;
                font-size: 1.5rem;
                font-weight: 600;
            }

            .lemma-iam-header p {
                margin: 0;
                color: #6b7280;
                font-size: 1rem;
            }

            .lemma-iam-section {
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 24px;
            }

            .lemma-iam-section h3 {
                margin: 0 0 16px 0;
                color: #111827;
                font-size: 1.1rem;
                font-weight: 600;
            }

            .section-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 16px;
            }

            .section-header h3 {
                margin: 0;
            }

            .add-user-form {
                display: grid;
                grid-template-columns: 1fr auto auto;
                gap: 12px;
                align-items: center;
            }

            .lemma-input {
                padding: 10px 12px;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                font-size: 0.9rem;
            }

            .lemma-select {
                padding: 10px 12px;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                font-size: 0.9rem;
                background: white;
            }

            .lemma-btn-primary {
                background: #6366f1;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 8px;
                font-size: 0.9rem;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s ease;
            }

            .lemma-btn-primary:hover {
                background: #5856eb;
            }

            .lemma-btn-secondary {
                background: #f3f4f6;
                color: #374151;
                border: 1px solid #d1d5db;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 0.8rem;
                cursor: pointer;
                transition: all 0.2s ease;
            }

            .lemma-btn-secondary:hover {
                background: #e5e7eb;
            }

            .user-item {
                display: grid;
                grid-template-columns: 1fr auto auto auto;
                gap: 16px;
                align-items: center;
                padding: 16px;
                background: #f9fafb;
                border-radius: 8px;
                margin-bottom: 8px;
                border: 1px solid #e5e7eb;
            }

            .user-info {
                display: flex;
                flex-direction: column;
            }

            .user-did {
                font-weight: 600;
                color: #111827;
                font-family: monospace;
                font-size: 0.85rem;
                margin-bottom: 2px;
            }

            .user-meta {
                font-size: 0.8rem;
                color: #6b7280;
            }

            .user-role {
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 0.75rem;
                font-weight: 500;
                background: #dbeafe;
                color: #1e40af;
            }

            .user-status {
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 0.75rem;
                font-weight: 500;
            }

            .status-active {
                background: #dcfce7;
                color: #166534;
            }

            .status-suspended {
                background: #fef3c7;
                color: #92400e;
            }

            .user-actions {
                display: flex;
                gap: 8px;
            }

            .btn-small {
                padding: 4px 8px;
                border: none;
                border-radius: 4px;
                font-size: 0.75rem;
                cursor: pointer;
                transition: all 0.2s ease;
            }

            .btn-grant {
                background: #10b981;
                color: white;
            }

            .btn-revoke {
                background: #ef4444;
                color: white;
            }

            .btn-remove {
                background: #6b7280;
                color: white;
            }

            @media (max-width: 768px) {
                .add-user-form {
                    grid-template-columns: 1fr;
                    gap: 8px;
                }

                .user-item {
                    grid-template-columns: 1fr;
                    gap: 12px;
                    text-align: center;
                }

                .user-actions {
                    justify-content: center;
                }
            }
            </style>
        `;

        // Store reference to this instance for onclick handlers
        container.userManager = this;

        // Initialize the interface
        this.initializeInterface();
    }

    async initializeInterface() {
        try {
            // Check if user has admin access to this site
            const hasAdminAccess = await this.checkAdminAccess();
            
            if (hasAdminAccess) {
                document.getElementById('admin-access-check').style.display = 'none';
                document.getElementById('user-management-interface').style.display = 'block';
                
                // Load initial data
                await this.loadUsers();
                await this.loadPermissions();
            } else {
                document.getElementById('admin-access-check').innerHTML = `
                    <div style="color: #ef4444;">
                        <h3>Admin Access Required</h3>
                        <p>You need admin permissions for ${this.config.siteId} to manage users.</p>
                        <p>Contact your site administrator to get admin access.</p>
                    </div>
                `;
            }

        } catch (error) {
            console.error('Failed to initialize user management:', error);
            document.getElementById('admin-access-check').innerHTML = `
                <div style="color: #ef4444;">
                    <h3>Initialization Error</h3>
                    <p>Failed to initialize user management interface.</p>
                </div>
            `;
        }
    }

    async checkAdminAccess() {
        try {
            if (!this.wallet) {
                await this.initializeWallet();
            }

            // Check for admin permission lemma for this site
            const permissionLemmas = await this.wallet.getCredentials('permission');
            const hasAdminAccess = permissionLemmas.some(lemma => 
                lemma.claims?.siteId === this.config.siteId && 
                (lemma.claims?.permissionId === 'admin' || 
                 lemma.claims?.permissionId === 'site_admin' ||
                 lemma.claims?.scope?.includes('user_management'))
            );

            return hasAdminAccess;

        } catch (error) {
            console.error('Failed to check admin access:', error);
            return false;
        }
    }

    async loadUsers() {
        try {
            this.state.loading = true;
            
            const response = await fetch(`${this.config.apiBase}/api/v1/sites/${this.config.siteId}/users`, {
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`,
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.state.users = data.users;
                this.displayUsers();
            } else {
                this.displayError('usersList', 'Failed to load users: ' + data.error);
            }

        } catch (error) {
            console.error('Failed to load users:', error);
            this.displayError('usersList', 'Failed to load users');
        } finally {
            this.state.loading = false;
        }
    }

    async loadPermissions() {
        try {
            const response = await fetch(`${this.config.apiBase}/api/v1/sites/${this.config.siteId}/permissions`, {
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`,
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.state.permissions = data.permissions;
                this.displayPermissions();
            } else {
                this.displayError('permissionsList', 'Failed to load permissions: ' + data.error);
            }

        } catch (error) {
            console.error('Failed to load permissions:', error);
            this.displayError('permissionsList', 'Failed to load permissions');
        }
    }

    displayUsers() {
        const container = document.getElementById('usersList');
        
        if (this.state.users.length === 0) {
            container.innerHTML = `
                <div style="padding: 20px; text-align: center; color: #6b7280;">
                    No users added to this site yet. Add your first user above.
                </div>
            `;
            return;
        }

        container.innerHTML = this.state.users.map(user => `
            <div class="user-item">
                <div class="user-info">
                    <div class="user-did" title="${user.user_did}">${user.display_name || user.user_did.substring(0, 35) + '...'}</div>
                    <div class="user-meta">
                        Added ${new Date(user.added_at).toLocaleDateString()} by ${user.added_by}
                        ${user.last_seen ? `• Last seen: ${new Date(user.last_seen).toLocaleDateString()}` : ''}
                    </div>
                </div>
                <div class="user-role">${user.role}</div>
                <div class="user-status status-${user.status}">${user.status}</div>
                <div class="user-actions">
                    <button class="btn-small btn-grant" onclick="this.closest('.lemma-iam-container').userManager.grantPermission('${user.user_did}')">
                        Grant Access
                    </button>
                    <button class="btn-small btn-revoke" onclick="this.closest('.lemma-iam-container').userManager.revokePermission('${user.user_did}')">
                        Revoke Access
                    </button>
                    <button class="btn-small btn-remove" onclick="this.closest('.lemma-iam-container').userManager.removeUser('${user.user_did}')">
                        Remove
                    </button>
                </div>
            </div>
        `).join('');
    }

    displayPermissions() {
        const container = document.getElementById('permissionsList');
        
        if (this.state.permissions.length === 0) {
            container.innerHTML = `
                <div style="padding: 20px; text-align: center; color: #6b7280;">
                    No custom permissions defined. Using default user/admin permissions.
                </div>
            `;
            return;
        }

        container.innerHTML = this.state.permissions.map(permission => `
            <div style="padding: 12px; background: #f9fafb; border-radius: 8px; margin-bottom: 8px; border: 1px solid #e5e7eb;">
                <div style="font-weight: 600; margin-bottom: 4px;">${permission.permission_id}</div>
                <div style="font-size: 0.8rem; color: #6b7280;">
                    ${permission.description} • Scope: ${permission.scope.join(', ')}
                </div>
            </div>
        `).join('');
    }

    async addUser() {
        const userDID = document.getElementById('newUserDID').value.trim();
        const role = document.getElementById('newUserRole').value;

        if (!userDID) {
            alert('Please enter a user DID (did:lemma:user:...)');
            return;
        }

        if (!userDID.startsWith('did:lemma:')) {
            alert('Invalid DID format. Should start with did:lemma:');
            return;
        }

        try {
            const response = await fetch(`${this.config.apiBase}/api/v1/sites/${this.config.siteId}/users`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    user_did: userDID,
                    role: role
                })
            });

            const result = await response.json();
            
            if (result.success) {
                // Clear form
                document.getElementById('newUserDID').value = '';
                document.getElementById('newUserRole').value = 'user';
                
                // Refresh users list
                await this.loadUsers();
                
                alert(`User ${userDID.substring(0, 30)}... added as ${role}`);
            } else {
                alert('Failed to add user: ' + result.error);
            }

        } catch (error) {
            console.error('Failed to add user:', error);
            alert('Failed to add user');
        }
    }

    /**
     * Generate an invite link for new users
     * Users visit the link, create a wallet/passkey, and get permission issued
     */
    async inviteUser() {
        const role = document.getElementById('newUserRole').value;
        
        try {
            const response = await fetch(`${this.config.apiBase}/api/v1/sites/${this.config.siteId}/invite`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    role: role,
                    expires_in: 86400 * 7  // 7 days
                })
            });

            const result = await response.json();
            
            if (result.success && result.invite_url) {
                // Copy to clipboard
                navigator.clipboard.writeText(result.invite_url);
                alert(`Invite link copied to clipboard!\n\n${result.invite_url}\n\nShare this with the user. They'll create a wallet and receive ${role} permissions.`);
            } else {
                alert('Failed to create invite: ' + (result.error || 'Unknown error'));
            }

        } catch (error) {
            console.error('Failed to create invite:', error);
            alert('Failed to create invite link');
        }
    }

    async grantPermission(userDid) {
        const permissionId = prompt('Enter permission ID to grant (e.g., "admin", "moderator", "editor"):', 'user');
        if (!permissionId) return;

        try {
            const response = await fetch(`${this.config.apiBase}/api/v1/sites/${this.config.siteId}/users/${userDid}/permissions`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    permission_id: permissionId,
                    expiry_days: 90
                })
            });

            const result = await response.json();
            
            if (result.success) {
                alert(`Permission "${permissionId}" granted. Permission lemma issued to user's wallet.`);
                await this.loadUsers(); // Refresh
            } else {
                alert('Failed to grant permission: ' + result.error);
            }

        } catch (error) {
            console.error('Failed to grant permission:', error);
            alert('Failed to grant permission');
        }
    }

    async revokePermission(userDid) {
        const permissionId = prompt('Enter permission ID to revoke:', 'user');
        if (!permissionId) return;

        const shortDid = userDid.substring(0, 30) + '...';
        if (!confirm(`Revoke "${permissionId}" from ${shortDid} for ${this.config.siteId}?\n\nThis removes access to THIS site only.`)) {
            return;
        }

        try {
            // Call API to revoke permission (adds to revocation list)
            const response = await fetch(`${this.config.apiBase}/api/v1/sites/${this.config.siteId}/users/${userDid}/permissions/${permissionId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`,
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();
            
            if (result.success) {
                // Also remove from user's wallet if they're on this page
                if (this.wallet) {
                    try {
                        // Get user's permission lemmas for this site
                        const permissionLemmas = await this.wallet.getCredentials('permission');
                        const targetLemma = permissionLemmas.find(lemma => 
                            lemma.claims?.siteId === this.config.siteId &&
                            lemma.claims?.permissionId === permissionId &&
                            lemma.subject === userDid
                        );
                        
                        if (targetLemma) {
                            await this.wallet.removeCredential(targetLemma.id);
                            console.log(`✅ Removed permission lemma ${targetLemma.id} for ${this.config.siteId}`);
                        }
                    } catch (walletError) {
                        console.warn('Could not remove from local wallet (user may not be on this device):', walletError);
                    }
                }
                
                alert(`Permission "${permissionId}" revoked for ${this.config.siteId}.`);
                await this.loadUsers(); // Refresh
            } else {
                alert('Failed to revoke permission: ' + result.error);
            }

        } catch (error) {
            console.error('Failed to revoke permission:', error);
            alert('Failed to revoke permission');
        }
    }

    async removeUser(userDid) {
        const shortDid = userDid.substring(0, 30) + '...';
        if (!confirm(`Remove ${shortDid} from this site?\n\nThis revokes all their permissions and cannot be undone.`)) {
            return;
        }

        try {
            const response = await fetch(`${this.config.apiBase}/api/v1/sites/${this.config.siteId}/users/${userDid}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.config.apiKey}`,
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();
            
            if (result.success) {
                alert(`User removed. All their permissions for this site have been revoked.`);
                await this.loadUsers(); // Refresh
            } else {
                alert('Failed to remove user: ' + result.error);
            }

        } catch (error) {
            console.error('Failed to remove user:', error);
            alert('Failed to remove user');
        }
    }

    async refreshUsers() {
        await this.loadUsers();
    }

    displayError(containerId, message) {
        const container = document.getElementById(containerId);
        container.innerHTML = `
            <div style="padding: 20px; text-align: center; color: #ef4444;">
                ${message}
            </div>
        `;
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LemmaIAMUserManager;
} else {
    window.LemmaIAMUserManager = LemmaIAMUserManager;
}
