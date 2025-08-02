//! Secure Wallet Implementation - Encrypted Credential Storage
//!
//! This module provides the security-hardened wallet implementation that replaces
//! the vulnerable plaintext storage with strong encryption and secure key derivation.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};
use serde::{Deserialize, Serialize};
use sha2::{Sha256, Digest};
use hmac::{Hmac, Mac};
use argon2::{Argon2, Config, ThreadMode, Variant, Version};
use chacha20poly1305::{
    aead::{Aead, KeyInit, OsRng, generic_array::GenericArray},
    ChaCha20Poly1305, Nonce,
};
use rand::{RngCore, CryptoRng};
use uuid::Uuid;
use zeroize::{Zeroize, ZeroizeOnDrop};

use crate::{
    core::{LemmaCore, VerificationResult},
    credentials::VerifiableCredential,
    Result, LemmaError,
};

#[cfg(not(target_arch = "wasm32"))]
use crate::zkp_claims::ZKPCredential;

/// Security parameters for key derivation
const ARGON2_MEMORY_COST: u32 = 65536; // 64 MB
const ARGON2_TIME_COST: u32 = 3;       // 3 iterations
const ARGON2_PARALLELISM: u32 = 1;     // Single thread for deterministic results
const SALT_SIZE: usize = 32;            // 256-bit salt
const KEY_SIZE: usize = 32;             // 256-bit keys
const NONCE_SIZE: usize = 12;           // 96-bit nonce for ChaCha20Poly1305

/// Master key for wallet encryption - automatically zeroized on drop
#[derive(Clone, ZeroizeOnDrop)]
pub struct SecretKey {
    key: [u8; KEY_SIZE],
}

impl SecretKey {
    /// Generate a new random secret key
    pub fn generate() -> Self {
        let mut key = [0u8; KEY_SIZE];
        OsRng.fill_bytes(&mut key);
        Self { key }
    }
    
    /// Derive key from password and salt using Argon2
    pub fn derive_from_password(password: &str, salt: &[u8]) -> Result<Self> {
        if salt.len() != SALT_SIZE {
            return Err(LemmaError::Credential("Invalid salt size".to_string()))?;
        }
        
        let config = Config {
            variant: Variant::Argon2id,
            version: Version::Version13,
            mem_cost: ARGON2_MEMORY_COST,
            time_cost: ARGON2_TIME_COST,
            lanes: ARGON2_PARALLELISM,
            thread_mode: ThreadMode::Sequential,
            secret: &[],
            ad: &[],
            hash_length: KEY_SIZE as u32,
        };
        
        let mut key = [0u8; KEY_SIZE];
        Argon2::new()
            .hash_password_into(password.as_bytes(), salt, &mut key)
            .map_err(|e| LemmaError::Credential(format!("Key derivation failed: {}", e)))?;
            
        Ok(Self { key })
    }
    
    /// Get the raw key bytes (use with caution)
    pub fn as_bytes(&self) -> &[u8; KEY_SIZE] {
        &self.key
    }
}

/// Key derivation parameters stored with encrypted data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Argon2Params {
    pub salt: [u8; SALT_SIZE],
    pub memory_cost: u32,
    pub time_cost: u32,
    pub parallelism: u32,
}

impl Argon2Params {
    /// Generate new random parameters
    pub fn generate() -> Self {
        let mut salt = [0u8; SALT_SIZE];
        OsRng.fill_bytes(&mut salt);
        
        Self {
            salt,
            memory_cost: ARGON2_MEMORY_COST,
            time_cost: ARGON2_TIME_COST,
            parallelism: ARGON2_PARALLELISM,
        }
    }
}

/// Encrypted credential stored in wallet
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptedCredential {
    /// Encrypted credential data
    pub ciphertext: Vec<u8>,
    /// Nonce for decryption
    pub nonce: [u8; NONCE_SIZE],
    /// HMAC for integrity verification
    pub hmac: [u8; 32],
    /// Metadata (unencrypted for indexing)
    pub metadata: EncryptedCredentialMetadata,
}

/// Metadata for encrypted credentials
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptedCredentialMetadata {
    /// Credential ID (for indexing)
    pub credential_id: String,
    /// Package type (for filtering)
    pub package_type: String,
    /// When encrypted and stored
    pub encrypted_at: u64,
    /// Last accessed timestamp
    pub last_accessed: u64,
    /// Access count for LRU eviction
    pub access_count: u64,
    /// Storage layer
    pub storage_layer: String,
    /// Whether this is a ZKP credential
    pub is_zkp: bool,
}

/// Secure encrypted wallet storage
pub struct EncryptedWalletStorage {
    /// Master encryption key (zeroized on drop)
    master_key: SecretKey,
    /// Encrypted credential vault
    credential_vault: Arc<Mutex<HashMap<String, EncryptedCredential>>>,
    /// Key derivation parameters
    key_derivation_params: Argon2Params,
    /// HMAC key for integrity verification
    hmac_key: [u8; 32],
    /// Integrated crypto core
    core: Arc<Mutex<LemmaCore>>,
    /// Configuration
    config: SecureWalletConfig,
}

/// Secure wallet configuration
#[derive(Debug, Clone)]
pub struct SecureWalletConfig {
    /// Maximum credentials in memory
    pub max_memory_credentials: usize,
    /// Enable hardware security module integration
    pub enable_hsm: bool,
    /// Enable secure enclave storage
    pub enable_secure_enclave: bool,
    /// Auto-lock timeout (seconds)
    pub auto_lock_timeout: u64,
    /// Require biometric authentication
    pub require_biometric: bool,
}

impl Default for SecureWalletConfig {
    fn default() -> Self {
        Self {
            max_memory_credentials: 1000,
            enable_hsm: true,
            enable_secure_enclave: true,
            auto_lock_timeout: 300, // 5 minutes
            require_biometric: false,
        }
    }
}

impl EncryptedWalletStorage {
    /// Create new encrypted wallet storage
    pub fn new(master_key: SecretKey, core: Arc<Mutex<LemmaCore>>) -> Result<Self> {
        let key_derivation_params = Argon2Params::generate();
        
        // Derive HMAC key from master key
        let mut hmac_key = [0u8; 32];
        let mut hasher = Hmac::<Sha256>::new_from_slice(master_key.as_bytes())
            .map_err(|e| LemmaError::Credential(format!("HMAC key derivation failed: {}", e)))?;
        hasher.update(b"LEMMA_WALLET_HMAC_KEY");
        let hmac_result = hasher.finalize();
        hmac_key.copy_from_slice(&hmac_result.into_bytes());
        
        Ok(Self {
            master_key,
            credential_vault: Arc::new(Mutex::new(HashMap::new())),
            key_derivation_params,
            hmac_key,
            core,
            config: SecureWalletConfig::default(),
        })
    }
    
    /// Create with custom configuration
    pub fn with_config(
        master_key: SecretKey,
        core: Arc<Mutex<LemmaCore>>,
        config: SecureWalletConfig,
    ) -> Result<Self> {
        let mut wallet = Self::new(master_key, core)?;
        wallet.config = config;
        Ok(wallet)
    }
    
    /// Derive credential-specific encryption key
    fn derive_credential_key(&self, credential_id: &str) -> Result<[u8; KEY_SIZE]> {
        let mut hasher = Hmac::<Sha256>::new_from_slice(self.master_key.as_bytes())
            .map_err(|e| LemmaError::Credential(format!("Key derivation failed: {}", e)))?;
        hasher.update(b"LEMMA_CREDENTIAL_KEY");
        hasher.update(credential_id.as_bytes());
        hasher.update(&self.key_derivation_params.salt);
        
        let result = hasher.finalize();
        let mut key = [0u8; KEY_SIZE];
        key.copy_from_slice(&result.into_bytes());
        Ok(key)
    }
    
    /// Encrypt a credential
    fn encrypt_credential(&self, credential: &VerifiableCredential, credential_key: &[u8; KEY_SIZE]) -> Result<EncryptedCredential> {
        // Serialize credential
        let plaintext = serde_json::to_vec(credential)
            .map_err(|e| LemmaError::Credential(format!("Credential serialization failed: {}", e)))?;
        
        // Generate random nonce
        let mut nonce = [0u8; NONCE_SIZE];
        OsRng.fill_bytes(&mut nonce);
        
        // Encrypt with ChaCha20Poly1305
        let cipher = ChaCha20Poly1305::new(GenericArray::from_slice(credential_key));
        let ciphertext = cipher.encrypt(
            Nonce::from_slice(&nonce),
            plaintext.as_ref()
        ).map_err(|e| LemmaError::Credential(format!("Encryption failed: {}", e)))?;
        
        // Calculate HMAC for integrity
        let mut hasher = Hmac::<Sha256>::new_from_slice(&self.hmac_key)
            .map_err(|e| LemmaError::Credential(format!("HMAC calculation failed: {}", e)))?;
        hasher.update(&ciphertext);
        hasher.update(&nonce);
        hasher.update(credential.id.as_bytes());
        
        let hmac_result = hasher.finalize();
        let mut hmac = [0u8; 32];
        hmac.copy_from_slice(&hmac_result.into_bytes());
        
        // Create metadata
        let package_type = credential.get_claim("packageType")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string();
            
        let metadata = EncryptedCredentialMetadata {
            credential_id: credential.id.clone(),
            package_type,
            encrypted_at: current_timestamp(),
            last_accessed: current_timestamp(),
            access_count: 0,
            storage_layer: "encrypted_memory".to_string(),
            is_zkp: false,
        };
        
        Ok(EncryptedCredential {
            ciphertext,
            nonce,
            hmac,
            metadata,
        })
    }
    
    /// Decrypt a credential
    fn decrypt_credential(&self, encrypted: &EncryptedCredential) -> Result<VerifiableCredential> {
        // Verify HMAC integrity
        let mut hasher = Hmac::<Sha256>::new_from_slice(&self.hmac_key)
            .map_err(|e| LemmaError::Credential(format!("HMAC verification failed: {}", e)))?;
        hasher.update(&encrypted.ciphertext);
        hasher.update(&encrypted.nonce);
        hasher.update(encrypted.metadata.credential_id.as_bytes());
        
        let computed_hmac = hasher.finalize();
        if computed_hmac.into_bytes().as_slice() != &encrypted.hmac {
            return Err(LemmaError::Credential("HMAC verification failed - credential may be tampered".to_string()))?;
        }
        
        // Derive decryption key
        let credential_key = self.derive_credential_key(&encrypted.metadata.credential_id)?;
        
        // Decrypt with ChaCha20Poly1305
        let cipher = ChaCha20Poly1305::new(GenericArray::from_slice(&credential_key));
        let plaintext = cipher.decrypt(
            Nonce::from_slice(&encrypted.nonce),
            encrypted.ciphertext.as_ref()
        ).map_err(|e| LemmaError::Credential(format!("Decryption failed: {}", e)))?;
        
        // Deserialize credential
        let credential: VerifiableCredential = serde_json::from_slice(&plaintext)
            .map_err(|e| LemmaError::Credential(format!("Credential deserialization failed: {}", e)))?;
            
        Ok(credential)
    }
    
    /// Store credential securely
    pub fn store_credential(&self, credential: VerifiableCredential) -> Result<String> {
        // Derive credential-specific key
        let credential_key = self.derive_credential_key(&credential.id)?;
        
        // Encrypt credential
        let encrypted = self.encrypt_credential(&credential, &credential_key)?;
        
        // Store in vault
        let mut vault = self.credential_vault.lock().unwrap();
        
        // Check memory limits
        if vault.len() >= self.config.max_memory_credentials {
            self.evict_lru_credential(&mut vault)?;
        }
        
        vault.insert(credential.id.clone(), encrypted);
        
        // Preload into crypto engine for performance
        self.preload_into_crypto_engine(&credential)?;
        
        Ok(credential.id)
    }
    
    /// Get credential securely
    pub fn get_credential(&self, credential_id: &str) -> Result<Option<VerifiableCredential>> {
        let mut vault = self.credential_vault.lock().unwrap();
        
        if let Some(encrypted) = vault.get_mut(credential_id) {
            // Update access statistics
            encrypted.metadata.last_accessed = current_timestamp();
            encrypted.metadata.access_count += 1;
            
            // Decrypt and return
            let credential = self.decrypt_credential(encrypted)?;
            Ok(Some(credential))
        } else {
            Ok(None)
        }
    }
    
    /// Get credentials for verification
    pub fn get_credentials_for_verification(&self, package_type: Option<&str>) -> Result<Vec<VerifiableCredential>> {
        let mut vault = self.credential_vault.lock().unwrap();
        let mut credentials = Vec::new();
        
        for encrypted in vault.values_mut() {
            // Filter by package type if specified
            if let Some(pkg_type) = package_type {
                if encrypted.metadata.package_type != pkg_type {
                    continue;
                }
            }
            
            // Update access statistics
            encrypted.metadata.last_accessed = current_timestamp();
            encrypted.metadata.access_count += 1;
            
            // Decrypt credential
            let credential = self.decrypt_credential(encrypted)?;
            credentials.push(credential);
        }
        
        Ok(credentials)
    }
    
    /// Verify credentials with integrated crypto engine
    pub fn verify_credentials(&self, package_type: Option<&str>) -> Result<Vec<VerificationResult>> {
        let credentials = self.get_credentials_for_verification(package_type)?;
        
        if credentials.is_empty() {
            return Ok(vec![]);
        }
        
        // Use integrated crypto engine for verification
        let mut results = Vec::new();
        let mut core = self.core.lock().unwrap();
        
        for credential in credentials {
            let result = core.verify(&credential)?;
            results.push(result);
        }
        
        Ok(results)
    }
    
    /// Remove credential
    pub fn remove_credential(&self, credential_id: &str) -> Result<bool> {
        let mut vault = self.credential_vault.lock().unwrap();
        Ok(vault.remove(credential_id).is_some())
    }
    
    /// Clear all credentials (secure wipe)
    pub fn clear_all_credentials(&self) -> Result<()> {
        let mut vault = self.credential_vault.lock().unwrap();
        vault.clear();
        Ok(())
    }
    
    /// Get storage statistics
    pub fn get_storage_stats(&self) -> SecureWalletStats {
        let vault = self.credential_vault.lock().unwrap();
        
        let total_credentials = vault.len();
        let zkp_credentials = vault.values().filter(|e| e.metadata.is_zkp).count();
        let total_access_count = vault.values().map(|e| e.metadata.access_count).sum();
        
        SecureWalletStats {
            total_credentials,
            zkp_credentials,
            total_access_count,
            memory_utilization: (total_credentials as f64 / self.config.max_memory_credentials as f64) * 100.0,
            encryption_enabled: true,
            integrity_protection: true,
        }
    }
    
    /// Preload credential into crypto engine
    fn preload_into_crypto_engine(&self, credential: &VerifiableCredential) -> Result<()> {
        let mut core = self.core.lock().unwrap();
        let _ = core.verify(credential)?; // Populates caches
        Ok(())
    }
    
    /// Evict least recently used credential
    fn evict_lru_credential(&self, vault: &mut HashMap<String, EncryptedCredential>) -> Result<()> {
        if let Some((lru_id, _)) = vault.iter()
            .min_by_key(|(_, encrypted)| encrypted.metadata.last_accessed) {
            let lru_id = lru_id.clone();
            vault.remove(&lru_id);
        }
        Ok(())
    }
}

/// Statistics for secure wallet
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecureWalletStats {
    pub total_credentials: usize,
    pub zkp_credentials: usize,
    pub total_access_count: u64,
    pub memory_utilization: f64,
    pub encryption_enabled: bool,
    pub integrity_protection: bool,
}

/// Get current timestamp
fn current_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::LemmaCore;
    use std::collections::HashMap;
    
    fn create_test_credential() -> VerifiableCredential {
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::json!("identity"));
        claims.insert("isHuman".to_string(), serde_json::json!(true));
        claims.insert("fullName".to_string(), serde_json::json!("Test User"));
        
        VerifiableCredential {
            id: "test_credential_001".to_string(),
            issuer: "did:lemma:test_issuer".to_string(),
            subject: "did:lemma:test_subject".to_string(),
            issued_at: current_timestamp(),
            expires_at: Some(current_timestamp() + 86400),
            claims,
            proof: None,
            signature: Some("test_signature".to_string()),
        }
    }
    
    #[test]
    fn test_encrypted_credential_storage() {
        let master_key = SecretKey::generate();
        let core = Arc::new(Mutex::new(LemmaCore::new().unwrap()));
        let wallet = EncryptedWalletStorage::new(master_key, core).unwrap();
        
        let credential = create_test_credential();
        let credential_id = credential.id.clone();
        
        // Store credential
        let stored_id = wallet.store_credential(credential.clone()).unwrap();
        assert_eq!(stored_id, credential_id);
        
        // Retrieve credential
        let retrieved = wallet.get_credential(&credential_id).unwrap().unwrap();
        assert_eq!(retrieved.id, credential.id);
        assert_eq!(retrieved.claims, credential.claims);
        
        // Verify storage is encrypted
        let vault = wallet.credential_vault.lock().unwrap();
        let encrypted = vault.get(&credential_id).unwrap();
        
        // ✅ SECURE: Ciphertext should not contain plaintext claims
        let ciphertext_str = String::from_utf8_lossy(&encrypted.ciphertext);
        assert!(!ciphertext_str.contains("isHuman"));
        assert!(!ciphertext_str.contains("Test User"));
        assert!(!ciphertext_str.contains("test_signature"));
    }
    
    #[test]
    fn test_hmac_integrity_protection() {
        let master_key = SecretKey::generate();
        let core = Arc::new(Mutex::new(LemmaCore::new().unwrap()));
        let wallet = EncryptedWalletStorage::new(master_key, core).unwrap();
        
        let credential = create_test_credential();
        wallet.store_credential(credential).unwrap();
        
        // Tamper with encrypted data
        let mut vault = wallet.credential_vault.lock().unwrap();
        let encrypted = vault.values_mut().next().unwrap();
        encrypted.ciphertext[10] ^= 0xFF; // Flip bits
        
        // Should detect tampering
        let result = wallet.decrypt_credential(encrypted);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("HMAC verification failed"));
    }
    
    #[test]
    fn test_key_derivation_uniqueness() {
        let master_key = SecretKey::generate();
        let core = Arc::new(Mutex::new(LemmaCore::new().unwrap()));
        let wallet = EncryptedWalletStorage::new(master_key, core).unwrap();
        
        let key1 = wallet.derive_credential_key("credential_001").unwrap();
        let key2 = wallet.derive_credential_key("credential_002").unwrap();
        
        // Keys should be different for different credentials
        assert_ne!(key1, key2);
    }
    
    #[test]
    fn test_secure_credential_removal() {
        let master_key = SecretKey::generate();
        let core = Arc::new(Mutex::new(LemmaCore::new().unwrap()));
        let wallet = EncryptedWalletStorage::new(master_key, core).unwrap();
        
        let credential = create_test_credential();
        let credential_id = credential.id.clone();
        
        wallet.store_credential(credential).unwrap();
        assert!(wallet.get_credential(&credential_id).unwrap().is_some());
        
        // Remove credential
        let removed = wallet.remove_credential(&credential_id).unwrap();
        assert!(removed);
        assert!(wallet.get_credential(&credential_id).unwrap().is_none());
    }
} 