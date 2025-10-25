"""
Audit Logging System for Lemma IAM
Comprehensive logging of all security-relevant events for compliance
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import request, g
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# Import database engine
try:
    from api.database import engine
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    logger.warning("⚠️ Database not available - audit logging disabled")


class AuditEvent:
    """Enumeration of audit event types"""
    
    # Authentication events
    EMAIL_CONFIRMATION_SENT = 'email_confirmation_sent'
    EMAIL_CONFIRMATION_CLICKED = 'email_confirmation_clicked'
    LOGIN_SUCCESS = 'login_success'
    LOGIN_FAILURE = 'login_failure'
    LOGOUT = 'logout'
    
    # Permission events
    PERMISSION_CREATED = 'permission_created'
    PERMISSION_GRANTED = 'permission_granted'
    PERMISSION_REVOKED = 'permission_revoked'
    PERMISSION_UPDATED = 'permission_updated'
    
    # Access control events
    ACCESS_GRANTED = 'access_granted'
    ACCESS_DENIED = 'access_denied'
    NONCE_REPLAY_DETECTED = 'nonce_replay_detected'
    
    # Credential events
    CREDENTIAL_ISSUED = 'credential_issued'
    CREDENTIAL_VERIFIED = 'credential_verified'
    CREDENTIAL_EXPIRED = 'credential_expired'
    CREDENTIAL_REVOKED = 'credential_revoked'
    
    # Site management events
    SITE_REGISTERED = 'site_registered'
    SITE_UPDATED = 'site_updated'
    SITE_DELETED = 'site_deleted'
    API_KEY_CREATED = 'api_key_created'
    API_KEY_ROTATED = 'api_key_rotated'
    
    # Admin events
    ADMIN_ACTION = 'admin_action'
    BULK_OPERATION = 'bulk_operation'
    
    # Security events
    RATE_LIMIT_EXCEEDED = 'rate_limit_exceeded'
    SUSPICIOUS_ACTIVITY = 'suspicious_activity'
    IP_BLOCKED = 'ip_blocked'
    
    # Data events
    AUDIT_LOG_EXPORTED = 'audit_log_exported'
    DATA_DELETED = 'data_deleted'


def init_audit_logging():
    """
    Initialize audit logging tables
    Run this once to create the audit_logs table
    """
    if not DATABASE_AVAILABLE:
        logger.error("❌ Cannot initialize audit logging - database not available")
        return False
    
    try:
        # SQL to create audit_logs table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGSERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            event_type VARCHAR(50) NOT NULL,
            user_email VARCHAR(255),
            user_did VARCHAR(255),
            site_id VARCHAR(100),
            resource VARCHAR(500),
            action VARCHAR(50),
            result VARCHAR(20) NOT NULL,
            ip_address INET,
            user_agent TEXT,
            nonce VARCHAR(128),
            credential_id VARCHAR(128),
            metadata JSONB,
            
            -- Indexes for fast queries
            CONSTRAINT audit_logs_result_check CHECK (result IN ('success', 'failure', 'warning'))
        );
        
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs (timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_user_email ON audit_logs (user_email);
        CREATE INDEX IF NOT EXISTS idx_audit_site ON audit_logs (site_id);
        CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_logs (event_type);
        CREATE INDEX IF NOT EXISTS idx_audit_result ON audit_logs (result);
        CREATE INDEX IF NOT EXISTS idx_audit_ip ON audit_logs (ip_address);
        """
        
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(create_table_sql))
            conn.commit()
        logger.info("✅ Audit logs table created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to create audit logs table: {e}")
        return False


def log_event(
    event_type: str,
    result: str = 'success',
    user_email: Optional[str] = None,
    user_did: Optional[str] = None,
    site_id: Optional[str] = None,
    resource: Optional[str] = None,
    action: Optional[str] = None,
    nonce: Optional[str] = None,
    credential_id: Optional[str] = None,
    metadata: Optional[Dict] = None
):
    """
    Log an audit event
    
    Args:
        event_type: Type of event (use AuditEvent constants)
        result: 'success', 'failure', or 'warning'
        user_email: Email of user (if applicable)
        user_did: DID of user (if applicable)
        site_id: Site identifier
        resource: Resource being accessed (e.g., '/admin/users')
        action: Action being performed (e.g., 'read', 'write')
        nonce: Nonce used (for replay detection)
        credential_id: Credential identifier
        metadata: Additional context (JSON)
    
    Example:
        log_event(
            AuditEvent.PERMISSION_GRANTED,
            result='success',
            user_email='user@example.com',
            site_id='site_123',
            metadata={'permission_id': 'admin', 'granted_by': 'admin@site.com'}
        )
    """
    if not DATABASE_AVAILABLE:
        # Fallback to file logging if database not available
        logger.info(f"AUDIT: {event_type} - {result} - {user_email or user_did}")
        return
    
    try:
        # Get request context if available
        ip_address = None
        user_agent = None
        
        if request:
            ip_address = request.remote_addr
            user_agent = request.headers.get('User-Agent', '')[:500]  # Truncate
        
        # Prepare metadata
        if metadata is None:
            metadata = {}
        
        # Add request metadata if available
        if request:
            metadata['request_method'] = request.method
            metadata['request_path'] = request.path
            metadata['request_id'] = getattr(g, 'request_id', None)
        
        # Insert into database
        from sqlalchemy import text
        
        insert_sql = text("""
        INSERT INTO audit_logs (
            timestamp, event_type, user_email, user_did, site_id,
            resource, action, result, ip_address, user_agent,
            nonce, credential_id, metadata
        ) VALUES (
            NOW(), :event_type, :user_email, :user_did, :site_id,
            :resource, :action, :result, :ip_address, :user_agent,
            :nonce, :credential_id, :metadata
        )
        """)
        
        with engine.connect() as conn:
            conn.execute(
                insert_sql,
                {
                    'event_type': event_type,
                    'user_email': user_email,
                    'user_did': user_did,
                    'site_id': site_id,
                    'resource': resource,
                    'action': action,
                    'result': result,
                    'ip_address': ip_address,
                    'user_agent': user_agent,
                    'nonce': nonce,
                    'credential_id': credential_id,
                    'metadata': json.dumps(metadata)
                }
            )
            conn.commit()
        
        # Also log to standard logger for real-time monitoring
        log_level = logging.WARNING if result == 'failure' else logging.INFO
        logger.log(
            log_level,
            f"AUDIT: {event_type} | {result} | {user_email or user_did or 'anonymous'} | {site_id or 'N/A'}"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to log audit event: {e}")
        # Never fail the main operation because of audit logging
        # But do try to report this to Sentry
        try:
            from monitoring.sentry_config import capture_exception
            capture_exception(e, context={
                'event_type': event_type,
                'message': 'Audit logging failed'
            })
        except:
            pass


def audit_decorator(event_type: str, resource_param: str = None):
    """
    Decorator to automatically log API endpoint access
    
    Usage:
        @audit_decorator(AuditEvent.PERMISSION_GRANTED, resource_param='site_id')
        def grant_permission(site_id, user_did):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get resource from function parameters
            resource = None
            if resource_param and resource_param in kwargs:
                resource = kwargs[resource_param]
            
            # Store start time
            start_time = time.time()
            
            try:
                # Execute the function
                result = f(*args, **kwargs)
                
                # Log success
                log_event(
                    event_type=event_type,
                    result='success',
                    site_id=kwargs.get('site_id'),
                    user_email=kwargs.get('user_email'),
                    user_did=kwargs.get('user_did'),
                    resource=resource or request.path,
                    action=request.method.lower(),
                    metadata={
                        'function': f.__name__,
                        'duration_ms': round((time.time() - start_time) * 1000, 2)
                    }
                )
                
                return result
                
            except Exception as e:
                # Log failure
                log_event(
                    event_type=event_type,
                    result='failure',
                    site_id=kwargs.get('site_id'),
                    user_email=kwargs.get('user_email'),
                    user_did=kwargs.get('user_did'),
                    resource=resource or request.path,
                    action=request.method.lower(),
                    metadata={
                        'function': f.__name__,
                        'error': str(e),
                        'duration_ms': round((time.time() - start_time) * 1000, 2)
                    }
                )
                
                # Re-raise the exception
                raise
        
        return decorated_function
    return decorator


def get_audit_logs(
    site_id: Optional[str] = None,
    user_email: Optional[str] = None,
    event_types: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    result: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0
) -> List[Dict]:
    """
    Query audit logs with filters
    
    Args:
        site_id: Filter by site
        user_email: Filter by user
        event_types: List of event types to include
        start_date: Start of date range
        end_date: End of date range
        result: Filter by result ('success', 'failure', 'warning')
        limit: Maximum number of results
        offset: Pagination offset
    
    Returns:
        List of audit log entries
    """
    if not DATABASE_AVAILABLE:
        return []
    
    try:
        # Build query with named parameters
        from sqlalchemy import text
        
        base_query = "SELECT * FROM audit_logs WHERE 1=1"
        param_dict = {}
        
        if site_id:
            base_query += " AND site_id = :site_id"
            param_dict['site_id'] = site_id
        
        if user_email:
            base_query += " AND user_email = :user_email"
            param_dict['user_email'] = user_email
        
        if event_types:
            # Handle multiple event types
            base_query += " AND event_type = ANY(:event_types)"
            param_dict['event_types'] = event_types
        
        if start_date:
            base_query += " AND timestamp >= :start_date"
            param_dict['start_date'] = start_date
        
        if end_date:
            base_query += " AND timestamp <= :end_date"
            param_dict['end_date'] = end_date
        
        if result:
            base_query += " AND result = :result"
            param_dict['result'] = result
        
        base_query += " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
        param_dict['limit'] = limit
        param_dict['offset'] = offset
        
        # Execute query
        with engine.connect() as conn:
            query_result = conn.execute(text(base_query), param_dict)
            
            # Convert to list of dicts
            logs = []
            for row in query_result:
                logs.append({
                    'id': row[0],
                    'timestamp': row[1].isoformat() if row[1] else None,
                    'event_type': row[2],
                    'user_email': row[3],
                    'user_did': row[4],
                    'site_id': row[5],
                    'resource': row[6],
                    'action': row[7],
                    'result': row[8],
                    'ip_address': str(row[9]) if row[9] else None,
                    'user_agent': row[10],
                    'nonce': row[11],
                    'credential_id': row[12],
                    'metadata': row[13]
                })
        
        return logs
        
    except Exception as e:
        logger.error(f"❌ Failed to query audit logs: {e}")
        return []


def export_audit_logs(
    site_id: str,
    format: str = 'csv',
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> str:
    """
    Export audit logs for a site
    
    Args:
        site_id: Site to export logs for
        format: 'csv' or 'json'
        start_date: Start of date range
        end_date: End of date range
    
    Returns:
        Formatted export data
    """
    # Get logs
    logs = get_audit_logs(
        site_id=site_id,
        start_date=start_date,
        end_date=end_date,
        limit=100000  # Large limit for export
    )
    
    if format == 'json':
        return json.dumps(logs, indent=2)
    
    elif format == 'csv':
        import csv
        import io
        
        output = io.StringIO()
        
        if logs:
            fieldnames = logs[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(logs)
        
        return output.getvalue()
    
    else:
        raise ValueError(f"Unsupported format: {format}")


# Convenience functions for common events

def log_email_confirmation_sent(user_email: str, site_id: str):
    """Log that confirmation email was sent"""
    log_event(
        AuditEvent.EMAIL_CONFIRMATION_SENT,
        user_email=user_email,
        site_id=site_id,
        result='success'
    )


def log_permission_granted(user_email: str, site_id: str, permission_id: str, granted_by: str):
    """Log permission grant"""
    log_event(
        AuditEvent.PERMISSION_GRANTED,
        user_email=user_email,
        site_id=site_id,
        result='success',
        metadata={
            'permission_id': permission_id,
            'granted_by': granted_by
        }
    )


def log_access_check(user_email: str, site_id: str, resource: str, action: str, allowed: bool):
    """Log access verification attempt"""
    log_event(
        AuditEvent.ACCESS_GRANTED if allowed else AuditEvent.ACCESS_DENIED,
        user_email=user_email,
        site_id=site_id,
        resource=resource,
        action=action,
        result='success' if allowed else 'failure'
    )


def log_nonce_replay(nonce: str, ip_address: str = None):
    """Log nonce replay attempt (security event)"""
    log_event(
        AuditEvent.NONCE_REPLAY_DETECTED,
        result='warning',
        nonce=nonce,
        metadata={
            'ip_address': ip_address or request.remote_addr if request else None,
            'severity': 'high'
        }
    )

