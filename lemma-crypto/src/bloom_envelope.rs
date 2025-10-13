//! Signed, versioned bloom filter envelopes for secure distribution
//!
//! NOTE: This is a simplified version for MVP. Full implementation with 
//! bincode serialization of CascadedBloomFilter will be added in Phase 2.

use serde::{Serialize, Deserialize};
use ed25519_dalek::{Signer, Verifier, SigningKey, VerifyingKey, Signature};
use sha2::{Sha256, Digest};
use crate::Result;

/// Bloom filter parameters for verification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BloomFilterParams {
    pub num_levels: usize,
    pub base_capacity: usize,
    pub false_positive_rate: f64,
    pub num_hash_functions: usize,
}

/// Signed bloom filter envelope (simplified version)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BloomFilterEnvelope {
    // Filter data (raw bytes for now)
    #[serde(with = "serde_bytes")]
    pub filter_data: Vec<u8>,
    
    // Versioning
    pub version: u64,
    pub previous_version: Option<u64>,
    #[serde(with = "serde_bytes")]
    pub previous_version_hash: Option<Vec<u8>>,
    
    // OPRF key association
    pub oprf_key_version: u32,
    
    // Temporal validity
    pub created_at: i64,
    pub valid_from: i64,
    pub valid_until: i64,
    
    // Content hash (for integrity)
    #[serde(with = "serde_bytes")]
    pub content_hash: Vec<u8>,
    
    // Metadata
    pub filter_params: BloomFilterParams,
    pub item_count: usize,
    
    // Cryptographic proof
    #[serde(with = "serde_bytes")]
    pub signature: Vec<u8>,
    pub issuer_did: String,
}

impl BloomFilterEnvelope {
    /// Create new signed envelope (simplified - takes raw bytes)
    pub fn create_simple(
        filter_data: Vec<u8>,
        oprf_key_version: u32,
        previous_envelope: Option<&BloomFilterEnvelope>,
        signing_key: &SigningKey,
        issuer_did: String,
    ) -> Result<Self> {
        let now = crate::utils::current_timestamp() as i64;
        
        // Compute content hash
        let content_hash = Self::compute_hash(&filter_data, oprf_key_version, now);
        
        // Version handling
        let (version, previous_version, previous_version_hash) = if let Some(prev) = previous_envelope {
            (
                prev.version + 1,
                Some(prev.version),
                Some(prev.content_hash.clone()),
            )
        } else {
            (1, None, None)
        };
        
        // Simple filter params (can be customized)
        let filter_params = BloomFilterParams {
            num_levels: 3,
            base_capacity: 10000,
            false_positive_rate: 0.001,
            num_hash_functions: 7,
        };
        
        let mut envelope = Self {
            filter_data,
            version,
            previous_version,
            previous_version_hash,
            oprf_key_version,
            created_at: now,
            valid_from: now,
            valid_until: now + (7 * 24 * 3600), // 7 days
            content_hash: content_hash.to_vec(),
            filter_params,
            item_count: 0,
            signature: vec![],
            issuer_did,
        };
        
        // Sign the envelope
        envelope.sign(signing_key)?;
        
        Ok(envelope)
    }

    /// Sign the envelope
    fn sign(&mut self, signing_key: &SigningKey) -> Result<()> {
        let message = self.create_signature_message();
        let signature = signing_key.sign(&message);
        self.signature = signature.to_bytes().to_vec();
        Ok(())
    }

    /// Verify envelope integrity and signature
    pub fn verify(&self, network_authority_public_key: &VerifyingKey) -> Result<()> {
        // 1. Verify content hash
        let computed_hash = Self::compute_hash(&self.filter_data, self.oprf_key_version, self.created_at);
        if computed_hash.as_slice() != self.content_hash.as_slice() {
            return Err(crate::LemmaError::Bloom("Hash mismatch".to_string()));
        }
        
        // 2. Verify temporal validity
        let now = crate::utils::current_timestamp() as i64;
        if now < self.valid_from {
            return Err(crate::LemmaError::Bloom("Not yet valid".to_string()));
        }
        if now > self.valid_until {
            return Err(crate::LemmaError::Bloom("Expired".to_string()));
        }
        
        // 3. Verify signature
        self.verify_signature(network_authority_public_key)?;
        
        Ok(())
    }

    /// Verify version chain
    pub fn verify_chain(&self, previous_envelope: &BloomFilterEnvelope) -> Result<()> {
        // Check version sequence
        if self.version != previous_envelope.version + 1 {
            return Err(crate::LemmaError::Bloom("Invalid version sequence".to_string()));
        }
        
        // Check previous version hash
        if let Some(ref prev_hash) = self.previous_version_hash {
            if prev_hash.as_slice() != previous_envelope.content_hash.as_slice() {
                return Err(crate::LemmaError::Bloom("Chain broken".to_string()));
            }
        } else {
            return Err(crate::LemmaError::Bloom("Missing previous version".to_string()));
        }
        
        // Check timestamps (new envelope should be newer)
        if self.created_at <= previous_envelope.created_at {
            return Err(crate::LemmaError::Bloom("Invalid timestamp".to_string()));
        }
        
        Ok(())
    }

    /// Verify signature
    fn verify_signature(&self, public_key: &VerifyingKey) -> Result<()> {
        let message = self.create_signature_message();
        
        if self.signature.len() != 64 {
            return Err(crate::LemmaError::Bloom("Invalid signature length".to_string()));
        }
        
        let mut sig_bytes = [0u8; 64];
        sig_bytes.copy_from_slice(&self.signature);
        let signature = Signature::from_bytes(&sig_bytes);
        
        public_key
            .verify(&message, &signature)
            .map_err(|_| crate::LemmaError::Bloom("Signature verification failed".to_string()))?;
        
        Ok(())
    }

    /// Create canonical message for signature
    fn create_signature_message(&self) -> Vec<u8> {
        let mut message = Vec::new();
        message.extend_from_slice(&self.version.to_le_bytes());
        message.extend_from_slice(&self.content_hash);
        message.extend_from_slice(&self.created_at.to_le_bytes());
        message.extend_from_slice(&self.valid_until.to_le_bytes());
        message.extend_from_slice(&self.oprf_key_version.to_le_bytes());
        message
    }

    /// Compute content hash
    fn compute_hash(filter_data: &[u8], oprf_key_version: u32, created_at: i64) -> [u8; 32] {
        let mut hasher = Sha256::new();
        hasher.update(filter_data);
        hasher.update(&oprf_key_version.to_le_bytes());
        hasher.update(&created_at.to_le_bytes());
        let hash = hasher.finalize();
        let mut result = [0u8; 32];
        result.copy_from_slice(&hash);
        result
    }

    /// Get filter data
    pub fn get_filter_data(&self) -> &[u8] {
        &self.filter_data
    }

    /// Check if envelope needs refresh
    pub fn should_refresh(&self) -> bool {
        let now = crate::utils::current_timestamp() as i64;
        let time_until_expiry = self.valid_until - now;
        time_until_expiry < 24 * 3600 // Less than 24 hours
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_envelope_creation_and_verification() {
        // Create signing key
        let mut csprng = rand::rngs::OsRng;
        let signing_key = SigningKey::generate(&mut csprng);
        let verifying_key = signing_key.verifying_key();
        
        // Create envelope with dummy data
        let filter_data = vec![1, 2, 3, 4, 5];
        
        let envelope = BloomFilterEnvelope::create_simple(
            filter_data,
            1, // OPRF key version
            None, // No previous envelope
            &signing_key,
            "did:lemma:test_issuer".to_string(),
        ).unwrap();
        
        // Verify envelope
        assert!(envelope.verify(&verifying_key).is_ok());
    }

    #[test]
    fn test_envelope_chain_validation() {
        let mut csprng = rand::rngs::OsRng;
        let signing_key = SigningKey::generate(&mut csprng);
        
        let filter_data = vec![1, 2, 3, 4, 5];
        
        // Create first envelope
        let envelope1 = BloomFilterEnvelope::create_simple(
            filter_data.clone(),
            1,
            None,
            &signing_key,
            "did:lemma:test_issuer".to_string(),
        ).unwrap();
        
        // Create second envelope (chained)
        let envelope2 = BloomFilterEnvelope::create_simple(
            filter_data,
            1,
            Some(&envelope1),
            &signing_key,
            "did:lemma:test_issuer".to_string(),
        ).unwrap();
        
        // Verify chain
        assert!(envelope2.verify_chain(&envelope1).is_ok());
        assert_eq!(envelope2.version, 2);
        assert_eq!(envelope2.previous_version, Some(1));
    }
}
