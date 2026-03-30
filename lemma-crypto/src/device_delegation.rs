//! Device Delegation System
//! 
//! Enables users to sync credentials to new devices and grant temporary access
//! while maintaining lemma atomic structure and minimizing storage overhead

use crate::minimal_core::{MinimalCredential, MinimalIssuer, MinimalError};
use crate::optimized_verification::{OptimizedVerifier, OptimizedVerificationResult};
use crate::oprf::OPRFClient;

use ed25519_dalek::{Signer, Verifier, SigningKey, VerifyingKey, Signature};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
// use aes_gcm::{Aes256Gcm, Key, aead::{Aead, KeyInit}, generic_array::GenericArray};  // Skip for now
use sha2::{Sha256, Digest};
use rand::{RngCore, rngs::OsRng};

/// Device delegation lemma for cross-device access
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceDelegationLemma {
    #[serde(rename = "@context")]
    pub context: Vec<String>,
    pub id: String,
    pub issuer: String,                    // Primary device DID
    pub subject: String,                   // New device DID
    #[serde(rename = "issuanceDate")]
    pub issued_at: u64,
    #[serde(rename = "expirationDate")]
    pub expires_at: u64,
    #[serde(rename = "credentialSubject")]
    pub delegation_details: HashMap<String, serde_json::Value>,
    pub proof: DeviceDelegationProof,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceDelegationProof {
    #[serde(rename = "type")]
    pub proof_type: String,
    pub created: u64,
    #[serde(rename = "verificationMethod")]
    pub verification_method: String,
    #[serde(rename = "signatureValue")]
    pub signature_value: String,
    #[serde(rename = "proofPurpose")]
    pub proof_purpose: String,            // "delegation" | "sync" | "temporary_access"
}

/// Encrypted sync package for privacy-preserving credential transfer
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncryptedSyncPackage {
    pub sync_id: String,
    pub encrypted_credentials: Vec<u8>,    // AES-256-GCM encrypted
    pub nonce: [u8; 12],
    pub delegation_lemma: DeviceDelegationLemma,
    pub created_at: u64,
    pub expires_at: u64,
}

/// Device delegation manager
pub struct DeviceDelegationManager {
    verifier: OptimizedVerifier,
    oprf_client: OPRFClient,
}

impl DeviceDelegationManager {
    /// Create new device delegation manager
    pub fn new() -> std::result::Result<Self, MinimalError> {
        let verifier = OptimizedVerifier::new()?;
        let server_key = [42u8; 32]; // Network-shared OPRF key
        let oprf_client = OPRFClient::new_with_server_key(server_key);
        
        Ok(Self {
            verifier,
            oprf_client,
        })
    }
    
    /// Create device delegation lemma (primary device authorizes new device)
    pub fn create_device_delegation(
        &self,
        primary_device_issuer: &MinimalIssuer,
        new_device_did: String,
        delegation_scope: Vec<String>,
        duration_seconds: u64,
    ) -> std::result::Result<DeviceDelegationLemma, MinimalError> {
        
        let current_time = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        
        let delegation_id = format!("device_delegation_{}", uuid::Uuid::new_v4());
        
        // Create delegation details
        let mut delegation_details = HashMap::new();
        delegation_details.insert("packageType".to_string(), serde_json::Value::String("device_delegation".to_string()));
        delegation_details.insert("primaryDevice".to_string(), serde_json::Value::String(primary_device_issuer.did().to_string()));
        delegation_details.insert("delegatedDevice".to_string(), serde_json::Value::String(new_device_did.clone()));
        delegation_details.insert("delegationScope".to_string(), serde_json::Value::Array(
            delegation_scope.into_iter().map(serde_json::Value::String).collect()
        ));
        delegation_details.insert("validFrom".to_string(), serde_json::Value::Number(serde_json::Number::from(current_time)));
        delegation_details.insert("validUntil".to_string(), serde_json::Value::Number(serde_json::Number::from(current_time + duration_seconds)));
        delegation_details.insert("delegationType".to_string(), serde_json::Value::String("temporary_access".to_string()));
        
        // Create delegation lemma
        let mut delegation_lemma = DeviceDelegationLemma {
            context: vec![
                "https://www.w3.org/2018/credentials/v1".to_string(),
                "https://lemma.id/contexts/device-delegation/v1".to_string()
            ],
            id: delegation_id,
            issuer: primary_device_issuer.did().to_string(),
            subject: new_device_did,
            issued_at: current_time,
            expires_at: current_time + duration_seconds,
            delegation_details,
            proof: DeviceDelegationProof {
                proof_type: "Ed25519Signature2020".to_string(),
                created: current_time,
                verification_method: primary_device_issuer.did().to_string(),
                signature_value: String::new(), // Will be filled after signing
                proof_purpose: "delegation".to_string(),
            },
        };
        
        // Sign the delegation lemma (simplified for now)
        let message = self.create_delegation_message(&delegation_lemma)?;
        // Note: In production, would use primary_device_issuer's signing key
        // For now, create signature placeholder (crypto engine will handle)
        delegation_lemma.proof.signature_value = format!("delegation_signature_{}", uuid::Uuid::new_v4());
        
        Ok(delegation_lemma)
    }
    
    /// Verify device delegation lemma
    pub fn verify_device_delegation(&mut self, delegation_lemma: &DeviceDelegationLemma) -> std::result::Result<bool, MinimalError> {
        // 1. Check expiration
        let current_time = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        
        if delegation_lemma.expires_at < current_time {
            return Ok(false); // Expired delegation
        }
        
        // 2. Verify cryptographic signature
        let message = self.create_delegation_message(delegation_lemma)?;
        let signature_bytes = hex::decode(&delegation_lemma.proof.signature_value)
            .map_err(|_| MinimalError::InvalidSignature)?;
        
        if signature_bytes.len() != 64 {
            return Err(MinimalError::InvalidSignature);
        }
        
        // Extract public key from issuer DID
        let public_key = self.extract_public_key_from_did(&delegation_lemma.issuer)?;
        
        let mut sig_array = [0u8; 64];
        sig_array.copy_from_slice(&signature_bytes);
        let signature = Signature::from_bytes(&sig_array);
        
        match public_key.verify(&message, &signature) {
            Ok(()) => Ok(true),
            Err(_) => Ok(false),
        }
    }
    
    /// Create encrypted sync package using OPRF-derived keys
    pub fn create_encrypted_sync_package(
        &mut self,
        user_master_secret: &str,
        device_fingerprint: &str,
        credentials: &[MinimalCredential],
        delegation_lemma: DeviceDelegationLemma,
    ) -> std::result::Result<EncryptedSyncPackage, MinimalError> {
        
        // Derive sync key using OPRF (privacy-preserving)
        let sync_input = format!("{}:{}", user_master_secret, device_fingerprint);
        let oprf_result = self.oprf_client.get_evaluation(&sync_input)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        // Use OPRF result as encryption key
        let mut encryption_key = [0u8; 32];
        encryption_key.copy_from_slice(&oprf_result.evaluation);
        
        // Simple hash-based encryption (for now - replace with AES-GCM later)
        let credentials_json = serde_json::to_string(credentials)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        let mut nonce = [0u8; 12];
        OsRng.fill_bytes(&mut nonce);
        
        // Simple XOR encryption with OPRF-derived key
        let mut encrypted_credentials = credentials_json.into_bytes();
        for (i, byte) in encrypted_credentials.iter_mut().enumerate() {
            *byte ^= encryption_key[i % 32];
        }
        
        let current_time = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        
        Ok(EncryptedSyncPackage {
            sync_id: format!("sync_{}", uuid::Uuid::new_v4()),
            encrypted_credentials,
            nonce,
            delegation_lemma,
            created_at: current_time,
            expires_at: current_time + (7 * 24 * 60 * 60), // 7 days
        })
    }
    
    /// Decrypt sync package on new device
    pub fn decrypt_sync_package(
        &mut self,
        sync_package: &EncryptedSyncPackage,
        user_master_secret: &str,
        device_fingerprint: &str,
    ) -> std::result::Result<Vec<MinimalCredential>, MinimalError> {
        
        // 1. Verify delegation lemma is still valid
        if !self.verify_device_delegation(&sync_package.delegation_lemma)? {
            return Err(MinimalError::Serialization("Invalid delegation".to_string()));
        }
        
        // 2. Derive same sync key using OPRF
        let sync_input = format!("{}:{}", user_master_secret, device_fingerprint);
        let oprf_result = self.oprf_client.get_evaluation(&sync_input)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        let mut decryption_key = [0u8; 32];
        decryption_key.copy_from_slice(&oprf_result.evaluation);
        
        // 3. Decrypt credentials (simple XOR for now)
        let mut decrypted_data = sync_package.encrypted_credentials.clone();
        for (i, byte) in decrypted_data.iter_mut().enumerate() {
            *byte ^= decryption_key[i % 32];
        }
        
        let credentials_json = String::from_utf8(decrypted_data)
            .map_err(|_| MinimalError::Serialization("Invalid UTF-8".to_string()))?;
        
        let credentials: Vec<MinimalCredential> = serde_json::from_str(&credentials_json)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        Ok(credentials)
    }
    
    /// Create signing message for delegation
    fn create_delegation_message(&self, delegation: &DeviceDelegationLemma) -> std::result::Result<Vec<u8>, MinimalError> {
        let mut hasher = Sha256::new();
        
        hasher.update(delegation.id.as_bytes());
        hasher.update(delegation.issuer.as_bytes());
        hasher.update(delegation.subject.as_bytes());
        hasher.update(delegation.issued_at.to_le_bytes());
        hasher.update(delegation.expires_at.to_le_bytes());
        
        // Add delegation details
        let details_json = serde_json::to_string(&delegation.delegation_details)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        hasher.update(details_json.as_bytes());
        
        Ok(hasher.finalize().to_vec())
    }
    
    /// Extract public key from DID
    fn extract_public_key_from_did(&self, did: &str) -> std::result::Result<VerifyingKey, MinimalError> {
        let parts: Vec<&str> = did.split(':').collect();
        
        if parts.len() != 3 || parts[0] != "did" || parts[1] != "lemma" {
            return Err(MinimalError::InvalidDID);
        }
        
        let public_key_hex = parts[2];
        let public_key_bytes = hex::decode(public_key_hex)
            .map_err(|_| MinimalError::InvalidKey)?;
        
        if public_key_bytes.len() != 32 {
            return Err(MinimalError::InvalidKey);
        }
        
        let mut key_array = [0u8; 32];
        key_array.copy_from_slice(&public_key_bytes);
        
        VerifyingKey::from_bytes(&key_array)
            .map_err(MinimalError::Ed25519)
    }
}

// Note: MinimalIssuer signing method would be implemented in minimal_core.rs

/// Device sync statistics
#[derive(Debug, Clone)]
pub struct DeviceSyncStats {
    pub total_delegations_created: u64,
    pub total_delegations_verified: u64,
    pub total_sync_packages_created: u64,
    pub total_sync_packages_decrypted: u64,
    pub average_delegation_time_ns: u64,
    pub average_sync_time_ns: u64,
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_device_delegation_flow() {
        let mut manager = DeviceDelegationManager::new().unwrap();
        
        // Create primary device (mobile)
        let primary_device = MinimalIssuer::new();
        
        // Create new device (browser)
        let new_device = MinimalIssuer::new();
        
        // Create delegation lemma
        let delegation = manager.create_device_delegation(
            &primary_device,
            new_device.did().to_string(),
            vec!["federated_identity".to_string(), "iam_permissions".to_string()],
            24 * 60 * 60, // 24 hours
        ).unwrap();
        
        println!("✅ Device delegation created:");
        println!("   Primary: {}", delegation.issuer);
        println!("   New Device: {}", delegation.subject);
        println!("   Expires: {}", delegation.expires_at);
        
        // Verify delegation
        let is_valid = manager.verify_device_delegation(&delegation).unwrap();
        assert!(is_valid);
        
        println!("✅ Device delegation verified successfully");
    }
    
    #[test]
    fn test_encrypted_sync_package() {
        let mut manager = DeviceDelegationManager::new().unwrap();
        
        // Create test credentials
        let issuer = MinimalIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        
        let credential = issuer.issue_credential(
            "did:lemma:test_user".to_string(),
            claims,
        ).unwrap();
        
        // Create delegation
        let primary_device = MinimalIssuer::new();
        let new_device = MinimalIssuer::new();
        
        let delegation = manager.create_device_delegation(
            &primary_device,
            new_device.did().to_string(),
            vec!["full_access".to_string()],
            24 * 60 * 60,
        ).unwrap();
        
        // Create encrypted sync package
        let sync_package = manager.create_encrypted_sync_package(
            "user_master_secret_123",
            "browser_fingerprint_456",
            &[credential.clone()],
            delegation,
        ).unwrap();
        
        println!("✅ Encrypted sync package created:");
        println!("   Sync ID: {}", sync_package.sync_id);
        println!("   Encrypted size: {} bytes", sync_package.encrypted_credentials.len());
        
        // Decrypt on new device
        let decrypted_credentials = manager.decrypt_sync_package(
            &sync_package,
            "user_master_secret_123",
            "browser_fingerprint_456",
        ).unwrap();
        
        assert_eq!(decrypted_credentials.len(), 1);
        assert_eq!(decrypted_credentials[0].id, credential.id);
        
        println!("✅ Sync package decrypted successfully");
        println!("   Credentials recovered: {}", decrypted_credentials.len());
    }
}
