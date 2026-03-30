//! ZKP Claims System
//! 
//! Zero-Knowledge Proofs for claims that are validated by complete lemma verification
//! (non-revoked OPRF + valid Ed25519 signature)

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use sha2::{Sha256, Digest};

use crate::minimal_core::{MinimalCredential, MinimalError};
use crate::complete_verification::{CompleteVerificationResult, CompleteVerifier};

/// ZKP Claim types that can be proven without revealing the claim value
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ZKPClaimType {
    /// Prove age is above threshold without revealing exact age
    AgeAbove(u32),
    /// Prove membership in a set without revealing which member
    SetMembership(Vec<String>),
    /// Prove a numeric value is within range without revealing value
    NumericRange { min: i64, max: i64 },
    /// Custom claim validation
    Custom(String),
}

/// ZKP Claim proof (simplified - not full ZK implementation yet)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ZKPClaimProof {
    pub claim_type: ZKPClaimType,
    pub proof_data: Vec<u8>,        // Simplified proof (would be actual ZK proof)
    pub public_inputs: Vec<u8>,     // Public parameters
    pub verified_by_lemma: bool,    // Must be validated by complete lemma verification
    pub lemma_verification_hash: String, // Hash of the complete verification result
}

/// ZKP Credential that contains claims validated by lemma verification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ZKPCredential {
    pub base_credential: MinimalCredential, // The underlying credential
    pub zkp_claims: Vec<ZKPClaimProof>,     // ZK proofs for specific claims
    pub validation_timestamp: u64,         // When lemma verification occurred
    pub validation_result_hash: String,    // Hash of complete verification result
}

/// ZKP Verifier that ensures claims are backed by complete lemma verification
pub struct ZKPVerifier {
    complete_verifier: CompleteVerifier,
}

impl ZKPVerifier {
    /// Create a new ZKP verifier
    pub fn new() -> std::result::Result<Self, MinimalError> {
        let complete_verifier = CompleteVerifier::new()?;
        
        Ok(Self {
            complete_verifier,
        })
    }
    
    /// Create ZKP credential with claims validated by complete lemma verification
    pub fn create_zkp_credential(
        &mut self,
        base_credential: MinimalCredential,
        zkp_claims: Vec<ZKPClaimType>,
    ) -> std::result::Result<ZKPCredential, MinimalError> {
        
        // CRITICAL: First verify the base credential with complete lemma verification
        let verification_result = self.complete_verifier.verify_complete(&base_credential)?;
        
        if !verification_result.verified {
            return Err(MinimalError::InvalidSignature);
        }
        
        // Create validation hash from the complete verification
        let validation_hash = self.create_validation_hash(&verification_result);
        
        // Create ZKP proofs for each claim (simplified implementation)
        let mut zkp_claim_proofs = Vec::new();
        
        for claim_type in zkp_claims {
            // Verify the claim exists in the base credential
            let claim_valid = self.validate_claim_against_credential(&claim_type, &base_credential)?;
            
            if !claim_valid {
                return Err(MinimalError::Serialization("Claim not found in credential".to_string()));
            }
            
            // Create simplified ZKP proof (in production, this would be actual ZK proof)
            let proof = ZKPClaimProof {
                claim_type: claim_type.clone(),
                proof_data: self.create_simplified_proof(&claim_type, &base_credential)?,
                public_inputs: self.extract_public_inputs(&claim_type)?,
                verified_by_lemma: true,
                lemma_verification_hash: validation_hash.clone(),
            };
            
            zkp_claim_proofs.push(proof);
        }
        
        Ok(ZKPCredential {
            base_credential,
            zkp_claims: zkp_claim_proofs,
            validation_timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            validation_result_hash: validation_hash,
        })
    }
    
    /// Verify ZKP credential - ensures underlying lemma verification is still valid
    pub fn verify_zkp_credential(
        &mut self,
        zkp_credential: &ZKPCredential,
    ) -> std::result::Result<CompleteVerificationResult, MinimalError> {
        
        // Re-verify the base credential with complete lemma verification
        let current_verification = self.complete_verifier.verify_complete(&zkp_credential.base_credential)?;
        
        // Ensure the current verification matches the original validation
        let current_hash = self.create_validation_hash(&current_verification);
        
        if current_hash != zkp_credential.validation_result_hash {
            // The underlying credential verification has changed (possibly revoked)
            return Ok(CompleteVerificationResult {
                verified: false,
                signature_valid: current_verification.signature_valid,
                not_revoked: current_verification.not_revoked,
                issuer_did: current_verification.issuer_did,
                verification_time_ns: current_verification.verification_time_ns,
                signature_time_ns: current_verification.signature_time_ns,
                revocation_time_ns: current_verification.revocation_time_ns,
                confidence: 0.0, // ZKP invalid due to base verification change
            });
        }
        
        // If base verification still valid, ZKP claims are still valid
        Ok(current_verification)
    }
    
    /// Verify a specific ZKP claim without revealing the claim value
    pub fn verify_zkp_claim(
        &self,
        zkp_proof: &ZKPClaimProof,
        public_challenge: &[u8],
    ) -> std::result::Result<bool, MinimalError> {
        
        // Ensure the claim was validated by lemma verification
        if !zkp_proof.verified_by_lemma {
            return Ok(false);
        }
        
        // Simplified ZKP verification (in production, this would be actual ZK verification)
        // For now, just verify the proof structure is valid
        match &zkp_proof.claim_type {
            ZKPClaimType::AgeAbove(threshold) => {
                // In real ZKP: verify age > threshold without revealing age
                // For now: simplified check
                Ok(zkp_proof.proof_data.len() > 0 && *threshold > 0)
            },
            ZKPClaimType::SetMembership(set) => {
                // In real ZKP: verify membership without revealing which member
                Ok(zkp_proof.proof_data.len() > 0 && !set.is_empty())
            },
            ZKPClaimType::NumericRange { min, max } => {
                // In real ZKP: verify value in range without revealing value
                Ok(zkp_proof.proof_data.len() > 0 && min < max)
            },
            ZKPClaimType::Custom(_) => {
                // Custom claim validation
                Ok(zkp_proof.proof_data.len() > 0)
            },
        }
    }
    
    /// Create validation hash from complete verification result
    fn create_validation_hash(&self, result: &CompleteVerificationResult) -> String {
        let mut hasher = Sha256::new();
        hasher.update(result.issuer_did.as_bytes());
        hasher.update(&result.verified.to_string().as_bytes());
        hasher.update(&result.signature_valid.to_string().as_bytes());
        hasher.update(&result.not_revoked.to_string().as_bytes());
        hasher.update(&result.confidence.to_be_bytes());
        
        hex::encode(hasher.finalize())
    }
    
    /// Validate that a claim exists in the credential
    fn validate_claim_against_credential(
        &self,
        claim_type: &ZKPClaimType,
        credential: &MinimalCredential,
    ) -> std::result::Result<bool, MinimalError> {
        match claim_type {
            ZKPClaimType::AgeAbove(threshold) => {
                // Check if credential has age claim
                if let Some(age_value) = credential.claims.get("age") {
                    // Try as number first, then as string
                    if let Some(age) = age_value.as_u64() {
                        return Ok(age as u32 >= *threshold);
                    } else if let Some(age_str) = age_value.as_str() {
                        if let Ok(age) = age_str.parse::<u32>() {
                            return Ok(age >= *threshold);
                        }
                    }
                }
                Ok(false)
            },
            ZKPClaimType::SetMembership(set) => {
                // Check if credential has membership claim
                if let Some(member_value) = credential.claims.get("membership") {
                    if let Some(member) = member_value.as_str() {
                        return Ok(set.contains(&member.to_string()));
                    }
                }
                Ok(false)
            },
            ZKPClaimType::NumericRange { min, max } => {
                // Check if credential has numeric claim in range
                if let Some(value) = credential.claims.get("numericValue") {
                    if let Some(num) = value.as_i64() {
                        return Ok(num >= *min && num <= *max);
                    }
                }
                Ok(false)
            },
            ZKPClaimType::Custom(claim_name) => {
                // Check if custom claim exists
                Ok(credential.claims.contains_key(claim_name))
            },
        }
    }
    
    /// Create simplified proof (in production, this would be actual ZK proof generation)
    fn create_simplified_proof(
        &self,
        claim_type: &ZKPClaimType,
        credential: &MinimalCredential,
    ) -> std::result::Result<Vec<u8>, MinimalError> {
        // Simplified proof generation - in production this would use actual ZK libraries
        let mut hasher = Sha256::new();
        hasher.update(credential.id.as_bytes());
        hasher.update(&serde_json::to_string(claim_type).unwrap().as_bytes());
        hasher.update(b"ZKP_PROOF_PLACEHOLDER");
        
        Ok(hasher.finalize().to_vec())
    }
    
    /// Extract public inputs for ZKP verification
    fn extract_public_inputs(&self, claim_type: &ZKPClaimType) -> std::result::Result<Vec<u8>, MinimalError> {
        // Public parameters that can be revealed
        let mut hasher = Sha256::new();
        
        match claim_type {
            ZKPClaimType::AgeAbove(threshold) => {
                hasher.update(b"AGE_ABOVE");
                hasher.update(&threshold.to_be_bytes());
            },
            ZKPClaimType::SetMembership(set) => {
                hasher.update(b"SET_MEMBERSHIP");
                hasher.update(&(set.len() as u32).to_be_bytes());
            },
            ZKPClaimType::NumericRange { min, max } => {
                hasher.update(b"NUMERIC_RANGE");
                hasher.update(&min.to_be_bytes());
                hasher.update(&max.to_be_bytes());
            },
            ZKPClaimType::Custom(name) => {
                hasher.update(b"CUSTOM_CLAIM");
                hasher.update(name.as_bytes());
            },
        }
        
        Ok(hasher.finalize().to_vec())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::minimal_core::MinimalIssuer;
    
    #[test]
    fn test_zkp_claims_with_complete_verification() {
        let mut zkp_verifier = ZKPVerifier::new().unwrap();
        
        // Create issuer and credential with age claim
        let issuer = MinimalIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("age".to_string(), serde_json::Value::Number(serde_json::Number::from(25)));
        claims.insert("membership".to_string(), serde_json::Value::String("premium".to_string()));
        
        let base_credential = issuer.issue_credential(
            "did:lemma:user_alice".to_string(),
            claims,
        ).unwrap();
        
        // Create ZKP claims
        let zkp_claims = vec![
            ZKPClaimType::AgeAbove(21),  // Prove age > 21 without revealing age
            ZKPClaimType::SetMembership(vec!["premium".to_string(), "basic".to_string()]), // Prove membership
        ];
        
        // Create ZKP credential (this validates the base credential first)
        let zkp_credential = zkp_verifier.create_zkp_credential(base_credential, zkp_claims).unwrap();
        
        println!("✅ ZKP credential created with {} claims", zkp_credential.zkp_claims.len());
        println!("   Base credential verified: {}", zkp_credential.zkp_claims[0].verified_by_lemma);
        
        // Verify the ZKP credential
        let verification_result = zkp_verifier.verify_zkp_credential(&zkp_credential).unwrap();
        
        assert!(verification_result.verified);
        println!("✅ ZKP credential verification passed");
        
        // Test individual ZKP claim verification
        let age_proof = &zkp_credential.zkp_claims[0];
        let age_valid = zkp_verifier.verify_zkp_claim(age_proof, b"public_challenge").unwrap();
        assert!(age_valid);
        
        println!("✅ ZKP age claim verification passed");
    }
}
