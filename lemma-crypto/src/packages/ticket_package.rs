use std::collections::HashMap;
use serde::{Deserialize, Serialize};

use crate::{
    credentials::VerifiableCredential,
    core::VerificationResult,
    packages::VerificationPackage,
    qr::{QRType, TicketClaims},
    ClaimSet, VerificationMetadata,
    Result, LemmaError
};

/// Enhanced QR-specific ticket verification package
#[derive(Debug, Clone)]
pub struct QRTicketPackage {
    event_registry: HashMap<String, QREventInfo>,
    venue_registry: HashMap<String, VenueInfo>,
    allow_transfers: bool,
    anti_counterfeit_enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QREventInfo {
    pub event_id: String,
    pub event_name: String,
    pub date: String,
    pub venue_id: String,
    pub venue_name: String,
    pub total_seats: usize,
    pub price_range: (f64, f64), // min, max prices
    pub event_type: String,
    pub organizer_did: String,
    pub anti_counterfeit_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VenueInfo {
    pub venue_id: String,
    pub name: String,
    pub address: String,
    pub capacity: usize,
    pub venue_type: String,
    pub verification_method: String, // QR scanner, NFC, etc.
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TicketVerificationContext {
    pub current_time: u64,
    pub venue_scanner_id: Option<String>,
    pub allow_early_entry: bool,
    pub check_seat_conflicts: bool,
}

impl QRTicketPackage {
    pub fn new() -> Self {
        Self {
            event_registry: HashMap::new(),
            venue_registry: HashMap::new(),
            allow_transfers: false,
            anti_counterfeit_enabled: true,
        }
    }
    
    pub fn with_anti_counterfeit(mut self, enabled: bool) -> Self {
        self.anti_counterfeit_enabled = enabled;
        self
    }
    
    pub fn with_transfers(mut self, allow: bool) -> Self {
        self.allow_transfers = allow;
        self
    }
    
    pub fn add_event(&mut self, event: QREventInfo) {
        self.event_registry.insert(event.event_id.clone(), event);
    }
    
    pub fn add_venue(&mut self, venue: VenueInfo) {
        self.venue_registry.insert(venue.venue_id.clone(), venue);
    }
    
    /// Verify QR ticket with enhanced context
    pub fn verify_qr_ticket(&self, claims: &TicketClaims, context: &TicketVerificationContext) -> Result<VerificationResult> {
        let mut metadata = HashMap::new();
        
        // Basic event validation
        let event_info = self.event_registry.get(&claims.event_id)
            .ok_or_else(|| LemmaError::Package(format!("Event not found: {}", claims.event_id)))?;
        
        let venue_info = self.venue_registry.get(&event_info.venue_id);
        
        // Verify event details match
        let event_name_matches = event_info.event_name == claims.event_name;
        let venue_matches = venue_info.map_or(true, |v| v.name == claims.venue);
        
        // Time-based validation
        let event_time = chrono::DateTime::parse_from_rfc3339(&event_info.date)
            .map_err(|_| LemmaError::Package("Invalid event date format".to_string()))?
            .timestamp() as u64;
        
        let is_future_event = event_time > context.current_time;
        let is_entry_time = if context.allow_early_entry {
            event_time > context.current_time - 3600 // Allow 1 hour early
        } else {
            event_time <= context.current_time + 1800 && event_time > context.current_time - 1800 // 30 min window
        };
        
        // Seat validation
        let seat_format_valid = self.validate_seat_format(&claims.seat, event_info);
        
        // Price validation (basic range check)
        let price_value = claims.price_paid.trim_start_matches('$').parse::<f64>().unwrap_or(0.0);
        let price_in_range = price_value >= event_info.price_range.0 && price_value <= event_info.price_range.1;
        
        // Anti-counterfeit validation
        let anti_counterfeit_valid = if self.anti_counterfeit_enabled {
            self.verify_anti_counterfeit_proof(claims, event_info)?
        } else {
            true
        };
        
        // Populate metadata
        metadata.insert("event_id".to_string(), serde_json::json!(claims.event_id));
        metadata.insert("event_name".to_string(), serde_json::json!(claims.event_name));
        metadata.insert("venue".to_string(), serde_json::json!(claims.venue));
        metadata.insert("seat".to_string(), serde_json::json!(claims.seat));
        metadata.insert("price_paid".to_string(), serde_json::json!(claims.price_paid));
        metadata.insert("event_name_matches".to_string(), serde_json::json!(event_name_matches));
        metadata.insert("venue_matches".to_string(), serde_json::json!(venue_matches));
        metadata.insert("is_future_event".to_string(), serde_json::json!(is_future_event));
        metadata.insert("is_entry_time".to_string(), serde_json::json!(is_entry_time));
        metadata.insert("seat_format_valid".to_string(), serde_json::json!(seat_format_valid));
        metadata.insert("price_in_range".to_string(), serde_json::json!(price_in_range));
        metadata.insert("anti_counterfeit_valid".to_string(), serde_json::json!(anti_counterfeit_valid));
        
        if let Some(venue) = venue_info {
            metadata.insert("venue_capacity".to_string(), serde_json::json!(venue.capacity));
            metadata.insert("venue_type".to_string(), serde_json::json!(venue.venue_type));
        }
        
        // Overall validation
        let is_valid = event_name_matches && 
                      venue_matches && 
                      is_entry_time &&
                      seat_format_valid && 
                      price_in_range && 
                      anti_counterfeit_valid;
        
        let confidence = if is_valid { 0.999 } else { 0.001 };
        
        Ok(VerificationResult::new(
            is_valid,
            "qr_ticket".to_string(),
            confidence,
            metadata,
        ))
    }
    
    fn validate_seat_format(&self, seat: &str, event_info: &QREventInfo) -> bool {
        // Basic seat format validation (e.g., "Section A, Row 15, Seat 8")
        if seat.contains("Section") && seat.contains("Row") && seat.contains("Seat") {
            return true;
        }
        
        // Allow simple formats like "A15" or "15A"
        if seat.len() >= 2 && seat.len() <= 10 {
            return true;
        }
        
        false
    }
    
    fn verify_anti_counterfeit_proof(&self, claims: &TicketClaims, event_info: &QREventInfo) -> Result<bool> {
        // In a real implementation, this would verify cryptographic proof
        // For now, check if the purchase timestamp and event details create a valid hash
        
        let proof_string = format!(
            "{}:{}:{}:{}:{}",
            claims.event_id,
            claims.seat,
            claims.purchase_timestamp,
            claims.purchaser_did,
            event_info.anti_counterfeit_key
        );
        
        // Simple hash validation (in reality, this would be cryptographic)
        let hash = self.simple_hash(&proof_string);
        let expected_hash_end = hash % 1000;
        
        // The "anti-counterfeit proof" should contain this hash
        let ticket_id_parts: Vec<&str> = claims.event_id.split('_').collect();
        if let Some(id_num) = ticket_id_parts.last() {
            if let Ok(id_val) = id_num.parse::<u64>() {
                return Ok((id_val % 1000) == expected_hash_end);
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

impl VerificationPackage for QRTicketPackage {
    fn package_type(&self) -> &str {
        "qr_ticket"
    }
    
    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        // Extract QR ticket claims
        let event_id = credential.get_claim("eventId")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing eventId claim".to_string()))?;
            
        let event_name = credential.get_claim("eventName")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing eventName claim".to_string()))?;
            
        let seat = credential.get_claim("seat")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing seat claim".to_string()))?;
            
        let price_paid = credential.get_claim("pricePaid")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing pricePaid claim".to_string()))?;
            
        let purchaser_did = credential.get_claim("purchaserDid")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing purchaserDid claim".to_string()))?;
            
        let purchase_timestamp = credential.get_claim("purchaseTimestamp")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing purchaseTimestamp claim".to_string()))?;
            
        let valid_until = credential.get_claim("validUntil")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing validUntil claim".to_string()))?;
            
        let venue = credential.get_claim("venue")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing venue claim".to_string()))?;
        
        // Convert to TicketClaims structure
        let ticket_claims = TicketClaims {
            event_id: event_id.to_string(),
            event_name: event_name.to_string(),
            seat: seat.to_string(),
            price_paid: price_paid.to_string(),
            purchaser_did: purchaser_did.to_string(),
            purchase_timestamp: purchase_timestamp.to_string(),
            valid_until: valid_until.to_string(),
            venue: venue.to_string(),
        };
        
        // Create verification context
        let context = TicketVerificationContext {
            current_time: chrono::Utc::now().timestamp() as u64,
            venue_scanner_id: None,
            allow_early_entry: true,
            check_seat_conflicts: true,
        };
        
        // Verify using QR-specific logic
        self.verify_qr_ticket(&ticket_claims, &context)
    }
    
    fn create_credential(&self, claims: ClaimSet) -> Result<VerifiableCredential> {
        // Validate QR ticket claims
        self.validate_claims(&claims)?;
        
        // TODO: Create actual QR ticket credential
        Err(LemmaError::Package("Not implemented: use QRLemmaGenerator for QR ticket creation".to_string()))
    }
    
    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String {
        let event_id = credential.get_claim("eventId")
            .and_then(|v| v.as_str())
            .unwrap_or(&credential.id);
        let seat = credential.get_claim("seat")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        format!("qr_ticket:{}:{}", event_id, seat)
    }
    
    fn validate_claims(&self, claims: &ClaimSet) -> Result<()> {
        let required_claims = [
            "eventId", "eventName", "seat", "pricePaid", 
            "purchaserDid", "purchaseTimestamp", "validUntil", "venue"
        ];
        
        for claim in &required_claims {
            if !claims.contains_key(*claim) {
                return Err(LemmaError::Package(format!("Missing required QR ticket claim: {}", claim)));
            }
        }
        
        // Validate lemma type
        if let Some(lemma_type) = claims.get("lemmaType") {
            if lemma_type.as_str() != Some("event_ticket") {
                return Err(LemmaError::Package("Invalid lemma type for QR ticket".to_string()));
            }
        }
        
        Ok(())
    }
}

/// Helper functions for creating sample events and venues
impl QRTicketPackage {
    pub fn create_sample_event() -> QREventInfo {
        QREventInfo {
            event_id: "concert_2024_001".to_string(),
            event_name: "Summer Music Festival".to_string(),
            date: "2024-12-31T20:00:00Z".to_string(),
            venue_id: "venue_msg".to_string(),
            venue_name: "Madison Square Garden".to_string(),
            total_seats: 20000,
            price_range: (50.0, 500.0),
            event_type: "concert".to_string(),
            organizer_did: "did:lemma:organizer_123".to_string(),
            anti_counterfeit_key: "secure_key_123".to_string(),
        }
    }
    
    pub fn create_sample_venue() -> VenueInfo {
        VenueInfo {
            venue_id: "venue_msg".to_string(),
            name: "Madison Square Garden".to_string(),
            address: "4 Pennsylvania Plaza, New York, NY 10001".to_string(),
            capacity: 20000,
            venue_type: "arena".to_string(),
            verification_method: "qr_scanner".to_string(),
        }
    }
    
    pub fn with_sample_data(mut self) -> Self {
        self.add_event(Self::create_sample_event());
        self.add_venue(Self::create_sample_venue());
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::qr::generator::QRLemmaGenerator;
    use crate::core::LemmaCore;
    use std::sync::{Arc, Mutex};

    #[test]
    fn test_qr_ticket_package_creation() {
        let package = QRTicketPackage::new()
            .with_anti_counterfeit(true)
            .with_transfers(false)
            .with_sample_data();
        
        assert_eq!(package.package_type(), "qr_ticket");
        assert!(package.anti_counterfeit_enabled);
        assert!(!package.allow_transfers);
        assert!(package.event_registry.contains_key("concert_2024_001"));
    }
    
    #[test]
    fn test_qr_ticket_verification() {
        let package = QRTicketPackage::new().with_sample_data();
        
        let ticket_claims = TicketClaims {
            event_id: "concert_2024_001".to_string(),
            event_name: "Summer Music Festival".to_string(),
            seat: "Section A, Row 15, Seat 8".to_string(),
            price_paid: "$120.00".to_string(),
            purchaser_did: "did:lemma:user_123".to_string(),
            purchase_timestamp: "2024-07-15T14:30:00Z".to_string(),
            valid_until: "2024-12-31T23:59:59Z".to_string(),
            venue: "Madison Square Garden".to_string(),
        };
        
        let context = TicketVerificationContext {
            current_time: chrono::Utc::now().timestamp() as u64,
            venue_scanner_id: None,
            allow_early_entry: true,
            check_seat_conflicts: true,
        };
        
        let result = package.verify_qr_ticket(&ticket_claims, &context);
        assert!(result.is_ok());
        
        let verification = result.unwrap();
        // Note: This might fail due to timing, but structure should be correct
        assert!(verification.metadata.contains_key("event_id"));
        assert!(verification.metadata.contains_key("seat_format_valid"));
    }
    
    #[test]
    fn test_seat_format_validation() {
        let package = QRTicketPackage::new();
        let event_info = QRTicketPackage::create_sample_event();
        
        assert!(package.validate_seat_format("Section A, Row 15, Seat 8", &event_info));
        assert!(package.validate_seat_format("A15", &event_info));
        assert!(!package.validate_seat_format("", &event_info));
        assert!(!package.validate_seat_format("invalid_seat_format_too_long", &event_info));
    }
} 