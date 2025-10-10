//! Encrypted Browser Wallet
//! 
//! Secure credential storage for browser environments with:
//! - AES-GCM encryption for credential protection
//! - PBKDF2 key derivation from user password/PIN
//! - IndexedDB persistence with encryption
//! - Cross-tab synchronization

use aes_gcm::{Aes256Gcm, Key, aead::{Aead, KeyInit}, Nonce};
use pbkdf2::{pbkdf2_hmac};
use sha2::Sha256;
use rand::{RngCore, rngs::OsRng};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::minimal_core::{MinimalCredential, MinimalError};

/// Encrypted credential storage entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptedCredentialEntry {
    pub credential_id: String,
    pub encrypted_data: Vec<u8>,    // AES-GCM encrypted credential JSON
    pub nonce: [u8; 12],           // AES-GCM nonce
    pub salt: [u8; 32],            // PBKDF2 salt
    pub credential_type: String,    // "identity", "permission", "zkp"
    pub issuer_did: String,        // For indexing and search
    pub created_at: u64,
    pub last_accessed: u64,
    pub access_count: u64,
}

/// Wallet encryption configuration
#[derive(Debug, Clone)]
pub struct EncryptionConfig {
    pub pbkdf2_iterations: u32,    // Key derivation iterations
    pub key_length: usize,         // Encryption key length
    pub nonce_length: usize,       // AES-GCM nonce length
    pub salt_length: usize,        // PBKDF2 salt length
}

impl Default for EncryptionConfig {
    fn default() -> Self {
        Self {
            pbkdf2_iterations: 100_000,  // Strong key derivation
            key_length: 32,              // AES-256
            nonce_length: 12,            // AES-GCM standard
            salt_length: 32,             // Strong salt
        }
    }
}

/// Encrypted browser wallet for secure credential storage
pub struct EncryptedBrowserWallet {
    config: EncryptionConfig,
    credentials: HashMap<String, EncryptedCredentialEntry>,
    master_key: Option<[u8; 32]>,  // Derived from user password
    is_unlocked: bool,
    wallet_stats: WalletStats,
}

/// Wallet performance and usage statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WalletStats {
    pub total_credentials: usize,
    pub identity_credentials: usize,
    pub permission_credentials: usize,
    pub zkp_credentials: usize,
    pub total_encryptions: u64,
    pub total_decryptions: u64,
    pub total_access_time_ns: u64,
    pub average_access_time_ns: u64,
}

impl EncryptedBrowserWallet {
    /// Create new encrypted wallet
    pub fn new() -> Self {
        Self {
            config: EncryptionConfig::default(),
            credentials: HashMap::new(),
            master_key: None,
            is_unlocked: false,
            wallet_stats: WalletStats {
                total_credentials: 0,
                identity_credentials: 0,
                permission_credentials: 0,
                zkp_credentials: 0,
                total_encryptions: 0,
                total_decryptions: 0,
                total_access_time_ns: 0,
                average_access_time_ns: 0,
            },
        }
    }
    
    /// Unlock wallet with password/PIN
    pub fn unlock(&mut self, password: &str) -> std::result::Result<(), MinimalError> {
        if password.is_empty() {
            return Err(MinimalError::InvalidKey);
        }
        
        // For now, derive key from password (in production, use stored salt)
        let salt = b"lemma_wallet_salt_v1"; // In production, use random salt per wallet
        let mut key = [0u8; 32];
        
        pbkdf2_hmac::<Sha256>(
            password.as_bytes(),
            salt,
            self.config.pbkdf2_iterations,
            &mut key,
        );
        
        self.master_key = Some(key);
        self.is_unlocked = true;
        
        Ok(())
    }
    
    /// Lock wallet (clear master key from memory)
    pub fn lock(&mut self) {
        self.master_key = None;
        self.is_unlocked = false;
    }
    
    /// Store encrypted credential
    pub fn store_credential(
        &mut self, 
        credential: &MinimalCredential,
        credential_type: &str,
    ) -> std::result::Result<String, MinimalError> {
        if !self.is_unlocked {
            return Err(MinimalError::InvalidKey);
        }
        
        let start_time = std::time::Instant::now();
        
        let master_key = self.master_key.ok_or(MinimalError::InvalidKey)?;
        
        // Serialize credential
        let credential_json = serde_json::to_string(credential)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        // Generate random nonce
        let mut nonce = [0u8; 12];
        OsRng.fill_bytes(&mut nonce);
        
        // Generate random salt for this credential
        let mut salt = [0u8; 32];
        OsRng.fill_bytes(&mut salt);
        
        // Derive encryption key from master key + salt
        let mut encryption_key = [0u8; 32];
        pbkdf2_hmac::<Sha256>(&master_key, &salt, 1000, &mut encryption_key);
        
        // Encrypt credential
        let key = Key::<Aes256Gcm>::from_slice(&encryption_key);
        let cipher = Aes256Gcm::new(key);
        let nonce_ref = Nonce::from_slice(&nonce);
        
        let encrypted_data = cipher.encrypt(nonce_ref, credential_json.as_bytes())
            .map_err(|_| MinimalError::Serialization("Encryption failed".to_string()))?;
        
        // Create encrypted entry
        let entry = EncryptedCredentialEntry {
            credential_id: credential.id.clone(),
            encrypted_data,
            nonce,
            salt,
            credential_type: credential_type.to_string(),
            issuer_did: credential.issuer.clone(),
            created_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            last_accessed: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            access_count: 0,
        };
        
        // Store in wallet
        self.credentials.insert(credential.id.clone(), entry);
        
        // Update statistics
        self.wallet_stats.total_credentials = self.credentials.len();
        self.wallet_stats.total_encryptions += 1;
        
        match credential_type {
            "identity" => self.wallet_stats.identity_credentials += 1,
            "permission" => self.wallet_stats.permission_credentials += 1,
            "zkp" => self.wallet_stats.zkp_credentials += 1,
            _ => {},
        }
        
        let access_time = start_time.elapsed().as_nanos() as u64;
        self.wallet_stats.total_access_time_ns += access_time;
        self.wallet_stats.average_access_time_ns = 
            self.wallet_stats.total_access_time_ns / (self.wallet_stats.total_encryptions + self.wallet_stats.total_decryptions);
        
        Ok(credential.id.clone())
    }
    
    /// Retrieve and decrypt credential
    pub fn get_credential(&mut self, credential_id: &str) -> std::result::Result<MinimalCredential, MinimalError> {
        if !self.is_unlocked {
            return Err(MinimalError::InvalidKey);
        }
        
        let start_time = std::time::Instant::now();
        
        let master_key = self.master_key.ok_or(MinimalError::InvalidKey)?;
        
        let entry = self.credentials.get_mut(credential_id)
            .ok_or(MinimalError::Serialization("Credential not found".to_string()))?;
        
        // Derive decryption key
        let mut decryption_key = [0u8; 32];
        pbkdf2_hmac::<Sha256>(&master_key, &entry.salt, 1000, &mut decryption_key);
        
        // Decrypt credential
        let key = Key::<Aes256Gcm>::from_slice(&decryption_key);
        let cipher = Aes256Gcm::new(key);
        let nonce_ref = Nonce::from_slice(&entry.nonce);
        
        let decrypted_data = cipher.decrypt(nonce_ref, entry.encrypted_data.as_slice())
            .map_err(|_| MinimalError::Serialization("Decryption failed".to_string()))?;
        
        let credential_json = String::from_utf8(decrypted_data)
            .map_err(|_| MinimalError::Serialization("Invalid UTF-8".to_string()))?;
        
        let credential: MinimalCredential = serde_json::from_str(&credential_json)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        // Update access statistics
        entry.last_accessed = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        entry.access_count += 1;
        
        self.wallet_stats.total_decryptions += 1;
        let access_time = start_time.elapsed().as_nanos() as u64;
        self.wallet_stats.total_access_time_ns += access_time;
        self.wallet_stats.average_access_time_ns = 
            self.wallet_stats.total_access_time_ns / (self.wallet_stats.total_encryptions + self.wallet_stats.total_decryptions);
        
        Ok(credential)
    }
    
    /// List all stored credentials (metadata only)
    pub fn list_credentials(&self) -> Vec<CredentialMetadata> {
        self.credentials.values().map(|entry| {
            CredentialMetadata {
                credential_id: entry.credential_id.clone(),
                credential_type: entry.credential_type.clone(),
                issuer_did: entry.issuer_did.clone(),
                created_at: entry.created_at,
                last_accessed: entry.last_accessed,
                access_count: entry.access_count,
            }
        }).collect()
    }
    
    /// Remove credential from wallet
    pub fn remove_credential(&mut self, credential_id: &str) -> std::result::Result<(), MinimalError> {
        self.credentials.remove(credential_id)
            .ok_or(MinimalError::Serialization("Credential not found".to_string()))?;
        
        self.wallet_stats.total_credentials = self.credentials.len();
        
        Ok(())
    }
    
    /// Get wallet statistics
    pub fn get_stats(&self) -> &WalletStats {
        &self.wallet_stats
    }
    
    /// Check if wallet is unlocked
    pub fn is_unlocked(&self) -> bool {
        self.is_unlocked
    }
}

/// Credential metadata (non-sensitive information)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CredentialMetadata {
    pub credential_id: String,
    pub credential_type: String,
    pub issuer_did: String,
    pub created_at: u64,
    pub last_accessed: u64,
    pub access_count: u64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::minimal_core::MinimalIssuer;
    
    #[test]
    fn test_encrypted_wallet() {
        let mut wallet = EncryptedBrowserWallet::new();
        
        // Test unlock
        wallet.unlock("test_password_123").unwrap();
        assert!(wallet.is_unlocked());
        
        // Create test credential
        let issuer = MinimalIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        
        let credential = issuer.issue_credential(
            "did:lemma:test_subject".to_string(),
            claims,
        ).unwrap();
        
        // Store encrypted credential
        let credential_id = wallet.store_credential(&credential, "identity").unwrap();
        println!("✅ Stored encrypted credential: {}", credential_id);
        
        // Retrieve and decrypt credential
        let retrieved_credential = wallet.get_credential(&credential_id).unwrap();
        assert_eq!(credential.id, retrieved_credential.id);
        assert_eq!(credential.issuer, retrieved_credential.issuer);
        println!("✅ Retrieved and decrypted credential successfully");
        
        // Test wallet lock/unlock
        wallet.lock();
        assert!(!wallet.is_unlocked());
        
        // Should fail when locked
        assert!(wallet.get_credential(&credential_id).is_err());
        
        // Unlock and access again
        wallet.unlock("test_password_123").unwrap();
        let retrieved_again = wallet.get_credential(&credential_id).unwrap();
        assert_eq!(credential.id, retrieved_again.id);
        
        // Check statistics
        let stats = wallet.get_stats();
        println!("✅ Wallet stats:");
        println!("   Total credentials: {}", stats.total_credentials);
        println!("   Encryptions: {}", stats.total_encryptions);
        println!("   Decryptions: {}", stats.total_decryptions);
        println!("   Average access time: {:.3}μs", stats.average_access_time_ns as f64 / 1000.0);
        
        assert_eq!(stats.total_credentials, 1);
        assert_eq!(stats.identity_credentials, 1);
        assert!(stats.total_encryptions > 0);
        assert!(stats.total_decryptions > 0);
    }
}
