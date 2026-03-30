//! WebAssembly bindings for client-side OPRF operations
//! 
//! Provides JavaScript-accessible OPRF blinding, unblinding, and Bloom filter checking

#[cfg(feature = "wasm")]
use wasm_bindgen::prelude::*;

#[cfg(feature = "wasm")]
use curve25519_dalek::{
    ristretto::RistrettoPoint,
    scalar::Scalar,
};

#[cfg(feature = "wasm")]
use crate::oprf::{OPRFClient, BlindResult};
#[cfg(feature = "wasm")]
use crate::bloom::CascadedBloomFilter;
#[cfg(feature = "wasm")]
use crate::Result;

/// JavaScript-accessible OPRF result
#[cfg(feature = "wasm")]
#[wasm_bindgen]
pub struct WasmBlindResult {
    blinded_point_bytes: Vec<u8>,
    unblind_scalar_bytes: Vec<u8>,
}

#[cfg(feature = "wasm")]
#[wasm_bindgen]
impl WasmBlindResult {
    /// Get the blinded point as hex string (for sending to server)
    pub fn blinded_hex(&self) -> String {
        hex::encode(&self.blinded_point_bytes)
    }
    
    /// Get the blinded point as bytes
    pub fn blinded_bytes(&self) -> Vec<u8> {
        self.blinded_point_bytes.clone()
    }
    
    /// Get internal unblinding scalar (kept private in browser)
    fn get_unblind_scalar_bytes(&self) -> &[u8] {
        &self.unblind_scalar_bytes
    }
}

/// WebAssembly OPRF client for client-side blinding/unblinding
#[cfg(feature = "wasm")]
#[wasm_bindgen]
pub struct WasmOPRFClient {
    client: OPRFClient,
}

#[cfg(feature = "wasm")]
#[wasm_bindgen]
impl WasmOPRFClient {
    /// Create a new WASM OPRF client
    #[wasm_bindgen(constructor)]
    pub fn new() -> WasmOPRFClient {
        // Set panic hook for better error messages in browser console
        #[cfg(feature = "wasm")]
        console_error_panic_hook::set_once();
        
        WasmOPRFClient {
            client: OPRFClient::new(),
        }
    }
    
    /// Blind a credential ID for OPRF evaluation
    /// 
    /// Returns a WasmBlindResult containing:
    /// - blinded_point: Send this to server for evaluation
    /// - unblind_scalar: Keep this private in browser for unblinding
    pub fn blind(&self, credential_id: &str) -> Result<WasmBlindResult, JsValue> {
        let blind_result = self.client.blind(credential_id)
            .map_err(|e| JsValue::from_str(&format!("OPRF blind error: {}", e)))?;
        
        // Convert to bytes for JavaScript
        let blinded_point_bytes = blind_result.blinded_point.compress().to_bytes().to_vec();
        let unblind_scalar_bytes = blind_result.unblind_scalar.to_bytes().to_vec();
        
        Ok(WasmBlindResult {
            blinded_point_bytes,
            unblind_scalar_bytes,
        })
    }
    
    /// Unblind the server's evaluated point
    /// 
    /// Takes:
    /// - evaluated_point_hex: Hex string from server
    /// - blind_result: The WasmBlindResult from the blind() call
    /// 
    /// Returns: 32-byte OPRF output (for Bloom filter lookup)
    pub fn unblind(
        &self,
        evaluated_point_hex: &str,
        blind_result: &WasmBlindResult,
    ) -> Result<Vec<u8>, JsValue> {
        // Parse evaluated point from hex
        let evaluated_bytes = hex::decode(evaluated_point_hex)
            .map_err(|e| JsValue::from_str(&format!("Invalid hex: {}", e)))?;
        
        if evaluated_bytes.len() != 32 {
            return Err(JsValue::from_str("Evaluated point must be 32 bytes"));
        }
        
        let mut point_bytes = [0u8; 32];
        point_bytes.copy_from_slice(&evaluated_bytes);
        
        let compressed = curve25519_dalek::ristretto::CompressedRistretto(point_bytes);
        let evaluated_point = compressed.decompress()
            .ok_or_else(|| JsValue::from_str("Invalid evaluated point"))?;
        
        // Parse unblinding scalar
        if blind_result.unblind_scalar_bytes.len() != 32 {
            return Err(JsValue::from_str("Invalid unblind scalar"));
        }
        
        let mut scalar_bytes = [0u8; 32];
        scalar_bytes.copy_from_slice(&blind_result.unblind_scalar_bytes);
        let unblind_scalar = Scalar::from_bytes_mod_order(scalar_bytes);
        
        // Unblind
        let final_output = self.client.unblind(&evaluated_point, &unblind_scalar);
        
        Ok(final_output.to_vec())
    }
    
    /// Complete OPRF flow with server evaluation
    /// 
    /// JavaScript usage:
    /// ```js
    /// const client = new WasmOPRFClient();
    /// const result = await client.evaluate_with_server(
    ///     "cred_abc123",
    ///     async (blindedHex) => {
    ///         // Send to server
    ///         const response = await fetch('/api/oprf/evaluate', {
    ///             method: 'POST',
    ///             body: JSON.stringify({ blinded: blindedHex })
    ///         });
    ///         const data = await response.json();
    ///         return data.evaluated_hex;
    ///     }
    /// );
    /// ```
    pub async fn evaluate_with_server(
        &self,
        credential_id: &str,
        server_evaluate_fn: js_sys::Function,
    ) -> Result<Vec<u8>, JsValue> {
        // 1. Blind locally
        let blind_result = self.blind(credential_id)?;
        
        // 2. Call JavaScript function to send to server
        let blinded_hex = blind_result.blinded_hex();
        let js_result = server_evaluate_fn.call1(
            &JsValue::NULL,
            &JsValue::from_str(&blinded_hex),
        )?;
        
        // 3. Wait for promise to resolve
        let evaluated_hex = wasm_bindgen_futures::JsFuture::from(js_sys::Promise::from(js_result))
            .await?
            .as_string()
            .ok_or_else(|| JsValue::from_str("Server did not return string"))?;
        
        // 4. Unblind locally
        self.unblind(&evaluated_hex, &blind_result)
    }
}

/// WebAssembly Bloom filter for client-side revocation checking
#[cfg(feature = "wasm")]
#[wasm_bindgen]
pub struct WasmBloomFilter {
    filter: CascadedBloomFilter,
}

#[cfg(feature = "wasm")]
#[wasm_bindgen]
impl WasmBloomFilter {
    /// Create a new Bloom filter from serialized bytes
    #[wasm_bindgen(constructor)]
    pub fn new(filter_bytes: &[u8]) -> Result<WasmBloomFilter, JsValue> {
        let filter = CascadedBloomFilter::from_bytes(filter_bytes)
            .map_err(|e| JsValue::from_str(&format!("Failed to deserialize Bloom filter: {}", e)))?;
        
        Ok(WasmBloomFilter { filter })
    }
    
    /// Check if a credential ID (OPRF output) is in the Bloom filter
    pub fn contains(&self, oprf_output: &[u8]) -> bool {
        let (found, _level) = self.filter.contains(oprf_output);
        found
    }
    
    /// Batch check multiple OPRF outputs
    pub fn contains_batch(&self, oprf_outputs: Vec<Vec<u8>>) -> Vec<bool> {
        let outputs_refs: Vec<&[u8]> = oprf_outputs.iter().map(|v| v.as_slice()).collect();
        let results = self.filter.batch_contains(&outputs_refs);
        results.into_iter().map(|(found, _)| found).collect()
    }
    
    /// Get Bloom filter statistics
    pub fn stats(&self) -> JsValue {
        let stats = self.filter.get_simd_stats();
        
        // Convert to JavaScript object
        let obj = js_sys::Object::new();
        js_sys::Reflect::set(
            &obj,
            &JsValue::from_str("levels"),
            &JsValue::from_f64(stats.total_levels as f64),
        ).unwrap();
        js_sys::Reflect::set(
            &obj,
            &JsValue::from_str("memory_bytes"),
            &JsValue::from_f64(stats.total_memory_usage as f64),
        ).unwrap();
        js_sys::Reflect::set(
            &obj,
            &JsValue::from_str("simd_optimized"),
            &JsValue::from_bool(stats.simd_optimized),
        ).unwrap();
        
        JsValue::from(obj)
    }
    
    /// Get memory usage in bytes
    pub fn memory_usage(&self) -> usize {
        self.filter.total_memory_usage()
    }
}

/// Complete OPRF-based revocation checker
#[cfg(feature = "wasm")]
#[wasm_bindgen]
pub struct WasmRevocationChecker {
    oprf_client: WasmOPRFClient,
    bloom_filter: Option<WasmBloomFilter>,
}

#[cfg(feature = "wasm")]
#[wasm_bindgen]
impl WasmRevocationChecker {
    /// Create a new revocation checker
    #[wasm_bindgen(constructor)]
    pub fn new() -> WasmRevocationChecker {
        WasmRevocationChecker {
            oprf_client: WasmOPRFClient::new(),
            bloom_filter: None,
        }
    }
    
    /// Load Bloom filter from bytes
    pub fn load_bloom_filter(&mut self, filter_bytes: &[u8]) -> Result<(), JsValue> {
        self.bloom_filter = Some(WasmBloomFilter::new(filter_bytes)?);
        Ok(())
    }
    
    /// Check if credential is revoked (complete flow)
    /// 
    /// Steps:
    /// 1. Blind credential ID locally
    /// 2. Send blinded point to server for evaluation
    /// 3. Unblind server response
    /// 4. Check OPRF output against Bloom filter
    pub async fn is_revoked(
        &self,
        credential_id: &str,
        server_evaluate_fn: js_sys::Function,
    ) -> Result<bool, JsValue> {
        // Get OPRF output
        let oprf_output = self.oprf_client.evaluate_with_server(
            credential_id,
            server_evaluate_fn,
        ).await?;
        
        // Check Bloom filter
        match &self.bloom_filter {
            Some(filter) => Ok(filter.contains(&oprf_output)),
            None => Err(JsValue::from_str("Bloom filter not loaded")),
        }
    }
    
    /// Check if credential is revoked (local-only, no server call)
    /// 
    /// Requires OPRF output to already be computed
    pub fn is_revoked_local(&self, oprf_output: &[u8]) -> Result<bool, JsValue> {
        match &self.bloom_filter {
            Some(filter) => Ok(filter.contains(oprf_output)),
            None => Err(JsValue::from_str("Bloom filter not loaded")),
        }
    }
}

// Helper function to convert bytes to hex (if hex crate not available)
#[cfg(feature = "wasm")]
mod hex {
    pub fn encode(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{:02x}", b)).collect()
    }
    
    pub fn decode(s: &str) -> Result<Vec<u8>, String> {
        if s.len() % 2 != 0 {
            return Err("Hex string must have even length".to_string());
        }
        
        (0..s.len())
            .step_by(2)
            .map(|i| {
                u8::from_str_radix(&s[i..i + 2], 16)
                    .map_err(|e| format!("Invalid hex: {}", e))
            })
            .collect()
    }
}

#[cfg(all(test, feature = "wasm"))]
mod tests {
    use super::*;
    
    #[test]
    fn test_hex_encode_decode() {
        let data = vec![0x12, 0x34, 0xab, 0xcd];
        let hex_str = hex::encode(&data);
        assert_eq!(hex_str, "1234abcd");
        
        let decoded = hex::decode(&hex_str).unwrap();
        assert_eq!(decoded, data);
    }
}
