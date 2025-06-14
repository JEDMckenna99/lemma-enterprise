"""
OFAC & Export Control Screening System
Comprehensive sanctions and export control compliance for KYC processes
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import hashlib
import re
from difflib import SequenceMatcher

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ScreeningResult:
    """Result of OFAC/Export Control screening"""
    is_clear: bool
    risk_level: str  # 'LOW', 'MEDIUM', 'HIGH', 'BLOCKED'
    matches: List[Dict[str, Any]]
    screening_id: str
    timestamp: datetime
    details: Dict[str, Any]

@dataclass
class SanctionedEntity:
    """Sanctioned entity from OFAC/export control lists"""
    name: str
    entity_type: str  # 'INDIVIDUAL', 'ENTITY', 'VESSEL', 'AIRCRAFT'
    list_source: str  # 'SDN', 'SSI', 'EL', 'DTC', etc.
    country: Optional[str]
    aliases: List[str]
    addresses: List[str]
    identifiers: List[Dict[str, str]]  # passport, tax_id, etc.
    programs: List[str]  # sanction programs
    remarks: Optional[str]

class OFACScreeningService:
    """
    OFAC and Export Control Screening Service
    Screens individuals and entities against US sanctions lists
    """
    
    def __init__(self):
        self.base_url = "https://api.trade.gov/consolidated_screening_list/search"
        self.cache_duration = timedelta(hours=24)
        self.screening_cache = {}
        self.sanctions_lists = self._load_sanctions_lists()
        
    def _load_sanctions_lists(self) -> Dict[str, List[SanctionedEntity]]:
        """Load and cache sanctions lists from official sources"""
        try:
            # In production, this would fetch from official OFAC APIs
            # For now, we'll simulate with key sanctioned entities
            return {
                'SDN': self._load_sdn_list(),
                'SSI': self._load_ssi_list(),
                'EL': self._load_entity_list(),
                'DTC': self._load_dtc_list()
            }
        except Exception as e:
            logger.error(f"Failed to load sanctions lists: {e}")
            return {}
    
    def _load_sdn_list(self) -> List[SanctionedEntity]:
        """Load Specially Designated Nationals (SDN) list"""
        # Simulated SDN entries - in production, fetch from OFAC API
        return [
            SanctionedEntity(
                name="BLOCKED PERSON",
                entity_type="INDIVIDUAL",
                list_source="SDN",
                country="XX",
                aliases=["BLOCKED INDIVIDUAL", "SANCTIONED PERSON"],
                addresses=["123 Blocked Street, Sanctioned City"],
                identifiers=[{"type": "passport", "value": "BLOCKED123"}],
                programs=["SANCTIONS_PROGRAM"],
                remarks="Example sanctioned individual for testing"
            )
        ]
    
    def _load_ssi_list(self) -> List[SanctionedEntity]:
        """Load Sectoral Sanctions Identifications (SSI) list"""
        return []
    
    def _load_entity_list(self) -> List[SanctionedEntity]:
        """Load Entity List (Bureau of Industry and Security)"""
        return []
    
    def _load_dtc_list(self) -> List[SanctionedEntity]:
        """Load Denied Persons List (Directorate of Defense Trade Controls)"""
        return []
    
    def screen_individual(self, 
                         name: str,
                         country: Optional[str] = None,
                         date_of_birth: Optional[str] = None,
                         passport_number: Optional[str] = None,
                         national_id: Optional[str] = None,
                         address: Optional[str] = None) -> ScreeningResult:
        """
        Screen an individual against OFAC and export control lists
        
        Args:
            name: Full name of the individual
            country: Country of residence/citizenship
            date_of_birth: Date of birth (YYYY-MM-DD)
            passport_number: Passport number
            national_id: National ID number
            address: Residential address
            
        Returns:
            ScreeningResult with screening outcome
        """
        screening_id = self._generate_screening_id(name, country)
        
        # Check cache first
        if screening_id in self.screening_cache:
            cached_result = self.screening_cache[screening_id]
            if datetime.now() - cached_result.timestamp < self.cache_duration:
                logger.info(f"Returning cached screening result for {screening_id}")
                return cached_result
        
        logger.info(f"Screening individual: {name} from {country}")
        
        matches = []
        risk_level = "LOW"
        
        # Screen against all sanctions lists
        for list_name, entities in self.sanctions_lists.items():
            list_matches = self._screen_against_list(
                name=name,
                country=country,
                entities=entities,
                list_source=list_name,
                identifiers={
                    'passport': passport_number,
                    'national_id': national_id,
                    'dob': date_of_birth
                },
                address=address
            )
            matches.extend(list_matches)
        
        # Determine risk level based on matches
        if matches:
            risk_level = self._calculate_risk_level(matches)
        
        # Additional country-based screening
        if country:
            country_risk = self._screen_country_risk(country)
            if country_risk > 0:
                risk_level = max(risk_level, "MEDIUM")
        
        is_clear = risk_level in ["LOW", "MEDIUM"]
        
        result = ScreeningResult(
            is_clear=is_clear,
            risk_level=risk_level,
            matches=matches,
            screening_id=screening_id,
            timestamp=datetime.now(),
            details={
                'name': name,
                'country': country,
                'screening_method': 'COMPREHENSIVE',
                'lists_checked': list(self.sanctions_lists.keys()),
                'match_count': len(matches)
            }
        )
        
        # Cache result
        self.screening_cache[screening_id] = result
        
        logger.info(f"Screening complete: {screening_id} - {risk_level} risk")
        return result
    
    def screen_entity(self,
                     entity_name: str,
                     country: Optional[str] = None,
                     entity_type: Optional[str] = None,
                     tax_id: Optional[str] = None,
                     address: Optional[str] = None) -> ScreeningResult:
        """
        Screen a business entity against sanctions lists
        
        Args:
            entity_name: Name of the business entity
            country: Country of incorporation/operation
            entity_type: Type of entity (corporation, LLC, etc.)
            tax_id: Tax identification number
            address: Business address
            
        Returns:
            ScreeningResult with screening outcome
        """
        screening_id = self._generate_screening_id(entity_name, country)
        
        logger.info(f"Screening entity: {entity_name} from {country}")
        
        matches = []
        risk_level = "LOW"
        
        # Screen against sanctions lists
        for list_name, entities in self.sanctions_lists.items():
            list_matches = self._screen_against_list(
                name=entity_name,
                country=country,
                entities=entities,
                list_source=list_name,
                identifiers={'tax_id': tax_id},
                address=address,
                entity_type=entity_type
            )
            matches.extend(list_matches)
        
        if matches:
            risk_level = self._calculate_risk_level(matches)
        
        # Country risk assessment
        if country:
            country_risk = self._screen_country_risk(country)
            if country_risk > 0:
                risk_level = max(risk_level, "MEDIUM")
        
        is_clear = risk_level in ["LOW", "MEDIUM"]
        
        result = ScreeningResult(
            is_clear=is_clear,
            risk_level=risk_level,
            matches=matches,
            screening_id=screening_id,
            timestamp=datetime.now(),
            details={
                'entity_name': entity_name,
                'country': country,
                'entity_type': entity_type,
                'screening_method': 'ENTITY_COMPREHENSIVE',
                'lists_checked': list(self.sanctions_lists.keys()),
                'match_count': len(matches)
            }
        )
        
        self.screening_cache[screening_id] = result
        
        logger.info(f"Entity screening complete: {screening_id} - {risk_level} risk")
        return result
    
    def _screen_against_list(self,
                           name: str,
                           country: Optional[str],
                           entities: List[SanctionedEntity],
                           list_source: str,
                           identifiers: Dict[str, Optional[str]] = None,
                           address: Optional[str] = None,
                           entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Screen against a specific sanctions list"""
        matches = []
        identifiers = identifiers or {}
        
        for entity in entities:
            match_score = 0
            match_reasons = []
            
            # Name matching
            name_similarity = self._calculate_name_similarity(name, entity.name)
            if name_similarity > 0.8:
                match_score += name_similarity * 100
                match_reasons.append(f"Name similarity: {name_similarity:.2f}")
            
            # Alias matching
            for alias in entity.aliases:
                alias_similarity = self._calculate_name_similarity(name, alias)
                if alias_similarity > 0.8:
                    match_score += alias_similarity * 80
                    match_reasons.append(f"Alias similarity: {alias_similarity:.2f}")
            
            # Country matching
            if country and entity.country:
                if country.upper() == entity.country.upper():
                    match_score += 50
                    match_reasons.append("Country match")
            
            # Identifier matching
            for id_type, id_value in identifiers.items():
                if id_value:
                    for entity_id in entity.identifiers:
                        if (entity_id.get('type') == id_type and 
                            entity_id.get('value') == id_value):
                            match_score += 200  # High score for exact ID match
                            match_reasons.append(f"Exact {id_type} match")
            
            # Address matching
            if address and entity.addresses:
                for entity_address in entity.addresses:
                    address_similarity = self._calculate_address_similarity(address, entity_address)
                    if address_similarity > 0.7:
                        match_score += address_similarity * 30
                        match_reasons.append(f"Address similarity: {address_similarity:.2f}")
            
            # If significant match found, add to results
            if match_score > 80:  # Threshold for potential match
                matches.append({
                    'entity': {
                        'name': entity.name,
                        'type': entity.entity_type,
                        'country': entity.country,
                        'programs': entity.programs,
                        'list_source': list_source
                    },
                    'match_score': match_score,
                    'match_reasons': match_reasons,
                    'confidence': min(match_score / 100, 1.0)
                })
        
        return matches
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names"""
        if not name1 or not name2:
            return 0.0
        
        # Normalize names
        name1_norm = self._normalize_name(name1)
        name2_norm = self._normalize_name(name2)
        
        # Use sequence matcher for similarity
        return SequenceMatcher(None, name1_norm, name2_norm).ratio()
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name for comparison"""
        # Remove special characters, convert to uppercase, remove extra spaces
        normalized = re.sub(r'[^\w\s]', '', name.upper())
        normalized = ' '.join(normalized.split())
        return normalized
    
    def _calculate_address_similarity(self, addr1: str, addr2: str) -> float:
        """Calculate similarity between two addresses"""
        if not addr1 or not addr2:
            return 0.0
        
        # Normalize addresses
        addr1_norm = re.sub(r'[^\w\s]', '', addr1.upper())
        addr2_norm = re.sub(r'[^\w\s]', '', addr2.upper())
        
        return SequenceMatcher(None, addr1_norm, addr2_norm).ratio()
    
    def _calculate_risk_level(self, matches: List[Dict[str, Any]]) -> str:
        """Calculate overall risk level based on matches"""
        if not matches:
            return "LOW"
        
        max_score = max(match['match_score'] for match in matches)
        high_confidence_matches = [m for m in matches if m['confidence'] > 0.9]
        
        if high_confidence_matches or max_score > 150:
            return "BLOCKED"
        elif max_score > 120:
            return "HIGH"
        elif max_score > 90:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _screen_country_risk(self, country: str) -> int:
        """Assess country-based risk level"""
        # High-risk countries (simplified list)
        high_risk_countries = {
            'IR': 3,  # Iran
            'KP': 3,  # North Korea
            'SY': 3,  # Syria
            'CU': 2,  # Cuba
            'SD': 2,  # Sudan
            'MM': 2,  # Myanmar
        }
        
        return high_risk_countries.get(country.upper(), 0)
    
    def _generate_screening_id(self, name: str, country: Optional[str]) -> str:
        """Generate unique screening ID"""
        data = f"{name}_{country}_{datetime.now().date()}"
        return hashlib.md5(data.encode()).hexdigest()[:12]
    
    def get_screening_report(self, screening_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed screening report by ID"""
        if screening_id in self.screening_cache:
            result = self.screening_cache[screening_id]
            return {
                'screening_id': screening_id,
                'timestamp': result.timestamp.isoformat(),
                'risk_level': result.risk_level,
                'is_clear': result.is_clear,
                'match_count': len(result.matches),
                'matches': result.matches,
                'details': result.details
            }
        return None
    
    def update_sanctions_lists(self) -> bool:
        """Update sanctions lists from official sources"""
        try:
            logger.info("Updating sanctions lists from official sources")
            # In production, this would fetch latest data from OFAC APIs
            self.sanctions_lists = self._load_sanctions_lists()
            # Clear cache to force re-screening with updated lists
            self.screening_cache.clear()
            logger.info("Sanctions lists updated successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to update sanctions lists: {e}")
            return False

class ExportControlScreening:
    """
    Export Control Screening for technology and dual-use items
    Screens against Entity List, Denied Persons List, etc.
    """
    
    def __init__(self):
        self.restricted_technologies = self._load_restricted_technologies()
        self.restricted_countries = self._load_restricted_countries()
    
    def _load_restricted_technologies(self) -> List[str]:
        """Load list of export-controlled technologies"""
        return [
            'CRYPTOGRAPHY',
            'ENCRYPTION_SOFTWARE',
            'BIOMETRIC_SYSTEMS',
            'IDENTITY_VERIFICATION',
            'SURVEILLANCE_TECHNOLOGY',
            'DUAL_USE_TECHNOLOGY'
        ]
    
    def _load_restricted_countries(self) -> Dict[str, int]:
        """Load countries with export restrictions"""
        return {
            'IR': 5,  # Iran - highest restrictions
            'KP': 5,  # North Korea
            'SY': 5,  # Syria
            'CU': 4,  # Cuba
            'RU': 3,  # Russia (varies by technology)
            'CN': 2,  # China (some restrictions)
        }
    
    def screen_technology_export(self,
                               technology_type: str,
                               destination_country: str,
                               end_user: str,
                               intended_use: str) -> ScreeningResult:
        """Screen technology export for compliance"""
        screening_id = self._generate_screening_id(technology_type, destination_country)
        
        risk_level = "LOW"
        matches = []
        
        # Check technology restrictions
        if technology_type.upper() in self.restricted_technologies:
            country_risk = self.restricted_countries.get(destination_country.upper(), 0)
            
            if country_risk >= 4:
                risk_level = "BLOCKED"
                matches.append({
                    'type': 'TECHNOLOGY_RESTRICTION',
                    'reason': f'Export of {technology_type} to {destination_country} is prohibited',
                    'severity': 'HIGH'
                })
            elif country_risk >= 2:
                risk_level = "HIGH"
                matches.append({
                    'type': 'TECHNOLOGY_RESTRICTION',
                    'reason': f'Export of {technology_type} to {destination_country} requires license',
                    'severity': 'MEDIUM'
                })
        
        is_clear = risk_level in ["LOW", "MEDIUM"]
        
        return ScreeningResult(
            is_clear=is_clear,
            risk_level=risk_level,
            matches=matches,
            screening_id=screening_id,
            timestamp=datetime.now(),
            details={
                'technology_type': technology_type,
                'destination_country': destination_country,
                'end_user': end_user,
                'intended_use': intended_use,
                'screening_type': 'EXPORT_CONTROL'
            }
        )
    
    def _generate_screening_id(self, tech_type: str, country: str) -> str:
        """Generate screening ID for export control"""
        data = f"export_{tech_type}_{country}_{datetime.now().date()}"
        return hashlib.md5(data.encode()).hexdigest()[:12]

# Integration with KYC process
class KYCComplianceScreening:
    """
    Integrated KYC compliance screening combining OFAC and export controls
    """
    
    def __init__(self):
        self.ofac_service = OFACScreeningService()
        self.export_control = ExportControlScreening()
    
    def comprehensive_kyc_screening(self,
                                  customer_data: Dict[str, Any],
                                  service_type: str = "HUMAN_VERIFICATION") -> Dict[str, Any]:
        """
        Perform comprehensive KYC screening including OFAC and export controls
        
        Args:
            customer_data: Customer information for screening
            service_type: Type of service being provided
            
        Returns:
            Comprehensive screening results
        """
        results = {
            'overall_status': 'PENDING',
            'risk_level': 'LOW',
            'screening_timestamp': datetime.now().isoformat(),
            'screenings': {}
        }
        
        # Individual/Entity OFAC screening
        if customer_data.get('entity_type') == 'INDIVIDUAL':
            ofac_result = self.ofac_service.screen_individual(
                name=customer_data.get('name', ''),
                country=customer_data.get('country'),
                date_of_birth=customer_data.get('date_of_birth'),
                passport_number=customer_data.get('passport_number'),
                national_id=customer_data.get('national_id'),
                address=customer_data.get('address')
            )
        else:
            ofac_result = self.ofac_service.screen_entity(
                entity_name=customer_data.get('name', ''),
                country=customer_data.get('country'),
                entity_type=customer_data.get('entity_type'),
                tax_id=customer_data.get('tax_id'),
                address=customer_data.get('address')
            )
        
        results['screenings']['ofac'] = {
            'status': 'CLEAR' if ofac_result.is_clear else 'BLOCKED',
            'risk_level': ofac_result.risk_level,
            'matches': len(ofac_result.matches),
            'screening_id': ofac_result.screening_id
        }
        
        # Export control screening for technology services
        if service_type in ['HUMAN_VERIFICATION', 'IDENTITY_VERIFICATION']:
            export_result = self.export_control.screen_technology_export(
                technology_type='IDENTITY_VERIFICATION',
                destination_country=customer_data.get('country', ''),
                end_user=customer_data.get('name', ''),
                intended_use='Human verification services'
            )
            
            results['screenings']['export_control'] = {
                'status': 'CLEAR' if export_result.is_clear else 'BLOCKED',
                'risk_level': export_result.risk_level,
                'matches': len(export_result.matches),
                'screening_id': export_result.screening_id
            }
        
        # Determine overall status
        all_clear = all(
            screening.get('status') == 'CLEAR' 
            for screening in results['screenings'].values()
        )
        
        if all_clear:
            results['overall_status'] = 'APPROVED'
            results['risk_level'] = max(
                screening.get('risk_level', 'LOW') 
                for screening in results['screenings'].values()
            )
        else:
            results['overall_status'] = 'BLOCKED'
            results['risk_level'] = 'BLOCKED'
        
        return results

# Example usage and testing
if __name__ == "__main__":
    # Initialize screening services
    kyc_screening = KYCComplianceScreening()
    
    # Test individual screening
    test_individual = {
        'entity_type': 'INDIVIDUAL',
        'name': 'John Smith',
        'country': 'US',
        'date_of_birth': '1990-01-01',
        'address': '123 Main St, New York, NY'
    }
    
    result = kyc_screening.comprehensive_kyc_screening(test_individual)
    print("Individual Screening Result:")
    print(json.dumps(result, indent=2))
    
    # Test entity screening
    test_entity = {
        'entity_type': 'CORPORATION',
        'name': 'Tech Company Inc',
        'country': 'US',
        'tax_id': '12-3456789',
        'address': '456 Business Ave, San Francisco, CA'
    }
    
    result = kyc_screening.comprehensive_kyc_screening(test_entity)
    print("\nEntity Screening Result:")
    print(json.dumps(result, indent=2)) 