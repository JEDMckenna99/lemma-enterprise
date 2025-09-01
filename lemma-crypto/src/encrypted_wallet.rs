//! Encrypted Browser Wallet - Enhanced Security for Credential Storage
//!
//! This module provides client-side encryption for browser wallet storage,
//! building on top of the existing Ed25519 tamper protection.

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use aes_gcm::{Aes256Gcm, Key, Nonce, AeadInPlace, KeyInit};
use sha2::{Sha256, Digest};
use rand::{RngCore, rngs::OsRng};
use pbkdf2::pbkdf2_hmac;

use crate::{
    credentials::VerifiableCredential,
    wallet::{WalletCredentialEntry, WalletCredentialMetadata, WalletStorage, PrivacyLevel},
    Result, LemmaError,
};

/// Encrypted credential storage entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptedCredentialEntry {
    /// Encrypted credential data
    pub encrypted_data: Vec<u8>,
    /// Encryption nonce/IV
    pub nonce: [u8; 12],
    /// Salt for key derivation
    pub salt: [u8; 32],
    /// Credential metadata (not encrypted for indexing)
    pub metadata: EncryptedCredentialMetadata,
}

/// Metadata for encrypted credentials (safe to store unencrypted)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptedCredentialMetadata {
    /// Credential ID (for indexing)
    pub credential_id: String,
    /// Package type (for filtering)
    pub package_type: String,
    /// Storage timestamp
    pub stored_at: u64,
    /// Last accessed timestamp
    pub last_accessed: u64,
    /// Whether this is a PoH lemma (universal) or permission lemma (site-specific)
    pub lemma_type: String, // "poh" or "permission"
    /// Site ID for permission lemmas (None for PoH)
    pub site_id: Option<String>,
    /// Encryption version for future upgrades
    pub encryption_version: u32,
}

/// Browser wallet with client-side encryption
pub struct EncryptedBrowserWallet {
    /// Encryption key derived from user PIN
    encryption_key: Option<Key<Aes256Gcm>>,
    /// User PIN hash for verification
    pin_hash: Option<[u8; 32]>,
    /// Encrypted storage
    encrypted_storage: HashMap<String, EncryptedCredentialEntry>,
    /// Memory cache for decrypted credentials (cleared on lock)
    memory_cache: HashMap<String, WalletCredentialEntry>,
    /// Wallet locked state
    is_locked: bool,
}

impl EncryptedBrowserWallet {
    /// Create new encrypted wallet
    pub fn new() -> Self {
        Self {
            encryption_key: None,
            pin_hash: None,
            encrypted_storage: HashMap::new(),
            memory_cache: HashMap::new(),
            is_locked: true,
        }
    }

    /// Initialize wallet with user PIN
    pub fn initialize_with_pin(&mut self, pin: &str) -> Result<()> {
        // Generate random salt for this wallet
        let mut salt = [0u8; 32];
        OsRng.fill_bytes(&mut salt);
        
        // Derive encryption key from PIN using PBKDF2
        let mut key_bytes = [0u8; 32];
        pbkdf2_hmac::<Sha256>(pin.as_bytes(), &salt, 100_000, &mut key_bytes);
        
        // Create AES-256-GCM key
        let key = Key::<Aes256Gcm>::from_slice(&key_bytes);
        self.encryption_key = Some(*key);
        
        // Store PIN hash for verification
        let mut hasher = Sha256::new();
        hasher.update(pin.as_bytes());
        hasher.update(&salt);
        let pin_hash_vec = hasher.finalize();
        let mut pin_hash = [0u8; 32];
        pin_hash.copy_from_slice(&pin_hash_vec);
        self.pin_hash = Some(pin_hash);
        
        self.is_locked = false;
        
        Ok(())
    }

    /// Unlock wallet with PIN
    pub fn unlock(&mut self, pin: &str, stored_salt: &[u8; 32]) -> Result<bool> {
        if let Some(stored_pin_hash) = &self.pin_hash {
            // Verify PIN
            let mut hasher = Sha256::new();
            hasher.update(pin.as_bytes());
            hasher.update(stored_salt);
            let provided_hash_vec = hasher.finalize();
            let mut provided_hash = [0u8; 32];
            provided_hash.copy_from_slice(&provided_hash_vec);
            
            if provided_hash == *stored_pin_hash {
                // Derive encryption key
                let mut key_bytes = [0u8; 32];
                pbkdf2_hmac::<Sha256>(pin.as_bytes(), stored_salt, 100_000, &mut key_bytes);
                let key = Key::<Aes256Gcm>::from_slice(&key_bytes);
                self.encryption_key = Some(*key);
                self.is_locked = false;
                return Ok(true);
            }
        }
        
        Ok(false)
    }

    /// Lock wallet (clears memory cache and encryption key)
    pub fn lock(&mut self) {
        self.memory_cache.clear();
        self.encryption_key = None;
        self.is_locked = true;
    }

    /// Store credential with encryption
    pub fn store_encrypted_credential(&mut self, credential: &VerifiableCredential, lemma_type: &str, site_id: Option<String>) -> Result<String> {
        if self.is_locked {
            return Err(LemmaError::Wallet("Wallet is locked".to_string()));
        }

        let encryption_key = self.encryption_key.as_ref()
            .ok_or_else(|| LemmaError::Wallet("No encryption key available".to_string()))?;

        // Serialize credential
        let credential_json = credential.to_json()?;
        let mut credential_bytes = credential_json.into_bytes();

        // Generate random nonce
        let mut nonce_bytes = [0u8; 12];
        OsRng.fill_bytes(&mut nonce_bytes);
        let nonce = Nonce::from_slice(&nonce_bytes);

        // Generate salt for this credential
        let mut salt = [0u8; 32];
        OsRng.fill_bytes(&mut salt);

        // Encrypt credential data
        let cipher = Aes256Gcm::new(encryption_key);
        cipher.encrypt_in_place(nonce, b"", &mut credential_bytes)
            .map_err(|e| LemmaError::Wallet(format!("Encryption failed: {}", e)))?;

        // Create encrypted entry
        let encrypted_entry = EncryptedCredentialEntry {
            encrypted_data: credential_bytes,
            nonce: nonce_bytes,
            salt,
            metadata: EncryptedCredentialMetadata {
                credential_id: credential.id.clone(),
                package_type: credential.get_claim("packageType")
                    .and_then(|v| v.as_str())
                    .unwrap_or("unknown").to_string(),
                stored_at: crate::utils::current_timestamp(),
                last_accessed: crate::utils::current_timestamp(),
                lemma_type: lemma_type.to_string(),
                site_id,
                encryption_version: 1,
            },
        };

        // Store encrypted entry
        self.encrypted_storage.insert(credential.id.clone(), encrypted_entry);

        // Also cache decrypted version in memory for performance
        let wallet_entry = WalletCredentialEntry {
            credential: credential.clone(),
            zkp_credential: None,
            metadata: WalletCredentialMetadata {
                fingerprint: credential.id.clone(),
                stored_at: crate::utils::current_timestamp(),
                last_accessed: crate::utils::current_timestamp(),
                access_count: 0,
                storage_layer: WalletStorage::Browser,
                preloaded: false,
                network_shared: lemma_type == "poh",
                privacy_level: PrivacyLevel::Public,
            },
        };
        
        self.memory_cache.insert(credential.id.clone(), wallet_entry);

        Ok(credential.id.clone())
    }

    /// Retrieve and decrypt credential
    pub fn get_encrypted_credential(&mut self, credential_id: &str) -> Result<Option<VerifiableCredential>> {
        if self.is_locked {
            return Err(LemmaError::Wallet("Wallet is locked".to_string()));
        }

        // Check memory cache first
        if let Some(cached_entry) = self.memory_cache.get(credential_id) {
            return Ok(Some(cached_entry.credential.clone()));
        }

        // Get from encrypted storage
        let encrypted_entry = match self.encrypted_storage.get(credential_id) {
            Some(entry) => entry,
            None => return Ok(None),
        };

        let encryption_key = self.encryption_key.as_ref()
            .ok_or_else(|| LemmaError::Wallet("No encryption key available".to_string()))?;

        // Decrypt credential data
        let mut encrypted_data = encrypted_entry.encrypted_data.clone();
        let nonce = Nonce::from_slice(&encrypted_entry.nonce);
        
        let cipher = Aes256Gcm::new(encryption_key);
        cipher.decrypt_in_place(nonce, b"", &mut encrypted_data)
            .map_err(|e| LemmaError::Wallet(format!("Decryption failed: {}", e)))?;

        // Deserialize credential
        let credential_json = String::from_utf8(encrypted_data)
            .map_err(|e| LemmaError::Wallet(format!("Invalid UTF-8: {}", e)))?;
        
        let credential = VerifiableCredential::from_json(&credential_json)?;

        // Cache in memory for performance
        let wallet_entry = WalletCredentialEntry {
            credential: credential.clone(),
            zkp_credential: None,
            metadata: WalletCredentialMetadata {
                fingerprint: credential.id.clone(),
                stored_at: encrypted_entry.metadata.stored_at,
                last_accessed: crate::utils::current_timestamp(),
                access_count: 0,
                storage_layer: WalletStorage::Browser,
                preloaded: false,
                network_shared: encrypted_entry.metadata.lemma_type == "poh",
                privacy_level: PrivacyLevel::Public,
            },
        };
        
        self.memory_cache.insert(credential.id.clone(), wallet_entry);

        Ok(Some(credential))
    }

    /// Get all PoH lemmas (universal credentials)
    pub fn get_poh_lemmas(&mut self) -> Result<Vec<VerifiableCredential>> {
        let mut poh_lemmas = Vec::new();
        
        // Collect credential IDs first to avoid borrowing issues
        let poh_ids: Vec<String> = self.encrypted_storage.values()
            .filter(|entry| entry.metadata.lemma_type == "poh")
            .map(|entry| entry.metadata.credential_id.clone())
            .collect();
        
        // Then retrieve credentials
        for credential_id in poh_ids {
            if let Ok(Some(credential)) = self.get_encrypted_credential(&credential_id) {
                poh_lemmas.push(credential);
            }
        }
        
        Ok(poh_lemmas)
    }

    /// Get permission lemmas for specific site
    pub fn get_permission_lemmas(&mut self, site_id: &str) -> Result<Vec<VerifiableCredential>> {
        let mut permission_lemmas = Vec::new();
        
        // Collect credential IDs first to avoid borrowing issues
        let permission_ids: Vec<String> = self.encrypted_storage.values()
            .filter(|entry| entry.metadata.lemma_type == "permission" && 
                           entry.metadata.site_id.as_deref() == Some(site_id))
            .map(|entry| entry.metadata.credential_id.clone())
            .collect();
        
        // Then retrieve credentials
        for credential_id in permission_ids {
            if let Ok(Some(credential)) = self.get_encrypted_credential(&credential_id) {
                permission_lemmas.push(credential);
            }
        }
        
        Ok(permission_lemmas)
    }

    /// Export encrypted storage for browser persistence
    pub fn export_encrypted_storage(&self) -> Result<String> {
        serde_json::to_string(&self.encrypted_storage)
            .map_err(|e| LemmaError::Wallet(format!("Export failed: {}", e)))
    }

    /// Import encrypted storage from browser
    pub fn import_encrypted_storage(&mut self, encrypted_data: &str) -> Result<()> {
        let storage: HashMap<String, EncryptedCredentialEntry> = serde_json::from_str(encrypted_data)
            .map_err(|e| LemmaError::Wallet(format!("Import failed: {}", e)))?;
        
        self.encrypted_storage = storage;
        self.memory_cache.clear(); // Force re-decryption
        
        Ok(())
    }

    /// Get wallet statistics
    pub fn get_stats(&self) -> HashMap<String, serde_json::Value> {
        let mut stats = HashMap::new();
        
        let total_credentials = self.encrypted_storage.len();
        let poh_count = self.encrypted_storage.values()
            .filter(|entry| entry.metadata.lemma_type == "poh")
            .count();
        let permission_count = total_credentials - poh_count;
        
        stats.insert("total_credentials".to_string(), serde_json::Value::Number(total_credentials.into()));
        stats.insert("poh_lemmas".to_string(), serde_json::Value::Number(poh_count.into()));
        stats.insert("permission_lemmas".to_string(), serde_json::Value::Number(permission_count.into()));
        stats.insert("is_locked".to_string(), serde_json::Value::Bool(self.is_locked));
        stats.insert("memory_cache_size".to_string(), serde_json::Value::Number(self.memory_cache.len().into()));
        stats.insert("encryption_enabled".to_string(), serde_json::Value::Bool(self.encryption_key.is_some()));
        
        stats
    }
}

/// Security levels for encrypted wallet
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum EncryptionLevel {
    /// Standard AES-256-GCM with PBKDF2
    Standard,
    /// Enhanced with additional key stretching
    Enhanced,
    /// Maximum security with hardware binding
    Maximum,
}

/// Wallet security configuration
#[derive(Debug, Clone)]
pub struct WalletSecurityConfig {
    /// Encryption level
    pub encryption_level: EncryptionLevel,
    /// Auto-lock timeout (seconds)
    pub auto_lock_timeout: u64,
    /// Maximum failed PIN attempts
    pub max_pin_attempts: u32,
    /// Key derivation iterations
    pub pbkdf2_iterations: u32,
    /// Enable device binding
    pub device_binding: bool,
}

impl Default for WalletSecurityConfig {
    fn default() -> Self {
        Self {
            encryption_level: EncryptionLevel::Standard,
            auto_lock_timeout: 300, // 5 minutes
            max_pin_attempts: 3,
            pbkdf2_iterations: 100_000,
            device_binding: false,
        }
    }
}
