"""
IAM Subnet Manager - Complete Client Control System
Provides full user and permission management for client sites
"""

import os
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from .database import (
    get_db, FederatedSite, SiteUser, SiteAdmin, Permission, PermissionRole,
    SitePermissionGrant, UserSession, SiteConfiguration, UserLemma, NetworkActivity
)

logger = logging.getLogger(__name__)

class IAMSubnetManager:
    """Complete IAM subnet management for client sites"""
    
    def __init__(self, site_id: str):
        self.site_id = site_id
        logger.info(f"✅ IAMSubnetManager initialized for site: {site_id}")
    
    # ================================================================================
    # USER MANAGEMENT - Complete Client Control
    # ================================================================================
    
    def add_user(self, admin_did: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new user to the site (client has complete control)"""
        try:
            db = get_db()
            
            # Verify admin has user management permissions
            if not self._verify_admin_permission(admin_did, 'users'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Generate user DID if not provided (site-specific)
            user_did = user_data.get('user_did') or f"did:lemma:site:{self.site_id}:user:{secrets.token_hex(16)}"
            
            # Check if user already exists on this site
            existing_user = db.query(SiteUser).filter(
                SiteUser.site_id == self.site_id,
                SiteUser.user_did == user_did
            ).first()
            
            if existing_user:
                db.close()
                return {'success': False, 'error': 'User already exists on this site'}
            
            # Create site user
            site_user = SiteUser(
                site_id=self.site_id,
                user_did=user_did,
                user_email=user_data.get('email'),
                display_name=user_data.get('display_name', user_data.get('email', 'Unknown User')),
                user_status=user_data.get('status', 'active'),
                user_role=user_data.get('role', 'user'),
                user_metadata=user_data.get('metadata', {}),
                added_by=admin_did
            )
            
            db.add(site_user)
            
            # If user has a default role, assign permissions
            default_role = user_data.get('role')
            if default_role:
                role = db.query(PermissionRole).filter(
                    PermissionRole.site_id == self.site_id,
                    PermissionRole.role_id == default_role
                ).first()
                
                if role:
                    # Grant all permissions from the role
                    for permission_id in role.permissions:
                        self._grant_permission_internal(db, user_did, permission_id, admin_did)
            
            db.commit()
            db.close()
            
            logger.info(f"✅ Added user {user_did} to site {self.site_id}")
            
            return {
                'success': True,
                'user_did': user_did,
                'site_id': self.site_id,
                'user_email': site_user.user_email,
                'display_name': site_user.display_name,
                'user_role': site_user.user_role,
                'user_status': site_user.user_status
            }
            
        except Exception as e:
            logger.error(f"❌ Add user failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    def update_user(self, admin_did: str, user_did: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update user information (client has complete control)"""
        try:
            db = get_db()
            
            # Verify admin has user management permissions
            if not self._verify_admin_permission(admin_did, 'users'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Get user
            user = db.query(SiteUser).filter(
                SiteUser.site_id == self.site_id,
                SiteUser.user_did == user_did
            ).first()
            
            if not user:
                db.close()
                return {'success': False, 'error': 'User not found'}
            
            # Update allowed fields
            allowed_updates = ['user_email', 'display_name', 'user_status', 'user_role', 'user_metadata']
            for field in allowed_updates:
                if field in updates:
                    setattr(user, field, updates[field])
            
            # If role changed, update permissions
            if 'user_role' in updates:
                new_role = updates['user_role']
                role = db.query(PermissionRole).filter(
                    PermissionRole.site_id == self.site_id,
                    PermissionRole.role_id == new_role
                ).first()
                
                if role:
                    # Revoke all current permissions
                    db.query(SitePermissionGrant).filter(
                        SitePermissionGrant.site_id == self.site_id,
                        SitePermissionGrant.user_did == user_did,
                        SitePermissionGrant.is_active == True
                    ).update({'is_active': False, 'revoked_at': datetime.utcnow()})
                    
                    # Grant new role permissions
                    for permission_id in role.permissions:
                        self._grant_permission_internal(db, user_did, permission_id, admin_did)
            
            db.commit()
            db.close()
            
            logger.info(f"✅ Updated user {user_did} on site {self.site_id}")
            
            return {
                'success': True,
                'user_did': user_did,
                'updates_applied': list(updates.keys())
            }
            
        except Exception as e:
            logger.error(f"❌ Update user failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    def remove_user(self, admin_did: str, user_did: str, reason: str = None) -> Dict[str, Any]:
        """Remove user from site (client has complete control)"""
        try:
            db = get_db()
            
            # Verify admin has user management permissions
            if not self._verify_admin_permission(admin_did, 'users'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Get user
            user = db.query(SiteUser).filter(
                SiteUser.site_id == self.site_id,
                SiteUser.user_did == user_did
            ).first()
            
            if not user:
                db.close()
                return {'success': False, 'error': 'User not found'}
            
            # Revoke all permissions
            db.query(SitePermissionGrant).filter(
                SitePermissionGrant.site_id == self.site_id,
                SitePermissionGrant.user_did == user_did,
                SitePermissionGrant.is_active == True
            ).update({
                'is_active': False,
                'revoked_at': datetime.utcnow()
            })
            
            # Revoke all lemmas
            db.query(UserLemma).filter(
                UserLemma.site_id == self.site_id,
                UserLemma.user_did == user_did,
                UserLemma.is_active == True
            ).update({
                'is_active': False,
                'revoked_at': datetime.utcnow()
            })
            
            # Deactivate user sessions
            db.query(UserSession).filter(
                UserSession.site_id == self.site_id,
                UserSession.user_did == user_did,
                UserSession.is_active == True
            ).update({'is_active': False})
            
            # Mark user as removed
            user.user_status = 'removed'
            
            db.commit()
            db.close()
            
            logger.info(f"✅ Removed user {user_did} from site {self.site_id}")
            
            return {
                'success': True,
                'user_did': user_did,
                'removed_at': datetime.utcnow().isoformat(),
                'reason': reason
            }
            
        except Exception as e:
            logger.error(f"❌ Remove user failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    def list_users(self, admin_did: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """List all users on the site (client has complete visibility)"""
        try:
            db = get_db()
            
            # Verify admin has user management permissions
            if not self._verify_admin_permission(admin_did, 'users'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Build query
            query = db.query(SiteUser).filter(SiteUser.site_id == self.site_id)
            
            # Apply filters
            if filters:
                if 'status' in filters:
                    query = query.filter(SiteUser.user_status == filters['status'])
                if 'role' in filters:
                    query = query.filter(SiteUser.user_role == filters['role'])
                if 'search' in filters:
                    search = f"%{filters['search']}%"
                    query = query.filter(
                        (SiteUser.display_name.ilike(search)) |
                        (SiteUser.user_email.ilike(search))
                    )
            
            users = query.all()
            db.close()
            
            user_list = []
            for user in users:
                user_list.append({
                    'user_did': user.user_did,
                    'user_email': user.user_email,
                    'display_name': user.display_name,
                    'user_status': user.user_status,
                    'user_role': user.user_role,
                    'added_at': user.added_at.isoformat(),
                    'last_login': user.last_login.isoformat() if user.last_login else None,
                    'login_count': user.login_count,
                    'user_metadata': user.user_metadata
                })
            
            return {
                'success': True,
                'site_id': self.site_id,
                'total_users': len(user_list),
                'users': user_list
            }
            
        except Exception as e:
            logger.error(f"❌ List users failed: {e}")
            db.close()
            return {'success': False, 'error': str(e)}
    
    # ================================================================================
    # PERMISSION MANAGEMENT - Complete Client Control
    # ================================================================================
    
    def create_permission(self, admin_did: str, permission_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create custom permission for the site"""
        try:
            db = get_db()
            
            # Verify admin has permission management rights
            if not self._verify_admin_permission(admin_did, 'permissions'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Create permission
            permission = Permission(
                site_id=self.site_id,
                permission_id=permission_data['permission_id'],
                display_name=permission_data['display_name'],
                scope=permission_data.get('scope', []),
                conditions=permission_data.get('conditions', []),
                delegation_allowed=permission_data.get('delegation_allowed', False),
                priority=permission_data.get('priority', 0),
                created_by=admin_did
            )
            
            db.add(permission)
            db.commit()
            db.close()
            
            logger.info(f"✅ Created permission {permission_data['permission_id']} for site {self.site_id}")
            
            return {
                'success': True,
                'permission_id': permission.permission_id,
                'site_id': self.site_id,
                'display_name': permission.display_name,
                'scope': permission.scope
            }
            
        except Exception as e:
            logger.error(f"❌ Create permission failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    def grant_permission(self, admin_did: str, user_did: str, permission_id: str, 
                        conditions: Dict[str, Any] = None, expires_days: int = 90) -> Dict[str, Any]:
        """Grant permission to user (client has complete control)"""
        try:
            db = get_db()
            
            # Verify admin has permission management rights
            if not self._verify_admin_permission(admin_did, 'permissions'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Grant permission
            result = self._grant_permission_internal(db, user_did, permission_id, admin_did, conditions, expires_days)
            
            db.commit()
            db.close()
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Grant permission failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    def revoke_permission(self, admin_did: str, user_did: str, permission_id: str, 
                         reason: str = None) -> Dict[str, Any]:
        """Revoke permission from user (INDEPENDENT of PoH lemma - client has complete control)"""
        try:
            db = get_db()
            
            # Verify admin has permission management rights
            if not self._verify_admin_permission(admin_did, 'permissions'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Revoke permission grant
            grant = db.query(SitePermissionGrant).filter(
                SitePermissionGrant.site_id == self.site_id,
                SitePermissionGrant.user_did == user_did,
                SitePermissionGrant.permission_id == permission_id,
                SitePermissionGrant.is_active == True
            ).first()
            
            if not grant:
                db.close()
                return {'success': False, 'error': 'Permission grant not found'}
            
            # Revoke the grant
            grant.is_active = False
            grant.revoked_at = datetime.utcnow()
            
            # Revoke associated permission lemma (ONLY this permission, NOT PoH)
            lemma = db.query(UserLemma).filter(
                UserLemma.site_id == self.site_id,
                UserLemma.user_did == user_did,
                UserLemma.permission_id == permission_id,
                UserLemma.lemma_type == 'permission',  # Only permission lemmas
                UserLemma.is_active == True
            ).first()
            
            if lemma:
                lemma.is_active = False
                lemma.revoked_at = datetime.utcnow()
                
                # Add to revocation list (permission-specific)
                from api.database import RevocationList
                revocation = RevocationList(
                    lemma_id=f"perm_{self.site_id}_{user_did}_{permission_id}",
                    lemma_type='permission',
                    site_id=self.site_id,
                    user_did=user_did,
                    revoked_by=admin_did,
                    reason=reason or f"Permission {permission_id} revoked by admin"
                )
                db.add(revocation)
            
            db.commit()
            db.close()
            
            logger.info(f"✅ Revoked permission {permission_id} from user {user_did} on site {self.site_id} (PoH lemma unaffected)")
            
            return {
                'success': True,
                'user_did': user_did,
                'permission_id': permission_id,
                'revoked_at': datetime.utcnow().isoformat(),
                'reason': reason,
                'note': 'Permission lemma revoked independently - PoH lemma unaffected'
            }
            
        except Exception as e:
            logger.error(f"❌ Revoke permission failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    def revoke_poh_only(self, admin_did: str, user_did: str, reason: str = None) -> Dict[str, Any]:
        """Revoke PoH lemma ONLY - permission lemmas remain valid and functional"""
        try:
            db = get_db()
            
            # Verify admin has user management rights (or is network admin)
            if not self._verify_admin_permission(admin_did, 'users'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions to revoke PoH'}
            
            # Revoke PoH lemma ONLY (lemma_type='poh', site_id=NULL for universal)
            poh_lemma = db.query(UserLemma).filter(
                UserLemma.user_did == user_did,
                UserLemma.lemma_type == 'poh',
                UserLemma.site_id.is_(None),  # Universal PoH lemmas have NULL site_id
                UserLemma.is_active == True
            ).first()
            
            if not poh_lemma:
                db.close()
                return {'success': False, 'error': 'PoH lemma not found or already revoked'}
            
            # Revoke the PoH lemma
            poh_lemma.is_active = False
            poh_lemma.revoked_at = datetime.utcnow()
            
            # Add to revocation list (PoH-specific)
            from api.database import RevocationList
            revocation = RevocationList(
                lemma_id=f"poh_{user_did}",
                lemma_type='poh',
                site_id=None,  # Universal PoH revocation
                user_did=user_did,
                revoked_by=admin_did,
                reason=reason or "PoH lemma revoked by admin"
            )
            db.add(revocation)
            
            db.commit()
            db.close()
            
            logger.info(f"✅ Revoked PoH lemma for user {user_did} (Permission lemmas remain valid)")
            
            return {
                'success': True,
                'user_did': user_did,
                'lemma_type': 'poh',
                'revoked_at': datetime.utcnow().isoformat(),
                'reason': reason,
                'note': 'PoH lemma revoked - all permission lemmas remain valid and functional'
            }
            
        except Exception as e:
            logger.error(f"❌ Revoke PoH failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    # ================================================================================
    # ROLE MANAGEMENT - Simplified Permission Bundles
    # ================================================================================
    
    def create_role(self, admin_did: str, role_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create permission role for easier management"""
        try:
            db = get_db()
            
            # Verify admin has permission management rights
            if not self._verify_admin_permission(admin_did, 'permissions'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Create role
            role = PermissionRole(
                site_id=self.site_id,
                role_id=role_data['role_id'],
                role_name=role_data['role_name'],
                description=role_data.get('description'),
                permissions=role_data['permissions'],
                is_default=role_data.get('is_default', False),
                created_by=admin_did
            )
            
            db.add(role)
            db.commit()
            db.close()
            
            logger.info(f"✅ Created role {role_data['role_id']} for site {self.site_id}")
            
            return {
                'success': True,
                'role_id': role.role_id,
                'role_name': role.role_name,
                'permissions': role.permissions
            }
            
        except Exception as e:
            logger.error(f"❌ Create role failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    def assign_role(self, admin_did: str, user_did: str, role_id: str) -> Dict[str, Any]:
        """Assign role to user (grants all role permissions)"""
        try:
            db = get_db()
            
            # Verify admin has permission management rights
            if not self._verify_admin_permission(admin_did, 'permissions'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Get role
            role = db.query(PermissionRole).filter(
                PermissionRole.site_id == self.site_id,
                PermissionRole.role_id == role_id
            ).first()
            
            if not role:
                db.close()
                return {'success': False, 'error': 'Role not found'}
            
            # Update user role
            user = db.query(SiteUser).filter(
                SiteUser.site_id == self.site_id,
                SiteUser.user_did == user_did
            ).first()
            
            if user:
                user.user_role = role_id
            
            # Grant all role permissions
            granted_permissions = []
            for permission_id in role.permissions:
                result = self._grant_permission_internal(db, user_did, permission_id, admin_did)
                if result['success']:
                    granted_permissions.append(permission_id)
            
            db.commit()
            db.close()
            
            return {
                'success': True,
                'user_did': user_did,
                'role_id': role_id,
                'granted_permissions': granted_permissions
            }
            
        except Exception as e:
            logger.error(f"❌ Assign role failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    # ================================================================================
    # SITE CONFIGURATION - Complete Client Control
    # ================================================================================
    
    def update_site_config(self, admin_did: str, config_updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update site configuration (client has complete control)"""
        try:
            db = get_db()
            
            # Verify admin has configuration rights
            if not self._verify_admin_permission(admin_did, 'configuration'):
                db.close()
                return {'success': False, 'error': 'Insufficient permissions'}
            
            # Get or create site configuration
            config = db.query(SiteConfiguration).filter(
                SiteConfiguration.site_id == self.site_id
            ).first()
            
            if not config:
                config = SiteConfiguration(site_id=self.site_id)
                db.add(config)
            
            # Update configuration
            allowed_fields = [
                'allow_self_registration', 'require_email_verification', 'default_user_role',
                'session_timeout_minutes', 'permission_inheritance', 'require_2fa_for_admin',
                'oauth_enabled', 'oauth_scopes', 'oauth_redirect_uris', 'site_name',
                'site_logo_url', 'custom_css', 'webhook_url', 'webhook_events',
                'ip_whitelist', 'rate_limit_per_minute'
            ]
            
            for field in allowed_fields:
                if field in config_updates:
                    setattr(config, field, config_updates[field])
            
            config.updated_at = datetime.utcnow()
            config.updated_by = admin_did
            
            db.commit()
            db.close()
            
            logger.info(f"✅ Updated site configuration for {self.site_id}")
            
            return {
                'success': True,
                'site_id': self.site_id,
                'updated_fields': list(config_updates.keys())
            }
            
        except Exception as e:
            logger.error(f"❌ Update site config failed: {e}")
            db.rollback()
            db.close()
            return {'success': False, 'error': str(e)}
    
    # ================================================================================
    # INTERNAL HELPER METHODS
    # ================================================================================
    
    def _verify_admin_permission(self, admin_did: str, permission_type: str) -> bool:
        """Verify admin has specific permission type"""
        try:
            db = get_db()
            admin = db.query(SiteAdmin).filter(
                SiteAdmin.site_id == self.site_id,
                SiteAdmin.admin_did == admin_did,
                SiteAdmin.is_active == True
            ).first()
            db.close()
            
            if not admin:
                return False
            
            # Site owners have all permissions
            if admin.admin_role == 'owner':
                return True
            
            # Check specific permissions
            return permission_type in admin.permissions or 'all' in admin.permissions
            
        except Exception as e:
            logger.error(f"❌ Admin permission check failed: {e}")
            return False
    
    def _grant_permission_internal(self, db: Session, user_did: str, permission_id: str, 
                                 granted_by: str, conditions: Dict[str, Any] = None, 
                                 expires_days: int = 90) -> Dict[str, Any]:
        """Internal method to grant permission"""
        try:
            # Check if permission exists
            permission = db.query(Permission).filter(
                Permission.site_id == self.site_id,
                Permission.permission_id == permission_id
            ).first()
            
            if not permission:
                return {'success': False, 'error': 'Permission not found'}
            
            # Create permission grant
            grant = SitePermissionGrant(
                site_id=self.site_id,
                user_did=user_did,
                permission_id=permission_id,
                granted_by=granted_by,
                expires_at=datetime.utcnow() + timedelta(days=expires_days),
                conditions=conditions or {}
            )
            
            # Create permission lemma
            lemma = UserLemma(
                user_did=user_did,
                lemma_type='permission',
                site_id=self.site_id,
                permission_id=permission_id,
                lemma_data={
                    'type': 'site_permission',
                    'site_id': self.site_id,
                    'permission_id': permission_id,
                    'granted_by': granted_by,
                    'conditions': conditions or {},
                    'scope': permission.scope,
                    'cryptographic_proof': {}  # Generated by Rust engine
                },
                expires_at=grant.expires_at
            )
            
            db.add(grant)
            db.add(lemma)
            
            return {
                'success': True,
                'user_did': user_did,
                'permission_id': permission_id,
                'expires_at': grant.expires_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Internal grant permission failed: {e}")
            return {'success': False, 'error': str(e)}

# Global subnet managers registry
subnet_managers: Dict[str, IAMSubnetManager] = {}

def get_subnet_manager(site_id: str) -> IAMSubnetManager:
    """Get or create subnet manager for site"""
    if site_id not in subnet_managers:
        subnet_managers[site_id] = IAMSubnetManager(site_id)
    return subnet_managers[site_id]
