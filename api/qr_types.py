"""
QR Types and Data Structures for Lemma-Powered QR Codes

This module defines the data structures, enums, and validation logic
for different types of QR codes supported by the Lemma system.
"""

from enum import Enum
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import re


class QRType(Enum):
    """Enumeration of supported QR code types"""
    TICKET = "ticket"
    PRODUCT = "product"
    ACCESS = "access"
    IDENTITY = "identity"


class QRImageFormat(Enum):
    """Supported QR image formats"""
    PNG = "PNG"
    SVG = "SVG"
    JPEG = "JPEG"


class QRErrorCorrectionLevel(Enum):
    """QR code error correction levels"""
    LOW = "low"          # ~7% correction
    MEDIUM = "medium"    # ~15% correction
    QUARTILE = "quartile"  # ~25% correction
    HIGH = "high"        # ~30% correction


@dataclass
class QREncodingOptions:
    """Options for QR code encoding"""
    format: QRImageFormat = QRImageFormat.PNG
    size: int = 200
    border: int = 4
    error_correction: QRErrorCorrectionLevel = QRErrorCorrectionLevel.MEDIUM
    include_base64: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format.value,
            "size": self.size,
            "border": self.border,
            "error_correction": self.error_correction.value,
            "include_base64": self.include_base64
        }


@dataclass
class QRMetadata:
    """Metadata for QR codes"""
    created_at: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))
    version: str = "1.0.0"
    issuer_did: str = "did:lemma:qr_system"
    expires_at: Optional[int] = None

    def is_expired(self) -> bool:
        """Check if the QR code has expired"""
        if self.expires_at is None:
            return False
        return int(datetime.now(timezone.utc).timestamp()) > self.expires_at

    def set_expiry_days(self, days: int) -> 'QRMetadata':
        """Set expiry time in days from now"""
        self.expires_at = int(datetime.now(timezone.utc).timestamp()) + (days * 24 * 60 * 60)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Ticket-specific data structures
@dataclass
class TicketClaims:
    """Claims structure for event tickets"""
    event_id: str
    event_name: str
    seat: str
    price_paid: str
    purchaser_did: str
    purchase_timestamp: str
    valid_until: str
    venue: str

    def validate(self) -> List[str]:
        """Validate ticket claims and return list of errors"""
        errors = []
        
        if not self.event_id:
            errors.append("Event ID is required")
        
        if not self.event_name:
            errors.append("Event name is required")
        
        if not self.seat:
            errors.append("Seat information is required")
        
        if not self.venue:
            errors.append("Venue is required")
        
        # Validate price format
        if not re.match(r'^\$?\d+(\.\d{2})?$', self.price_paid):
            errors.append("Invalid price format")
        
        # Validate DID format
        if not self.purchaser_did.startswith('did:'):
            errors.append("Invalid purchaser DID format")
        
        # Validate timestamp formats
        try:
            datetime.fromisoformat(self.purchase_timestamp.replace('Z', '+00:00'))
        except ValueError:
            errors.append("Invalid purchase timestamp format")
        
        try:
            datetime.fromisoformat(self.valid_until.replace('Z', '+00:00'))
        except ValueError:
            errors.append("Invalid valid_until timestamp format")
        
        return errors

    def to_claims_dict(self) -> Dict[str, Any]:
        """Convert to claims dictionary for lemma creation"""
        return {
            "lemmaType": "event_ticket",
            "eventId": self.event_id,
            "eventName": self.event_name,
            "seat": self.seat,
            "pricePaid": self.price_paid,
            "purchaserDid": self.purchaser_did,
            "purchaseTimestamp": self.purchase_timestamp,
            "validUntil": self.valid_until,
            "venue": self.venue
        }


# Product-specific data structures
@dataclass
class ProductClaims:
    """Claims structure for product authenticity"""
    product_id: str
    product_name: str
    manufacturer: str
    batch_number: str
    manufacture_date: str
    serial_number: str
    materials: List[str]
    supply_chain_hash: str
    warranty_expires: str

    def validate(self) -> List[str]:
        """Validate product claims and return list of errors"""
        errors = []
        
        if not self.product_id:
            errors.append("Product ID is required")
        
        if not self.product_name:
            errors.append("Product name is required")
        
        if not self.manufacturer:
            errors.append("Manufacturer is required")
        
        if not self.serial_number:
            errors.append("Serial number is required")
        
        # Validate serial number format (alphanumeric, 5-20 chars)
        if not re.match(r'^[A-Za-z0-9]{5,20}$', self.serial_number):
            errors.append("Invalid serial number format")
        
        # Validate batch number format
        if not self.batch_number:
            errors.append("Batch number is required")
        
        # Validate manufacture date
        try:
            datetime.strptime(self.manufacture_date, '%Y-%m-%d')
        except ValueError:
            errors.append("Invalid manufacture date format (expected YYYY-MM-DD)")
        
        # Validate warranty expiration
        try:
            datetime.fromisoformat(self.warranty_expires.replace('Z', '+00:00'))
        except ValueError:
            errors.append("Invalid warranty expiration format")
        
        # Validate materials
        if not self.materials:
            errors.append("At least one material must be specified")
        
        # Validate supply chain hash
        if not self.supply_chain_hash:
            errors.append("Supply chain hash is required")
        
        return errors

    def to_claims_dict(self) -> Dict[str, Any]:
        """Convert to claims dictionary for lemma creation"""
        return {
            "lemmaType": "product_authenticity",
            "productId": self.product_id,
            "productName": self.product_name,
            "manufacturer": self.manufacturer,
            "batchNumber": self.batch_number,
            "manufactureDate": self.manufacture_date,
            "serialNumber": self.serial_number,
            "materials": self.materials,
            "supplyChainHash": self.supply_chain_hash,
            "warrantyExpires": self.warranty_expires
        }


# Access control-specific data structures
@dataclass
class AccessClaims:
    """Claims structure for access control"""
    employee_id: str
    employee_name: str
    department: str
    access_level: str
    clearance: str
    valid_from: str
    valid_until: str
    issued_by: str
    access_zones: List[str]
    emergency_contact: str

    def validate(self) -> List[str]:
        """Validate access claims and return list of errors"""
        errors = []
        
        if not self.employee_id:
            errors.append("Employee ID is required")
        
        if not self.employee_name:
            errors.append("Employee name is required")
        
        if not self.department:
            errors.append("Department is required")
        
        if not self.access_level:
            errors.append("Access level is required")
        
        # Validate clearance level
        valid_clearances = ["basic", "standard", "elevated", "high", "critical"]
        if self.clearance not in valid_clearances:
            errors.append(f"Invalid clearance level. Must be one of: {', '.join(valid_clearances)}")
        
        # Validate timestamps
        try:
            datetime.fromisoformat(self.valid_from.replace('Z', '+00:00'))
        except ValueError:
            errors.append("Invalid valid_from timestamp format")
        
        try:
            datetime.fromisoformat(self.valid_until.replace('Z', '+00:00'))
        except ValueError:
            errors.append("Invalid valid_until timestamp format")
        
        # Validate issuer DID
        if not self.issued_by.startswith('did:'):
            errors.append("Invalid issuer DID format")
        
        # Validate access zones
        if not self.access_zones:
            errors.append("At least one access zone must be specified")
        
        # Validate emergency contact (basic phone number check)
        if not re.match(r'^[\+]?[\d\-\(\)\s]{10,}$', self.emergency_contact):
            errors.append("Invalid emergency contact format")
        
        return errors

    def to_claims_dict(self) -> Dict[str, Any]:
        """Convert to claims dictionary for lemma creation"""
        return {
            "lemmaType": "access_control",
            "employeeId": self.employee_id,
            "employeeName": self.employee_name,
            "department": self.department,
            "accessLevel": self.access_level,
            "clearance": self.clearance,
            "validFrom": self.valid_from,
            "validUntil": self.valid_until,
            "issuedBy": self.issued_by,
            "accessZones": self.access_zones,
            "emergencyContact": self.emergency_contact
        }


# Identity verification-specific data structures
@dataclass
class IdentityClaims:
    """Claims structure for identity verification"""
    identity_did: str
    verification_type: str
    age_over_21: bool
    age_over_18: bool
    professional_license: Optional[str] = None
    license_number: Optional[str] = None
    license_expires: Optional[str] = None
    verified_by: str = ""
    country: str = ""
    state: str = ""
    privacy_preserving: bool = False

    def validate(self) -> List[str]:
        """Validate identity claims and return list of errors"""
        errors = []
        
        if not self.identity_did:
            errors.append("Identity DID is required")
        
        if not self.identity_did.startswith('did:'):
            errors.append("Invalid identity DID format")
        
        if not self.verification_type:
            errors.append("Verification type is required")
        
        valid_verification_types = [
            "age_and_profession", "government_id", "professional_credential",
            "basic_identity", "enhanced_identity"
        ]
        if self.verification_type not in valid_verification_types:
            errors.append(f"Invalid verification type. Must be one of: {', '.join(valid_verification_types)}")
        
        # Consistency check for age claims
        if self.age_over_21 and not self.age_over_18:
            errors.append("Inconsistent age claims: cannot be over 21 but not over 18")
        
        # Validate professional license if provided
        if self.professional_license:
            if not self.license_number:
                errors.append("License number is required when professional license is specified")
            
            if self.license_expires:
                try:
                    datetime.fromisoformat(self.license_expires.replace('Z', '+00:00'))
                except ValueError:
                    errors.append("Invalid license expiration format")
        
        if not self.verified_by:
            errors.append("Verified by (issuer) is required")
        
        if not self.verified_by.startswith('did:'):
            errors.append("Invalid verifier DID format")
        
        if not self.country:
            errors.append("Country is required")
        
        return errors

    def to_claims_dict(self) -> Dict[str, Any]:
        """Convert to claims dictionary for lemma creation"""
        return {
            "lemmaType": "identity_verification",
            "identityDid": self.identity_did,
            "verificationType": self.verification_type,
            "ageOver21": self.age_over_21,
            "ageOver18": self.age_over_18,
            "professionalLicense": self.professional_license,
            "licenseNumber": self.license_number,
            "licenseExpires": self.license_expires,
            "verifiedBy": self.verified_by,
            "country": self.country,
            "state": self.state,
            "privacyPreserving": self.privacy_preserving
        }


# Main QR data structure
@dataclass
class QRData:
    """Complete QR code data structure"""
    lemma: Dict[str, Any]
    qr_type: QRType
    metadata: QRMetadata

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "lemma": self.lemma,
            "qr_type": self.qr_type.value,
            "metadata": self.metadata.to_dict()
        }

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QRData':
        """Create QRData from dictionary"""
        return cls(
            lemma=data["lemma"],
            qr_type=QRType(data["qr_type"]),
            metadata=QRMetadata(**data["metadata"])
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'QRData':
        """Create QRData from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)


# Utility functions for claims validation
class QRValidator:
    """Utility class for validating QR claims"""
    
    @staticmethod
    def validate_claims_for_type(qr_type: QRType, claims: Dict[str, Any]) -> List[str]:
        """Validate claims for a specific QR type"""
        try:
            if qr_type == QRType.TICKET:
                ticket_claims = TicketClaims(**claims)
                return ticket_claims.validate()
            elif qr_type == QRType.PRODUCT:
                product_claims = ProductClaims(**claims)
                return product_claims.validate()
            elif qr_type == QRType.ACCESS:
                access_claims = AccessClaims(**claims)
                return access_claims.validate()
            elif qr_type == QRType.IDENTITY:
                identity_claims = IdentityClaims(**claims)
                return identity_claims.validate()
            else:
                return [f"Unsupported QR type: {qr_type}"]
        except TypeError as e:
            return [f"Invalid claims structure: {str(e)}"]

    @staticmethod
    def convert_claims_to_lemma_format(qr_type: QRType, claims: Dict[str, Any]) -> Dict[str, Any]:
        """Convert claims to lemma format for a specific QR type"""
        try:
            if qr_type == QRType.TICKET:
                ticket_claims = TicketClaims(**claims)
                return ticket_claims.to_claims_dict()
            elif qr_type == QRType.PRODUCT:
                product_claims = ProductClaims(**claims)
                return product_claims.to_claims_dict()
            elif qr_type == QRType.ACCESS:
                access_claims = AccessClaims(**claims)
                return access_claims.to_claims_dict()
            elif qr_type == QRType.IDENTITY:
                identity_claims = IdentityClaims(**claims)
                return identity_claims.to_claims_dict()
            else:
                raise ValueError(f"Unsupported QR type: {qr_type}")
        except TypeError as e:
            raise ValueError(f"Invalid claims structure: {str(e)}")


# Sample data generators
class QRSampleDataGenerator:
    """Generate sample data for testing and demos"""
    
    @staticmethod
    def generate_ticket_sample() -> TicketClaims:
        """Generate sample ticket claims"""
        return TicketClaims(
            event_id="concert_2024_001",
            event_name="Summer Music Festival",
            seat="Section A, Row 15, Seat 8",
            price_paid="$120.00",
            purchaser_did="did:lemma:user_123",
            purchase_timestamp="2024-07-15T14:30:00Z",
            valid_until="2024-12-31T23:59:59Z",
            venue="Madison Square Garden"
        )

    @staticmethod
    def generate_product_sample() -> ProductClaims:
        """Generate sample product claims"""
        return ProductClaims(
            product_id="luxury_watch_SW_001",
            product_name="Submariner Professional",
            manufacturer="did:lemma:swiss_watches",
            batch_number="BATCH_2024_Q3_001",
            manufacture_date="2024-07-15",
            serial_number="SW123456789",
            materials=["steel", "sapphire_crystal", "ceramic_bezel"],
            supply_chain_hash="0x123456789abcdef",
            warranty_expires="2026-07-15T00:00:00Z"
        )

    @staticmethod
    def generate_access_sample() -> AccessClaims:
        """Generate sample access claims"""
        return AccessClaims(
            employee_id="EMP_001",
            employee_name="John Smith",
            department="Engineering",
            access_level="floor_5_conference_rooms",
            clearance="standard",
            valid_from="2024-07-01T00:00:00Z",
            valid_until="2024-12-31T23:59:59Z",
            issued_by="did:lemma:hr_department",
            access_zones=["building_main", "floor_5", "conference_rooms"],
            emergency_contact="+1-555-0123"
        )

    @staticmethod
    def generate_identity_sample() -> IdentityClaims:
        """Generate sample identity claims"""
        return IdentityClaims(
            identity_did="did:lemma:person_123",
            verification_type="age_and_profession",
            age_over_21=True,
            age_over_18=True,
            professional_license="medical_doctor",
            license_number="MD123456",
            license_expires="2026-05-15T00:00:00Z",
            verified_by="did:lemma:state_medical_board",
            country="USA",
            state="California",
            privacy_preserving=True
        )

    @staticmethod
    def generate_sample_for_type(qr_type: QRType) -> Union[TicketClaims, ProductClaims, AccessClaims, IdentityClaims]:
        """Generate sample claims for any QR type"""
        if qr_type == QRType.TICKET:
            return QRSampleDataGenerator.generate_ticket_sample()
        elif qr_type == QRType.PRODUCT:
            return QRSampleDataGenerator.generate_product_sample()
        elif qr_type == QRType.ACCESS:
            return QRSampleDataGenerator.generate_access_sample()
        elif qr_type == QRType.IDENTITY:
            return QRSampleDataGenerator.generate_identity_sample()
        else:
            raise ValueError(f"Unsupported QR type: {qr_type}")


# Export all public classes and functions
__all__ = [
    'QRType', 'QRImageFormat', 'QRErrorCorrectionLevel',
    'QREncodingOptions', 'QRMetadata', 'QRData',
    'TicketClaims', 'ProductClaims', 'AccessClaims', 'IdentityClaims',
    'QRValidator', 'QRSampleDataGenerator'
] 