//! WebAssembly bindings for Lemma Bot Shield
//!
//! This module provides a minimal WebAssembly implementation focused on
//! bot shield functionality for browser deployment.

use wasm_bindgen::prelude::*;
use js_sys::Date;
use web_sys::{console};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::{
    core::LemmaCore,
    credentials::VerifiableCredential,
    packages::{IdentityPackage, TicketPackage, PackageAuthenticityPackage, QRCodePackage},
};

// Logging macro for WebAssembly
macro_rules! console_log {
    ($($t:tt)*) => (console::log_1(&format_args!($($t)*).to_string().into()))
}

/// Bot Shield Request structure
#[wasm_bindgen]
#[derive(Debug, Serialize, Deserialize)]
pub struct BotShieldRequest {
    user_id: String,
    action: String,
    timestamp: u64,
}

#[wasm_bindgen]
impl BotShieldRequest {
    #[wasm_bindgen(constructor)]
    pub fn new(user_id: String, action: String, timestamp: u64) -> BotShieldRequest {
        BotShieldRequest { user_id, action, timestamp }
    }
    
    #[wasm_bindgen(getter)]
    pub fn user_id(&self) -> String { self.user_id.clone() }
    
    #[wasm_bindgen(getter)]
    pub fn action(&self) -> String { self.action.clone() }
    
    #[wasm_bindgen(getter)]
    pub fn timestamp(&self) -> u64 { self.timestamp }
}

/// Bot Shield Response structure
#[wasm_bindgen]
#[derive(Debug, Serialize, Deserialize)]
pub struct BotShieldResponse {
    verified: bool,
    confidence: f64,
    verification_time_ns: u64,
    offline: bool,
    fingerprint: String,
}

#[wasm_bindgen]
impl BotShieldResponse {
    #[wasm_bindgen(getter)]
    pub fn verified(&self) -> bool { self.verified }
    
    #[wasm_bindgen(getter)]
    pub fn confidence(&self) -> f64 { self.confidence }
    
    #[wasm_bindgen(getter)]
    pub fn verification_time_ns(&self) -> u64 { self.verification_time_ns }
    
    #[wasm_bindgen(getter)]
    pub fn offline(&self) -> bool { self.offline }
    
    #[wasm_bindgen(getter)]
    pub fn fingerprint(&self) -> String { self.fingerprint.clone() }
}

/// Simple credential storage for WebAssembly
#[wasm_bindgen]
#[derive(Debug)]
pub struct SimpleCredentialStore {
    credentials: HashMap<String, String>, // fingerprint -> credential JSON
    verification_count: u32,
}

#[wasm_bindgen]
impl SimpleCredentialStore {
    #[wasm_bindgen(constructor)]
    pub fn new() -> SimpleCredentialStore {
        SimpleCredentialStore {
            credentials: HashMap::new(),
            verification_count: 0,
        }
    }
    
    #[wasm_bindgen]
    pub fn store_credential(&mut self, credential_json: &str) -> std::result::Result<String, JsValue> {
        // Parse credential to validate
        let credential: VerifiableCredential = serde_json::from_str(credential_json)
            .map_err(|e| JsValue::from_str(&format!("Invalid credential JSON: {}", e)))?;
        
        // Generate fingerprint
        let fingerprint = format!("cred_{}", credential.id);
        
        // Store credential
        self.credentials.insert(fingerprint.clone(), credential_json.to_string());
        
        console_log!("Stored credential with fingerprint: {}", fingerprint);
        Ok(fingerprint)
    }
    
    #[wasm_bindgen]
    pub fn get_credential_count(&self) -> u32 {
        self.credentials.len() as u32
    }
    
    #[wasm_bindgen]
    pub fn get_verification_count(&self) -> u32 {
        self.verification_count
    }
    
    #[wasm_bindgen]
    pub fn has_human_credentials(&self) -> bool {
        // Simple check - assume any identity credential is human
        self.credentials.values().any(|json| {
            if let Ok(cred) = serde_json::from_str::<VerifiableCredential>(json) {
                cred.claims.get("packageType")
                    .and_then(|v| v.as_str())
                    .map(|t| t == "identity")
                    .unwrap_or(false)
            } else {
                false
            }
        })
    }
}

/// Lemma Bot Shield - Minimal WebAssembly Implementation
#[wasm_bindgen]
#[derive(Debug)]
pub struct LemmaBotShield {
    core: LemmaCore,
    store: SimpleCredentialStore,
}

#[wasm_bindgen]
impl LemmaBotShield {
    /// Create a new bot shield instance
    #[wasm_bindgen(constructor)]
    pub fn new() -> std::result::Result<LemmaBotShield, JsValue> {
        console_log!("Creating Lemma Bot Shield...");
        
        // Create crypto engine
        let mut core = LemmaCore::new()
            .map_err(|e| JsValue::from_str(&format!("Failed to initialize LemmaCore: {}", e)))?;
        
        // Register packages
        core.register_package(IdentityPackage::new());
        core.register_package(TicketPackage::new());
        core.register_package(PackageAuthenticityPackage::new());
        core.register_package(QRCodePackage::new("generic".to_string()));
        
        let store = SimpleCredentialStore::new();
        
        console_log!("Bot Shield initialized successfully");
        Ok(LemmaBotShield {
            core,
            store,
        })
    }
    
    /// Handle bot shield verification request
    #[wasm_bindgen]
    pub fn handle_shield_request(&mut self, request: &BotShieldRequest) -> std::result::Result<BotShieldResponse, JsValue> {
        let start_time = Date::now();
        
        // Check if we have human credentials
        if !self.store.has_human_credentials() {
            // No credentials available - return unverified
            return Ok(BotShieldResponse {
                verified: false,
                confidence: 0.0,
                verification_time_ns: ((Date::now() - start_time) * 1_000_000.0) as u64,
                offline: true,
                fingerprint: "no_credentials".to_string(),
            });
        }
        
        // Simple verification - find first human credential and verify it
        for (fingerprint, json) in &self.store.credentials {
            if let Ok(credential) = serde_json::from_str::<VerifiableCredential>(json) {
                if credential.claims.get("packageType")
                    .and_then(|v| v.as_str())
                    .map(|t| t == "identity")
                    .unwrap_or(false) {
                    
                    // Verify the credential
                    match self.core.verify(&credential) {
                        Ok(result) => {
                            self.store.verification_count += 1;
                            let verification_time_ns = ((Date::now() - start_time) * 1_000_000.0) as u64;
                            
                            return Ok(BotShieldResponse {
                                verified: result.verified,
                                confidence: result.confidence,
                                verification_time_ns,
                                offline: result.offline,
                                fingerprint: fingerprint.clone(),
                            });
                        }
                        Err(e) => {
                            console_log!("Verification failed for {}: {:?}", fingerprint, e);
                            // Continue to next credential
                        }
                    }
                }
            }
        }
        
        // No valid credentials found
        Ok(BotShieldResponse {
            verified: false,
            confidence: 0.0,
            verification_time_ns: ((Date::now() - start_time) * 1_000_000.0) as u64,
            offline: true,
            fingerprint: "no_valid_credentials".to_string(),
        })
    }
    
    /// Add a human verification credential to the shield
    #[wasm_bindgen]
    pub fn add_human_credential(&mut self, credential_json: &str) -> std::result::Result<String, JsValue> {
        self.store.store_credential(credential_json)
    }
    
    /// Get shield statistics
    #[wasm_bindgen]
    pub fn get_shield_stats(&self) -> JsValue {
        let js_stats = js_sys::Object::new();
        js_sys::Reflect::set(&js_stats, &"totalCredentials".into(), &self.store.get_credential_count().into()).unwrap();
        js_sys::Reflect::set(&js_stats, &"verificationCount".into(), &self.store.get_verification_count().into()).unwrap();
        js_sys::Reflect::set(&js_stats, &"hasHumanCredentials".into(), &self.store.has_human_credentials().into()).unwrap();
        js_sys::Reflect::set(&js_stats, &"offline".into(), &true.into()).unwrap();
        
        js_stats.into()
    }
    
    /// Check if shield is ready for verification
    #[wasm_bindgen]
    pub fn is_shield_ready(&self) -> bool {
        self.store.has_human_credentials()
    }
    
    /// Clear all stored credentials
    #[wasm_bindgen]
    pub fn clear_credentials(&mut self) {
        self.store.credentials.clear();
        console_log!("Cleared all credentials");
    }
    
    /// Get the number of stored credentials
    #[wasm_bindgen]
    pub fn get_credential_count(&self) -> u32 {
        self.store.get_credential_count()
    }
}

    /// Verify QR code lemma directly (Phase 3 - QR WebAssembly support)
    #[wasm_bindgen]
    pub fn verify_qr_lemma(&mut self, qr_data_json: &str) -> std::result::Result<JsValue, JsValue> {
        let start_time = Date::now();
        
        console_log!("Starting QR verification with data: {}", qr_data_json);
        
        // Parse QR data
        let qr_data: serde_json::Value = serde_json::from_str(qr_data_json)
            .map_err(|e| JsValue::from_str(&format!("Invalid QR data JSON: {}", e)))?;
        
        // Extract lemma from QR data
        let lemma_data = qr_data.get("lemma")
            .ok_or_else(|| JsValue::from_str("No lemma found in QR data"))?;
        
        // Convert to VerifiableCredential
        let credential: VerifiableCredential = serde_json::from_value(lemma_data.clone())
            .map_err(|e| JsValue::from_str(&format!("Invalid lemma format: {}", e)))?;
        
        // Verify the QR lemma
        match self.core.verify(&credential) {
            Ok(result) => {
                let verification_time_us = ((Date::now() - start_time) * 1000.0) as u64;
                
                // Create response object
                let response = js_sys::Object::new();
                js_sys::Reflect::set(&response, &"verified".into(), &result.verified.into())?;
                js_sys::Reflect::set(&response, &"confidence".into(), &result.confidence.into())?;
                js_sys::Reflect::set(&response, &"verification_time_us".into(), &verification_time_us.into())?;
                js_sys::Reflect::set(&response, &"offline".into(), &result.offline.into())?;
                js_sys::Reflect::set(&response, &"qr_type".into(), &credential.claims.get("qr_type").unwrap_or(&serde_json::Value::String("unknown".to_string())).as_str().unwrap_or("unknown").into())?;
                js_sys::Reflect::set(&response, &"claims".into(), &JsValue::from_serde(&credential.claims).unwrap_or(JsValue::NULL))?;
                
                console_log!("QR verification completed in {}µs - verified: {}", verification_time_us, result.verified);
                Ok(response.into())
            }
            Err(e) => {
                console_log!("QR verification failed: {:?}", e);
                Err(JsValue::from_str(&format!("QR verification failed: {:?}", e)))
            }
        }
    }
    
    /// Generate QR code with embedded lemma (Phase 3 - QR WebAssembly support)
    #[wasm_bindgen]
    pub fn generate_qr_lemma(&mut self, qr_type: &str, claims_json: &str) -> std::result::Result<JsValue, JsValue> {
        let start_time = Date::now();
        
        console_log!("Generating QR lemma for type: {} with claims: {}", qr_type, claims_json);
        
        // Parse claims
        let claims: serde_json::Value = serde_json::from_str(claims_json)
            .map_err(|e| JsValue::from_str(&format!("Invalid claims JSON: {}", e)))?;
        
        // Create credential structure
        let mut credential_claims = claims.as_object().unwrap().clone();
        credential_claims.insert("qr_type".to_string(), serde_json::Value::String(qr_type.to_string()));
        credential_claims.insert("packageType".to_string(), serde_json::Value::String("qr".to_string()));
        credential_claims.insert("timestamp".to_string(), serde_json::Value::Number(serde_json::Number::from(Date::now() as u64)));
        
        let credential = VerifiableCredential {
            id: format!("qr_{}_{}", qr_type, Date::now() as u64),
            r#type: "LemmaQRCredential".to_string(),
            issuer: "lemma_qr_generator".to_string(),
            issuance_date: Date::now() as u64,
            claims: serde_json::Value::Object(credential_claims),
            proof: None, // Will be generated by verification process
        };
        
        // Generate proof through verification process
        match self.core.verify(&credential) {
            Ok(_) => {
                let generation_time_us = ((Date::now() - start_time) * 1000.0) as u64;
                
                // Create QR data structure
                let qr_data = js_sys::Object::new();
                js_sys::Reflect::set(&qr_data, &"lemma".into(), &JsValue::from_serde(&credential)?)?;
                js_sys::Reflect::set(&qr_data, &"qr_type".into(), &qr_type.into())?;
                js_sys::Reflect::set(&qr_data, &"generation_time_us".into(), &generation_time_us.into())?;
                js_sys::Reflect::set(&qr_data, &"timestamp".into(), &(Date::now() as u64).into())?;
                
                console_log!("QR generation completed in {}µs", generation_time_us);
                Ok(qr_data.into())
            }
            Err(e) => {
                console_log!("QR generation failed: {:?}", e);
                Err(JsValue::from_str(&format!("QR generation failed: {:?}", e)))
            }
        }
    }
    
    /// Batch verify multiple QR codes for performance testing
    #[wasm_bindgen]
    pub fn batch_verify_qr_codes(&mut self, qr_data_array: &js_sys::Array) -> std::result::Result<JsValue, JsValue> {
        let start_time = Date::now();
        let batch_size = qr_data_array.length();
        
        console_log!("Starting batch verification of {} QR codes", batch_size);
        
        let results = js_sys::Array::new();
        let mut total_verified = 0u32;
        let mut total_errors = 0u32;
        
        for i in 0..batch_size {
            let qr_item = qr_data_array.get(i);
            
            if let Ok(qr_data_str) = qr_item.as_string() {
                match self.verify_qr_lemma(&qr_data_str) {
                    Ok(result) => {
                        // Check if verified
                        if let Ok(verified) = js_sys::Reflect::get(&result, &"verified".into()) {
                            if verified.as_bool().unwrap_or(false) {
                                total_verified += 1;
                            }
                        }
                        results.push(&result);
                    }
                    Err(_) => {
                        total_errors += 1;
                        let error_result = js_sys::Object::new();
                        js_sys::Reflect::set(&error_result, &"verified".into(), &false.into())?;
                        js_sys::Reflect::set(&error_result, &"error".into(), &"verification_failed".into())?;
                        results.push(&error_result);
                    }
                }
            } else {
                total_errors += 1;
            }
        }
        
        let total_time_ms = Date::now() - start_time;
        let avg_time_us = if batch_size > 0 { (total_time_ms * 1000.0) / batch_size as f64 } else { 0.0 };
        
        // Create batch result
        let batch_result = js_sys::Object::new();
        js_sys::Reflect::set(&batch_result, &"results".into(), &results)?;
        js_sys::Reflect::set(&batch_result, &"total_count".into(), &batch_size.into())?;
        js_sys::Reflect::set(&batch_result, &"verified_count".into(), &total_verified.into())?;
        js_sys::Reflect::set(&batch_result, &"error_count".into(), &total_errors.into())?;
        js_sys::Reflect::set(&batch_result, &"total_time_ms".into(), &total_time_ms.into())?;
        js_sys::Reflect::set(&batch_result, &"average_time_us".into(), &avg_time_us.into())?;
        js_sys::Reflect::set(&batch_result, &"throughput_per_second".into(), &(batch_size as f64 / (total_time_ms / 1000.0)).into())?;
        
        console_log!("Batch verification completed: {}/{} verified in {:.2}ms (avg: {:.3}µs per QR)", 
                    total_verified, batch_size, total_time_ms, avg_time_us);
        
        Ok(batch_result.into())
    }
}

/// Initialize the module (called once when WASM loads)
#[wasm_bindgen(start)]
pub fn init() {
    console_log!("Lemma WASM Bot Shield with QR support initialized");
} 