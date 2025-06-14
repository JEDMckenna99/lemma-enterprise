"""
📊 ENTERPRISE COMPLIANCE DASHBOARD
=================================
Unified Security & Compliance Management Interface
SOC 2 Type II / ISO 27001 Compliance Monitoring
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import logging

# Import all compliance components
from .data_protection import get_data_protection_manager, DataSubjectRights, ProcessingPurpose
from .incident_response import get_incident_response_manager, IncidentSeverity, IncidentStatus
from .log_retention import get_log_retention_manager, DataClassification
from .audit_framework import get_audit_manager, AuditType, AuditStatus, ControlStatus
from ..auth.api_key_manager import get_api_key_manager, APIKeyScope, APIKeyStatus
from ..auth.secrets_manager import get_secrets_manager

logger = logging.getLogger(__name__)

class ComplianceStatus:
    """Overall compliance status indicators"""
    COMPLIANT = "compliant"
    NEEDS_ATTENTION = "needs_attention"
    NON_COMPLIANT = "non_compliant"
    IN_PROGRESS = "in_progress"

class ComplianceDashboard:
    """
    Enterprise Compliance Dashboard
    
    Provides unified view of:
    - API Key Lifecycle Management
    - Secrets Management Status
    - Data Protection Impact Assessment
    - Log Retention & Deletion Compliance
    - Incident Response Readiness
    - Third-Party Audit Progress
    - Overall Compliance Score
    """
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.environ.get('STORAGE_DIR', '.lemma_enterprise')
        
        # Initialize all compliance managers
        self.api_key_manager = get_api_key_manager()
        self.secrets_manager = get_secrets_manager()
        self.data_protection_manager = get_data_protection_manager()
        self.incident_manager = get_incident_response_manager()
        self.log_retention_manager = get_log_retention_manager()
        self.audit_manager = get_audit_manager()
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive compliance status across all areas."""
        try:
            # Get status from each component
            api_key_status = self._get_api_key_compliance()
            secrets_status = self._get_secrets_compliance()
            data_protection_status = self._get_data_protection_compliance()
            incident_response_status = self._get_incident_response_compliance()
            log_retention_status = self._get_log_retention_compliance()
            audit_status = self._get_audit_compliance()
            
            # Calculate overall compliance score
            component_scores = [
                api_key_status['compliance_score'],
                secrets_status['compliance_score'],
                data_protection_status['compliance_score'],
                incident_response_status['compliance_score'],
                log_retention_status['compliance_score'],
                audit_status['compliance_score']
            ]
            
            overall_score = sum(component_scores) / len(component_scores)
            overall_status = self._determine_overall_status(overall_score)
            
            # Identify critical issues
            critical_issues = []
            critical_issues.extend(api_key_status.get('critical_issues', []))
            critical_issues.extend(secrets_status.get('critical_issues', []))
            critical_issues.extend(data_protection_status.get('critical_issues', []))
            critical_issues.extend(incident_response_status.get('critical_issues', []))
            critical_issues.extend(log_retention_status.get('critical_issues', []))
            critical_issues.extend(audit_status.get('critical_issues', []))
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                overall_score, component_scores, critical_issues
            )
            
            return {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'overall_compliance_score': round(overall_score, 1),
                'overall_status': overall_status,
                'critical_issues_count': len(critical_issues),
                'components': {
                    'api_key_lifecycle': api_key_status,
                    'secrets_management': secrets_status,
                    'data_protection': data_protection_status,
                    'incident_response': incident_response_status,
                    'log_retention': log_retention_status,
                    'third_party_audit': audit_status
                },
                'critical_issues': critical_issues,
                'recommendations': recommendations,
                'compliance_summary': self._generate_compliance_summary(overall_score, component_scores),
                'next_actions': self._get_next_actions(critical_issues, component_scores)
            }
            
        except Exception as e:
            logger.error(f"Failed to get comprehensive compliance status: {e}")
            return {
                'error': 'Failed to generate compliance status',
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
    
    def _get_api_key_compliance(self) -> Dict[str, Any]:
        """Assess API key lifecycle management compliance."""
        try:
            # Get API key statistics
            all_keys = self.api_key_manager.list_api_keys()
            active_keys = [k for k in all_keys if k['status'] == APIKeyStatus.ACTIVE.value]
            expired_keys = [k for k in all_keys if k['status'] == APIKeyStatus.EXPIRED.value]
            
            # Check for compliance issues
            critical_issues = []
            compliance_score = 100
            
            # Check for keys without scopes (should have least-privilege)
            keys_without_scopes = [k for k in active_keys if not k.get('scopes')]
            if keys_without_scopes:
                critical_issues.append(f"{len(keys_without_scopes)} API keys lack least-privilege scopes")
                compliance_score -= 20
            
            # Check for keys nearing expiration
            thirty_days = datetime.now(timezone.utc) + timedelta(days=30)
            expiring_soon = [k for k in active_keys 
                           if k.get('expires_at') and datetime.fromisoformat(k['expires_at']) < thirty_days]
            if expiring_soon:
                critical_issues.append(f"{len(expiring_soon)} API keys expire within 30 days")
                compliance_score -= 10
            
            # Check rotation drill status
            last_drill = self.api_key_manager.get_last_rotation_drill_date()
            if not last_drill or (datetime.now(timezone.utc) - last_drill).days > 90:
                critical_issues.append("Quarterly rotation drill overdue")
                compliance_score -= 15
            
            return {
                'compliance_score': max(compliance_score, 0),
                'status': ComplianceStatus.COMPLIANT if compliance_score >= 80 else ComplianceStatus.NEEDS_ATTENTION,
                'total_keys': len(all_keys),
                'active_keys': len(active_keys),
                'expired_keys': len(expired_keys),
                'keys_with_scopes': len(active_keys) - len(keys_without_scopes),
                'keys_expiring_soon': len(expiring_soon),
                'last_rotation_drill': last_drill.isoformat() if last_drill else None,
                'critical_issues': critical_issues
            }
            
        except Exception as e:
            logger.error(f"Failed to assess API key compliance: {e}")
            return {
                'compliance_score': 0,
                'status': ComplianceStatus.NON_COMPLIANT,
                'critical_issues': ['API key compliance assessment failed']
            }
    
    def _get_secrets_compliance(self) -> Dict[str, Any]:
        """Assess secrets management compliance."""
        try:
            # Get secrets statistics
            secrets_list = self.secrets_manager.list_secrets()
            
            critical_issues = []
            compliance_score = 100
            
            # Check for secrets without rotation schedules
            secrets_without_rotation = [s for s in secrets_list if not s.get('rotation_schedule')]
            if secrets_without_rotation:
                critical_issues.append(f"{len(secrets_without_rotation)} secrets lack rotation schedules")
                compliance_score -= 25
            
            # Check for overdue rotations
            overdue_rotations = []
            for secret in secrets_list:
                if secret.get('rotation_schedule') and secret.get('last_rotated'):
                    last_rotated = datetime.fromisoformat(secret['last_rotated'])
                    rotation_days = secret['rotation_schedule']
                    if (datetime.now(timezone.utc) - last_rotated).days > rotation_days:
                        overdue_rotations.append(secret)
            
            if overdue_rotations:
                critical_issues.append(f"{len(overdue_rotations)} secrets have overdue rotations")
                compliance_score -= 30
            
            # Check quarterly drill status
            drill_result = self.secrets_manager.run_quarterly_rotation_drill()
            if not drill_result.get('success', False):
                critical_issues.append("Quarterly rotation drill failed")
                compliance_score -= 20
            
            return {
                'compliance_score': max(compliance_score, 0),
                'status': ComplianceStatus.COMPLIANT if compliance_score >= 80 else ComplianceStatus.NEEDS_ATTENTION,
                'total_secrets': len(secrets_list),
                'secrets_with_rotation': len(secrets_list) - len(secrets_without_rotation),
                'overdue_rotations': len(overdue_rotations),
                'last_drill_success': drill_result.get('success', False),
                'critical_issues': critical_issues
            }
            
        except Exception as e:
            logger.error(f"Failed to assess secrets compliance: {e}")
            return {
                'compliance_score': 0,
                'status': ComplianceStatus.NON_COMPLIANT,
                'critical_issues': ['Secrets management compliance assessment failed']
            }
    
    def _get_data_protection_compliance(self) -> Dict[str, Any]:
        """Assess data protection and GDPR/CCPA compliance."""
        try:
            # Get RoPA report
            ropa_report = self.data_protection_manager.generate_ropa_report()
            
            critical_issues = []
            compliance_score = 100
            
            # Check DPIA completion
            activities_requiring_dpia = ropa_report.get('activities_requiring_dpia', 0)
            completed_dpias = ropa_report.get('completed_dpias', 0)
            if activities_requiring_dpia > completed_dpias:
                missing_dpias = activities_requiring_dpia - completed_dpias
                critical_issues.append(f"{missing_dpias} Data Protection Impact Assessments incomplete")
                compliance_score -= 30
            
            # Check processor agreements
            total_processors = ropa_report.get('total_processors', 0)
            processors_with_dpa = ropa_report.get('processors_with_dpa', 0)
            if total_processors > processors_with_dpa:
                missing_dpas = total_processors - processors_with_dpa
                critical_issues.append(f"{missing_dpas} data processors lack signed DPAs")
                compliance_score -= 25
            
            # Check pending subject requests
            pending_requests = ropa_report.get('pending_subject_requests', 0)
            if pending_requests > 0:
                critical_issues.append(f"{pending_requests} data subject requests pending")
                compliance_score -= 15
            
            return {
                'compliance_score': max(compliance_score, 0),
                'status': ComplianceStatus.COMPLIANT if compliance_score >= 80 else ComplianceStatus.NEEDS_ATTENTION,
                'total_processing_activities': ropa_report.get('total_activities', 0),
                'completed_dpias': completed_dpias,
                'required_dpias': activities_requiring_dpia,
                'processors_with_agreements': processors_with_dpa,
                'total_processors': total_processors,
                'pending_subject_requests': pending_requests,
                'critical_issues': critical_issues
            }
            
        except Exception as e:
            logger.error(f"Failed to assess data protection compliance: {e}")
            return {
                'compliance_score': 0,
                'status': ComplianceStatus.NON_COMPLIANT,
                'critical_issues': ['Data protection compliance assessment failed']
            }
    
    def _get_incident_response_compliance(self) -> Dict[str, Any]:
        """Assess incident response readiness."""
        try:
            # Get SLA metrics
            sla_metrics = self.incident_manager.get_sla_metrics(30)
            
            critical_issues = []
            compliance_score = 100
            
            # Check if there are any incidents
            if 'error' in sla_metrics:
                # No incidents is actually good for compliance
                return {
                    'compliance_score': 100,
                    'status': ComplianceStatus.COMPLIANT,
                    'total_incidents_30_days': 0,
                    'average_resolution_time': None,
                    'sla_compliance': {},
                    'on_call_configured': len(self.incident_manager.oncall_engineers) > 0,
                    'escalation_policies_configured': len(self.incident_manager.escalation_policies) > 0,
                    'critical_issues': []
                }
            
            # Check SLA compliance
            sla_compliance = sla_metrics.get('sla_compliance_percentage', {})
            for severity, compliance_pct in sla_compliance.items():
                if compliance_pct < 80:
                    critical_issues.append(f"{severity} incident SLA compliance below 80% ({compliance_pct:.1f}%)")
                    compliance_score -= 15
            
            # Check on-call configuration
            if not self.incident_manager.oncall_engineers:
                critical_issues.append("No on-call engineers configured")
                compliance_score -= 30
            
            # Check escalation policies
            if not self.incident_manager.escalation_policies:
                critical_issues.append("No escalation policies configured")
                compliance_score -= 25
            
            return {
                'compliance_score': max(compliance_score, 0),
                'status': ComplianceStatus.COMPLIANT if compliance_score >= 80 else ComplianceStatus.NEEDS_ATTENTION,
                'total_incidents_30_days': sla_metrics.get('total_incidents', 0),
                'resolved_incidents': sla_metrics.get('resolved_incidents', 0),
                'average_resolution_time': sla_metrics.get('average_resolution_time_minutes'),
                'sla_compliance': sla_compliance,
                'on_call_configured': len(self.incident_manager.oncall_engineers),
                'escalation_policies_configured': len(self.incident_manager.escalation_policies),
                'critical_issues': critical_issues
            }
            
        except Exception as e:
            logger.error(f"Failed to assess incident response compliance: {e}")
            return {
                'compliance_score': 0,
                'status': ComplianceStatus.NON_COMPLIANT,
                'critical_issues': ['Incident response compliance assessment failed']
            }
    
    def _get_log_retention_compliance(self) -> Dict[str, Any]:
        """Assess log retention and deletion compliance."""
        try:
            # Get retention status
            retention_status = self.log_retention_manager.get_retention_status()
            
            critical_issues = []
            compliance_score = 100
            
            # Check for overdue purges
            overdue_purges = retention_status.get('files_overdue_for_purge', 0)
            if overdue_purges > 0:
                critical_issues.append(f"{overdue_purges} log files overdue for purging")
                compliance_score -= 25
            
            # Check backup encryption
            encryption_status = self.log_retention_manager.verify_backup_encryption()
            failed_encryption = encryption_status.get('failed_verifications', 0)
            if failed_encryption > 0:
                critical_issues.append(f"{failed_encryption} backup files failed encryption verification")
                compliance_score -= 30
            
            # Check for files exceeding 31-day retention
            files_over_31_days = retention_status.get('files_exceeding_gdpr_limit', 0)
            if files_over_31_days > 0:
                critical_issues.append(f"{files_over_31_days} files exceed 31-day GDPR retention limit")
                compliance_score -= 35
            
            return {
                'compliance_score': max(compliance_score, 0),
                'status': ComplianceStatus.COMPLIANT if compliance_score >= 80 else ComplianceStatus.NEEDS_ATTENTION,
                'total_log_files': retention_status.get('total_files', 0),
                'files_within_retention': retention_status.get('files_within_retention', 0),
                'files_overdue_purge': overdue_purges,
                'encrypted_backups': retention_status.get('encrypted_files', 0),
                'backup_encryption_verified': encryption_status.get('successful_verifications', 0),
                'critical_issues': critical_issues
            }
            
        except Exception as e:
            logger.error(f"Failed to assess log retention compliance: {e}")
            return {
                'compliance_score': 0,
                'status': ComplianceStatus.NON_COMPLIANT,
                'critical_issues': ['Log retention compliance assessment failed']
            }
    
    def _get_audit_compliance(self) -> Dict[str, Any]:
        """Assess third-party audit readiness."""
        try:
            # Get compliance dashboard from audit manager
            audit_dashboard = self.audit_manager.generate_compliance_dashboard()
            
            critical_issues = []
            compliance_score = 100
            
            # Check for signed engagement letters
            active_engagements = audit_dashboard.get('active_engagements', 0)
            signed_letters = audit_dashboard.get('signed_engagement_letters', 0)
            if active_engagements > signed_letters:
                unsigned = active_engagements - signed_letters
                critical_issues.append(f"{unsigned} audit engagements lack signed letters")
                compliance_score -= 30
            
            # Check control implementation
            control_implementation = audit_dashboard.get('overall_control_implementation', 0)
            if control_implementation < 80:
                critical_issues.append(f"Control implementation below 80% ({control_implementation:.1f}%)")
                compliance_score -= 25
            
            # Check upcoming deadlines
            upcoming_deadlines = audit_dashboard.get('upcoming_audit_deadlines', [])
            overdue_audits = [d for d in upcoming_deadlines if d['days_remaining'] < 0]
            if overdue_audits:
                critical_issues.append(f"{len(overdue_audits)} audit deadlines overdue")
                compliance_score -= 40
            
            return {
                'compliance_score': max(compliance_score, 0),
                'status': ComplianceStatus.COMPLIANT if compliance_score >= 80 else ComplianceStatus.NEEDS_ATTENTION,
                'active_engagements': active_engagements,
                'signed_engagement_letters': signed_letters,
                'control_implementation_percentage': control_implementation,
                'total_controls': audit_dashboard.get('total_controls', 0),
                'implemented_controls': audit_dashboard.get('implemented_controls', 0),
                'evidence_items': audit_dashboard.get('evidence_items_collected', 0),
                'upcoming_deadlines': len(upcoming_deadlines),
                'critical_issues': critical_issues
            }
            
        except Exception as e:
            logger.error(f"Failed to assess audit compliance: {e}")
            return {
                'compliance_score': 0,
                'status': ComplianceStatus.NON_COMPLIANT,
                'critical_issues': ['Third-party audit compliance assessment failed']
            }
    
    def _determine_overall_status(self, score: float) -> str:
        """Determine overall compliance status based on score."""
        if score >= 90:
            return ComplianceStatus.COMPLIANT
        elif score >= 70:
            return ComplianceStatus.NEEDS_ATTENTION
        else:
            return ComplianceStatus.NON_COMPLIANT
    
    def _generate_recommendations(self, overall_score: float, component_scores: List[float], 
                                critical_issues: List[str]) -> List[str]:
        """Generate actionable recommendations for compliance improvement."""
        recommendations = []
        
        if overall_score < 80:
            recommendations.append("Overall compliance score below 80% - immediate attention required")
        
        # Component-specific recommendations
        component_names = [
            "API Key Lifecycle", "Secrets Management", "Data Protection",
            "Incident Response", "Log Retention", "Third-Party Audit"
        ]
        
        for i, score in enumerate(component_scores):
            if score < 70:
                recommendations.append(f"Focus on {component_names[i]} - score critically low ({score:.1f}%)")
        
        if len(critical_issues) > 5:
            recommendations.append("High number of critical issues - prioritize immediate remediation")
        
        if overall_score >= 90:
            recommendations.append("Excellent compliance posture - maintain current practices")
        
        return recommendations
    
    def _generate_compliance_summary(self, overall_score: float, component_scores: List[float]) -> Dict[str, Any]:
        """Generate executive summary of compliance status."""
        component_names = [
            "API Key Lifecycle", "Secrets Management", "Data Protection",
            "Incident Response", "Log Retention", "Third-Party Audit"
        ]
        
        strongest_area = component_names[component_scores.index(max(component_scores))]
        weakest_area = component_names[component_scores.index(min(component_scores))]
        
        return {
            'overall_grade': 'A' if overall_score >= 90 else 'B' if overall_score >= 80 else 'C' if overall_score >= 70 else 'D',
            'strongest_compliance_area': strongest_area,
            'weakest_compliance_area': weakest_area,
            'areas_above_80_percent': sum(1 for score in component_scores if score >= 80),
            'areas_needing_improvement': sum(1 for score in component_scores if score < 80),
            'ready_for_audit': overall_score >= 85,
            'executive_summary': self._get_executive_summary(overall_score, strongest_area, weakest_area)
        }
    
    def _get_executive_summary(self, score: float, strongest: str, weakest: str) -> str:
        """Generate executive summary text."""
        if score >= 90:
            return f"Excellent compliance posture across all areas. {strongest} is particularly strong. Ready for audit."
        elif score >= 80:
            return f"Good compliance posture with some areas for improvement. Focus on {weakest} to achieve audit readiness."
        elif score >= 70:
            return f"Moderate compliance posture requiring attention. {weakest} needs immediate improvement before audit."
        else:
            return f"Compliance posture requires significant improvement. Critical focus needed on {weakest} and overall remediation."
    
    def _get_next_actions(self, critical_issues: List[str], component_scores: List[float]) -> List[Dict[str, Any]]:
        """Get prioritized next actions for compliance improvement."""
        actions = []
        
        # High priority actions based on critical issues
        for issue in critical_issues[:3]:  # Top 3 critical issues
            actions.append({
                'priority': 'HIGH',
                'action': f"Resolve: {issue}",
                'category': 'Critical Issue',
                'estimated_effort': 'Medium'
            })
        
        # Component improvement actions
        component_names = [
            "API Key Lifecycle", "Secrets Management", "Data Protection",
            "Incident Response", "Log Retention", "Third-Party Audit"
        ]
        
        for i, score in enumerate(component_scores):
            if score < 80:
                actions.append({
                    'priority': 'MEDIUM',
                    'action': f"Improve {component_names[i]} compliance",
                    'category': 'Component Improvement',
                    'estimated_effort': 'High' if score < 60 else 'Medium'
                })
        
        return actions[:5]  # Return top 5 actions

def get_compliance_dashboard() -> ComplianceDashboard:
    """Get the global compliance dashboard instance."""
    global _compliance_dashboard
    if '_compliance_dashboard' not in globals():
        _compliance_dashboard = ComplianceDashboard()
    return _compliance_dashboard 