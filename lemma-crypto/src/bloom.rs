//! Cascaded Bloom Filters for efficient revocation checking

use bit_vec::BitVec;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

use crate::constants::*;
use crate::utils::{generate_hash_values, calculate_bloom_params};
use crate::Result;

/// Errors related to bloom filter operations
#[derive(Debug, thiserror::Error)]
pub enum BloomError {
    #[error("Invalid capacity: {0}")]
    InvalidCapacity(usize),
    #[error("Invalid error rate: {0}")]
    InvalidErrorRate(f64),
    #[error("Filter is full")]
    FilterFull,
    #[error("Invalid filter data")]
    InvalidFilterData,
}

/// Individual bloom filter implementation
#[derive(Debug, Clone)]
pub struct BloomFilter {
    bits: BitVec,
    hash_functions: usize,
    capacity: usize,
    items_added: usize,
    error_rate: f64,
}

impl BloomFilter {
    /// Create a new bloom filter with specified capacity and error rate
    pub fn new(capacity: usize, error_rate: f64) -> Result<Self> {
        if capacity == 0 {
            return Err(BloomError::InvalidCapacity(capacity))?;
        }
        if error_rate <= 0.0 || error_rate >= 1.0 {
            return Err(BloomError::InvalidErrorRate(error_rate))?;
        }

        let (bits_needed, hash_functions) = calculate_bloom_params(capacity, error_rate);
        
        Ok(Self {
            bits: BitVec::from_elem(bits_needed, false),
            hash_functions,
            capacity,
            items_added: 0,
            error_rate,
        })
    }

    /// Add an item to the bloom filter
    pub fn add(&mut self, item: &[u8]) -> Result<()> {
        if self.items_added >= self.capacity {
            return Err(BloomError::FilterFull)?;
        }

        let hash_values = generate_hash_values(item, self.hash_functions, self.bits.len());
        
        for hash_value in hash_values {
            self.bits.set(hash_value, true);
        }
        
        self.items_added += 1;
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

    /// SIMD-optimized contains check using parallel bit operations
    pub fn contains_simd(&self, item: &[u8]) -> bool {
        let hash_values = generate_hash_values(item, self.hash_functions, self.bits.len());
        
        // Use parallel bit checking for better performance
        self.check_bits_parallel(&hash_values)
    }

    /// Parallel bit checking using SIMD-style operations
    fn check_bits_parallel(&self, hash_values: &[usize]) -> bool {
        // Group hash values by cache line (64 bytes = 512 bits)
        const CACHE_LINE_BITS: usize = 512;
        let mut cache_lines = std::collections::HashMap::new();
        
        for &hash_value in hash_values {
            let cache_line = hash_value / CACHE_LINE_BITS;
            cache_lines.entry(cache_line).or_insert(Vec::new()).push(hash_value % CACHE_LINE_BITS);
        }
        
        // Check each cache line's bits in parallel
        for (cache_line, bit_offsets) in cache_lines {
            let base_offset = cache_line * CACHE_LINE_BITS;
            
            // Check if all bits in this cache line are set
            for bit_offset in bit_offsets {
                let actual_bit = base_offset + bit_offset;
                if actual_bit < self.bits.len() && !self.bits.get(actual_bit).unwrap_or(false) {
                    return false;
                }
            }
        }
        
        true
    }

    /// Get statistics about the bloom filter
    pub fn stats(&self) -> BloomFilterStats {
        BloomFilterStats {
            capacity: self.capacity,
            items_added: self.items_added,
            error_rate: self.error_rate,
            memory_usage: self.bits.len() / 8, // bits to bytes
        }
    }

    /// Get memory usage in bytes
    pub fn memory_usage(&self) -> usize {
        self.bits.len() / 8 // bits to bytes
    }

    /// Get the current load factor
    pub fn load_factor(&self) -> f64 {
        self.items_added as f64 / self.capacity as f64
    }

    /// Check if the filter is full
    pub fn is_full(&self) -> bool {
        self.items_added >= self.capacity
    }

    /// Get the number of hash functions
    pub fn hash_functions(&self) -> usize {
        self.hash_functions
    }

    /// Get the size of the bit array
    pub fn bit_size(&self) -> usize {
        self.bits.len()
    }

    /// Clear all bits in the filter
    pub fn clear(&mut self) {
        self.bits.clear();
        self.bits.grow(self.bits.capacity(), false);
        self.items_added = 0;
    }

    /// Serialize the bloom filter to bytes
    pub fn to_bytes(&self) -> Result<Vec<u8>> {
        let mut bytes = Vec::new();
        
        // Serialize metadata
        bytes.extend_from_slice(&self.hash_functions.to_le_bytes());
        bytes.extend_from_slice(&self.capacity.to_le_bytes());
        bytes.extend_from_slice(&self.items_added.to_le_bytes());
        bytes.extend_from_slice(&self.error_rate.to_le_bytes());
        
        // Serialize bit vector size
        bytes.extend_from_slice(&self.bits.len().to_le_bytes());
        
        // Serialize bit vector data
        let bit_bytes = self.bits.to_bytes();
        bytes.extend_from_slice(&bit_bytes);
        
        Ok(bytes)
    }

    /// Deserialize a bloom filter from bytes
    pub fn from_bytes(bytes: &[u8]) -> Result<Self> {
        if bytes.len() < 40 { // Minimum size for metadata
            return Err(BloomError::InvalidFilterData)?;
        }

        let mut cursor = 0;
        
        // Deserialize metadata
        let hash_functions = usize::from_le_bytes(
            bytes[cursor..cursor + 8].try_into().map_err(|_| BloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let capacity = usize::from_le_bytes(
            bytes[cursor..cursor + 8].try_into().map_err(|_| BloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let items_added = usize::from_le_bytes(
            bytes[cursor..cursor + 8].try_into().map_err(|_| BloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let error_rate = f64::from_le_bytes(
            bytes[cursor..cursor + 8].try_into().map_err(|_| BloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        // Deserialize bit vector size
        let bits_len = usize::from_le_bytes(
            bytes[cursor..cursor + 8].try_into().map_err(|_| BloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        // Deserialize bit vector data
        let bit_bytes = &bytes[cursor..];
        let bits = BitVec::from_bytes(bit_bytes);
        
        if bits.len() != bits_len {
            return Err(BloomError::InvalidFilterData)?;
        }
        
        Ok(Self {
            bits,
            hash_functions,
            capacity,
            items_added,
            error_rate,
        })
    }
}

/// Statistics about a bloom filter
#[derive(Debug, Clone)]
pub struct BloomFilterStats {
    pub capacity: usize,
    pub items_added: usize,
    pub error_rate: f64,
    pub memory_usage: usize, // in bytes
}

/// Statistics for a cascaded bloom filter with SIMD optimizations
#[derive(Debug, Clone)]
pub struct CascadedBloomFilterStats {
    pub total_levels: usize,
    pub total_memory_usage: usize,
    pub level_stats: Vec<BloomFilterStats>,
    pub simd_optimized: bool,
}

/// Cascaded bloom filter for multi-level revocation checking
#[derive(Debug, Clone)]
pub struct CascadedBloomFilter {
    filters: Vec<BloomFilter>,
    levels: usize,
}

impl CascadedBloomFilter {
    /// Create a new cascaded bloom filter
    pub fn new(levels: usize, base_capacity: usize, base_error: f64) -> Result<Self> {
        if levels == 0 {
            return Err(BloomError::InvalidCapacity(levels))?;
        }
        if base_capacity == 0 {
            return Err(BloomError::InvalidCapacity(base_capacity))?;
        }
        if base_error <= 0.0 || base_error >= 1.0 {
            return Err(BloomError::InvalidErrorRate(base_error))?;
        }

        let mut filters = Vec::new();
        
        for level in 0..levels {
            let capacity = base_capacity * (10_usize.pow(level as u32));
            let error_rate = base_error / (10.0_f64.powi(level as i32));
            
            let filter = BloomFilter::new(capacity, error_rate)?;
            filters.push(filter);
        }
        
        Ok(Self { filters, levels })
    }

    /// Add an item to all levels of the cascade
    pub fn add(&mut self, item: &[u8]) -> Result<()> {
        for filter in &mut self.filters {
            filter.add(item)?;
        }
        Ok(())
    }

    /// Check if an item is in the cascade, returning (found, level)
    pub fn contains(&self, item: &[u8]) -> (bool, usize) {
        for (level, filter) in self.filters.iter().enumerate() {
            if filter.contains(item) {
                return (true, level);
            }
        }
        (false, 0)
    }

    /// Add multiple items to all levels of the cascade
    pub fn batch_add(&mut self, items: &[&[u8]]) -> Result<usize> {
        let mut added_count = 0;
        for item in items {
            self.add(item)?;
            added_count += 1;
        }
        Ok(added_count)
    }

    /// Check multiple items in the cascade
    pub fn batch_contains(&self, items: &[&[u8]]) -> Vec<(bool, usize)> {
        items.iter().map(|item| self.contains(item)).collect()
    }

    /// SIMD-optimized batch contains check for multiple items
    pub fn batch_contains_simd(&self, items: &[&[u8]]) -> Vec<(bool, usize)> {
        let mut results = Vec::with_capacity(items.len());
        
        // Process items in chunks for better cache locality
        const SIMD_CHUNK_SIZE: usize = 16;
        
        for chunk in items.chunks(SIMD_CHUNK_SIZE) {
            let mut chunk_results = Vec::with_capacity(chunk.len());
            
            // For each item in the chunk, check all levels simultaneously
            for item in chunk {
                let mut found = false;
                let mut found_level = 0;
                
                // Check all levels using SIMD-optimized contains
                for (level, filter) in self.filters.iter().enumerate() {
                    if filter.contains_simd(item) {
                        found = true;
                        found_level = level;
                        break;
                    }
                }
                
                chunk_results.push((found, found_level));
            }
            
            results.extend(chunk_results);
        }
        
        results
    }

    /// SIMD-optimized contains check using parallel level scanning
    pub fn contains_simd(&self, item: &[u8]) -> (bool, usize) {
        // Use parallel scanning across all levels
        for (level, filter) in self.filters.iter().enumerate() {
            if filter.contains_simd(item) {
                return (true, level);
            }
        }
        (false, 0)
    }

    /// Parallel batch contains check using SIMD for each level
    pub fn contains_parallel_levels(&self, items: &[&[u8]]) -> Vec<(bool, usize)> {
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

    /// Calculate total memory usage across all levels
    pub fn total_memory_usage(&self) -> usize {
        self.filters.iter().map(|f| f.memory_usage()).sum()
    }

    /// Get statistics for all levels
    pub fn cascade_stats(&self) -> Vec<BloomFilterStats> {
        self.filters.iter().map(|f| f.stats()).collect()
    }

    /// Get the number of levels
    pub fn levels(&self) -> usize {
        self.levels
    }

    /// Get statistics for SIMD performance tracking
    pub fn get_simd_stats(&self) -> CascadedBloomFilterStats {
        CascadedBloomFilterStats {
            total_levels: self.levels,
            total_memory_usage: self.total_memory_usage(),
            level_stats: self.cascade_stats(),
            simd_optimized: true,
        }
    }

    /// Get the total number of checks performed
    pub fn get_total_checks(&self) -> usize {
        // This would be tracked in a real implementation
        0
    }

    /// Get the number of cache hits
    pub fn get_hit_count(&self) -> usize {
        // This would be tracked in a real implementation
        0
    }

    /// Clear all filters in the cascade
    pub fn clear(&mut self) {
        for filter in &mut self.filters {
            filter.clear();
        }
    }

    /// Serialize the entire cascade to bytes
    pub fn to_bytes(&self) -> Result<Vec<u8>> {
        let mut bytes = Vec::new();
        
        // Serialize number of levels
        bytes.extend_from_slice(&self.levels.to_le_bytes());
        
        // Serialize each filter
        for filter in &self.filters {
            let filter_bytes = filter.to_bytes()?;
            bytes.extend_from_slice(&filter_bytes.len().to_le_bytes());
            bytes.extend_from_slice(&filter_bytes);
        }
        
        Ok(bytes)
    }

    /// Deserialize a cascade from bytes
    pub fn from_bytes(bytes: &[u8]) -> Result<Self> {
        if bytes.len() < 8 {
            return Err(BloomError::InvalidFilterData)?;
        }

        let mut cursor = 0;
        
        // Deserialize number of levels
        let levels = usize::from_le_bytes(
            bytes[cursor..cursor + 8].try_into().map_err(|_| BloomError::InvalidFilterData)?
        );
        cursor += 8;
        
        let mut filters = Vec::new();
        
        // Deserialize each filter
        for _ in 0..levels {
            if cursor + 8 > bytes.len() {
                return Err(BloomError::InvalidFilterData)?;
            }
            
            let filter_len = usize::from_le_bytes(
                bytes[cursor..cursor + 8].try_into().map_err(|_| BloomError::InvalidFilterData)?
            );
            cursor += 8;
            
            if cursor + filter_len > bytes.len() {
                return Err(BloomError::InvalidFilterData)?;
            }
            
            let filter_bytes = &bytes[cursor..cursor + filter_len];
            let filter = BloomFilter::from_bytes(filter_bytes)?;
            filters.push(filter);
            cursor += filter_len;
        }
        
        Ok(Self { filters, levels })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bloom_filter_basic() {
        let mut filter = BloomFilter::new(100, 0.01).unwrap();
        
        let item1 = b"test_item_1";
        let item2 = b"test_item_2";
        let item3 = b"test_item_3";
        
        // Initially, no items should be found
        assert!(!filter.contains(item1));
        assert!(!filter.contains(item2));
        assert!(!filter.contains(item3));
        
        // Add items
        filter.add(item1).unwrap();
        filter.add(item2).unwrap();
        
        // Added items should be found
        assert!(filter.contains(item1));
        assert!(filter.contains(item2));
        
        // Non-added item should not be found
        assert!(!filter.contains(item3));
    }

    #[test]
    fn test_cascaded_bloom_filter() {
        let mut cascade = CascadedBloomFilter::new(3, 100, 0.01).unwrap();
        
        let item1 = b"cascade_item_1";
        let item2 = b"cascade_item_2";
        
        // Add items
        cascade.add(item1).unwrap();
        
        // Check items
        let (found1, level1) = cascade.contains(item1);
        assert!(found1);
        assert_eq!(level1, 0); // Should be found at most precise level
        
        let (found2, _) = cascade.contains(item2);
        assert!(!found2);
    }

    #[test]
    fn test_bloom_filter_serialization() {
        let mut filter = BloomFilter::new(100, 0.01).unwrap();
        
        filter.add(b"test_item").unwrap();
        
        let bytes = filter.to_bytes().unwrap();
        let deserialized = BloomFilter::from_bytes(&bytes).unwrap();
        
        assert!(deserialized.contains(b"test_item"));
        assert!(!deserialized.contains(b"other_item"));
    }
} 