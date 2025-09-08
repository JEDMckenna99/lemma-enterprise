//! Complete Verification System
//! 
//! Combines Ed25519 signature verification + OPRF revocation checking
//! This is the REAL authentication system that requires BOTH components

use crate::minimal_core::{MinimalCredential, MinimalVerifier, MinimalError};
use crate::oprf::OPRFClient;
use crate::bloom::CascadedBloomFilter;
use std::collections::HashMap;

/// Complete verification result
#[derive(Debug, Clone)]
pub struct CompleteVerificationResult {
    pub verified: bool,
    pub signature_valid: bool,
    pub not_revoked: bool,
    pub issuer_did: String,
    pub verification_time_ns: u64,
    pub signature_time_ns: u64,
    pub revocation_time_ns: u64,
    pub confidence: f64,
}

/// Complete verifier that checks BOTH signature AND revocation
pub struct CompleteVerifier {
    signature_verifier: MinimalVerifier,
    oprf_client: OPRFClient,
    revocation_filter: CascadedBloomFilter,
}

impl CompleteVerifier {
    /// Create a new complete verifier
    pub fn new() -> std::result::Result<Self, MinimalError> {
        let signature_verifier = MinimalVerifier::new();
        
        // Use shared OPRF key for network consistency
        let server_key = [42u8; 32]; // In production, this would be network-shared
        let oprf_client = OPRFClient::new_with_server_key(server_key);
        
        // Create revocation bloom filter
        let revocation_filter = CascadedBloomFilter::new(3, 10000, 0.001)
            .map_err(|_| MinimalError::InvalidKey)?;
        
        Ok(Self {
            signature_verifier,
            oprf_client,
            revocation_filter,
        })
    }
    
    /// Complete verification: Ed25519 signature + OPRF revocation
    pub fn verify_complete(&mut self, credential: &MinimalCredential) -> std::result::Result<CompleteVerificationResult, MinimalError> {
        let total_start = std::time::Instant::now();
        
        // Step 1: Verify Ed25519 signature
        let sig_start = std::time::Instant::now();
        let signature_valid = self.signature_verifier.verify(credential)?;
        let signature_time_ns = sig_start.elapsed().as_nanos() as u64;
        
        // Step 2: Check revocation using OPRF + Bloom
        let revocation_start = std::time::Instant::now();
        let not_revoked = if signature_valid {
            self.check_not_revoked(&credential.id)?
        } else {
            false // If signature invalid, don't bother checking revocation
        };
        let revocation_time_ns = revocation_start.elapsed().as_nanos() as u64;
        
        let total_time_ns = total_start.elapsed().as_nanos() as u64;
        
        // Both signature AND revocation must pass
        let verified = signature_valid && not_revoked;
        
        // Calculate confidence based on both checks
        let confidence = if verified {
            if signature_valid && not_revoked { 1.0 }
            else { 0.0 }
        } else {
            0.0
        };
        
        Ok(CompleteVerificationResult {
            verified,
            signature_valid,
            not_revoked,
            issuer_did: credential.issuer.clone(),
            verification_time_ns: total_time_ns,
            signature_time_ns,
            revocation_time_ns,
            confidence,
        })
    }
    
    /// Check if credential is NOT revoked using OPRF + Bloom
    fn check_not_revoked(&mut self, credential_id: &str) -> std::result::Result<bool, MinimalError> {
        // Step 1: Get OPRF evaluation for privacy
        let oprf_result = self.oprf_client.get_evaluation(credential_id)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        // Step 2: Check if OPRF result is in revocation bloom filter
        let (is_revoked, _level) = self.revocation_filter.contains(&oprf_result.evaluation);
        
        // Return true if NOT revoked
        Ok(!is_revoked)
    }
    
    /// Add a credential to the revocation list
    pub fn revoke_credential(&mut self, credential_id: &str) -> std::result::Result<(), MinimalError> {
        // Get OPRF evaluation
        let oprf_result = self.oprf_client.get_evaluation(credential_id)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        // Add to revocation bloom filter
        self.revocation_filter.add(&oprf_result.evaluation)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        Ok(())
    }
    
    /// Verify from JSON string
    pub fn verify_credential_json(&mut self, credential_json: &str) -> std::result::Result<CompleteVerificationResult, MinimalError> {
        let credential: MinimalCredential = serde_json::from_str(credential_json)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        self.verify_complete(&credential)
    }
    
    /// Get verification stats
    pub fn get_stats(&self) -> HashMap<String, serde_json::Value> {
        let mut stats = HashMap::new();
        stats.insert("signature_verifier".to_string(), serde_json::Value::String("Ed25519".to_string()));
        stats.insert("revocation_system".to_string(), serde_json::Value::String("OPRF + Bloom".to_string()));
        stats.insert("privacy_preserving".to_string(), serde_json::Value::Bool(true));
        stats.insert("offline_capable".to_string(), serde_json::Value::Bool(true));
        stats
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::minimal_core::MinimalIssuer;
    
    #[test]
    fn test_complete_verification_system() {
        let mut verifier = CompleteVerifier::new().unwrap();
        
        // Create issuer and credential
        let issuer = MinimalIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        
        let credential = issuer.issue_credential(
            "did:lemma:test_subject".to_string(),
            claims,
        ).unwrap();
        
        // Test 1: Valid credential should pass both checks
        let result = verifier.verify_complete(&credential).unwrap();
        assert!(result.verified);
        assert!(result.signature_valid);
        assert!(result.not_revoked);
        assert_eq!(result.confidence, 1.0);
        
        println!("✅ Valid credential verification:");
        println!("   Total time: {} ns", result.verification_time_ns);
        println!("   Signature time: {} ns", result.signature_time_ns);
        println!("   Revocation time: {} ns", result.revocation_time_ns);
        
        // Test 2: Revoke the credential
        verifier.revoke_credential(&credential.id).unwrap();
        
        // Test 3: Revoked credential should fail
        let result = verifier.verify_complete(&credential).unwrap();
        assert!(!result.verified);
        assert!(result.signature_valid); // Signature still valid
        assert!(!result.not_revoked);    // But revoked
        assert_eq!(result.confidence, 0.0);
        
        println!("✅ Revoked credential correctly rejected");
    }
}
