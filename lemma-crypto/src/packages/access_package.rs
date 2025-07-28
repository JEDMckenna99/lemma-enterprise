use std::collections::HashMap;
use serde::{Deserialize, Serialize};

use crate::{
    credentials::VerifiableCredential,
    core::VerificationResult,
    packages::VerificationPackage,
    qr::{QRType, AccessClaims},
    ClaimSet, VerificationMetadata,
    Result, LemmaError
};

/// Enhanced QR-specific access control verification package
#[derive(Debug, Clone)]
pub struct QRAccessPackage {
    organization_registry: HashMap<String, OrganizationInfo>,
    employee_registry: HashMap<String, EmployeeInfo>,
    access_zone_registry: HashMap<String, AccessZoneInfo>,
    enable_time_restrictions: bool,
    enable_zone_validation: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrganizationInfo {
    pub did: String,
    pub name: String,
    pub verified: bool,
    pub industry: String,
    pub security_level: String,
    pub zones: Vec<String>,
    pub hr_contact: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmployeeInfo {
    pub employee_id: String,
    pub name: String,
    pub organization_did: String,
    pub department: String,
    pub position: String,
    pub hire_date: String,
    pub clearance_level: String,
    pub active: bool,
    pub manager_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccessZoneInfo {
    pub zone_id: String,
    pub name: String,
    pub organization_did: String,
    pub required_clearance: String,
    pub zone_type: String, // "building", "floor", "room", "equipment"
    pub capacity: Option<u32>,
    pub restricted_hours: Option<TimeRestriction>,
    pub parent_zone: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimeRestriction {
    pub start_hour: u8, // 0-23
    pub end_hour: u8,   // 0-23
    pub days_of_week: Vec<u8>, // 0=Sunday, 1=Monday, etc.
    pub timezone: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccessVerificationContext {
    pub current_time: u64,
    pub scanner_location: Option<String>,
    pub scanner_zone: Option<String>,
    pub check_time_restrictions: bool,
    pub check_capacity_limits: bool,
    pub allow_emergency_override: bool,
}

impl QRAccessPackage {
    pub fn new() -> Self {
        Self {
            organization_registry: HashMap::new(),
            employee_registry: HashMap::new(),
            access_zone_registry: HashMap::new(),
            enable_time_restrictions: true,
            enable_zone_validation: true,
        }
    }
    
    pub fn with_time_restrictions(mut self, enabled: bool) -> Self {
        self.enable_time_restrictions = enabled;
        self
    }
    
    pub fn with_zone_validation(mut self, enabled: bool) -> Self {
        self.enable_zone_validation = enabled;
        self
    }
    
    pub fn add_organization(&mut self, organization: OrganizationInfo) {
        self.organization_registry.insert(organization.did.clone(), organization);
    }
    
    pub fn add_employee(&mut self, employee: EmployeeInfo) {
        self.employee_registry.insert(employee.employee_id.clone(), employee);
    }
    
    pub fn add_access_zone(&mut self, zone: AccessZoneInfo) {
        self.access_zone_registry.insert(zone.zone_id.clone(), zone);
    }
    
    /// Verify QR access pass with enhanced context
    pub fn verify_qr_access(&self, claims: &AccessClaims, context: &AccessVerificationContext) -> Result<VerificationResult> {
        let mut metadata = HashMap::new();
        
        // Basic employee validation
        let employee_info = self.employee_registry.get(&claims.employee_id)
            .ok_or_else(|| LemmaError::Package(format!("Employee not found: {}", claims.employee_id)))?;
        
        let organization_info = self.organization_registry.get(&employee_info.organization_did);
        
        // Verify employee details match
        let employee_name_matches = employee_info.name == claims.employee_name;
        let department_matches = employee_info.department == claims.department;
        let employee_active = employee_info.active;
        
        // Verify issuer matches organization
        let issued_by_org = organization_info.map_or(false, |org| org.did == claims.issued_by);
        
        // Access level validation
        let clearance_sufficient = self.verify_clearance_level(&claims.clearance, &employee_info.clearance_level);
        
        // Time-based validation
        let time_valid = if self.enable_time_restrictions && context.check_time_restrictions {
            self.verify_time_restrictions(claims, context)?
        } else {
            true
        };
        
        // Zone access validation
        let zone_access_valid = if self.enable_zone_validation {
            self.verify_zone_access(&claims.access_zones, employee_info, context)?
        } else {
            true
        };
        
        // Validity period check
        let validity_period_ok = self.verify_validity_period(claims, context.current_time)?;
        
        // Emergency contact validation
        let emergency_contact_valid = self.validate_emergency_contact(&claims.emergency_contact);
        
        // Populate metadata
        metadata.insert("employee_id".to_string(), serde_json::json!(claims.employee_id));
        metadata.insert("employee_name".to_string(), serde_json::json!(claims.employee_name));
        metadata.insert("department".to_string(), serde_json::json!(claims.department));
        metadata.insert("access_level".to_string(), serde_json::json!(claims.access_level));
        metadata.insert("clearance".to_string(), serde_json::json!(claims.clearance));
        metadata.insert("employee_name_matches".to_string(), serde_json::json!(employee_name_matches));
        metadata.insert("department_matches".to_string(), serde_json::json!(department_matches));
        metadata.insert("employee_active".to_string(), serde_json::json!(employee_active));
        metadata.insert("issued_by_org".to_string(), serde_json::json!(issued_by_org));
        metadata.insert("clearance_sufficient".to_string(), serde_json::json!(clearance_sufficient));
        metadata.insert("time_valid".to_string(), serde_json::json!(time_valid));
        metadata.insert("zone_access_valid".to_string(), serde_json::json!(zone_access_valid));
        metadata.insert("validity_period_ok".to_string(), serde_json::json!(validity_period_ok));
        metadata.insert("emergency_contact_valid".to_string(), serde_json::json!(emergency_contact_valid));
        
        if let Some(employee) = Some(employee_info) {
            metadata.insert("employee_position".to_string(), serde_json::json!(employee.position));
            metadata.insert("employee_hire_date".to_string(), serde_json::json!(employee.hire_date));
            metadata.insert("employee_clearance_level".to_string(), serde_json::json!(employee.clearance_level));
        }
        
        if let Some(organization) = organization_info {
            metadata.insert("organization_name".to_string(), serde_json::json!(organization.name));
            metadata.insert("organization_security_level".to_string(), serde_json::json!(organization.security_level));
            metadata.insert("organization_industry".to_string(), serde_json::json!(organization.industry));
        }
        
        // Overall validation
        let is_valid = employee_name_matches && 
                      department_matches && 
                      employee_active &&
                      issued_by_org &&
                      clearance_sufficient && 
                      time_valid &&
                      zone_access_valid &&
                      validity_period_ok &&
                      emergency_contact_valid;
        
        let confidence = if is_valid { 0.998 } else { 0.002 };
        
        Ok(VerificationResult::new(
            is_valid,
            "qr_access".to_string(),
            confidence,
            metadata,
        ))
    }
    
    fn verify_clearance_level(&self, required: &str, employee: &str) -> bool {
        // Define clearance hierarchy
        let clearance_levels = vec!["basic", "standard", "elevated", "high", "critical"];
        
        let required_index = clearance_levels.iter().position(|&x| x == required).unwrap_or(0);
        let employee_index = clearance_levels.iter().position(|&x| x == employee).unwrap_or(0);
        
        employee_index >= required_index
    }
    
    fn verify_time_restrictions(&self, claims: &AccessClaims, context: &AccessVerificationContext) -> Result<bool> {
        // Parse valid from and until times
        let valid_from = chrono::DateTime::parse_from_rfc3339(&claims.valid_from)
            .map_err(|_| LemmaError::Package("Invalid valid_from date format".to_string()))?
            .timestamp() as u64;
            
        let valid_until = chrono::DateTime::parse_from_rfc3339(&claims.valid_until)
            .map_err(|_| LemmaError::Package("Invalid valid_until date format".to_string()))?
            .timestamp() as u64;
        
        // Check if current time is within validity period
        let current_time = context.current_time;
        Ok(current_time >= valid_from && current_time <= valid_until)
    }
    
    fn verify_zone_access(&self, requested_zones: &[String], employee: &EmployeeInfo, context: &AccessVerificationContext) -> Result<bool> {
        // If scanner zone is specified, check if employee has access to it
        if let Some(scanner_zone) = &context.scanner_zone {
            if !requested_zones.contains(scanner_zone) {
                return Ok(false);
            }
            
            // Check if the employee's clearance allows access to this zone
            if let Some(zone_info) = self.access_zone_registry.get(scanner_zone) {
                let clearance_ok = self.verify_clearance_level(&zone_info.required_clearance, &employee.clearance_level);
                if !clearance_ok {
                    return Ok(false);
                }
            }
        }
        
        // All requested zones must exist and be accessible
        for zone in requested_zones {
            if let Some(zone_info) = self.access_zone_registry.get(zone) {
                // Verify employee's organization matches zone's organization
                if zone_info.organization_did != employee.organization_did {
                    return Ok(false);
                }
                
                // Check clearance level
                let clearance_ok = self.verify_clearance_level(&zone_info.required_clearance, &employee.clearance_level);
                if !clearance_ok {
                    return Ok(false);
                }
            } else {
                // Zone doesn't exist
                return Ok(false);
            }
        }
        
        Ok(true)
    }
    
    fn verify_validity_period(&self, claims: &AccessClaims, current_time: u64) -> Result<bool> {
        let valid_from = chrono::DateTime::parse_from_rfc3339(&claims.valid_from)
            .map_err(|_| LemmaError::Package("Invalid valid_from date format".to_string()))?
            .timestamp() as u64;
            
        let valid_until = chrono::DateTime::parse_from_rfc3339(&claims.valid_until)
            .map_err(|_| LemmaError::Package("Invalid valid_until date format".to_string()))?
            .timestamp() as u64;
        
        Ok(current_time >= valid_from && current_time <= valid_until)
    }
    
    fn validate_emergency_contact(&self, contact: &str) -> bool {
        // Basic phone number validation
        if contact.starts_with("+1-") && contact.len() >= 10 {
            return true;
        }
        
        // Allow various formats
        if contact.len() >= 10 && contact.chars().any(|c| c.is_numeric()) {
            return true;
        }
        
        false
    }
}

impl VerificationPackage for QRAccessPackage {
    fn package_type(&self) -> &str {
        "qr_access"
    }
    
    fn verify_credential(&self, credential: &VerifiableCredential) -> Result<VerificationResult> {
        // Extract QR access claims
        let employee_id = credential.get_claim("employeeId")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing employeeId claim".to_string()))?;
            
        let employee_name = credential.get_claim("employeeName")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing employeeName claim".to_string()))?;
            
        let department = credential.get_claim("department")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing department claim".to_string()))?;
            
        let access_level = credential.get_claim("accessLevel")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing accessLevel claim".to_string()))?;
            
        let clearance = credential.get_claim("clearance")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing clearance claim".to_string()))?;
            
        let valid_from = credential.get_claim("validFrom")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing validFrom claim".to_string()))?;
            
        let valid_until = credential.get_claim("validUntil")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing validUntil claim".to_string()))?;
            
        let issued_by = credential.get_claim("issuedBy")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing issuedBy claim".to_string()))?;
            
        let access_zones = credential.get_claim("accessZones")
            .and_then(|v| v.as_array())
            .map(|arr| arr.iter().filter_map(|v| v.as_str()).map(|s| s.to_string()).collect())
            .unwrap_or_else(Vec::new);
            
        let emergency_contact = credential.get_claim("emergencyContact")
            .and_then(|v| v.as_str())
            .ok_or_else(|| LemmaError::Package("Missing emergencyContact claim".to_string()))?;
        
        // Convert to AccessClaims structure
        let access_claims = AccessClaims {
            employee_id: employee_id.to_string(),
            employee_name: employee_name.to_string(),
            department: department.to_string(),
            access_level: access_level.to_string(),
            clearance: clearance.to_string(),
            valid_from: valid_from.to_string(),
            valid_until: valid_until.to_string(),
            issued_by: issued_by.to_string(),
            access_zones,
            emergency_contact: emergency_contact.to_string(),
        };
        
        // Create verification context
        let context = AccessVerificationContext {
            current_time: chrono::Utc::now().timestamp() as u64,
            scanner_location: None,
            scanner_zone: None,
            check_time_restrictions: true,
            check_capacity_limits: false,
            allow_emergency_override: false,
        };
        
        // Verify using QR-specific logic
        self.verify_qr_access(&access_claims, &context)
    }
    
    fn create_credential(&self, claims: ClaimSet) -> Result<VerifiableCredential> {
        // Validate QR access claims
        self.validate_claims(&claims)?;
        
        // TODO: Create actual QR access credential
        Err(LemmaError::Package("Not implemented: use QRLemmaGenerator for QR access creation".to_string()))
    }
    
    fn get_revocation_key(&self, credential: &VerifiableCredential) -> String {
        let employee_id = credential.get_claim("employeeId")
            .and_then(|v| v.as_str())
            .unwrap_or(&credential.id);
        let organization = credential.get_claim("issuedBy")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        format!("qr_access:{}:{}", organization, employee_id)
    }
    
    fn validate_claims(&self, claims: &ClaimSet) -> Result<()> {
        let required_claims = [
            "employeeId", "employeeName", "department", "accessLevel",
            "clearance", "validFrom", "validUntil", "issuedBy", "accessZones", "emergencyContact"
        ];
        
        for claim in &required_claims {
            if !claims.contains_key(*claim) {
                return Err(LemmaError::Package(format!("Missing required QR access claim: {}", claim)));
            }
        }
        
        // Validate lemma type
        if let Some(lemma_type) = claims.get("lemmaType") {
            if lemma_type.as_str() != Some("access_control") {
                return Err(LemmaError::Package("Invalid lemma type for QR access".to_string()));
            }
        }
        
        Ok(())
    }
}

/// Helper functions for creating sample organizations and employees
impl QRAccessPackage {
    pub fn create_sample_organization() -> OrganizationInfo {
        OrganizationInfo {
            did: "did:lemma:hr_department".to_string(),
            name: "Tech Corp Inc.".to_string(),
            verified: true,
            industry: "technology".to_string(),
            security_level: "high".to_string(),
            zones: vec!["building_main".to_string(), "floor_5".to_string(), "conference_rooms".to_string()],
            hr_contact: "hr@techcorp.com".to_string(),
        }
    }
    
    pub fn create_sample_employee() -> EmployeeInfo {
        EmployeeInfo {
            employee_id: "EMP_001".to_string(),
            name: "John Smith".to_string(),
            organization_did: "did:lemma:hr_department".to_string(),
            department: "Engineering".to_string(),
            position: "Senior Software Engineer".to_string(),
            hire_date: "2022-01-15".to_string(),
            clearance_level: "standard".to_string(),
            active: true,
            manager_id: Some("EMP_MANAGER_001".to_string()),
        }
    }
    
    pub fn create_sample_zones() -> Vec<AccessZoneInfo> {
        vec![
            AccessZoneInfo {
                zone_id: "building_main".to_string(),
                name: "Main Building".to_string(),
                organization_did: "did:lemma:hr_department".to_string(),
                required_clearance: "basic".to_string(),
                zone_type: "building".to_string(),
                capacity: Some(1000),
                restricted_hours: None,
                parent_zone: None,
            },
            AccessZoneInfo {
                zone_id: "floor_5".to_string(),
                name: "5th Floor - Engineering".to_string(),
                organization_did: "did:lemma:hr_department".to_string(),
                required_clearance: "standard".to_string(),
                zone_type: "floor".to_string(),
                capacity: Some(200),
                restricted_hours: None,
                parent_zone: Some("building_main".to_string()),
            },
            AccessZoneInfo {
                zone_id: "conference_rooms".to_string(),
                name: "Conference Rooms".to_string(),
                organization_did: "did:lemma:hr_department".to_string(),
                required_clearance: "standard".to_string(),
                zone_type: "room".to_string(),
                capacity: Some(50),
                restricted_hours: Some(TimeRestriction {
                    start_hour: 6,
                    end_hour: 22,
                    days_of_week: vec![1, 2, 3, 4, 5], // Monday to Friday
                    timezone: "UTC".to_string(),
                }),
                parent_zone: Some("floor_5".to_string()),
            }
        ]
    }
    
    pub fn with_sample_data(mut self) -> Self {
        self.add_organization(Self::create_sample_organization());
        self.add_employee(Self::create_sample_employee());
        
        for zone in Self::create_sample_zones() {
            self.add_access_zone(zone);
        }
        
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_qr_access_package_creation() {
        let package = QRAccessPackage::new()
            .with_time_restrictions(true)
            .with_zone_validation(true)
            .with_sample_data();
        
        assert_eq!(package.package_type(), "qr_access");
        assert!(package.enable_time_restrictions);
        assert!(package.enable_zone_validation);
        assert!(package.organization_registry.contains_key("did:lemma:hr_department"));
        assert!(package.employee_registry.contains_key("EMP_001"));
    }
    
    #[test]
    fn test_clearance_level_verification() {
        let package = QRAccessPackage::new();
        
        assert!(package.verify_clearance_level("basic", "standard"));
        assert!(package.verify_clearance_level("standard", "high"));
        assert!(!package.verify_clearance_level("high", "basic"));
        assert!(package.verify_clearance_level("standard", "standard"));
    }
    
    #[test]
    fn test_emergency_contact_validation() {
        let package = QRAccessPackage::new();
        
        assert!(package.validate_emergency_contact("+1-555-0123"));
        assert!(package.validate_emergency_contact("555-123-4567"));
        assert!(package.validate_emergency_contact("5551234567"));
        assert!(!package.validate_emergency_contact(""));
        assert!(!package.validate_emergency_contact("invalid"));
    }
    
    #[test]
    fn test_sample_data_creation() {
        let organization = QRAccessPackage::create_sample_organization();
        let employee = QRAccessPackage::create_sample_employee();
        let zones = QRAccessPackage::create_sample_zones();
        
        assert_eq!(organization.name, "Tech Corp Inc.");
        assert_eq!(employee.name, "John Smith");
        assert_eq!(zones.len(), 3);
        assert_eq!(zones[0].zone_id, "building_main");
    }
} 