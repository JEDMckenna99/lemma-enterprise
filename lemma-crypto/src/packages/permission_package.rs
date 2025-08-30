//! Permission/IAM verification package for access control and identity management
//!
//! This package enables sites to create IAM subnets using Lemma's cryptographic infrastructure.
//! Users store site-specific permission lemmas in their wallet alongside their PoH lemma.

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};

use crate::{
    credentials::VerifiableCredential,
    core::VerificationResult,
    ClaimSet, VerificationMetadata,
    Result, LemmaError,
    packages::VerificationPackage,
};

/// Permission/IAM verification package for complete access management
#[derive(Debug, Clone)]
pub struct PermissionPackage {
    site_id: String,
    permission_registry: HashMap<String, PermissionInfo>,
    subnet_config: SubnetConfig,
    revocation_authority: String,
}

/// Detailed permission information with scope and conditions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PermissionInfo {
    pub permission_id: String,          // e.g., "admin", "user", "read_only"
    pub display_name: String,           // e.g., "Administrator", "Standard User"
    pub scope: Vec<String>,             // e.g., ["users:read", "posts:write", "admin:*"]
    pub expiry: Option<DateTime<Utc>>,  // Optional expiration
    pub conditions: Vec<String>,        // e.g., ["ip_range:192.168.1.0/24", "time:9-17"]
    pub delegation_allowed: bool,       // Can this permission be delegated?
    pub priority: u32,                  // Permission priority (higher = more access)
    pub created_at: DateTime<Utc>,
    pub created_by: String,             // DID of permission granter
}

/// IAM subnet configuration for site-specific access management
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubnetConfig {
    pub site_domain: String,            // e.g., "company.com"
    pub iam_namespace: String,          // e.g., "company_iam_2024"
    pub max_permissions_per_user: usize, // Limit per user (prevent permission bloat)
    pub require_poh: bool,              // Require PoH lemma for any access
    pub allow_federation: bool,         // Allow cross-site permission sharing
    pub session_timeout: u64,           // Session timeout in seconds
    pub mfa_required: bool,             // Multi-factor authentication required
    pub audit_logging: bool,            // Enable detailed audit logs
}

/// Access request context for permission verification
#[derive(Debug, Clone)]
pub struct AccessRequest {
    pub user_did: String,
    pub resource: String,               // e.g., "/api/users", "/admin/dashboard"
    pub action: String,                 // e.g., "read", "write", "delete"
    pub ip_address: Option<String>,
    pub user_agent: Option<String>,
    pub timestamp: DateTime<Utc>,
    pub session_id: Option<String>,
}

impl PermissionPackage {
    /// Create new permission package for a site
    pub fn new(site_id: String, site_domain: String) -> Self {
        let subnet_config = SubnetConfig {
            site_domain,
            iam_namespace: format!("{}_iam_{}", site_id, Utc::now().format("%Y")),
            max_permissions_per_user: 50,
            require_poh: true,
            allow_federation: false,
            session_timeout: 3600, // 1 hour
            mfa_required: false,
            audit_logging: true,
        };

        Self {
            site_id: site_id.clone(),
            permission_registry: HashMap::new(),
            subnet_config,
            revocation_authority: format!("did:lemma:site:{}", site_id),
        }
    }

    /// Add a permission definition to the registry
    pub fn add_permission(&mut self, permission: PermissionInfo) {
        self.permission_registry.insert(permission.permission_id.clone(), permission);
    }

    /// Create standard permission set for common IAM patterns
    pub fn create_standard_permissions(&mut self) -> Result<()> {
        let standard_permissions = vec![
            PermissionInfo {
                permission_id: "admin".to_string(),
                display_name: "Administrator".to_string(),
                scope: vec!["*:*".to_string()], // Full access
                expiry: None,
                conditions: vec![],
                delegation_allowed: true,
                priority: 1000,
                created_at: Utc::now(),
                created_by: self.revocation_authority.clone(),
            },
            PermissionInfo {
                permission_id: "user".to_string(),
                display_name: "Standard User".to_string(),
                scope: vec!["profile:read".to_string(), "profile:write".to_string()],
                expiry: None,
                conditions: vec![],
                delegation_allowed: false,
                priority: 100,
                created_at: Utc::now(),
                created_by: self.revocation_authority.clone(),
            },
            PermissionInfo {
                permission_id: "read_only".to_string(),
                display_name: "Read Only".to_string(),
                scope: vec!["*:read".to_string()],
                expiry: None,
                conditions: vec![],
                delegation_allowed: false,
                priority: 50,
                created_at: Utc::now(),
                created_by: self.revocation_authority.clone(),
            },
        ];

        for permission in standard_permissions {
            self.add_permission(permission);
        }

        Ok(())
    }

    /// Check if access request is authorized based on permission lemmas
    pub fn check_access(&self, request: &AccessRequest, permission_lemmas: &[VerifiableCredential]) -> Result<bool> {
        // Extract permissions from lemmas
        let mut user_permissions = Vec::new();
        for lemma in permission_lemmas {
            if let Some(permission_id) = lemma.get_claim("permissionId").and_then(|v| v.as_str()) {
                if let Some(permission_info) = self.permission_registry.get(permission_id) {
                    user_permissions.push(permission_info);
                }
            }
        }

        // Check if any permission grants access to the requested resource/action
        for permission in &user_permissions {
            if self.permission_grants_access(permission, request)? {
                return Ok(true);
            }
        }

        Ok(false)
    }

    /// Check if a specific permission grants access to a resource/action
    fn permission_grants_access(&self, permission: &PermissionInfo, request: &AccessRequest) -> Result<bool> {
        // Check expiry
        if let Some(expiry) = permission.expiry {
            if Utc::now() > expiry {
                return Ok(false);
            }
        }

        // Check scope
        let resource_action = format!("{}:{}", request.resource, request.action);
        let mut scope_match = false;

        for scope in &permission.scope {
            if scope == "*:*" || scope == &resource_action {
                scope_match = true;
                break;
            }
            
            // Wildcard matching
            if scope.ends_with(":*") {
                let scope_resource = scope.trim_end_matches(":*");
                if request.resource.starts_with(scope_resource) {
                    scope_match = true;
                    break;
                }
            }
            
            if scope.starts_with("*:") {
                let scope_action = scope.trim_start_matches("*:");
                if request.action == scope_action {
                    scope_match = true;
                    break;
                }
            }
        }

        if !scope_match {
            return Ok(false);
        }

        // Check conditions (IP range, time restrictions, etc.)
        for condition in &permission.conditions {
            if !self.check_condition(condition, request)? {
                return Ok(false);
            }
        }

        Ok(true)
    }

    /// Check if a condition is satisfied
    fn check_condition(&self, condition: &str, request: &AccessRequest) -> Result<bool> {
        if condition.starts_with("ip_range:") {
            // TODO: Implement IP range checking
            return Ok(true);
        }
        
        if condition.starts_with("time:") {
            // TODO: Implement time-based access control
            return Ok(true);
        }

        // Unknown condition - default to true for now
        Ok(true)
    }
}

impl VerificationPackage for PermissionPackage {
    fn package_type(&self) -> &str {
        "permission"
    }

    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        let permission_id = credential.get_claim("permissionId")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing permissionId claim".to_string()))?;

        let user_did = credential.get_claim("userDID")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing userDID claim".to_string()))?;

        let site_id = credential.get_claim("siteId")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing siteId claim".to_string()))?;

        // Verify this permission belongs to our site
        let site_matches = site_id == self.site_id;
        
        // Check if permission exists in registry
        let permission_exists = self.permission_registry.contains_key(permission_id);

        let mut metadata = HashMap::new();
        metadata.insert("permission_id".to_string(), serde_json::Value::String(permission_id.to_string()));
        metadata.insert("user_did".to_string(), serde_json::Value::String(user_did.to_string()));
        metadata.insert("site_id".to_string(), serde_json::Value::String(site_id.to_string()));
        metadata.insert("site_matches".to_string(), serde_json::Value::Bool(site_matches));
        metadata.insert("permission_exists".to_string(), serde_json::Value::Bool(permission_exists));

        if let Some(permission_info) = self.permission_registry.get(permission_id) {
            metadata.insert("permission_name".to_string(), serde_json::Value::String(permission_info.display_name.clone()));
            metadata.insert("scope".to_string(), serde_json::Value::Array(
                permission_info.scope.iter().map(|s| serde_json::Value::String(s.clone())).collect()
            ));
            metadata.insert("priority".to_string(), serde_json::Value::Number(permission_info.priority.into()));
            
            // Check expiry
            let not_expired = permission_info.expiry.map_or(true, |expiry| Utc::now() <= expiry);
            metadata.insert("not_expired".to_string(), serde_json::Value::Bool(not_expired));
        }

        let verified = site_matches && permission_exists;

        Ok(VerificationResult::new(
            verified,
            "permission".to_string(),
            if verified { 0.999 } else { 0.001 },
            metadata,
        ))
    }

    fn create_credential(&self, claims: ClaimSet) -> Result<VerifiableCredential> {
        // TODO: Create actual permission credential with proper issuer
        Err(LemmaError::Package("Not implemented: use CredentialIssuer directly".to_string()))
    }

    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String {
        let user_did = credential.get_claim("userDID")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let permission_id = credential.get_claim("permissionId")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        format!("permission:{}:{}:{}", self.site_id, user_did, permission_id)
    }

    fn validate_claims(&self, claims: &ClaimSet) -> Result<()> {
        let required_claims = ["permissionId", "userDID", "siteId"];
        for claim in &required_claims {
            if !claims.contains_key(*claim) {
                return Err(LemmaError::Package(format!("Missing required claim: {}", claim)));
            }
        }

        // Validate site ID matches
        if let Some(site_id) = claims.get("siteId").and_then(|v| v.as_str()) {
            if site_id != self.site_id {
                return Err(LemmaError::Package("Site ID mismatch".to_string()));
            }
        }

        Ok(())
    }
}

/// IAM Subnet Manager for site administrators
pub struct IAMSubnetManager {
    site_id: String,
    permission_package: PermissionPackage,
    admin_credentials: Vec<VerifiableCredential>,
}

impl IAMSubnetManager {
    pub fn new(site_id: String, site_domain: String) -> Self {
        let mut permission_package = PermissionPackage::new(site_id.clone(), site_domain);
        permission_package.create_standard_permissions().unwrap();

        Self {
            site_id,
            permission_package,
            admin_credentials: Vec::new(),
        }
    }

    /// Grant permission to a user (creates permission lemma)
    pub fn grant_permission(&mut self, user_did: &str, permission_id: &str) -> Result<ClaimSet> {
        // Verify permission exists
        if !self.permission_package.permission_registry.contains_key(permission_id) {
            return Err(LemmaError::Package(format!("Permission '{}' not found", permission_id)));
        }

        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("permission".to_string()));
        claims.insert("permissionId".to_string(), serde_json::Value::String(permission_id.to_string()));
        claims.insert("userDID".to_string(), serde_json::Value::String(user_did.to_string()));
        claims.insert("siteId".to_string(), serde_json::Value::String(self.site_id.clone()));
        claims.insert("grantedAt".to_string(), serde_json::Value::String(Utc::now().to_rfc3339()));
        claims.insert("grantedBy".to_string(), serde_json::Value::String(self.permission_package.revocation_authority.clone()));

        Ok(claims)
    }

    /// Revoke permission from a user
    pub fn revoke_permission(&mut self, user_did: &str, permission_id: &str) -> Result<String> {
        // Return revocation key for bloom filter
        Ok(format!("permission:{}:{}:{}", self.site_id, user_did, permission_id))
    }

    /// List all permissions for a user
    pub fn list_user_permissions(&self, _user_did: &str) -> Vec<&PermissionInfo> {
        // TODO: Query user's permission lemmas from wallet
        self.permission_package.permission_registry.values().collect()
    }

    /// Check access for a user request
    pub fn check_access(&self, request: &AccessRequest, user_lemmas: &[VerifiableCredential]) -> Result<bool> {
        self.permission_package.check_access(request, user_lemmas)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_permission_package_creation() {
        let package = PermissionPackage::new("test_site".to_string(), "test.com".to_string());
        assert_eq!(package.package_type(), "permission");
        assert_eq!(package.site_id, "test_site");
    }

    #[test]
    fn test_iam_subnet_manager() {
        let mut manager = IAMSubnetManager::new("test_site".to_string(), "test.com".to_string());
        
        // Test granting permission
        let claims = manager.grant_permission("did:lemma:user123", "admin").unwrap();
        assert_eq!(claims.get("permissionId").unwrap().as_str().unwrap(), "admin");
        assert_eq!(claims.get("siteId").unwrap().as_str().unwrap(), "test_site");
    }

    #[test]
    fn test_standard_permissions() {
        let mut package = PermissionPackage::new("test_site".to_string(), "test.com".to_string());
        package.create_standard_permissions().unwrap();
        
        assert!(package.permission_registry.contains_key("admin"));
        assert!(package.permission_registry.contains_key("user"));
        assert!(package.permission_registry.contains_key("read_only"));
    }
}
