//! Credential operations for DID/VC handling

use ed25519_dalek::{Signer, Verifier, SigningKey, VerifyingKey, Signature};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use sha2::{Sha256, Digest};
use rand::rngs::OsRng;

use crate::constants::*;
use crate::utils::{bytes_to_hex, hex_to_bytes, current_timestamp};
use crate::Result;

/// Errors related to credential operations
#[derive(Debug, thiserror::Error)]
pub enum CredentialError {
    #[error("Invalid credential format")]
    InvalidFormat,
    #[error("Invalid signature")]
    InvalidSignature,
    #[error("Invalid DID format")]
    InvalidDID,
    #[error("Credential expired")]
    Expired,
    #[error("Invalid key format")]
    InvalidKey,
    #[error("Serialization error: {0}")]
    Serialization(String),
    #[error("Verification failed: {0}")]
    VerificationFailed(String),
    #[error("Ed25519 error: {0}")]
    Ed25519(#[from] ed25519_dalek::SignatureError),
}

/// Ed25519 signature wrapper
#[derive(Debug, Clone)]
pub struct Ed25519Signature {
    pub inner: Signature,
}

impl Ed25519Signature {
    pub fn from_bytes(bytes: [u8; SIGNATURE_SIZE]) -> Result<Self> {
        let signature = Signature::from_bytes(&bytes);
        Ok(Self { inner: signature })
    }
    
    pub fn to_bytes(&self) -> [u8; SIGNATURE_SIZE] {
        self.inner.to_bytes()
    }
    
    pub fn to_hex(&self) -> String {
        bytes_to_hex(&self.to_bytes())
    }
    
    pub fn from_hex(hex: &str) -> Result<Self> {
        let bytes = hex_to_bytes(hex)
            .map_err(|_| CredentialError::InvalidSignature)?;
        if bytes.len() != SIGNATURE_SIZE {
            return Err(CredentialError::InvalidSignature.into());
        }
        let mut signature_bytes = [0u8; SIGNATURE_SIZE];
        signature_bytes.copy_from_slice(&bytes);
        Self::from_bytes(signature_bytes)
    }
}

/// Ed25519 public key wrapper
#[derive(Debug, Clone)]
pub struct Ed25519PublicKey {
    pub inner: VerifyingKey,
}

impl Ed25519PublicKey {
    pub fn from_bytes(bytes: [u8; PUBLIC_KEY_SIZE]) -> Result<Self> {
        let key = VerifyingKey::from_bytes(&bytes)
            .map_err(|e| CredentialError::InvalidKey)?;
        Ok(Self { inner: key })
    }
    
    pub fn to_bytes(&self) -> [u8; PUBLIC_KEY_SIZE] {
        self.inner.to_bytes()
    }
    
    pub fn to_hex(&self) -> String {
        bytes_to_hex(&self.to_bytes())
    }
    
    pub fn from_hex(hex: &str) -> Result<Self> {
        let bytes = hex_to_bytes(hex)
            .map_err(|_| CredentialError::InvalidKey)?;
        if bytes.len() != PUBLIC_KEY_SIZE {
            return Err(CredentialError::InvalidKey.into());
        }
        let mut key_bytes = [0u8; PUBLIC_KEY_SIZE];
        key_bytes.copy_from_slice(&bytes);
        Self::from_bytes(key_bytes)
    }
}

/// Ed25519 private key wrapper
#[derive(Debug, Clone)]
pub struct Ed25519PrivateKey {
    pub inner: SigningKey,
}

impl Ed25519PrivateKey {
    pub fn from_bytes(bytes: [u8; PRIVATE_KEY_SIZE]) -> Self {
        let key = SigningKey::from_bytes(&bytes);
        Self { inner: key }
    }
    
    pub fn to_bytes(&self) -> [u8; PRIVATE_KEY_SIZE] {
        self.inner.to_bytes()
    }
    
    pub fn to_hex(&self) -> String {
        bytes_to_hex(&self.to_bytes())
    }
    
    pub fn from_hex(hex: &str) -> Result<Self> {
        let bytes = hex_to_bytes(hex)
            .map_err(|_| CredentialError::InvalidKey)?;
        if bytes.len() != PRIVATE_KEY_SIZE {
            return Err(CredentialError::InvalidKey.into());
        }
        let mut key_bytes = [0u8; PRIVATE_KEY_SIZE];
        key_bytes.copy_from_slice(&bytes);
        Ok(Self::from_bytes(key_bytes))
    }
    
    pub fn verifying_key(&self) -> Ed25519PublicKey {
        Ed25519PublicKey { inner: self.inner.verifying_key() }
    }
}

/// Generate a new Ed25519 keypair
pub fn generate_keypair() -> (Ed25519PrivateKey, Ed25519PublicKey) {
    let mut csprng = OsRng;
    let signing_key = SigningKey::generate(&mut csprng);
    let verifying_key = signing_key.verifying_key();
    
    let private_key = Ed25519PrivateKey { inner: signing_key };
    let public_key = Ed25519PublicKey { inner: verifying_key };
    
    (private_key, public_key)
}

/// Generate a DID from a public key
pub fn generate_did(public_key: &Ed25519PublicKey) -> String {
    let identifier = public_key.to_hex();
    format!("did:{}:{}", DID_METHOD, identifier)
}

/// Create Ed25519 signature
pub fn sign(private_key: &Ed25519PrivateKey, message: &[u8]) -> Ed25519Signature {
    let signature = private_key.inner.sign(message);
    Ed25519Signature { inner: signature }
}

/// Verify Ed25519 signature
pub fn verify(public_key: &Ed25519PublicKey, message: &[u8], signature: &Ed25519Signature) -> bool {
    public_key.inner.verify(message, &signature.inner).is_ok()
}

/// Cryptographic proof for verifiable credentials
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CryptographicProof {
    pub proof_type: String,
    pub created: u64,
    pub verification_method: String,
    pub signature_value: String,
}

/// Verifiable Credential following W3C VC Data Model
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerifiableCredential {
    pub id: String,
    pub issuer: String,
    pub subject: String,
    pub issued_at: u64,
    pub expires_at: Option<u64>,
    pub claims: HashMap<String, serde_json::Value>,
    pub proof: Option<CryptographicProof>,
}

impl VerifiableCredential {
    /// Create a new verifiable credential
    pub fn new(
        issuer: String,
        subject: String,
        claims: HashMap<String, serde_json::Value>,
        expires_at: Option<u64>,
    ) -> Self {
        let id = format!("urn:uuid:{}", uuid::Uuid::new_v4());
        let issued_at = current_timestamp();
        
        Self {
            id,
            issuer,
            subject,
            issued_at,
            expires_at,
            claims,
            proof: None,
        }
    }
    
    /// Add a cryptographic proof to the credential
    pub fn add_proof(&mut self, proof: CryptographicProof) {
        self.proof = Some(proof);
    }
    
    /// Get a claim value
    pub fn get_claim(&self, key: &str) -> Option<&serde_json::Value> {
        self.claims.get(key)
    }
    
    /// Check if the credential is expired
    pub fn is_expired(&self) -> bool {
        if let Some(expires_at) = self.expires_at {
            current_timestamp() > expires_at
        } else {
            false
        }
    }
    
    /// Check if this is a human verification credential
    pub fn is_human_verification(&self) -> bool {
        self.get_claim("isHuman")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
    }
    
    /// Verify the credential signature
    pub fn verify_signature(&self) -> Result<bool> {
        let proof = self.proof.as_ref()
            .ok_or(CredentialError::InvalidSignature)?;
        
        // Extract the public key from the issuer DID
        let public_key = self.extract_public_key_from_did()?;
        
        // Create the message to verify
        let message = self.create_verification_message()?;
        
        // Verify the signature
        let signature = Ed25519Signature::from_hex(&proof.signature_value)?;
        Ok(verify(&public_key, &message, &signature))
    }
    
    /// Verify the credential signature with a pre-cached public key (for multi-level caching)
    pub fn verify_signature_with_key(&self, public_key: &Ed25519PublicKey) -> Result<bool> {
        let proof = self.proof.as_ref()
            .ok_or(CredentialError::InvalidSignature)?;
        
        // Create the message to verify
        let message = self.create_verification_message()?;
        
        // Verify the signature using the provided key
        let signature = Ed25519Signature::from_hex(&proof.signature_value)?;
        Ok(verify(public_key, &message, &signature))
    }
    
    /// Extract public key from DID
    pub fn extract_public_key_from_did(&self) -> Result<Ed25519PublicKey> {
        let did_parts: Vec<&str> = self.issuer.split(':').collect();
        if did_parts.len() != 3 || did_parts[1] != DID_METHOD {
            return Err(CredentialError::InvalidDID.into());
        }
        
        let identifier = did_parts[2];
        Ed25519PublicKey::from_hex(identifier)
    }
    
    /// Create verification message for signing
    pub fn create_verification_message(&self) -> Result<Vec<u8>> {
        let mut message = Vec::new();
        message.extend_from_slice(CREDENTIAL_CONTEXT);
        message.extend_from_slice(self.id.as_bytes());
        message.extend_from_slice(self.issuer.as_bytes());
        message.extend_from_slice(self.subject.as_bytes());
        message.extend_from_slice(&self.issued_at.to_le_bytes());
        
        if let Some(expires_at) = self.expires_at {
            message.extend_from_slice(&expires_at.to_le_bytes());
        }
        
        // Add claims to message (sorted for consistency)
        let mut sorted_claims: Vec<_> = self.claims.iter().collect();
        sorted_claims.sort_by_key(|(k, _)| *k);
        
        for (key, value) in sorted_claims {
            message.extend_from_slice(key.as_bytes());
            let value_json = serde_json::to_string(value)
                .map_err(|e| CredentialError::Serialization(e.to_string()))?;
            message.extend_from_slice(value_json.as_bytes());
        }
        
        Ok(message)
    }
    
    /// Convert to JSON string
    pub fn to_json(&self) -> Result<String> {
        serde_json::to_string(self)
            .map_err(|e| CredentialError::Serialization(e.to_string()).into())
    }
    
    /// Create from JSON string
    pub fn from_json(json: &str) -> Result<Self> {
        serde_json::from_str(json)
            .map_err(|e| CredentialError::Serialization(e.to_string()).into())
    }

    /// Get signature data for HSM operations
    pub fn signature_data(&self) -> Vec<u8> {
        self.proof.as_ref()
            .and_then(|p| hex::decode(&p.signature_value).ok())
            .unwrap_or_default()
    }

    /// Get message bytes for HSM operations
    pub fn message_bytes(&self) -> Vec<u8> {
        self.create_verification_message()
            .unwrap_or_default()
    }
}

/// Credential issuer for creating and signing credentials
pub struct CredentialIssuer {
    private_key: Ed25519PrivateKey,
    public_key: Ed25519PublicKey,
    did: String,
}

impl CredentialIssuer {
    /// Create a new credential issuer
    pub fn new() -> Self {
        let (private_key, public_key) = generate_keypair();
        let did = generate_did(&public_key);
        
        Self {
            private_key,
            public_key,
            did,
        }
    }
    
    /// Create a new issuer with existing keys
    pub fn from_keys(private_key: Ed25519PrivateKey, public_key: Ed25519PublicKey) -> Self {
        let did = generate_did(&public_key);
        
        Self {
            private_key,
            public_key,
            did,
        }
    }
    
    /// Create issuer from hex-encoded private key
    pub fn from_private_key_hex(hex: &str) -> Result<Self> {
        let private_key = Ed25519PrivateKey::from_hex(hex)?;
        let public_key = private_key.verifying_key();
        let did = generate_did(&public_key);
        
        Ok(Self {
            private_key,
            public_key,
            did,
        })
    }
    
    /// Get the issuer's DID
    pub fn get_did(&self) -> String {
        self.did.clone()
    }
    
    /// Get the issuer's public key
    pub fn get_public_key(&self) -> &Ed25519PublicKey {
        &self.public_key
    }
    
    /// Get the issuer's private key hex
    pub fn get_private_key_hex(&self) -> String {
        self.private_key.to_hex()
    }
    
    /// Issue a new verifiable credential
    pub fn issue_credential(
        &self,
        subject: String,
        claims: HashMap<String, serde_json::Value>,
        expires_at: Option<u64>,
    ) -> Result<VerifiableCredential> {
        let mut credential = VerifiableCredential::new(
            self.did.clone(),
            subject,
            claims,
            expires_at,
        );
        
        // Create proof
        let message = credential.create_verification_message()?;
        let signature = sign(&self.private_key, &message);
        
        let proof = CryptographicProof {
            proof_type: "Ed25519Signature2020".to_string(),
            created: current_timestamp(),
            verification_method: self.did.clone(),
            signature_value: signature.to_hex(),
        };
        
        credential.add_proof(proof);
        Ok(credential)
    }

    /// Verify a credential using this issuer's public key
    pub fn verify_credential(&self, credential: &VerifiableCredential) -> Result<bool> {
        // Check if credential is issued by this issuer
        if credential.issuer != self.did {
            return Ok(false);
        }
        
        // Verify the signature
        credential.verify_signature()
    }
}

impl Default for CredentialIssuer {
    fn default() -> Self {
        Self::new()
    }
}

/// Credential verifier for checking credential signatures
pub struct CredentialVerifier {
    public_key: Ed25519PublicKey,
}

impl CredentialVerifier {
    /// Create a new verifier with a public key
    pub fn new(public_key: Ed25519PublicKey) -> Self {
        Self { public_key }
    }
    
    /// Create verifier from hex-encoded public key
    pub fn from_public_key_hex(hex: &str) -> Result<Self> {
        let public_key = Ed25519PublicKey::from_hex(hex)?;
        Ok(Self { public_key })
    }
    
    /// Verify a credential
    pub fn verify_credential(&self, credential: &VerifiableCredential) -> Result<bool> {
        // Check if credential is expired
        if credential.is_expired() {
            return Ok(false);
        }
        
        // Verify signature
        credential.verify_signature()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    
    #[test]
    fn test_keypair_generation() {
        let (private_key, public_key) = generate_keypair();
        
        // Test that we can derive public key from private key
        let derived_public = private_key.verifying_key();
        assert_eq!(public_key.to_bytes(), derived_public.to_bytes());
    }
    
    #[test]
    fn test_signature_verification() {
        let (private_key, public_key) = generate_keypair();
        let message = b"Hello, World!";
        
        let signature = sign(&private_key, message);
        assert!(verify(&public_key, message, &signature));
        
        // Test with wrong message
        let wrong_message = b"Wrong message";
        assert!(!verify(&public_key, wrong_message, &signature));
    }
    
    #[test]
    fn test_credential_issuance_and_verification() {
        let issuer = CredentialIssuer::new();
        
        let mut claims = HashMap::new();
        claims.insert("isHuman".to_string(), json!(true));
        claims.insert("verificationLevel".to_string(), json!("high"));
        
        let credential = issuer.issue_credential(
            "did:lemma:user123".to_string(),
            claims,
            None,
        ).unwrap();
        
        assert!(credential.verify_signature().unwrap());
        assert!(credential.is_human_verification());
    }
    
    #[test]
    fn test_credential_serialization() {
        let issuer = CredentialIssuer::new();
        
        let mut claims = HashMap::new();
        claims.insert("test".to_string(), json!("value"));
        
        let credential = issuer.issue_credential(
            "did:lemma:user123".to_string(),
            claims,
            None,
        ).unwrap();
        
        let json_str = credential.to_json().unwrap();
        let deserialized = VerifiableCredential::from_json(&json_str).unwrap();
        
        assert_eq!(credential.id, deserialized.id);
        assert_eq!(credential.issuer, deserialized.issuer);
        assert_eq!(credential.subject, deserialized.subject);
    }
    
    #[test]
    fn test_credential_expiration() {
        let issuer = CredentialIssuer::new();
        
        let mut claims = HashMap::new();
        claims.insert("test".to_string(), json!("value"));
        
        // Create expired credential
        let expired_credential = issuer.issue_credential(
            "did:lemma:user123".to_string(),
            claims.clone(),
            Some(current_timestamp() - 1000), // Expired 1000 seconds ago
        ).unwrap();
        
        assert!(expired_credential.is_expired());
        
        // Create valid credential
        let valid_credential = issuer.issue_credential(
            "did:lemma:user123".to_string(),
            claims,
            Some(current_timestamp() + 1000), // Expires in 1000 seconds
        ).unwrap();
        
        assert!(!valid_credential.is_expired());
    }
}

// Add uuid dependency for credential IDs
mod uuid {
    use rand::Rng;
    
    pub struct Uuid {
        bytes: [u8; 16],
    }
    
    impl Uuid {
        pub fn new_v4() -> Self {
            let mut rng = rand::thread_rng();
            let mut bytes = [0u8; 16];
            rng.fill(&mut bytes);
            
            // Set version (4) and variant bits
            bytes[6] = (bytes[6] & 0x0f) | 0x40;
            bytes[8] = (bytes[8] & 0x3f) | 0x80;
            
            Self { bytes }
        }
    }
    
    impl std::fmt::Display for Uuid {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            write!(f, "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
                self.bytes[0], self.bytes[1], self.bytes[2], self.bytes[3],
                self.bytes[4], self.bytes[5],
                self.bytes[6], self.bytes[7],
                self.bytes[8], self.bytes[9],
                self.bytes[10], self.bytes[11], self.bytes[12], self.bytes[13], self.bytes[14], self.bytes[15]
            )
        }
    }
} 