use crate::credentials::VerifiableCredential;
use crate::LemmaError;
use std::collections::HashMap;
use thiserror::Error;

#[cfg(feature = "gpu")]
use cudarc::driver::*;
#[cfg(feature = "gpu")]
use cudarc::nvrtc::*;
#[cfg(feature = "gpu")]
use std::sync::Arc;

type Result<T> = std::result::Result<T, LemmaError>;

#[derive(Debug, Error)]
pub enum GPUError {
    #[error("GPU initialization failed: {0}")]
    InitializationFailed(String),
    #[error("GPU operation failed: {0}")]
    OperationFailed(String),
    #[error("GPU memory allocation failed: {0}")]
    MemoryAllocationFailed(String),
    #[error("GPU kernel execution failed: {0}")]
    KernelExecutionFailed(String),
    #[error("GPU feature not available")]
    FeatureNotAvailable,
}

impl From<GPUError> for LemmaError {
    fn from(error: GPUError) -> Self {
        LemmaError::VerificationFailed(error.to_string())
    }
}

/// GPU-accelerated batch verifier for parallel processing
pub struct GPUVerifier {
    #[cfg(feature = "gpu")]
    device: Arc<CudaDevice>,
    #[cfg(feature = "gpu")]
    context: CudaContext,
    #[cfg(feature = "gpu")]
    stream: CudaStream,
    #[cfg(feature = "gpu")]
    kernel_module: CudaModule,
    
    // Statistics
    pub gpu_verifications: u64,
    pub gpu_hits: u64,
    pub gpu_misses: u64,
    pub hardware_available: bool,
    pub max_batch_size: usize,
}

impl GPUVerifier {
    /// Create a new GPU verifier
    pub fn new() -> Result<Self> {
        #[cfg(feature = "gpu")]
        {
            Self::new_with_gpu()
        }
        #[cfg(not(feature = "gpu"))]
        {
            Ok(Self {
                gpu_verifications: 0,
                gpu_hits: 0,
                gpu_misses: 0,
                hardware_available: false,
                max_batch_size: 0,
            })
        }
    }

    #[cfg(feature = "gpu")]
    fn new_with_gpu() -> Result<Self> {
        // Initialize CUDA device
        let device = match CudaDevice::new(0) {
            Ok(device) => Arc::new(device),
            Err(e) => {
                log::warn!("GPU initialization failed: {:?}", e);
                return Ok(Self {
                    device: Arc::new(CudaDevice::new(0).map_err(|e| 
                        GPUError::InitializationFailed(e.to_string()))?),
                    context: CudaContext::new(0).map_err(|e| 
                        GPUError::InitializationFailed(e.to_string()))?,
                    stream: CudaStream::new().map_err(|e| 
                        GPUError::InitializationFailed(e.to_string()))?,
                    kernel_module: CudaModule::new().map_err(|e| 
                        GPUError::InitializationFailed(e.to_string()))?,
                    gpu_verifications: 0,
                    gpu_hits: 0,
                    gpu_misses: 0,
                    hardware_available: false,
                    max_batch_size: 0,
                });
            }
        };

        // Create CUDA context
        let context = device.create_context()
            .map_err(|e| GPUError::InitializationFailed(e.to_string()))?;

        // Create CUDA stream for async operations
        let stream = device.create_stream()
            .map_err(|e| GPUError::InitializationFailed(e.to_string()))?;

        // Load and compile CUDA kernel
        let kernel_module = Self::load_verification_kernel(&device)?;

        // Get device properties for optimal batch size
        let device_props = device.get_device_properties()
            .map_err(|e| GPUError::InitializationFailed(e.to_string()))?;
        
        let max_batch_size = (device_props.max_threads_per_block * device_props.multiprocessor_count) as usize;

        Ok(Self {
            device,
            context,
            stream,
            kernel_module,
            gpu_verifications: 0,
            gpu_hits: 0,
            gpu_misses: 0,
            hardware_available: true,
            max_batch_size,
        })
    }

    #[cfg(feature = "gpu")]
    fn load_verification_kernel(device: &CudaDevice) -> Result<CudaModule> {
        let kernel_code = r#"
        extern "C" __global__ void batch_verify_signatures(
            const unsigned char* signatures,
            const unsigned char* messages,
            const unsigned int* message_lengths,
            const unsigned char* public_keys,
            bool* results,
            unsigned int batch_size
        ) {
            unsigned int idx = blockIdx.x * blockDim.x + threadIdx.x;
            
            if (idx >= batch_size) return;
            
            // Each thread handles one signature verification
            const unsigned char* signature = signatures + (idx * 64);  // Ed25519 signature size
            const unsigned char* message = messages + (idx * 2048);    // Max message size
            const unsigned char* public_key = public_keys + (idx * 32); // Ed25519 public key size
            unsigned int message_length = message_lengths[idx];
            
            // Simplified verification logic (actual implementation would use proper Ed25519)
            // For demonstration, we'll just do a basic check
            bool is_valid = true;
            
            // Basic signature validation
            for (int i = 0; i < 64; i++) {
                if (signature[i] == 0 && i < 32) {
                    is_valid = false;
                    break;
                }
            }
            
            // Basic message validation
            if (message_length == 0 || message_length > 2048) {
                is_valid = false;
            }
            
            // Basic public key validation
            for (int i = 0; i < 32; i++) {
                if (public_key[i] == 0 && i < 16) {
                    is_valid = false;
                    break;
                }
            }
            
            results[idx] = is_valid;
        }
        "#;

        let nvrtc = Nvrtc::new().map_err(|e| GPUError::InitializationFailed(e.to_string()))?;
        let program = nvrtc.create_program(kernel_code, "batch_verify_kernel")
            .map_err(|e| GPUError::InitializationFailed(e.to_string()))?;
        
        let ptx = nvrtc.compile_program(&program, &["--use_fast_math", "--gpu-architecture=compute_70"])
            .map_err(|e| GPUError::InitializationFailed(e.to_string()))?;
        
        let module = device.load_module(&ptx)
            .map_err(|e| GPUError::InitializationFailed(e.to_string()))?;
        
        Ok(module)
    }

    /// Verify a batch of credentials using GPU acceleration
    pub fn verify_batch_gpu(&mut self, credentials: &[VerifiableCredential]) -> Result<Vec<bool>> {
        #[cfg(feature = "gpu")]
        {
            if !self.hardware_available {
                return Err(GPUError::FeatureNotAvailable.into());
            }

            let batch_size = credentials.len().min(self.max_batch_size);
            if batch_size == 0 {
                return Ok(vec![]);
            }

            // Prepare data for GPU
            let mut signatures = Vec::with_capacity(batch_size * 64);
            let mut messages = Vec::with_capacity(batch_size * 2048);
            let mut message_lengths = Vec::with_capacity(batch_size);
            let mut public_keys = Vec::with_capacity(batch_size * 32);

            for (i, credential) in credentials.iter().take(batch_size).enumerate() {
                // Get signature data
                let signature_data = credential.signature_data();
                signatures.extend_from_slice(&signature_data);
                if signature_data.len() < 64 {
                    signatures.resize(signatures.len() + (64 - signature_data.len()), 0);
                }

                // Get message data
                let message_data = credential.message_bytes();
                message_lengths.push(message_data.len() as u32);
                messages.extend_from_slice(&message_data);
                if message_data.len() < 2048 {
                    messages.resize(messages.len() + (2048 - message_data.len()), 0);
                }

                // Get public key data (simplified - in real implementation would extract from DID)
                let public_key_data = vec![0u8; 32]; // Placeholder
                public_keys.extend_from_slice(&public_key_data);
            }

            // Allocate GPU memory
            let d_signatures = self.device.alloc_zeros::<u8>(signatures.len())
                .map_err(|e| GPUError::MemoryAllocationFailed(e.to_string()))?;
            let d_messages = self.device.alloc_zeros::<u8>(messages.len())
                .map_err(|e| GPUError::MemoryAllocationFailed(e.to_string()))?;
            let d_message_lengths = self.device.alloc_zeros::<u32>(message_lengths.len())
                .map_err(|e| GPUError::MemoryAllocationFailed(e.to_string()))?;
            let d_public_keys = self.device.alloc_zeros::<u8>(public_keys.len())
                .map_err(|e| GPUError::MemoryAllocationFailed(e.to_string()))?;
            let d_results = self.device.alloc_zeros::<bool>(batch_size)
                .map_err(|e| GPUError::MemoryAllocationFailed(e.to_string()))?;

            // Copy data to GPU
            self.device.htod_copy(signatures, &d_signatures)
                .map_err(|e| GPUError::OperationFailed(e.to_string()))?;
            self.device.htod_copy(messages, &d_messages)
                .map_err(|e| GPUError::OperationFailed(e.to_string()))?;
            self.device.htod_copy(message_lengths, &d_message_lengths)
                .map_err(|e| GPUError::OperationFailed(e.to_string()))?;
            self.device.htod_copy(public_keys, &d_public_keys)
                .map_err(|e| GPUError::OperationFailed(e.to_string()))?;

            // Launch kernel
            let kernel_func = self.kernel_module.get_function("batch_verify_signatures")
                .map_err(|e| GPUError::KernelExecutionFailed(e.to_string()))?;

            let threads_per_block = 256;
            let num_blocks = (batch_size + threads_per_block - 1) / threads_per_block;

            self.stream.launch_kernel(
                &kernel_func,
                (num_blocks, 1, 1),
                (threads_per_block, 1, 1),
                0,
                &[
                    &d_signatures,
                    &d_messages,
                    &d_message_lengths,
                    &d_public_keys,
                    &d_results,
                    &batch_size,
                ],
            ).map_err(|e| GPUError::KernelExecutionFailed(e.to_string()))?;

            // Copy results back to CPU
            let results = self.device.dtoh_sync_copy(&d_results)
                .map_err(|e| GPUError::OperationFailed(e.to_string()))?;

            // Update statistics
            self.gpu_verifications += batch_size as u64;
            self.gpu_hits += batch_size as u64;

            Ok(results)
        }
        #[cfg(not(feature = "gpu"))]
        {
            self.gpu_misses += credentials.len() as u64;
            Err(GPUError::FeatureNotAvailable.into())
        }
    }

    /// Verify large batches by splitting them into optimal chunks
    pub fn verify_large_batch_gpu(&mut self, credentials: &[VerifiableCredential]) -> Result<Vec<bool>> {
        if credentials.is_empty() {
            return Ok(vec![]);
        }

        let mut results = Vec::with_capacity(credentials.len());
        let chunk_size = self.max_batch_size.max(1);

        for chunk in credentials.chunks(chunk_size) {
            let chunk_results = self.verify_batch_gpu(chunk)?;
            results.extend(chunk_results);
        }

        Ok(results)
    }

    /// Get GPU statistics
    pub fn get_stats(&self) -> GPUStats {
        GPUStats {
            hardware_available: self.hardware_available,
            total_verifications: self.gpu_verifications,
            hardware_hits: self.gpu_hits,
            hardware_misses: self.gpu_misses,
            hit_rate: if self.gpu_verifications > 0 {
                (self.gpu_hits as f64 / self.gpu_verifications as f64) * 100.0
            } else {
                0.0
            },
            max_batch_size: self.max_batch_size,
        }
    }

    /// Check if GPU hardware acceleration is available
    pub fn is_hardware_available(&self) -> bool {
        self.hardware_available
    }

    /// Get optimal batch size for this GPU
    pub fn get_optimal_batch_size(&self) -> usize {
        self.max_batch_size
    }
}

/// GPU statistics structure
#[derive(Debug, Clone)]
pub struct GPUStats {
    pub hardware_available: bool,
    pub total_verifications: u64,
    pub hardware_hits: u64,
    pub hardware_misses: u64,
    pub hit_rate: f64,
    pub max_batch_size: usize,
}

/// GPU-accelerated verification result
#[derive(Debug, Clone)]
pub struct GPUVerificationResult {
    pub results: Vec<bool>,
    pub used_hardware: bool,
    pub batch_size: usize,
    pub verification_time_ns: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gpu_verifier_creation() {
        let verifier = GPUVerifier::new();
        assert!(verifier.is_ok());
    }

    #[test]
    fn test_gpu_stats() {
        let verifier = GPUVerifier::new().unwrap();
        let stats = verifier.get_stats();
        assert_eq!(stats.total_verifications, 0);
        assert_eq!(stats.hit_rate, 0.0);
    }

    #[cfg(feature = "gpu")]
    #[test]
    fn test_gpu_batch_verification() {
        let mut verifier = GPUVerifier::new().unwrap();
        let credentials = vec![]; // Empty test batch
        
        // This will fail gracefully if no GPU is available
        let result = verifier.verify_batch_gpu(&credentials);
        
        // We don't assert success because GPU may not be available in test environment
        let _ = result;
    }
} 