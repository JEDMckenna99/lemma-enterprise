"""
📋 THIRD-PARTY AUDIT FRAMEWORK
=============================
SOC 2 Type II / ISO 27001 Compliance Management
Audit Engagement and Evidence Collection System
"""

import os
import json
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class AuditType(Enum):
    """Types of compliance audits"""
    SOC2_TYPE_I = "soc2_type_i"
    SOC2_TYPE_II = "soc2_type_ii"
    ISO_27001 = "iso_27001"
    PCI_DSS = "pci_dss"
    GDPR_COMPLIANCE = "gdpr_compliance"
    HIPAA = "hipaa"
    CUSTOM = "custom"

class AuditStatus(Enum):
    """Audit engagement status"""
    PLANNING = "planning"
    ENGAGEMENT_SIGNED = "engagement_signed"
    FIELDWORK = "fieldwork"
    TESTING = "testing"
    REPORTING = "reporting"
    COMPLETED = "completed"
    REMEDIATION = "remediation"

class ControlCategory(Enum):
    """SOC 2 Trust Service Categories"""
    SECURITY = "security"
    AVAILABILITY = "availability"
    PROCESSING_INTEGRITY = "processing_integrity"
    CONFIDENTIALITY = "confidentiality"
    PRIVACY = "privacy"

class ControlStatus(Enum):
    """Control implementation status"""
    NOT_IMPLEMENTED = "not_implemented"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    IMPLEMENTED = "implemented"
    OPERATING_EFFECTIVELY = "operating_effectively"
    DEFICIENT = "deficient"

@dataclass
class AuditFirm:
    """Third-party audit firm information"""
    firm_name: str
    contact_person: str
    email: str
    phone: str
    certifications: List[str]
    specializations: List[AuditType]
    engagement_letter_signed: bool = False
    engagement_date: Optional[datetime] = None
    firm_id: str = field(default_factory=lambda: str(uuid.uuid4()))

@dataclass
class ControlRequirement:
    """Individual control requirement"""
    control_id: str
    control_name: str
    category: ControlCategory
    description: str
    implementation_guidance: str
    testing_procedures: List[str]
    evidence_requirements: List[str]
    status: ControlStatus = ControlStatus.NOT_IMPLEMENTED
    implementation_date: Optional[datetime] = None
    last_tested: Optional[datetime] = None
    deficiencies: List[str] = field(default_factory=list)
    remediation_plan: Optional[str] = None

@dataclass
class AuditEvidence:
    """Evidence collected for audit"""
    evidence_id: str
    control_id: str
    evidence_type: str  # document, screenshot, log_file, interview, observation
    description: str
    file_path: Optional[str] = None
    collected_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    collected_by: str = "system"
    hash_value: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AuditEngagement:
    """Complete audit engagement tracking"""
    engagement_id: str
    audit_type: AuditType
    audit_firm: AuditFirm
    start_date: datetime
    target_completion_date: datetime
    status: AuditStatus
    scope_description: str
    controls: List[ControlRequirement] = field(default_factory=list)
    evidence: List[AuditEvidence] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    completed_date: Optional[datetime] = None
    report_issued_date: Optional[datetime] = None
    certification_achieved: bool = False

class ThirdPartyAuditManager:
    """
    Enterprise Third-Party Audit Management System
    
    Features:
    - SOC 2 Type II and ISO 27001 audit management
    - Signed engagement letter tracking
    - Control implementation monitoring
    - Evidence collection and management
    - Audit timeline and milestone tracking
    - Compliance gap analysis and remediation
    - Automated evidence gathering
    - Audit readiness assessments
    """
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.environ.get('STORAGE_DIR', '.lemma_enterprise')
        self.audit_dir = os.path.join(self.storage_dir, 'audits')
        self.evidence_dir = os.path.join(self.audit_dir, 'evidence')
        self.engagements_file = os.path.join(self.audit_dir, 'engagements.json')
        self.controls_file = os.path.join(self.audit_dir, 'controls.json')
        self.firms_file = os.path.join(self.audit_dir, 'audit_firms.json')
        
        # Ensure directories exist
        os.makedirs(self.evidence_dir, exist_ok=True)
        
        # Load existing data
        self.engagements = self._load_engagements()
        self.controls = self._load_controls()
        self.audit_firms = self._load_audit_firms()
        
        # Initialize default controls
        self._initialize_default_controls()
    
    def _load_engagements(self) -> Dict[str, AuditEngagement]:
        """Load audit engagements from storage."""
        if not os.path.exists(self.engagements_file):
            return {}
        
        try:
            with open(self.engagements_file, 'r') as f:
                data = json.load(f)
            
            engagements = {}
            for engagement_id, engagement_data in data.items():
                # Convert datetime strings
                engagement_data['start_date'] = datetime.fromisoformat(engagement_data['start_date'])
                engagement_data['target_completion_date'] = datetime.fromisoformat(engagement_data['target_completion_date'])
                if engagement_data.get('completed_date'):
                    engagement_data['completed_date'] = datetime.fromisoformat(engagement_data['completed_date'])
                if engagement_data.get('report_issued_date'):
                    engagement_data['report_issued_date'] = datetime.fromisoformat(engagement_data['report_issued_date'])
                
                # Convert enums
                engagement_data['audit_type'] = AuditType(engagement_data['audit_type'])
                engagement_data['status'] = AuditStatus(engagement_data['status'])
                
                # Convert audit firm
                firm_data = engagement_data['audit_firm']
                firm_data['specializations'] = [AuditType(s) for s in firm_data['specializations']]
                if firm_data.get('engagement_date'):
                    firm_data['engagement_date'] = datetime.fromisoformat(firm_data['engagement_date'])
                engagement_data['audit_firm'] = AuditFirm(**firm_data)
                
                # Convert controls
                controls = []
                for control_data in engagement_data.get('controls', []):
                    control_data['category'] = ControlCategory(control_data['category'])
                    control_data['status'] = ControlStatus(control_data['status'])
                    if control_data.get('implementation_date'):
                        control_data['implementation_date'] = datetime.fromisoformat(control_data['implementation_date'])
                    if control_data.get('last_tested'):
                        control_data['last_tested'] = datetime.fromisoformat(control_data['last_tested'])
                    controls.append(ControlRequirement(**control_data))
                engagement_data['controls'] = controls
                
                # Convert evidence
                evidence = []
                for evidence_data in engagement_data.get('evidence', []):
                    evidence_data['collected_date'] = datetime.fromisoformat(evidence_data['collected_date'])
                    evidence.append(AuditEvidence(**evidence_data))
                engagement_data['evidence'] = evidence
                
                engagements[engagement_id] = AuditEngagement(**engagement_data)
            
            return engagements
        except Exception as e:
            logger.error(f"Failed to load audit engagements: {e}")
            return {}
    
    def _load_controls(self) -> Dict[str, ControlRequirement]:
        """Load control requirements from storage."""
        if not os.path.exists(self.controls_file):
            return {}
        
        try:
            with open(self.controls_file, 'r') as f:
                data = json.load(f)
            
            controls = {}
            for control_id, control_data in data.items():
                control_data['category'] = ControlCategory(control_data['category'])
                control_data['status'] = ControlStatus(control_data['status'])
                if control_data.get('implementation_date'):
                    control_data['implementation_date'] = datetime.fromisoformat(control_data['implementation_date'])
                if control_data.get('last_tested'):
                    control_data['last_tested'] = datetime.fromisoformat(control_data['last_tested'])
                controls[control_id] = ControlRequirement(**control_data)
            
            return controls
        except Exception as e:
            logger.error(f"Failed to load controls: {e}")
            return {}
    
    def _load_audit_firms(self) -> Dict[str, AuditFirm]:
        """Load audit firms from storage."""
        if not os.path.exists(self.firms_file):
            return {}
        
        try:
            with open(self.firms_file, 'r') as f:
                data = json.load(f)
            
            firms = {}
            for firm_id, firm_data in data.items():
                firm_data['specializations'] = [AuditType(s) for s in firm_data['specializations']]
                if firm_data.get('engagement_date'):
                    firm_data['engagement_date'] = datetime.fromisoformat(firm_data['engagement_date'])
                firms[firm_id] = AuditFirm(**firm_data)
            
            return firms
        except Exception as e:
            logger.error(f"Failed to load audit firms: {e}")
            return {}
    
    def _initialize_default_controls(self):
        """Initialize default SOC 2 and ISO 27001 controls."""
        if not self.controls:
            default_controls = [
                # SOC 2 Security Controls
                {
                    'control_id': 'CC6.1',
                    'control_name': 'Logical and Physical Access Controls',
                    'category': ControlCategory.SECURITY,
                    'description': 'The entity implements logical and physical access controls to protect against threats from sources outside its system boundaries.',
                    'implementation_guidance': 'Implement multi-factor authentication, access reviews, and physical security controls.',
                    'testing_procedures': ['Review access control policies', 'Test MFA implementation', 'Observe physical security'],
                    'evidence_requirements': ['Access control policy', 'MFA configuration', 'Access review reports']
                },
                {
                    'control_id': 'CC6.2',
                    'control_name': 'Logical and Physical Access Controls - User Access',
                    'category': ControlCategory.SECURITY,
                    'description': 'Prior to issuing system credentials and granting system access, the entity registers and authorizes new internal and external users.',
                    'implementation_guidance': 'Implement user provisioning and deprovisioning procedures with approval workflows.',
                    'testing_procedures': ['Review user provisioning process', 'Test approval workflows', 'Verify deprovisioning'],
                    'evidence_requirements': ['User access request forms', 'Approval documentation', 'Deprovisioning logs']
                },
                {
                    'control_id': 'CC6.3',
                    'control_name': 'Logical and Physical Access Controls - Network Security',
                    'category': ControlCategory.SECURITY,
                    'description': 'The entity authorizes, modifies, or removes access to data, software, functions, and other protected information assets.',
                    'implementation_guidance': 'Implement network segmentation, firewalls, and intrusion detection systems.',
                    'testing_procedures': ['Review network architecture', 'Test firewall rules', 'Verify IDS configuration'],
                    'evidence_requirements': ['Network diagrams', 'Firewall configurations', 'IDS logs']
                },
                {
                    'control_id': 'CC7.1',
                    'control_name': 'System Operations - Data Backup and Recovery',
                    'category': ControlCategory.AVAILABILITY,
                    'description': 'To meet its objectives, the entity uses detection and monitoring procedures to identify system security events.',
                    'implementation_guidance': 'Implement automated backup systems with regular recovery testing.',
                    'testing_procedures': ['Review backup procedures', 'Test recovery processes', 'Verify backup integrity'],
                    'evidence_requirements': ['Backup policies', 'Recovery test results', 'Backup verification logs']
                },
                {
                    'control_id': 'CC8.1',
                    'control_name': 'Change Management',
                    'category': ControlCategory.PROCESSING_INTEGRITY,
                    'description': 'The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, and implements changes to infrastructure, data, software, and procedures.',
                    'implementation_guidance': 'Implement formal change management process with testing and approval requirements.',
                    'testing_procedures': ['Review change management policy', 'Test change approval process', 'Verify documentation'],
                    'evidence_requirements': ['Change management policy', 'Change request forms', 'Approval documentation']
                },
                
                # ISO 27001 Controls
                {
                    'control_id': 'A.5.1.1',
                    'control_name': 'Information Security Policies',
                    'category': ControlCategory.SECURITY,
                    'description': 'A set of policies for information security shall be defined, approved by management, published and communicated to employees and relevant external parties.',
                    'implementation_guidance': 'Develop comprehensive information security policies covering all aspects of the ISMS.',
                    'testing_procedures': ['Review policy documentation', 'Verify management approval', 'Test communication methods'],
                    'evidence_requirements': ['Security policies', 'Management approval records', 'Training records']
                },
                {
                    'control_id': 'A.6.1.1',
                    'control_name': 'Information Security Roles and Responsibilities',
                    'category': ControlCategory.SECURITY,
                    'description': 'All information security responsibilities shall be defined and allocated.',
                    'implementation_guidance': 'Define clear roles and responsibilities for information security across the organization.',
                    'testing_procedures': ['Review role definitions', 'Verify responsibility assignments', 'Test accountability measures'],
                    'evidence_requirements': ['Role descriptions', 'Responsibility matrices', 'Accountability documentation']
                },
                {
                    'control_id': 'A.12.6.1',
                    'control_name': 'Management of Technical Vulnerabilities',
                    'category': ControlCategory.SECURITY,
                    'description': 'Information about technical vulnerabilities of information systems being used shall be obtained in a timely fashion.',
                    'implementation_guidance': 'Implement vulnerability management program with regular scanning and patching.',
                    'testing_procedures': ['Review vulnerability management process', 'Test scanning procedures', 'Verify patch management'],
                    'evidence_requirements': ['Vulnerability scan reports', 'Patch management logs', 'Remediation tracking']
                }
            ]
            
            for control_data in default_controls:
                control = ControlRequirement(**control_data)
                self.controls[control.control_id] = control
            
            self._save_controls()
    
    def create_audit_engagement(self, audit_type: AuditType, audit_firm: AuditFirm,
                               start_date: datetime, target_completion_date: datetime,
                               scope_description: str) -> str:
        """Create a new audit engagement."""
        try:
            engagement_id = f"AUDIT-{int(datetime.now().timestamp())}-{str(uuid.uuid4())[:8]}"
            
            engagement = AuditEngagement(
                engagement_id=engagement_id,
                audit_type=audit_type,
                audit_firm=audit_firm,
                start_date=start_date,
                target_completion_date=target_completion_date,
                status=AuditStatus.PLANNING,
                scope_description=scope_description
            )
            
            # Add relevant controls based on audit type
            relevant_controls = self._get_relevant_controls(audit_type)
            engagement.controls = relevant_controls
            
            self.engagements[engagement_id] = engagement
            self._save_engagements()
            
            logger.info(f"Created audit engagement: {engagement_id}")
            return engagement_id
            
        except Exception as e:
            logger.error(f"Failed to create audit engagement: {e}")
            return ""
    
    def sign_engagement_letter(self, engagement_id: str, signed_date: datetime) -> bool:
        """Mark engagement letter as signed."""
        try:
            engagement = self.engagements.get(engagement_id)
            if not engagement:
                logger.error(f"Engagement not found: {engagement_id}")
                return False
            
            engagement.audit_firm.engagement_letter_signed = True
            engagement.audit_firm.engagement_date = signed_date
            engagement.status = AuditStatus.ENGAGEMENT_SIGNED
            
            self._save_engagements()
            logger.info(f"Engagement letter signed for: {engagement_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to sign engagement letter: {e}")
            return False
    
    def update_control_status(self, control_id: str, status: ControlStatus,
                             implementation_date: datetime = None,
                             deficiencies: List[str] = None,
                             remediation_plan: str = None) -> bool:
        """Update control implementation status."""
        try:
            control = self.controls.get(control_id)
            if not control:
                logger.error(f"Control not found: {control_id}")
                return False
            
            control.status = status
            if implementation_date:
                control.implementation_date = implementation_date
            if deficiencies:
                control.deficiencies = deficiencies
            if remediation_plan:
                control.remediation_plan = remediation_plan
            
            self._save_controls()
            logger.info(f"Updated control status: {control_id} -> {status.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update control status: {e}")
            return False
    
    def collect_evidence(self, control_id: str, evidence_type: str, description: str,
                        file_path: str = None, collected_by: str = "system",
                        metadata: Dict[str, Any] = None) -> str:
        """Collect evidence for a control."""
        try:
            evidence_id = str(uuid.uuid4())
            
            # Calculate hash if file provided
            hash_value = None
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    hash_value = hashlib.sha256(f.read()).hexdigest()
            
            evidence = AuditEvidence(
                evidence_id=evidence_id,
                control_id=control_id,
                evidence_type=evidence_type,
                description=description,
                file_path=file_path,
                collected_by=collected_by,
                hash_value=hash_value,
                metadata=metadata or {}
            )
            
            # Add evidence to all relevant engagements
            for engagement in self.engagements.values():
                if any(c.control_id == control_id for c in engagement.controls):
                    engagement.evidence.append(evidence)
            
            self._save_engagements()
            logger.info(f"Collected evidence: {evidence_id} for control {control_id}")
            return evidence_id
            
        except Exception as e:
            logger.error(f"Failed to collect evidence: {e}")
            return ""
    
    def generate_audit_readiness_report(self, engagement_id: str) -> Dict[str, Any]:
        """Generate audit readiness assessment report."""
        engagement = self.engagements.get(engagement_id)
        if not engagement:
            return {'error': 'Engagement not found'}
        
        total_controls = len(engagement.controls)
        implemented_controls = sum(1 for c in engagement.controls 
                                 if c.status in [ControlStatus.IMPLEMENTED, ControlStatus.OPERATING_EFFECTIVELY])
        deficient_controls = sum(1 for c in engagement.controls if c.status == ControlStatus.DEFICIENT)
        
        # Calculate readiness percentage
        readiness_percentage = (implemented_controls / total_controls * 100) if total_controls > 0 else 0
        
        # Evidence collection status
        controls_with_evidence = set(e.control_id for e in engagement.evidence)
        evidence_coverage = (len(controls_with_evidence) / total_controls * 100) if total_controls > 0 else 0
        
        # Gap analysis
        gaps = []
        for control in engagement.controls:
            if control.status in [ControlStatus.NOT_IMPLEMENTED, ControlStatus.PARTIALLY_IMPLEMENTED]:
                gaps.append({
                    'control_id': control.control_id,
                    'control_name': control.control_name,
                    'status': control.status.value,
                    'deficiencies': control.deficiencies,
                    'remediation_plan': control.remediation_plan
                })
        
        return {
            'engagement_id': engagement_id,
            'audit_type': engagement.audit_type.value,
            'audit_firm': engagement.audit_firm.firm_name,
            'engagement_letter_signed': engagement.audit_firm.engagement_letter_signed,
            'target_completion_date': engagement.target_completion_date.isoformat(),
            'days_remaining': (engagement.target_completion_date - datetime.now(timezone.utc)).days,
            'readiness_percentage': round(readiness_percentage, 1),
            'evidence_coverage_percentage': round(evidence_coverage, 1),
            'total_controls': total_controls,
            'implemented_controls': implemented_controls,
            'deficient_controls': deficient_controls,
            'gaps_requiring_attention': len(gaps),
            'control_gaps': gaps,
            'evidence_collected': len(engagement.evidence),
            'recommendations': self._get_readiness_recommendations(readiness_percentage, evidence_coverage, gaps)
        }
    
    def _get_readiness_recommendations(self, readiness_percentage: float, 
                                     evidence_coverage: float, gaps: List[Dict]) -> List[str]:
        """Get recommendations for audit readiness improvement."""
        recommendations = []
        
        if readiness_percentage < 80:
            recommendations.append("Focus on implementing remaining controls to achieve 80%+ readiness")
        
        if evidence_coverage < 90:
            recommendations.append("Collect additional evidence for controls lacking documentation")
        
        if gaps:
            recommendations.append(f"Address {len(gaps)} control gaps before audit fieldwork begins")
        
        if readiness_percentage >= 90 and evidence_coverage >= 90:
            recommendations.append("Excellent audit readiness - ready for fieldwork")
        
        return recommendations
    
    def _get_relevant_controls(self, audit_type: AuditType) -> List[ControlRequirement]:
        """Get controls relevant to the audit type."""
        if audit_type == AuditType.SOC2_TYPE_II:
            # Return SOC 2 controls (CC prefix)
            return [c for c in self.controls.values() if c.control_id.startswith('CC')]
        elif audit_type == AuditType.ISO_27001:
            # Return ISO 27001 controls (A. prefix)
            return [c for c in self.controls.values() if c.control_id.startswith('A.')]
        else:
            # Return all controls for other audit types
            return list(self.controls.values())
    
    def generate_compliance_dashboard(self) -> Dict[str, Any]:
        """Generate comprehensive compliance dashboard."""
        active_engagements = [e for e in self.engagements.values() 
                            if e.status not in [AuditStatus.COMPLETED]]
        
        total_controls = len(self.controls)
        implemented_controls = sum(1 for c in self.controls.values() 
                                 if c.status in [ControlStatus.IMPLEMENTED, ControlStatus.OPERATING_EFFECTIVELY])
        
        return {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'active_engagements': len(active_engagements),
            'signed_engagement_letters': sum(1 for e in active_engagements 
                                           if e.audit_firm.engagement_letter_signed),
            'overall_control_implementation': round((implemented_controls / total_controls * 100), 1) if total_controls > 0 else 0,
            'total_controls': total_controls,
            'implemented_controls': implemented_controls,
            'audit_firms_engaged': len(self.audit_firms),
            'evidence_items_collected': sum(len(e.evidence) for e in self.engagements.values()),
            'upcoming_audit_deadlines': [
                {
                    'engagement_id': e.engagement_id,
                    'audit_type': e.audit_type.value,
                    'target_completion': e.target_completion_date.isoformat(),
                    'days_remaining': (e.target_completion_date - datetime.now(timezone.utc)).days
                }
                for e in active_engagements
                if (e.target_completion_date - datetime.now(timezone.utc)).days <= 90
            ],
            'control_status_breakdown': {
                status.value: sum(1 for c in self.controls.values() if c.status == status)
                for status in ControlStatus
            },
            'audit_type_breakdown': {
                audit_type.value: sum(1 for e in self.engagements.values() if e.audit_type == audit_type)
                for audit_type in AuditType
            }
        }
    
    def _save_engagements(self):
        """Save audit engagements to storage."""
        try:
            data = {}
            for engagement_id, engagement in self.engagements.items():
                # Convert audit firm
                firm_dict = {
                    'firm_id': engagement.audit_firm.firm_id,
                    'firm_name': engagement.audit_firm.firm_name,
                    'contact_person': engagement.audit_firm.contact_person,
                    'email': engagement.audit_firm.email,
                    'phone': engagement.audit_firm.phone,
                    'certifications': engagement.audit_firm.certifications,
                    'specializations': [s.value for s in engagement.audit_firm.specializations],
                    'engagement_letter_signed': engagement.audit_firm.engagement_letter_signed
                }
                if engagement.audit_firm.engagement_date:
                    firm_dict['engagement_date'] = engagement.audit_firm.engagement_date.isoformat()
                
                # Convert controls
                controls_data = []
                for control in engagement.controls:
                    control_dict = {
                        'control_id': control.control_id,
                        'control_name': control.control_name,
                        'category': control.category.value,
                        'description': control.description,
                        'implementation_guidance': control.implementation_guidance,
                        'testing_procedures': control.testing_procedures,
                        'evidence_requirements': control.evidence_requirements,
                        'status': control.status.value,
                        'deficiencies': control.deficiencies,
                        'remediation_plan': control.remediation_plan
                    }
                    if control.implementation_date:
                        control_dict['implementation_date'] = control.implementation_date.isoformat()
                    if control.last_tested:
                        control_dict['last_tested'] = control.last_tested.isoformat()
                    controls_data.append(control_dict)
                
                # Convert evidence
                evidence_data = []
                for evidence in engagement.evidence:
                    evidence_dict = {
                        'evidence_id': evidence.evidence_id,
                        'control_id': evidence.control_id,
                        'evidence_type': evidence.evidence_type,
                        'description': evidence.description,
                        'file_path': evidence.file_path,
                        'collected_date': evidence.collected_date.isoformat(),
                        'collected_by': evidence.collected_by,
                        'hash_value': evidence.hash_value,
                        'metadata': evidence.metadata
                    }
                    evidence_data.append(evidence_dict)
                
                engagement_dict = {
                    'engagement_id': engagement.engagement_id,
                    'audit_type': engagement.audit_type.value,
                    'audit_firm': firm_dict,
                    'start_date': engagement.start_date.isoformat(),
                    'target_completion_date': engagement.target_completion_date.isoformat(),
                    'status': engagement.status.value,
                    'scope_description': engagement.scope_description,
                    'controls': controls_data,
                    'evidence': evidence_data,
                    'findings': engagement.findings,
                    'recommendations': engagement.recommendations,
                    'certification_achieved': engagement.certification_achieved
                }
                
                if engagement.completed_date:
                    engagement_dict['completed_date'] = engagement.completed_date.isoformat()
                if engagement.report_issued_date:
                    engagement_dict['report_issued_date'] = engagement.report_issued_date.isoformat()
                
                data[engagement_id] = engagement_dict
            
            with open(self.engagements_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save audit engagements: {e}")
    
    def _save_controls(self):
        """Save controls to storage."""
        try:
            data = {}
            for control_id, control in self.controls.items():
                control_dict = {
                    'control_id': control.control_id,
                    'control_name': control.control_name,
                    'category': control.category.value,
                    'description': control.description,
                    'implementation_guidance': control.implementation_guidance,
                    'testing_procedures': control.testing_procedures,
                    'evidence_requirements': control.evidence_requirements,
                    'status': control.status.value,
                    'deficiencies': control.deficiencies,
                    'remediation_plan': control.remediation_plan
                }
                if control.implementation_date:
                    control_dict['implementation_date'] = control.implementation_date.isoformat()
                if control.last_tested:
                    control_dict['last_tested'] = control.last_tested.isoformat()
                
                data[control_id] = control_dict
            
            with open(self.controls_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save controls: {e}")
    
    def _save_audit_firms(self):
        """Save audit firms to storage."""
        try:
            data = {}
            for firm_id, firm in self.audit_firms.items():
                firm_dict = {
                    'firm_id': firm.firm_id,
                    'firm_name': firm.firm_name,
                    'contact_person': firm.contact_person,
                    'email': firm.email,
                    'phone': firm.phone,
                    'certifications': firm.certifications,
                    'specializations': [s.value for s in firm.specializations],
                    'engagement_letter_signed': firm.engagement_letter_signed
                }
                if firm.engagement_date:
                    firm_dict['engagement_date'] = firm.engagement_date.isoformat()
                
                data[firm_id] = firm_dict
            
            with open(self.firms_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save audit firms: {e}")

def get_audit_manager() -> ThirdPartyAuditManager:
    """Get the global audit manager instance."""
    global _audit_manager
    if '_audit_manager' not in globals():
        _audit_manager = ThirdPartyAuditManager()
    return _audit_manager 