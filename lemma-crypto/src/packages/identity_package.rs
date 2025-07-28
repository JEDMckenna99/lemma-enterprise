use std::collections::HashMap;
use serde::{Deserialize, Serialize};

use crate::{
    credentials::VerifiableCredential,
    core::VerificationResult,
    packages::VerificationPackage,
    qr::{QRType, IdentityClaims},
    ClaimSet, VerificationMetadata,
    Result, LemmaError
};

/// Enhanced QR-specific identity verification package
#[derive(Debug, Clone)]
pub struct QRIdentityPackage {
    issuer_registry: HashMap<String, IdentityIssuerInfo>,
    license_registry: HashMap<String, LicenseInfo>,
    verification_standards: HashMap<String, VerificationStandard>,
    enable_age_verification: bool,
    enable_professional_verification: bool,
    enable_privacy_preservation: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IdentityIssuerInfo {
    pub did: String,
    pub name: String,
    pub issuer_type: String, // "government", "professional_board", "educational", "corporate"
    pub country: String,
    pub state: Option<String>,
    pub verified: bool,
    pub public_key: String,
    pub trust_score: f64, // 0.0-1.0
    pub issued_credentials: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LicenseInfo {
    pub license_type: String,
    pub issuing_authority: String,
    pub validation_endpoint: Option<String>,
    pub verification_method: String,
    pub renewal_required: bool,
    pub renewal_period_months: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerificationStandard {
    pub standard_name: String,
    pub required_evidence_level: String, // "basic", "enhanced", "superior"
    pub age_verification_method: String,
    pub biometric_required: bool,
    pub document_verification_required: bool,
    pub in_person_verification_required: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IdentityVerificationContext {
    pub current_time: u64,
    pub verifier_location: Option<String>,
    pub check_professional_licenses: bool,
    pub check_age_restrictions: bool,
    pub minimum_age_requirement: Option<u8>,
    pub accept_privacy_preserving: bool,
    pub required_verification_level: String,
}

impl QRIdentityPackage {
    pub fn new() -> Self {
        Self {
            issuer_registry: HashMap::new(),
            license_registry: HashMap::new(),
            verification_standards: HashMap::new(),
            enable_age_verification: true,
            enable_professional_verification: true,
            enable_privacy_preservation: true,
        }
    }
    
    pub fn with_age_verification(mut self, enabled: bool) -> Self {
        self.enable_age_verification = enabled;
        self
    }
    
    pub fn with_professional_verification(mut self, enabled: bool) -> Self {
        self.enable_professional_verification = enabled;
        self
    }
    
    pub fn with_privacy_preservation(mut self, enabled: bool) -> Self {
        self.enable_privacy_preservation = enabled;
        self
    }
    
    pub fn add_issuer(&mut self, issuer: IdentityIssuerInfo) {
        self.issuer_registry.insert(issuer.did.clone(), issuer);
    }
    
    pub fn add_license(&mut self, license_type: String, license: LicenseInfo) {
        self.license_registry.insert(license_type, license);
    }
    
    pub fn add_verification_standard(&mut self, standard: VerificationStandard) {
        self.verification_standards.insert(standard.standard_name.clone(), standard);
    }
    
    /// Verify QR identity with enhanced context
    pub fn verify_qr_identity(&self, claims: &IdentityClaims, context: &IdentityVerificationContext) -> Result<VerificationResult> {
        let mut metadata = HashMap::new();
        
        // Basic issuer validation
        let issuer_info = self.issuer_registry.get(&claims.verified_by)
            .ok_or_else(|| LemmaError::Package(format!("Identity issuer not found: {}", claims.verified_by)))?;
        
        // Verify verification type and standards
        let verification_standard = self.verification_standards.get(&claims.verification_type);
        let verification_type_valid = verification_standard.is_some();
        
        // Age verification
        let age_verification_valid = if self.enable_age_verification && context.check_age_restrictions {
            self.verify_age_claims(claims, context)?
        } else {
            true
        };
        
        // Professional license verification
        let professional_license_valid = if self.enable_professional_verification && context.check_professional_licenses {
            self.verify_professional_license(claims, context)?
        } else {
            true
        };
        
        // Privacy preservation validation
        let privacy_valid = if self.enable_privacy_preservation && claims.privacy_preserving {
            context.accept_privacy_preserving
        } else {
            true
        };
        
        // Geographic/jurisdictional validation
        let jurisdiction_valid = self.verify_jurisdiction(claims, issuer_info, context)?;
        
        // Issuer trust validation
        let issuer_trust_sufficient = issuer_info.trust_score >= 0.8 && issuer_info.verified;
        
        // Verification method validation
        let verification_method_valid = self.verify_verification_method(claims, issuer_info, verification_standard.as_ref())?;
        
        // Populate metadata
        metadata.insert("identity_did".to_string(), serde_json::json!(claims.identity_did));
        metadata.insert("verification_type".to_string(), serde_json::json!(claims.verification_type));
        metadata.insert("age_over_21".to_string(), serde_json::json!(claims.age_over_21));
        metadata.insert("age_over_18".to_string(), serde_json::json!(claims.age_over_18));
        metadata.insert("professional_license".to_string(), serde_json::json!(claims.professional_license));
        metadata.insert("country".to_string(), serde_json::json!(claims.country));
        metadata.insert("state".to_string(), serde_json::json!(claims.state));
        metadata.insert("privacy_preserving".to_string(), serde_json::json!(claims.privacy_preserving));
        metadata.insert("verification_type_valid".to_string(), serde_json::json!(verification_type_valid));
        metadata.insert("age_verification_valid".to_string(), serde_json::json!(age_verification_valid));
        metadata.insert("professional_license_valid".to_string(), serde_json::json!(professional_license_valid));
        metadata.insert("privacy_valid".to_string(), serde_json::json!(privacy_valid));
        metadata.insert("jurisdiction_valid".to_string(), serde_json::json!(jurisdiction_valid));
        metadata.insert("issuer_trust_sufficient".to_string(), serde_json::json!(issuer_trust_sufficient));
        metadata.insert("verification_method_valid".to_string(), serde_json::json!(verification_method_valid));
        
        // Add issuer information
        metadata.insert("issuer_name".to_string(), serde_json::json!(issuer_info.name));
        metadata.insert("issuer_type".to_string(), serde_json::json!(issuer_info.issuer_type));
        metadata.insert("issuer_country".to_string(), serde_json::json!(issuer_info.country));
        metadata.insert("issuer_trust_score".to_string(), serde_json::json!(issuer_info.trust_score));
        metadata.insert("issuer_verified".to_string(), serde_json::json!(issuer_info.verified));
        
        if let Some(standard) = verification_standard {
            metadata.insert("verification_standard".to_string(), serde_json::json!(standard.standard_name));
            metadata.insert("required_evidence_level".to_string(), serde_json::json!(standard.required_evidence_level));
        }
        
        // Overall validation
        let is_valid = verification_type_valid && 
                      age_verification_valid && 
                      professional_license_valid &&
                      privacy_valid &&
                      jurisdiction_valid &&
                      issuer_trust_sufficient &&
                      verification_method_valid;
        
        let confidence = if is_valid { 
            // Base confidence on issuer trust score
            0.95 + (issuer_info.trust_score * 0.05)
        } else { 
            0.05 
        };
        
        Ok(VerificationResult::new(
            is_valid,
            "qr_identity".to_string(),
            confidence,
            metadata,
        ))
    }
    
    fn verify_age_claims(&self, claims: &IdentityClaims, context: &IdentityVerificationContext) -> Result<bool> {
        // Check minimum age requirement if specified
        if let Some(min_age) = context.minimum_age_requirement {
            if min_age <= 18 && !claims.age_over_18 {
                return Ok(false);
            }
            if min_age <= 21 && !claims.age_over_21 {
                return Ok(false);
            }
            // For ages > 21, we'd need more specific age claims or ZKP proofs
        }
        
        // Consistency check: if over 21, must also be over 18
        if claims.age_over_21 && !claims.age_over_18 {
            return Ok(false);
        }
        
        Ok(true)
    }
    
    fn verify_professional_license(&self, claims: &IdentityClaims, context: &IdentityVerificationContext) -> Result<bool> {
        if let Some(license_type) = &claims.professional_license {
            // Check if we have information about this license type
            if let Some(license_info) = self.license_registry.get(license_type) {
                // Check if license number is provided
                if claims.license_number.is_none() {
                    return Ok(false);
                }
                
                // Check if license has expiration and it's provided
                if license_info.renewal_required && claims.license_expires.is_none() {
                    return Ok(false);
                }
                
                // If expiration is provided, check if it's still valid
                if let Some(expires) = &claims.license_expires {
                    if let Ok(expiry_date) = chrono::DateTime::parse_from_rfc3339(expires) {
                        let expiry_timestamp = expiry_date.timestamp() as u64;
                        if expiry_timestamp <= context.current_time {
                            return Ok(false); // License expired
                        }
                    } else {
                        return Ok(false); // Invalid date format
                    }
                }
                
                return Ok(true);
            } else {
                // Unknown license type - could be suspicious
                return Ok(false);
            }
        }
        
        // No professional license claimed - that's okay
        Ok(true)
    }
    
    fn verify_jurisdiction(&self, claims: &IdentityClaims, issuer: &IdentityIssuerInfo, context: &IdentityVerificationContext) -> Result<bool> {
        // Check if issuer's jurisdiction matches claimed location
        if issuer.country != claims.country {
            return Ok(false);
        }
        
        // If issuer has a specific state and claims have a state, they should match
        if let (Some(issuer_state), Some(claims_state)) = (&issuer.state, Some(&claims.state)) {
            if issuer_state != claims_state {
                return Ok(false);
            }
        }
        
        Ok(true)
    }
    
    fn verify_verification_method(&self, claims: &IdentityClaims, issuer: &IdentityIssuerInfo, standard: Option<&VerificationStandard>) -> Result<bool> {
        // Check if the issuer is appropriate for the verification type
        match claims.verification_type.as_str() {
            "age_and_profession" => {
                if issuer.issuer_type == "professional_board" || issuer.issuer_type == "government" {
                    return Ok(true);
                }
            },
            "government_id" => {
                if issuer.issuer_type == "government" {
                    return Ok(true);
                }
            },
            "professional_credential" => {
                if issuer.issuer_type == "professional_board" || issuer.issuer_type == "educational" {
                    return Ok(true);
                }
            },
            _ => {
                // Generic verification - most issuers can handle this
                return Ok(true);
            }
        }
        
        Ok(false)
    }
}

impl VerificationPackage for QRIdentityPackage {
    fn package_type(&self) -> &str {
        "qr_identity"
    }
    
    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        // Extract QR identity claims
        let identity_did = credential.get_claim("identityDid")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing identityDid claim".to_string()))?;
            
        let verification_type = credential.get_claim("verificationType")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing verificationType claim".to_string()))?;
            
        let age_over_21 = credential.get_claim("ageOver21")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
            
        let age_over_18 = credential.get_claim("ageOver18")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
            
        let professional_license = credential.get_claim("professionalLicense")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
            
        let license_number = credential.get_claim("licenseNumber")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
            
        let license_expires = credential.get_claim("licenseExpires")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
            
        let verified_by = credential.get_claim("verifiedBy")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing verifiedBy claim".to_string()))?;
            
        let country = credential.get_claim("country")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing country claim".to_string()))?;
            
        let state = credential.get_claim("state")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing state claim".to_string()))?;
            
        let privacy_preserving = credential.get_claim("privacyPreserving")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        
        // Convert to IdentityClaims structure
        let identity_claims = IdentityClaims {
            identity_did: identity_did.to_string(),
            verification_type: verification_type.to_string(),
            age_over_21,
            age_over_18,
            professional_license,
            license_number,
            license_expires,
            verified_by: verified_by.to_string(),
            country: country.to_string(),
            state: state.to_string(),
            privacy_preserving,
        };
        
        // Create verification context
        let context = IdentityVerificationContext {
            current_time: chrono::Utc::now().timestamp() as u64,
            verifier_location: None,
            check_professional_licenses: true,
            check_age_restrictions: true,
            minimum_age_requirement: None,
            accept_privacy_preserving: true,
            required_verification_level: "standard".to_string(),
        };
        
        // Verify using QR-specific logic
        self.verify_qr_identity(&identity_claims, &context)
    }
    
    fn create_credential(&self, claims: ClaimSet) -> Result<VerifiableCredential> {
        // Validate QR identity claims
        self.validate_claims(&claims)?;
        
        // TODO: Create actual QR identity credential
        Err(LemmaError::Package("Not implemented: use QRLemmaGenerator for QR identity creation".to_string()))
    }
    
    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String {
        let identity_did = credential.get_claim("identityDid")
            .and_then(|v| v.as_str())
            .unwrap_or(&credential.id);
        let verified_by = credential.get_claim("verifiedBy")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        format!("qr_identity:{}:{}", verified_by, identity_did)
    }
    
    fn validate_claims(&self, claims: &ClaimSet) -> Result<()> {
        let required_claims = [
            "identityDid", "verificationType", "ageOver21", "ageOver18",
            "verifiedBy", "country", "state", "privacyPreserving"
        ];
        
        for claim in &required_claims {
            if !claims.contains_key(*claim) {
                return Err(LemmaError::Package(format!("Missing required QR identity claim: {}", claim)));
            }
        }
        
        // Validate lemma type
        if let Some(lemma_type) = claims.get("lemmaType") {
            if lemma_type.as_str() != Some("identity_verification") {
                return Err(LemmaError::Package("Invalid lemma type for QR identity".to_string()));
            }
        }
        
        Ok(())
    }
}

/// Helper functions for creating sample identity issuers and standards
impl QRIdentityPackage {
    pub fn create_sample_issuer() -> IdentityIssuerInfo {
        IdentityIssuerInfo {
            did: "did:lemma:state_medical_board".to_string(),
            name: "California State Medical Board".to_string(),
            issuer_type: "professional_board".to_string(),
            country: "USA".to_string(),
            state: Some("California".to_string()),
            verified: true,
            public_key: "public_key_ca_medical_board_123".to_string(),
            trust_score: 0.95,
            issued_credentials: 125000,
        }
    }
    
    pub fn create_sample_government_issuer() -> IdentityIssuerInfo {
        IdentityIssuerInfo {
            did: "did:lemma:ca_dmv".to_string(),
            name: "California Department of Motor Vehicles".to_string(),
            issuer_type: "government".to_string(),
            country: "USA".to_string(),
            state: Some("California".to_string()),
            verified: true,
            public_key: "public_key_ca_dmv_456".to_string(),
            trust_score: 0.98,
            issued_credentials: 2500000,
        }
    }
    
    pub fn create_sample_licenses() -> Vec<(String, LicenseInfo)> {
        vec![
            ("medical_doctor".to_string(), LicenseInfo {
                license_type: "medical_doctor".to_string(),
                issuing_authority: "State Medical Board".to_string(),
                validation_endpoint: Some("https://medical-board.ca.gov/verify".to_string()),
                verification_method: "online_lookup".to_string(),
                renewal_required: true,
                renewal_period_months: Some(24),
            }),
            ("registered_nurse".to_string(), LicenseInfo {
                license_type: "registered_nurse".to_string(),
                issuing_authority: "Board of Registered Nursing".to_string(),
                validation_endpoint: Some("https://nursing-board.ca.gov/verify".to_string()),
                verification_method: "online_lookup".to_string(),
                renewal_required: true,
                renewal_period_months: Some(24),
            }),
            ("attorney".to_string(), LicenseInfo {
                license_type: "attorney".to_string(),
                issuing_authority: "State Bar".to_string(),
                validation_endpoint: Some("https://bar.ca.gov/verify".to_string()),
                verification_method: "online_lookup".to_string(),
                renewal_required: true,
                renewal_period_months: Some(12),
            })
        ]
    }
    
    pub fn create_sample_standards() -> Vec<VerificationStandard> {
        vec![
            VerificationStandard {
                standard_name: "age_and_profession".to_string(),
                required_evidence_level: "enhanced".to_string(),
                age_verification_method: "government_id".to_string(),
                biometric_required: false,
                document_verification_required: true,
                in_person_verification_required: false,
            },
            VerificationStandard {
                standard_name: "government_id".to_string(),
                required_evidence_level: "superior".to_string(),
                age_verification_method: "birth_certificate".to_string(),
                biometric_required: true,
                document_verification_required: true,
                in_person_verification_required: true,
            },
            VerificationStandard {
                standard_name: "professional_credential".to_string(),
                required_evidence_level: "enhanced".to_string(),
                age_verification_method: "not_required".to_string(),
                biometric_required: false,
                document_verification_required: true,
                in_person_verification_required: false,
            }
        ]
    }
    
    pub fn with_sample_data(mut self) -> Self {
        self.add_issuer(Self::create_sample_issuer());
        self.add_issuer(Self::create_sample_government_issuer());
        
        for (license_type, license_info) in Self::create_sample_licenses() {
            self.add_license(license_type, license_info);
        }
        
        for standard in Self::create_sample_standards() {
            self.add_verification_standard(standard);
        }
        
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_qr_identity_package_creation() {
        let package = QRIdentityPackage::new()
            .with_age_verification(true)
            .with_professional_verification(true)
            .with_privacy_preservation(true)
            .with_sample_data();
        
        assert_eq!(package.package_type(), "qr_identity");
        assert!(package.enable_age_verification);
        assert!(package.enable_professional_verification);
        assert!(package.enable_privacy_preservation);
        assert!(package.issuer_registry.contains_key("did:lemma:state_medical_board"));
        assert!(package.license_registry.contains_key("medical_doctor"));
    }
    
    #[test]
    fn test_age_verification() {
        let package = QRIdentityPackage::new();
        
        let valid_claims = IdentityClaims {
            identity_did: "did:lemma:person_123".to_string(),
            verification_type: "age_and_profession".to_string(),
            age_over_21: true,
            age_over_18: true,
            professional_license: None,
            license_number: None,
            license_expires: None,
            verified_by: "did:lemma:ca_dmv".to_string(),
            country: "USA".to_string(),
            state: "California".to_string(),
            privacy_preserving: false,
        };
        
        let context = IdentityVerificationContext {
            current_time: chrono::Utc::now().timestamp() as u64,
            verifier_location: None,
            check_professional_licenses: false,
            check_age_restrictions: true,
            minimum_age_requirement: Some(21),
            accept_privacy_preserving: true,
            required_verification_level: "standard".to_string(),
        };
        
        let result = package.verify_age_claims(&valid_claims, &context);
        assert!(result.is_ok());
        assert!(result.unwrap());
        
        // Test inconsistent age claims
        let invalid_claims = IdentityClaims {
            age_over_21: true,
            age_over_18: false, // Inconsistent!
            ..valid_claims
        };
        
        let result = package.verify_age_claims(&invalid_claims, &context);
        assert!(result.is_ok());
        assert!(!result.unwrap());
    }
    
    #[test]
    fn test_professional_license_verification() {
        let package = QRIdentityPackage::new().with_sample_data();
        
        let valid_claims = IdentityClaims {
            identity_did: "did:lemma:person_123".to_string(),
            verification_type: "age_and_profession".to_string(),
            age_over_21: true,
            age_over_18: true,
            professional_license: Some("medical_doctor".to_string()),
            license_number: Some("MD123456".to_string()),
            license_expires: Some("2026-05-15T00:00:00Z".to_string()),
            verified_by: "did:lemma:state_medical_board".to_string(),
            country: "USA".to_string(),
            state: "California".to_string(),
            privacy_preserving: false,
        };
        
        let context = IdentityVerificationContext {
            current_time: chrono::Utc::now().timestamp() as u64,
            verifier_location: None,
            check_professional_licenses: true,
            check_age_restrictions: false,
            minimum_age_requirement: None,
            accept_privacy_preserving: true,
            required_verification_level: "standard".to_string(),
        };
        
        let result = package.verify_professional_license(&valid_claims, &context);
        assert!(result.is_ok());
        assert!(result.unwrap());
    }
    
    #[test]
    fn test_sample_data_creation() {
        let issuer = QRIdentityPackage::create_sample_issuer();
        let licenses = QRIdentityPackage::create_sample_licenses();
        let standards = QRIdentityPackage::create_sample_standards();
        
        assert_eq!(issuer.name, "California State Medical Board");
        assert_eq!(licenses.len(), 3);
        assert_eq!(standards.len(), 3);
        assert_eq!(standards[0].standard_name, "age_and_profession");
    }
} 