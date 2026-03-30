//! Optimized Advanced Wallet with Caching
//! Addresses performance concerns with intelligent caching

use crate::advanced_wallet::{AdvancedWalletCrypto, KYCTuple, WalletEnvelope};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use blake3;
use hmac::{Hmac, Mac};
use sha2::Sha256;
use hkdf::Hkdf;

type HmacSha256 = Hmac<Sha256>;

#[derive(Debug, Clone)]
pub struct OptimizedWalletCrypto {
    core: AdvancedWalletCrypto,
    
    // Performance caches
    rid_cache: Arc<Mutex<HashMap<Vec<u8>, [u8; 32]>>>,      // KYC -> RID cache
    tag_cache: Arc<Mutex<HashMap<String, [u8; 32]>>>,       // (RID,RP) -> tag cache  
    key_cache: Arc<Mutex<HashMap<String, [u8; 32]>>>,       // RP -> child_key cache
    vid_cache: Arc<Mutex<HashMap<[u8; 32], [u8; 32]>>>,     // RID -> VID cache
}

impl OptimizedWalletCrypto {
    pub fn new(core: AdvancedWalletCrypto) -> Self {
        Self {
            core,
            rid_cache: Arc::new(Mutex::new(HashMap::new())),
            tag_cache: Arc::new(Mutex::new(HashMap::new())),
            key_cache: Arc::new(Mutex::new(HashMap::new())),
            vid_cache: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Cached RID derivation (expensive operation cached after first use)
    pub fn derive_rid_cached(&self, kyc_tuple_cbor: &[u8]) -> [u8; 32] {
        // Check cache first
        {
            let cache = self.rid_cache.lock().unwrap();
            if let Some(&cached_rid) = cache.get(kyc_tuple_cbor) {
                return cached_rid;
            }
        }
        
        // Compute RID if not cached
        let rid = self.core.derive_rid(kyc_tuple_cbor);
        
        // Cache the result
        {
            let mut cache = self.rid_cache.lock().unwrap();
            cache.insert(kyc_tuple_cbor.to_vec(), rid);
        }
        
        rid
    }

    /// Cached pairwise tag generation (per-RP, cached after first use)
    pub fn generate_pairwise_tag_cached(&self, rid: &[u8; 32], rp_id: &str) -> Result<[u8; 32], String> {
        let cache_key = format!("{}:{}", hex::encode(rid), rp_id);
        
        // Check cache first
        {
            let cache = self.tag_cache.lock().unwrap();
            if let Some(&cached_tag) = cache.get(&cache_key) {
                return Ok(cached_tag);
            }
        }
        
        // Compute tag if not cached
        let tag = self.core.generate_pairwise_tag(rid, rp_id)?;
        
        // Cache the result
        {
            let mut cache = self.tag_cache.lock().unwrap();
            cache.insert(cache_key, tag);
        }
        
        Ok(tag)
    }

    /// Cached per-RP key derivation (expensive HKDF cached per RP)
    pub fn derive_rp_child_key_cached(&self, sk_master: &[u8; 32], rp_id: &str) -> Result<[u8; 32], String> {
        // Check cache first (most RPs will be accessed repeatedly)
        {
            let cache = self.key_cache.lock().unwrap();
            if let Some(&cached_key) = cache.get(rp_id) {
                return Ok(cached_key);
            }
        }
        
        // Compute child key if not cached (expensive operation)
        let child_key = AdvancedWalletCrypto::derive_rp_child_key(sk_master, rp_id)?;
        
        // Cache the result (permanent for this wallet session)
        {
            let mut cache = self.key_cache.lock().unwrap();
            cache.insert(rp_id.to_string(), child_key);
        }
        
        Ok(child_key)
    }

    /// Cached VID computation
    pub fn derive_vid_cached(&self, rid: &[u8; 32]) -> [u8; 32] {
        // Check cache first
        {
            let cache = self.vid_cache.lock().unwrap();
            if let Some(&cached_vid) = cache.get(rid) {
                return cached_vid;
            }
        }
        
        // Compute VID if not cached
        let vid = self.core.derive_vid(rid);
        
        // Cache the result
        {
            let mut cache = self.vid_cache.lock().unwrap();
            cache.insert(*rid, vid);
        }
        
        vid
    }

    /// Get cache statistics for monitoring
    pub fn get_cache_stats(&self) -> HashMap<String, usize> {
        let mut stats = HashMap::new();
        
        stats.insert("rid_cache_size".to_string(), 
                    self.rid_cache.lock().unwrap().len());
        stats.insert("tag_cache_size".to_string(), 
                    self.tag_cache.lock().unwrap().len());
        stats.insert("key_cache_size".to_string(), 
                    self.key_cache.lock().unwrap().len());
        stats.insert("vid_cache_size".to_string(), 
                    self.vid_cache.lock().unwrap().len());
        
        stats
    }

    /// Clear all caches (for testing or memory management)
    pub fn clear_caches(&self) {
        self.rid_cache.lock().unwrap().clear();
        self.tag_cache.lock().unwrap().clear();
        self.key_cache.lock().unwrap().clear();
        self.vid_cache.lock().unwrap().clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_optimized_wallet_caching() {
        let (salt, k_pair, r_vault) = AdvancedWalletCrypto::generate_secrets();
        let core = AdvancedWalletCrypto::new(
            salt.try_into().unwrap(),
            k_pair.try_into().unwrap(),
            r_vault.try_into().unwrap()
        );
        let optimized = OptimizedWalletCrypto::new(core);

        let kyc = KYCTuple {
            jurisdiction_code: "US".to_string(),
            doc_type: "passport".to_string(),
            doc_number_norm: "123456789".to_string(),
            surname_norm: "smith".to_string(),
            dob_yyyymmdd: "1990-01-01".to_string(),
            liveness_template_hash: "abc123".to_string(),
        };

        let kyc_cbor = AdvancedWalletCrypto::normalize_kyc_tuple(&kyc).unwrap();

        // First call should compute and cache
        let rid1 = optimized.derive_rid_cached(&kyc_cbor);
        
        // Second call should hit cache (much faster)
        let rid2 = optimized.derive_rid_cached(&kyc_cbor);
        
        assert_eq!(rid1, rid2, "Cached RID should match computed RID");
        
        // Check cache was populated
        let stats = optimized.get_cache_stats();
        assert_eq!(stats["rid_cache_size"], 1, "RID cache should have 1 entry");
    }

    #[test]
    fn test_per_rp_key_caching() {
        let (salt, k_pair, r_vault) = AdvancedWalletCrypto::generate_secrets();
        let core = AdvancedWalletCrypto::new(
            salt.try_into().unwrap(),
            k_pair.try_into().unwrap(),
            r_vault.try_into().unwrap()
        );
        let optimized = OptimizedWalletCrypto::new(core);

        let master_key = [42u8; 32];
        let rp_id = "example.com";

        // First derivation (expensive)
        let key1 = optimized.derive_rp_child_key_cached(&master_key, rp_id).unwrap();
        
        // Second derivation (cached, fast)
        let key2 = optimized.derive_rp_child_key_cached(&master_key, rp_id).unwrap();
        
        assert_eq!(key1, key2, "Cached key should match computed key");
        
        // Check cache was populated
        let stats = optimized.get_cache_stats();
        assert_eq!(stats["key_cache_size"], 1, "Key cache should have 1 entry");
    }
}

/// Performance benchmarking for optimized wallet
#[cfg(test)]
mod performance_tests {
    use super::*;
    use std::time::Instant;

    #[test]
    fn benchmark_optimized_wallet_operations() {
        let (salt, k_pair, r_vault) = AdvancedWalletCrypto::generate_secrets();
        let core = AdvancedWalletCrypto::new(
            salt.try_into().unwrap(),
            k_pair.try_into().unwrap(),
            r_vault.try_into().unwrap()
        );
        let optimized = OptimizedWalletCrypto::new(core);

        let kyc = KYCTuple {
            jurisdiction_code: "US".to_string(),
            doc_type: "passport".to_string(),
            doc_number_norm: "123456789".to_string(),
            surname_norm: "smith".to_string(),
            dob_yyyymmdd: "1990-01-01".to_string(),
            liveness_template_hash: "abc123".to_string(),
        };

        let kyc_cbor = AdvancedWalletCrypto::normalize_kyc_tuple(&kyc).unwrap();

        // Benchmark cached RID lookup (after first computation)
        let _rid = optimized.derive_rid_cached(&kyc_cbor); // Prime cache
        
        let start = Instant::now();
        let _rid = optimized.derive_rid_cached(&kyc_cbor); // Cached lookup
        let rid_cached_time = start.elapsed();
        println!("⚡ RID lookup (cached): {:.3}μs", rid_cached_time.as_nanos() as f64 / 1000.0);
        assert!(rid_cached_time.as_micros() < 5, "Cached RID lookup should be <5μs");

        // Benchmark cached pairwise tag (after first computation)
        let rid = [1u8; 32];
        let _tag = optimized.generate_pairwise_tag_cached(&rid, "example.com").unwrap(); // Prime cache
        
        let start = Instant::now();
        let _tag = optimized.generate_pairwise_tag_cached(&rid, "example.com").unwrap(); // Cached
        let tag_cached_time = start.elapsed();
        println!("⚡ Pairwise tag (cached): {:.3}μs", tag_cached_time.as_nanos() as f64 / 1000.0);
        assert!(tag_cached_time.as_micros() < 5, "Cached tag generation should be <5μs");

        // Benchmark cached per-RP key derivation (after first computation)
        let master_key = [42u8; 32];
        let _key = optimized.derive_rp_child_key_cached(&master_key, "example.com").unwrap(); // Prime cache
        
        let start = Instant::now();
        let _key = optimized.derive_rp_child_key_cached(&master_key, "example.com").unwrap(); // Cached
        let key_cached_time = start.elapsed();
        println!("⚡ Child key (cached): {:.3}μs", key_cached_time.as_nanos() as f64 / 1000.0);
        assert!(key_cached_time.as_micros() < 5, "Cached key derivation should be <5μs");

        // Benchmark cached VID computation
        let _vid = optimized.derive_vid_cached(&rid); // Prime cache
        
        let start = Instant::now();
        let _vid = optimized.derive_vid_cached(&rid); // Cached lookup
        let vid_cached_time = start.elapsed();
        println!("⚡ VID lookup (cached): {:.3}μs", vid_cached_time.as_nanos() as f64 / 1000.0);
        assert!(vid_cached_time.as_micros() < 5, "Cached VID lookup should be <5μs");

        println!("✅ All cached operations under 5μs target");
        
        let total_cached_overhead = rid_cached_time.as_micros() + tag_cached_time.as_micros() + 
                                   key_cached_time.as_micros() + vid_cached_time.as_micros();
        println!("📊 Total cached overhead: ~{}μs", total_cached_overhead);
        assert!(total_cached_overhead < 20, "Total cached overhead should be <20μs");
    }
}
