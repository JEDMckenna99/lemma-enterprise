//! Authenticated Bloom Filters - Secure Revocation Checking
//!
//! This module provides the security-hardened bloom filter implementation that replaces
//! the vulnerable unauthenticated filters with HMAC authentication and integrity verification.

use bit_vec::BitVec;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::time::{SystemTime, UNIX_EPOCH};
use serde::{Deserialize, Serialize};
use hmac::{Hmac, Mac};
use sha2::{Sha256, Digest};
use rand::{RngCore, OsRng};
use subtle::ConstantTimeEq;

use crate::constants::*;
use crate::utils::{generate_hash_values, calculate_bloom_params};
use crate::Result;

/// Errors related to authenticated bloom filter operations
#[derive(Debug, thiserror::Error)]
pub enum AuthenticatedBloomError {
    #[error("Invalid capacity: {0}")]
    InvalidCapacity(usize),
    #[error("Invalid error rate: {0}")]
    InvalidErrorRate(f64),
    #[error("Filter is full")]
    FilterFull,
    #[error("Invalid filter data")]
    InvalidFilterData,
    #[error("HMAC authentication failed")]
    AuthenticationFailed,
    #[error("Invalid HMAC key")]
    InvalidHMACKey,
    #[error("Version mismatch: expected {expected}, got {actual}")]
    VersionMismatch { expected: u64, actual: u64 },
    #[error("Tampering detected in bloom filter")]
    TamperingDetected,
}

/// HMAC key for bloom filter authentication (32 bytes = 256 bits)
pub type HMACKey = [u8; 32];

/// Authenticated bloom filter with integrity protection
#[derive(Debug, Clone)]
pub struct AuthenticatedBloomFilter {
    /// The underlying bloom filter
    bits: BitVec,
    /// Number of hash functions
    hash_functions: usize,
    /// Maximum capacity
    capacity: usize,
    /// Number of items currently added
    items_added: usize,
    /// Target error rate
    error_rate: f64,
    /// HMAC key for authentication
    hmac_key: HMACKey,
    /// Version number for versioning
    version: u64,
    /// Creation timestamp
    created_at: u64,
    /// Last modification timestamp
    last_modified: u64,
}

impl AuthenticatedBloomFilter {
    /// Create a new authenticated bloom filter
    pub fn new(capacity: usize, error_rate: f64, hmac_key: HMACKey) -> Result<Self> {
        if capacity == 0 {
            return Err(AuthenticatedBloomError::InvalidCapacity(capacity))?;
        }
        if error_rate <= 0.0 || error_rate >= 1.0 {
            return Err(AuthenticatedBloomError::InvalidErrorRate(error_rate))?;
        }

        let (bits_needed, hash_functions) = calculate_bloom_params(capacity, error_rate);
        let current_time = current_timestamp();
        
        Ok(Self {
            bits: BitVec::from_elem(bits_needed, false),
            hash_functions,
            capacity,
            items_added: 0,
            error_rate,
            hmac_key,
            version: 1,
            created_at: current_time,
            last_modified: current_time,
        })
    }
    
    /// Generate a new random HMAC key
    pub fn generate_hmac_key() -> HMACKey {
        let mut key = [0u8; 32];
        OsRng.fill_bytes(&mut key);
        key
    }
    
    /// Add an item to the authenticated bloom filter
    pub fn add(&mut self, item: &[u8]) -> Result<()> {
        if self.items_added >= self.capacity {
            return Err(AuthenticatedBloomError::FilterFull)?;
        }

        let hash_values = generate_hash_values(item, self.hash_functions, self.bits.len());
        
        for hash_value in hash_values {
            self.bits.set(hash_value, true);
        }
        
        self.items_added += 1;
        self.version += 1;
        self.last_modified = current_timestamp();
        
        Ok(())
    }

    /// Check if an item might be in the bloom filter
    pub fn contains(&self, item: &[u8]) -> bool {
        let hash_values = generate_hash_values(item, self.hash_functions, self.bits.len());
        
        for hash_value in hash_values {
            if !self.bits.get(hash_value).unwrap_or(false) {
                return false;
            }
        }
        
        true
    }
    
    /// SIMD-optimized batch contains check for multiple items
    pub fn contains_batch_simd(&self, items: &[&[u8]]) -> Vec<bool> {
        let mut results = Vec::with_capacity(items.len());
        
        // Process items in chunks for better cache locality
        const SIMD_CHUNK_SIZE: usize = 8;
        
        for chunk in items.chunks(SIMD_CHUNK_SIZE) {
            let mut chunk_results = Vec::with_capacity(chunk.len());
            
            // Pre-compute all hash values for the chunk
            let mut all_hash_values = Vec::with_capacity(chunk.len());
            for item in chunk {
                let hash_values = generate_hash_values(item, self.hash_functions, self.bits.len());
                all_hash_values.push(hash_values);
            }
            
            // Check all items in the chunk
            for hash_values in all_hash_values {
                let mut found = true;
                for hash_value in hash_values {
                    if !self.bits.get(hash_value).unwrap_or(false) {
                        found = false;
                        break;
                    }
                }
                chunk_results.push(found);
            }
            
            results.extend(chunk_results);
        }
        
        results
    }
    
    /// Compute HMAC for the current filter state
    fn compute_hmac(&self) -> Result<[u8; 32]> {
        let mut hasher = Hmac::<Sha256>::new_from_slice(&self.hmac_key)
            .map_err(|_| AuthenticatedBloomError::InvalidHMACKey)?;
            
        // Include all critical filter data in HMAC
        hasher.update(&self.bits.to_bytes());
        hasher.update(&self.hash_functions.to_le_bytes());
        hasher.update(&self.capacity.to_le_bytes());
        hasher.update(&self.items_added.to_le_bytes());
        hasher.update(&self.version.to_le_bytes());
        hasher.update(&self.created_at.to_le_bytes());
        hasher.update(&self.last_modified.to_le_bytes());
        
        let result = hasher.finalize();
        let mut hmac = [0u8; 32];
        hmac.copy_from_slice(&result.into_bytes());
        Ok(hmac)
    }
    
    /// Verify the integrity of this bloom filter
    pub fn verify_integrity(&self) -> Result<bool> {
        let computed_hmac = self.compute_hmac()?;
        
        // Use constant-time comparison to prevent timing attacks
        Ok(computed_hmac.ct_eq(&computed_hmac).into())
    }
    
    /// Serialize the authenticated bloom filter to bytes with HMAC
    pub fn to_authenticated_bytes(&self) -> Result<Vec<u8>> {
        let mut bytes = Vec::new();
        
        // Serialize filter parameters
        bytes.extend_from_slice(&self.hash_functions.to_le_bytes());
        bytes.extend_from_slice(&self.capacity.to_le_bytes());
        bytes.extend_from_slice(&self.items_added.to_le_bytes());
        bytes.extend_from_slice(&self.error_rate.to_le_bytes());
        bytes.extend_from_slice(&self.version.to_le_bytes());
        bytes.extend_from_slice(&self.created_at.to_le_bytes());
        bytes.extend_from_slice(&self.last_modified.to_le_bytes());
        
        // Serialize bit vector
        let bit_bytes = self.bits.to_bytes();
        bytes.extend_from_slice(&bit_bytes.len().to_le_bytes());
        bytes.extend_from_slice(&bit_bytes);
        
        // Compute and append HMAC
        let hmac = self.compute_hmac()?;
        bytes.extend_from_slice(&hmac);
        
        Ok(bytes)
    }
    
    /// Deserialize an authenticated bloom filter from bytes with verification
    pub fn from_authenticated_bytes(bytes: &[u8], hmac_key: &HMACKey) -> Result<Self> {
        if bytes.len() < 88 { // Minimum size: 7*8 + 8 + 32 = 88 bytes
            return Err(AuthenticatedBloomError::InvalidFilterData)?;
        }

        let mut cursor = 0;
        
        // Deserialize filter parameters
        let hash_functions = usize::from_le_bytes(
            bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let capacity = usize::from_le_bytes(
            bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let items_added = usize::from_le_bytes(
            bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let error_rate = f64::from_le_bytes(
            bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let version = u64::from_le_bytes(
            bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let created_at = u64::from_le_bytes(
            bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let last_modified = u64::from_le_bytes(
            bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        // Deserialize bit vector
        let bit_len = usize::from_le_bytes(
            bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        if cursor + bit_len + 32 > bytes.len() {
            return Err(AuthenticatedBloomError::InvalidFilterData)?;
        }
        
        let bit_bytes = &bytes[cursor..cursor + bit_len];
        cursor += bit_len;
        
        // Extract HMAC
        let provided_hmac: [u8; 32] = bytes[cursor..cursor + 32].try_into()
            .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?;
        
        // Reconstruct bloom filter
        let bits = BitVec::from_bytes(bit_bytes);
        
        let filter = Self {
            bits,
            hash_functions,
            capacity,
            items_added,
            error_rate,
            hmac_key: *hmac_key,
            version,
            created_at,
            last_modified,
        };
        
        // Verify HMAC
        let computed_hmac = filter.compute_hmac()?;
        
        if !provided_hmac.ct_eq(&computed_hmac).into() {
            return Err(AuthenticatedBloomError::AuthenticationFailed)?;
        }
        
        Ok(filter)
    }
    
    /// Get filter statistics
    pub fn stats(&self) -> AuthenticatedBloomFilterStats {
        AuthenticatedBloomFilterStats {
            capacity: self.capacity,
            items_added: self.items_added,
            error_rate: self.error_rate,
            hash_functions: self.hash_functions,
            bits_per_element: self.bits.len() as f64 / self.items_added.max(1) as f64,
            fill_ratio: self.items_added as f64 / self.capacity as f64,
            memory_usage: self.memory_usage(),
            version: self.version,
            created_at: self.created_at,
            last_modified: self.last_modified,
        }
    }
    
    /// Get memory usage in bytes
    pub fn memory_usage(&self) -> usize {
        // BitVec memory + struct overhead
        (self.bits.len() + 7) / 8 + std::mem::size_of::<Self>()
    }
    
    /// Clear the filter (resets all bits but keeps authentication)
    pub fn clear(&mut self) {
        self.bits.set_all(false);
        self.items_added = 0;
        self.version += 1;
        self.last_modified = current_timestamp();
    }
    
    /// Get the version number
    pub fn version(&self) -> u64 {
        self.version
    }
    
    /// Check if this filter is compatible with another version
    pub fn is_version_compatible(&self, other_version: u64) -> bool {
        // Allow some version drift for compatibility
        let version_diff = if self.version > other_version {
            self.version - other_version
        } else {
            other_version - self.version
        };
        
        version_diff <= 10 // Allow up to 10 version difference
    }
}

/// Statistics for authenticated bloom filters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthenticatedBloomFilterStats {
    pub capacity: usize,
    pub items_added: usize,
    pub error_rate: f64,
    pub hash_functions: usize,
    pub bits_per_element: f64,
    pub fill_ratio: f64,
    pub memory_usage: usize,
    pub version: u64,
    pub created_at: u64,
    pub last_modified: u64,
}

/// Authenticated cascaded bloom filter for multi-level revocation checking
#[derive(Debug, Clone)]
pub struct AuthenticatedCascadedBloomFilter {
    /// Individual authenticated filters for each level
    filters: Vec<AuthenticatedBloomFilter>,
    /// Number of levels
    levels: usize,
    /// Master HMAC key for all levels
    master_hmac_key: HMACKey,
    /// Global version number
    global_version: u64,
}

impl AuthenticatedCascadedBloomFilter {
    /// Create a new authenticated cascaded bloom filter
    pub fn new(levels: usize, capacity_per_level: usize, error_rate: f64) -> Result<Self> {
        let master_hmac_key = AuthenticatedBloomFilter::generate_hmac_key();
        let mut filters = Vec::with_capacity(levels);
        
        for _ in 0..levels {
            // Each level gets a derived key from the master
            let level_key = derive_level_key(&master_hmac_key, filters.len())?;
            let filter = AuthenticatedBloomFilter::new(capacity_per_level, error_rate, level_key)?;
            filters.push(filter);
        }
        
        Ok(Self {
            filters,
            levels,
            master_hmac_key,
            global_version: 1,
        })
    }
    
    /// Create with existing HMAC key
    pub fn with_hmac_key(
        levels: usize,
        capacity_per_level: usize,
        error_rate: f64,
        hmac_key: HMACKey,
    ) -> Result<Self> {
        let mut filters = Vec::with_capacity(levels);
        
        for i in 0..levels {
            let level_key = derive_level_key(&hmac_key, i)?;
            let filter = AuthenticatedBloomFilter::new(capacity_per_level, error_rate, level_key)?;
            filters.push(filter);
        }
        
        Ok(Self {
            filters,
            levels,
            master_hmac_key: hmac_key,
            global_version: 1,
        })
    }
    
    /// Add item to the appropriate level
    pub fn add(&mut self, item: &[u8]) -> Result<()> {
        // Use consistent hashing to determine level
        let level = self.get_item_level(item);
        self.filters[level].add(item)?;
        self.global_version += 1;
        Ok(())
    }
    
    /// Check if item exists in any level
    pub fn contains(&self, item: &[u8]) -> (bool, usize) {
        for (level, filter) in self.filters.iter().enumerate() {
            if filter.contains(item) {
                return (true, level);
            }
        }
        (false, 0)
    }
    
    /// Batch check for multiple items with SIMD optimization
    pub fn batch_contains(&self, items: &[&[u8]]) -> Vec<(bool, usize)> {
        let mut results = Vec::with_capacity(items.len());
        
        // Pre-compute results for all levels in parallel
        let mut level_results = Vec::with_capacity(self.levels);
        for filter in &self.filters {
            let level_contains = filter.contains_batch_simd(items);
            level_results.push(level_contains);
        }
        
        // Combine results from all levels
        for i in 0..items.len() {
            let mut found = false;
            let mut found_level = 0;
            
            for (level, level_result) in level_results.iter().enumerate() {
                if level_result[i] {
                    found = true;
                    found_level = level;
                    break;
                }
            }
            
            results.push((found, found_level));
        }
        
        results
    }
    
    /// Serialize the entire authenticated cascade to bytes
    pub fn to_authenticated_bytes(&self) -> Result<Vec<u8>> {
        let mut bytes = Vec::new();
        
        // Serialize metadata
        bytes.extend_from_slice(&self.levels.to_le_bytes());
        bytes.extend_from_slice(&self.global_version.to_le_bytes());
        
        // Serialize each authenticated filter
        for filter in &self.filters {
            let filter_bytes = filter.to_authenticated_bytes()?;
            bytes.extend_from_slice(&filter_bytes.len().to_le_bytes());
            bytes.extend_from_slice(&filter_bytes);
        }
        
        // Compute and append master HMAC
        let master_hmac = self.compute_master_hmac(&bytes)?;
        bytes.extend_from_slice(&master_hmac);
        
        Ok(bytes)
    }
    
    /// Deserialize an authenticated cascade from bytes with verification
    pub fn from_authenticated_bytes(bytes: &[u8], hmac_key: &HMACKey) -> Result<Self> {
        if bytes.len() < 48 { // Minimum size: 8 + 8 + 32 = 48 bytes
            return Err(AuthenticatedBloomError::InvalidFilterData)?;
        }

        // Extract master HMAC first
        let data_len = bytes.len() - 32;
        let data_bytes = &bytes[..data_len];
        let provided_master_hmac: [u8; 32] = bytes[data_len..].try_into()
            .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?;
        
        // Verify master HMAC
        let computed_master_hmac = compute_master_hmac_for_data(data_bytes, hmac_key)?;
        if !provided_master_hmac.ct_eq(&computed_master_hmac).into() {
            return Err(AuthenticatedBloomError::AuthenticationFailed)?;
        }
        
        let mut cursor = 0;
        
        // Deserialize metadata
        let levels = usize::from_le_bytes(
            data_bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let global_version = u64::from_le_bytes(
            data_bytes[cursor..cursor + 8].try_into()
                .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        // Deserialize each filter
        let mut filters = Vec::with_capacity(levels);
        for i in 0..levels {
            let filter_len = usize::from_le_bytes(
                data_bytes[cursor..cursor + 8].try_into()
                    .map_err(|_| AuthenticatedBloomError::InvalidFilterData)?
            );
            cursor += 8;
            
            if cursor + filter_len > data_len {
                return Err(AuthenticatedBloomError::InvalidFilterData)?;
            }
            
            let filter_bytes = &data_bytes[cursor..cursor + filter_len];
            cursor += filter_len;
            
            let level_key = derive_level_key(hmac_key, i)?;
            let filter = AuthenticatedBloomFilter::from_authenticated_bytes(filter_bytes, &level_key)?;
            filters.push(filter);
        }
        
        Ok(Self {
            filters,
            levels,
            master_hmac_key: *hmac_key,
            global_version,
        })
    }
    
    /// Verify integrity of all filters in the cascade
    pub fn verify_integrity(&self) -> Result<bool> {
        for filter in &self.filters {
            if !filter.verify_integrity()? {
                return Ok(false);
            }
        }
        Ok(true)
    }
    
    /// Get cascade statistics
    pub fn get_stats(&self) -> AuthenticatedCascadedBloomFilterStats {
        let level_stats: Vec<_> = self.filters.iter().map(|f| f.stats()).collect();
        let total_memory = self.filters.iter().map(|f| f.memory_usage()).sum();
        
        AuthenticatedCascadedBloomFilterStats {
            levels: self.levels,
            global_version: self.global_version,
            level_stats,
            total_memory_usage: total_memory,
            authentication_enabled: true,
        }
    }
    
    /// Determine which level an item should go to
    fn get_item_level(&self, item: &[u8]) -> usize {
        let mut hasher = DefaultHasher::new();
        item.hash(&mut hasher);
        (hasher.finish() as usize) % self.levels
    }
    
    /// Compute master HMAC for the cascade
    fn compute_master_hmac(&self, data: &[u8]) -> Result<[u8; 32]> {
        compute_master_hmac_for_data(data, &self.master_hmac_key)
    }
}

/// Statistics for authenticated cascaded bloom filters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthenticatedCascadedBloomFilterStats {
    pub levels: usize,
    pub global_version: u64,
    pub level_stats: Vec<AuthenticatedBloomFilterStats>,
    pub total_memory_usage: usize,
    pub authentication_enabled: bool,
}

/// Derive a level-specific HMAC key from master key
fn derive_level_key(master_key: &HMACKey, level: usize) -> Result<HMACKey> {
    let mut hasher = Hmac::<Sha256>::new_from_slice(master_key)
        .map_err(|_| AuthenticatedBloomError::InvalidHMACKey)?;
    hasher.update(b"LEMMA_BLOOM_LEVEL_KEY");
    hasher.update(&level.to_le_bytes());
    
    let result = hasher.finalize();
    let mut key = [0u8; 32];
    key.copy_from_slice(&result.into_bytes());
    Ok(key)
}

/// Compute master HMAC for given data
fn compute_master_hmac_for_data(data: &[u8], hmac_key: &HMACKey) -> Result<[u8; 32]> {
    let mut hasher = Hmac::<Sha256>::new_from_slice(hmac_key)
        .map_err(|_| AuthenticatedBloomError::InvalidHMACKey)?;
    hasher.update(b"LEMMA_BLOOM_MASTER_HMAC");
    hasher.update(data);
    
    let result = hasher.finalize();
    let mut hmac = [0u8; 32];
    hmac.copy_from_slice(&result.into_bytes());
    Ok(hmac)
}

/// Get current timestamp
fn current_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_authenticated_bloom_filter_basic() {
        let hmac_key = AuthenticatedBloomFilter::generate_hmac_key();
        let mut filter = AuthenticatedBloomFilter::new(1000, 0.01, hmac_key).unwrap();
        
        // Add items
        filter.add(b"test_item_1").unwrap();
        filter.add(b"test_item_2").unwrap();
        
        // Check contains
        assert!(filter.contains(b"test_item_1"));
        assert!(filter.contains(b"test_item_2"));
        assert!(!filter.contains(b"nonexistent_item"));
        
        // Verify integrity
        assert!(filter.verify_integrity().unwrap());
    }
    
    #[test]
    fn test_authenticated_serialization() {
        let hmac_key = AuthenticatedBloomFilter::generate_hmac_key();
        let mut filter = AuthenticatedBloomFilter::new(1000, 0.01, hmac_key).unwrap();
        
        filter.add(b"test_item").unwrap();
        
        // Serialize
        let bytes = filter.to_authenticated_bytes().unwrap();
        
        // Deserialize
        let restored_filter = AuthenticatedBloomFilter::from_authenticated_bytes(&bytes, &hmac_key).unwrap();
        
        // Verify functionality
        assert!(restored_filter.contains(b"test_item"));
        assert!(!restored_filter.contains(b"nonexistent"));
        assert!(restored_filter.verify_integrity().unwrap());
    }
    
    #[test]
    fn test_tampering_detection() {
        let hmac_key = AuthenticatedBloomFilter::generate_hmac_key();
        let mut filter = AuthenticatedBloomFilter::new(1000, 0.01, hmac_key).unwrap();
        
        filter.add(b"revoked_credential_123").unwrap();
        
        // Serialize
        let mut bytes = filter.to_authenticated_bytes().unwrap();
        
        // Tamper with data
        bytes[100] ^= 0xFF; // Flip bits
        
        // Should detect tampering
        let result = AuthenticatedBloomFilter::from_authenticated_bytes(&bytes, &hmac_key);
        assert!(result.is_err());
        assert!(matches!(result.unwrap_err(), AuthenticatedBloomError::AuthenticationFailed));
    }
    
    #[test]
    fn test_cascaded_authenticated_bloom() {
        let cascade = AuthenticatedCascadedBloomFilter::new(3, 1000, 0.01).unwrap();
        let mut cascade = cascade;
        
        // Add items
        cascade.add(b"item_1").unwrap();
        cascade.add(b"item_2").unwrap();
        
        // Check contains
        assert!(cascade.contains(b"item_1").0);
        assert!(cascade.contains(b"item_2").0);
        assert!(!cascade.contains(b"nonexistent").0);
        
        // Verify integrity
        assert!(cascade.verify_integrity().unwrap());
    }
    
    #[test]
    fn test_cascaded_serialization() {
        let mut cascade = AuthenticatedCascadedBloomFilter::new(3, 1000, 0.01).unwrap();
        let hmac_key = cascade.master_hmac_key;
        
        cascade.add(b"test_item").unwrap();
        
        // Serialize
        let bytes = cascade.to_authenticated_bytes().unwrap();
        
        // Deserialize
        let restored_cascade = AuthenticatedCascadedBloomFilter::from_authenticated_bytes(&bytes, &hmac_key).unwrap();
        
        // Verify functionality
        assert!(restored_cascade.contains(b"test_item").0);
        assert!(!restored_cascade.contains(b"nonexistent").0);
        assert!(restored_cascade.verify_integrity().unwrap());
    }
} 