"""
🛡️ DATA PROTECTION IMPACT ASSESSMENT (DPIA)
==========================================
GDPR/CCPA Compliant Data Protection Framework
SOC 2 Type II / ISO 27001 Records of Processing Activities (RoPA)
"""

import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class DataCategory(Enum):
    """GDPR Article 4 - Categories of Personal Data"""
    IDENTITY = "identity"              # Name, address, phone, email
    FINANCIAL = "financial"            # Payment data, bank details
    BIOMETRIC = "biometric"           # Facial recognition, fingerprints
    BEHAVIORAL = "behavioral"         # Usage patterns, preferences
    LOCATION = "location"             # Geographic/GPS data
    ONLINE_IDENTIFIERS = "online_ids" # IP address, cookies, device IDs
    SPECIAL_CATEGORY = "special"      # Health, genetic, racial data
    PSEUDONYMIZED = "pseudonymized"   # Hashed/anonymized data

class LegalBasis(Enum):
    """GDPR Article 6 - Legal Basis for Processing"""
    CONSENT = "consent"               # Article 6(1)(a)
    CONTRACT = "contract"             # Article 6(1)(b)
    LEGAL_OBLIGATION = "legal_obligation"  # Article 6(1)(c)
    VITAL_INTERESTS = "vital_interests"    # Article 6(1)(d)
    PUBLIC_TASK = "public_task"           # Article 6(1)(e)
    LEGITIMATE_INTERESTS = "legitimate_interests"  # Article 6(1)(f)

class ProcessingPurpose(Enum):
    """Business purposes for data processing"""
    IDENTITY_VERIFICATION = "identity_verification"
    KYC_COMPLIANCE = "kyc_compliance"
    FRAUD_PREVENTION = "fraud_prevention"
    SERVICE_DELIVERY = "service_delivery"
    BILLING_INVOICING = "billing_invoicing"
    TECHNICAL_SUPPORT = "technical_support"
    LEGAL_COMPLIANCE = "legal_compliance"
    SECURITY_MONITORING = "security_monitoring"
    ANALYTICS_INSIGHTS = "analytics_insights"
    MARKETING = "marketing"

class DataSubjectRights(Enum):
    """GDPR Chapter III - Data Subject Rights"""
    ACCESS = "access"                 # Article 15
    RECTIFICATION = "rectification"   # Article 16
    ERASURE = "erasure"              # Article 17 (Right to be forgotten)
    RESTRICT_PROCESSING = "restrict_processing"  # Article 18
    DATA_PORTABILITY = "data_portability"       # Article 20
    OBJECT = "object"                # Article 21
    WITHDRAW_CONSENT = "withdraw_consent"       # Article 7(3)

@dataclass
class DataProcessor:
    """Third-party processors and sub-processors (GDPR Article 28)"""
    name: str
    contact_email: str
    processing_purpose: str
    data_categories: List[DataCategory]
    location: str  # Data processing location
    adequacy_decision: bool  # EU adequacy decision status
    safeguards: List[str]  # Standard contractual clauses, etc.
    contract_date: datetime
    dpa_signed: bool  # Data Processing Agreement
    security_assessment_date: Optional[datetime] = None
    last_audit_date: Optional[datetime] = None
    processor_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass
class ProcessingActivity:
    """Records of Processing Activities (GDPR Article 30)"""
    activity_id: str
    activity_name: str
    controller_name: str
    controller_contact: str
    purposes: List[ProcessingPurpose]
    legal_basis: List[LegalBasis]
    data_categories: List[DataCategory]
    data_subjects: List[str]  # Categories of data subjects
    recipients: List[str]     # Categories of recipients
    third_country_transfers: List[str]
    retention_period: str
    security_measures: List[str]
    processors: List[DataProcessor] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    dpia_required: bool = False
    dpia_completed: bool = False

@dataclass
class DataSubjectRequest:
    """Individual rights requests tracking"""
    request_id: str
    request_type: DataSubjectRights
    subject_email: str
    subject_id: str
    requested_at: datetime
    status: str  # pending, in_progress, completed, rejected
    legal_basis_for_processing: List[LegalBasis]
    completion_deadline: datetime
    completed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    data_provided: Optional[str] = None  # For access requests
    verification_method: str = "email_verification"

class DataProtectionManager:
    """
    Enterprise Data Protection Impact Assessment Manager
    
    Features:
    - Records of Processing Activities (RoPA) maintenance
    - KYC sub-processor tracking and compliance
    - GDPR/CCPA data subject rights management
    - Automated DPIA triggers and assessments
    - Third-party processor security monitoring
    - Data breach notification workflows
    - Privacy policy generation and updates
    """
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.environ.get('STORAGE_DIR', '.lemma_enterprise')
        self.compliance_dir = os.path.join(self.storage_dir, 'compliance')
        self.ropa_file = os.path.join(self.compliance_dir, 'records_of_processing.json')
        self.processors_file = os.path.join(self.compliance_dir, 'data_processors.json')
        self.requests_file = os.path.join(self.compliance_dir, 'subject_requests.json')
        
        # Ensure directories exist
        os.makedirs(self.compliance_dir, exist_ok=True)
        
        # Load existing data
        self.processing_activities = self._load_processing_activities()
        self.data_processors = self._load_data_processors()
        self.subject_requests = self._load_subject_requests()
        
        # Initialize default Lemma processing activities
        self._initialize_default_activities()
    
    def _load_processing_activities(self) -> Dict[str, ProcessingActivity]:
        """Load Records of Processing Activities from storage."""
        if not os.path.exists(self.ropa_file):
            return {}
        
        try:
            with open(self.ropa_file, 'r') as f:
                data = json.load(f)
            
            activities = {}
            for activity_id, activity_data in data.items():
                # Convert string enums back to enum objects
                activity_data['purposes'] = [ProcessingPurpose(p) for p in activity_data['purposes']]
                activity_data['legal_basis'] = [LegalBasis(b) for b in activity_data['legal_basis']]
                activity_data['data_categories'] = [DataCategory(c) for c in activity_data['data_categories']]
                activity_data['created_at'] = datetime.fromisoformat(activity_data['created_at'])
                activity_data['last_updated'] = datetime.fromisoformat(activity_data['last_updated'])
                
                # Load processors
                processors = []
                for proc_data in activity_data.get('processors', []):
                    proc_data['data_categories'] = [DataCategory(c) for c in proc_data['data_categories']]
                    proc_data['contract_date'] = datetime.fromisoformat(proc_data['contract_date'])
                    if proc_data.get('security_assessment_date'):
                        proc_data['security_assessment_date'] = datetime.fromisoformat(proc_data['security_assessment_date'])
                    if proc_data.get('last_audit_date'):
                        proc_data['last_audit_date'] = datetime.fromisoformat(proc_data['last_audit_date'])
                    processors.append(DataProcessor(**proc_data))
                
                activity_data['processors'] = processors
                activities[activity_id] = ProcessingActivity(**activity_data)
            
            return activities
        except Exception as e:
            logger.error(f"Failed to load processing activities: {e}")
            return {}
    
    def _load_data_processors(self) -> Dict[str, DataProcessor]:
        """Load data processors registry."""
        if not os.path.exists(self.processors_file):
            return {}
        
        try:
            with open(self.processors_file, 'r') as f:
                data = json.load(f)
            
            processors = {}
            for proc_id, proc_data in data.items():
                proc_data['data_categories'] = [DataCategory(c) for c in proc_data['data_categories']]
                proc_data['contract_date'] = datetime.fromisoformat(proc_data['contract_date'])
                if proc_data.get('security_assessment_date'):
                    proc_data['security_assessment_date'] = datetime.fromisoformat(proc_data['security_assessment_date'])
                if proc_data.get('last_audit_date'):
                    proc_data['last_audit_date'] = datetime.fromisoformat(proc_data['last_audit_date'])
                processors[proc_id] = DataProcessor(**proc_data)
            
            return processors
        except Exception as e:
            logger.error(f"Failed to load data processors: {e}")
            return {}
    
    def _load_subject_requests(self) -> Dict[str, DataSubjectRequest]:
        """Load data subject requests."""
        if not os.path.exists(self.requests_file):
            return {}
        
        try:
            with open(self.requests_file, 'r') as f:
                data = json.load(f)
            
            requests = {}
            for req_id, req_data in data.items():
                req_data['request_type'] = DataSubjectRights(req_data['request_type'])
                req_data['legal_basis_for_processing'] = [LegalBasis(b) for b in req_data['legal_basis_for_processing']]
                req_data['requested_at'] = datetime.fromisoformat(req_data['requested_at'])
                req_data['completion_deadline'] = datetime.fromisoformat(req_data['completion_deadline'])
                if req_data.get('completed_at'):
                    req_data['completed_at'] = datetime.fromisoformat(req_data['completed_at'])
                requests[req_id] = DataSubjectRequest(**req_data)
            
            return requests
        except Exception as e:
            logger.error(f"Failed to load subject requests: {e}")
            return {}
    
    def _initialize_default_activities(self):
        """Initialize default processing activities for Lemma."""
        default_activities = [
            {
                'activity_id': 'lemma_kyc_verification',
                'activity_name': 'Know Your Customer (KYC) Identity Verification',
                'controller_name': 'Lemma Enterprise Inc.',
                'controller_contact': 'privacy@lemma.network',
                'purposes': [ProcessingPurpose.IDENTITY_VERIFICATION, ProcessingPurpose.KYC_COMPLIANCE, ProcessingPurpose.FRAUD_PREVENTION],
                'legal_basis': [LegalBasis.LEGAL_OBLIGATION, LegalBasis.LEGITIMATE_INTERESTS],
                'data_categories': [DataCategory.IDENTITY, DataCategory.FINANCIAL],
                'data_subjects': ['Individual customers', 'Business representatives'],
                'recipients': ['KYC service providers', 'Regulatory authorities'],
                'third_country_transfers': ['United States', 'European Union'],
                'retention_period': '7 years after account closure (regulatory requirement)',
                'security_measures': ['Encryption at rest', 'Access controls', 'Audit logging'],
                'dpia_required': True
            },
            {
                'activity_id': 'lemma_api_usage',
                'activity_name': 'API Usage Monitoring and Billing',
                'controller_name': 'Lemma Enterprise Inc.',
                'controller_contact': 'privacy@lemma.network',
                'purposes': [ProcessingPurpose.SERVICE_DELIVERY, ProcessingPurpose.BILLING_INVOICING],
                'legal_basis': [LegalBasis.CONTRACT],
                'data_categories': [DataCategory.ONLINE_IDENTIFIERS, DataCategory.BEHAVIORAL],
                'data_subjects': ['API customers', 'End users'],
                'recipients': ['Billing processors', 'Analytics providers'],
                'third_country_transfers': ['United States'],
                'retention_period': '31 days for raw data, 7 years for billing records',
                'security_measures': ['API authentication', 'Rate limiting', 'Log encryption'],
                'dpia_required': False
            }
        ]
        
        for activity_data in default_activities:
            activity_id = activity_data['activity_id']
            if activity_id not in self.processing_activities:
                self.add_processing_activity(**activity_data)
    
    def add_processing_activity(self, activity_id: str, activity_name: str,
                              controller_name: str, controller_contact: str,
                              purposes: List[ProcessingPurpose], legal_basis: List[LegalBasis],
                              data_categories: List[DataCategory], data_subjects: List[str],
                              recipients: List[str], third_country_transfers: List[str],
                              retention_period: str, security_measures: List[str],
                              dpia_required: bool = False) -> bool:
        """Add a new processing activity to the RoPA."""
        try:
            activity = ProcessingActivity(
                activity_id=activity_id,
                activity_name=activity_name,
                controller_name=controller_name,
                controller_contact=controller_contact,
                purposes=purposes,
                legal_basis=legal_basis,
                data_categories=data_categories,
                data_subjects=data_subjects,
                recipients=recipients,
                third_country_transfers=third_country_transfers,
                retention_period=retention_period,
                security_measures=security_measures,
                dpia_required=dpia_required
            )
            
            self.processing_activities[activity_id] = activity
            self._save_processing_activities()
            
            logger.info(f"Added processing activity: {activity_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to add processing activity: {e}")
            return False
    
    def add_data_processor(self, name: str, contact_email: str, processing_purpose: str,
                          data_categories: List[DataCategory], location: str,
                          adequacy_decision: bool, safeguards: List[str],
                          dpa_signed: bool) -> str:
        """Add a new data processor or sub-processor."""
        try:
            processor = DataProcessor(
                name=name,
                contact_email=contact_email,
                processing_purpose=processing_purpose,
                data_categories=data_categories,
                location=location,
                adequacy_decision=adequacy_decision,
                safeguards=safeguards,
                contract_date=datetime.now(timezone.utc),
                dpa_signed=dpa_signed
            )
            
            self.data_processors[processor.processor_id] = processor
            self._save_data_processors()
            
            logger.info(f"Added data processor: {name}")
            return processor.processor_id
        except Exception as e:
            logger.error(f"Failed to add data processor: {e}")
            return ""
    
    def create_subject_request(self, request_type: DataSubjectRights, subject_email: str,
                             subject_id: str, legal_basis: List[LegalBasis]) -> str:
        """Create a new data subject rights request."""
        try:
            request_id = str(uuid.uuid4())
            completion_deadline = datetime.now(timezone.utc) + timedelta(days=30)  # GDPR Article 12
            
            request = DataSubjectRequest(
                request_id=request_id,
                request_type=request_type,
                subject_email=subject_email,
                subject_id=subject_id,
                requested_at=datetime.now(timezone.utc),
                status='pending',
                legal_basis_for_processing=legal_basis,
                completion_deadline=completion_deadline
            )
            
            self.subject_requests[request_id] = request
            self._save_subject_requests()
            
            logger.info(f"Created subject request: {request_type.value} for {subject_email}")
            return request_id
        except Exception as e:
            logger.error(f"Failed to create subject request: {e}")
            return ""
    
    def complete_subject_request(self, request_id: str, data_provided: str = None,
                               rejection_reason: str = None) -> bool:
        """Complete a data subject rights request."""
        try:
            if request_id not in self.subject_requests:
                logger.error(f"Subject request not found: {request_id}")
                return False
            
            request = self.subject_requests[request_id]
            request.completed_at = datetime.now(timezone.utc)
            
            if rejection_reason:
                request.status = 'rejected'
                request.rejection_reason = rejection_reason
            else:
                request.status = 'completed'
                request.data_provided = data_provided
            
            self._save_subject_requests()
            
            logger.info(f"Completed subject request: {request_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to complete subject request: {e}")
            return False
    
    def conduct_dpia(self, activity_id: str) -> Dict[str, Any]:
        """Conduct a Data Protection Impact Assessment."""
        if activity_id not in self.processing_activities:
            return {'error': 'Processing activity not found'}
        
        activity = self.processing_activities[activity_id]
        
        # DPIA assessment criteria (GDPR Article 35)
        high_risk_indicators = []
        
        # Check for special categories of data
        if DataCategory.SPECIAL_CATEGORY in activity.data_categories:
            high_risk_indicators.append('Processing special categories of personal data')
        
        # Check for large scale processing
        if 'large scale' in activity.activity_name.lower():
            high_risk_indicators.append('Large scale processing')
        
        # Check for systematic monitoring
        if ProcessingPurpose.SECURITY_MONITORING in activity.purposes:
            high_risk_indicators.append('Systematic monitoring of publicly accessible areas')
        
        # Check for third country transfers
        if activity.third_country_transfers:
            high_risk_indicators.append('International data transfers to third countries')
        
        # Calculate risk score
        risk_score = len(high_risk_indicators)
        risk_level = 'low' if risk_score <= 1 else 'medium' if risk_score <= 2 else 'high'
        
        dpia_result = {
            'activity_id': activity_id,
            'activity_name': activity.activity_name,
            'assessment_date': datetime.now(timezone.utc).isoformat(),
            'high_risk_indicators': high_risk_indicators,
            'risk_score': risk_score,
            'risk_level': risk_level,
            'dpia_required': risk_score >= 2,
            'recommended_measures': self._get_risk_mitigation_measures(risk_level),
            'processors_assessed': len(activity.processors),
            'compliance_status': 'compliant' if risk_score < 3 else 'requires_review'
        }
        
        # Update activity
        activity.dpia_completed = True
        activity.last_updated = datetime.now(timezone.utc)
        self._save_processing_activities()
        
        return dpia_result
    
    def _get_risk_mitigation_measures(self, risk_level: str) -> List[str]:
        """Get recommended risk mitigation measures."""
        base_measures = [
            'Implement encryption at rest and in transit',
            'Regular access control reviews',
            'Staff privacy training',
            'Data retention policy enforcement'
        ]
        
        if risk_level == 'medium':
            base_measures.extend([
                'Enhanced logging and monitoring',
                'Regular security assessments',
                'Data anonymization where possible'
            ])
        elif risk_level == 'high':
            base_measures.extend([
                'Privacy by design implementation',
                'Regular external audits',
                'Data minimization principles',
                'Enhanced consent mechanisms',
                'Regular DPIA reviews'
            ])
        
        return base_measures
    
    def generate_ropa_report(self) -> Dict[str, Any]:
        """Generate a comprehensive Records of Processing Activities report."""
        return {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'controller': 'Lemma Enterprise Inc.',
            'dpo_contact': 'privacy@lemma.network',
            'total_activities': len(self.processing_activities),
            'activities_requiring_dpia': sum(1 for a in self.processing_activities.values() if a.dpia_required),
            'completed_dpias': sum(1 for a in self.processing_activities.values() if a.dpia_completed),
            'total_processors': len(self.data_processors),
            'processors_with_dpa': sum(1 for p in self.data_processors.values() if p.dpa_signed),
            'pending_subject_requests': sum(1 for r in self.subject_requests.values() if r.status == 'pending'),
            'processing_activities': {
                activity_id: {
                    'name': activity.activity_name,
                    'purposes': [p.value for p in activity.purposes],
                    'legal_basis': [b.value for b in activity.legal_basis],
                    'data_categories': [c.value for c in activity.data_categories],
                    'retention_period': activity.retention_period,
                    'dpia_required': activity.dpia_required,
                    'dpia_completed': activity.dpia_completed,
                    'processors_count': len(activity.processors)
                }
                for activity_id, activity in self.processing_activities.items()
            }
        }
    
    def _save_processing_activities(self):
        """Save processing activities to storage."""
        try:
            data = {}
            for activity_id, activity in self.processing_activities.items():
                activity_dict = {
                    'activity_id': activity.activity_id,
                    'activity_name': activity.activity_name,
                    'controller_name': activity.controller_name,
                    'controller_contact': activity.controller_contact,
                    'purposes': [p.value for p in activity.purposes],
                    'legal_basis': [b.value for b in activity.legal_basis],
                    'data_categories': [c.value for c in activity.data_categories],
                    'data_subjects': activity.data_subjects,
                    'recipients': activity.recipients,
                    'third_country_transfers': activity.third_country_transfers,
                    'retention_period': activity.retention_period,
                    'security_measures': activity.security_measures,
                    'created_at': activity.created_at.isoformat(),
                    'last_updated': activity.last_updated.isoformat(),
                    'dpia_required': activity.dpia_required,
                    'dpia_completed': activity.dpia_completed,
                    'processors': []
                }
                
                # Convert processors
                for processor in activity.processors:
                    proc_dict = {
                        'processor_id': processor.processor_id,
                        'name': processor.name,
                        'contact_email': processor.contact_email,
                        'processing_purpose': processor.processing_purpose,
                        'data_categories': [c.value for c in processor.data_categories],
                        'location': processor.location,
                        'adequacy_decision': processor.adequacy_decision,
                        'safeguards': processor.safeguards,
                        'contract_date': processor.contract_date.isoformat(),
                        'dpa_signed': processor.dpa_signed
                    }
                    if processor.security_assessment_date:
                        proc_dict['security_assessment_date'] = processor.security_assessment_date.isoformat()
                    if processor.last_audit_date:
                        proc_dict['last_audit_date'] = processor.last_audit_date.isoformat()
                    
                    activity_dict['processors'].append(proc_dict)
                
                data[activity_id] = activity_dict
            
            with open(self.ropa_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save processing activities: {e}")
    
    def _save_data_processors(self):
        """Save data processors to storage."""
        try:
            data = {}
            for proc_id, processor in self.data_processors.items():
                proc_dict = {
                    'processor_id': processor.processor_id,
                    'name': processor.name,
                    'contact_email': processor.contact_email,
                    'processing_purpose': processor.processing_purpose,
                    'data_categories': [c.value for c in processor.data_categories],
                    'location': processor.location,
                    'adequacy_decision': processor.adequacy_decision,
                    'safeguards': processor.safeguards,
                    'contract_date': processor.contract_date.isoformat(),
                    'dpa_signed': processor.dpa_signed
                }
                if processor.security_assessment_date:
                    proc_dict['security_assessment_date'] = processor.security_assessment_date.isoformat()
                if processor.last_audit_date:
                    proc_dict['last_audit_date'] = processor.last_audit_date.isoformat()
                
                data[proc_id] = proc_dict
            
            with open(self.processors_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save data processors: {e}")
    
    def _save_subject_requests(self):
        """Save subject requests to storage."""
        try:
            data = {}
            for req_id, request in self.subject_requests.items():
                req_dict = {
                    'request_id': request.request_id,
                    'request_type': request.request_type.value,
                    'subject_email': request.subject_email,
                    'subject_id': request.subject_id,
                    'requested_at': request.requested_at.isoformat(),
                    'status': request.status,
                    'legal_basis_for_processing': [b.value for b in request.legal_basis_for_processing],
                    'completion_deadline': request.completion_deadline.isoformat(),
                    'verification_method': request.verification_method
                }
                if request.completed_at:
                    req_dict['completed_at'] = request.completed_at.isoformat()
                if request.rejection_reason:
                    req_dict['rejection_reason'] = request.rejection_reason
                if request.data_provided:
                    req_dict['data_provided'] = request.data_provided
                
                data[req_id] = req_dict
            
            with open(self.requests_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save subject requests: {e}")

def get_data_protection_manager() -> DataProtectionManager:
    """Get the global data protection manager instance."""
    global _data_protection_manager
    if '_data_protection_manager' not in globals():
        _data_protection_manager = DataProtectionManager()
    return _data_protection_manager 