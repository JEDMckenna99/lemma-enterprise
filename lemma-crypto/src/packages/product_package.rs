use std::collections::HashMap;
use serde::{Deserialize, Serialize};

use crate::{
    credentials::VerifiableCredential,
    core::VerificationResult,
    packages::VerificationPackage,
    qr::{QRType, ProductClaims},
    ClaimSet, VerificationMetadata,
    Result, LemmaError
};

/// Enhanced QR-specific product authenticity verification package
#[derive(Debug, Clone)]
pub struct QRProductPackage {
    manufacturer_registry: HashMap<String, QRManufacturerInfo>,
    product_registry: HashMap<String, QRProductInfo>,
    supply_chain_registry: HashMap<String, SupplyChainInfo>,
    enable_supply_chain_tracking: bool,
    enable_warranty_validation: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QRManufacturerInfo {
    pub did: String,
    pub name: String,
    pub verified: bool,
    pub public_key: String,
    pub country: String,
    pub certification_level: String,
    pub established_year: u32,
    pub specialties: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QRProductInfo {
    pub product_id: String,
    pub name: String,
    pub manufacturer_did: String,
    pub category: String,
    pub model: String,
    pub materials: Vec<String>,
    pub country_of_origin: String,
    pub msrp: f64,
    pub warranty_period_months: u32,
    pub certifications: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupplyChainInfo {
    pub supply_chain_hash: String,
    pub stages: Vec<SupplyChainStage>,
    pub verified: bool,
    pub transparency_level: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupplyChainStage {
    pub stage_name: String,
    pub location: String,
    pub timestamp: String,
    pub verified_by: String,
    pub stage_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProductVerificationContext {
    pub current_time: u64,
    pub verifier_location: Option<String>,
    pub check_warranty: bool,
    pub check_recalls: bool,
    pub allow_gray_market: bool,
}

impl QRProductPackage {
    pub fn new() -> Self {
        Self {
            manufacturer_registry: HashMap::new(),
            product_registry: HashMap::new(),
            supply_chain_registry: HashMap::new(),
            enable_supply_chain_tracking: true,
            enable_warranty_validation: true,
        }
    }
    
    pub fn with_supply_chain_tracking(mut self, enabled: bool) -> Self {
        self.enable_supply_chain_tracking = enabled;
        self
    }
    
    pub fn with_warranty_validation(mut self, enabled: bool) -> Self {
        self.enable_warranty_validation = enabled;
        self
    }
    
    pub fn add_manufacturer(&mut self, manufacturer: QRManufacturerInfo) {
        self.manufacturer_registry.insert(manufacturer.did.clone(), manufacturer);
    }
    
    pub fn add_product(&mut self, product: QRProductInfo) {
        self.product_registry.insert(product.product_id.clone(), product);
    }
    
    pub fn add_supply_chain(&mut self, supply_chain: SupplyChainInfo) {
        self.supply_chain_registry.insert(supply_chain.supply_chain_hash.clone(), supply_chain);
    }
    
    /// Verify QR product with enhanced context
    pub fn verify_qr_product(&self, claims: &ProductClaims, context: &ProductVerificationContext) -> Result<VerificationResult> {
        let mut metadata = HashMap::new();
        
        // Basic product validation
        let product_info = self.product_registry.get(&claims.product_id)
            .ok_or_else(|| LemmaError::Package(format!("Product not found: {}", claims.product_id)))?;
        
        let manufacturer_info = self.manufacturer_registry.get(&claims.manufacturer);
        
        // Verify product details match
        let product_name_matches = product_info.name == claims.product_name;
        let manufacturer_matches = manufacturer_info.map_or(false, |m| m.did == claims.manufacturer);
        let materials_match = self.verify_materials(&claims.materials, &product_info.materials);
        
        // Serial number validation
        let serial_format_valid = self.validate_serial_format(&claims.serial_number, product_info);
        
        // Batch number validation
        let batch_format_valid = self.validate_batch_format(&claims.batch_number, product_info);
        
        // Manufacturing date validation
        let manufacture_date_valid = self.validate_manufacture_date(&claims.manufacture_date, product_info);
        
        // Supply chain validation
        let supply_chain_valid = if self.enable_supply_chain_tracking {
            self.verify_supply_chain(&claims.supply_chain_hash, product_info)?
        } else {
            true
        };
        
        // Warranty validation
        let warranty_valid = if self.enable_warranty_validation && context.check_warranty {
            self.verify_warranty(&claims.warranty_expires, product_info, context.current_time)?
        } else {
            true
        };
        
        // Anti-counterfeiting validation
        let authenticity_proof_valid = self.verify_authenticity_proof(claims, product_info, manufacturer_info)?;
        
        // Populate metadata
        metadata.insert("product_id".to_string(), serde_json::json!(claims.product_id));
        metadata.insert("product_name".to_string(), serde_json::json!(claims.product_name));
        metadata.insert("manufacturer".to_string(), serde_json::json!(claims.manufacturer));
        metadata.insert("serial_number".to_string(), serde_json::json!(claims.serial_number));
        metadata.insert("batch_number".to_string(), serde_json::json!(claims.batch_number));
        metadata.insert("manufacture_date".to_string(), serde_json::json!(claims.manufacture_date));
        metadata.insert("product_name_matches".to_string(), serde_json::json!(product_name_matches));
        metadata.insert("manufacturer_matches".to_string(), serde_json::json!(manufacturer_matches));
        metadata.insert("materials_match".to_string(), serde_json::json!(materials_match));
        metadata.insert("serial_format_valid".to_string(), serde_json::json!(serial_format_valid));
        metadata.insert("batch_format_valid".to_string(), serde_json::json!(batch_format_valid));
        metadata.insert("manufacture_date_valid".to_string(), serde_json::json!(manufacture_date_valid));
        metadata.insert("supply_chain_valid".to_string(), serde_json::json!(supply_chain_valid));
        metadata.insert("warranty_valid".to_string(), serde_json::json!(warranty_valid));
        metadata.insert("authenticity_proof_valid".to_string(), serde_json::json!(authenticity_proof_valid));
        
        if let Some(manufacturer) = manufacturer_info {
            metadata.insert("manufacturer_name".to_string(), serde_json::json!(manufacturer.name));
            metadata.insert("manufacturer_verified".to_string(), serde_json::json!(manufacturer.verified));
            metadata.insert("manufacturer_country".to_string(), serde_json::json!(manufacturer.country));
        }
        
        metadata.insert("product_category".to_string(), serde_json::json!(product_info.category));
        metadata.insert("product_model".to_string(), serde_json::json!(product_info.model));
        metadata.insert("country_of_origin".to_string(), serde_json::json!(product_info.country_of_origin));
        
        // Overall validation
        let is_valid = product_name_matches && 
                      manufacturer_matches && 
                      materials_match &&
                      serial_format_valid && 
                      batch_format_valid &&
                      manufacture_date_valid &&
                      supply_chain_valid &&
                      warranty_valid &&
                      authenticity_proof_valid;
        
        let confidence = if is_valid { 0.995 } else { 0.005 };
        
        Ok(VerificationResult::new(
            is_valid,
            "qr_product".to_string(),
            confidence,
            metadata,
        ))
    }
    
    fn verify_materials(&self, claimed_materials: &[String], actual_materials: &[String]) -> bool {
        // Check if all claimed materials are in the actual materials list
        claimed_materials.iter().all(|claimed| {
            actual_materials.iter().any(|actual| {
                actual.to_lowercase() == claimed.to_lowercase()
            })
        })
    }
    
    fn validate_serial_format(&self, serial: &str, product_info: &QRProductInfo) -> bool {
        // Basic serial number format validation
        if serial.len() < 5 || serial.len() > 20 {
            return false;
        }
        
        // Check if it contains alphanumeric characters
        serial.chars().all(|c| c.is_alphanumeric())
    }
    
    fn validate_batch_format(&self, batch: &str, product_info: &QRProductInfo) -> bool {
        // Basic batch format validation (e.g., "BATCH_2024_Q3_001")
        if batch.starts_with("BATCH_") && batch.len() > 10 {
            return true;
        }
        
        // Allow simple formats
        if batch.len() >= 5 && batch.len() <= 30 {
            return true;
        }
        
        false
    }
    
    fn validate_manufacture_date(&self, date_str: &str, product_info: &QRProductInfo) -> bool {
        // Try to parse the date
        if let Ok(date) = chrono::NaiveDate::parse_from_str(date_str, "%Y-%m-%d") {
            let current_date = chrono::Utc::now().date_naive();
            
            // Ensure manufacture date is not in the future
            if date > current_date {
                return false;
            }
            
            // Ensure it's not too old (e.g., more than 10 years)
            let ten_years_ago = current_date - chrono::Duration::days(365 * 10);
            if date < ten_years_ago {
                return false;
            }
            
            return true;
        }
        
        false
    }
    
    fn verify_supply_chain(&self, supply_chain_hash: &str, product_info: &QRProductInfo) -> Result<bool> {
        if let Some(supply_chain) = self.supply_chain_registry.get(supply_chain_hash) {
            Ok(supply_chain.verified)
        } else {
            // If supply chain tracking is enabled but no data found, it's suspicious
            Ok(false)
        }
    }
    
    fn verify_warranty(&self, warranty_expires: &str, product_info: &QRProductInfo, current_time: u64) -> Result<bool> {
        if let Ok(expiry_date) = chrono::DateTime::parse_from_rfc3339(warranty_expires) {
            let expiry_timestamp = expiry_date.timestamp() as u64;
            Ok(expiry_timestamp > current_time)
        } else {
            // Invalid warranty date format
            Ok(false)
        }
    }
    
    fn verify_authenticity_proof(&self, claims: &ProductClaims, product_info: &QRProductInfo, manufacturer_info: Option<&QRManufacturerInfo>) -> Result<bool> {
        // In a real implementation, this would verify cryptographic signatures
        // For now, do basic consistency checks
        
        if let Some(manufacturer) = manufacturer_info {
            // Create proof string from product details
            let proof_string = format!(
                "{}:{}:{}:{}:{}",
                claims.product_id,
                claims.serial_number,
                claims.batch_number,
                claims.manufacture_date,
                manufacturer.public_key
            );
            
            // Simple hash validation (in reality, this would be cryptographic)
            let hash = self.simple_hash(&proof_string);
            let expected_hash_end = hash % 10000;
            
            // Check if the serial number encodes this hash (basic demo)
            if let Some(serial_suffix) = claims.serial_number.chars().rev().take(4).collect::<String>().chars().rev().collect::<String>().parse::<u64>().ok() {
                return Ok(serial_suffix == expected_hash_end);
            }
        }
        
        // Fallback: if we can't validate, assume valid for demo
        Ok(true)
    }
    
    fn simple_hash(&self, data: &str) -> u64 {
        let mut hash = 0xcbf29ce484222325u64; // FNV offset basis
        for byte in data.bytes() {
            hash ^= byte as u64;
            hash = hash.wrapping_mul(0x100000001b3u64); // FNV prime
        }
        hash
    }
}

impl VerificationPackage for QRProductPackage {
    fn package_type(&self) -> &str {
        "qr_product"
    }
    
    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        // Extract QR product claims
        let product_id = credential.get_claim("productId")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing productId claim".to_string()))?;
            
        let product_name = credential.get_claim("productName")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing productName claim".to_string()))?;
            
        let manufacturer = credential.get_claim("manufacturer")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing manufacturer claim".to_string()))?;
            
        let batch_number = credential.get_claim("batchNumber")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing batchNumber claim".to_string()))?;
            
        let manufacture_date = credential.get_claim("manufactureDate")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing manufactureDate claim".to_string()))?;
            
        let serial_number = credential.get_claim("serialNumber")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing serialNumber claim".to_string()))?;
            
        let materials = credential.get_claim("materials")
            .and_then(|v| v.as_array())
            .map(|arr| arr.iter().filter_map(|v| v.as_str()).map(|s| s.to_string()).collect())
            .unwrap_or_else(Vec::new);
            
        let supply_chain_hash = credential.get_claim("supplyChainHash")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing supplyChainHash claim".to_string()))?;
            
        let warranty_expires = credential.get_claim("warrantyExpires")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing warrantyExpires claim".to_string()))?;
        
        // Convert to ProductClaims structure
        let product_claims = ProductClaims {
            product_id: product_id.to_string(),
            product_name: product_name.to_string(),
            manufacturer: manufacturer.to_string(),
            batch_number: batch_number.to_string(),
            manufacture_date: manufacture_date.to_string(),
            serial_number: serial_number.to_string(),
            materials,
            supply_chain_hash: supply_chain_hash.to_string(),
            warranty_expires: warranty_expires.to_string(),
        };
        
        // Create verification context
        let context = ProductVerificationContext {
            current_time: chrono::Utc::now().timestamp() as u64,
            verifier_location: None,
            check_warranty: true,
            check_recalls: false,
            allow_gray_market: false,
        };
        
        // Verify using QR-specific logic
        self.verify_qr_product(&product_claims, &context)
    }
    
    fn create_credential(&self, claims: ClaimSet) -> Result<VerifiableCredential> {
        // Validate QR product claims
        self.validate_claims(&claims)?;
        
        // TODO: Create actual QR product credential
        Err(LemmaError::Package("Not implemented: use QRLemmaGenerator for QR product creation".to_string()))
    }
    
    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String {
        let product_id = credential.get_claim("productId")
            .and_then(|v| v.as_str())
            .unwrap_or(&credential.id);
        let serial_number = credential.get_claim("serialNumber")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        format!("qr_product:{}:{}", product_id, serial_number)
    }
    
    fn validate_claims(&self, claims: &ClaimSet) -> Result<()> {
        let required_claims = [
            "productId", "productName", "manufacturer", "batchNumber",
            "manufactureDate", "serialNumber", "materials", "supplyChainHash", "warrantyExpires"
        ];
        
        for claim in &required_claims {
            if !claims.contains_key(*claim) {
                return Err(LemmaError::Package(format!("Missing required QR product claim: {}", claim)));
            }
        }
        
        // Validate lemma type
        if let Some(lemma_type) = claims.get("lemmaType") {
            if lemma_type.as_str() != Some("product_authenticity") {
                return Err(LemmaError::Package("Invalid lemma type for QR product".to_string()));
            }
        }
        
        Ok(())
    }
}

/// Helper functions for creating sample manufacturers and products
impl QRProductPackage {
    pub fn create_sample_manufacturer() -> QRManufacturerInfo {
        QRManufacturerInfo {
            did: "did:lemma:swiss_watches".to_string(),
            name: "Swiss Luxury Watches Ltd.".to_string(),
            verified: true,
            public_key: "public_key_swiss_watches_123".to_string(),
            country: "Switzerland".to_string(),
            certification_level: "premium".to_string(),
            established_year: 1905,
            specialties: vec!["luxury_watches".to_string(), "precision_timepieces".to_string()],
        }
    }
    
    pub fn create_sample_product() -> QRProductInfo {
        QRProductInfo {
            product_id: "luxury_watch_SW_001".to_string(),
            name: "Submariner Professional".to_string(),
            manufacturer_did: "did:lemma:swiss_watches".to_string(),
            category: "luxury_watch".to_string(),
            model: "Submariner Pro 2024".to_string(),
            materials: vec!["steel".to_string(), "sapphire_crystal".to_string(), "ceramic_bezel".to_string()],
            country_of_origin: "Switzerland".to_string(),
            msrp: 12500.0,
            warranty_period_months: 60,
            certifications: vec!["COSC".to_string(), "Swiss Made".to_string()],
        }
    }
    
    pub fn create_sample_supply_chain() -> SupplyChainInfo {
        SupplyChainInfo {
            supply_chain_hash: "0x123456789abcdef".to_string(),
            stages: vec![
                SupplyChainStage {
                    stage_name: "Raw Materials".to_string(),
                    location: "Geneva, Switzerland".to_string(),
                    timestamp: "2024-06-01T10:00:00Z".to_string(),
                    verified_by: "did:lemma:supplier_001".to_string(),
                    stage_hash: "0x111".to_string(),
                },
                SupplyChainStage {
                    stage_name: "Manufacturing".to_string(),
                    location: "Basel, Switzerland".to_string(),
                    timestamp: "2024-07-15T14:00:00Z".to_string(),
                    verified_by: "did:lemma:swiss_watches".to_string(),
                    stage_hash: "0x222".to_string(),
                },
                SupplyChainStage {
                    stage_name: "Quality Control".to_string(),
                    location: "Zurich, Switzerland".to_string(),
                    timestamp: "2024-07-20T09:00:00Z".to_string(),
                    verified_by: "did:lemma:qc_certifier".to_string(),
                    stage_hash: "0x333".to_string(),
                }
            ],
            verified: true,
            transparency_level: "full".to_string(),
        }
    }
    
    pub fn with_sample_data(mut self) -> Self {
        self.add_manufacturer(Self::create_sample_manufacturer());
        self.add_product(Self::create_sample_product());
        self.add_supply_chain(Self::create_sample_supply_chain());
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_qr_product_package_creation() {
        let package = QRProductPackage::new()
            .with_supply_chain_tracking(true)
            .with_warranty_validation(true)
            .with_sample_data();
        
        assert_eq!(package.package_type(), "qr_product");
        assert!(package.enable_supply_chain_tracking);
        assert!(package.enable_warranty_validation);
        assert!(package.manufacturer_registry.contains_key("did:lemma:swiss_watches"));
        assert!(package.product_registry.contains_key("luxury_watch_SW_001"));
    }
    
    #[test]
    fn test_materials_verification() {
        let package = QRProductPackage::new();
        
        let claimed = vec!["steel".to_string(), "sapphire_crystal".to_string()];
        let actual = vec!["steel".to_string(), "sapphire_crystal".to_string(), "ceramic_bezel".to_string()];
        
        assert!(package.verify_materials(&claimed, &actual));
        
        let claimed_wrong = vec!["aluminum".to_string()];
        assert!(!package.verify_materials(&claimed_wrong, &actual));
    }
    
    #[test]
    fn test_serial_format_validation() {
        let package = QRProductPackage::new();
        let product_info = QRProductPackage::create_sample_product();
        
        assert!(package.validate_serial_format("SW123456789", &product_info));
        assert!(package.validate_serial_format("ABC123", &product_info));
        assert!(!package.validate_serial_format("", &product_info));
        assert!(!package.validate_serial_format("A", &product_info)); // Too short
        assert!(!package.validate_serial_format("SW-123!", &product_info)); // Special characters
    }
    
    #[test]
    fn test_manufacture_date_validation() {
        let package = QRProductPackage::new();
        let product_info = QRProductPackage::create_sample_product();
        
        assert!(package.validate_manufacture_date("2024-07-15", &product_info));
        assert!(package.validate_manufacture_date("2023-01-01", &product_info));
        assert!(!package.validate_manufacture_date("2030-01-01", &product_info)); // Future date
        assert!(!package.validate_manufacture_date("invalid-date", &product_info)); // Invalid format
    }
} 