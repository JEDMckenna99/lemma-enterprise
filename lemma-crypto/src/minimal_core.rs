//! Minimal Working Crypto Core
//! 
//! This is a complete rewrite focusing on WORKING basic cryptography
//! before any optimizations. Goal: Actually verify Ed25519 signatures.

use ed25519_dalek::{Signer, Verifier, SigningKey, VerifyingKey, Signature};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use sha2::{Sha256, Digest};
use rand::rngs::OsRng;
use std::time::{SystemTime, UNIX_EPOCH};

// Don't use the broken crate::Result - use our own

/// Simple error type for minimal core
#[derive(Debug, thiserror::Error)]
pub enum MinimalError {
    #[error("Invalid signature")]
    InvalidSignature,
    #[error("Invalid DID format")]
    InvalidDID,
    #[error("Invalid key format")]
    InvalidKey,
    #[error("Serialization error: {0}")]
    Serialization(String),
    #[error("Ed25519 error: {0}")]
    Ed25519(#[from] ed25519_dalek::SignatureError),
}

/// W3C compliant Verifiable Credential
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MinimalCredential {
    #[serde(rename = "@context")]
    pub context: Vec<String>,        // W3C standard: @context field
    pub id: String,
    pub issuer: String,              // DID format: did:lemma:{public_key_hex}
    pub subject: String,
    #[serde(rename = "issuanceDate")]
    pub issued_at: u64,              // W3C uses issuanceDate
    #[serde(rename = "expirationDate")]
    pub expires_at: Option<u64>,     // W3C uses expirationDate
    #[serde(rename = "credentialSubject")]
    pub claims: HashMap<String, serde_json::Value>,  // W3C uses credentialSubject
    pub proof: Option<MinimalProof>,
}

/// W3C compliant cryptographic proof
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MinimalProof {
    #[serde(rename = "type")]
    pub proof_type: String,           // W3C standard: "type" field
    pub created: u64,
    #[serde(rename = "verificationMethod")]
    pub verification_method: String,  // W3C standard: camelCase
    #[serde(rename = "signatureValue")]
    pub signature_value: String,      // W3C standard: camelCase
}

/// Minimal credential issuer that ACTUALLY works
pub struct MinimalIssuer {
    signing_key: SigningKey,
    verifying_key: VerifyingKey,
    did: String,
}

impl MinimalIssuer {
    /// Create a new issuer with fresh Ed25519 keypair
    pub fn new() -> Self {
        let signing_key = SigningKey::generate(&mut OsRng);
        let verifying_key = signing_key.verifying_key();
        
        // Create DID from public key
        let public_key_bytes = verifying_key.to_bytes();
        let public_key_hex = hex::encode(public_key_bytes);
        let did = format!("did:lemma:{}", public_key_hex);
        
        Self {
            signing_key,
            verifying_key,
            did,
        }
    }
    
    /// Create an issuer from a deterministic seed (for production consistency)
    pub fn from_seed(seed: &[u8; 32]) -> Self {
        let signing_key = SigningKey::from_bytes(seed);
        let verifying_key = signing_key.verifying_key();
        
        // Create DID from public key
        let public_key_bytes = verifying_key.to_bytes();
        let public_key_hex = hex::encode(public_key_bytes);
        let did = format!("did:lemma:{}", public_key_hex);
        
        Self {
            signing_key,
            verifying_key,
            did,
        }
    }
    
    /// Create an issuer from environment variable or default seed (production)
    pub fn from_env_or_default() -> Self {
        use std::env;
        use sha2::{Sha256, Digest};
        
        // Try to get seed from environment variable
        let seed_source = env::var("LEMMA_ISSUER_SEED")
            .unwrap_or_else(|_| "lemma_production_issuer_seed_2024".to_string());
        
        // Create deterministic 32-byte seed from string
        let mut hasher = Sha256::new();
        hasher.update(seed_source.as_bytes());
        let hash_result = hasher.finalize();
        
        let mut seed = [0u8; 32];
        seed.copy_from_slice(&hash_result[..32]);
        
        Self::from_seed(&seed)
    }
    
    /// Get the issuer's DID
    pub fn did(&self) -> &str {
        &self.did
    }
    
    /// Get the public key as hex
    pub fn public_key_hex(&self) -> String {
        hex::encode(self.verifying_key.to_bytes())
    }
    
    /// Get the signing key bytes (for KMS encryption)
    /// WARNING: This exposes the private key - only use for secure storage!
    pub fn signing_key_bytes(&self) -> [u8; 32] {
        self.signing_key.to_bytes()
    }
    
    /// Issue and sign a credential
    pub fn issue_credential(
        &self,
        subject: String,
        claims: HashMap<String, serde_json::Value>,
    ) -> std::result::Result<MinimalCredential, MinimalError> {
        let current_time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        
        let credential_id = format!("cred_{}", uuid::Uuid::new_v4());
        
        // Create W3C compliant credential
        let mut credential = MinimalCredential {
            context: vec![
                "https://www.w3.org/2018/credentials/v1".to_string(),
                "https://lemma.id/contexts/v1".to_string()
            ],
            id: credential_id,
            issuer: self.did.clone(),
            subject,
            issued_at: current_time,
            expires_at: Some(current_time + (2 * 365 * 24 * 60 * 60)), // 2 years
            claims,
            proof: None,
        };
        
        // Create the message to sign
        let message = self.create_signing_message(&credential)?;
        
        // Sign the message
        let signature = self.signing_key.sign(&message);
        let signature_hex = hex::encode(signature.to_bytes());
        
        // Add the proof (W3C compliant)
        credential.proof = Some(MinimalProof {
            proof_type: "Ed25519Signature2020".to_string(),
            created: current_time,
            verification_method: self.did.clone(),
            signature_value: signature_hex,
        });
        
        Ok(credential)
    }
    
    /// Create the message that gets signed
    fn create_signing_message(&self, credential: &MinimalCredential) -> std::result::Result<Vec<u8>, MinimalError> {
        // Create a deterministic message from the credential
        let mut hasher = Sha256::new();
        
        // Add credential fields in a deterministic order
        hasher.update(credential.id.as_bytes());
        hasher.update(credential.issuer.as_bytes());
        hasher.update(credential.subject.as_bytes());
        hasher.update(credential.issued_at.to_le_bytes());
        
        if let Some(expires_at) = credential.expires_at {
            hasher.update(expires_at.to_le_bytes());
        }
        
        // Add claims in sorted order for determinism
        let mut claim_keys: Vec<_> = credential.claims.keys().collect();
        claim_keys.sort();
        
        for key in claim_keys {
            hasher.update(key.as_bytes());
            let value_str = serde_json::to_string(&credential.claims[key])
                .map_err(|e| MinimalError::Serialization(e.to_string()))?;
            hasher.update(value_str.as_bytes());
        }
        
        Ok(hasher.finalize().to_vec())
    }
}

/// Minimal verifier that ACTUALLY works
pub struct MinimalVerifier;

impl MinimalVerifier {
    pub fn new() -> Self {
        Self
    }
    
    /// Verify a credential's signature
    pub fn verify(&self, credential: &MinimalCredential) -> std::result::Result<bool, MinimalError> {
        // Extract proof
        let proof = credential.proof.as_ref()
            .ok_or(MinimalError::InvalidSignature)?;
        
        // Extract public key from issuer DID
        let public_key = self.extract_public_key_from_did(&credential.issuer)?;
        
        // Recreate the signing message
        let message = self.create_verification_message(credential)?;
        
        // Decode the signature
        let signature_bytes = hex::decode(&proof.signature_value)
            .map_err(|_| MinimalError::InvalidSignature)?;
        
        if signature_bytes.len() != 64 {
            return Err(MinimalError::InvalidSignature);
        }
        
        let mut sig_array = [0u8; 64];
        sig_array.copy_from_slice(&signature_bytes);
        let signature = Signature::from_bytes(&sig_array);
        
        // Verify the signature
        match public_key.verify(&message, &signature) {
            Ok(()) => Ok(true),
            Err(_) => Ok(false),
        }
    }
    
    /// Extract public key from DID
    fn extract_public_key_from_did(&self, did: &str) -> std::result::Result<VerifyingKey, MinimalError> {
        let parts: Vec<&str> = did.split(':').collect();
        
        if parts.len() != 3 || parts[0] != "did" || parts[1] != "lemma" {
            return Err(MinimalError::InvalidDID);
        }
        
        let public_key_hex = parts[2];
        
        // Decode hex to bytes
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
    
    /// Create the verification message (same as signing message)
    fn create_verification_message(&self, credential: &MinimalCredential) -> std::result::Result<Vec<u8>, MinimalError> {
        let mut hasher = Sha256::new();
        
        // Add credential fields in the same deterministic order as signing
        hasher.update(credential.id.as_bytes());
        hasher.update(credential.issuer.as_bytes());
        hasher.update(credential.subject.as_bytes());
        hasher.update(credential.issued_at.to_le_bytes());
        
        if let Some(expires_at) = credential.expires_at {
            hasher.update(expires_at.to_le_bytes());
        }
        
        // Add claims in sorted order for determinism
        let mut claim_keys: Vec<_> = credential.claims.keys().collect();
        claim_keys.sort();
        
        for key in claim_keys {
            hasher.update(key.as_bytes());
            let value_str = serde_json::to_string(&credential.claims[key])
                .map_err(|e| MinimalError::Serialization(e.to_string()))?;
            hasher.update(value_str.as_bytes());
        }
        
        Ok(hasher.finalize().to_vec())
    }
}

/// Minimal verification result
#[derive(Debug, Clone)]
pub struct MinimalVerificationResult {
    pub verified: bool,
    pub issuer_did: String,
    pub verification_time_ns: u64,
}

/// Minimal core engine that ACTUALLY works
pub struct MinimalCore {
    verifier: MinimalVerifier,
}

impl MinimalCore {
    pub fn new() -> Self {
        Self {
            verifier: MinimalVerifier::new(),
        }
    }
    
    /// Verify a credential and return timing
    pub fn verify(&self, credential: &MinimalCredential) -> std::result::Result<MinimalVerificationResult, MinimalError> {
        let start = std::time::Instant::now();
        
        let verified = self.verifier.verify(credential)?;
        
        let verification_time_ns = start.elapsed().as_nanos() as u64;
        
        Ok(MinimalVerificationResult {
            verified,
            issuer_did: credential.issuer.clone(),
            verification_time_ns,
        })
    }
    
    /// Verify from JSON string
    pub fn verify_credential_json(&self, credential_json: &str) -> std::result::Result<MinimalVerificationResult, MinimalError> {
        let credential: MinimalCredential = serde_json::from_str(credential_json)
            .map_err(|e| MinimalError::Serialization(e.to_string()))?;
        
        self.verify(&credential)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_minimal_crypto_system() {
        // Create issuer
        let issuer = MinimalIssuer::new();
        println!("Issuer DID: {}", issuer.did());
        
        // Create claims
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
        
        // Issue credential
        let credential = issuer.issue_credential(
            "did:lemma:subject123".to_string(),
            claims,
        ).unwrap();
        
        println!("Credential ID: {}", credential.id);
        println!("Has proof: {}", credential.proof.is_some());
        
        // Verify credential
        let core = MinimalCore::new();
        let result = core.verify(&credential).unwrap();
        
        println!("Verified: {}", result.verified);
        println!("Verification time: {} ns", result.verification_time_ns);
        
        assert!(result.verified);
    }
    
    #[test]
    fn test_invalid_signature_fails() {
        let issuer = MinimalIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("test".to_string(), serde_json::Value::String("value".to_string()));
        
        let mut credential = issuer.issue_credential(
            "did:lemma:subject".to_string(),
            claims,
        ).unwrap();
        
        // Corrupt the signature
        if let Some(ref mut proof) = credential.proof {
            proof.signature_value = "invalid_signature".to_string();
        }
        
        let core = MinimalCore::new();
        let result = core.verify(&credential).unwrap();
        
        assert!(!result.verified);
    }
}
