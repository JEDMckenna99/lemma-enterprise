//! Network Partition Handling
//!
//! Provides graceful degradation and sync strategies for offline scenarios

use serde::{Serialize, Deserialize};
use crate::Result;

/// Risk level for determining grace periods
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RiskLevel {
    Low,      // Public content, blogs
    Medium,   // E-commerce, SaaS
    High,     // Banking, healthcare
}

/// Grace period configuration based on risk level
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraceConfig {
    pub max_filter_age_seconds: i64,
    pub max_key_age_seconds: i64,
    pub allow_expired_verification: bool,
    pub warn_on_stale: bool,
    pub risk_level: RiskLevel,
}

impl GraceConfig {
    /// Low-risk configuration (30-day grace periods)
    pub fn low_risk() -> Self {
        Self {
            max_filter_age_seconds: 30 * 24 * 3600,  // 30 days
            max_key_age_seconds: 120 * 24 * 3600,    // 120 days
            allow_expired_verification: true,
            warn_on_stale: true,
            risk_level: RiskLevel::Low,
        }
    }
    
    /// Medium-risk configuration (7-day grace periods)
    pub fn medium_risk() -> Self {
        Self {
            max_filter_age_seconds: 7 * 24 * 3600,   // 7 days
            max_key_age_seconds: 90 * 24 * 3600,     // 90 days
            allow_expired_verification: false,
            warn_on_stale: true,
            risk_level: RiskLevel::Medium,
        }
    }
    
    /// High-risk configuration (24-hour grace periods)
    pub fn high_risk() -> Self {
        Self {
            max_filter_age_seconds: 24 * 3600,       // 24 hours
            max_key_age_seconds: 7 * 24 * 3600,      // 7 days
            allow_expired_verification: false,
            warn_on_stale: true,
            risk_level: RiskLevel::High,
        }
    }
}

/// Filter freshness assessment
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FilterFreshness {
    Fresh,       // < 24 hours
    Acceptable,  // 24 hours - 7 days
    Stale,       // 7 days - 30 days
    Expired,     // > 30 days
}

impl FilterFreshness {
    pub fn from_age(age_seconds: i64) -> Self {
        if age_seconds < 24 * 3600 {
            FilterFreshness::Fresh
        } else if age_seconds < 7 * 24 * 3600 {
            FilterFreshness::Acceptable
        } else if age_seconds < 30 * 24 * 3600 {
            FilterFreshness::Stale
        } else {
            FilterFreshness::Expired
        }
    }
}

/// Verification decision based on network state
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum VerificationDecision {
    Allow,
    AllowWithWarning {
        warning: String,
        filter_age_days: i64,
    },
    Deny {
        reason: String,
        required_action: String,
    },
}

/// Network partition handler
pub struct NetworkPartitionHandler {
    config: GraceConfig,
    last_sync: i64,
}

impl NetworkPartitionHandler {
    pub fn new(config: GraceConfig) -> Self {
        Self {
            config,
            last_sync: 0,
        }
    }
    
    /// Update last sync timestamp
    pub fn record_sync(&mut self) {
        self.last_sync = crate::utils::current_timestamp() as i64;
    }
    
    /// Get filter age in seconds
    pub fn filter_age(&self) -> i64 {
        let now = crate::utils::current_timestamp() as i64;
        now - self.last_sync
    }
    
    /// Check if verification is allowed given current network state
    pub fn check_verification_allowed(&self, _credential_key_version: u32) -> Result<VerificationDecision> {
        let filter_age = self.filter_age();
        
        // Check filter age against configured maximum
        if filter_age > self.config.max_filter_age_seconds {
            if self.config.allow_expired_verification {
                return Ok(VerificationDecision::AllowWithWarning {
                    warning: "Bloom filter expired but verification allowed".to_string(),
                    filter_age_days: filter_age / 86400,
                });
            } else {
                return Ok(VerificationDecision::Deny {
                    reason: "Bloom filter too old, sync required".to_string(),
                    required_action: "Sync bloom filter from server".to_string(),
                });
            }
        }
        
        // All checks passed
        Ok(VerificationDecision::Allow)
    }
    
    /// Determine filter freshness
    pub fn get_filter_freshness(&self) -> FilterFreshness {
        FilterFreshness::from_age(self.filter_age())
    }
    
    /// Check if sync is recommended
    pub fn should_sync(&self) -> bool {
        let age = self.filter_age();
        
        match self.config.risk_level {
            RiskLevel::Low => age > 3 * 24 * 3600,    // Sync every 3 days
            RiskLevel::Medium => age > 24 * 3600,      // Sync daily
            RiskLevel::High => age > 3600,             // Sync hourly
        }
    }
    
    /// Check if sync is required (mandatory)
    pub fn sync_required(&self) -> bool {
        self.filter_age() > self.config.max_filter_age_seconds
    }
}

/// Sync strategy for different scenarios
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SyncStrategy {
    /// Only sync when absolutely necessary
    Lazy,
    /// Sync periodically in background
    Opportunistic,
    /// Always sync before operations
    Aggressive,
}

impl SyncStrategy {
    pub fn for_risk_level(risk: RiskLevel) -> Self {
        match risk {
            RiskLevel::Low => SyncStrategy::Lazy,
            RiskLevel::Medium => SyncStrategy::Opportunistic,
            RiskLevel::High => SyncStrategy::Aggressive,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_grace_config_low_risk() {
        let config = GraceConfig::low_risk();
        assert_eq!(config.max_filter_age_seconds, 30 * 24 * 3600);
        assert_eq!(config.allow_expired_verification, true);
    }

    #[test]
    fn test_grace_config_high_risk() {
        let config = GraceConfig::high_risk();
        assert_eq!(config.max_filter_age_seconds, 24 * 3600);
        assert_eq!(config.allow_expired_verification, false);
    }

    #[test]
    fn test_filter_freshness() {
        assert_eq!(FilterFreshness::from_age(12 * 3600), FilterFreshness::Fresh);
        assert_eq!(FilterFreshness::from_age(3 * 24 * 3600), FilterFreshness::Acceptable);
        assert_eq!(FilterFreshness::from_age(10 * 24 * 3600), FilterFreshness::Stale);
        assert_eq!(FilterFreshness::from_age(40 * 24 * 3600), FilterFreshness::Expired);
    }

    #[test]
    fn test_verification_decision() {
        let mut handler = NetworkPartitionHandler::new(GraceConfig::medium_risk());
        
        // Fresh sync
        handler.record_sync();
        let decision = handler.check_verification_allowed(1).unwrap();
        assert_eq!(decision, VerificationDecision::Allow);
        
        // Simulate old sync (10 days ago)
        handler.last_sync -= 10 * 24 * 3600;
        let decision = handler.check_verification_allowed(1).unwrap();
        assert!(matches!(decision, VerificationDecision::Deny { .. }));
    }
}

