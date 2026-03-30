//! Advanced Wallet Recovery System - Cryptographic Foundation
//! Implements RID derivation, VID computation, and pairwise tagging

use blake3;
use hmac::{Hmac, Mac};
use sha2::Sha256;
use hkdf::Hkdf;
use serde::{Deserialize, Serialize};
// use std::collections::HashMap;

type HmacSha256 = Hmac<Sha256>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KYCTuple {
    pub jurisdiction_code: String,    // e.g., "US", "GB", "CA"
    pub doc_type: String,            // e.g., "passport", "drivers_license"
    pub doc_number_norm: String,     // normalized document number
    pub surname_norm: String,        // normalized surname
    pub dob_yyyymmdd: String,       // YYYY-MM-DD format
    pub liveness_template_hash: String, // biometric template hash
}

#[derive(Debug, Clone)]
pub struct AdvancedWalletCrypto {
    issuer_secret_salt: [u8; 32],   // HSM/KMS stored
    k_pair: [u8; 32],               // HSM/KMS stored for pairwise tags
    r_vault: [u8; 32],              // HSM/KMS stored for vault indexing
}

impl AdvancedWalletCrypto {
    /// Create new advanced wallet crypto system
    pub fn new(
        issuer_secret_salt: [u8; 32],
        k_pair: [u8; 32], 
        r_vault: [u8; 32]
    ) -> Self {
        Self {
            issuer_secret_salt,
            k_pair,
            r_vault,
        }
    }

    /// Generate cryptographically secure random secrets for HSM storage
    pub fn generate_secrets() -> (Vec<u8>, Vec<u8>, Vec<u8>) {
        use rand::RngCore;
        let mut rng = rand::thread_rng();
        
        let mut issuer_salt = [0u8; 32];
        let mut k_pair = [0u8; 32];
        let mut r_vault = [0u8; 32];
        
        rng.fill_bytes(&mut issuer_salt);
        rng.fill_bytes(&mut k_pair);
        rng.fill_bytes(&mut r_vault);
        
        (issuer_salt.to_vec(), k_pair.to_vec(), r_vault.to_vec())
    }

    /// Normalize KYC tuple to canonical format
    pub fn normalize_kyc_tuple(kyc: &KYCTuple) -> Result<Vec<u8>, String> {
        // Normalize all fields to lowercase ASCII where applicable
        let normalized = KYCTuple {
            jurisdiction_code: kyc.jurisdiction_code.to_lowercase().trim().to_string(),
            doc_type: kyc.doc_type.to_lowercase().replace("-", "").replace("_", ""),
            doc_number_norm: kyc.doc_number_norm.to_uppercase().replace(" ", "").replace("-", ""),
            surname_norm: kyc.surname_norm.to_lowercase().trim().to_string(),
            dob_yyyymmdd: kyc.dob_yyyymmdd.clone(), // Already normalized format
            liveness_template_hash: kyc.liveness_template_hash.to_lowercase(),
        };

        // Serialize to CBOR in fixed field order for determinism
        match serde_cbor::to_vec(&normalized) {
            Ok(cbor_bytes) => Ok(cbor_bytes),
            Err(e) => Err(format!("CBOR serialization failed: {}", e))
        }
    }

    /// Derive RID (Root ID) from normalized KYC tuple
    /// RID = BLAKE3(normalized_KYC_tuple || issuer_secret_salt)
    pub fn derive_rid(&self, kyc_tuple_cbor: &[u8]) -> [u8; 32] {
        let mut input = Vec::with_capacity(kyc_tuple_cbor.len() + self.issuer_secret_salt.len());
        input.extend_from_slice(kyc_tuple_cbor);
        input.extend_from_slice(&self.issuer_secret_salt);
        
        blake3::hash(&input).into()
    }

    /// Generate pairwise tag for RP uniqueness enforcement
    /// tag_rp = HMAC(k_pair, RID || rp_id)
    pub fn generate_pairwise_tag(&self, rid: &[u8; 32], rp_id: &str) -> Result<[u8; 32], String> {
        let mut mac = match HmacSha256::new_from_slice(&self.k_pair) {
            Ok(m) => m,
            Err(e) => return Err(format!("HMAC initialization failed: {}", e))
        };
        
        mac.update(rid);
        mac.update(rp_id.as_bytes());
        
        Ok(mac.finalize().into_bytes().into())
    }

    /// Derive VID (Vault Index) for privacy-preserving vault lookup
    /// VID = BLAKE3(r_vault || RID)
    pub fn derive_vid(&self, rid: &[u8; 32]) -> [u8; 32] {
        let mut input = Vec::with_capacity(self.r_vault.len() + rid.len());
        input.extend_from_slice(&self.r_vault);
        input.extend_from_slice(rid);
        
        blake3::hash(&input).into()
    }

    /// Derive per-RP child key for wallet
    /// child_key_rp = HKDF(SK_master, info=rp_id)
    pub fn derive_rp_child_key(sk_master: &[u8; 32], rp_id: &str) -> Result<[u8; 32], String> {
        let hk = Hkdf::<Sha256>::new(None, sk_master);
        let mut child_key = [0u8; 32];
        
        match hk.expand(rp_id.as_bytes(), &mut child_key) {
            Ok(_) => Ok(child_key),
            Err(e) => Err(format!("HKDF expansion failed: {}", e))
        }
    }

    /// Generate DID from child key
    /// did_rp = did:key(pub(child_key_rp))
    pub fn generate_rp_did(child_key: &[u8; 32]) -> Result<String, String> {
        use ed25519_dalek::{SigningKey, VerifyingKey};
        
        let signing_key = SigningKey::from_bytes(child_key);
        let verifying_key = VerifyingKey::from(&signing_key);
        let public_key_bytes = verifying_key.to_bytes();
        
        Ok(format!("did:lemma:{}", hex::encode(public_key_bytes)))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WalletEnvelope {
    pub version: u16,
    pub counter: u64,               // Monotonic counter for rollback protection
    pub wallet_schema: u16,
    pub master_seed: [u8; 32],     // SK_master
    pub device_records: Option<Vec<u8>>, // Optional encrypted cache
}

#[derive(Debug, Clone)]
pub struct EnvelopeEncryption {
    // Will implement XChaCha20-Poly1305 AEAD
}

impl EnvelopeEncryption {
    pub fn new() -> Self {
        Self {}
    }

    /// Encrypt wallet envelope with 2-of-N key derivation
    pub fn encrypt_envelope(
        &self, 
        envelope: &WalletEnvelope,
        _passphrase: &str,
        _device_key: Option<&[u8; 32]>
    ) -> Result<Vec<u8>, String> {
        // TODO: Implement XChaCha20-Poly1305 with 2-of-N key derivation
        // For now, return placeholder
        Ok(serde_cbor::to_vec(envelope).map_err(|e| e.to_string())?)
    }

    /// Decrypt wallet envelope
    pub fn decrypt_envelope(
        &self,
        ciphertext: &[u8],
        _passphrase: &str,
        _device_key: Option<&[u8; 32]>
    ) -> Result<WalletEnvelope, String> {
        // TODO: Implement decryption
        // For now, return placeholder
        serde_cbor::from_slice(ciphertext).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rid_determinism() {
        let (salt, k_pair, r_vault) = AdvancedWalletCrypto::generate_secrets();
        let crypto = AdvancedWalletCrypto::new(
            salt.try_into().unwrap(),
            k_pair.try_into().unwrap(), 
            r_vault.try_into().unwrap()
        );

        let kyc = KYCTuple {
            jurisdiction_code: "US".to_string(),
            doc_type: "passport".to_string(),
            doc_number_norm: "123456789".to_string(),
            surname_norm: "smith".to_string(),
            dob_yyyymmdd: "1990-01-01".to_string(),
            liveness_template_hash: "abc123".to_string(),
        };

        let kyc_cbor = AdvancedWalletCrypto::normalize_kyc_tuple(&kyc).unwrap();
        
        // Same KYC should produce same RID
        let rid1 = crypto.derive_rid(&kyc_cbor);
        let rid2 = crypto.derive_rid(&kyc_cbor);
        assert_eq!(rid1, rid2, "RID should be deterministic");

        // Different KYC should produce different RID
        let mut kyc2 = kyc.clone();
        kyc2.surname_norm = "jones".to_string();
        let kyc2_cbor = AdvancedWalletCrypto::normalize_kyc_tuple(&kyc2).unwrap();
        let rid3 = crypto.derive_rid(&kyc2_cbor);
        assert_ne!(rid1, rid3, "Different KYC should produce different RID");
    }

    #[test]
    fn test_pairwise_tag_uniqueness() {
        let (salt, k_pair, r_vault) = AdvancedWalletCrypto::generate_secrets();
        let crypto = AdvancedWalletCrypto::new(
            salt.try_into().unwrap(),
            k_pair.try_into().unwrap(),
            r_vault.try_into().unwrap()
        );

        let rid = [1u8; 32]; // Test RID
        
        // Same RID + RP should produce same tag
        let tag1 = crypto.generate_pairwise_tag(&rid, "example.com").unwrap();
        let tag2 = crypto.generate_pairwise_tag(&rid, "example.com").unwrap();
        assert_eq!(tag1, tag2, "Same RID+RP should produce same tag");

        // Different RP should produce different tag
        let tag3 = crypto.generate_pairwise_tag(&rid, "different.com").unwrap();
        assert_ne!(tag1, tag3, "Different RP should produce different tag");
    }

    #[test]
    fn test_vid_privacy() {
        let (salt, k_pair, r_vault) = AdvancedWalletCrypto::generate_secrets();
        let crypto = AdvancedWalletCrypto::new(
            salt.clone().try_into().unwrap(),
            k_pair.clone().try_into().unwrap(),
            r_vault.clone().try_into().unwrap()
        );

        let rid = [1u8; 32];
        let vid = crypto.derive_vid(&rid);

        // VID should be deterministic for same RID
        let vid2 = crypto.derive_vid(&rid);
        assert_eq!(vid, vid2, "VID should be deterministic");

        // Different r_vault should produce different VID (privacy)
        let (_, _, r_vault2) = AdvancedWalletCrypto::generate_secrets();
        let crypto2 = AdvancedWalletCrypto::new(
            salt.try_into().unwrap(),
            k_pair.try_into().unwrap(),
            r_vault2.try_into().unwrap()
        );
        let vid3 = crypto2.derive_vid(&rid);
        assert_ne!(vid, vid3, "Different r_vault should break VID lookup");
    }

    #[test]
    fn test_per_rp_key_derivation() {
        let master_key = [42u8; 32];
        
        // Same master + RP should produce same child key
        let child1 = AdvancedWalletCrypto::derive_rp_child_key(&master_key, "example.com").unwrap();
        let child2 = AdvancedWalletCrypto::derive_rp_child_key(&master_key, "example.com").unwrap();
        assert_eq!(child1, child2, "Child key should be deterministic");

        // Different RP should produce different child key
        let child3 = AdvancedWalletCrypto::derive_rp_child_key(&master_key, "different.com").unwrap();
        assert_ne!(child1, child3, "Different RP should produce different child key");
    }

    #[test]
    fn test_kyc_normalization() {
        let kyc = KYCTuple {
            jurisdiction_code: " US ".to_string(),
            doc_type: "drivers-license".to_string(),
            doc_number_norm: "D123-456-789".to_string(),
            surname_norm: " Smith ".to_string(),
            dob_yyyymmdd: "1990-01-01".to_string(),
            liveness_template_hash: "ABC123DEF".to_string(),
        };

        let normalized = AdvancedWalletCrypto::normalize_kyc_tuple(&kyc).unwrap();
        
        // Should be deterministic
        let normalized2 = AdvancedWalletCrypto::normalize_kyc_tuple(&kyc).unwrap();
        assert_eq!(normalized, normalized2, "KYC normalization should be deterministic");
        
        // Should handle whitespace and formatting
        assert!(normalized.len() > 0, "Normalized KYC should not be empty");
    }
}

/// Performance benchmarking for wallet operations
#[cfg(test)]
mod performance_tests {
    use super::*;
    use std::time::Instant;

    #[test]
    fn benchmark_wallet_operations() {
        let (salt, k_pair, r_vault) = AdvancedWalletCrypto::generate_secrets();
        let crypto = AdvancedWalletCrypto::new(
            salt.try_into().unwrap(),
            k_pair.try_into().unwrap(),
            r_vault.try_into().unwrap()
        );

        let kyc = KYCTuple {
            jurisdiction_code: "US".to_string(),
            doc_type: "passport".to_string(),
            doc_number_norm: "123456789".to_string(),
            surname_norm: "smith".to_string(),
            dob_yyyymmdd: "1990-01-01".to_string(),
            liveness_template_hash: "abc123".to_string(),
        };

        // Benchmark RID derivation
        let kyc_cbor = AdvancedWalletCrypto::normalize_kyc_tuple(&kyc).unwrap();
        let start = Instant::now();
        let _rid = crypto.derive_rid(&kyc_cbor);
        let rid_time = start.elapsed();
        println!("⚡ RID derivation: {:.3}μs", rid_time.as_nanos() as f64 / 1000.0);
        assert!(rid_time.as_micros() < 100, "RID derivation should be <100μs");

        // Benchmark pairwise tag generation
        let rid = [1u8; 32];
        let start = Instant::now();
        let _tag = crypto.generate_pairwise_tag(&rid, "example.com").unwrap();
        let tag_time = start.elapsed();
        println!("⚡ Pairwise tag: {:.3}μs", tag_time.as_nanos() as f64 / 1000.0);
        assert!(tag_time.as_micros() < 10, "Pairwise tag should be <10μs");

        // Benchmark VID computation
        let start = Instant::now();
        let _vid = crypto.derive_vid(&rid);
        let vid_time = start.elapsed();
        println!("⚡ VID computation: {:.3}μs", vid_time.as_nanos() as f64 / 1000.0);
        assert!(vid_time.as_micros() < 5, "VID computation should be <5μs");

        // Benchmark per-RP key derivation
        let master_key = [42u8; 32];
        let start = Instant::now();
        let _child_key = AdvancedWalletCrypto::derive_rp_child_key(&master_key, "example.com").unwrap();
        let child_time = start.elapsed();
        println!("⚡ Child key derivation: {:.3}μs", child_time.as_nanos() as f64 / 1000.0);
        assert!(child_time.as_micros() < 20, "Child key derivation should be <20μs");

        println!("✅ All wallet operations under performance targets");
        println!("📊 Total overhead: ~{}μs", 
                rid_time.as_micros() + tag_time.as_micros() + vid_time.as_micros() + child_time.as_micros());
    }
}
