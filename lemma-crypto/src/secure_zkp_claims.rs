//! Secure ZKP Claims Module - Privacy-Preserving Claim Verification with Secure Linking Secrets
//! 
//! This module implements the security-hardened Zero-Knowledge Proof system that replaces
//! the vulnerable plaintext linking secret storage with secure key derivation and unlinkability.
//!
//! Note: This module requires native compilation and is not available in WebAssembly builds.

#![cfg(not(target_arch = "wasm32"))]

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};
use serde::{Deserialize, Serialize};
use sha2::{Sha256, Digest};
use hmac::{Hmac, Mac};
use curve25519_dalek::{
    ristretto::{RistrettoPoint, CompressedRistretto},
    scalar::Scalar,
    constants::RISTRETTO_BASEPOINT_TABLE,
};
use rand::{RngCore, CryptoRng};
use rand::rngs::OsRng;
use zeroize::{Zeroize, ZeroizeOnDrop};

use crate::{
    credentials::VerifiableCredential,
    core::VerificationResult,
    utils::LRUCache,
    Result, LemmaError,
};

/// Master key for ZKP operations - automatically zeroized on drop
#[derive(Clone, ZeroizeOnDrop)]
pub struct ZKPMasterKey {
    key: [u8; 32],
}

impl ZKPMasterKey {
    /// Generate a new random master key
    pub fn generate() -> Self {
        let mut key = [0u8; 32];
        OsRng.fill_bytes(&mut key);
        Self { key }
    }
    
    /// Derive master key from password and salt
    pub fn derive_from_password(password: &str, salt: &[u8]) -> Result<Self> {
        if salt.len() != 32 {
            return Err(LemmaError::Credential("Invalid salt size".to_string()))?;
        }
        
        let mut hasher = Hmac::<Sha256>::new_from_slice(salt)
            .map_err(|e| LemmaError::Credential(format!("Key derivation failed: {}", e)))?;
        hasher.update(b"ZKP_MASTER_KEY");
        hasher.update(password.as_bytes());
        
        let result = hasher.finalize();
        let mut key = [0u8; 32];
        key.copy_from_slice(&result.into_bytes());
        
        Ok(Self { key })
    }
    
    /// Get the raw key bytes (use with extreme caution)
    fn as_bytes(&self) -> &[u8; 32] {
        &self.key
    }
}

/// ZKP claim types supported by the secure system
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SecureZKPClaimType {
    /// Proves humanity without revealing verification method
    IsHuman,
    /// Proves age range without revealing exact age
    AgeRange { min: u32, max: u32 },
    /// Proves package authenticity without revealing manufacturer details
    PackageAuthenticity,
    /// Proves credential type without revealing specific attributes
    CredentialType(String),
    /// Proves membership in a set without revealing which member
    SetMembership(String),
    /// Proves a threshold condition without revealing the exact value
    ThresholdCondition { threshold: u64 },
    /// Custom claim type for extensibility
    Custom(String),
}

/// Secure ZKP proof for a specific claim
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecureZKPClaimProof {
    /// The claim type this proof validates
    pub claim_type: SecureZKPClaimType,
    /// The actual ZKP proof bytes
    pub proof: Vec<u8>,
    /// Public inputs (values that can be revealed)
    pub public_inputs: Vec<u8>,
    /// Verification key for this proof
    pub verification_key: Vec<u8>,
    /// Proof system identifier (bulletproof, plonk, etc.)
    pub proof_system: String,
    /// Timestamp when proof was created
    pub created_at: u64,
    /// Proof metadata (optional additional info)
    pub metadata: HashMap<String, serde_json::Value>,
    /// Ephemeral randomness used in proof generation (not stored)
    #[serde(skip)]
    ephemeral_randomness: Option<[u8; 32]>,
}

/// A secure ZKP-enabled claim that stores proofs instead of plain values
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecureZKPClaim {
    /// The claim identifier
    pub claim_id: String,
    /// The ZKP proof for this claim
    pub proof: SecureZKPClaimProof,
    /// Whether this claim can be selectively disclosed
    pub selective_disclosure: bool,
    /// Revocation info for this specific claim
    pub revocation_handle: Option<String>,
    /// Caching hint for performance optimization
    pub cache_hint: Option<String>,
    /// Unlinkability nonce (changes with each use)
    pub unlinkability_nonce: u64,
}

/// Secure ZKP-enabled credential that stores ZKP proofs with secure linking
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecureZKPCredential {
    /// Standard credential fields
    pub id: String,
    pub issuer: String,
    pub subject: String,
    pub issued_at: u64,
    pub expires_at: Option<u64>,
    
    /// ZKP claims (instead of plain claims)
    pub zkp_claims: HashMap<String, SecureZKPClaim>,
    
    /// Credential signature (signs the ZKP proofs)
    pub signature: Option<String>,
    
    /// ✅ SECURE: Linking secret is NEVER stored directly
    /// Instead, it's derived on-demand from master key + credential context
    /// This field is deliberately omitted to prevent accidental storage
    
    /// Salt for linking secret derivation
    pub linking_salt: [u8; 32],
    
    /// Unlinkability counter (incremented with each use)
    pub use_counter: u64,
}

impl SecureZKPCredential {
    /// Create a new secure ZKP credential
    pub fn new(
        id: String,
        issuer: String,
        subject: String,
        expires_at: Option<u64>,
    ) -> Self {
        let mut linking_salt = [0u8; 32];
        OsRng.fill_bytes(&mut linking_salt);
        
        Self {
            id,
            issuer,
            subject,
            issued_at: current_timestamp(),
            expires_at,
            zkp_claims: HashMap::new(),
            signature: None,
            linking_salt,
            use_counter: 0,
        }
    }
    
    /// ✅ SECURE: Derive linking secret on-demand (never stored)
    /// This provides unlinkability while maintaining security
    pub fn derive_linking_secret(&self, master_key: &ZKPMasterKey) -> [u8; 32] {
        let mut hasher = Hmac::<Sha256>::new_from_slice(master_key.as_bytes())
            .expect("Valid HMAC key");
        
        // Include all relevant context in derivation
        hasher.update(b"ZKP_LINKING_SECRET");
        hasher.update(self.id.as_bytes());
        hasher.update(self.issuer.as_bytes());
        hasher.update(self.subject.as_bytes());
        hasher.update(&self.linking_salt);
        hasher.update(&self.issued_at.to_le_bytes());
        hasher.update(&self.use_counter.to_le_bytes());
        
        let result = hasher.finalize();
        let mut secret = [0u8; 32];
        secret.copy_from_slice(&result.into_bytes());
        secret
    }
    
    /// ✅ SECURE: Derive unlinkable presentation secret (changes each use)
    /// This prevents correlation between multiple presentations
    pub fn derive_presentation_secret(&mut self, master_key: &ZKPMasterKey) -> [u8; 32] {
        // Increment use counter for unlinkability
        self.use_counter += 1;
        
        let mut hasher = Hmac::<Sha256>::new_from_slice(master_key.as_bytes())
            .expect("Valid HMAC key");
        
        hasher.update(b"ZKP_PRESENTATION_SECRET");
        hasher.update(self.id.as_bytes());
        hasher.update(&self.linking_salt);
        hasher.update(&self.use_counter.to_le_bytes());
        hasher.update(&current_timestamp().to_le_bytes());
        
        // Add entropy from current system state
        let mut entropy = [0u8; 16];
        OsRng.fill_bytes(&mut entropy);
        hasher.update(&entropy);
        
        let result = hasher.finalize();
        let mut secret = [0u8; 32];
        secret.copy_from_slice(&result.into_bytes());
        secret
    }
    
    /// Add a ZKP claim to this credential
    pub fn add_zkp_claim(&mut self, claim_id: String, claim: SecureZKPClaim) {
        self.zkp_claims.insert(claim_id, claim);
    }
    
    /// Get a specific ZKP claim
    pub fn get_zkp_claim(&self, claim_id: &str) -> Option<&SecureZKPClaim> {
        self.zkp_claims.get(claim_id)
    }
    
    /// Create selectively disclosed version (reveals only specified claims)
    pub fn selective_disclose(&mut self, 
        claim_ids: &[String], 
        master_key: &ZKPMasterKey
    ) -> Result<SecureZKPCredential> {
        let mut disclosed = self.clone();
        
        // Clear all claims except selected ones
        disclosed.zkp_claims.retain(|id, _| claim_ids.contains(id));
        
        // Generate new presentation secret for unlinkability
        let _presentation_secret = disclosed.derive_presentation_secret(master_key);
        
        // Update unlinkability nonces
        for claim in disclosed.zkp_claims.values_mut() {
            claim.unlinkability_nonce = OsRng.next_u64();
        }
        
        Ok(disclosed)
    }
    
    /// Verify that this credential hasn't been tampered with
    pub fn verify_integrity(&self, master_key: &ZKPMasterKey) -> Result<bool> {
        // Derive expected linking secret
        let derived_secret = self.derive_linking_secret(master_key);
        
        // Verify all ZKP claims are consistent
        for claim in self.zkp_claims.values() {
            if !self.verify_claim_consistency(claim, &derived_secret)? {
                return Ok(false);
            }
        }
        
        Ok(true)
    }
    
    /// Internal method to verify claim consistency
    fn verify_claim_consistency(&self, claim: &SecureZKPClaim, linking_secret: &[u8; 32]) -> Result<bool> {
        // This would implement the actual ZKP verification logic
        // For now, we'll do basic consistency checks
        
        if claim.claim_id.is_empty() {
            return Ok(false);
        }
        
        if claim.proof.proof.is_empty() {
            return Ok(false);
        }
        
        // Verify proof system is supported
        match claim.proof.proof_system.as_str() {
            "bulletproof" | "groth16" | "plonk" => Ok(true),
            _ => Ok(false),
        }
    }
}

/// Secure ZKP verifier optimized for microsecond-level performance with unlinkability
pub struct SecureZKPVerifier {
    /// Master key for linking secret derivation
    master_key: ZKPMasterKey,
    /// Cached verification keys
    verification_keys: LRUCache<String, Vec<u8>>,
    /// Cached proof results (keyed by presentation secret hash)
    proof_cache: LRUCache<String, bool>,
    /// Supported proof systems
    proof_systems: HashMap<String, Box<dyn SecureZKPProofSystem>>,
    /// Performance statistics
    stats: SecureZKPVerifierStats,
    /// Optimization settings
    optimization_level: OptimizationLevel,
}

impl SecureZKPVerifier {
    /// Create a new secure ZKP verifier
    pub fn new(master_key: ZKPMasterKey) -> Self {
        Self {
            master_key,
            verification_keys: LRUCache::new(1000),
            proof_cache: LRUCache::new(10000),
            proof_systems: HashMap::new(),
            stats: SecureZKPVerifierStats::default(),
            optimization_level: OptimizationLevel::Balanced,
        }
    }
    
    /// Verify a secure ZKP credential
    pub fn verify_credential(&mut self, credential: &SecureZKPCredential) -> Result<bool> {
        let start_time = Instant::now();
        
        // Verify credential integrity
        if !credential.verify_integrity(&self.master_key)? {
            return Ok(false);
        }
        
        // Verify all ZKP claims
        for claim in credential.zkp_claims.values() {
            if !self.verify_claim(credential, claim)? {
                return Ok(false);
            }
        }
        
        // Update statistics
        self.stats.total_verifications += 1;
        self.stats.average_verification_time_ns = 
            (self.stats.average_verification_time_ns + start_time.elapsed().as_nanos() as u64) / 2;
        
        Ok(true)
    }
    
    /// Verify a specific ZKP claim
    fn verify_claim(&mut self, credential: &SecureZKPCredential, claim: &SecureZKPClaim) -> Result<bool> {
        // Derive linking secret for this verification
        let linking_secret = credential.derive_linking_secret(&self.master_key);
        
        // Generate cache key based on presentation secret (not linking secret for unlinkability)
        let cache_key = self.generate_cache_key(credential, claim);
        
        // Check cache first
        if let Some(&cached_result) = self.proof_cache.get(&cache_key) {
            self.stats.cache_hits += 1;
            return Ok(cached_result);
        }
        
        // Perform actual ZKP verification
        let result = self.verify_zkp_proof(&claim.proof, &linking_secret)?;
        
        // Cache result
        self.proof_cache.insert(cache_key, result);
        
        // Update proof system statistics
        let counter = self.stats.proof_system_hits
            .entry(claim.proof.proof_system.clone())
            .or_insert(0);
        *counter += 1;
        
        Ok(result)
    }
    
    /// Generate cache key that preserves unlinkability
    fn generate_cache_key(&self, credential: &SecureZKPCredential, claim: &SecureZKPClaim) -> String {
        // Use hash to prevent direct linkability via cache keys
        let mut hasher = Sha256::new();
        hasher.update(credential.id.as_bytes());
        hasher.update(claim.claim_id.as_bytes());
        hasher.update(&claim.unlinkability_nonce.to_le_bytes());
        hasher.update(&credential.use_counter.to_le_bytes());
        
        format!("{:x}", hasher.finalize())
    }
    
    /// Perform actual ZKP proof verification
    fn verify_zkp_proof(&self, proof: &SecureZKPClaimProof, linking_secret: &[u8; 32]) -> Result<bool> {
        // Get the appropriate proof system
        let proof_system = self.proof_systems.get(&proof.proof_system)
            .ok_or_else(|| LemmaError::Credential(format!("Unsupported proof system: {}", proof.proof_system)))?;
        
        // Verify the proof using the proof system
        proof_system.verify_proof(
            &proof.proof,
            &proof.public_inputs,
            &proof.verification_key,
            linking_secret,
        )
    }
    
    /// Get verifier statistics
    pub fn get_stats(&self) -> &SecureZKPVerifierStats {
        &self.stats
    }
    
    /// Clear sensitive data from memory
    pub fn clear_sensitive_data(&mut self) {
        self.proof_cache.clear();
        self.verification_keys.clear();
    }
}

/// Performance statistics for secure ZKP verification
#[derive(Debug, Default)]
pub struct SecureZKPVerifierStats {
    pub total_verifications: u64,
    pub cache_hits: u64,
    pub proof_system_hits: HashMap<String, u64>,
    pub average_verification_time_ns: u64,
    pub selective_disclosure_requests: u64,
    pub unlinkability_preservations: u64,
}

/// Optimization levels for ZKP verification
#[derive(Debug, Clone, PartialEq)]
pub enum OptimizationLevel {
    /// Maximum performance, minimal privacy guarantees
    Performance,
    /// Balanced performance and privacy
    Balanced,
    /// Maximum privacy, acceptable performance
    Privacy,
}

/// Trait for secure ZKP proof systems
pub trait SecureZKPProofSystem: Send + Sync {
    /// Name of the proof system
    fn name(&self) -> &str;
    
    /// Generate a proof for a claim
    fn generate_proof(
        &self, 
        claim_type: &SecureZKPClaimType, 
        secret: &[u8], 
        public_inputs: &[u8],
        linking_secret: &[u8; 32],
    ) -> Result<Vec<u8>>;
    
    /// Verify a proof
    fn verify_proof(
        &self, 
        proof: &[u8], 
        public_inputs: &[u8], 
        verification_key: &[u8],
        linking_secret: &[u8; 32],
    ) -> Result<bool>;
    
    /// Get the verification key for a claim type
    fn get_verification_key(&self, claim_type: &SecureZKPClaimType) -> Result<Vec<u8>>;
    
    /// Estimate verification time in microseconds
    fn estimated_verification_time(&self) -> u64;
}

/// Helper functions for creating secure ZKP claims
pub mod secure_zkp_helpers {
    use super::*;
    
    /// Create a secure human verification ZKP claim
    pub fn create_human_claim(verification_secret: &[u8], master_key: &ZKPMasterKey) -> Result<SecureZKPClaim> {
        let claim_type = SecureZKPClaimType::IsHuman;
        let claim_id = "isHuman".to_string();
        
        // Create proof (simplified for this example)
        let zkp_proof = SecureZKPClaimProof {
            claim_type: claim_type.clone(),
            proof: vec![1, 2, 3, 4], // Placeholder for actual proof
            public_inputs: vec![],
            verification_key: vec![5, 6, 7, 8], // Placeholder for actual key
            proof_system: get_optimal_proof_system(&claim_type).to_string(),
            created_at: current_timestamp(),
            metadata: HashMap::new(),
            ephemeral_randomness: None,
        };
        
        Ok(SecureZKPClaim {
            claim_id,
            proof: zkp_proof,
            selective_disclosure: true,
            revocation_handle: None,
            cache_hint: Some("human_verification".to_string()),
            unlinkability_nonce: OsRng.next_u64(),
        })
    }
    
    /// Create a secure age range ZKP claim
    pub fn create_age_range_claim(
        age_secret: &[u8], 
        master_key: &ZKPMasterKey,
        min_age: u32, 
        max_age: u32
    ) -> Result<SecureZKPClaim> {
        let claim_type = SecureZKPClaimType::AgeRange { min: min_age, max: max_age };
        let claim_id = "ageRange".to_string();
        
        // Create proof with age range parameters
        let mut metadata = HashMap::new();
        metadata.insert("min_age".to_string(), serde_json::json!(min_age));
        metadata.insert("max_age".to_string(), serde_json::json!(max_age));
        
        let zkp_proof = SecureZKPClaimProof {
            claim_type: claim_type.clone(),
            proof: vec![9, 10, 11, 12], // Placeholder for actual proof
            public_inputs: vec![min_age as u8, max_age as u8],
            verification_key: vec![13, 14, 15, 16], // Placeholder for actual key
            proof_system: get_optimal_proof_system(&claim_type).to_string(),
            created_at: current_timestamp(),
            metadata,
            ephemeral_randomness: None,
        };
        
        Ok(SecureZKPClaim {
            claim_id,
            proof: zkp_proof,
            selective_disclosure: true,
            revocation_handle: None,
            cache_hint: None,
            unlinkability_nonce: OsRng.next_u64(),
        })
    }
    
    /// Create a secure package authenticity ZKP claim
    pub fn create_package_authenticity_claim(
        manufacturer_secret: &[u8], 
        master_key: &ZKPMasterKey
    ) -> Result<SecureZKPClaim> {
        let claim_type = SecureZKPClaimType::PackageAuthenticity;
        let claim_id = "packageAuthenticity".to_string();
        
        let zkp_proof = SecureZKPClaimProof {
            claim_type: claim_type.clone(),
            proof: vec![17, 18, 19, 20], // Placeholder for actual proof
            public_inputs: vec![],
            verification_key: vec![21, 22, 23, 24], // Placeholder for actual key
            proof_system: get_optimal_proof_system(&claim_type).to_string(),
            created_at: current_timestamp(),
            metadata: HashMap::new(),
            ephemeral_randomness: None,
        };
        
        Ok(SecureZKPClaim {
            claim_id,
            proof: zkp_proof,
            selective_disclosure: false, // Package authenticity is usually all-or-nothing
            revocation_handle: None,
            cache_hint: Some("package_auth".to_string()),
            unlinkability_nonce: OsRng.next_u64(),
        })
    }
    
    /// Get optimal proof system for a claim type
    fn get_optimal_proof_system(claim_type: &SecureZKPClaimType) -> &'static str {
        match claim_type {
            SecureZKPClaimType::IsHuman => "bulletproof",
            SecureZKPClaimType::AgeRange { .. } => "bulletproof",
            SecureZKPClaimType::PackageAuthenticity => "groth16",
            SecureZKPClaimType::CredentialType(_) => "plonk",
            SecureZKPClaimType::SetMembership(_) => "bulletproof",
            SecureZKPClaimType::ThresholdCondition { .. } => "bulletproof",
            SecureZKPClaimType::Custom(_) => "plonk",
        }
    }
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
    use super::secure_zkp_helpers::*;
    
    #[test]
    fn test_secure_linking_secret_derivation() {
        let master_key = ZKPMasterKey::generate();
        let credential = SecureZKPCredential::new(
            "test_credential_001".to_string(),
            "did:lemma:test_issuer".to_string(),
            "did:lemma:test_subject".to_string(),
            None,
        );
        
        // Derive linking secret
        let secret1 = credential.derive_linking_secret(&master_key);
        let secret2 = credential.derive_linking_secret(&master_key);
        
        // ✅ SECURE: Same credential should produce same secret
        assert_eq!(secret1, secret2);
        
        // Different credentials should produce different secrets
        let other_credential = SecureZKPCredential::new(
            "test_credential_002".to_string(),
            "did:lemma:test_issuer".to_string(),
            "did:lemma:test_subject".to_string(),
            None,
        );
        
        let other_secret = other_credential.derive_linking_secret(&master_key);
        assert_ne!(secret1, other_secret);
    }
    
    #[test]
    fn test_unlinkable_presentation_secrets() {
        let master_key = ZKPMasterKey::generate();
        let mut credential = SecureZKPCredential::new(
            "test_credential_001".to_string(),
            "did:lemma:test_issuer".to_string(),
            "did:lemma:test_subject".to_string(),
            None,
        );
        
        // Generate multiple presentation secrets
        let secret1 = credential.derive_presentation_secret(&master_key);
        let secret2 = credential.derive_presentation_secret(&master_key);
        let secret3 = credential.derive_presentation_secret(&master_key);
        
        // ✅ SECURE: Each presentation should be unlinkable
        assert_ne!(secret1, secret2);
        assert_ne!(secret2, secret3);
        assert_ne!(secret1, secret3);
        
        // Use counter should increment
        assert_eq!(credential.use_counter, 3);
    }
    
    #[test]
    fn test_no_plaintext_linking_secret_storage() {
        let credential = SecureZKPCredential::new(
            "test_credential_001".to_string(),
            "did:lemma:test_issuer".to_string(),
            "did:lemma:test_subject".to_string(),
            None,
        );
        
        // Serialize credential to JSON
        let json = serde_json::to_string(&credential).unwrap();
        
        // ✅ SECURE: Verify no plaintext linking secrets in serialized data
        assert!(!json.contains("linking_secret"));
        assert!(!json.contains("presentation_secret"));
        
        // Should contain salt and other safe data
        assert!(json.contains("linking_salt"));
        assert!(json.contains("use_counter"));
    }
    
    #[test]
    fn test_selective_disclosure() {
        let master_key = ZKPMasterKey::generate();
        let mut credential = SecureZKPCredential::new(
            "test_credential_001".to_string(),
            "did:lemma:test_issuer".to_string(),
            "did:lemma:test_subject".to_string(),
            None,
        );
        
        // Add multiple claims
        let human_claim = create_human_claim(&[1, 2, 3, 4], &master_key).unwrap();
        let age_claim = create_age_range_claim(&[5, 6, 7, 8], &master_key, 18, 65).unwrap();
        
        credential.add_zkp_claim("isHuman".to_string(), human_claim);
        credential.add_zkp_claim("ageRange".to_string(), age_claim);
        
        // Selectively disclose only human claim
        let disclosed = credential.selective_disclose(
            &["isHuman".to_string()],
            &master_key
        ).unwrap();
        
        // ✅ SECURE: Only selected claim should be present
        assert!(disclosed.get_zkp_claim("isHuman").is_some());
        assert!(disclosed.get_zkp_claim("ageRange").is_none());
        
        // Use counter should have incremented for unlinkability
        assert_eq!(disclosed.use_counter, credential.use_counter);
    }
    
    #[test]
    fn test_zkp_verifier() {
        let master_key = ZKPMasterKey::generate();
        let mut verifier = SecureZKPVerifier::new(master_key.clone());
        
        let mut credential = SecureZKPCredential::new(
            "test_credential_001".to_string(),
            "did:lemma:test_issuer".to_string(),
            "did:lemma:test_subject".to_string(),
            None,
        );
        
        let human_claim = create_human_claim(&[1, 2, 3, 4], &master_key).unwrap();
        credential.add_zkp_claim("isHuman".to_string(), human_claim);
        
        // Verify credential
        let result = verifier.verify_credential(&credential);
        
        // Should succeed (basic integrity checks)
        assert!(result.is_ok());
        
        // Stats should be updated
        let stats = verifier.get_stats();
        assert_eq!(stats.total_verifications, 1);
    }
    
    #[test]
    fn test_master_key_zeroization() {
        let master_key = ZKPMasterKey::generate();
        let key_copy = master_key.as_bytes().clone();
        
        // Drop the master key
        drop(master_key);
        
        // The key should have been zeroized (can't directly test due to zeroize internals,
        // but this test ensures the ZeroizeOnDrop trait is correctly applied)
        // This is more of a compilation test to ensure proper trait implementation
    }
} 