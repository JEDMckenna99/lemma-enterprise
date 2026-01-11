"""
API Input Validation Middleware

Prevents edge cases like:
- Empty or missing site_id defaulting to 'lemma.id' unexpectedly
- Invalid credential formats
- Timestamp format mismatches
"""

from functools import wraps
from flask import request, jsonify
import re
from datetime import datetime


# Valid site_id patterns (domains or known internal IDs)
VALID_SITE_ID_PATTERN = re.compile(
    r'^[a-zA-Z0-9]([a-zA-Z0-9\-_]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-_]*[a-zA-Z0-9])?)*$'
)

# Known internal site IDs that are valid
KNOWN_INTERNAL_SITE_IDS = {
    'lemma.id',
    'lemma_platform',
    'lemma-platform',
    'demo.lemma.id',
    'test.lemma.id'
}

# Maximum lengths for inputs
MAX_SITE_ID_LENGTH = 255
MAX_EMAIL_LENGTH = 320
MAX_PERMISSION_ID_LENGTH = 100


class ValidationError(Exception):
    """Custom validation error with details"""
    def __init__(self, field: str, message: str, code: str = 'invalid'):
        self.field = field
        self.message = message
        self.code = code
        super().__init__(f"{field}: {message}")


def validate_site_id(site_id: str, required: bool = True, allow_lemma_default: bool = False) -> str:
    """
    Validate and normalize site_id.
    
    Args:
        site_id: The site ID to validate
        required: If True, raises error when empty
        allow_lemma_default: If True, allows defaulting to 'lemma.id' when empty
        
    Returns:
        Normalized site_id
        
    Raises:
        ValidationError: If validation fails
    """
    # Handle None/empty
    if site_id is None or (isinstance(site_id, str) and site_id.strip() == ''):
        if required and not allow_lemma_default:
            raise ValidationError('site_id', 'site_id is required', 'required')
        if allow_lemma_default:
            return 'lemma.id'
        return ''
    
    site_id = str(site_id).strip().lower()
    
    # Check length
    if len(site_id) > MAX_SITE_ID_LENGTH:
        raise ValidationError('site_id', f'site_id must be <= {MAX_SITE_ID_LENGTH} characters', 'too_long')
    
    # Check if it's a known internal ID
    if site_id in KNOWN_INTERNAL_SITE_IDS:
        return site_id
    
    # Validate format (domain-like pattern)
    if not VALID_SITE_ID_PATTERN.match(site_id):
        raise ValidationError('site_id', 'site_id must be a valid domain or identifier', 'invalid_format')
    
    return site_id


def validate_email(email: str, required: bool = True) -> str:
    """Validate email format"""
    if email is None or (isinstance(email, str) and email.strip() == ''):
        if required:
            raise ValidationError('email', 'email is required', 'required')
        return ''
    
    email = str(email).strip().lower()
    
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValidationError('email', f'email must be <= {MAX_EMAIL_LENGTH} characters', 'too_long')
    
    # Basic email pattern (not exhaustive, but catches obvious issues)
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    if not email_pattern.match(email):
        raise ValidationError('email', 'invalid email format', 'invalid_format')
    
    return email


def validate_permission_id(permission_id: str, required: bool = True) -> str:
    """Validate permission ID"""
    if permission_id is None or (isinstance(permission_id, str) and permission_id.strip() == ''):
        if required:
            raise ValidationError('permission_id', 'permission_id is required', 'required')
        return ''
    
    permission_id = str(permission_id).strip()
    
    if len(permission_id) > MAX_PERMISSION_ID_LENGTH:
        raise ValidationError('permission_id', f'permission_id must be <= {MAX_PERMISSION_ID_LENGTH} characters', 'too_long')
    
    # Only allow alphanumeric, underscore, hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', permission_id):
        raise ValidationError('permission_id', 'permission_id must contain only letters, numbers, underscores, and hyphens', 'invalid_format')
    
    return permission_id


def validate_timestamp(timestamp, field_name: str = 'timestamp') -> int:
    """
    Validate and normalize timestamp to milliseconds.
    
    Handles:
    - Unix seconds
    - Unix milliseconds
    - ISO 8601 strings
    - datetime objects
    
    Returns:
        Timestamp in milliseconds
    """
    if timestamp is None:
        return None
    
    # Already a number
    if isinstance(timestamp, (int, float)):
        ts = int(timestamp)
        # If it looks like seconds (before year 2100 in seconds), convert to ms
        if ts < 4102444800:  # 2100-01-01 in seconds
            return ts * 1000
        return ts
    
    # String - try parsing
    if isinstance(timestamp, str):
        timestamp = timestamp.strip()
        
        # Try as numeric string first
        try:
            ts = int(float(timestamp))
            if ts < 4102444800:
                return ts * 1000
            return ts
        except ValueError:
            pass
        
        # Try ISO format
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        except ValueError:
            raise ValidationError(field_name, 'invalid timestamp format', 'invalid_format')
    
    # datetime object
    if isinstance(timestamp, datetime):
        return int(timestamp.timestamp() * 1000)
    
    raise ValidationError(field_name, 'timestamp must be a number, ISO string, or datetime', 'invalid_type')


def validate_credential_claims(claims: dict) -> dict:
    """Validate credential claims structure"""
    if not isinstance(claims, dict):
        raise ValidationError('claims', 'claims must be an object', 'invalid_type')
    
    validated = {}
    
    # Normalize site_id from various formats
    site_id = claims.get('siteId') or claims.get('site') or claims.get('site_id') or claims.get('siteDomain')
    if site_id:
        validated['siteId'] = validate_site_id(site_id, required=False)
    
    # Normalize email
    email = claims.get('email')
    if email:
        validated['email'] = validate_email(email, required=False)
    
    # Normalize permission
    permission = claims.get('permissionId') or claims.get('permission_level') or claims.get('permissions')
    if permission:
        validated['permissionId'] = validate_permission_id(permission, required=False)
    
    # Copy other claims as-is
    for key, value in claims.items():
        if key not in ['siteId', 'site', 'site_id', 'siteDomain', 'email', 'permissionId', 'permission_level', 'permissions']:
            validated[key] = value
    
    return validated


def require_valid_json(*required_fields):
    """
    Decorator that validates JSON request body.
    
    Usage:
        @require_valid_json('site_id', 'email')
        def my_endpoint():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                data = request.get_json(force=True)
            except Exception:
                return jsonify({
                    'success': False,
                    'error': 'invalid_json',
                    'message': 'Request body must be valid JSON'
                }), 400
            
            if data is None:
                return jsonify({
                    'success': False,
                    'error': 'missing_body',
                    'message': 'Request body is required'
                }), 400
            
            # Check required fields
            missing = [field for field in required_fields if field not in data or data[field] is None]
            if missing:
                return jsonify({
                    'success': False,
                    'error': 'missing_fields',
                    'message': f'Missing required fields: {", ".join(missing)}',
                    'fields': missing
                }), 400
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_api_request(*field_validators):
    """
    Decorator that applies validation to specific fields.
    
    Usage:
        @validate_api_request(
            ('site_id', validate_site_id, {'required': True}),
            ('email', validate_email, {'required': False})
        )
        def my_endpoint():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                data = request.get_json(silent=True) or {}
            except Exception:
                data = {}
            
            errors = []
            
            for field_name, validator, options in field_validators:
                value = data.get(field_name)
                try:
                    validator(value, **options)
                except ValidationError as e:
                    errors.append({
                        'field': e.field,
                        'message': e.message,
                        'code': e.code
                    })
            
            if errors:
                return jsonify({
                    'success': False,
                    'error': 'validation_failed',
                    'message': 'Request validation failed',
                    'errors': errors
                }), 400
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Pre-built validators for common patterns
def require_site_id(allow_default: bool = False):
    """Decorator requiring valid site_id"""
    return validate_api_request(
        ('site_id', validate_site_id, {'required': True, 'allow_lemma_default': allow_default})
    )


def require_email():
    """Decorator requiring valid email"""
    return validate_api_request(
        ('email', validate_email, {'required': True})
    )
