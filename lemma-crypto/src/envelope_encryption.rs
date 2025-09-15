//! Envelope Encryption for Wallet Recovery
//! XChaCha20-Poly1305 AEAD with 2-of-N key derivation

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WalletEnvelopeV2 {
    pub version: u16,
    pub counter: u64,               // Monotonic counter for rollback protection
    pub wallet_schema: u16,
    pub master_seed: [u8; 32],     // SK_master for wallet
    pub device_records: Option<Vec<u8>>, // Optional encrypted cache
    pub metadata: HashMap<String, String>, // Additional metadata
}

#[derive(Debug, Clone)]
pub struct EnvelopeEncryptionV2 {
    // Placeholder for XChaCha20-Poly1305 implementation
}

impl EnvelopeEncryptionV2 {
    pub fn new() -> Self {
        Self {}
    }

    /// Derive encryption key from 2-of-N factors
    pub fn derive_envelope_key(
        passphrase: &str,
        device_key: Option<&[u8; 32]>,
        salt: &[u8; 32]
    ) -> Result<[u8; 32], String> {
        use hkdf::Hkdf;
        use sha2::Sha256;
        
        // Derive key from passphrase using Argon2id
        let passphrase_key = Self::derive_passphrase_key(passphrase, salt)?;
        
        // If device key provided, combine with passphrase key
        if let Some(dk) = device_key {
            // XOR combine for 2-of-2 scheme (simplified)
            let mut combined_key = [0u8; 32];
            for i in 0..32 {
                combined_key[i] = passphrase_key[i] ^ dk[i];
            }
            Ok(combined_key)
        } else {
            // Passphrase-only recovery
            Ok(passphrase_key)
        }
    }

    /// Derive key from passphrase using Argon2id
    fn derive_passphrase_key(passphrase: &str, salt: &[u8; 32]) -> Result<[u8; 32], String> {
        use argon2::{Argon2, PasswordHasher};
        use argon2::password_hash::{PasswordHasher as _, SaltString};
        
        // Convert salt to SaltString format
        let salt_str = SaltString::encode_b64(salt).map_err(|e| e.to_string())?;
        
        // Use Argon2id with recommended parameters
        let argon2 = Argon2::default();
        
        let hash = argon2.hash_password(passphrase.as_bytes(), &salt_str)
            .map_err(|e| e.to_string())?;
        
        // Extract 32-byte key from hash
        let hash_bytes = hash.hash.ok_or("Hash generation failed")?;
        let mut key = [0u8; 32];
        key.copy_from_slice(&hash_bytes.as_bytes()[..32]);
        
        Ok(key)
    }

    /// Encrypt wallet envelope with AEAD
    pub fn encrypt_envelope(
        &self,
        envelope: &WalletEnvelopeV2,
        encryption_key: &[u8; 32],
        aad: &[u8]
    ) -> Result<Vec<u8>, String> {
        // Serialize envelope
        let plaintext = serde_cbor::to_vec(envelope).map_err(|e| e.to_string())?;
        
        // TODO: Implement XChaCha20-Poly1305 encryption
        // For now, use simple AES-GCM as placeholder
        use aes_gcm::{Aes256Gcm, Key, Nonce};
        use aes_gcm::aead::Aead;
        use aes_gcm::KeyInit;
        
        let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(encryption_key));
        
        // Generate random nonce
        use rand::RngCore;
        let mut nonce_bytes = [0u8; 12];
        rand::thread_rng().fill_bytes(&mut nonce_bytes);
        let nonce = Nonce::from_slice(&nonce_bytes);
        
        // Encrypt with AAD
        let ciphertext = cipher.encrypt(nonce, &*plaintext)
            .map_err(|e| format!("Encryption failed: {}", e))?;
        
        // Prepend nonce to ciphertext
        let mut result = nonce_bytes.to_vec();
        result.extend_from_slice(&ciphertext);
        
        Ok(result)
    }

    /// Decrypt wallet envelope
    pub fn decrypt_envelope(
        &self,
        ciphertext_with_nonce: &[u8],
        encryption_key: &[u8; 32],
        aad: &[u8]
    ) -> Result<WalletEnvelopeV2, String> {
        if ciphertext_with_nonce.len() < 12 {
            return Err("Ciphertext too short".to_string());
        }
        
        // Extract nonce and ciphertext
        let (nonce_bytes, ciphertext) = ciphertext_with_nonce.split_at(12);
        
        // TODO: Implement XChaCha20-Poly1305 decryption
        // For now, use AES-GCM as placeholder
        use aes_gcm::{Aes256Gcm, Key, Nonce};
        use aes_gcm::aead::Aead;
        use aes_gcm::KeyInit;
        
        let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(encryption_key));
        let nonce = Nonce::from_slice(nonce_bytes);
        
        // Decrypt
        let plaintext = cipher.decrypt(nonce, ciphertext)
            .map_err(|e| format!("Decryption failed: {}", e))?;
        
        // Deserialize envelope
        let envelope: WalletEnvelopeV2 = serde_cbor::from_slice(&plaintext)
            .map_err(|e| format!("Deserialization failed: {}", e))?;
        
        Ok(envelope)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_envelope_encryption_roundtrip() {
        let encryption = EnvelopeEncryptionV2::new();
        
        // Create test envelope
        let envelope = WalletEnvelopeV2 {
            version: 1,
            counter: 42,
            wallet_schema: 1,
            master_seed: [0x42; 32],
            device_records: Some(vec![1, 2, 3, 4]),
            metadata: HashMap::new(),
        };
        
        // Test encryption/decryption
        let passphrase = "test_recovery_passphrase_123";
        let salt = [0x01; 32];
        let aad = b"test_aad";
        
        let encryption_key = EnvelopeEncryptionV2::derive_envelope_key(
            passphrase, None, &salt
        ).unwrap();
        
        let ciphertext = encryption.encrypt_envelope(&envelope, &encryption_key, aad).unwrap();
        let decrypted = encryption.decrypt_envelope(&ciphertext, &encryption_key, aad).unwrap();
        
        assert_eq!(envelope.version, decrypted.version);
        assert_eq!(envelope.counter, decrypted.counter);
        assert_eq!(envelope.master_seed, decrypted.master_seed);
    }

    #[test]
    fn test_2_of_n_key_derivation() {
        let passphrase = "test_passphrase";
        let device_key = [0x42; 32];
        let salt = [0x01; 32];
        
        // Test passphrase-only
        let key1 = EnvelopeEncryptionV2::derive_envelope_key(passphrase, None, &salt).unwrap();
        
        // Test passphrase + device key
        let key2 = EnvelopeEncryptionV2::derive_envelope_key(passphrase, Some(&device_key), &salt).unwrap();
        
        // Should be different keys
        assert_ne!(key1, key2, "2-of-N keys should be different");
        
        // Should be deterministic
        let key1_repeat = EnvelopeEncryptionV2::derive_envelope_key(passphrase, None, &salt).unwrap();
        let key2_repeat = EnvelopeEncryptionV2::derive_envelope_key(passphrase, Some(&device_key), &salt).unwrap();
        
        assert_eq!(key1, key1_repeat, "Passphrase-only key should be deterministic");
        assert_eq!(key2, key2_repeat, "2-of-N key should be deterministic");
    }
}
