"""
🛡️ ENTERPRISE COMPLIANCE ROUTES
==============================
SOC 2 Type II / ISO 27001 Compliance API Endpoints
Unified Security & Compliance Management Interface
"""

from flask import Blueprint, request, jsonify, session
from datetime import datetime, timezone, timedelta
import logging

from ..auth.security import admin_required, api_key_required
from ..compliance.compliance_dashboard import get_compliance_dashboard
from ..compliance.data_protection import get_data_protection_manager, DataSubjectRights, LegalBasis, DataCategory
from ..compliance.incident_response import get_incident_response_manager, IncidentSeverity, IncidentCategory, IncidentStatus
from ..compliance.log_retention import get_log_retention_manager, DataClassification
from ..compliance.audit_framework import get_audit_manager, AuditType, AuditStatus
from ..auth.api_key_manager import get_api_key_manager, APIKeyScope
from ..auth.secrets_manager import get_secrets_manager
from ..utils.input_validation import validate_input, ValidationError

logger = logging.getLogger(__name__)

compliance_bp = Blueprint('compliance', __name__, url_prefix='/api/compliance')

# ============================================================================
# COMPLIANCE DASHBOARD ENDPOINTS
# ============================================================================

@compliance_bp.route('/dashboard', methods=['GET'])
@admin_required
def get_compliance_dashboard_status():
    """Get comprehensive compliance dashboard status."""
    try:
        dashboard = get_compliance_dashboard()
        status = dashboard.get_comprehensive_status()
        
        return jsonify({
            'success': True,
            'dashboard': status
        })
        
    except Exception as e:
        logger.error(f"Failed to get compliance dashboard: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve compliance dashboard'
        }), 500

# ============================================================================
# API KEY LIFECYCLE MANAGEMENT
# ============================================================================

@compliance_bp.route('/api-keys', methods=['GET'])
@admin_required
def list_api_keys():
    """List all API keys with compliance information."""
    try:
        api_key_manager = get_api_key_manager()
        keys = api_key_manager.list_api_keys()
        
        return jsonify({
            'success': True,
            'api_keys': keys,
            'total_keys': len(keys),
            'active_keys': len([k for k in keys if k['status'] == 'active'])
        })
        
    except Exception as e:
        logger.error(f"Failed to list API keys: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve API keys'
        }), 500

@compliance_bp.route('/api-keys/rotation-drill', methods=['POST'])
@admin_required
def run_api_key_rotation_drill():
    """Run quarterly API key rotation drill."""
    try:
        api_key_manager = get_api_key_manager()
        result = api_key_manager.run_quarterly_rotation_drill()
        
        return jsonify({
            'success': True,
            'drill_result': result
        })
        
    except Exception as e:
        logger.error(f"Failed to run rotation drill: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to run rotation drill'
        }), 500

@compliance_bp.route('/api-keys/<key_id>/rotate', methods=['POST'])
@admin_required
def rotate_api_key(key_id):
    """Rotate a specific API key."""
    try:
        api_key_manager = get_api_key_manager()
        
        # Validate input
        data = request.get_json() or {}
        grace_period_hours = validate_input(
            data.get('grace_period_hours', 24), 
            'grace_period_hours', 
            int, 
            min_value=1, 
            max_value=168
        )
        
        result = api_key_manager.rotate_api_key(key_id, grace_period_hours)
        
        if result:
            return jsonify({
                'success': True,
                'message': f'API key {key_id} rotation initiated'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to rotate API key'
            }), 400
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': f'Validation error: {e}'
        }), 400
    except Exception as e:
        logger.error(f"Failed to rotate API key: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to rotate API key'
        }), 500

# ============================================================================
# SECRETS MANAGEMENT
# ============================================================================

@compliance_bp.route('/secrets', methods=['GET'])
@admin_required
def list_secrets():
    """List all managed secrets with compliance information."""
    try:
        secrets_manager = get_secrets_manager()
        secrets = secrets_manager.list_secrets()
        
        return jsonify({
            'success': True,
            'secrets': secrets,
            'total_secrets': len(secrets)
        })
        
    except Exception as e:
        logger.error(f"Failed to list secrets: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve secrets'
        }), 500

@compliance_bp.route('/secrets/rotation-drill', methods=['POST'])
@admin_required
def run_secrets_rotation_drill():
    """Run quarterly secrets rotation drill."""
    try:
        secrets_manager = get_secrets_manager()
        result = secrets_manager.run_quarterly_rotation_drill()
        
        return jsonify({
            'success': True,
            'drill_result': result
        })
        
    except Exception as e:
        logger.error(f"Failed to run secrets rotation drill: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to run secrets rotation drill'
        }), 500

# ============================================================================
# DATA PROTECTION & GDPR/CCPA COMPLIANCE
# ============================================================================

@compliance_bp.route('/data-protection/ropa', methods=['GET'])
@admin_required
def get_records_of_processing():
    """Get Records of Processing Activities (RoPA) report."""
    try:
        data_protection_manager = get_data_protection_manager()
        ropa_report = data_protection_manager.generate_ropa_report()
        
        return jsonify({
            'success': True,
            'ropa_report': ropa_report
        })
        
    except Exception as e:
        logger.error(f"Failed to get RoPA report: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve RoPA report'
        }), 500

@compliance_bp.route('/data-protection/dpia/<activity_id>', methods=['POST'])
@admin_required
def conduct_dpia(activity_id):
    """Conduct Data Protection Impact Assessment."""
    try:
        data_protection_manager = get_data_protection_manager()
        dpia_result = data_protection_manager.conduct_dpia(activity_id)
        
        return jsonify({
            'success': True,
            'dpia_result': dpia_result
        })
        
    except Exception as e:
        logger.error(f"Failed to conduct DPIA: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to conduct DPIA'
        }), 500

@compliance_bp.route('/data-protection/subject-request', methods=['POST'])
@admin_required
def create_subject_request():
    """Create a data subject rights request."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request data required'
            }), 400
        
        # Validate input
        request_type = validate_input(data.get('request_type'), 'request_type', str, required=True)
        subject_email = validate_input(data.get('subject_email'), 'subject_email', str, required=True)
        subject_id = validate_input(data.get('subject_id'), 'subject_id', str, required=True)
        legal_basis = data.get('legal_basis', [])
        
        # Convert string to enum
        try:
            request_type_enum = DataSubjectRights(request_type)
            legal_basis_enums = [LegalBasis(basis) for basis in legal_basis]
        except ValueError as e:
            return jsonify({
                'success': False,
                'error': f'Invalid enum value: {e}'
            }), 400
        
        data_protection_manager = get_data_protection_manager()
        request_id = data_protection_manager.create_subject_request(
            request_type_enum, subject_email, subject_id, legal_basis_enums
        )
        
        if request_id:
            return jsonify({
                'success': True,
                'request_id': request_id
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to create subject request'
            }), 500
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': f'Validation error: {e}'
        }), 400
    except Exception as e:
        logger.error(f"Failed to create subject request: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to create subject request'
        }), 500

# ============================================================================
# INCIDENT RESPONSE MANAGEMENT
# ============================================================================

@compliance_bp.route('/incidents', methods=['GET'])
@admin_required
def list_incidents():
    """List all incidents with filtering options."""
    try:
        incident_manager = get_incident_response_manager()
        
        # Get query parameters
        days = request.args.get('days', 30, type=int)
        severity = request.args.get('severity')
        status = request.args.get('status')
        
        # Get SLA metrics for the period
        sla_metrics = incident_manager.get_sla_metrics(days)
        
        return jsonify({
            'success': True,
            'sla_metrics': sla_metrics
        })
        
    except Exception as e:
        logger.error(f"Failed to list incidents: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve incidents'
        }), 500

@compliance_bp.route('/incidents', methods=['POST'])
@admin_required
def create_incident():
    """Create a new incident."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Incident data required'
            }), 400
        
        # Validate input
        title = validate_input(data.get('title'), 'title', str, required=True, max_length=200)
        description = validate_input(data.get('description'), 'description', str, required=True, max_length=2000)
        severity = validate_input(data.get('severity'), 'severity', str, required=True)
        category = validate_input(data.get('category'), 'category', str, required=True)
        affected_services = data.get('affected_services', [])
        affected_customers = validate_input(data.get('affected_customers', 0), 'affected_customers', int, min_value=0)
        
        # Convert strings to enums
        try:
            severity_enum = IncidentSeverity(severity)
            category_enum = IncidentCategory(category)
        except ValueError as e:
            return jsonify({
                'success': False,
                'error': f'Invalid enum value: {e}'
            }), 400
        
        incident_manager = get_incident_response_manager()
        incident_id = incident_manager.create_incident(
            title, description, severity_enum, category_enum, affected_services, affected_customers
        )
        
        if incident_id:
            return jsonify({
                'success': True,
                'incident_id': incident_id
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to create incident'
            }), 500
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': f'Validation error: {e}'
        }), 400
    except Exception as e:
        logger.error(f"Failed to create incident: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to create incident'
        }), 500

@compliance_bp.route('/incidents/<incident_id>/status', methods=['PUT'])
@admin_required
def update_incident_status(incident_id):
    """Update incident status."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Status update data required'
            }), 400
        
        # Validate input
        status = validate_input(data.get('status'), 'status', str, required=True)
        update_message = validate_input(data.get('update_message'), 'update_message', str, required=True, max_length=1000)
        updated_by = validate_input(data.get('updated_by', 'admin'), 'updated_by', str, max_length=100)
        
        # Convert string to enum
        try:
            status_enum = IncidentStatus(status)
        except ValueError as e:
            return jsonify({
                'success': False,
                'error': f'Invalid status: {e}'
            }), 400
        
        incident_manager = get_incident_response_manager()
        success = incident_manager.update_incident_status(incident_id, status_enum, update_message, updated_by)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Incident {incident_id} status updated'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update incident status'
            }), 400
            
    except ValidationError as e:
        return jsonify({
            'success': False,
            'error': f'Validation error: {e}'
        }), 400
    except Exception as e:
        logger.error(f"Failed to update incident status: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to update incident status'
        }), 500

# ============================================================================
# LOG RETENTION & DELETION
# ============================================================================

@compliance_bp.route('/log-retention/status', methods=['GET'])
@admin_required
def get_log_retention_status():
    """Get log retention and deletion status."""
    try:
        log_retention_manager = get_log_retention_manager()
        status = log_retention_manager.get_retention_status()
        
        return jsonify({
            'success': True,
            'retention_status': status
        })
        
    except Exception as e:
        logger.error(f"Failed to get log retention status: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve log retention status'
        }), 500

@compliance_bp.route('/log-retention/process', methods=['POST'])
@admin_required
def process_retention_actions():
    """Process log retention actions (purging, archiving)."""
    try:
        log_retention_manager = get_log_retention_manager()
        result = log_retention_manager.process_retention_actions()
        
        return jsonify({
            'success': True,
            'retention_result': result
        })
        
    except Exception as e:
        logger.error(f"Failed to process retention actions: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to process retention actions'
        }), 500

@compliance_bp.route('/log-retention/verify-encryption', methods=['POST'])
@admin_required
def verify_backup_encryption():
    """Verify backup encryption status."""
    try:
        log_retention_manager = get_log_retention_manager()
        result = log_retention_manager.verify_backup_encryption()
        
        return jsonify({
            'success': True,
            'encryption_verification': result
        })
        
    except Exception as e:
        logger.error(f"Failed to verify backup encryption: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to verify backup encryption'
        }), 500

# ============================================================================
# THIRD-PARTY AUDIT MANAGEMENT
# ============================================================================

@compliance_bp.route('/audits', methods=['GET'])
@admin_required
def list_audit_engagements():
    """List all audit engagements."""
    try:
        audit_manager = get_audit_manager()
        dashboard = audit_manager.generate_compliance_dashboard()
        
        return jsonify({
            'success': True,
            'audit_dashboard': dashboard
        })
        
    except Exception as e:
        logger.error(f"Failed to list audit engagements: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve audit engagements'
        }), 500

@compliance_bp.route('/audits/<engagement_id>/readiness', methods=['GET'])
@admin_required
def get_audit_readiness(engagement_id):
    """Get audit readiness assessment for an engagement."""
    try:
        audit_manager = get_audit_manager()
        readiness_report = audit_manager.generate_audit_readiness_report(engagement_id)
        
        return jsonify({
            'success': True,
            'readiness_report': readiness_report
        })
        
    except Exception as e:
        logger.error(f"Failed to get audit readiness: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve audit readiness'
        }), 500

# ============================================================================
# COMPLIANCE REPORTING
# ============================================================================

@compliance_bp.route('/reports/executive-summary', methods=['GET'])
@admin_required
def get_executive_summary():
    """Get executive compliance summary report."""
    try:
        dashboard = get_compliance_dashboard()
        status = dashboard.get_comprehensive_status()
        
        # Extract executive summary
        executive_summary = {
            'generated_at': status['generated_at'],
            'overall_compliance_score': status['overall_compliance_score'],
            'overall_status': status['overall_status'],
            'critical_issues_count': status['critical_issues_count'],
            'compliance_summary': status['compliance_summary'],
            'next_actions': status['next_actions'][:3],  # Top 3 actions
            'component_scores': {
                component: data['compliance_score']
                for component, data in status['components'].items()
            }
        }
        
        return jsonify({
            'success': True,
            'executive_summary': executive_summary
        })
        
    except Exception as e:
        logger.error(f"Failed to get executive summary: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate executive summary'
        }), 500

@compliance_bp.route('/reports/detailed', methods=['GET'])
@admin_required
def get_detailed_compliance_report():
    """Get detailed compliance report with all components."""
    try:
        dashboard = get_compliance_dashboard()
        status = dashboard.get_comprehensive_status()
        
        return jsonify({
            'success': True,
            'detailed_report': status
        })
        
    except Exception as e:
        logger.error(f"Failed to get detailed compliance report: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate detailed compliance report'
        }), 500

# ============================================================================
# HEALTH CHECK
# ============================================================================

@compliance_bp.route('/health', methods=['GET'])
def compliance_health_check():
    """Health check for compliance system."""
    try:
        # Test each component
        components_status = {}
        
        try:
            get_api_key_manager()
            components_status['api_key_manager'] = 'operational'
        except Exception:
            components_status['api_key_manager'] = 'error'
        
        try:
            get_secrets_manager()
            components_status['secrets_manager'] = 'operational'
        except Exception:
            components_status['secrets_manager'] = 'error'
        
        try:
            get_data_protection_manager()
            components_status['data_protection_manager'] = 'operational'
        except Exception:
            components_status['data_protection_manager'] = 'error'
        
        try:
            get_incident_response_manager()
            components_status['incident_response_manager'] = 'operational'
        except Exception:
            components_status['incident_response_manager'] = 'error'
        
        try:
            get_log_retention_manager()
            components_status['log_retention_manager'] = 'operational'
        except Exception:
            components_status['log_retention_manager'] = 'error'
        
        try:
            get_audit_manager()
            components_status['audit_manager'] = 'operational'
        except Exception:
            components_status['audit_manager'] = 'error'
        
        all_operational = all(status == 'operational' for status in components_status.values())
        
        return jsonify({
            'status': 'ok' if all_operational else 'degraded',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'components': components_status,
            'version': '1.0.0'
        })
        
    except Exception as e:
        logger.error(f"Compliance health check failed: {e}")
        return jsonify({
            'status': 'error',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': 'Health check failed'
        }), 500 