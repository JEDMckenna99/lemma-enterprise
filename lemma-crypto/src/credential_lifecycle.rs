//! Credential Lifecycle Management
//!
//! Handles credential expiration, renewal, and lifecycle state transitions

use serde::{Serialize, Deserialize};
use crate::minimal_core::MinimalCredential;

/// Credential lifecycle state
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CredentialState {
    /// Valid and usable
    Valid,
    /// Expiring soon (< 30 days)
    ExpiringSoon,
    /// Expired but within grace period
    Expired,
    /// Revoked by issuer
    Revoked,
    /// Invalid (failed verification)
    Invalid,
}

/// Credential lifecycle manager
pub struct CredentialLifecycleManager {
    grace_period_seconds: i64,
    expiry_warning_seconds: i64,
}

impl CredentialLifecycleManager {
    pub fn new() -> Self {
        Self {
            grace_period_seconds: 7 * 24 * 3600,  // 7-day grace period
            expiry_warning_seconds: 30 * 24 * 3600, // Warn 30 days before expiry
        }
    }
    
    /// Check credential temporal state
    pub fn check_state(&self, credential: &MinimalCredential) -> CredentialState {
        let now = crate::utils::current_timestamp() as i64;
        
        // Check if expired
        if let Some(expires_at) = credential.expires_at {
            let expires_at_i64 = expires_at as i64;
            
            if now > expires_at_i64 {
                // Expired - check if within grace period
                let expired_for = now - expires_at_i64;
                if expired_for <= self.grace_period_seconds {
                    return CredentialState::Expired;
                } else {
                    return CredentialState::Invalid;
                }
            }
            
            // Check if expiring soon
            let time_until_expiry = expires_at_i64 - now;
            if time_until_expiry <= self.expiry_warning_seconds {
                return CredentialState::ExpiringSoon;
            }
        }
        
        // Not expired, not expiring soon
        CredentialState::Valid
    }
    
    /// Check if credential needs renewal
    pub fn needs_renewal(&self, credential: &MinimalCredential) -> bool {
        matches!(
            self.check_state(credential),
            CredentialState::ExpiringSoon | CredentialState::Expired
        )
    }
    
    /// Get time until expiry (seconds)
    pub fn time_until_expiry(&self, credential: &MinimalCredential) -> Option<i64> {
        credential.expires_at.map(|expires_at| {
            let now = crate::utils::current_timestamp() as i64;
            let expires_at_i64 = expires_at as i64;
            expires_at_i64 - now
        })
    }
    
    /// Get days until expiry
    pub fn days_until_expiry(&self, credential: &MinimalCredential) -> Option<i64> {
        self.time_until_expiry(credential).map(|seconds| seconds / 86400)
    }
    
    /// Check if credential is within grace period
    pub fn is_in_grace_period(&self, credential: &MinimalCredential) -> bool {
        if let Some(expires_at) = credential.expires_at {
            let now = crate::utils::current_timestamp() as i64;
            let expires_at_i64 = expires_at as i64;
            if now > expires_at_i64 {
                let expired_for = now - expires_at_i64;
                return expired_for <= self.grace_period_seconds;
            }
        }
        false
    }
}

impl Default for CredentialLifecycleManager {
    fn default() -> Self {
        Self::new()
    }
}

/// Renewal policy configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RenewalPolicy {
    /// How long before expiry to allow renewal
    pub renewal_window_seconds: i64,
    /// Whether to allow renewal of expired credentials
    pub allow_expired_renewal: bool,
    /// Maximum age for expired credential renewal
    pub max_expired_renewal_age_seconds: i64,
}

impl RenewalPolicy {
    /// Standard renewal policy
    pub fn standard() -> Self {
        Self {
            renewal_window_seconds: 30 * 24 * 3600,  // 30 days before expiry
            allow_expired_renewal: true,
            max_expired_renewal_age_seconds: 7 * 24 * 3600,  // 7 days after expiry
        }
    }
    
    /// Strict renewal policy (no expired renewal)
    pub fn strict() -> Self {
        Self {
            renewal_window_seconds: 60 * 24 * 3600,  // 60 days before expiry
            allow_expired_renewal: false,
            max_expired_renewal_age_seconds: 0,
        }
    }
    
    /// Check if credential can be renewed
    pub fn can_renew(&self, credential: &MinimalCredential) -> bool {
        if let Some(expires_at) = credential.expires_at {
            let now = crate::utils::current_timestamp() as i64;
            let expires_at_i64 = expires_at as i64;
            
            // Check if in renewal window (before expiry)
            if now < expires_at_i64 {
                let time_until_expiry = expires_at_i64 - now;
                return time_until_expiry <= self.renewal_window_seconds;
            }
            
            // Check if expired but still renewable
            if self.allow_expired_renewal {
                let expired_for = now - expires_at_i64;
                return expired_for <= self.max_expired_renewal_age_seconds;
            }
        }
        
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_credential_state_valid() {
        let manager = CredentialLifecycleManager::new();
        
        let now = crate::utils::current_timestamp() as i64;
        let credential = MinimalCredential {
            id: "test".to_string(),
            issuer: "issuer".to_string(),
            subject: "subject".to_string(),
            claims: serde_json::json!({}),
            signature: [0u8; 64],
            issued_at: now - 1000,
            expires_at: Some(now + 100000), // Far future
        };
        
        assert_eq!(manager.check_state(&credential), CredentialState::Valid);
    }

    #[test]
    fn test_credential_state_expiring_soon() {
        let manager = CredentialLifecycleManager::new();
        
        let now = crate::utils::current_timestamp() as i64;
        let credential = MinimalCredential {
            id: "test".to_string(),
            issuer: "issuer".to_string(),
            subject: "subject".to_string(),
            claims: serde_json::json!({}),
            signature: [0u8; 64],
            issued_at: now - 1000,
            expires_at: Some(now + 20 * 24 * 3600), // 20 days (< 30 day warning)
        };
        
        assert_eq!(manager.check_state(&credential), CredentialState::ExpiringSoon);
    }

    #[test]
    fn test_credential_state_expired() {
        let manager = CredentialLifecycleManager::new();
        
        let now = crate::utils::current_timestamp() as i64;
        let credential = MinimalCredential {
            id: "test".to_string(),
            issuer: "issuer".to_string(),
            subject: "subject".to_string(),
            claims: serde_json::json!({}),
            signature: [0u8; 64],
            issued_at: now - 10000,
            expires_at: Some(now - 1000), // Expired 1000 seconds ago (within grace)
        };
        
        assert_eq!(manager.check_state(&credential), CredentialState::Expired);
    }

    #[test]
    fn test_renewal_policy() {
        let policy = RenewalPolicy::standard();
        
        let now = crate::utils::current_timestamp() as i64;
        
        // Credential expiring in 20 days (within 30-day window)
        let credential = MinimalCredential {
            id: "test".to_string(),
            issuer: "issuer".to_string(),
            subject: "subject".to_string(),
            claims: serde_json::json!({}),
            signature: [0u8; 64],
            issued_at: now,
            expires_at: Some(now + 20 * 24 * 3600),
        };
        
        assert!(policy.can_renew(&credential));
    }
}

