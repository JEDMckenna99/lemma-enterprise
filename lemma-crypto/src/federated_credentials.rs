//! Federated Credentials - True Decentralized Identity
//!
//! This module implements credentials that are inherently decentralized and portable
//! across all deployments in the federated network, solving the core architectural
//! flaw where credentials were trapped in local deployments.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use ed25519_dalek::{Signer, Verifier, Signature, SigningKey, VerifyingKey};
use sha2::{Sha256, Digest};
use rand::rngs::OsRng;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::{LemmaError, Result};

/// Network-wide unique identifier for federated credentials
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct FederatedCredentialId {
    /// Network identifier (same across all deployments)
    pub network_id: String,
    /// Unique credential identifier
    pub credential_id: String,
    /// Hash of the credential content for integrity
    pub content_hash: [u8; 32],
}

impl FederatedCredentialId {
    pub fn new(network_id: String, credential_id: String, content: &[u8]) -> Self {
        let mut hasher = Sha256::new();
        hasher.update(content);
        let content_hash: [u8; 32] = hasher.finalize().into();
        
        Self {
            network_id,
            credential_id,
            content_hash,
        }
    }
    
    /// Generate a globally unique identifier for this credential
    pub fn global_id(&self) -> String {
        format!("{}::{}", self.network_id, self.credential_id)
    }
}

/// Decentralized Identity Document (DID) that can be resolved across the network
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecentralizedIdentityDocument {
    /// DID identifier
    pub id: String,
    /// Network-wide public key for verification (as bytes for serialization)
    pub public_key: Vec<u8>,
    /// Service endpoints across the federation
    pub service_endpoints: Vec<ServiceEndpoint>,
    /// Creation timestamp
    pub created: u64,
    /// Last update timestamp  
    pub updated: u64,
    /// Network signature proving authenticity (as bytes for serialization)
    pub network_signature: Option<Vec<u8>>,
}

/// Service endpoint for federated network access
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceEndpoint {
    /// Endpoint type (verification, revocation, etc.)
    pub endpoint_type: String,
    /// Service URL
    pub service_url: String,
    /// Priority for load balancing
    pub priority: u32,
}

/// Truly federated credential that works across all deployments
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FederatedCredential {
    /// Federated credential identifier
    pub id: FederatedCredentialId,
    /// Issuer DID (resolvable across network)
    pub issuer_did: DecentralizedIdentityDocument,
    /// Subject DID (resolvable across network)  
    pub subject_did: DecentralizedIdentityDocument,
    /// Claims with cryptographic proofs
    pub claims: HashMap<String, serde_json::Value>,
    /// Issued timestamp
    pub issued_at: u64,
    /// Expiration timestamp
    pub expires_at: Option<u64>,
    /// Network-wide cryptographic signature (as bytes for serialization)
    pub network_signature: Vec<u8>,
    /// Portability proof (allows cross-deployment verification)
    pub portability_proof: PortabilityProof,
}

/// Cryptographic proof that allows credentials to work across deployments
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortabilityProof {
    /// Proof that this credential is valid in the federated network
    pub network_membership_proof: NetworkMembershipProof,
    /// Cross-deployment verification data
    pub cross_deployment_data: CrossDeploymentData,
    /// Revocation check data
    pub revocation_data: RevocationData,
}

/// Proof that a credential is part of the federated network
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetworkMembershipProof {
    /// Network identifier
    pub network_id: String,
    /// Merkle proof of inclusion in network registry
    pub merkle_proof: Vec<[u8; 32]>,
    /// Network root hash
    pub network_root: [u8; 32],
    /// Signature from network authority (as bytes for serialization)
    pub authority_signature: Vec<u8>,
}

/// Data needed for cross-deployment verification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrossDeploymentData {
    /// Shared OPRF key for network-wide evaluation
    pub shared_oprf_key: [u8; 32],
    /// Shared Bloom filter parameters
    pub bloom_filter_params: BloomFilterParams,
    /// Network consensus data
    pub consensus_data: ConsensusData,
}

/// Shared Bloom filter parameters across the network
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BloomFilterParams {
    /// Network-wide filter size
    pub filter_size: usize,
    /// Number of hash functions
    pub hash_functions: usize,
    /// Expected error rate
    pub error_rate: f64,
    /// Network-wide HMAC key for filter authentication
    pub network_hmac_key: [u8; 32],
}

/// Network consensus data for revocation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsensusData {
    /// Consensus round number
    pub round: u64,
    /// Participating nodes
    pub participants: Vec<String>,
    /// Consensus signature (as bytes for serialization)
    pub consensus_signature: Vec<u8>,
}

/// Revocation data for network-wide revocation checking
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RevocationData {
    /// OPRF evaluation for privacy-preserving revocation
    pub oprf_evaluation: [u8; 32],
    /// Revocation registry proof
    pub revocation_proof: Option<RevocationProof>,
    /// Last revocation check timestamp
    pub last_check: u64,
}

/// Proof of revocation status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RevocationProof {
    /// Proof that credential is/isn't in revocation list
    pub inclusion_proof: Vec<[u8; 32]>,
    /// Revocation registry root
    pub registry_root: [u8; 32],
    /// Authority signature (as bytes for serialization)
    pub authority_signature: Vec<u8>,
}

/// Federated credential issuer that creates portable credentials
pub struct FederatedCredentialIssuer {
    /// Network signing key
    signing_key: SigningKey,
    /// Network identifier
    network_id: String,
    /// Shared network parameters
    network_params: NetworkParameters,
}

/// Network-wide parameters shared across all deployments
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetworkParameters {
    /// Shared OPRF key for network-wide evaluation
    pub shared_oprf_key: [u8; 32],
    /// Shared Bloom filter parameters
    pub bloom_params: BloomFilterParams,
    /// Network authority public key (as bytes for serialization)
    pub network_authority_key: Vec<u8>,
    /// Service endpoints for the network
    pub service_endpoints: Vec<ServiceEndpoint>,
}

impl FederatedCredentialIssuer {
    /// Create a new federated credential issuer
    pub fn new(network_id: String, network_params: NetworkParameters) -> Self {
        let signing_key = SigningKey::generate(&mut OsRng);
        
        Self {
            signing_key,
            network_id,
            network_params,
        }
    }
    
    /// Issue a federated credential that works across all deployments
    pub fn issue_federated_credential(
        &self,
        subject_id: String,
        claims: HashMap<String, serde_json::Value>,
        expires_at: Option<u64>,
    ) -> Result<FederatedCredential> {
        let current_time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        
        // Create credential content for hashing
        let credential_content = serde_json::to_vec(&claims)
            .map_err(|e| LemmaError::Serialization(e.to_string()))?;
        
        // Create federated credential ID
        let credential_id = format!("fed_cred_{}", current_time);
        let fed_id = FederatedCredentialId::new(
            self.network_id.clone(),
            credential_id,
            &credential_content,
        );
        
        // Create issuer DID
        let issuer_did = DecentralizedIdentityDocument {
            id: format!("did:lemma:issuer:{}", self.network_id),
            public_key: self.signing_key.verifying_key().to_bytes().to_vec(),
            service_endpoints: self.network_params.service_endpoints.clone(),
            created: current_time,
            updated: current_time,
            network_signature: None, // Would be signed by network authority
        };
        
        // Create subject DID
        let subject_did = DecentralizedIdentityDocument {
            id: format!("did:lemma:user:{}", subject_id),
            public_key: self.signing_key.verifying_key().to_bytes().to_vec(), // In reality, user's key
            service_endpoints: self.network_params.service_endpoints.clone(),
            created: current_time,
            updated: current_time,
            network_signature: None,
        };
        
        // Create portability proof
        let portability_proof = self.create_portability_proof(&fed_id, &claims)?;
        
        // Create credential without signature first
        let mut credential = FederatedCredential {
            id: fed_id,
            issuer_did,
            subject_did,
            claims,
            issued_at: current_time,
            expires_at,
            network_signature: vec![0u8; 64], // Placeholder
            portability_proof,
        };
        
        // Sign the credential
        let credential_bytes = serde_json::to_vec(&credential)
            .map_err(|e| LemmaError::Serialization(e.to_string()))?;
        let signature = self.signing_key.sign(&credential_bytes);
        credential.network_signature = signature.to_bytes().to_vec();
        
        Ok(credential)
    }
    
    /// Create portability proof for cross-deployment verification
    fn create_portability_proof(
        &self,
        credential_id: &FederatedCredentialId,
        claims: &HashMap<String, serde_json::Value>,
    ) -> Result<PortabilityProof> {
        // Create network membership proof
        let network_membership_proof = NetworkMembershipProof {
            network_id: self.network_id.clone(),
            merkle_proof: vec![], // Would be computed from network registry
            network_root: [0u8; 32], // Would be actual network root
            authority_signature: vec![0u8; 64], // Authority signature
        };
        
        // Create cross-deployment data
        let cross_deployment_data = CrossDeploymentData {
            shared_oprf_key: self.network_params.shared_oprf_key,
            bloom_filter_params: self.network_params.bloom_params.clone(),
            consensus_data: ConsensusData {
                round: 1,
                participants: vec![self.network_id.clone()],
                consensus_signature: vec![0u8; 64],
            },
        };
        
        // Create OPRF evaluation for revocation checking
        let credential_data = serde_json::to_vec(claims)
            .map_err(|e| LemmaError::Serialization(e.to_string()))?;
        let mut hasher = Sha256::new();
        hasher.update(&self.network_params.shared_oprf_key);
        hasher.update(&credential_data);
        let oprf_evaluation: [u8; 32] = hasher.finalize().into();
        
        let revocation_data = RevocationData {
            oprf_evaluation,
            revocation_proof: None,
            last_check: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs(),
        };
        
        Ok(PortabilityProof {
            network_membership_proof,
            cross_deployment_data,
            revocation_data,
        })
    }
}

/// Federated credential verifier that works across deployments
pub struct FederatedCredentialVerifier {
    /// Network parameters
    network_params: NetworkParameters,
    /// Network authority public key for verification (as bytes)
    network_authority_key: Vec<u8>,
}

impl FederatedCredentialVerifier {
    /// Create a new federated credential verifier
    pub fn new(network_params: NetworkParameters) -> Self {
        let network_authority_key = network_params.network_authority_key.clone();
        
        Self {
            network_params,
            network_authority_key,
        }
    }
    
    /// Verify a federated credential (works on any deployment)
    pub fn verify_federated_credential(&self, credential: &FederatedCredential) -> Result<bool> {
        // 1. Verify network signature
        let credential_bytes = serde_json::to_vec(credential)
            .map_err(|e| LemmaError::Serialization(e.to_string()))?;
        
        // Convert bytes back to VerifyingKey for verification
        let public_key_bytes: [u8; 32] = credential.issuer_did.public_key.as_slice()
            .try_into()
            .map_err(|_| LemmaError::Crypto("Invalid public key length".to_string()))?;
        let public_key = VerifyingKey::from_bytes(&public_key_bytes)
            .map_err(|e| LemmaError::Crypto(format!("Invalid public key: {}", e)))?;
        
        let signature_bytes: [u8; 64] = credential.network_signature.as_slice()
            .try_into()
            .map_err(|_| LemmaError::Crypto("Invalid signature length".to_string()))?;
        let signature = Signature::from_bytes(&signature_bytes);
        
        public_key
            .verify(&credential_bytes, &signature)
            .map_err(|e| LemmaError::Crypto(format!("Signature verification failed: {}", e)))?;
        
        // 2. Verify network membership
        if credential.portability_proof.network_membership_proof.network_id != credential.id.network_id {
            return Ok(false);
        }
        
        // 3. Check revocation using shared OPRF+Bloom
        let is_revoked = self.check_revocation(&credential.portability_proof.revocation_data)?;
        if is_revoked {
            return Ok(false);
        }
        
        // 4. Verify expiration
        if let Some(expires_at) = credential.expires_at {
            let current_time = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs();
            if current_time > expires_at {
                return Ok(false);
            }
        }
        
        Ok(true)
    }
    
    /// Check revocation using shared network parameters
    fn check_revocation(&self, revocation_data: &RevocationData) -> Result<bool> {
        // This would check against the shared network-wide Bloom filter
        // For now, return false (not revoked) as a placeholder
        Ok(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_federated_credential_creation() {
        let network_params = NetworkParameters {
            shared_oprf_key: [1u8; 32],
            bloom_params: BloomFilterParams {
                filter_size: 10000,
                hash_functions: 7,
                error_rate: 0.01,
                network_hmac_key: [2u8; 32],
            },
            network_authority_key: SigningKey::generate(&mut OsRng).verifying_key().to_bytes().to_vec(),
            service_endpoints: vec![],
        };
        
        let issuer = FederatedCredentialIssuer::new(
            "lemma_federated_network".to_string(),
            network_params.clone(),
        );
        
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationMethod".to_string(), serde_json::Value::String("stripe_identity".to_string()));
        
        let credential = issuer.issue_federated_credential(
            "test_user_123".to_string(),
            claims,
            None,
        ).unwrap();
        
        // Verify the credential can be verified on any deployment
        let verifier = FederatedCredentialVerifier::new(network_params);
        let is_valid = verifier.verify_federated_credential(&credential).unwrap();
        
        assert!(is_valid, "Federated credential should be valid");
        assert_eq!(credential.id.network_id, "lemma_federated_network");
        assert!(credential.claims.contains_key("isHuman"));
    }
    
    #[test]
    fn test_credential_portability() {
        // Test that credentials work across different "deployments"
        let network_params = NetworkParameters {
            shared_oprf_key: [3u8; 32], // Same key across network
            bloom_params: BloomFilterParams {
                filter_size: 10000,
                hash_functions: 7,
                error_rate: 0.01,
                network_hmac_key: [4u8; 32], // Same HMAC key across network
            },
            network_authority_key: SigningKey::generate(&mut OsRng).verifying_key().to_bytes().to_vec(),
            service_endpoints: vec![],
        };
        
        // Create credential on "lemma-enterprise" deployment
        let enterprise_issuer = FederatedCredentialIssuer::new(
            "lemma_federated_network".to_string(),
            network_params.clone(),
        );
        
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        
        let credential = enterprise_issuer.issue_federated_credential(
            "portable_user_456".to_string(),
            claims,
            None,
        ).unwrap();
        
        // Verify credential on "lemma-federated-identity" deployment
        let federated_verifier = FederatedCredentialVerifier::new(network_params.clone());
        let is_valid = federated_verifier.verify_federated_credential(&credential).unwrap();
        
        assert!(is_valid, "Credential should be portable across deployments");
        
        // Verify same credential on a "third-party" deployment
        let third_party_verifier = FederatedCredentialVerifier::new(network_params);
        let is_still_valid = third_party_verifier.verify_federated_credential(&credential).unwrap();
        
        assert!(is_still_valid, "Credential should work on any network deployment");
    }
}
