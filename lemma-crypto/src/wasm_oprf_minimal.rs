//! Minimal OPRF module for WebAssembly
//! Contains only what's needed for client-side revocation checking

#[cfg(feature = "wasm")]
use wasm_bindgen::prelude::*;

#[cfg(feature = "wasm")]
use curve25519_dalek::{
    ristretto::RistrettoPoint,
    scalar::Scalar,
};

#[cfg(feature = "wasm")]
use sha2::{Sha512, Digest};

/// Hash credential ID to a point on the curve
#[cfg(feature = "wasm")]
fn hash_to_point(data: &[u8]) -> RistrettoPoint {
    let mut hasher = Sha512::new();
    hasher.update(b"LEMMA_OPRF_V1");
    hasher.update(data);
    let hash = hasher.finalize();
    
    let mut uniform_bytes = [0u8; 64];
    uniform_bytes.copy_from_slice(&hash);
    
    RistrettoPoint::from_uniform_bytes(&uniform_bytes)
}

/// OPRF blind result (kept in browser memory)
#[cfg(feature = "wasm")]
#[wasm_bindgen]
pub struct OPRFBlindResult {
    blinded_hex: String,
    unblind_scalar_bytes: Vec<u8>,
}

#[cfg(feature = "wasm")]
#[wasm_bindgen]
impl OPRFBlindResult {
    /// Get blinded point as hex (send this to server)
    pub fn get_blinded_hex(&self) -> String {
        self.blinded_hex.clone()
    }
}

/// Minimal OPRF client for WASM
#[cfg(feature = "wasm")]
#[wasm_bindgen]
pub struct LemmaOPRFClient {
}

#[cfg(feature = "wasm")]
#[wasm_bindgen]
impl LemmaOPRFClient {
    /// Create new OPRF client
    #[wasm_bindgen(constructor)]
    pub fn new() -> LemmaOPRFClient {
        // Set panic hook for better errors in browser
        #[cfg(feature = "console_error_panic_hook")]
        console_error_panic_hook::set_once();
        
        LemmaOPRFClient {}
    }
    
    /// Blind a credential ID (client-side, privacy-preserving)
    pub fn blind(&self, credential_id: &str) -> std::result::Result<OPRFBlindResult, JsValue> {
        // Hash credential ID to point
        let input_point = hash_to_point(credential_id.as_bytes());
        
        // Generate random blinding factor (use getrandom which works in WASM)
        let mut random_bytes = [0u8; 32];
        getrandom::getrandom(&mut random_bytes)
            .map_err(|e| JsValue::from_str(&format!("Random generation failed: {}", e)))?;
        
        let blind_scalar = Scalar::from_bytes_mod_order(random_bytes);
        
        // Blind the point
        let blinded_point = input_point * blind_scalar;
        
        // Convert to hex for sending to server
        let blinded_hex = hex::encode(&blinded_point.compress().to_bytes());
        
        Ok(OPRFBlindResult {
            blinded_hex,
            unblind_scalar_bytes: blind_scalar.to_bytes().to_vec(),
        })
    }
    
    /// Unblind server's response (client-side)
    pub fn unblind(
        &self,
        evaluated_hex: &str,
        blind_result: &OPRFBlindResult,
    ) -> std::result::Result<String, JsValue> {
        // Parse evaluated point
        let evaluated_bytes = hex::decode(evaluated_hex)
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
        let unblinded_point = evaluated_point * unblind_scalar.invert();
        
        // Return as hex
        Ok(hex::encode(&unblinded_point.compress().to_bytes()))
    }
}

// Hex encoding/decoding (minimal, no external deps)
#[cfg(feature = "wasm")]
mod hex {
    pub fn encode(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{:02x}", b)).collect()
    }
    
    pub fn decode(s: &str) -> Result<Vec<u8>, String> {
        if s.len() % 2 != 0 {
            return Err("Hex must have even length".to_string());
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

