pub mod generator;
pub mod verifier;
pub mod encoder;

pub use generator::*;
pub use verifier::*;
pub use encoder::*;

use crate::core::LemmaCore;
use crate::credentials::LemmaCredential;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// QR Code types supported by the Lemma system
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum QRType {
    EventTicket,
    ProductAuthenticity,
    AccessControl,
    IdentityVerification,
}

/// Metadata attached to QR codes
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QRMetadata {
    pub created_at: u64,
    pub version: String,
    pub issuer_did: String,
    pub expires_at: Option<u64>,
}

impl QRMetadata {
    pub fn new() -> Self {
        Self {
            created_at: chrono::Utc::now().timestamp() as u64,
            version: "1.0.0".to_string(),
            issuer_did: "did:lemma:qr_system".to_string(),
            expires_at: None,
        }
    }
    
    pub fn with_expiry(mut self, expires_at: u64) -> Self {
        self.expires_at = Some(expires_at);
        self
    }
    
    pub fn with_issuer(mut self, issuer_did: String) -> Self {
        self.issuer_did = issuer_did;
        self
    }
}

/// Main QR data structure containing the lemma and metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QRData {
    pub lemma: LemmaCredential,
    pub qr_type: QRType,
    pub metadata: QRMetadata,
}

impl QRData {
    pub fn new(lemma: LemmaCredential, qr_type: QRType, metadata: QRMetadata) -> Self {
        Self {
            lemma,
            qr_type,
            metadata,
        }
    }
    
    pub fn is_expired(&self) -> bool {
        if let Some(expires_at) = self.metadata.expires_at {
            let now = chrono::Utc::now().timestamp() as u64;
            now > expires_at
        } else {
            false
        }
    }
}

/// QR Code wrapper that contains encoded QR data
#[derive(Debug, Clone)]
pub struct QRCode {
    pub data: QRData,
    pub encoded_data: String,
    pub image_data: Option<Vec<u8>>,
}

impl QRCode {
    pub fn from_data(data: QRData) -> crate::Result<Self> {
        let encoded_data = serde_json::to_string(&data)
            .map_err(|e| crate::Error::Serialization(e.to_string()))?;
        
        Ok(Self {
            data,
            encoded_data,
            image_data: None,
        })
    }
    
    pub fn with_image(mut self, image_data: Vec<u8>) -> Self {
        self.image_data = Some(image_data);
        self
    }
}

/// Claims structures for different QR types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TicketClaims {
    pub event_id: String,
    pub event_name: String,
    pub seat: String,
    pub price_paid: String,
    pub purchaser_did: String,
    pub purchase_timestamp: String,
    pub valid_until: String,
    pub venue: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProductClaims {
    pub product_id: String,
    pub product_name: String,
    pub manufacturer: String,
    pub batch_number: String,
    pub manufacture_date: String,
    pub serial_number: String,
    pub materials: Vec<String>,
    pub supply_chain_hash: String,
    pub warranty_expires: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccessClaims {
    pub employee_id: String,
    pub employee_name: String,
    pub department: String,
    pub access_level: String,
    pub clearance: String,
    pub valid_from: String,
    pub valid_until: String,
    pub issued_by: String,
    pub access_zones: Vec<String>,
    pub emergency_contact: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IdentityClaims {
    pub identity_did: String,
    pub verification_type: String,
    pub age_over_21: bool,
    pub age_over_18: bool,
    pub professional_license: Option<String>,
    pub license_number: Option<String>,
    pub license_expires: Option<String>,
    pub verified_by: String,
    pub country: String,
    pub state: String,
    pub privacy_preserving: bool,
}

/// Helper functions to convert claims to HashMap for lemma creation
impl TicketClaims {
    pub fn to_claims_map(&self) -> HashMap<String, serde_json::Value> {
        let mut claims = HashMap::new();
        claims.insert("lemmaType".to_string(), serde_json::json!("event_ticket"));
        claims.insert("eventId".to_string(), serde_json::json!(self.event_id));
        claims.insert("eventName".to_string(), serde_json::json!(self.event_name));
        claims.insert("seat".to_string(), serde_json::json!(self.seat));
        claims.insert("pricePaid".to_string(), serde_json::json!(self.price_paid));
        claims.insert("purchaserDid".to_string(), serde_json::json!(self.purchaser_did));
        claims.insert("purchaseTimestamp".to_string(), serde_json::json!(self.purchase_timestamp));
        claims.insert("validUntil".to_string(), serde_json::json!(self.valid_until));
        claims.insert("venue".to_string(), serde_json::json!(self.venue));
        claims
    }
}

impl ProductClaims {
    pub fn to_claims_map(&self) -> HashMap<String, serde_json::Value> {
        let mut claims = HashMap::new();
        claims.insert("lemmaType".to_string(), serde_json::json!("product_authenticity"));
        claims.insert("productId".to_string(), serde_json::json!(self.product_id));
        claims.insert("productName".to_string(), serde_json::json!(self.product_name));
        claims.insert("manufacturer".to_string(), serde_json::json!(self.manufacturer));
        claims.insert("batchNumber".to_string(), serde_json::json!(self.batch_number));
        claims.insert("manufactureDate".to_string(), serde_json::json!(self.manufacture_date));
        claims.insert("serialNumber".to_string(), serde_json::json!(self.serial_number));
        claims.insert("materials".to_string(), serde_json::json!(self.materials));
        claims.insert("supplyChainHash".to_string(), serde_json::json!(self.supply_chain_hash));
        claims.insert("warrantyExpires".to_string(), serde_json::json!(self.warranty_expires));
        claims
    }
}

impl AccessClaims {
    pub fn to_claims_map(&self) -> HashMap<String, serde_json::Value> {
        let mut claims = HashMap::new();
        claims.insert("lemmaType".to_string(), serde_json::json!("access_control"));
        claims.insert("employeeId".to_string(), serde_json::json!(self.employee_id));
        claims.insert("employeeName".to_string(), serde_json::json!(self.employee_name));
        claims.insert("department".to_string(), serde_json::json!(self.department));
        claims.insert("accessLevel".to_string(), serde_json::json!(self.access_level));
        claims.insert("clearance".to_string(), serde_json::json!(self.clearance));
        claims.insert("validFrom".to_string(), serde_json::json!(self.valid_from));
        claims.insert("validUntil".to_string(), serde_json::json!(self.valid_until));
        claims.insert("issuedBy".to_string(), serde_json::json!(self.issued_by));
        claims.insert("accessZones".to_string(), serde_json::json!(self.access_zones));
        claims.insert("emergencyContact".to_string(), serde_json::json!(self.emergency_contact));
        claims
    }
}

impl IdentityClaims {
    pub fn to_claims_map(&self) -> HashMap<String, serde_json::Value> {
        let mut claims = HashMap::new();
        claims.insert("lemmaType".to_string(), serde_json::json!("identity_verification"));
        claims.insert("identityDid".to_string(), serde_json::json!(self.identity_did));
        claims.insert("verificationType".to_string(), serde_json::json!(self.verification_type));
        claims.insert("ageOver21".to_string(), serde_json::json!(self.age_over_21));
        claims.insert("ageOver18".to_string(), serde_json::json!(self.age_over_18));
        claims.insert("professionalLicense".to_string(), serde_json::json!(self.professional_license));
        claims.insert("licenseNumber".to_string(), serde_json::json!(self.license_number));
        claims.insert("licenseExpires".to_string(), serde_json::json!(self.license_expires));
        claims.insert("verifiedBy".to_string(), serde_json::json!(self.verified_by));
        claims.insert("country".to_string(), serde_json::json!(self.country));
        claims.insert("state".to_string(), serde_json::json!(self.state));
        claims.insert("privacyPreserving".to_string(), serde_json::json!(self.privacy_preserving));
        claims
    }
} 