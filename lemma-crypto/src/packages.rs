//! Verification packages for different use cases

use std::collections::HashMap;
use serde::{Deserialize, Serialize};

use crate::{
    credentials::VerifiableCredential,
    core::VerificationResult,
    ClaimSet, VerificationMetadata,
    Result, LemmaError
};

/// Trait for pluggable verification packages
pub trait VerificationPackage: Send + Sync {
    /// Get the package type identifier
    fn package_type(&self) -> &str;
    
    /// Verify a credential according to package-specific logic
    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult>;
    
    /// Create a new credential for this package type
    fn create_credential(&self, claims: ClaimSet) -> Result<VerifiableCredential>;
    
    /// Get the revocation key for a credential
    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String;
    
    /// Validate that a credential has the required claims for this package
    fn validate_claims(&self, claims: &ClaimSet) -> Result<()>;
}

/// Identity verification package (current Lemma functionality)
#[derive(Debug, Clone)]
pub struct IdentityPackage {
    stripe_integration: bool,
    kyc_level: String,
}

impl IdentityPackage {
    pub fn new() -> Self {
        Self {
            stripe_integration: true,
            kyc_level: "high".to_string(),
        }
    }
    
    pub fn with_kyc_level(kyc_level: String) -> Self {
        Self {
            stripe_integration: true,
            kyc_level,
        }
    }
}

impl VerificationPackage for IdentityPackage {
    fn package_type(&self) -> &str {
        "identity"
    }
    
    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        let is_human = credential.get_claim("isHuman")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
            
        let verification_level = credential.get_claim("verificationLevel")
            .and_then(|v| v.as_str())
            .unwrap_or("low");
            
        let meets_kyc_level = verification_level == self.kyc_level;
        
        let mut metadata = HashMap::new();
        metadata.insert("human_verified".to_string(), serde_json::Value::Bool(is_human));
        metadata.insert("kyc_level".to_string(), serde_json::Value::String(verification_level.to_string()));
        metadata.insert("required_level".to_string(), serde_json::Value::String(self.kyc_level.clone()));
        
        Ok(VerificationResult::new(
            is_human && meets_kyc_level,
            "identity".to_string(),
            if is_human && meets_kyc_level { 0.99 } else { 0.01 },
            metadata,
        ))
    }
    
    fn create_credential(&self, mut claims: ClaimSet) -> Result<VerifiableCredential> {
        claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
        
        // Validate required claims
        self.validate_claims(&claims)?;
        
        // TODO: Create actual credential with issuer
        Err(LemmaError::Package("Not implemented: use CredentialIssuer directly".to_string()))
    }
    
    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String {
        format!("identity:{}", credential.id)
    }
    
    fn validate_claims(&self, claims: &ClaimSet) -> Result<()> {
        if !claims.contains_key("isHuman") {
            return Err(LemmaError::Package("Missing required claim: isHuman".to_string()));
        }
        if !claims.contains_key("verificationLevel") {
            return Err(LemmaError::Package("Missing required claim: verificationLevel".to_string()));
        }
        Ok(())
    }
}

/// Ticket verification package for events
#[derive(Debug, Clone)]
pub struct TicketPackage {
    event_registry: HashMap<String, EventInfo>,
    allow_transfers: bool,
}

#[derive(Debug, Clone)]
pub struct EventInfo {
    pub event_id: String,
    pub event_name: String,
    pub date: String,
    pub venue: String,
    pub total_seats: usize,
}

impl TicketPackage {
    pub fn new() -> Self {
        Self {
            event_registry: HashMap::new(),
            allow_transfers: false,
        }
    }
    
    pub fn with_events(events: Vec<EventInfo>) -> Self {
        let mut registry = HashMap::new();
        for event in events {
            registry.insert(event.event_id.clone(), event);
        }
        
        Self {
            event_registry: registry,
            allow_transfers: false,
        }
    }
    
    pub fn add_event(&mut self, event: EventInfo) {
        self.event_registry.insert(event.event_id.clone(), event);
    }
}

impl VerificationPackage for TicketPackage {
    fn package_type(&self) -> &str {
        "ticket"
    }
    
    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        let event_id = credential.get_claim("eventId")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing eventId claim".to_string()))?;
            
        let seat_number = credential.get_claim("seatNumber")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing seatNumber claim".to_string()))?;
            
        let ticket_hash = credential.get_claim("ticketHash")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing ticketHash claim".to_string()))?;
        
        // Check if event exists
        let event_exists = self.event_registry.contains_key(event_id);
        
        let mut metadata = HashMap::new();
        metadata.insert("event_id".to_string(), serde_json::Value::String(event_id.to_string()));
        metadata.insert("seat".to_string(), serde_json::Value::String(seat_number.to_string()));
        metadata.insert("ticket_hash".to_string(), serde_json::Value::String(ticket_hash.to_string()));
        metadata.insert("event_exists".to_string(), serde_json::Value::Bool(event_exists));
        
        if let Some(event) = self.event_registry.get(event_id) {
            metadata.insert("event_name".to_string(), serde_json::Value::String(event.event_name.clone()));
            metadata.insert("venue".to_string(), serde_json::Value::String(event.venue.clone()));
            metadata.insert("date".to_string(), serde_json::Value::String(event.date.clone()));
        }
        
        // Note: Revocation checking (ticket already used) happens in core verification
        Ok(VerificationResult::new(
            event_exists,
            "ticket".to_string(),
            if event_exists { 0.999 } else { 0.001 },
            metadata,
        ))
    }
    
    fn create_credential(&self, claims: ClaimSet) -> Result<VerifiableCredential> {
        // TODO: Create actual ticket credential
        Err(LemmaError::Package("Not implemented: use CredentialIssuer directly".to_string()))
    }
    
    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String {
        let ticket_hash = credential.get_claim("ticketHash")
            .and_then(|v| v.as_str())
            .unwrap_or(&credential.id);
        format!("ticket:{}", ticket_hash)
    }
    
    fn validate_claims(&self, claims: &ClaimSet) -> Result<()> {
        let required_claims = ["eventId", "seatNumber", "ticketHash"];
        for claim in &required_claims {
            if !claims.contains_key(*claim) {
                return Err(LemmaError::Package(format!("Missing required claim: {}", claim)));
            }
        }
        Ok(())
    }
}

/// Package authenticity verification
#[derive(Debug, Clone)]
pub struct PackageAuthenticityPackage {
    manufacturer_registry: HashMap<String, ManufacturerInfo>,
    product_registry: HashMap<String, ProductInfo>,
}

#[derive(Debug, Clone)]
pub struct ManufacturerInfo {
    pub did: String,
    pub name: String,
    pub verified: bool,
    pub public_key: String,
}

#[derive(Debug, Clone)]
pub struct ProductInfo {
    pub product_id: String,
    pub name: String,
    pub manufacturer_did: String,
    pub category: String,
}

impl PackageAuthenticityPackage {
    pub fn new() -> Self {
        Self {
            manufacturer_registry: HashMap::new(),
            product_registry: HashMap::new(),
        }
    }
    
    pub fn add_manufacturer(&mut self, manufacturer: ManufacturerInfo) {
        self.manufacturer_registry.insert(manufacturer.did.clone(), manufacturer);
    }
    
    pub fn add_product(&mut self, product: ProductInfo) {
        self.product_registry.insert(product.product_id.clone(), product);
    }
}

impl VerificationPackage for PackageAuthenticityPackage {
    fn package_type(&self) -> &str {
        "package_authenticity"
    }
    
    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        let product_id = credential.get_claim("productId")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing productId claim".to_string()))?;
            
        let batch_number = credential.get_claim("batchNumber")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing batchNumber claim".to_string()))?;
            
        let manufacturer_did = credential.get_claim("manufacturerDID")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing manufacturerDID claim".to_string()))?;
        
        // Check if manufacturer and product exist
        let manufacturer_exists = self.manufacturer_registry.contains_key(manufacturer_did);
        let product_exists = self.product_registry.contains_key(product_id);
        
        let mut metadata = HashMap::new();
        metadata.insert("product_id".to_string(), serde_json::Value::String(product_id.to_string()));
        metadata.insert("batch".to_string(), serde_json::Value::String(batch_number.to_string()));
        metadata.insert("manufacturer_did".to_string(), serde_json::Value::String(manufacturer_did.to_string()));
        metadata.insert("manufacturer_verified".to_string(), serde_json::Value::Bool(manufacturer_exists));
        metadata.insert("product_verified".to_string(), serde_json::Value::Bool(product_exists));
        
        if let Some(manufacturer) = self.manufacturer_registry.get(manufacturer_did) {
            metadata.insert("manufacturer_name".to_string(), serde_json::Value::String(manufacturer.name.clone()));
            metadata.insert("manufacturer_verified".to_string(), serde_json::Value::Bool(manufacturer.verified));
        }
        
        if let Some(product) = self.product_registry.get(product_id) {
            metadata.insert("product_name".to_string(), serde_json::Value::String(product.name.clone()));
            metadata.insert("product_category".to_string(), serde_json::Value::String(product.category.clone()));
        }
        
        let verified = manufacturer_exists && product_exists;
        
        Ok(VerificationResult::new(
            verified,
            "package_authenticity".to_string(),
            if verified { 0.995 } else { 0.005 },
            metadata,
        ))
    }
    
    fn create_credential(&self, claims: ClaimSet) -> Result<VerifiableCredential> {
        // TODO: Create actual package authenticity credential
        Err(LemmaError::Package("Not implemented: use CredentialIssuer directly".to_string()))
    }
    
    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String {
        let product_id = credential.get_claim("productId")
            .and_then(|v| v.as_str())
            .unwrap_or(&credential.id);
        let batch_number = credential.get_claim("batchNumber")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        format!("package:{}:{}", product_id, batch_number)
    }
    
    fn validate_claims(&self, claims: &ClaimSet) -> Result<()> {
        let required_claims = ["productId", "batchNumber", "manufacturerDID"];
        for claim in &required_claims {
            if !claims.contains_key(*claim) {
                return Err(LemmaError::Package(format!("Missing required claim: {}", claim)));
            }
        }
        Ok(())
    }
}

/// QR Code verification package (generic)
#[derive(Debug, Clone)]
pub struct QRCodePackage {
    qr_type: String,
    validation_rules: HashMap<String, String>,
}

impl QRCodePackage {
    pub fn new(qr_type: String) -> Self {
        Self {
            qr_type,
            validation_rules: HashMap::new(),
        }
    }
    
    pub fn add_validation_rule(&mut self, field: String, rule: String) {
        self.validation_rules.insert(field, rule);
    }
}

impl VerificationPackage for QRCodePackage {
    fn package_type(&self) -> &str {
        "qr_code"
    }
    
    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        let qr_data = credential.get_claim("qrData")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing qrData claim".to_string()))?;
            
        let qr_type = credential.get_claim("qrType")
            .and_then(|v| v.as_str())
            .unwrap_or("generic");
        
        let mut metadata = HashMap::new();
        metadata.insert("qr_data".to_string(), serde_json::Value::String(qr_data.to_string()));
        metadata.insert("qr_type".to_string(), serde_json::Value::String(qr_type.to_string()));
        metadata.insert("expected_type".to_string(), serde_json::Value::String(self.qr_type.clone()));
        
        let type_matches = qr_type == self.qr_type;
        
        Ok(VerificationResult::new(
            type_matches,
            "qr_code".to_string(),
            if type_matches { 0.95 } else { 0.05 },
            metadata,
        ))
    }
    
    fn create_credential(&self, claims: ClaimSet) -> Result<VerifiableCredential> {
        // TODO: Create actual QR code credential
        Err(LemmaError::Package("Not implemented: use CredentialIssuer directly".to_string()))
    }
    
    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String {
        let qr_data = credential.get_claim("qrData")
            .and_then(|v| v.as_str())
            .unwrap_or(&credential.id);
        format!("qr:{}:{}", self.qr_type, qr_data)
    }
    
    fn validate_claims(&self, claims: &ClaimSet) -> Result<()> {
        if !claims.contains_key("qrData") {
            return Err(LemmaError::Package("Missing required claim: qrData".to_string()));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::credentials::CredentialIssuer;
    use std::collections::HashMap;

    #[test]
    fn test_identity_package() {
        let package = IdentityPackage::new();
        assert_eq!(package.package_type(), "identity");
    }

    #[test]
    fn test_ticket_package() {
        let mut package = TicketPackage::new();
        let event = EventInfo {
            event_id: "event_123".to_string(),
            event_name: "Test Concert".to_string(),
            date: "2024-01-01".to_string(),
            venue: "Test Venue".to_string(),
            total_seats: 1000,
        };
        package.add_event(event);
        
        assert_eq!(package.package_type(), "ticket");
        assert!(package.event_registry.contains_key("event_123"));
    }

    #[test]
    fn test_package_authenticity_package() {
        let mut package = PackageAuthenticityPackage::new();
        let manufacturer = ManufacturerInfo {
            did: "did:lemma:manufacturer123".to_string(),
            name: "Test Manufacturer".to_string(),
            verified: true,
            public_key: "public_key_123".to_string(),
        };
        package.add_manufacturer(manufacturer);
        
        assert_eq!(package.package_type(), "package_authenticity");
        assert!(package.manufacturer_registry.contains_key("did:lemma:manufacturer123"));
    }
} 