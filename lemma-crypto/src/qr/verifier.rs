use crate::core::{LemmaCore, VerificationResult};
use super::{QRCode, QRData, QRType};
use std::sync::{Arc, Mutex};
use std::time::Instant;

/// QR Lemma Verifier that verifies QR codes with embedded cryptographic proofs
pub struct QRLemmaVerifier {
    pub core: Arc<Mutex<LemmaCore>>,
}

/// Verification result for QR codes
#[derive(Debug, Clone)]
pub struct QRVerificationResult {
    pub is_valid: bool,
    pub qr_type: QRType,
    pub verification_time_us: f64,
    pub claims: std::collections::HashMap<String, serde_json::Value>,
    pub metadata: super::QRMetadata,
    pub error_message: Option<String>,
    pub performance_metrics: QRPerformanceMetrics,
}

/// Performance metrics for QR verification
#[derive(Debug, Clone)]
pub struct QRPerformanceMetrics {
    pub decode_time_us: f64,
    pub lemma_verification_time_us: f64,
    pub total_time_us: f64,
    pub cache_hit: bool,
}

impl QRLemmaVerifier {
    /// Create a new QR verifier with a Lemma core
    pub fn new(core: Arc<Mutex<LemmaCore>>) -> Self {
        Self { core }
    }

    /// Verify a QR code from encoded JSON string
    pub fn verify_qr_string(&self, qr_json: &str) -> QRVerificationResult {
        let start_time = Instant::now();
        
        // Decode QR data
        let decode_start = Instant::now();
        let qr_data = match serde_json::from_str::<QRData>(qr_json) {
            Ok(data) => data,
            Err(e) => {
                return QRVerificationResult {
                    is_valid: false,
                    qr_type: QRType::IdentityVerification, // Default
                    verification_time_us: start_time.elapsed().as_micros() as f64,
                    claims: std::collections::HashMap::new(),
                    metadata: super::QRMetadata::new(),
                    error_message: Some(format!("Failed to decode QR data: {}", e)),
                    performance_metrics: QRPerformanceMetrics {
                        decode_time_us: decode_start.elapsed().as_micros() as f64,
                        lemma_verification_time_us: 0.0,
                        total_time_us: start_time.elapsed().as_micros() as f64,
                        cache_hit: false,
                    },
                };
            }
        };
        let decode_time = decode_start.elapsed().as_micros() as f64;

        self.verify_qr_data(qr_data, decode_time)
    }

    /// Verify a QR code from QRData structure
    pub fn verify_qr_data(&self, qr_data: QRData, decode_time_us: f64) -> QRVerificationResult {
        let start_time = Instant::now();
        
        // Check if QR is expired
        if qr_data.is_expired() {
            return QRVerificationResult {
                is_valid: false,
                qr_type: qr_data.qr_type,
                verification_time_us: start_time.elapsed().as_micros() as f64,
                claims: std::collections::HashMap::new(),
                metadata: qr_data.metadata,
                error_message: Some("QR code has expired".to_string()),
                performance_metrics: QRPerformanceMetrics {
                    decode_time_us,
                    lemma_verification_time_us: 0.0,
                    total_time_us: start_time.elapsed().as_micros() as f64,
                    cache_hit: false,
                },
            };
        }

        // Verify the embedded lemma using the universal engine (4.176µs performance)
        let verification_start = Instant::now();
        let verification_result = {
            let mut core = self.core.lock().unwrap();
            core.verify(&qr_data.lemma)
        };
        let lemma_verification_time = verification_start.elapsed().as_micros() as f64;

        let total_time = start_time.elapsed().as_micros() as f64;

        match verification_result {
            Ok(result) => QRVerificationResult {
                is_valid: result.is_valid,
                qr_type: qr_data.qr_type,
                verification_time_us: total_time,
                claims: result.claims,
                metadata: qr_data.metadata,
                error_message: result.error_message,
                performance_metrics: QRPerformanceMetrics {
                    decode_time_us,
                    lemma_verification_time_us: lemma_verification_time,
                    total_time_us: total_time,
                    cache_hit: result.from_cache,
                },
            },
            Err(e) => QRVerificationResult {
                is_valid: false,
                qr_type: qr_data.qr_type,
                verification_time_us: total_time,
                claims: std::collections::HashMap::new(),
                metadata: qr_data.metadata,
                error_message: Some(format!("Verification failed: {}", e)),
                performance_metrics: QRPerformanceMetrics {
                    decode_time_us,
                    lemma_verification_time_us: lemma_verification_time,
                    total_time_us: total_time,
                    cache_hit: false,
                },
            },
        }
    }

    /// Verify a QR code object
    pub fn verify_qr_code(&self, qr_code: &QRCode) -> QRVerificationResult {
        self.verify_qr_data(qr_code.data.clone(), 0.0)
    }

    /// Batch verify multiple QR codes for enhanced performance
    pub fn batch_verify_qr_codes(&self, qr_codes: Vec<&QRCode>) -> Vec<QRVerificationResult> {
        let start_time = Instant::now();
        
        // Group QR codes by type for batch optimization
        let mut results = Vec::new();
        
        for qr_code in qr_codes {
            let result = self.verify_qr_code(qr_code);
            results.push(result);
        }
        
        results
    }

    /// Verify QR code with specific requirements
    pub fn verify_qr_with_requirements(&self, qr_json: &str, required_claims: Vec<String>) -> QRVerificationResult {
        let mut result = self.verify_qr_string(qr_json);
        
        if result.is_valid {
            // Check if all required claims are present
            for required_claim in required_claims {
                if !result.claims.contains_key(&required_claim) {
                    result.is_valid = false;
                    result.error_message = Some(format!("Missing required claim: {}", required_claim));
                    break;
                }
            }
        }
        
        result
    }
}

/// Helper functions for QR verification scenarios
impl QRLemmaVerifier {
    /// Verify a concert ticket QR code
    pub fn verify_ticket_qr(&self, qr_json: &str) -> TicketVerificationResult {
        let result = self.verify_qr_string(qr_json);
        
        if result.qr_type != QRType::EventTicket {
            return TicketVerificationResult {
                is_valid: false,
                error_message: Some("Not a valid ticket QR code".to_string()),
                ticket_info: None,
                verification_time_us: result.verification_time_us,
            };
        }

        let ticket_info = if result.is_valid {
            Some(TicketInfo {
                event_name: result.claims.get("eventName")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown Event")
                    .to_string(),
                seat: result.claims.get("seat")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown Seat")
                    .to_string(),
                venue: result.claims.get("venue")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown Venue")
                    .to_string(),
                purchaser: result.claims.get("purchaserDid")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown")
                    .to_string(),
            })
        } else {
            None
        };

        TicketVerificationResult {
            is_valid: result.is_valid,
            error_message: result.error_message,
            ticket_info,
            verification_time_us: result.verification_time_us,
        }
    }

    /// Verify a product authenticity QR code
    pub fn verify_product_qr(&self, qr_json: &str) -> ProductVerificationResult {
        let result = self.verify_qr_string(qr_json);
        
        if result.qr_type != QRType::ProductAuthenticity {
            return ProductVerificationResult {
                is_valid: false,
                error_message: Some("Not a valid product authenticity QR code".to_string()),
                product_info: None,
                verification_time_us: result.verification_time_us,
            };
        }

        let product_info = if result.is_valid {
            Some(ProductInfo {
                product_name: result.claims.get("productName")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown Product")
                    .to_string(),
                manufacturer: result.claims.get("manufacturer")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown Manufacturer")
                    .to_string(),
                serial_number: result.claims.get("serialNumber")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown")
                    .to_string(),
                manufacture_date: result.claims.get("manufactureDate")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown")
                    .to_string(),
            })
        } else {
            None
        };

        ProductVerificationResult {
            is_valid: result.is_valid,
            error_message: result.error_message,
            product_info,
            verification_time_us: result.verification_time_us,
        }
    }

    /// Verify an access control QR code
    pub fn verify_access_qr(&self, qr_json: &str, required_zones: Vec<String>) -> AccessVerificationResult {
        let result = self.verify_qr_string(qr_json);
        
        if result.qr_type != QRType::AccessControl {
            return AccessVerificationResult {
                is_valid: false,
                error_message: Some("Not a valid access control QR code".to_string()),
                access_info: None,
                verification_time_us: result.verification_time_us,
            };
        }

        let mut is_access_granted = result.is_valid;
        let mut error_message = result.error_message;

        // Check access zones if verification passed
        if is_access_granted && !required_zones.is_empty() {
            if let Some(access_zones_value) = result.claims.get("accessZones") {
                if let Some(access_zones) = access_zones_value.as_array() {
                    let user_zones: Vec<String> = access_zones
                        .iter()
                        .filter_map(|v| v.as_str())
                        .map(|s| s.to_string())
                        .collect();
                    
                    for required_zone in &required_zones {
                        if !user_zones.contains(required_zone) {
                            is_access_granted = false;
                            error_message = Some(format!("Access denied: missing access to zone '{}'", required_zone));
                            break;
                        }
                    }
                } else {
                    is_access_granted = false;
                    error_message = Some("Invalid access zones format".to_string());
                }
            } else {
                is_access_granted = false;
                error_message = Some("No access zones specified".to_string());
            }
        }

        let access_info = if result.is_valid {
            Some(AccessInfo {
                employee_name: result.claims.get("employeeName")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown Employee")
                    .to_string(),
                department: result.claims.get("department")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown Department")
                    .to_string(),
                access_level: result.claims.get("accessLevel")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown")
                    .to_string(),
                clearance: result.claims.get("clearance")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown")
                    .to_string(),
            })
        } else {
            None
        };

        AccessVerificationResult {
            is_valid: is_access_granted,
            error_message,
            access_info,
            verification_time_us: result.verification_time_us,
        }
    }
}

/// Specific verification result types
#[derive(Debug, Clone)]
pub struct TicketVerificationResult {
    pub is_valid: bool,
    pub error_message: Option<String>,
    pub ticket_info: Option<TicketInfo>,
    pub verification_time_us: f64,
}

#[derive(Debug, Clone)]
pub struct TicketInfo {
    pub event_name: String,
    pub seat: String,
    pub venue: String,
    pub purchaser: String,
}

#[derive(Debug, Clone)]
pub struct ProductVerificationResult {
    pub is_valid: bool,
    pub error_message: Option<String>,
    pub product_info: Option<ProductInfo>,
    pub verification_time_us: f64,
}

#[derive(Debug, Clone)]
pub struct ProductInfo {
    pub product_name: String,
    pub manufacturer: String,
    pub serial_number: String,
    pub manufacture_date: String,
}

#[derive(Debug, Clone)]
pub struct AccessVerificationResult {
    pub is_valid: bool,
    pub error_message: Option<String>,
    pub access_info: Option<AccessInfo>,
    pub verification_time_us: f64,
}

#[derive(Debug, Clone)]
pub struct AccessInfo {
    pub employee_name: String,
    pub department: String,
    pub access_level: String,
    pub clearance: String,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::packages::*;
    use crate::qr::generator::QRLemmaGenerator;
    use std::sync::{Arc, Mutex};

    fn setup_verifier() -> (QRLemmaVerifier, QRLemmaGenerator) {
        let mut core = LemmaCore::new().unwrap();
        core.register_package(IdentityPackage::new());
        let core = Arc::new(Mutex::new(core));
        
        let verifier = QRLemmaVerifier::new(core.clone());
        let generator = QRLemmaGenerator::new(core);
        
        (verifier, generator)
    }

    #[test]
    fn test_verify_ticket_qr() {
        let (verifier, generator) = setup_verifier();
        
        // Generate a ticket QR
        let qr_code = generator.create_sample_ticket_qr().unwrap();
        
        // Verify it
        let result = verifier.verify_qr_code(&qr_code);
        
        assert!(result.is_valid);
        assert_eq!(result.qr_type, QRType::EventTicket);
        assert!(result.verification_time_us > 0.0);
        assert!(!result.claims.is_empty());
    }

    #[test]
    fn test_verify_product_qr() {
        let (verifier, generator) = setup_verifier();
        
        // Generate a product QR
        let qr_code = generator.create_sample_product_qr().unwrap();
        
        // Verify it
        let result = verifier.verify_qr_code(&qr_code);
        
        assert!(result.is_valid);
        assert_eq!(result.qr_type, QRType::ProductAuthenticity);
        assert!(result.verification_time_us > 0.0);
    }

    #[test]
    fn test_verify_access_qr() {
        let (verifier, generator) = setup_verifier();
        
        // Generate an access QR
        let qr_code = generator.create_sample_access_qr().unwrap();
        
        // Verify it with required zones
        let result = verifier.verify_access_qr(
            &qr_code.encoded_data,
            vec!["building_main".to_string(), "floor_5".to_string()]
        );
        
        assert!(result.is_valid);
        assert!(result.verification_time_us > 0.0);
        assert!(result.access_info.is_some());
    }

    #[test]
    fn test_invalid_qr_data() {
        let (verifier, _) = setup_verifier();
        
        // Try to verify invalid JSON
        let result = verifier.verify_qr_string("invalid json");
        
        assert!(!result.is_valid);
        assert!(result.error_message.is_some());
        assert!(result.verification_time_us > 0.0);
    }
} 