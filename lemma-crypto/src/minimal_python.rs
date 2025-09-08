//! Minimal Python bindings for the complete working system

use pyo3::prelude::*;
use std::collections::HashMap;

use crate::minimal_core::{MinimalIssuer, MinimalCore, MinimalCredential, MinimalVerificationResult};
use crate::complete_verification::{CompleteVerifier, CompleteVerificationResult};
use crate::zkp_claims::{ZKPVerifier, ZKPCredential, ZKPClaimType, ZKPClaimProof};
use crate::optimized_verification::{OptimizedVerifier, OptimizedVerificationResult, OptimizationStats};

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
            inner: MinimalIssuer::new(),
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

/// Module initialization for minimal Python bindings
pub fn register_minimal_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<PyMinimalIssuer>()?;
    m.add_class::<PyCompleteVerifier>()?;
    m.add_class::<PyCompleteVerificationResult>()?;
    m.add_class::<PyOptimizedVerifier>()?;
    m.add_class::<PyOptimizedVerificationResult>()?;
    m.add_class::<PyOptimizationStats>()?;
    m.add_class::<PyZKPVerifier>()?;
    Ok(())
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