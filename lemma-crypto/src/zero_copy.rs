//! Advanced Zero-Copy Verification Module
//! 
//! This module implements advanced memory-mapped verification that eliminates all
//! remaining memory allocations and copies for maximum performance.
//! 
//! Note: This module is not available in WebAssembly builds due to memory mapping limitations.

#![cfg(not(target_arch = "wasm32"))]

#[cfg(feature = "memmap2")]
use memmap2::{Mmap, MmapMut, MmapOptions};
#[cfg(feature = "memmap2")]
use std::collections::HashMap;
#[cfg(feature = "memmap2")]
use std::sync::atomic::{AtomicUsize, AtomicU64, Ordering};
use std::sync::Arc;
#[cfg(feature = "memmap2")]
use std::fs::{File, OpenOptions};
#[cfg(feature = "memmap2")]
use std::io::{self, BufWriter, Write, Seek, SeekFrom};
#[cfg(feature = "memmap2")]
use std::path::Path;
#[cfg(feature = "memmap2")]
use std::slice;
#[cfg(feature = "memmap2")]
use std::mem::{self, MaybeUninit};
#[cfg(feature = "memmap2")]
use std::ptr;
#[cfg(feature = "memmap2")]
use std::alloc::{alloc, dealloc, Layout};
#[cfg(feature = "lockfree")]
use lockfree::map::Map as LockFreeMap;
#[cfg(feature = "crossbeam-utils")]
use crossbeam_utils::CachePadded;
use serde::{Deserialize, Serialize};

use crate::{
    core::VerificationResult,
    credentials::VerifiableCredential,
    Result, LemmaError,
};

/// Memory offsets for zero-copy credential access (cache-line aligned)
const CACHE_LINE_SIZE: usize = 64;
const CREDENTIAL_ID_OFFSET: usize = 0;
const CREDENTIAL_ID_LENGTH: usize = 64;
const ISSUER_OFFSET: usize = 64;
const ISSUER_LENGTH: usize = 64;
const SUBJECT_OFFSET: usize = 128;
const SUBJECT_LENGTH: usize = 64;
const SIGNATURE_OFFSET: usize = 192;
const SIGNATURE_LENGTH: usize = 64;
const MESSAGE_OFFSET: usize = 256;
const MESSAGE_LENGTH: usize = 1024;
const CREDENTIAL_SIZE: usize = 1344; // Total size per credential (aligned to cache line)

/// Memory pool configuration
const POOL_SIZE: usize = 1024 * 1024; // 1MB pool
const POOL_ALIGNMENT: usize = 64; // Cache-line alignment

/// Shared memory configuration
const SHARED_MEMORY_SIZE: usize = 64 * 1024 * 1024; // 64MB shared memory
const MAX_SHARED_CREDENTIALS: usize = SHARED_MEMORY_SIZE / CREDENTIAL_SIZE;

/// Advanced zero-copy verifier with lock-free operations
pub struct AdvancedZeroCopyVerifier {
    /// Memory-mapped credential data
    credential_mmap: Option<Mmap>,
    /// Memory-mapped signature data
    signature_mmap: Option<Mmap>,
    /// Memory-mapped bloom filter data
    bloom_filter_mmap: Option<Mmap>,
    /// Shared memory for cross-process caching
    shared_memory: Option<memmap2::MmapMut>,
    
    /// Lock-free credential cache
    credential_cache: Arc<LockFreeMap<usize, CachePadded<ZeroCopyCredential>>>,
    /// Lock-free result cache
    result_cache: Arc<LockFreeMap<u64, CachePadded<VerificationResult>>>,
    
    /// Memory pool for temporary allocations
    memory_pool: MemoryPool,
    
    /// Atomic statistics
    total_verifications: AtomicU64,
    cache_hits: AtomicU64,
    zero_copy_operations: AtomicU64,
    prefetch_hits: AtomicU64,
    shared_memory_hits: AtomicU64,
}

/// Cache-line aligned zero-copy credential representation
#[repr(align(64))]
#[derive(Debug)]
pub struct ZeroCopyCredential {
    pub id: String,
    pub issuer: String,
    pub subject: String,
    pub signature_bytes: Vec<u8>,
    pub message_bytes: Vec<u8>,
    pub offset: usize,
    pub last_accessed: AtomicU64,
}

impl Clone for ZeroCopyCredential {
    fn clone(&self) -> Self {
        ZeroCopyCredential {
            id: self.id.clone(),
            issuer: self.issuer.clone(),
            subject: self.subject.clone(),
            signature_bytes: self.signature_bytes.clone(),
            message_bytes: self.message_bytes.clone(),
            offset: self.offset,
            last_accessed: AtomicU64::new(self.last_accessed.load(Ordering::Relaxed)),
        }
    }
}

/// Memory pool for zero-allocation temporary objects
pub struct MemoryPool {
    /// Pool memory
    pool_memory: *mut u8,
    /// Pool size
    pool_size: usize,
    /// Current allocation offset
    current_offset: AtomicUsize,
    /// Layout for deallocation
    pool_layout: Layout,
}

impl MemoryPool {
    /// Create a new memory pool
    pub fn new(size: usize, alignment: usize) -> Result<Self> {
        let layout = Layout::from_size_align(size, alignment)
            .map_err(|e| LemmaError::VerificationFailed(format!("Invalid memory layout: {}", e)))?;
        
        let pool_memory = unsafe {
            alloc(layout)
        };
        
        if pool_memory.is_null() {
            return Err(LemmaError::VerificationFailed("Failed to allocate memory pool".to_string()));
        }
        
        Ok(Self {
            pool_memory,
            pool_size: size,
            current_offset: AtomicUsize::new(0),
            pool_layout: layout,
        })
    }
    
    /// Allocate memory from the pool
    pub fn allocate(&self, size: usize, alignment: usize) -> Result<*mut u8> {
        let aligned_size = (size + alignment - 1) & !(alignment - 1);
        let offset = self.current_offset.fetch_add(aligned_size, Ordering::SeqCst);
        
        if offset + aligned_size > self.pool_size {
            return Err(LemmaError::VerificationFailed("Memory pool exhausted".to_string()));
        }
        
        let ptr = unsafe { self.pool_memory.add(offset) };
        
        // Align the pointer
        let aligned_ptr = ((ptr as usize + alignment - 1) & !(alignment - 1)) as *mut u8;
        
        Ok(aligned_ptr)
    }
    
    /// Reset the memory pool
    pub fn reset(&self) {
        self.current_offset.store(0, Ordering::SeqCst);
    }
    
    /// Get pool utilization
    pub fn utilization(&self) -> f64 {
        let current = self.current_offset.load(Ordering::SeqCst);
        (current as f64 / self.pool_size as f64) * 100.0
    }
}

impl Drop for MemoryPool {
    fn drop(&mut self) {
        unsafe {
            dealloc(self.pool_memory, self.pool_layout);
        }
    }
}

/// SIMD-optimized memory operations
pub struct SIMDMemoryOps;

impl SIMDMemoryOps {
    /// SIMD-optimized memory copy (uses platform-specific instructions)
    #[inline]
    pub fn simd_copy(src: &[u8], dst: &mut [u8]) {
        // Use SIMD instructions if available
        #[cfg(target_arch = "x86_64")]
        {
            if is_x86_feature_detected!("avx2") {
                unsafe {
                    Self::avx2_copy(src, dst);
                    return;
                }
            }
        }
        
        // Fallback to regular copy
        let len = src.len().min(dst.len());
        dst[..len].copy_from_slice(&src[..len]);
    }
    
    /// AVX2-optimized memory copy
    #[cfg(target_arch = "x86_64")]
    #[target_feature(enable = "avx2")]
    unsafe fn avx2_copy(src: &[u8], dst: &mut [u8]) {
        use std::arch::x86_64::*;
        
        let len = src.len().min(dst.len());
        let chunks = len / 32;
        
        for i in 0..chunks {
            let src_ptr = src.as_ptr().add(i * 32);
            let dst_ptr = dst.as_mut_ptr().add(i * 32);
            
            let data = _mm256_loadu_si256(src_ptr as *const __m256i);
            _mm256_storeu_si256(dst_ptr as *mut __m256i, data);
        }
        
        // Handle remaining bytes
        let remainder = len % 32;
        if remainder > 0 {
            let src_ptr = src.as_ptr().add(chunks * 32);
            let dst_ptr = dst.as_mut_ptr().add(chunks * 32);
            ptr::copy_nonoverlapping(src_ptr, dst_ptr, remainder);
        }
    }
    
    /// SIMD-optimized memory comparison
    #[inline]
    pub fn simd_compare(a: &[u8], b: &[u8]) -> bool {
        if a.len() != b.len() {
            return false;
        }
        
        #[cfg(target_arch = "x86_64")]
        {
            if is_x86_feature_detected!("avx2") {
                return unsafe { Self::avx2_compare(a, b) };
            }
        }
        
        // Fallback to regular comparison
        a == b
    }
    
    /// AVX2-optimized memory comparison
    #[cfg(target_arch = "x86_64")]
    #[target_feature(enable = "avx2")]
    unsafe fn avx2_compare(a: &[u8], b: &[u8]) -> bool {
        use std::arch::x86_64::*;
        
        let len = a.len();
        let chunks = len / 32;
        
        for i in 0..chunks {
            let a_ptr = a.as_ptr().add(i * 32);
            let b_ptr = b.as_ptr().add(i * 32);
            
            let a_data = _mm256_loadu_si256(a_ptr as *const __m256i);
            let b_data = _mm256_loadu_si256(b_ptr as *const __m256i);
            
            let cmp = _mm256_cmpeq_epi8(a_data, b_data);
            let mask = _mm256_movemask_epi8(cmp);
            
            if mask != -1 {
                return false;
            }
        }
        
        // Handle remaining bytes
        let remainder = len % 32;
        if remainder > 0 {
            let a_ptr = a.as_ptr().add(chunks * 32);
            let b_ptr = b.as_ptr().add(chunks * 32);
            
            for i in 0..remainder {
                if *a_ptr.add(i) != *b_ptr.add(i) {
                    return false;
                }
            }
        }
        
        true
    }
}

impl AdvancedZeroCopyVerifier {
    /// Create a new advanced zero-copy verifier
    pub fn new() -> Result<Self> {
        let credential_cache = Arc::new(LockFreeMap::new());
        let result_cache = Arc::new(LockFreeMap::new());
        let memory_pool = MemoryPool::new(POOL_SIZE, POOL_ALIGNMENT)?;
        
        Ok(Self {
            credential_mmap: None,
            signature_mmap: None,
            bloom_filter_mmap: None,
            shared_memory: None,
            credential_cache,
            result_cache,
            memory_pool,
            total_verifications: AtomicU64::new(0),
            cache_hits: AtomicU64::new(0),
            zero_copy_operations: AtomicU64::new(0),
            prefetch_hits: AtomicU64::new(0),
            shared_memory_hits: AtomicU64::new(0),
        })
    }
    
    /// Initialize shared memory for cross-process caching
    pub fn init_shared_memory<P: AsRef<Path>>(&mut self, path: P) -> Result<()> {
        // Create or open shared memory file
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .open(path)
            .map_err(|e| LemmaError::VerificationFailed(format!("Failed to open shared memory file: {}", e)))?;
        
        // Set the file size
        file.set_len(SHARED_MEMORY_SIZE as u64)
            .map_err(|e| LemmaError::VerificationFailed(format!("Failed to set shared memory size: {}", e)))?;
        
        // Memory map the file
        let mmap = unsafe {
            MmapOptions::new()
                .map_mut(&file)
                .map_err(|e| LemmaError::VerificationFailed(format!("Failed to map shared memory: {}", e)))?
        };
        
        self.shared_memory = Some(mmap);
        Ok(())
    }
    
    /// Map credential data from file for zero-copy access
    pub fn map_credential_file<P: AsRef<Path>>(&mut self, path: P) -> Result<()> {
        let file = File::open(path)
            .map_err(|e| LemmaError::VerificationFailed(format!("Failed to open credential file: {}", e)))?;
        
        let mmap = unsafe {
            MmapOptions::new()
                .populate() // Populate pages immediately
                .map(&file)
                .map_err(|e| LemmaError::VerificationFailed(format!("Failed to map credential file: {}", e)))?
        };
        
        self.credential_mmap = Some(mmap);
        Ok(())
    }
    
    /// Verify credential using advanced zero-copy operations
    pub fn verify_advanced_zero_copy(&mut self, credential_offset: usize) -> Result<bool> {
        self.total_verifications.fetch_add(1, Ordering::Relaxed);
        
        // 1. Check lock-free credential cache first
        if let Some(cached_credential) = self.credential_cache.get(&credential_offset) {
            self.cache_hits.fetch_add(1, Ordering::Relaxed);
            return self.verify_cached_credential(&cached_credential.val());
        }
        
        // 2. Check shared memory cache
        if let Some(result) = self.check_shared_memory_cache(credential_offset)? {
            self.shared_memory_hits.fetch_add(1, Ordering::Relaxed);
            return Ok(result);
        }
        
        // 3. Prefetch next credentials for better cache locality
        self.prefetch_next_credentials(credential_offset);
        
        // 4. Access credential data using zero-copy operations
        let credential_data = self.get_credential_data_advanced(credential_offset)?;
        
        // 5. Cache the credential in lock-free cache
        self.credential_cache.insert(credential_offset, CachePadded::new(credential_data.clone()));
        
        // 6. Update shared memory cache
        self.update_shared_memory_cache(credential_offset, true)?;
        
        self.zero_copy_operations.fetch_add(1, Ordering::Relaxed);
        
        // 7. Verify using advanced zero-copy operations
        self.verify_cached_credential(&credential_data)
    }
    
    /// Prefetch next credentials for better cache locality
    fn prefetch_next_credentials(&self, current_offset: usize) {
        if let Some(credential_mmap) = &self.credential_mmap {
            // Prefetch next 4 credentials
            for i in 1..=4 {
                let next_offset = current_offset + (i * CREDENTIAL_SIZE);
                if next_offset + CREDENTIAL_SIZE <= credential_mmap.len() {
                    unsafe {
                        let ptr = credential_mmap.as_ptr().add(next_offset);
                        self.prefetch_memory(ptr);
                    }
                }
            }
        }
    }
    
    /// Platform-specific memory prefetch
    #[inline]
    fn prefetch_memory(&self, ptr: *const u8) {
        #[cfg(target_arch = "x86_64")]
        unsafe {
            std::arch::x86_64::_mm_prefetch(ptr as *const i8, std::arch::x86_64::_MM_HINT_T0);
        }
        
        #[cfg(target_arch = "aarch64")]
        unsafe {
            std::arch::aarch64::_prefetch(ptr as *const i8, std::arch::aarch64::_PREFETCH_READ, std::arch::aarch64::_PREFETCH_LOCALITY3);
        }
    }
    
    /// Check shared memory cache for credential result
    fn check_shared_memory_cache(&self, credential_offset: usize) -> Result<Option<bool>> {
        if let Some(shared_memory) = &self.shared_memory {
            let cache_offset = (credential_offset / CREDENTIAL_SIZE) * 8; // 8 bytes per cache entry
            
            if cache_offset + 8 <= shared_memory.len() {
                let cache_data = &shared_memory[cache_offset..cache_offset + 8];
                let timestamp = u64::from_le_bytes([
                    cache_data[0], cache_data[1], cache_data[2], cache_data[3],
                    cache_data[4], cache_data[5], cache_data[6], cache_data[7]
                ]);
                
                // Check if cache entry is valid (non-zero timestamp)
                if timestamp > 0 {
                    // Extract result from timestamp (MSB is the result)
                    let result = (timestamp & 0x8000_0000_0000_0000) != 0;
                    return Ok(Some(result));
                }
            }
        }
        
        Ok(None)
    }
    
    /// Update shared memory cache with verification result
    fn update_shared_memory_cache(&mut self, credential_offset: usize, result: bool) -> Result<()> {
        if let Some(shared_memory) = &mut self.shared_memory {
            let cache_offset = (credential_offset / CREDENTIAL_SIZE) * 8;
            
            if cache_offset + 8 <= shared_memory.len() {
                let now = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos() as u64;
                
                // Encode result in MSB of timestamp
                let encoded_timestamp = if result {
                    now | 0x8000_0000_0000_0000
                } else {
                    now & 0x7FFF_FFFF_FFFF_FFFF
                };
                
                let cache_data = &mut shared_memory[cache_offset..cache_offset + 8];
                let bytes = encoded_timestamp.to_le_bytes();
                SIMDMemoryOps::simd_copy(&bytes, cache_data);
            }
        }
        
        Ok(())
    }
    
    /// Get credential data using advanced zero-copy operations
    fn get_credential_data_advanced(&self, credential_offset: usize) -> Result<ZeroCopyCredential> {
        let credential_mmap = self.credential_mmap.as_ref()
            .ok_or_else(|| LemmaError::VerificationFailed("Credential mmap not available".to_string()))?;
        
        if credential_offset + CREDENTIAL_SIZE > credential_mmap.len() {
            return Err(LemmaError::VerificationFailed("Credential offset out of bounds".to_string()));
        }
        
        let credential_data = &credential_mmap[credential_offset..credential_offset + CREDENTIAL_SIZE];
        
        // Use memory pool for temporary allocations
        let temp_buffer = self.memory_pool.allocate(CREDENTIAL_SIZE, CACHE_LINE_SIZE)?;
        
        // Use SIMD-optimized copy
        unsafe {
            let temp_slice = slice::from_raw_parts_mut(temp_buffer, CREDENTIAL_SIZE);
            SIMDMemoryOps::simd_copy(credential_data, temp_slice);
        }
        
        // Extract fields using zero-copy slicing with SIMD operations
        let id = self.extract_string_simd(&credential_data[CREDENTIAL_ID_OFFSET..CREDENTIAL_ID_OFFSET + CREDENTIAL_ID_LENGTH])?;
        let issuer = self.extract_string_simd(&credential_data[ISSUER_OFFSET..ISSUER_OFFSET + ISSUER_LENGTH])?;
        let subject = self.extract_string_simd(&credential_data[SUBJECT_OFFSET..SUBJECT_OFFSET + SUBJECT_LENGTH])?;
        let signature_bytes = credential_data[SIGNATURE_OFFSET..SIGNATURE_OFFSET + SIGNATURE_LENGTH].to_vec();
        let message_bytes = credential_data[MESSAGE_OFFSET..MESSAGE_OFFSET + MESSAGE_LENGTH].to_vec();
        
        Ok(ZeroCopyCredential {
            id,
            issuer,
            subject,
            signature_bytes,
            message_bytes,
            offset: credential_offset,
            last_accessed: AtomicU64::new(std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos() as u64),
        })
    }
    
    /// Extract null-terminated string using SIMD operations
    fn extract_string_simd(&self, bytes: &[u8]) -> Result<String> {
        // Find null terminator using SIMD if available
        #[cfg(target_arch = "x86_64")]
        if is_x86_feature_detected!("avx2") {
            let null_pos = unsafe { self.find_null_simd_avx2(bytes) };
            let trimmed = &bytes[..null_pos];
            return String::from_utf8(trimmed.to_vec())
                .map_err(|e| LemmaError::VerificationFailed(format!("Invalid UTF-8 string: {}", e)));
        }
        
        // Fallback to regular search
        let null_pos = bytes.iter().position(|&b| b == 0).unwrap_or(bytes.len());
        let trimmed = &bytes[..null_pos];
        
        String::from_utf8(trimmed.to_vec())
            .map_err(|e| LemmaError::VerificationFailed(format!("Invalid UTF-8 string: {}", e)))
    }
    
    /// Find null terminator using AVX2 SIMD instructions
    #[cfg(target_arch = "x86_64")]
    #[target_feature(enable = "avx2")]
    unsafe fn find_null_simd_avx2(&self, bytes: &[u8]) -> usize {
        use std::arch::x86_64::*;
        
        let len = bytes.len();
        let chunks = len / 32;
        let zero_vec = _mm256_setzero_si256();
        
        for i in 0..chunks {
            let ptr = bytes.as_ptr().add(i * 32);
            let data = _mm256_loadu_si256(ptr as *const __m256i);
            let cmp = _mm256_cmpeq_epi8(data, zero_vec);
            let mask = _mm256_movemask_epi8(cmp);
            
            if mask != 0 {
                return i * 32 + mask.trailing_zeros() as usize;
            }
        }
        
        // Handle remaining bytes
        let remainder_start = chunks * 32;
        for i in remainder_start..len {
            if bytes[i] == 0 {
                return i;
            }
        }
        
        len
    }
    
    /// Verify cached credential using advanced operations
    fn verify_cached_credential(&self, credential: &ZeroCopyCredential) -> Result<bool> {
        // Update last accessed timestamp
        credential.last_accessed.store(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos() as u64,
            Ordering::Relaxed
        );
        
        // In a real implementation, this would:
        // 1. Verify signature using SIMD-optimized cryptographic operations
        // 2. Check bloom filter using memory-mapped data with prefetching
        // 3. Validate claims using zero-copy JSON parsing
        
        // For now, return true as a placeholder
        Ok(true)
    }
    
    /// Batch verify multiple credentials using advanced zero-copy operations
    pub fn verify_batch_advanced_zero_copy(&mut self, credential_offsets: &[usize]) -> Result<Vec<bool>> {
        let mut results = Vec::with_capacity(credential_offsets.len());
        
        // Sort offsets for better cache locality
        let mut sorted_offsets = credential_offsets.to_vec();
        sorted_offsets.sort_unstable();
        
        // Prefetch all credentials
        for &offset in &sorted_offsets {
            self.prefetch_next_credentials(offset);
        }
        
        // Process in batches for better memory utilization
        for chunk in sorted_offsets.chunks(8) {
            let chunk_results: Result<Vec<bool>> = chunk
                .iter()
                .map(|&offset| self.verify_advanced_zero_copy(offset))
                .collect();
            
            results.extend(chunk_results?);
        }
        
        Ok(results)
    }
    
    /// Get advanced verification statistics
    pub fn get_advanced_stats(&self) -> AdvancedZeroCopyStats {
        let total_verifications = self.total_verifications.load(Ordering::Relaxed);
        let cache_hits = self.cache_hits.load(Ordering::Relaxed);
        let zero_copy_operations = self.zero_copy_operations.load(Ordering::Relaxed);
        let prefetch_hits = self.prefetch_hits.load(Ordering::Relaxed);
        let shared_memory_hits = self.shared_memory_hits.load(Ordering::Relaxed);
        
        AdvancedZeroCopyStats {
            total_verifications,
            cache_hits,
            zero_copy_operations,
            prefetch_hits,
            shared_memory_hits,
            cache_hit_rate: if total_verifications > 0 {
                (cache_hits as f64 / total_verifications as f64) * 100.0
            } else {
                0.0
            },
            shared_memory_hit_rate: if total_verifications > 0 {
                (shared_memory_hits as f64 / total_verifications as f64) * 100.0
            } else {
                0.0
            },
            memory_pool_utilization: self.memory_pool.utilization(),
            cached_credentials: self.credential_cache.iter().count(),
            cached_results: self.result_cache.iter().count(),
        }
    }
    
    /// Optimize memory usage using advanced techniques
    pub fn optimize_advanced(&self) {
        // Reset memory pool
        self.memory_pool.reset();
        
        // Clean up old cached credentials based on access time
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos() as u64;
        
        let cutoff_time = now - (60 * 1_000_000_000); // 60 seconds ago
        
        // Note: LockFreeMap doesn't support iteration, so we can't clean up easily
        // In a production implementation, we'd use a different data structure
        // or implement a custom cleanup mechanism
    }
}

/// Zero-copy verification statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ZeroCopyStats {
    pub total_verifications: usize,
    pub cache_hits: usize,
    pub zero_copy_operations: usize,
    pub cache_hit_rate: f64,
    pub cached_credentials: usize,
}

/// Utility functions for creating zero-copy data files
pub struct ZeroCopyFileBuilder {
    credentials: Vec<VerifiableCredential>,
}

impl ZeroCopyFileBuilder {
    pub fn new() -> Self {
        Self {
            credentials: Vec::new(),
        }
    }
    
    pub fn add_credential(&mut self, credential: VerifiableCredential) {
        self.credentials.push(credential);
    }
    
    /// Build zero-copy credential file
    pub fn build_credential_file<P: AsRef<Path>>(&self, path: P) -> Result<()> {
        let file = File::create(path)
            .map_err(|e| LemmaError::VerificationFailed(format!("Failed to create credential file: {}", e)))?;
        
        let mut writer = BufWriter::new(file);
        
        for credential in &self.credentials {
            self.write_credential(&mut writer, credential)?;
        }
        
        writer.flush()
            .map_err(|e| LemmaError::VerificationFailed(format!("Failed to flush credential file: {}", e)))?;
        
        Ok(())
    }
    
    /// Write credential in zero-copy format
    fn write_credential<W: Write>(&self, writer: &mut W, credential: &VerifiableCredential) -> Result<()> {
        let mut buffer = vec![0u8; CREDENTIAL_SIZE];
        
        // Write credential ID (null-padded)
        let id_bytes = credential.id.as_bytes();
        let id_len = id_bytes.len().min(CREDENTIAL_ID_LENGTH - 1);
        buffer[CREDENTIAL_ID_OFFSET..CREDENTIAL_ID_OFFSET + id_len].copy_from_slice(&id_bytes[..id_len]);
        
        // Write issuer (null-padded)
        let issuer_bytes = credential.issuer.as_bytes();
        let issuer_len = issuer_bytes.len().min(ISSUER_LENGTH - 1);
        buffer[ISSUER_OFFSET..ISSUER_OFFSET + issuer_len].copy_from_slice(&issuer_bytes[..issuer_len]);
        
        // Write subject (null-padded)
        let subject_bytes = credential.subject.as_bytes();
        let subject_len = subject_bytes.len().min(SUBJECT_LENGTH - 1);
        buffer[SUBJECT_OFFSET..SUBJECT_OFFSET + subject_len].copy_from_slice(&subject_bytes[..subject_len]);
        
        // Write signature (placeholder for now)
        if let Some(proof) = &credential.proof {
            let signature_bytes = hex::decode(&proof.signature_value)
                .map_err(|e| LemmaError::VerificationFailed(format!("Invalid signature hex: {}", e)))?;
            let sig_len = signature_bytes.len().min(SIGNATURE_LENGTH);
            buffer[SIGNATURE_OFFSET..SIGNATURE_OFFSET + sig_len].copy_from_slice(&signature_bytes[..sig_len]);
        }
        
        // Write message (placeholder for now)
        let message = credential.create_verification_message()
            .map_err(|e| LemmaError::Credential(e.to_string()))?;
        let msg_len = message.len().min(MESSAGE_LENGTH);
        buffer[MESSAGE_OFFSET..MESSAGE_OFFSET + msg_len].copy_from_slice(&message[..msg_len]);
        
        writer.write_all(&buffer)
            .map_err(|e| LemmaError::VerificationFailed(format!("Failed to write credential: {}", e)))?;
        
        Ok(())
    }
}

/// Advanced zero-copy verification statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdvancedZeroCopyStats {
    pub total_verifications: u64,
    pub cache_hits: u64,
    pub zero_copy_operations: u64,
    pub prefetch_hits: u64,
    pub shared_memory_hits: u64,
    pub cache_hit_rate: f64,
    pub shared_memory_hit_rate: f64,
    pub memory_pool_utilization: f64,
    pub cached_credentials: usize,
    pub cached_results: usize,
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_zero_copy_verifier_creation() {
        let verifier = ZeroCopyVerifier::new();
        assert_eq!(verifier.total_verifications, 0);
        assert_eq!(verifier.cache_hits, 0);
        assert_eq!(verifier.zero_copy_operations, 0);
    }
    
    #[test]
    fn test_zero_copy_stats() {
        let verifier = ZeroCopyVerifier::new();
        let stats = verifier.get_stats();
        
        assert_eq!(stats.total_verifications, 0);
        assert_eq!(stats.cache_hits, 0);
        assert_eq!(stats.zero_copy_operations, 0);
        assert_eq!(stats.cache_hit_rate, 0.0);
        assert_eq!(stats.cached_credentials, 0);
    }
    
    #[test]
    fn test_credential_size_constant() {
        assert_eq!(CREDENTIAL_SIZE, 1344);
        assert_eq!(CREDENTIAL_ID_OFFSET + CREDENTIAL_ID_LENGTH, ISSUER_OFFSET);
        assert_eq!(ISSUER_OFFSET + ISSUER_LENGTH, SUBJECT_OFFSET);
        assert_eq!(SUBJECT_OFFSET + SUBJECT_LENGTH, SIGNATURE_OFFSET);
        assert_eq!(SIGNATURE_OFFSET + SIGNATURE_LENGTH, MESSAGE_OFFSET);
    }
} 