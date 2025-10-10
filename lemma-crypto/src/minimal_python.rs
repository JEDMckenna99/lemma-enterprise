//! Minimal Python bindings for the complete working system

use pyo3::prelude::*;
use std::collections::HashMap;

use crate::minimal_core::{MinimalIssuer, MinimalCore, MinimalCredential, MinimalVerificationResult};
use crate::complete_verification::{CompleteVerifier, CompleteVerificationResult};
use crate::zkp_claims::{ZKPVerifier, ZKPCredential, ZKPClaimType, ZKPClaimProof};
use crate::optimized_verification::{OptimizedVerifier, OptimizedVerificationResult, OptimizationStats};
use crate::ultra_optimized_verification::{UltraOptimizedVerifier, UltraVerificationResult, UltraOptimizationStats};
use crate::device_delegation::{DeviceDelegationManager, DeviceDelegationLemma};
use crate::qr_authentication::{QRSyncManager, QRAuthenticationLemma, QRVerificationResult};
use crate::advanced_wallet::{AdvancedWalletCrypto, KYCTuple};
use crate::envelope_encryption::{WalletEnvelopeV2, EnvelopeEncryptionV2};
use crate::encrypted_browser_wallet::{EncryptedBrowserWallet, CredentialMetadata};

/// Python wrapper for MinimalIssuer
#[pyclass]
pub struct PyMinimalIssuer {
    inner: MinimalIssuer,
}

#[pymethods]
impl PyMinimalIssuer {
    #[new]
    pub fn new() -> Self {
        Self {
            inner: MinimalIssuer::new(),  // Generate NEW unique keypair each time!
        }
    }
    
    #[staticmethod]
    pub fn from_env_or_default() -> Self {
        // For federated identity network - use consistent keypair from env
        Self {
            inner: MinimalIssuer::from_env_or_default(),
        }
    }
    
    pub fn get_did(&self) -> String {
        self.inner.did().to_string()
    }
    
    pub fn get_public_key_hex(&self) -> String {
        self.inner.public_key_hex()
    }
    
    pub fn issue_credential(&self, subject: String, claims: HashMap<String, String>) -> PyResult<String> {
        let json_claims: HashMap<String, serde_json::Value> = claims
            .into_iter()
            .map(|(k, v)| (k, serde_json::Value::String(v)))
            .collect();
        
        let credential = self.inner.issue_credential(subject, json_claims)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        serde_json::to_string(&credential)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }
}

/// Python wrapper for CompleteVerificationResult
#[pyclass]
pub struct PyCompleteVerificationResult {
    #[pyo3(get)]
    pub verified: bool,
    #[pyo3(get)]
    pub signature_valid: bool,
    #[pyo3(get)]
    pub not_revoked: bool,
    #[pyo3(get)]
    pub issuer_did: String,
    #[pyo3(get)]
    pub verification_time_ns: u64,
    #[pyo3(get)]
    pub signature_time_ns: u64,
    #[pyo3(get)]
    pub revocation_time_ns: u64,
    #[pyo3(get)]
    pub confidence: f64,
}

impl From<CompleteVerificationResult> for PyCompleteVerificationResult {
    fn from(result: CompleteVerificationResult) -> Self {
        Self {
            verified: result.verified,
            signature_valid: result.signature_valid,
            not_revoked: result.not_revoked,
            issuer_did: result.issuer_did,
            verification_time_ns: result.verification_time_ns,
            signature_time_ns: result.signature_time_ns,
            revocation_time_ns: result.revocation_time_ns,
            confidence: result.confidence,
        }
    }
}

/// Python wrapper for CompleteVerifier
#[pyclass]
pub struct PyCompleteVerifier {
    inner: CompleteVerifier,
}

#[pymethods]
impl PyCompleteVerifier {
    #[new]
    pub fn new() -> PyResult<Self> {
        let inner = CompleteVerifier::new()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(Self { inner })
    }
    
    pub fn verify_credential(&mut self, credential_json: String) -> PyResult<PyCompleteVerificationResult> {
        let result = self.inner.verify_credential_json(&credential_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(result.into())
    }
    
    pub fn revoke_credential(&mut self, credential_id: String) -> PyResult<()> {
        self.inner.revoke_credential(&credential_id)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(())
    }
}

/// Python wrapper for ZKPVerifier
#[pyclass]
pub struct PyZKPVerifier {
    inner: ZKPVerifier,
}

#[pymethods]
impl PyZKPVerifier {
    #[new]
    pub fn new() -> PyResult<Self> {
        let inner = ZKPVerifier::new()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(Self { inner })
    }
    
    pub fn create_zkp_credential(&mut self, credential_json: String, claim_types: Vec<String>) -> PyResult<String> {
        // Parse base credential
        let base_credential: MinimalCredential = serde_json::from_str(&credential_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        // Convert string claim types to ZKPClaimType
        let zkp_claims: Vec<ZKPClaimType> = claim_types.into_iter().map(|claim_type| {
            match claim_type.as_str() {
                "age_above_21" => ZKPClaimType::AgeAbove(21),
                "age_above_18" => ZKPClaimType::AgeAbove(18),
                "premium_membership" => ZKPClaimType::SetMembership(vec!["premium".to_string(), "vip".to_string()]),
                _ => ZKPClaimType::Custom(claim_type),
            }
        }).collect();
        
        let zkp_credential = self.inner.create_zkp_credential(base_credential, zkp_claims)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        serde_json::to_string(&zkp_credential)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }
    
    pub fn verify_zkp_credential(&mut self, zkp_credential_json: String) -> PyResult<PyCompleteVerificationResult> {
        let zkp_credential: ZKPCredential = serde_json::from_str(&zkp_credential_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        let result = self.inner.verify_zkp_credential(&zkp_credential)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(result.into())
    }
}

/// Python wrapper for OptimizedVerifier
#[pyclass]
pub struct PyOptimizedVerifier {
    inner: OptimizedVerifier,
}

#[pymethods]
impl PyOptimizedVerifier {
    #[new]
    pub fn new() -> PyResult<Self> {
        let inner = OptimizedVerifier::new()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(Self { inner })
    }
    
    pub fn verify_credential(&mut self, credential_json: String) -> PyResult<PyOptimizedVerificationResult> {
        let credential: MinimalCredential = serde_json::from_str(&credential_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        let result = self.inner.verify_optimized(&credential)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(result.into())
    }
    
    pub fn revoke_credential(&mut self, credential_id: String) -> PyResult<()> {
        self.inner.revoke_credential(&credential_id)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(())
    }
    
    pub fn get_performance_stats(&self) -> PyResult<PyOptimizationStats> {
        let stats = self.inner.get_performance_stats();
        Ok(stats.into())
    }
    
    /// Compute OPRF evaluation for privacy-preserving revocation
    /// 
    /// This takes a credential ID and returns a privacy-preserving hash using
    /// Ristretto255 OPRF. The server's secret key is used to evaluate the OPRF
    /// without learning the credential ID.
    pub fn compute_oprf_evaluation(&self, credential_id: String) -> PyResult<String> {
        use crate::oprf::OPRFClient;
        use sha2::{Sha512, Digest};
        
        // Get or create server key from environment
        let server_key_bytes = std::env::var("LEMMA_OPRF_SERVER_KEY")
            .ok()
            .and_then(|hex| hex::decode(hex).ok())
            .and_then(|bytes| {
                if bytes.len() == 32 {
                    let mut arr = [0u8; 32];
                    arr.copy_from_slice(&bytes);
                    Some(arr)
                } else {
                    None
                }
            })
            .unwrap_or_else(|| {
                // Generate deterministic key from a constant seed for consistency
                let mut hasher = Sha512::new();
                hasher.update(b"LEMMA_OPRF_SERVER_KEY_V1");
                let hash = hasher.finalize();
                let mut key = [0u8; 32];
                key.copy_from_slice(&hash[0..32]);
                key
            });
        
        // Create OPRF client with server key
        let mut oprf_client = OPRFClient::new_with_server_key(server_key_bytes);
        
        // Perform complete OPRF evaluation
        let oprf_result = oprf_client.get_evaluation(&credential_id)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        // Return hex-encoded OPRF evaluation
        Ok(hex::encode(oprf_result.evaluation))
    }
}

/// Python wrapper for OptimizedVerificationResult
#[pyclass]
pub struct PyOptimizedVerificationResult {
    #[pyo3(get)]
    pub verified: bool,
    #[pyo3(get)]
    pub signature_valid: bool,
    #[pyo3(get)]
    pub not_revoked: bool,
    #[pyo3(get)]
    pub issuer_did: String,
    #[pyo3(get)]
    pub verification_time_ns: u64,
    #[pyo3(get)]
    pub signature_time_ns: u64,
    #[pyo3(get)]
    pub revocation_time_ns: u64,
    #[pyo3(get)]
    pub confidence: f64,
    #[pyo3(get)]
    pub cache_hit: bool,
    #[pyo3(get)]
    pub optimization_used: bool,
}

impl From<OptimizedVerificationResult> for PyOptimizedVerificationResult {
    fn from(result: OptimizedVerificationResult) -> Self {
        Self {
            verified: result.verified,
            signature_valid: result.signature_valid,
            not_revoked: result.not_revoked,
            issuer_did: result.issuer_did,
            verification_time_ns: result.verification_time_ns,
            signature_time_ns: result.signature_time_ns,
            revocation_time_ns: result.revocation_time_ns,
            confidence: result.confidence,
            cache_hit: result.cache_hit,
            optimization_used: result.optimization_used,
        }
    }
}

/// Python wrapper for OptimizationStats
#[pyclass]
pub struct PyOptimizationStats {
    #[pyo3(get)]
    pub total_verifications: u64,
    #[pyo3(get)]
    pub cache_hits: u64,
    #[pyo3(get)]
    pub cache_misses: u64,
    #[pyo3(get)]
    pub cache_hit_rate: f64,
    #[pyo3(get)]
    pub public_key_cache_size: usize,
    #[pyo3(get)]
    pub oprf_cache_size: usize,
}

impl From<OptimizationStats> for PyOptimizationStats {
    fn from(stats: OptimizationStats) -> Self {
        Self {
            total_verifications: stats.total_verifications,
            cache_hits: stats.cache_hits,
            cache_misses: stats.cache_misses,
            cache_hit_rate: stats.cache_hit_rate,
            public_key_cache_size: stats.public_key_cache_size,
            oprf_cache_size: stats.oprf_cache_size,
        }
    }
}

/// Python wrapper for UltraOptimizedVerifier
#[pyclass]
pub struct PyUltraOptimizedVerifier {
    inner: UltraOptimizedVerifier,
}

#[pymethods]
impl PyUltraOptimizedVerifier {
    #[new]
    pub fn new() -> PyResult<Self> {
        let inner = UltraOptimizedVerifier::new()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(Self { inner })
    }
    
    pub fn verify_credential(&mut self, credential_json: String) -> PyResult<PyUltraVerificationResult> {
        let result = self.inner.verify_credential_json_ultra(&credential_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(result.into())
    }
    
    pub fn revoke_credential(&mut self, credential_id: String) -> PyResult<()> {
        self.inner.revoke_credential(&credential_id)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(())
    }
    
    pub fn get_ultra_stats(&self) -> PyResult<PyUltraOptimizationStats> {
        let stats = self.inner.get_ultra_stats().clone();
        Ok(stats.into())
    }
}

/// Python wrapper for UltraVerificationResult
#[pyclass]
pub struct PyUltraVerificationResult {
    #[pyo3(get)]
    pub verified: bool,
    #[pyo3(get)]
    pub signature_valid: bool,
    #[pyo3(get)]
    pub not_revoked: bool,
    #[pyo3(get)]
    pub issuer_did: String,
    #[pyo3(get)]
    pub verification_time_ns: u64,
    #[pyo3(get)]
    pub signature_time_ns: u64,
    #[pyo3(get)]
    pub revocation_time_ns: u64,
    #[pyo3(get)]
    pub confidence: f64,
    #[pyo3(get)]
    pub cache_level: u8,
    #[pyo3(get)]
    pub optimization_level: String,
    #[pyo3(get)]
    pub simd_used: bool,
}

impl From<UltraVerificationResult> for PyUltraVerificationResult {
    fn from(result: UltraVerificationResult) -> Self {
        Self {
            verified: result.verified,
            signature_valid: result.signature_valid,
            not_revoked: result.not_revoked,
            issuer_did: result.issuer_did,
            verification_time_ns: result.verification_time_ns,
            signature_time_ns: result.signature_time_ns,
            revocation_time_ns: result.revocation_time_ns,
            confidence: result.confidence,
            cache_level: result.cache_level,
            optimization_level: result.optimization_level,
            simd_used: result.simd_used,
        }
    }
}

/// Python wrapper for UltraOptimizationStats
#[pyclass]
pub struct PyUltraOptimizationStats {
    #[pyo3(get)]
    pub total_verifications: u64,
    #[pyo3(get)]
    pub batch_verifications: u64,
    #[pyo3(get)]
    pub single_verifications: u64,
    #[pyo3(get)]
    pub cache_hits: u64,
    #[pyo3(get)]
    pub cache_misses: u64,
    #[pyo3(get)]
    pub simd_operations: u64,
    #[pyo3(get)]
    pub memory_pool_hits: u64,
    #[pyo3(get)]
    pub average_verification_ns: u64,
    #[pyo3(get)]
    pub average_cached_ns: u64,
    #[pyo3(get)]
    pub average_batch_ns: u64,
}

impl From<UltraOptimizationStats> for PyUltraOptimizationStats {
    fn from(stats: UltraOptimizationStats) -> Self {
        Self {
            total_verifications: stats.total_verifications,
            batch_verifications: stats.batch_verifications,
            single_verifications: stats.single_verifications,
            cache_hits: stats.cache_hits,
            cache_misses: stats.cache_misses,
            simd_operations: stats.simd_operations,
            memory_pool_hits: stats.memory_pool_hits,
            average_verification_ns: stats.average_verification_ns,
            average_cached_ns: stats.average_cached_ns,
            average_batch_ns: stats.average_batch_ns,
        }
    }
}

/// Python wrapper for QRSyncManager (Multi-Lemma Wallet Sync)
#[pyclass]
pub struct PyQRSyncManager {
    inner: QRSyncManager,
}

#[pymethods]
impl PyQRSyncManager {
    #[new]
    pub fn new() -> PyResult<Self> {
        let inner = QRSyncManager::new()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(Self { inner })
    }
    
    pub fn create_qr_auth_lemma(
        &self,
        mobile_issuer: &PyMinimalIssuer,
        requesting_device_did: String,
        requested_scope: Vec<String>,
        requested_duration: u64,
        device_fingerprint: String,
    ) -> PyResult<String> {
        let qr_lemma = self.inner.create_qr_auth_lemma(
            &mobile_issuer.inner,
            requesting_device_did,
            requested_scope,
            requested_duration,
            device_fingerprint,
        ).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        serde_json::to_string(&qr_lemma)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }
    
    pub fn verify_qr_auth_lemma(&mut self, qr_lemma_json: String) -> PyResult<PyQRVerificationResult> {
        let qr_lemma: QRAuthenticationLemma = serde_json::from_str(&qr_lemma_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        let result = self.inner.verify_qr_auth_lemma(&qr_lemma)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(result.into())
    }
    
    pub fn generate_qr_data(&self, qr_lemma_json: String) -> PyResult<String> {
        let qr_lemma: QRAuthenticationLemma = serde_json::from_str(&qr_lemma_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        self.inner.generate_qr_data(&qr_lemma)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }
    
    pub fn parse_qr_data(&self, qr_data: String) -> PyResult<String> {
        let qr_lemma = self.inner.parse_qr_data(&qr_data)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        serde_json::to_string(&qr_lemma)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }
}

/// Python wrapper for QRVerificationResult
#[pyclass]
pub struct PyQRVerificationResult {
    #[pyo3(get)]
    pub valid: bool,
    #[pyo3(get)]
    pub reason: String,
    #[pyo3(get)]
    pub sync_authorized: bool,
    #[pyo3(get)]
    pub delegation_lemma_json: Option<String>,
}

impl From<QRVerificationResult> for PyQRVerificationResult {
    fn from(result: QRVerificationResult) -> Self {
        let delegation_json = result.delegation_lemma.map(|lemma| {
            serde_json::to_string(&lemma).unwrap_or_default()
        });
        
        Self {
            valid: result.valid,
            reason: result.reason,
            sync_authorized: result.sync_authorized,
            delegation_lemma_json: delegation_json,
        }
    }
}

/// Python wrapper for DeviceDelegationManager
#[pyclass]
pub struct PyDeviceDelegationManager {
    inner: DeviceDelegationManager,
}

#[pymethods]
impl PyDeviceDelegationManager {
    #[new]
    pub fn new() -> PyResult<Self> {
        let inner = DeviceDelegationManager::new()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        Ok(Self { inner })
    }
    
    pub fn verify_device_delegation(&mut self, delegation_lemma_json: String) -> PyResult<bool> {
        let delegation_lemma: DeviceDelegationLemma = serde_json::from_str(&delegation_lemma_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        
        self.inner.verify_device_delegation(&delegation_lemma)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }
}

/// Module initialization for minimal Python bindings
pub fn register_minimal_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<PyMinimalIssuer>()?;
    m.add_class::<PyCompleteVerifier>()?;
    m.add_class::<PyCompleteVerificationResult>()?;
    m.add_class::<PyOptimizedVerifier>()?;
    m.add_class::<PyOptimizedVerificationResult>()?;
    m.add_class::<PyOptimizationStats>()?;
    m.add_class::<PyUltraOptimizedVerifier>()?;
    m.add_class::<PyUltraVerificationResult>()?;
    m.add_class::<PyUltraOptimizationStats>()?;
    m.add_class::<PyZKPVerifier>()?;
    m.add_class::<PyQRSyncManager>()?;
    m.add_class::<PyQRVerificationResult>()?;
    m.add_class::<PyDeviceDelegationManager>()?;
    m.add_class::<PyAdvancedWalletCrypto>()?;
    m.add_class::<PyEncryptedWallet>()?;  // Add encrypted wallet
    Ok(())
}

/// Python wrapper for AdvancedWalletCrypto
#[pyclass]
pub struct PyAdvancedWalletCrypto {
    inner: AdvancedWalletCrypto,
}

#[pymethods]
impl PyAdvancedWalletCrypto {
    #[new]
    pub fn new(issuer_salt: Vec<u8>, k_pair: Vec<u8>, r_vault: Vec<u8>) -> PyResult<Self> {
        if issuer_salt.len() != 32 || k_pair.len() != 32 || r_vault.len() != 32 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "All keys must be exactly 32 bytes"
            ));
        }
        
        let mut issuer_array = [0u8; 32];
        let mut k_pair_array = [0u8; 32];
        let mut r_vault_array = [0u8; 32];
        
        issuer_array.copy_from_slice(&issuer_salt);
        k_pair_array.copy_from_slice(&k_pair);
        r_vault_array.copy_from_slice(&r_vault);
        
        Ok(PyAdvancedWalletCrypto {
            inner: AdvancedWalletCrypto::new(issuer_array, k_pair_array, r_vault_array)
        })
    }
    
    #[staticmethod]
    pub fn generate_secrets() -> (Vec<u8>, Vec<u8>, Vec<u8>) {
        AdvancedWalletCrypto::generate_secrets()
    }
    
    pub fn derive_rid(&self, kyc_tuple_cbor: Vec<u8>) -> Vec<u8> {
        self.inner.derive_rid(&kyc_tuple_cbor).to_vec()
    }
    
    pub fn generate_pairwise_tag(&self, rid: Vec<u8>, rp_id: String) -> PyResult<Vec<u8>> {
        if rid.len() != 32 {
            return Err(pyo3::exceptions::PyValueError::new_err("RID must be 32 bytes"));
        }
        
        let mut rid_array = [0u8; 32];
        rid_array.copy_from_slice(&rid);
        
        match self.inner.generate_pairwise_tag(&rid_array, &rp_id) {
            Ok(tag) => Ok(tag.to_vec()),
            Err(e) => Err(pyo3::exceptions::PyRuntimeError::new_err(e))
        }
    }
    
    pub fn derive_vid(&self, rid: Vec<u8>) -> PyResult<Vec<u8>> {
        if rid.len() != 32 {
            return Err(pyo3::exceptions::PyValueError::new_err("RID must be 32 bytes"));
        }
        
        let mut rid_array = [0u8; 32];
        rid_array.copy_from_slice(&rid);
        
        Ok(self.inner.derive_vid(&rid_array).to_vec())
    }
}

/// Python wrapper for EncryptedBrowserWallet
#[pyclass]
pub struct PyEncryptedWallet {
    inner: EncryptedBrowserWallet,
}

#[pymethods]
impl PyEncryptedWallet {
    #[new]
    pub fn new() -> Self {
        Self {
            inner: EncryptedBrowserWallet::new(),
        }
    }
    
    /// Unlock wallet with password/PIN
    pub fn unlock(&mut self, password: String) -> PyResult<()> {
        self.inner.unlock(&password)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to unlock wallet: {:?}", e)
            ))
    }
    
    /// Lock wallet (clear master key from memory)
    pub fn lock(&mut self) {
        self.inner.lock();
    }
    
    /// Store encrypted credential
    pub fn store_credential(&mut self, credential_json: String, credential_type: String) -> PyResult<String> {
        let credential: MinimalCredential = serde_json::from_str(&credential_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to parse credential: {}", e)
            ))?;
        
        self.inner.store_credential(&credential, &credential_type)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to store credential: {:?}", e)
            ))
    }
    
    /// Get encrypted credential by ID
    pub fn get_credential(&mut self, credential_id: String) -> PyResult<String> {
        let credential = self.inner.get_credential(&credential_id)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to get credential: {:?}", e)
            ))?;
        
        serde_json::to_string(&credential)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to serialize credential: {}", e)
            ))
    }
    
    /// List all credentials (metadata only, non-sensitive)
    pub fn list_credentials(&self) -> PyResult<Vec<String>> {
        let metadata_list = self.inner.list_credentials();
        
        metadata_list.into_iter()
            .map(|meta| serde_json::to_string(&meta)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    format!("Failed to serialize metadata: {}", e)
                )))
            .collect()
    }
    
    /// Remove credential from wallet
    pub fn remove_credential(&mut self, credential_id: String) -> PyResult<()> {
        self.inner.remove_credential(&credential_id)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to remove credential: {:?}", e)
            ))
    }
    
    /// Check if wallet is unlocked
    pub fn is_unlocked(&self) -> bool {
        self.inner.is_unlocked()
    }
    
    /// Get wallet statistics
    pub fn get_stats(&self) -> PyResult<String> {
        let stats = self.inner.get_stats();
        serde_json::to_string(stats)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to serialize stats: {}", e)
            ))
    }
}

/// Python module
#[cfg(feature = "python")]
#[pyo3::pymodule]
fn lemma_crypto(_py: Python, m: &PyModule) -> PyResult<()> {
    // Add working classes
    register_minimal_classes(m)?;
    
    // Add constants
    m.add("SCALAR_SIZE", crate::constants::SCALAR_SIZE)?;
    m.add("PUBLIC_KEY_SIZE", crate::constants::PUBLIC_KEY_SIZE)?;
    m.add("SIGNATURE_SIZE", crate::constants::SIGNATURE_SIZE)?;
    m.add("DID_METHOD", crate::constants::DID_METHOD)?;
    
    // Add library info
    let info = crate::library_info();
    for (key, value) in info {
        m.add(&key, value)?;
    }
    
    Ok(())
}