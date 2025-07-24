//! Utility functions for cryptographic operations

use std::collections::HashMap;
use sha2::{Sha256, Digest};
use blake3::Hasher;
use curve25519_dalek::ristretto::RistrettoPoint;
use curve25519_dalek::scalar::Scalar;

use crate::constants::*;
use crate::Result;

/// Hash a credential ID to a point on the curve
pub fn hash_to_point(credential_id: &str) -> RistrettoPoint {
    let mut hasher = Sha256::new();
    hasher.update(credential_id.as_bytes());
    let hash = hasher.finalize();
    
    // Convert to 64-byte array for uniform bytes
    let mut uniform_bytes = [0u8; 64];
    for (i, &byte) in hash.iter().enumerate() {
        uniform_bytes[i] = byte;
        if i < 32 {
            uniform_bytes[i + 32] = byte;
        }
    }
    
    RistrettoPoint::from_uniform_bytes(&uniform_bytes)
}

/// Generate secure random bytes
pub fn secure_random_bytes(size: usize) -> Vec<u8> {
    use rand::RngCore;
    let mut rng = rand::thread_rng();
    let mut bytes = vec![0u8; size];
    rng.fill_bytes(&mut bytes);
    bytes
}

/// Generate hash values for bloom filter
pub fn generate_hash_values(item: &[u8], hash_functions: usize, bit_size: usize) -> Vec<usize> {
    let mut values = Vec::new();
    let mut hasher = blake3::Hasher::new();
    
    for i in 0..hash_functions {
        hasher.update(item);
        hasher.update(&(i as u32).to_le_bytes());
        let hash = hasher.finalize();
        
        let mut hash_bytes = [0u8; 8];
        hash_bytes.copy_from_slice(&hash.as_bytes()[..8]);
        let hash_val = u64::from_le_bytes(hash_bytes) as usize;
        
        values.push(hash_val % bit_size);
        hasher.reset();
    }
    
    values
}

/// Calculate optimal bloom filter parameters
pub fn calculate_bloom_params(capacity: usize, error_rate: f64) -> (usize, usize) {
    let ln2 = std::f64::consts::LN_2;
    let bits_needed = (-(capacity as f64) * error_rate.ln() / (ln2 * ln2)).ceil() as usize;
    let hash_functions = ((bits_needed as f64 / capacity as f64) * ln2).ceil() as usize;
    
    (bits_needed, hash_functions)
}

/// Get current timestamp in seconds
pub fn current_timestamp() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs()
}

/// Convert bytes to hex string
pub fn bytes_to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

/// Convert hex string to bytes
pub fn hex_to_bytes(hex: &str) -> Result<Vec<u8>> {
    if hex.len() % 2 != 0 {
        return Err(crate::LemmaError::Crypto("Invalid hex string length".to_string()));
    }
    
    let mut bytes = Vec::new();
    for i in (0..hex.len()).step_by(2) {
        let byte_str = &hex[i..i+2];
        let byte = u8::from_str_radix(byte_str, 16)
            .map_err(|_| crate::LemmaError::Crypto("Invalid hex string".to_string()))?;
        bytes.push(byte);
    }
    
    Ok(bytes)
}

/// Simple LRU cache implementation
pub struct LRUCache<K, V> {
    capacity: usize,
    data: HashMap<K, (V, u64)>,
    access_counter: u64,
}

impl<K, V> LRUCache<K, V> 
where
    K: Clone + Eq + std::hash::Hash,
    V: Clone,
{
    pub fn new(capacity: usize) -> Self {
        Self {
            capacity,
            data: HashMap::new(),
            access_counter: 0,
        }
    }
    
    pub fn get(&mut self, key: &K) -> Option<V> {
        if let Some((value, timestamp)) = self.data.get_mut(key) {
            self.access_counter += 1;
            *timestamp = self.access_counter;
            Some(value.clone())
        } else {
            None
        }
    }
    
    pub fn put(&mut self, key: K, value: V) {
        self.access_counter += 1;
        
        if self.data.len() >= self.capacity && !self.data.contains_key(&key) {
            // Remove least recently used item
            let mut oldest_key = None;
            let mut oldest_timestamp = u64::MAX;
            
            for (k, (_, timestamp)) in &self.data {
                if *timestamp < oldest_timestamp {
                    oldest_timestamp = *timestamp;
                    oldest_key = Some(k.clone());
                }
            }
            
            if let Some(key_to_remove) = oldest_key {
                self.data.remove(&key_to_remove);
            }
        }
        
        self.data.insert(key, (value, self.access_counter));
    }
    
    pub fn clear(&mut self) {
        self.data.clear();
        self.access_counter = 0;
    }
    
    pub fn len(&self) -> usize {
        self.data.len()
    }
    
    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }
    
    /// Clean up expired entries (if timestamps are used for TTL)
    pub fn cleanup_expired(&mut self, ttl_seconds: u64) {
        let now = current_timestamp();
        
        self.data.retain(|_, (_, timestamp)| now - *timestamp < ttl_seconds);
    }
}

/// Timing-safe comparison of byte arrays
pub fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    
    let mut result = 0u8;
    for (x, y) in a.iter().zip(b.iter()) {
        result |= x ^ y;
    }
    
    result == 0
}

/// Generate a random DID
pub fn generate_did() -> String {
    let random_bytes = secure_random_bytes(16);
    let hex = bytes_to_hex(&random_bytes);
    format!("did:lemma:{}", hex)
}

/// Validate DID format
pub fn validate_did(did: &str) -> bool {
    did.starts_with("did:lemma:") && did.len() == 42 // "did:lemma:" + 32 hex chars
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hash_to_point() {
        let point1 = hash_to_point("test_credential_1");
        let point2 = hash_to_point("test_credential_2");
        let point3 = hash_to_point("test_credential_1"); // Same input
        
        assert_ne!(point1, point2); // Different inputs produce different points
        assert_eq!(point1, point3); // Same input produces same point
    }

    #[test]
    fn test_generate_hash_values() {
        let item = b"test_item";
        let hash_values = generate_hash_values(item, 3, 1000);
        
        assert_eq!(hash_values.len(), 3);
        assert!(hash_values.iter().all(|&v| v < 1000));
        
        // Same input should produce same values
        let hash_values2 = generate_hash_values(item, 3, 1000);
        assert_eq!(hash_values, hash_values2);
    }

    #[test]
    fn test_calculate_bloom_params() {
        let (bits, hash_funcs) = calculate_bloom_params(1000, 0.01);
        assert!(bits > 0);
        assert!(hash_funcs > 0);
        assert!(hash_funcs < 20); // Reasonable number of hash functions
    }

    #[test]
    fn test_hex_conversion() {
        let bytes = vec![0xde, 0xad, 0xbe, 0xef];
        let hex = bytes_to_hex(&bytes);
        assert_eq!(hex, "deadbeef");
        
        let decoded = hex_to_bytes(&hex).unwrap();
        assert_eq!(bytes, decoded);
    }

    #[test]
    fn test_lru_cache() {
        let mut cache = LRUCache::new(2);
        
        // Add items
        cache.put("key1", "value1");
        cache.put("key2", "value2");
        
        // Both should be retrievable
        assert_eq!(cache.get(&"key1"), Some("value1"));
        assert_eq!(cache.get(&"key2"), Some("value2"));
        
        // Add third item (should evict least recently used)
        cache.put("key3", "value3");
        
        // key1 should be evicted (was accessed before key2)
        assert_eq!(cache.get(&"key1"), None);
        assert_eq!(cache.get(&"key2"), Some("value2"));
        assert_eq!(cache.get(&"key3"), Some("value3"));
    }

    #[test]
    fn test_constant_time_eq() {
        let a = b"hello";
        let b = b"hello";
        let c = b"world";
        
        assert!(constant_time_eq(a, b));
        assert!(!constant_time_eq(a, c));
        assert!(!constant_time_eq(a, b"hell")); // Different lengths
    }

    #[test]
    fn test_did_generation() {
        let did1 = generate_did();
        let did2 = generate_did();
        
        assert_ne!(did1, did2);
        assert!(validate_did(&did1));
        assert!(validate_did(&did2));
        
        // Test invalid DIDs
        assert!(!validate_did("invalid"));
        assert!(!validate_did("did:other:123"));
    }
} 