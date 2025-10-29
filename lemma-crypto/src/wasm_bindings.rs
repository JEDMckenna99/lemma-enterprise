/**
 * WebAssembly Bindings for Browser-Side Verification
 * 
 * Exports Rust crypto functions to JavaScript
 */

use wasm_bindgen::prelude::*;
use ed25519_dalek::{Verifier, VerifyingKey, Signature};
use sha2::{Sha256, Digest};

/// Verify Ed25519 signature (raw bytes)
/// 
/// Parameters:
/// - public_key: 32-byte Ed25519 public key
/// - message: Message bytes (already hashed to 32 bytes by createVerificationMessage)
/// - signature: 64-byte Ed25519 signature
/// 
/// Returns: true if signature is valid
#[wasm_bindgen]
pub fn verify_signature_bytes(
    public_key: &[u8],
    message: &[u8],
    signature: &[u8]
) -> bool {
    // Validate inputs
    if public_key.len() != 32 {
        web_sys::console::error_1(&format!("Invalid public key length: {} (expected 32)", public_key.len()).into());
        return false;
    }
    
    if signature.len() != 64 {
        web_sys::console::error_1(&format!("Invalid signature length: {} (expected 64)", signature.len()).into());
        return false;
    }
    
    if message.len() != 32 {
        web_sys::console::error_1(&format!("Invalid message length: {} (expected 32-byte hash)", message.len()).into());
        return false;
    }
    
    // Parse public key
    let mut pk_bytes = [0u8; 32];
    pk_bytes.copy_from_slice(public_key);
    
    let verifying_key = match VerifyingKey::from_bytes(&pk_bytes) {
        Ok(key) => key,
        Err(e) => {
            web_sys::console::error_1(&format!("Invalid public key: {}", e).into());
            return false;
        }
    };
    
    // Parse signature
    let mut sig_bytes = [0u8; 64];
    sig_bytes.copy_from_slice(signature);
    
    let sig = Signature::from_bytes(&sig_bytes);
    
    // Verify signature
    verifying_key.verify(message, &sig).is_ok()
}

/// Create verification message from credential (for debugging)
/// 
/// This duplicates the JavaScript createVerificationMessage logic
/// to ensure both produce identical output.
#[wasm_bindgen]
pub fn create_verification_message_debug(
    id: &str,
    issuer: &str,
    subject: &str,
    issued_at: u64,
    expires_at: Option<u64>,
    claims_json: &str
) -> Vec<u8> {
    use std::collections::HashMap;
    
    let mut hasher = Sha256::new();
    
    // 1. ID
    hasher.update(id.as_bytes());
    
    // 2. Issuer
    hasher.update(issuer.as_bytes());
    
    // 3. Subject
    hasher.update(subject.as_bytes());
    
    // 4. Issued At (u64 little-endian)
    hasher.update(issued_at.to_le_bytes());
    
    // 5. Expires At (optional, u64 little-endian)
    if let Some(exp) = expires_at {
        hasher.update(exp.to_le_bytes());
    }
    
    // 6. Claims (sorted alphabetically)
    if let Ok(claims) = serde_json::from_str::<HashMap<String, serde_json::Value>>(claims_json) {
        let mut claim_keys: Vec<_> = claims.keys().collect();
        claim_keys.sort();
        
        for key in claim_keys {
            hasher.update(key.as_bytes());
            if let Ok(value_json) = serde_json::to_string(&claims[key]) {
                hasher.update(value_json.as_bytes());
            }
        }
    }
    
    hasher.finalize().to_vec()
}

/// Initialize WASM module
#[wasm_bindgen(start)]
pub fn init_wasm() {
    // Set panic hook for better error messages
    #[cfg(feature = "wasm")]
    console_error_panic_hook::set_once();
}

