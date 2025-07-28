use crate::core::LemmaCore;
use crate::credentials::LemmaCredential;
use super::{QRCode, QRData, QRType, QRMetadata, TicketClaims, ProductClaims, AccessClaims, IdentityClaims};
use std::sync::{Arc, Mutex};

/// QR Lemma Generator that creates QR codes with embedded cryptographic proofs
pub struct QRLemmaGenerator {
    pub core: Arc<Mutex<LemmaCore>>,
}

impl QRLemmaGenerator {
    /// Create a new QR generator with a Lemma core
    pub fn new(core: Arc<Mutex<LemmaCore>>) -> Self {
        Self { core }
    }

    /// Generate a ticket QR code with embedded lemma
    pub fn generate_ticket_qr(&self, claims: TicketClaims) -> crate::Result<QRCode> {
        let claims_map = claims.to_claims_map();
        
        // Create lemma using the universal engine (4.176µs performance)
        let lemma = {
            let mut core = self.core.lock().unwrap();
            core.create_lemma(&claims_map)?
        };
        
        // Create QR metadata
        let metadata = QRMetadata::new()
            .with_issuer("did:lemma:ticket_issuer".to_string());
        
        // Create QR data structure
        let qr_data = QRData::new(lemma, QRType::EventTicket, metadata);
        
        // Generate QR code
        QRCode::from_data(qr_data)
    }

    /// Generate a product authenticity QR code with embedded lemma
    pub fn generate_product_qr(&self, claims: ProductClaims) -> crate::Result<QRCode> {
        let claims_map = claims.to_claims_map();
        
        // Create lemma using the universal engine (4.176µs performance)
        let lemma = {
            let mut core = self.core.lock().unwrap();
            core.create_lemma(&claims_map)?
        };
        
        // Create QR metadata
        let metadata = QRMetadata::new()
            .with_issuer(claims.manufacturer.clone());
        
        // Create QR data structure
        let qr_data = QRData::new(lemma, QRType::ProductAuthenticity, metadata);
        
        // Generate QR code
        QRCode::from_data(qr_data)
    }

    /// Generate an access control QR code with embedded lemma
    pub fn generate_access_qr(&self, claims: AccessClaims) -> crate::Result<QRCode> {
        let claims_map = claims.to_claims_map();
        
        // Create lemma using the universal engine (4.176µs performance)
        let lemma = {
            let mut core = self.core.lock().unwrap();
            core.create_lemma(&claims_map)?
        };
        
        // Parse expiry time for metadata
        let expires_at = chrono::DateTime::parse_from_rfc3339(&claims.valid_until)
            .map(|dt| dt.timestamp() as u64)
            .ok();
        
        // Create QR metadata
        let mut metadata = QRMetadata::new()
            .with_issuer(claims.issued_by.clone());
        
        if let Some(expiry) = expires_at {
            metadata = metadata.with_expiry(expiry);
        }
        
        // Create QR data structure
        let qr_data = QRData::new(lemma, QRType::AccessControl, metadata);
        
        // Generate QR code
        QRCode::from_data(qr_data)
    }

    /// Generate an identity verification QR code with embedded lemma
    pub fn generate_identity_qr(&self, claims: IdentityClaims) -> crate::Result<QRCode> {
        let claims_map = claims.to_claims_map();
        
        // Create lemma using the universal engine (4.176µs performance)
        let lemma = {
            let mut core = self.core.lock().unwrap();
            core.create_lemma(&claims_map)?
        };
        
        // Create QR metadata
        let metadata = QRMetadata::new()
            .with_issuer(claims.verified_by.clone());
        
        // Create QR data structure
        let qr_data = QRData::new(lemma, QRType::IdentityVerification, metadata);
        
        // Generate QR code
        QRCode::from_data(qr_data)
    }

    /// Generate a QR code from generic claims map
    pub fn generate_generic_qr(&self, claims: std::collections::HashMap<String, serde_json::Value>, qr_type: QRType) -> crate::Result<QRCode> {
        // Create lemma using the universal engine (4.176µs performance)
        let lemma = {
            let mut core = self.core.lock().unwrap();
            core.create_lemma(&claims)?
        };
        
        // Create QR metadata
        let metadata = QRMetadata::new();
        
        // Create QR data structure
        let qr_data = QRData::new(lemma, qr_type, metadata);
        
        // Generate QR code
        QRCode::from_data(qr_data)
    }
}

/// Helper functions for creating sample QR codes
impl QRLemmaGenerator {
    /// Create a sample concert ticket QR
    pub fn create_sample_ticket_qr(&self) -> crate::Result<QRCode> {
        let claims = TicketClaims {
            event_id: "concert_2024_001".to_string(),
            event_name: "Summer Music Festival".to_string(),
            seat: "Section A, Row 15, Seat 8".to_string(),
            price_paid: "$120.00".to_string(),
            purchaser_did: "did:lemma:user_123".to_string(),
            purchase_timestamp: "2024-07-15T14:30:00Z".to_string(),
            valid_until: "2024-12-31T23:59:59Z".to_string(),
            venue: "Madison Square Garden".to_string(),
        };
        
        self.generate_ticket_qr(claims)
    }

    /// Create a sample luxury product QR
    pub fn create_sample_product_qr(&self) -> crate::Result<QRCode> {
        let claims = ProductClaims {
            product_id: "luxury_watch_SW_001".to_string(),
            product_name: "Submariner Professional".to_string(),
            manufacturer: "did:lemma:swiss_watches".to_string(),
            batch_number: "BATCH_2024_Q3_001".to_string(),
            manufacture_date: "2024-07-15".to_string(),
            serial_number: "SW123456789".to_string(),
            materials: vec!["steel".to_string(), "sapphire_crystal".to_string(), "ceramic_bezel".to_string()],
            supply_chain_hash: "0x123456789abcdef".to_string(),
            warranty_expires: "2026-07-15".to_string(),
        };
        
        self.generate_product_qr(claims)
    }

    /// Create a sample access control QR
    pub fn create_sample_access_qr(&self) -> crate::Result<QRCode> {
        let claims = AccessClaims {
            employee_id: "EMP_001".to_string(),
            employee_name: "John Smith".to_string(),
            department: "Engineering".to_string(),
            access_level: "floor_5_conference_rooms".to_string(),
            clearance: "standard".to_string(),
            valid_from: "2024-07-01T00:00:00Z".to_string(),
            valid_until: "2024-12-31T23:59:59Z".to_string(),
            issued_by: "did:lemma:hr_department".to_string(),
            access_zones: vec!["building_main".to_string(), "floor_5".to_string(), "conference_rooms".to_string()],
            emergency_contact: "+1-555-0123".to_string(),
        };
        
        self.generate_access_qr(claims)
    }

    /// Create a sample identity verification QR
    pub fn create_sample_identity_qr(&self) -> crate::Result<QRCode> {
        let claims = IdentityClaims {
            identity_did: "did:lemma:person_123".to_string(),
            verification_type: "age_and_profession".to_string(),
            age_over_21: true,
            age_over_18: true,
            professional_license: Some("medical_doctor".to_string()),
            license_number: Some("MD123456".to_string()),
            license_expires: Some("2026-05-15".to_string()),
            verified_by: "did:lemma:state_medical_board".to_string(),
            country: "USA".to_string(),
            state: "California".to_string(),
            privacy_preserving: true,
        };
        
        self.generate_identity_qr(claims)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::packages::*;
    use std::sync::{Arc, Mutex};

    fn setup_generator() -> QRLemmaGenerator {
        let mut core = LemmaCore::new().unwrap();
        core.register_package(IdentityPackage::new());
        QRLemmaGenerator::new(Arc::new(Mutex::new(core)))
    }

    #[test]
    fn test_generate_ticket_qr() {
        let generator = setup_generator();
        let result = generator.create_sample_ticket_qr();
        assert!(result.is_ok());
        
        let qr_code = result.unwrap();
        assert_eq!(qr_code.data.qr_type, QRType::EventTicket);
        assert!(!qr_code.encoded_data.is_empty());
    }

    #[test]
    fn test_generate_product_qr() {
        let generator = setup_generator();
        let result = generator.create_sample_product_qr();
        assert!(result.is_ok());
        
        let qr_code = result.unwrap();
        assert_eq!(qr_code.data.qr_type, QRType::ProductAuthenticity);
        assert!(!qr_code.encoded_data.is_empty());
    }

    #[test]
    fn test_generate_access_qr() {
        let generator = setup_generator();
        let result = generator.create_sample_access_qr();
        assert!(result.is_ok());
        
        let qr_code = result.unwrap();
        assert_eq!(qr_code.data.qr_type, QRType::AccessControl);
        assert!(!qr_code.encoded_data.is_empty());
    }

    #[test]
    fn test_generate_identity_qr() {
        let generator = setup_generator();
        let result = generator.create_sample_identity_qr();
        assert!(result.is_ok());
        
        let qr_code = result.unwrap();
        assert_eq!(qr_code.data.qr_type, QRType::IdentityVerification);
        assert!(!qr_code.encoded_data.is_empty());
    }
} 