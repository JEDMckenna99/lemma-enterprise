//! OPRF Key Management with Rotation Support
//!
//! Handles versioned OPRF keys with secure rotation and graceful transitions.

use std::collections::HashMap;
use serde::{Serialize, Deserialize};
use crate::Result;

const KEY_SIZE: usize = 32;

/// OPRF key lifecycle status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum KeyStatus {
    /// Generated but not yet active
    Pending,
    /// Currently signing new credentials
    Active,
    /// Valid but being phased out (grace period)
    Rotating,
    /// Only for verification, no new signatures
    Deprecated,
    /// Compromised - reject all usage
    Revoked,
}

/// Type of OPRF key
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum KeyType {
    /// Global federated identity network
    Network,
    /// Site-specific IAM
    Site(String),
}

/// Versioned OPRF key
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OPRFKeyVersion {
    pub version: u32,
    pub key_material: [u8; KEY_SIZE],
    pub created_at: i64,
    pub valid_from: i64,
    pub valid_until: i64,
    pub status: KeyStatus,
    pub key_type: KeyType,
}

/// Key rotation plan
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RotationPlan {
    pub old_version: u32,
    pub new_version: u32,
    pub grace_period_days: i64,
    pub estimated_completion: i64,
}

/// Errors related to OPRF key management
#[derive(Debug, thiserror::Error)]
pub enum OPRFKeyError {
    #[error("Key not found: version {0}")]
    KeyNotFound(u32),
    #[error("Key expired: version {0}")]
    KeyExpired(u32),
    #[error("Key revoked: version {0}")]
    KeyRevoked(u32),
    #[error("Key not yet active: version {0}")]
    KeyNotYetActive(u32),
    #[error("Key generation failed")]
    KeyGenerationFailed,
    #[error("Invalid key version")]
    InvalidKeyVersion,
    #[error("No active key")]
    NoActiveKey,
}

/// OPRF Key Manager
pub struct OPRFKeyManager {
    keys: HashMap<u32, OPRFKeyVersion>,
    current_active_version: u32,
    key_type: KeyType,
}

impl OPRFKeyManager {
    /// Create new key manager
    pub fn new(key_type: KeyType) -> Self {
        Self {
            keys: HashMap::new(),
            current_active_version: 0,
            key_type,
        }
    }

    /// Generate a new OPRF key version
    pub fn generate_new_version(&mut self) -> Result<u32> {
        let new_version = self.current_active_version + 1;
        let key_material = Self::generate_secure_key()?;
        
        let now = crate::utils::current_timestamp() as i64;
        let key_version = OPRFKeyVersion {
            version: new_version,
            key_material,
            created_at: now,
            valid_from: now + (7 * 24 * 3600), // 7-day pending period
            valid_until: now + (365 * 24 * 3600), // 1-year validity
            status: KeyStatus::Pending,
            key_type: self.key_type.clone(),
        };
        
        self.keys.insert(new_version, key_version);
        Ok(new_version)
    }

    /// Activate a pending key (initiate rotation)
    pub fn activate_key(&mut self, new_version: u32) -> Result<RotationPlan> {
        // Mark current key as rotating
        let old_version = self.current_active_version;
        if old_version > 0 {
            if let Some(current_key) = self.keys.get_mut(&old_version) {
                current_key.status = KeyStatus::Rotating;
                let now = crate::utils::current_timestamp() as i64;
                current_key.valid_until = now + (90 * 24 * 3600); // 90-day grace
            }
        }
        
        // Activate new key
        if let Some(new_key) = self.keys.get_mut(&new_version) {
            let now = crate::utils::current_timestamp() as i64;
            new_key.status = KeyStatus::Active;
            new_key.valid_from = now;
            self.current_active_version = new_version;
            
            Ok(RotationPlan {
                old_version,
                new_version,
                grace_period_days: 90,
                estimated_completion: now + (90 * 24 * 3600),
            })
        } else {
            Err(crate::LemmaError::OPRF("Key not found".to_string()))
        }
    }

    /// Get key for signing (only active key)
    pub fn get_active_key(&self) -> Result<[u8; KEY_SIZE]> {
        if self.current_active_version == 0 {
            return Err(crate::LemmaError::OPRF("No active key".to_string()));
        }
        
        if let Some(key) = self.keys.get(&self.current_active_version) {
            if key.status == KeyStatus::Active {
                Ok(key.key_material)
            } else {
                Err(crate::LemmaError::OPRF("No active key".to_string()))
            }
        } else {
            Err(crate::LemmaError::OPRF("Key not found".to_string()))
        }
    }

    /// Get key for verification (supports old versions during grace period)
    pub fn get_key_for_verification(&self, version: u32) -> Result<[u8; KEY_SIZE]> {
        if let Some(key) = self.keys.get(&version) {
            let now = crate::utils::current_timestamp() as i64;
            
            match key.status {
                KeyStatus::Active | KeyStatus::Rotating | KeyStatus::Deprecated => {
                    // Check if still within valid period
                    if now >= key.valid_from && now <= key.valid_until {
                        Ok(key.key_material)
                    } else if now < key.valid_from {
                        return Err(crate::LemmaError::OPRF("Key not yet active".to_string()));
                    } else {
                        return Err(crate::LemmaError::OPRF("Key expired".to_string()));
                    }
                }
                KeyStatus::Revoked => {
                    return Err(crate::LemmaError::OPRF("Key revoked".to_string()));
                }
                KeyStatus::Pending => {
                    return Err(crate::LemmaError::OPRF("Key not yet active".to_string()));
                }
            }
        } else {
            Err(crate::LemmaError::OPRF("Key not found".to_string()))
        }
    }

    /// Emergency key revocation
    pub fn revoke_key(&mut self, version: u32, reason: &str) -> Result<()> {
        if let Some(key) = self.keys.get_mut(&version) {
            key.status = KeyStatus::Revoked;
            let now = crate::utils::current_timestamp() as i64;
            key.valid_until = now; // Immediate expiration
            
            // Log revocation (in production, send to audit system)
            eprintln!("🚨 OPRF Key {} revoked: {}", version, reason);
            
            // If revoking active key, immediately activate next version
            if version == self.current_active_version {
                let new_version = self.generate_new_version()?;
                self.activate_key(new_version)?;
            }
            
            Ok(())
        } else {
            Err(crate::LemmaError::OPRF("Key not found".to_string()))
        }
    }

    /// Get current active version number
    pub fn get_active_version(&self) -> u32 {
        self.current_active_version
    }

    /// Get all supported versions for verification
    pub fn get_supported_versions(&self) -> Vec<u32> {
        let now = crate::utils::current_timestamp() as i64;
        self.keys
            .iter()
            .filter(|(_, key)| {
                matches!(key.status, KeyStatus::Active | KeyStatus::Rotating | KeyStatus::Deprecated)
                    && now >= key.valid_from
                    && now <= key.valid_until
            })
            .map(|(version, _)| *version)
            .collect()
    }

    /// Complete key rotation (mark old key as deprecated)
    pub fn complete_rotation(&mut self, old_version: u32) -> Result<()> {
        if let Some(old_key) = self.keys.get_mut(&old_version) {
            if old_key.status == KeyStatus::Rotating {
                old_key.status = KeyStatus::Deprecated;
                Ok(())
            } else {
                Err(crate::LemmaError::OPRF("Invalid key version".to_string()))
            }
        } else {
            Err(crate::LemmaError::OPRF("Key not found".to_string()))
        }
    }

    /// Generate cryptographically secure random key
    fn generate_secure_key() -> Result<[u8; KEY_SIZE]> {
        let mut key = [0u8; KEY_SIZE];
        
        #[cfg(feature = "ring")]
        {
            use ring::rand::{SystemRandom, SecureRandom};
            let rng = SystemRandom::new();
            rng.fill(&mut key)
                .map_err(|_| crate::LemmaError::OPRF("Key generation failed".to_string()))?;
        }
        
        #[cfg(not(feature = "ring"))]
        {
            use rand::RngCore;
            let mut rng = rand::thread_rng();
            rng.fill_bytes(&mut key);
        }
        
        Ok(key)
    }

    /// Get key metadata (for API responses)
    pub fn get_key_metadata(&self, version: u32) -> Option<&OPRFKeyVersion> {
        self.keys.get(&version)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_key_generation() {
        let mut manager = OPRFKeyManager::new(KeyType::Network);
        let version = manager.generate_new_version().unwrap();
        assert_eq!(version, 1);
        
        let key_meta = manager.get_key_metadata(version).unwrap();
        assert_eq!(key_meta.status, KeyStatus::Pending);
    }

    #[test]
    fn test_key_rotation() {
        let mut manager = OPRFKeyManager::new(KeyType::Network);
        
        // Generate and activate first key
        let v1 = manager.generate_new_version().unwrap();
        manager.activate_key(v1).unwrap();
        assert_eq!(manager.get_active_version(), 1);
        
        // Generate and activate second key (rotation)
        let v2 = manager.generate_new_version().unwrap();
        let plan = manager.activate_key(v2).unwrap();
        assert_eq!(plan.old_version, 1);
        assert_eq!(plan.new_version, 2);
        assert_eq!(manager.get_active_version(), 2);
        
        // Old key should still be verifiable during grace period
        let old_key = manager.get_key_for_verification(v1).unwrap();
        assert_eq!(old_key.len(), KEY_SIZE);
    }

    #[test]
    fn test_key_revocation() {
        let mut manager = OPRFKeyManager::new(KeyType::Network);
        
        let v1 = manager.generate_new_version().unwrap();
        manager.activate_key(v1).unwrap();
        
        // Revoke key
        manager.revoke_key(v1, "test revocation").unwrap();
        
        // Should not be able to verify with revoked key
        assert!(manager.get_key_for_verification(v1).is_err());
        
        // Should have auto-generated new active key
        assert!(manager.get_active_version() > v1);
    }
}

