"""
Audit Log API Endpoints
Provides access to audit logs for compliance and security monitoring
"""

from flask import Blueprint, request, jsonify, Response
from flask_cors import cross_origin
from datetime import datetime, timedelta
import logging

from auth.decorators import require_api_key, require_site_admin
from .audit_logger import (
    get_audit_logs,
    export_audit_logs,
    log_event,
    AuditEvent
)

logger = logging.getLogger(__name__)

audit_api = Blueprint('audit_api', __name__)


@audit_api.route('/api/v1/audit/logs', methods=['GET'])
@cross_origin()
@require_site_admin
def query_audit_logs():
    """
    Query audit logs with filters
    
    GET /api/v1/audit/logs?site_id=site_123&start_date=2025-01-01&limit=100
    
    Query Parameters:
        site_id: Filter by site (required)
        user_email: Filter by user email
        event_type: Filter by event type (comma-separated for multiple)
        start_date: Start date (ISO format: 2025-01-01)
        end_date: End date (ISO format: 2025-01-31)
        result: Filter by result (success, failure, warning)
        limit: Max results (default: 100, max: 1000)
        offset: Pagination offset (default: 0)
    """
    try:
        # Get query parameters
        site_id = request.args.get('site_id')
        if not site_id:
            return jsonify({'error': 'site_id is required'}), 400
        
        user_email = request.args.get('user_email')
        event_types_param = request.args.get('event_type')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        result = request.args.get('result')
        limit = min(int(request.args.get('limit', 100)), 1000)
        offset = int(request.args.get('offset', 0))
        
        # Parse event types
        event_types = None
        if event_types_param:
            event_types = [et.strip() for et in event_types_param.split(',')]
        
        # Parse dates
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str)
            except ValueError:
                return jsonify({'error': 'Invalid start_date format. Use ISO format: 2025-01-01'}), 400
        
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str)
            except ValueError:
                return jsonify({'error': 'Invalid end_date format. Use ISO format: 2025-01-31'}), 400
        
        # Query logs
        logs = get_audit_logs(
            site_id=site_id,
            user_email=user_email,
            event_types=event_types,
            start_date=start_date,
            end_date=end_date,
            result=result,
            limit=limit,
            offset=offset
        )
        
        # Log this export for audit trail
        log_event(
            AuditEvent.AUDIT_LOG_EXPORTED,
            site_id=site_id,
            result='success',
            metadata={
                'query': {
                    'user_email': user_email,
                    'event_types': event_types,
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'result_filter': result
                },
                'results_count': len(logs)
            }
        )
        
        return jsonify({
            'success': True,
            'logs': logs,
            'count': len(logs),
            'limit': limit,
            'offset': offset,
            'has_more': len(logs) == limit
        }), 200
        
    except Exception as e:
        logger.error(f"Audit log query error: {e}")
        return jsonify({'error': str(e)}), 500


@audit_api.route('/api/v1/audit/export', methods=['GET'])
@cross_origin()
@require_site_admin
def export_audit_logs_endpoint():
    """
    Export audit logs for compliance
    
    GET /api/v1/audit/export?site_id=site_123&format=csv&start_date=2025-01-01
    
    Query Parameters:
        site_id: Site to export logs for (required)
        format: 'csv' or 'json' (default: csv)
        start_date: Start date (optional)
        end_date: End date (optional)
    """
    try:
        # Get parameters
        site_id = request.args.get('site_id')
        if not site_id:
            return jsonify({'error': 'site_id is required'}), 400
        
        format_type = request.args.get('format', 'csv').lower()
        if format_type not in ['csv', 'json']:
            return jsonify({'error': 'format must be csv or json'}), 400
        
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        # Parse dates
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str)
            except ValueError:
                return jsonify({'error': 'Invalid start_date format'}), 400
        
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str)
            except ValueError:
                return jsonify({'error': 'Invalid end_date format'}), 400
        
        # Export logs
        export_data = export_audit_logs(
            site_id=site_id,
            format=format_type,
            start_date=start_date,
            end_date=end_date
        )
        
        # Log this export
        log_event(
            AuditEvent.AUDIT_LOG_EXPORTED,
            site_id=site_id,
            result='success',
            metadata={
                'format': format_type,
                'start_date': start_date_str,
                'end_date': end_date_str,
                'size_bytes': len(export_data)
            }
        )
        
        # Return as downloadable file
        if format_type == 'csv':
            return Response(
                export_data,
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename=audit_logs_{site_id}_{datetime.now().strftime("%Y%m%d")}.csv'
                }
            )
        else:  # json
            return Response(
                export_data,
                mimetype='application/json',
                headers={
                    'Content-Disposition': f'attachment; filename=audit_logs_{site_id}_{datetime.now().strftime("%Y%m%d")}.json'
                }
            )
        
    except Exception as e:
        logger.error(f"Audit log export error: {e}")
        return jsonify({'error': str(e)}), 500


@audit_api.route('/api/v1/audit/stats', methods=['GET'])
@cross_origin()
@require_site_admin
def audit_stats():
    """
    Get audit log statistics for a site
    
    GET /api/v1/audit/stats?site_id=site_123&days=30
    
    Returns summary statistics for last N days
    """
    try:
        site_id = request.args.get('site_id')
        if not site_id:
            return jsonify({'error': 'site_id is required'}), 400
        
        days = int(request.args.get('days', 30))
        start_date = datetime.now() - timedelta(days=days)
        
        # Get all logs for the period
        logs = get_audit_logs(
            site_id=site_id,
            start_date=start_date,
            limit=100000
        )
        
        # Calculate statistics
        stats = {
            'total_events': len(logs),
            'period_days': days,
            'by_event_type': {},
            'by_result': {
                'success': 0,
                'failure': 0,
                'warning': 0
            },
            'unique_users': set(),
            'security_events': 0
        }
        
        for log in logs:
            # Count by event type
            event_type = log['event_type']
            stats['by_event_type'][event_type] = stats['by_event_type'].get(event_type, 0) + 1
            
            # Count by result
            result = log['result']
            stats['by_result'][result] += 1
            
            # Track unique users
            if log['user_email']:
                stats['unique_users'].add(log['user_email'])
            
            # Count security events
            if event_type in [
                AuditEvent.NONCE_REPLAY_DETECTED,
                AuditEvent.ACCESS_DENIED,
                AuditEvent.RATE_LIMIT_EXCEEDED,
                AuditEvent.SUSPICIOUS_ACTIVITY,
                AuditEvent.IP_BLOCKED
            ]:
                stats['security_events'] += 1
        
        # Convert set to count
        stats['unique_users'] = len(stats['unique_users'])
        
        return jsonify({
            'success': True,
            'site_id': site_id,
            'stats': stats
        }), 200
        
    except Exception as e:
        logger.error(f"Audit stats error: {e}")
        return jsonify({'error': str(e)}), 500

