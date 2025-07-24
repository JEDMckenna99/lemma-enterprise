//! Core verification engine with pluggable micro-package architecture

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;
use serde::{Deserialize, Serialize};

use crate::{
    oprf::{OPRFClient, OPRFResult},
    bloom::CascadedBloomFilter,
    credentials::{VerifiableCredential, Ed25519PublicKey},
    packages::VerificationPackage,
    simd_signatures::SIMDVerifier,
    hsm::{HSMVerifier, HSMStats},
    gpu::{GPUVerifier, GPUStats},
    ClaimSet, VerificationMetadata,
    Result, LemmaError
};

#[cfg(not(target_arch = "wasm32"))]
use crate::zkp_claims::{ZKPCredential, ZKPVerifier, ZKPClaim, ZKPProofSystem};
use ed25519_dalek::{VerifyingKey, Signature};

/// Memory pool for efficient credential verification
pub struct VerificationMemoryPool {
    // Pre-allocated buffers for common operations
    credential_buffers: Vec<Vec<u8>>,
    result_buffers: Vec<Vec<u8>>,
    message_buffers: Vec<Vec<u8>>,
    free_credential_indices: Vec<usize>,
    free_result_indices: Vec<usize>,
    free_message_indices: Vec<usize>,
    
    // Pool statistics
    total_allocations: usize,
    pool_hits: usize,
    pool_misses: usize,
}

impl VerificationMemoryPool {
    pub fn new(initial_capacity: usize) -> Self {
        let mut credential_buffers = Vec::with_capacity(initial_capacity);
        let mut result_buffers = Vec::with_capacity(initial_capacity);
        let mut message_buffers = Vec::with_capacity(initial_capacity);
        let mut free_credential_indices = Vec::with_capacity(initial_capacity);
        let mut free_result_indices = Vec::with_capacity(initial_capacity);
        let mut free_message_indices = Vec::with_capacity(initial_capacity);
        
        // Pre-allocate buffers
        for i in 0..initial_capacity {
            credential_buffers.push(Vec::with_capacity(8192)); // 8KB per credential
            result_buffers.push(Vec::with_capacity(1024)); // 1KB per result
            message_buffers.push(Vec::with_capacity(2048)); // 2KB per message
            free_credential_indices.push(i);
            free_result_indices.push(i);
            free_message_indices.push(i);
        }
        
        Self {
            credential_buffers,
            result_buffers,
            message_buffers,
            free_credential_indices,
            free_result_indices,
            free_message_indices,
            total_allocations: 0,
            pool_hits: 0,
            pool_misses: 0,
        }
    }
    
    pub fn get_credential_buffer(&mut self) -> (usize, &mut Vec<u8>) {
        self.total_allocations += 1;
        
        if let Some(index) = self.free_credential_indices.pop() {
            self.pool_hits += 1;
            let buffer = &mut self.credential_buffers[index];
            buffer.clear();
            (index, buffer)
        } else {
            self.pool_misses += 1;
            // Pool exhausted - allocate new
            let new_buffer = Vec::with_capacity(8192);
            self.credential_buffers.push(new_buffer);
            let index = self.credential_buffers.len() - 1;
            (index, &mut self.credential_buffers[index])
        }
    }
    
    pub fn get_result_buffer(&mut self) -> (usize, &mut Vec<u8>) {
        self.total_allocations += 1;
        
        if let Some(index) = self.free_result_indices.pop() {
            self.pool_hits += 1;
            let buffer = &mut self.result_buffers[index];
            buffer.clear();
            (index, buffer)
        } else {
            self.pool_misses += 1;
            let new_buffer = Vec::with_capacity(1024);
            self.result_buffers.push(new_buffer);
            let index = self.result_buffers.len() - 1;
            (index, &mut self.result_buffers[index])
        }
    }
    
    pub fn get_message_buffer(&mut self) -> (usize, &mut Vec<u8>) {
        self.total_allocations += 1;
        
        if let Some(index) = self.free_message_indices.pop() {
            self.pool_hits += 1;
            let buffer = &mut self.message_buffers[index];
            buffer.clear();
            (index, buffer)
        } else {
            self.pool_misses += 1;
            let new_buffer = Vec::with_capacity(2048);
            self.message_buffers.push(new_buffer);
            let index = self.message_buffers.len() - 1;
            (index, &mut self.message_buffers[index])
        }
    }
    
    pub fn return_credential_buffer(&mut self, index: usize) {
        if index < self.credential_buffers.len() {
            self.free_credential_indices.push(index);
        }
    }
    
    pub fn return_result_buffer(&mut self, index: usize) {
        if index < self.result_buffers.len() {
            self.free_result_indices.push(index);
        }
    }
    
    pub fn return_message_buffer(&mut self, index: usize) {
        if index < self.message_buffers.len() {
            self.free_message_indices.push(index);
        }
    }
    
    pub fn get_stats(&self) -> VerificationPoolStats {
        VerificationPoolStats {
            total_allocations: self.total_allocations,
            pool_hits: self.pool_hits,
            pool_misses: self.pool_misses,
            hit_rate: if self.total_allocations > 0 {
                (self.pool_hits as f64 / self.total_allocations as f64) * 100.0
            } else {
                0.0
            },
            credential_buffers_count: self.credential_buffers.len(),
            result_buffers_count: self.result_buffers.len(),
            message_buffers_count: self.message_buffers.len(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerificationPoolStats {
    pub total_allocations: usize,
    pub pool_hits: usize,
    pub pool_misses: usize,
    pub hit_rate: f64,
    pub credential_buffers_count: usize,
    pub result_buffers_count: usize,
    pub message_buffers_count: usize,
}

/// Universal verification result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerificationResult {
    pub verified: bool,
    pub package_type: String,
    pub confidence: f64,
    pub metadata: VerificationMetadata,
    pub cached: bool,
    pub offline: bool,
    pub verification_time_ns: u64,
}

impl VerificationResult {
    pub fn new(
        verified: bool,
        package_type: String,
        confidence: f64,
        metadata: VerificationMetadata,
    ) -> Self {
        Self {
            verified,
            package_type,
            confidence,
            metadata,
            cached: false,
            offline: true,
            verification_time_ns: 0,
        }
    }
    
    pub fn with_timing(
        verified: bool,
        package_type: String,
        confidence: f64,
        metadata: VerificationMetadata,
        verification_time_ns: u64,
    ) -> Self {
        Self {
            verified,
            package_type,
            confidence,
            metadata,
            cached: false,
            offline: true,
            verification_time_ns,
        }
    }
}

/// LRU Cache implementation for efficient multi-level caching
pub struct LRUCache<K, V> {
    capacity: usize,
    map: HashMap<K, V>,
    access_order: Vec<K>,
}

impl<K: Clone + Eq + std::hash::Hash, V> LRUCache<K, V> {
    pub fn new(capacity: usize) -> Self {
        Self {
            capacity,
            map: HashMap::new(),
            access_order: Vec::new(),
        }
    }
    
    pub fn get(&mut self, key: &K) -> Option<&V> {
        if self.map.contains_key(key) {
            // Move to end (most recently used)
            self.access_order.retain(|k| k != key);
            self.access_order.push(key.clone());
            self.map.get(key)
        } else {
            None
        }
    }
    
    pub fn insert(&mut self, key: K, value: V) {
        if self.map.contains_key(&key) {
            // Update existing
            self.map.insert(key.clone(), value);
            self.access_order.retain(|k| k != &key);
            self.access_order.push(key);
        } else {
            // Check capacity
            if self.map.len() >= self.capacity {
                // Remove least recently used
                if let Some(lru_key) = self.access_order.first().cloned() {
                    self.map.remove(&lru_key);
                    self.access_order.remove(0);
                }
            }
            
            self.map.insert(key.clone(), value);
            self.access_order.push(key);
        }
    }
    
    pub fn len(&self) -> usize {
        self.map.len()
    }
    
    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }
    
    pub fn remove(&mut self, key: &K) -> Option<V> {
        self.access_order.retain(|k| k != key);
        self.map.remove(key)
    }
    
    pub fn clear(&mut self) {
        self.map.clear();
        self.access_order.clear();
    }
}

/// Cache configuration constants
const MAX_ISSUER_CACHE_SIZE: usize = 1000;     // 1000 issuers
const MAX_PACKAGE_CACHE_SIZE: usize = 50;      // 50 package types
const MAX_RESULT_CACHE_SIZE: usize = 10000;    // 10K results
const BATCH_THRESHOLD: usize = 10;             // Process batch every 10 credentials

/// Tier 1: Issuer-Level Cache Data
#[derive(Debug, Clone)]
pub struct IssuerVerificationData {
    pub public_key: Ed25519PublicKey,
    pub did_parsed: String,
    pub last_used: Instant,
    pub usage_count: u64,
}

impl IssuerVerificationData {
    pub fn new(public_key: Ed25519PublicKey, did_parsed: String) -> Self {
        Self {
            public_key,
            did_parsed,
            last_used: Instant::now(),
            usage_count: 1,
        }
    }
    
    pub fn update_usage(&mut self) {
        self.last_used = Instant::now();
        self.usage_count += 1;
    }
}

/// Tier 2: Package-Level Cache Data
#[derive(Debug, Clone)]
pub struct PackageVerificationData {
    pub package_type: String,
    pub revocation_bloom: Arc<CascadedBloomFilter>,
    pub last_used: Instant,
    pub usage_count: u64,
}

impl PackageVerificationData {
    pub fn new(package_type: String, revocation_bloom: Arc<CascadedBloomFilter>) -> Self {
        Self {
            package_type,
            revocation_bloom,
            last_used: Instant::now(),
            usage_count: 1,
        }
    }
    
    pub fn update_usage(&mut self) {
        self.last_used = Instant::now();
        self.usage_count += 1;
    }
}

/// Verification ID for batch processing
pub type VerificationId = u64;

/// Pending verification for batch processing
#[derive(Debug, Clone)]
pub struct PendingVerification {
    pub id: VerificationId,
    pub credential: VerifiableCredential,
    pub submitted_at: Instant,
}

/// Tier 3: Batch Processing Engine
pub struct BatchVerificationEngine {
    pub pending_batch: Vec<PendingVerification>,
    pub batch_threshold: usize,
    pub next_id: VerificationId,
    pub completed_verifications: HashMap<VerificationId, VerificationResult>,
}

impl BatchVerificationEngine {
    pub fn new(batch_threshold: usize) -> Self {
        Self {
            pending_batch: Vec::new(),
            batch_threshold,
            next_id: 1,
            completed_verifications: HashMap::new(),
        }
    }
    
    pub fn add_verification(&mut self, credential: &VerifiableCredential) -> VerificationId {
        let verification_id = self.next_id;
        self.next_id += 1;
        
        self.pending_batch.push(PendingVerification {
            id: verification_id,
            credential: credential.clone(),
            submitted_at: Instant::now(),
        });
        
        verification_id
    }
    
    pub fn should_process_batch(&self) -> bool {
        self.pending_batch.len() >= self.batch_threshold
    }
    
    pub fn get_pending_count(&self) -> usize {
        self.pending_batch.len()
    }
    
    pub fn clear_batch(&mut self) {
        self.pending_batch.clear();
    }
    
    pub fn get_result(&self, id: VerificationId) -> Option<&VerificationResult> {
        self.completed_verifications.get(&id)
    }
    
    pub fn insert_result(&mut self, id: VerificationId, result: VerificationResult) {
        self.completed_verifications.insert(id, result);
    }
}

/// Multi-level cache statistics for performance monitoring
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MultiLevelCacheStats {
    pub issuer_cache_size: usize,
    pub issuer_cache_capacity: usize,
    pub package_cache_size: usize,
    pub package_cache_capacity: usize,
    pub result_cache_size: usize,
    pub result_cache_capacity: usize,
    pub pending_batch_size: usize,
    pub batch_threshold: usize,
}

impl MultiLevelCacheStats {
    /// Calculate cache hit rate estimates
    pub fn issuer_cache_utilization(&self) -> f64 {
        (self.issuer_cache_size as f64 / self.issuer_cache_capacity as f64) * 100.0
    }
    
    pub fn package_cache_utilization(&self) -> f64 {
        (self.package_cache_size as f64 / self.package_cache_capacity as f64) * 100.0
    }
    
    pub fn result_cache_utilization(&self) -> f64 {
        (self.result_cache_size as f64 / self.result_cache_capacity as f64) * 100.0
    }
}

/// Universal offline verification engine with multi-level caching
pub struct LemmaCore {
    oprf_client: OPRFClient,
    bloom_cascade: CascadedBloomFilter,
    verification_packages: HashMap<String, Box<dyn VerificationPackage>>,
    
    // Multi-level caching system
    issuer_cache: LRUCache<String, IssuerVerificationData>,
    package_cache: LRUCache<String, PackageVerificationData>,
    result_cache: LRUCache<String, VerificationResult>,
    batch_processor: BatchVerificationEngine,
    
    // Hardware acceleration
    memory_pool: VerificationMemoryPool,
    simd_verifier: SIMDVerifier,
    hsm_verifier: HSMVerifier,
    gpu_verifier: GPUVerifier,
    
    // ZKP support for privacy-preserving verification
    zkp_verifier: ZKPVerifier,
}

impl LemmaCore {
    /// Create a new LemmaCore instance with multi-level caching
    pub fn new() -> Result<Self> {
        let oprf_client = OPRFClient::new();
        let bloom_cascade = CascadedBloomFilter::new(3, 100_000, 0.01)
            .map_err(|e| LemmaError::Bloom(e.to_string()))?;
        let verification_packages = HashMap::new();
        
        // Initialize multi-level caching system
        let issuer_cache = LRUCache::new(MAX_ISSUER_CACHE_SIZE);
        let package_cache = LRUCache::new(MAX_PACKAGE_CACHE_SIZE);
        let result_cache = LRUCache::new(MAX_RESULT_CACHE_SIZE);
        let batch_processor = BatchVerificationEngine::new(BATCH_THRESHOLD);
        
        // Initialize hardware acceleration
        let memory_pool = VerificationMemoryPool::new(64); // Start with 64 pre-allocated buffers
        let simd_verifier = SIMDVerifier::new();
        let hsm_verifier = HSMVerifier::new()?;
        let gpu_verifier = GPUVerifier::new()?;
        
        // Initialize ZKP verifier
        let zkp_verifier = ZKPVerifier::new();
        
        Ok(Self {
            oprf_client,
            bloom_cascade,
            verification_packages,
            issuer_cache,
            package_cache,
            result_cache,
            batch_processor,
            memory_pool,
            simd_verifier,
            hsm_verifier,
            gpu_verifier,
            zkp_verifier,
        })
    }

    /// Register a verification package
    pub fn register_package<P: VerificationPackage + 'static>(&mut self, package: P) {
        self.verification_packages.insert(
            package.package_type().to_string(),
            Box::new(package)
        );
    }
    
    /// Register a verifying key for SIMD signature verification
    pub fn register_verifying_key(&mut self, issuer: String, key: VerifyingKey) {
        self.simd_verifier.add_verifying_key(issuer, key);
    }
    
    // Multi-level cache key generation functions
    
    /// Generate issuer cache key
    fn issuer_cache_key(issuer_did: &str) -> String {
        format!("issuer:{}", issuer_did)
    }
    
    /// Generate package cache key
    fn package_cache_key(package_type: &str, issuer_did: &str) -> String {
        format!("package:{}:{}", package_type, issuer_did)
    }
    
    /// Generate credential cache key
    fn credential_cache_key(package_type: &str, credential_id: &str) -> String {
        format!("{}:{}", package_type, credential_id)
    }
    
    /// Extract issuer DID from credential
    fn extract_issuer_did(credential: &VerifiableCredential) -> Result<String> {
        credential.get_claim("issuer")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string())
            .ok_or_else(|| LemmaError::VerificationFailed("Missing issuer claim".to_string()))
    }

    /// Universal verification method with multi-level caching optimization
    pub fn verify(&mut self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        let start_time = std::time::Instant::now();

        // Get package type from credential
        let package_type = credential.get_claim("packageType")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::VerificationFailed("Missing packageType claim".to_string()))?;

        // Extract issuer DID
        let issuer_did = Self::extract_issuer_did(credential)?;

        // TIER 3: Check credential-level cache first (fastest)
        let credential_cache_key = Self::credential_cache_key(package_type, &credential.id);
        if let Some(cached_result) = self.result_cache.get(&credential_cache_key) {
            let mut result = cached_result.clone();
            result.cached = true;
            result.verification_time_ns = start_time.elapsed().as_nanos() as u64;
            return Ok(result);
        }

        // TIER 1: Check or populate issuer cache
        let issuer_cache_key = Self::issuer_cache_key(&issuer_did);
        let issuer_data = if let Some(issuer_data) = self.issuer_cache.get(&issuer_cache_key) {
            // Cache hit - issuer data available
            let mut issuer_data = issuer_data.clone();
            issuer_data.update_usage();
            issuer_data
        } else {
            // Cache miss - extract and cache issuer data
            let public_key = credential.extract_public_key_from_did()
                .map_err(|e| LemmaError::Credential(e.to_string()))?;
            let issuer_data = IssuerVerificationData::new(public_key, issuer_did.clone());
            self.issuer_cache.insert(issuer_cache_key.clone(), issuer_data.clone());
            issuer_data
        };

        // TIER 2: Check or populate package cache
        let package_cache_key = Self::package_cache_key(package_type, &issuer_did);
        let package_data = if let Some(package_data) = self.package_cache.get(&package_cache_key) {
            // Cache hit - package data available
            let mut package_data = package_data.clone();
            package_data.update_usage();
            package_data
        } else {
            // Cache miss - create package data
            let package_data = PackageVerificationData::new(
                package_type.to_string(),
                Arc::new(self.bloom_cascade.clone()),
            );
            self.package_cache.insert(package_cache_key.clone(), package_data.clone());
            package_data
        };

        // Check if package exists first
        if !self.verification_packages.contains_key(package_type) {
            return Err(LemmaError::UnsupportedPackageType(package_type.to_string()));
        }

        // Perform optimized verification using cached data
        let mut result = self.verify_with_cached_data_by_type(
            credential,
            &issuer_data,
            &package_data,
            package_type,
        )?;

        // Add timing information
        result.verification_time_ns = start_time.elapsed().as_nanos() as u64;

        // Cache the result
        self.result_cache.insert(credential_cache_key, result.clone());

        Ok(result)
    }

    /// Optimized verification using cached issuer and package data
    fn verify_with_cached_data(
        &mut self,
        credential: &VerifiableCredential,
        issuer_data: &IssuerVerificationData,
        package_data: &PackageVerificationData,
        package: &Box<dyn VerificationPackage>,
    ) -> Result<VerificationResult> {
        // 1. Signature verification using cached public key (much faster)
        let signature_valid = match self.hsm_verifier.verify_signature_hsm(credential) {
            Ok(valid) => valid,
            Err(_) => {
                // Fallback to software verification using cached public key
                credential.verify_signature_with_key(&issuer_data.public_key)
                    .map_err(|e| LemmaError::Credential(e.to_string()))?
            }
        };

        // 2. Revocation checking using cached bloom filter
        let revocation_key = package.get_revocation_key(credential);
        let oprf_result = self.oprf_client.get_evaluation(&revocation_key)
            .map_err(|e| LemmaError::OPRF(e.to_string()))?;
        
        // Use cached bloom filter for faster revocation checking
        let (is_revoked, _level) = package_data.revocation_bloom.contains(&oprf_result.evaluation);

        // 3. Package-specific verification
        let mut result = package.verify_credential(credential)?;

        // 4. Combine results
        result.verified = result.verified && signature_valid && !is_revoked;
        result.cached = oprf_result.cached;

        Ok(result)
    }

    /// Optimized verification using cached issuer and package data (by package type)
    fn verify_with_cached_data_by_type(
        &mut self,
        credential: &VerifiableCredential,
        issuer_data: &IssuerVerificationData,
        package_data: &PackageVerificationData,
        package_type: &str,
    ) -> Result<VerificationResult> {
        // 1. Signature verification using cached public key (much faster)
        let signature_valid = match self.hsm_verifier.verify_signature_hsm(credential) {
            Ok(valid) => valid,
            Err(_) => {
                // Fallback to software verification using cached public key
                credential.verify_signature_with_key(&issuer_data.public_key)
                    .map_err(|e| LemmaError::Credential(e.to_string()))?
            }
        };

        // 2. Get verification package
        let package = self.verification_packages.get(package_type)
            .ok_or_else(|| LemmaError::UnsupportedPackageType(package_type.to_string()))?;

        // 3. Revocation checking using cached bloom filter
        let revocation_key = package.get_revocation_key(credential);
        let oprf_result = self.oprf_client.get_evaluation(&revocation_key)
            .map_err(|e| LemmaError::OPRF(e.to_string()))?;
        
        // Use cached bloom filter for faster revocation checking
        let (is_revoked, _level) = package_data.revocation_bloom.contains(&oprf_result.evaluation);

        // 4. Package-specific verification
        let mut result = package.verify_credential(credential)?;

        // 5. Combine results
        result.verified = result.verified && signature_valid && !is_revoked;
        result.cached = oprf_result.cached;

        Ok(result)
    }

    /// Batch verification for multiple credentials (optimized for same-issuer credentials)
    pub fn verify_batch(&mut self, credentials: &[VerifiableCredential]) -> Result<Vec<VerificationResult>> {
        let mut results = Vec::with_capacity(credentials.len());
        
        // Group credentials by issuer for batch optimization
        let mut by_issuer: HashMap<String, Vec<&VerifiableCredential>> = HashMap::new();
        
        for credential in credentials {
            let issuer_did = Self::extract_issuer_did(credential)?;
            by_issuer.entry(issuer_did).or_insert_with(Vec::new).push(credential);
        }
        
        // Process each issuer group
        for (issuer_did, issuer_credentials) in by_issuer {
            let issuer_results = self.verify_batch_same_issuer(&issuer_credentials, &issuer_did)?;
            results.extend(issuer_results);
        }
        
        Ok(results)
    }
    
    /// Batch verification for credentials from the same issuer (maximum optimization)
    fn verify_batch_same_issuer(&mut self, credentials: &[&VerifiableCredential], issuer_did: &str) -> Result<Vec<VerificationResult>> {
        let mut results = Vec::with_capacity(credentials.len());
        
        // Pre-populate issuer cache once for all credentials
        let issuer_cache_key = Self::issuer_cache_key(issuer_did);
        let issuer_data = if let Some(issuer_data) = self.issuer_cache.get(&issuer_cache_key) {
            issuer_data.clone()
        } else {
            // Extract issuer data from first credential
            let public_key = credentials[0].extract_public_key_from_did()
                .map_err(|e| LemmaError::Credential(e.to_string()))?;
            let issuer_data = IssuerVerificationData::new(public_key, issuer_did.to_string());
            self.issuer_cache.insert(issuer_cache_key.clone(), issuer_data.clone());
            issuer_data
        };
        
        // Process all credentials from this issuer
        for credential in credentials {
            let result = self.verify_with_issuer_data(credential, &issuer_data)?;
            results.push(result);
        }
        
        Ok(results)
    }
    
    /// Verify credential with pre-cached issuer data (fastest path)
    fn verify_with_issuer_data(&mut self, credential: &VerifiableCredential, issuer_data: &IssuerVerificationData) -> Result<VerificationResult> {
        // Get package type
        let package_type = credential.get_claim("packageType")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::VerificationFailed("Missing packageType claim".to_string()))?;

        // Check credential-level cache first
        let credential_cache_key = Self::credential_cache_key(package_type, &credential.id);
        if let Some(cached_result) = self.result_cache.get(&credential_cache_key) {
            let mut result = cached_result.clone();
            result.cached = true;
            return Ok(result);
        }

        // Get package cache
        let package_cache_key = Self::package_cache_key(package_type, &issuer_data.did_parsed);
        let package_data = if let Some(package_data) = self.package_cache.get(&package_cache_key) {
            package_data.clone()
        } else {
            let package_data = PackageVerificationData::new(
                package_type.to_string(),
                Arc::new(self.bloom_cascade.clone()),
            );
            self.package_cache.insert(package_cache_key.clone(), package_data.clone());
            package_data
        };

        // Check if package exists first
        if !self.verification_packages.contains_key(package_type) {
            return Err(LemmaError::UnsupportedPackageType(package_type.to_string()));
        }

        // Perform optimized verification
        let mut result = self.verify_with_cached_data_by_type(credential, issuer_data, &package_data, package_type)?;

        // Cache the result
        self.result_cache.insert(credential_cache_key, result.clone());

        Ok(result)
    }

    /// Add credential to batch processing queue
    pub fn add_to_batch(&mut self, credential: &VerifiableCredential) -> VerificationId {
        self.batch_processor.add_verification(credential)
    }
    
    /// Process pending batch if threshold is met
    pub fn process_batch_if_ready(&mut self) -> Result<Vec<VerificationResult>> {
        if self.batch_processor.should_process_batch() {
            self.process_current_batch()
        } else {
            Ok(Vec::new())
        }
    }
    
    /// Process all pending credentials in the batch
    fn process_current_batch(&mut self) -> Result<Vec<VerificationResult>> {
        let pending = self.batch_processor.pending_batch.clone();
        self.batch_processor.clear_batch();
        
        // Extract credentials for batch processing
        let credentials: Vec<VerifiableCredential> = pending.iter()
            .map(|pending| pending.credential.clone())
            .collect();
        
        // Process batch
        let results = self.verify_batch(&credentials)?;
        
        // Store results in batch processor
        for (pending_verification, result) in pending.iter().zip(results.iter()) {
            self.batch_processor.insert_result(pending_verification.id, result.clone());
        }
        
        Ok(results)
    }

    /// Get cache statistics for performance monitoring
    pub fn get_cache_stats(&self) -> MultiLevelCacheStats {
        MultiLevelCacheStats {
            issuer_cache_size: self.issuer_cache.len(),
            issuer_cache_capacity: MAX_ISSUER_CACHE_SIZE,
            package_cache_size: self.package_cache.len(),
            package_cache_capacity: MAX_PACKAGE_CACHE_SIZE,
            result_cache_size: self.result_cache.len(),
            result_cache_capacity: MAX_RESULT_CACHE_SIZE,
            pending_batch_size: self.batch_processor.get_pending_count(),
            batch_threshold: self.batch_processor.batch_threshold,
        }
    }

    /// Clear all caches (for testing or memory management)
    pub fn clear_all_caches(&mut self) {
        self.issuer_cache = LRUCache::new(MAX_ISSUER_CACHE_SIZE);
        self.package_cache = LRUCache::new(MAX_PACKAGE_CACHE_SIZE);
        self.result_cache = LRUCache::new(MAX_RESULT_CACHE_SIZE);
        self.batch_processor = BatchVerificationEngine::new(BATCH_THRESHOLD);
    }

    /// Optimized verification using pre-allocated buffers
    fn verify_with_buffers(
        &mut self,
        credential: &VerifiableCredential,
        package: &Box<dyn VerificationPackage>,
        _credential_buffer: &mut Vec<u8>,
        _result_buffer: &mut Vec<u8>,
        _message_buffer: &mut Vec<u8>,
    ) -> Result<VerificationResult> {
        Self::verify_with_buffers_static(
            credential,
            package,
            _credential_buffer,
            _result_buffer,
            _message_buffer,
            &mut self.oprf_client,
            &self.bloom_cascade,
        )
    }

    /// HSM-accelerated verification with fallback to software verification (by package type)
    fn verify_with_buffers_hsm_by_type(
        &mut self,
        credential: &VerifiableCredential,
        package_type: &str,
        _credential_buffer: &mut Vec<u8>,
        _result_buffer: &mut Vec<u8>,
        _message_buffer: &mut Vec<u8>,
    ) -> Result<VerificationResult> {
        // 1. Try HSM signature verification first
        let signature_valid = match self.hsm_verifier.verify_signature_hsm(credential) {
            Ok(valid) => {
                // HSM verification succeeded
                valid
            }
            Err(_) => {
                // HSM verification failed, fall back to software verification
                credential.verify_signature()
                    .map_err(|e| LemmaError::Credential(e.to_string()))?
            }
        };

        // 2. Get the package for revocation and specific verification
        let package = self.verification_packages.get(package_type)
            .ok_or_else(|| LemmaError::UnsupportedPackageType(package_type.to_string()))?;

        // 3. Check revocation (universal)
        let revocation_key = package.get_revocation_key(credential);
        let oprf_result = self.oprf_client.get_evaluation(&revocation_key)
            .map_err(|e| LemmaError::OPRF(e.to_string()))?;
        let (is_revoked, _level) = self.bloom_cascade.contains(&oprf_result.evaluation);

        // 4. Package-specific verification
        let mut result = package.verify_credential(credential)?;

        // 5. Combine results
        result.verified = result.verified && signature_valid && !is_revoked;
        result.cached = oprf_result.cached;

        Ok(result)
    }

    /// HSM-accelerated verification with fallback to software verification
    fn verify_with_buffers_hsm(
        &mut self,
        credential: &VerifiableCredential,
        package: &Box<dyn VerificationPackage>,
        _credential_buffer: &mut Vec<u8>,
        _result_buffer: &mut Vec<u8>,
        _message_buffer: &mut Vec<u8>,
    ) -> Result<VerificationResult> {
        // 1. Try HSM signature verification first
        let signature_valid = match self.hsm_verifier.verify_signature_hsm(credential) {
            Ok(valid) => {
                // HSM verification succeeded
                valid
            }
            Err(_) => {
                // HSM verification failed, fall back to software verification
                credential.verify_signature()
                    .map_err(|e| LemmaError::Credential(e.to_string()))?
            }
        };

        // 2. Check revocation (universal)
        let revocation_key = package.get_revocation_key(credential);
        let oprf_result = self.oprf_client.get_evaluation(&revocation_key)
            .map_err(|e| LemmaError::OPRF(e.to_string()))?;
        let (is_revoked, _level) = self.bloom_cascade.contains(&oprf_result.evaluation);

        // 3. Package-specific verification
        let mut result = package.verify_credential(credential)?;

        // 4. Combine results
        result.verified = result.verified && signature_valid && !is_revoked;
        result.cached = oprf_result.cached;

        Ok(result)
    }

    /// Static version of verify_with_buffers to avoid borrowing issues
    fn verify_with_buffers_static(
        credential: &VerifiableCredential,
        package: &Box<dyn VerificationPackage>,
        _credential_buffer: &mut Vec<u8>,
        _result_buffer: &mut Vec<u8>,
        _message_buffer: &mut Vec<u8>,
        oprf_client: &mut OPRFClient,
        bloom_cascade: &CascadedBloomFilter,
    ) -> Result<VerificationResult> {
        // 1. Verify credential signature (universal)
        let signature_valid = credential.verify_signature()
            .map_err(|e| LemmaError::Credential(e.to_string()))?;

        // 2. Check revocation (universal)
        let revocation_key = package.get_revocation_key(credential);
        let oprf_result = oprf_client.get_evaluation(&revocation_key)
            .map_err(|e| LemmaError::OPRF(e.to_string()))?;
        let (is_revoked, _level) = bloom_cascade.contains(&oprf_result.evaluation);

        // 3. Package-specific verification
        let mut result = package.verify_credential(credential)?;

        // 4. Combine results
        result.verified = result.verified && signature_valid && !is_revoked;
        result.cached = oprf_result.cached;

        Ok(result)
    }



    /// Optimized verification for batch processing with precomputed signature result
    fn verify_with_batch_buffers_simd(
        &mut self,
        credential: &VerifiableCredential,
        signature_valid: bool,
        _credential_buffer: &mut Vec<u8>,
        _result_buffer: &mut Vec<u8>,
        _message_buffer: &mut Vec<u8>,
    ) -> Result<VerificationResult> {
        // Get package type from credential
        let package_type = credential.get_claim("packageType")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::VerificationFailed("Missing packageType claim".to_string()))?;

        // Check cache first
        let cache_key = format!("{}:{}", package_type, credential.id);
        if let Some(cached_result) = self.result_cache.get(&cache_key) {
            let mut result = cached_result.clone();
            result.cached = true;
            return Ok(result);
        }

        // Get verification package
        let package = self.verification_packages.get(package_type)
            .ok_or_else(|| LemmaError::UnsupportedPackageType(package_type.to_string()))?;

        // 1. Signature verification already done via SIMD (passed as parameter)

        // 2. Check revocation (universal)
        let revocation_key = package.get_revocation_key(credential);
        let oprf_result = self.oprf_client.get_evaluation(&revocation_key)
            .map_err(|e| LemmaError::OPRF(e.to_string()))?;
        let (is_revoked, _level) = self.bloom_cascade.contains(&oprf_result.evaluation);

        // 3. Package-specific verification
        let mut result = package.verify_credential(credential)?;

        // 4. Combine results
        result.verified = result.verified && signature_valid && !is_revoked;
        result.cached = oprf_result.cached;

        // Cache result
        self.result_cache.insert(cache_key, result.clone());

        Ok(result)
    }

    /// Batch OPRF evaluation for multiple credentials (optimized)
    pub fn batch_oprf_evaluate(&mut self, credential_ids: &[String]) -> Result<Vec<OPRFResult>> {
        let mut results = Vec::with_capacity(credential_ids.len());
        
        // Process in optimal chunks
        const OPRF_BATCH_SIZE: usize = 16;
        
        for chunk in credential_ids.chunks(OPRF_BATCH_SIZE) {
            for credential_id in chunk {
                let oprf_result = self.oprf_client.get_evaluation(credential_id)
                    .map_err(|e| LemmaError::OPRF(e.to_string()))?;
                results.push(oprf_result);
            }
        }
        
        Ok(results)
    }

    /// Batch bloom filter checks (optimized)
    pub fn batch_bloom_check(&self, evaluations: &[&[u8]]) -> Result<Vec<(bool, u32)>> {
        // Use the cascaded bloom filter's batch operation if available
        let results = self.bloom_cascade.batch_contains(evaluations);
        // Convert usize to u32 for consistency
        Ok(results.into_iter().map(|(found, level)| (found, level as u32)).collect())
    }

    /// Add item to revocation list
    pub fn revoke(&mut self, package_type: &str, credential: &VerifiableCredential) -> Result<()> {
        let package = self.verification_packages.get(package_type)
            .ok_or_else(|| LemmaError::UnsupportedPackageType(package_type.to_string()))?;

        let revocation_key = package.get_revocation_key(credential);
        let oprf_result = self.oprf_client.get_evaluation(&revocation_key)
            .map_err(|e| LemmaError::OPRF(e.to_string()))?;

        self.bloom_cascade.add(&oprf_result.evaluation)
            .map_err(|e| LemmaError::Bloom(e.to_string()))?;

        // Clear cache for this credential
        let cache_key = format!("{}:{}", package_type, credential.id);
        self.result_cache.remove(&cache_key);

        Ok(())
    }

    /// Get verification statistics
    pub fn get_stats(&self) -> HashMap<String, serde_json::Value> {
        let mut stats = HashMap::new();
        
        stats.insert("registered_packages".to_string(), 
            serde_json::Value::Number(self.verification_packages.len().into()));
        
        stats.insert("cached_results".to_string(), 
            serde_json::Value::Number(self.result_cache.len().into()));
        
        stats.insert("oprf_cache_stats".to_string(), 
            serde_json::Value::Object(
                self.oprf_client.get_cache_stats().into_iter()
                    .map(|(k, v)| (k, serde_json::Value::Number(v.into())))
                    .collect()
            ));
        
        stats.insert("bloom_stats".to_string(), 
            serde_json::Value::Object(
                self.bloom_cascade.cascade_stats().into_iter()
                    .enumerate()
                    .map(|(i, stat)| (format!("level_{}", i), serde_json::json!({
                        "capacity": stat.capacity,
                        "items_added": stat.items_added,
                        "error_rate": stat.error_rate,
                        "memory_usage": stat.memory_usage
                    })))
                    .collect()
            ));
        
        stats
    }

    /// Clear all caches
    pub fn clear_caches(&mut self) {
        self.result_cache.clear();
        self.oprf_client.clear_cache();
    }

    /// Get list of registered package types
    pub fn get_package_types(&self) -> Vec<String> {
        self.verification_packages.keys().cloned().collect()
    }

    /// Get memory pool statistics
    pub fn get_pool_stats(&self) -> VerificationPoolStats {
        self.memory_pool.get_stats()
    }

    /// Register a verifying key with the HSM for hardware acceleration
    pub fn register_hsm_key(&mut self, issuer: &str, public_key: &[u8]) -> Result<()> {
        self.hsm_verifier.register_verifying_key(issuer, public_key)
    }

    /// Get HSM statistics
    pub fn get_hsm_stats(&self) -> HSMStats {
        self.hsm_verifier.get_stats()
    }

    /// Check if HSM hardware acceleration is available
    pub fn is_hsm_available(&self) -> bool {
        self.hsm_verifier.is_hardware_available()
    }

    /// Verify a batch of credentials using GPU acceleration
    fn verify_batch_gpu(&mut self, credentials: &[VerifiableCredential]) -> Result<Vec<VerificationResult>> {
        // Use GPU for signature verification
        let signature_results = self.gpu_verifier.verify_large_batch_gpu(credentials)?;
        
        let mut results = Vec::with_capacity(credentials.len());
        
        for (i, credential) in credentials.iter().enumerate() {
            let signature_valid = signature_results[i];
            
            // Get package for revocation and specific verification
            let package_type = credential.get_claim("packageType")
                .and_then(|v| v.as_str())
                .unwrap_or("identity");
            
            let package = self.verification_packages.get(package_type)
                .ok_or_else(|| LemmaError::UnsupportedPackageType(package_type.to_string()))?;
            
            // Check revocation (universal)
            let revocation_key = package.get_revocation_key(credential);
            let oprf_result = self.oprf_client.get_evaluation(&revocation_key)
                .map_err(|e| LemmaError::OPRF(e.to_string()))?;
            let (is_revoked, _level) = self.bloom_cascade.contains(&oprf_result.evaluation);
            
            // Package-specific verification
            let mut result = package.verify_credential(credential)?;
            
            // Combine results
            result.verified = result.verified && signature_valid && !is_revoked;
            result.cached = oprf_result.cached;
            
            results.push(result);
        }
        
        Ok(results)
    }

    /// **ZKP VERIFICATION METHODS** 
    /// These methods integrate ZKP verification with the existing microsecond-level optimization engine
    
    /// Verify a ZKP credential using the optimized verification engine
    pub fn verify_zkp_credential(&mut self, credential: &ZKPCredential) -> Result<VerificationResult> {
        // Convert ZKP credential to standard credential for compatibility with existing caching
        let standard_credential = credential.to_verifiable_credential()?;
        
        // Use existing caching infrastructure
        let package_type = "zkp_credential";
        let credential_cache_key = Self::credential_cache_key(package_type, &credential.id);
        
        // Check result cache first (leverages existing microsecond-level caching)
        if let Some(cached_result) = self.result_cache.get(&credential_cache_key) {
            let mut result = cached_result.clone();
            result.cached = true;
            return Ok(result);
        }
        
        // Verify the ZKP credential
        let mut result = self.zkp_verifier.verify_zkp_credential(credential)?;
        
        // Cache the result for future microsecond-level lookups
        self.result_cache.insert(credential_cache_key, result.clone());
        
        Ok(result)
    }
    
    /// Verify a single ZKP claim with caching
    pub fn verify_zkp_claim(&mut self, claim: &ZKPClaim) -> Result<bool> {
        self.zkp_verifier.verify_zkp_claim(claim)
    }
    
    /// Batch verify multiple ZKP credentials (leverages existing batch optimization)
    pub fn verify_zkp_credentials_batch(&mut self, credentials: &[ZKPCredential]) -> Result<Vec<VerificationResult>> {
        let mut results = Vec::with_capacity(credentials.len());
        
        for credential in credentials {
            let result = self.verify_zkp_credential(credential)?;
            results.push(result);
        }
        
        Ok(results)
    }
    
    /// Create a ZKP credential from claims (integrates with existing issuer system)
    pub fn create_zkp_credential_from_claims(&mut self, 
        issuer: String, 
        subject: String, 
        claims: HashMap<String, ZKPClaim>
    ) -> Result<ZKPCredential> {
        let mut credential = ZKPCredential::new(
            format!("zkp_{}", rand::random::<u64>()),
            issuer,
            subject,
        );
        
        // Add each ZKP claim
        for (key, claim) in claims {
            credential.add_zkp_claim(key, claim);
        }
        
        // Generate linking secret for unlinkability
        credential.generate_linking_secret();
        
        Ok(credential)
    }
    
    /// Selective disclosure of ZKP claims (preserves privacy while using existing caching)
    pub fn selective_disclose_zkp_credential(&mut self, 
        credential: &ZKPCredential, 
        claim_keys: &[String]
    ) -> Result<ZKPCredential> {
        let disclosed_credential = credential.selective_disclose(claim_keys)?;
        
        // Pre-warm the cache with the disclosed credential
        let _ = self.verify_zkp_credential(&disclosed_credential)?;
        
        Ok(disclosed_credential)
    }
    
    /// Verify ZKP credential against specific package type (leverages existing package system)
    pub fn verify_zkp_credential_with_package(&mut self, 
        credential: &ZKPCredential, 
        package_type: &str
    ) -> Result<VerificationResult> {
        // Convert to standard credential for package verification
        let standard_credential = credential.to_verifiable_credential()?;
        
        // Check if package exists and verify ZKP credential first
        let zkp_result = self.verify_zkp_credential(credential)?;
        
        if !zkp_result.verified {
            return Ok(zkp_result);
        }
        
        // Then verify against package requirements
        let package = self.verification_packages.get(package_type)
            .ok_or_else(|| LemmaError::UnsupportedPackageType(package_type.to_string()))?;
        let package_result = package.verify_credential(&standard_credential)?;
        
        // Combine results
        let mut combined_result = zkp_result;
        combined_result.verified = combined_result.verified && package_result.verified;
        combined_result.confidence = combined_result.confidence * package_result.confidence;
        
        // Merge metadata
        for (key, value) in package_result.metadata {
            combined_result.metadata.insert(format!("package_{}", key), value);
        }
        
        Ok(combined_result)
    }
    
    /// Get ZKP verification statistics
    pub fn get_zkp_stats(&self) -> &crate::zkp_claims::ZKPVerifierStats {
        self.zkp_verifier.get_stats()
    }
    
    /// Set ZKP optimization level (integrates with existing performance settings)
    pub fn set_zkp_optimization_level(&mut self, level: crate::zkp_claims::OptimizationLevel) {
        self.zkp_verifier.set_optimization_level(level);
    }
    
    /// Convert regular credential to ZKP credential (migration helper)
    pub fn convert_credential_to_zkp(&self, credential: &VerifiableCredential) -> Result<ZKPCredential> {
        let mut zkp_credential = ZKPCredential::new(
            credential.id.clone(),
            credential.issuer.clone(),
            credential.subject.clone(),
        );
        
        // Convert each claim to a ZKP claim
        for (key, value) in &credential.claims {
            match key.as_str() {
                "isHuman" => {
                    if let Some(is_human) = value.as_bool() {
                        if is_human {
                            let human_claim = crate::zkp_claims::zkp_helpers::create_human_claim(&[1, 2, 3, 4])?;
                            zkp_credential.add_zkp_claim(key.clone(), human_claim);
                        }
                    }
                }
                "packageType" => {
                    if let Some(package_type) = value.as_str() {
                        // Create a credential type ZKP claim
                        let claim_type = crate::zkp_claims::ZKPClaimType::CredentialType(package_type.to_string());
                        let proof_system = crate::zkp_claims::PLONKSystem { srs: vec![] };
                        let verification_key = proof_system.get_verification_key(&claim_type)?;
                        let proof = proof_system.generate_proof(&claim_type, package_type.as_bytes(), &[])?;
                        
                        let zkp_proof = crate::zkp_claims::ZKPClaimProof {
                            claim_type,
                            proof,
                            public_inputs: vec![],
                            verification_key,
                            proof_system: "plonk".to_string(),
                            created_at: crate::utils::current_timestamp(),
                            metadata: HashMap::new(),
                        };
                        
                        let zkp_claim = crate::zkp_claims::ZKPClaim::new(key.clone(), zkp_proof);
                        zkp_credential.add_zkp_claim(key.clone(), zkp_claim);
                    }
                }
                _ => {
                    // For other claims, create a custom ZKP claim
                    let claim_type = crate::zkp_claims::ZKPClaimType::Custom(key.clone());
                    let proof_system = crate::zkp_claims::PLONKSystem { srs: vec![] };
                    let verification_key = proof_system.get_verification_key(&claim_type)?;
                    let value_bytes = serde_json::to_string(value)
                        .map_err(|e| LemmaError::Serialization(e.to_string()))?;
                    let proof = proof_system.generate_proof(&claim_type, value_bytes.as_bytes(), &[])?;
                    
                    let zkp_proof = crate::zkp_claims::ZKPClaimProof {
                        claim_type,
                        proof,
                        public_inputs: vec![],
                        verification_key,
                        proof_system: "plonk".to_string(),
                        created_at: crate::utils::current_timestamp(),
                        metadata: HashMap::new(),
                    };
                    
                    let zkp_claim = crate::zkp_claims::ZKPClaim::new(key.clone(), zkp_proof);
                    zkp_credential.add_zkp_claim(key.clone(), zkp_claim);
                }
            }
        }
        
        zkp_credential.generate_linking_secret();
        Ok(zkp_credential)
    }

    /// Get GPU statistics
    pub fn get_gpu_stats(&self) -> GPUStats {
        self.gpu_verifier.get_stats()
    }

    /// Check if GPU hardware acceleration is available
    pub fn is_gpu_available(&self) -> bool {
        self.gpu_verifier.is_hardware_available()
    }

    /// Get optimal GPU batch size
    pub fn get_optimal_gpu_batch_size(&self) -> usize {
        self.gpu_verifier.get_optimal_batch_size()
    }
}

impl Default for LemmaCore {
    fn default() -> Self {
        Self::new().expect("Failed to create LemmaCore")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::packages::IdentityPackage;
    use crate::credentials::CredentialIssuer;
    use std::collections::HashMap;

    #[test]
    fn test_lemma_core_creation() {
        let core = LemmaCore::new();
        assert!(core.is_ok());
    }

    #[test]
    fn test_package_registration() {
        let mut core = LemmaCore::new().unwrap();
        let identity_package = IdentityPackage::new();
        
        core.register_package(identity_package);
        
        let package_types = core.get_package_types();
        assert!(package_types.contains(&"identity".to_string()));
    }

    #[test]
    fn test_verification_flow() {
        let mut core = LemmaCore::new().unwrap();
        let identity_package = IdentityPackage::new();
        core.register_package(identity_package);

        // Create test credential
        let issuer = CredentialIssuer::new();
        let mut claims = HashMap::new();
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
        claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));

        let credential = issuer.issue_credential(
            "test_subject".to_string(),
            claims,
            None,
        ).unwrap();

        // Verify credential
        let result = core.verify(&credential).unwrap();
        assert!(result.verified);
        assert_eq!(result.package_type, "identity");
        assert!(result.confidence > 0.0);
    }
} 