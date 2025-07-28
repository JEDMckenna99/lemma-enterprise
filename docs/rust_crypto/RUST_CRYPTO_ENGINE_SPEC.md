# 🦀 Lemma Rust Crypto Engine Specification

## 🎯 **Overview**

This document specifies the design and implementation of the Lemma cryptographic engine in Rust, replacing the current Python implementation for enhanced performance, security, and WebAssembly compatibility.

## 📋 **Core Requirements**

### **Performance Goals**
- **OPRF Operations**: 10-100x faster than current Python implementation
- **Bloom Filter Checks**: Sub-millisecond verification
- **Batch Processing**: Handle 1000+ operations per second
- **WebAssembly**: Compile for client-side offline verification

### **Security Requirements**
- **Memory Safety**: No buffer overflows or memory leaks
- **Constant Time**: Timing attack resistant operations
- **Hardware Backing**: TPM/Secure Enclave integration
- **Auditable Code**: Simple, reviewable cryptographic operations

---

## 🏗️ **Architecture**

### **Crate Structure**
```
lemma-crypto/
├── Cargo.toml
├── src/
│   ├── lib.rs              # Main library with Python bindings
│   ├── oprf.rs             # OPRF implementation
│   ├── bloom.rs            # Cascaded Bloom filters
│   ├── credentials.rs      # DID/VC operations
│   ├── utils.rs            # Utility functions
│   └── constants.rs        # Cryptographic constants
├── benches/
│   └── benchmarks.rs       # Performance benchmarks
├── tests/
│   └── integration.rs      # Integration tests
└── python/
    └── lemma_crypto.pyi     # Python type hints
```

### **Dependencies**
```toml
[dependencies]
# Core cryptography
curve25519-dalek = "4.0"
ristretto255 = "0.1"
sha2 = "0.10"
blake3 = "1.3"

# Bloom filters
bit-vec = "0.6"
fnv = "1.0"

# Python bindings
pyo3 = { version = "0.20", features = ["extension-module"] }

# Serialization
serde = { version = "1.0", features = ["derive"] }
bincode = "1.3"

# WebAssembly
wasm-bindgen = "0.2"
js-sys = "0.3"
web-sys = "0.3"

# Testing
criterion = "0.5"
```

---

## 🔐 **OPRF Implementation**

### **Protocol: OPRF with Ristretto255**

The OPRF (Oblivious Pseudorandom Function) implementation provides privacy-preserving verification where:
- **Client**: Blinds credential IDs before sending to server
- **Server**: Evaluates OPRF on blinded values without learning inputs
- **Client**: Unblinds results for local verification

### **Core Operations**

#### **1. Blind Operation**
```rust
/// Blinds a credential ID for OPRF evaluation
pub fn blind(credential_id: &str, client_random: &[u8; 32]) -> BlindResult {
    let input = RistrettoPoint::hash_from_bytes::<Sha512>(credential_id.as_bytes());
    let blind_scalar = Scalar::from_bytes_mod_order(*client_random);
    
    BlindResult {
        blinded_point: input * blind_scalar,
        unblind_scalar: blind_scalar,
    }
}
```

#### **2. Evaluate Operation**
```rust
/// Server-side OPRF evaluation
pub fn evaluate(blinded_point: &RistrettoPoint, server_key: &Scalar) -> RistrettoPoint {
    blinded_point * server_key
}
```

#### **3. Unblind Operation**
```rust
/// Client-side unblinding to get final OPRF output
pub fn unblind(evaluated_point: &RistrettoPoint, unblind_scalar: &Scalar) -> [u8; 32] {
    let final_point = evaluated_point * unblind_scalar.invert();
    final_point.compress().to_bytes()
}
```

### **OPRF API**
```rust
pub struct OPRFClient {
    server_key: Option<RistrettoPoint>,
    cache: HashMap<String, [u8; 32]>,
}

impl OPRFClient {
    pub fn new() -> Self { /* ... */ }
    
    pub fn blind(&self, credential_id: &str) -> (RistrettoPoint, Scalar) { /* ... */ }
    
    pub fn evaluate(&self, blinded_point: &RistrettoPoint) -> RistrettoPoint { /* ... */ }
    
    pub fn unblind(&self, evaluated_point: &RistrettoPoint, unblind_scalar: &Scalar) -> [u8; 32] { /* ... */ }
    
    pub fn get_evaluation(&mut self, credential_id: &str) -> Result<[u8; 32], OPRFError> { /* ... */ }
}
```

---

## 🌸 **Cascaded Bloom Filters**

### **Design**
Multi-level Bloom filters with increasing capacity and decreasing error rates:
- **Level 0**: 10K capacity, 0.01% error rate (most precise)
- **Level 1**: 100K capacity, 0.001% error rate
- **Level 2**: 1M capacity, 0.0001% error rate (largest)

### **Implementation**
```rust
pub struct CascadedBloomFilter {
    levels: Vec<BloomFilter>,
    error_rates: Vec<f64>,
    capacities: Vec<usize>,
}

impl CascadedBloomFilter {
    pub fn new(levels: usize, base_capacity: usize, base_error: f64) -> Self {
        let mut filters = Vec::new();
        
        for level in 0..levels {
            let capacity = base_capacity * (10_usize.pow(level as u32));
            let error_rate = base_error / (10.0_f64.powi(level as i32));
            
            filters.push(BloomFilter::new(capacity, error_rate));
        }
        
        Self {
            levels: filters,
            error_rates: vec![/* ... */],
            capacities: vec![/* ... */],
        }
    }
    
    pub fn add(&mut self, item: &[u8]) {
        for filter in &mut self.levels {
            filter.add(item);
        }
    }
    
    pub fn contains(&self, item: &[u8]) -> (bool, usize) {
        for (level, filter) in self.levels.iter().enumerate() {
            if filter.contains(item) {
                return (true, level);
            }
        }
        (false, usize::MAX)
    }
}
```

### **Optimized Bloom Filter**
```rust
pub struct BloomFilter {
    bits: BitVec,
    hash_functions: usize,
    capacity: usize,
    items_added: usize,
}

impl BloomFilter {
    pub fn new(capacity: usize, error_rate: f64) -> Self {
        let bits_needed = Self::optimal_bits(capacity, error_rate);
        let hash_functions = Self::optimal_hash_functions(bits_needed, capacity);
        
        Self {
            bits: BitVec::from_elem(bits_needed, false),
            hash_functions,
            capacity,
            items_added: 0,
        }
    }
    
    fn optimal_bits(capacity: usize, error_rate: f64) -> usize {
        (-((capacity as f64) * error_rate.ln()) / (2.0_f64.ln().powi(2))).ceil() as usize
    }
    
    fn optimal_hash_functions(bits: usize, capacity: usize) -> usize {
        ((bits as f64 / capacity as f64) * 2.0_f64.ln()).round() as usize
    }
    
    pub fn add(&mut self, item: &[u8]) {
        let hashes = self.hash_item(item);
        for hash in hashes {
            self.bits.set(hash % self.bits.len(), true);
        }
        self.items_added += 1;
    }
    
    pub fn contains(&self, item: &[u8]) -> bool {
        let hashes = self.hash_item(item);
        hashes.iter().all(|&hash| self.bits[hash % self.bits.len()])
    }
    
    fn hash_item(&self, item: &[u8]) -> Vec<usize> {
        let mut hashes = Vec::new();
        let mut hasher = Blake3::new();
        
        for i in 0..self.hash_functions {
            hasher.update(item);
            hasher.update(&i.to_le_bytes());
            let hash = hasher.finalize_xof();
            hashes.push(u64::from_le_bytes(hash.next()[0..8].try_into().unwrap()) as usize);
            hasher.reset();
        }
        
        hashes
    }
}
```

---

## 🔑 **Credentials & DID Operations**

### **DID Generation**
```rust
pub fn generate_did(method: &str, identifier: &str) -> String {
    format!("did:{}:{}", method, identifier)
}

pub fn generate_keypair() -> (SecretKey, PublicKey) {
    let mut csprng = OsRng;
    let secret_key = SecretKey::generate(&mut csprng);
    let public_key = PublicKey::from(&secret_key);
    (secret_key, public_key)
}
```

### **Verifiable Credentials**
```rust
pub struct VerifiableCredential {
    pub id: String,
    pub issuer: String,
    pub subject: String,
    pub claims: HashMap<String, Value>,
    pub proof: Proof,
}

pub struct Proof {
    pub signature: [u8; 64],
    pub verification_method: String,
    pub proof_purpose: String,
}
```

---

## 🔗 **Python Bindings**

### **PyO3 Integration**
```rust
use pyo3::prelude::*;

#[pyclass]
pub struct PyOPRFClient {
    inner: OPRFClient,
}

#[pymethods]
impl PyOPRFClient {
    #[new]
    pub fn new() -> Self {
        Self {
            inner: OPRFClient::new(),
        }
    }
    
    #[pyo3(signature = (credential_id))]
    pub fn blind(&self, credential_id: &str) -> PyResult<(Vec<u8>, Vec<u8>)> {
        let (blinded_point, unblind_scalar) = self.inner.blind(credential_id);
        Ok((
            blinded_point.compress().to_bytes().to_vec(),
            unblind_scalar.to_bytes().to_vec(),
        ))
    }
    
    #[pyo3(signature = (credential_id))]
    pub fn get_evaluation(&mut self, credential_id: &str) -> PyResult<Vec<u8>> {
        match self.inner.get_evaluation(credential_id) {
            Ok(evaluation) => Ok(evaluation.to_vec()),
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                format!("OPRF evaluation failed: {}", e)
            )),
        }
    }
}

#[pyclass]
pub struct PyCascadedBloomFilter {
    inner: CascadedBloomFilter,
}

#[pymethods]
impl PyCascadedBloomFilter {
    #[new]
    pub fn new(levels: usize, base_capacity: usize, base_error: f64) -> Self {
        Self {
            inner: CascadedBloomFilter::new(levels, base_capacity, base_error),
        }
    }
    
    #[pyo3(signature = (item))]
    pub fn add(&mut self, item: &[u8]) {
        self.inner.add(item);
    }
    
    #[pyo3(signature = (item))]
    pub fn contains(&self, item: &[u8]) -> (bool, usize) {
        self.inner.contains(item)
    }
}
```

---

## 🌐 **WebAssembly Support**

### **WASM Bindings**
```rust
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub struct WasmOPRFClient {
    inner: OPRFClient,
}

#[wasm_bindgen]
impl WasmOPRFClient {
    #[wasm_bindgen(constructor)]
    pub fn new() -> Self {
        Self {
            inner: OPRFClient::new(),
        }
    }
    
    #[wasm_bindgen(js_name = "getEvaluation")]
    pub fn get_evaluation(&mut self, credential_id: &str) -> Result<Vec<u8>, JsValue> {
        self.inner.get_evaluation(credential_id)
            .map(|eval| eval.to_vec())
            .map_err(|e| JsValue::from_str(&format!("OPRF error: {}", e)))
    }
}
```

---

## 🚀 **Performance Benchmarks**

### **Target Performance**
```rust
// Benchmarks to achieve
#[cfg(test)]
mod benchmarks {
    use criterion::{black_box, criterion_group, criterion_main, Criterion};
    
    fn oprf_blind_benchmark(c: &mut Criterion) {
        let client = OPRFClient::new();
        c.bench_function("oprf_blind", |b| {
            b.iter(|| client.blind(black_box("test_credential_id")))
        });
    }
    
    fn bloom_check_benchmark(c: &mut Criterion) {
        let mut filter = CascadedBloomFilter::new(3, 10000, 0.01);
        let test_data = b"test_credential_hash";
        filter.add(test_data);
        
        c.bench_function("bloom_check", |b| {
            b.iter(|| filter.contains(black_box(test_data)))
        });
    }
    
    criterion_group!(benches, oprf_blind_benchmark, bloom_check_benchmark);
    criterion_main!(benches);
}
```

### **Expected Results**
- **OPRF Blind/Unblind**: < 1ms per operation
- **OPRF Evaluate**: < 0.5ms per operation
- **Bloom Filter Check**: < 0.1ms per operation
- **Cascade Build**: < 100ms for 100K items

---

## 📦 **Build Configuration**

### **Cargo.toml**
```toml
[package]
name = "lemma-crypto"
version = "0.1.0"
edition = "2021"

[lib]
name = "lemma_crypto"
crate-type = ["cdylib", "rlib"]

[dependencies]
# Core dependencies listed above

[dev-dependencies]
criterion = "0.5"
quickcheck = "1.0"

[[bench]]
name = "benchmarks"
harness = false

[features]
default = ["python"]
python = ["pyo3"]
wasm = ["wasm-bindgen", "js-sys", "web-sys"]
```

### **Python Build**
```bash
# Build Python extension
maturin develop

# Build optimized release
maturin build --release
```

### **WebAssembly Build**
```bash
# Build for web
wasm-pack build --target web --features wasm

# Build for Node.js
wasm-pack build --target nodejs --features wasm
```

---

## 🧪 **Testing Strategy**

### **Unit Tests**
```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_oprf_roundtrip() {
        let client = OPRFClient::new();
        let credential_id = "test_credential";
        
        // Test complete OPRF flow
        let (blinded_point, unblind_scalar) = client.blind(credential_id);
        let evaluated_point = client.evaluate(&blinded_point);
        let final_result = client.unblind(&evaluated_point, &unblind_scalar);
        
        // Result should be deterministic for same input
        let (blinded_point2, unblind_scalar2) = client.blind(credential_id);
        let evaluated_point2 = client.evaluate(&blinded_point2);
        let final_result2 = client.unblind(&evaluated_point2, &unblind_scalar2);
        
        assert_eq!(final_result, final_result2);
    }
    
    #[test]
    fn test_bloom_filter_accuracy() {
        let mut filter = CascadedBloomFilter::new(3, 10000, 0.01);
        
        // Add known items
        let known_items = vec![b"item1", b"item2", b"item3"];
        for item in &known_items {
            filter.add(item);
        }
        
        // Test known items are found
        for item in &known_items {
            assert!(filter.contains(item).0);
        }
        
        // Test unknown items are not found (with some tolerance for false positives)
        let unknown_items = vec![b"unknown1", b"unknown2", b"unknown3"];
        let mut false_positives = 0;
        for item in &unknown_items {
            if filter.contains(item).0 {
                false_positives += 1;
            }
        }
        
        // Should have very few false positives
        assert!(false_positives as f64 / unknown_items.len() as f64 < 0.02);
    }
}
```

### **Integration Tests**
```rust
#[cfg(test)]
mod integration {
    use super::*;
    
    #[test]
    fn test_full_verification_flow() {
        // Test complete credential verification flow
        let mut client = OPRFClient::new();
        let mut filter = CascadedBloomFilter::new(3, 10000, 0.01);
        
        // Simulate revoked credential
        let revoked_credential = "revoked_credential_123";
        let oprf_result = client.get_evaluation(revoked_credential).unwrap();
        filter.add(&oprf_result);
        
        // Test revoked credential is detected
        let check_result = client.get_evaluation(revoked_credential).unwrap();
        assert!(filter.contains(&check_result).0);
        
        // Test non-revoked credential is not detected
        let valid_credential = "valid_credential_456";
        let valid_result = client.get_evaluation(valid_credential).unwrap();
        assert!(!filter.contains(&valid_result).0);
    }
}
```

---

## 🔄 **Migration Plan**

### **Phase 1: Core Implementation (Week 1-2)**
1. Set up Rust project with dependencies
2. Implement basic OPRF operations
3. Create simple Bloom filter implementation
4. Add Python bindings with PyO3
5. Basic unit tests

### **Phase 2: Advanced Features (Week 3-4)**
1. Implement cascaded Bloom filters
2. Add performance optimizations
3. Create WebAssembly bindings
4. Comprehensive testing suite
5. Benchmarking and profiling

### **Phase 3: Integration (Week 5-6)**
1. Replace Python crypto calls with Rust implementation
2. Performance testing and optimization
3. Documentation and examples
4. Production deployment preparation

---

## 📝 **Usage Examples**

### **Python Integration**
```python
import lemma_crypto

# Initialize OPRF client
client = lemma_crypto.OPRFClient()

# Get OPRF evaluation for credential
evaluation = client.get_evaluation("credential_id_123")

# Initialize cascaded bloom filter
filter = lemma_crypto.CascadedBloomFilter(levels=3, base_capacity=10000, base_error=0.01)

# Add revoked credential
filter.add(evaluation)

# Check if credential is revoked
is_revoked, level = filter.contains(evaluation)
```

### **JavaScript/WebAssembly Integration**
```javascript
import init, { WasmOPRFClient } from './pkg/lemma_crypto.js';

async function main() {
    await init();
    
    const client = new WasmOPRFClient();
    const evaluation = client.getEvaluation("credential_id_123");
    
    // Use evaluation for offline verification
    console.log("OPRF evaluation:", evaluation);
}
```

---

This specification provides a comprehensive foundation for implementing the Lemma cryptographic engine in Rust, achieving the performance, security, and compatibility goals required for the protocol. 