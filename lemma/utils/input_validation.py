"""
Comprehensive input validation utilities for Lemma Enterprise.
Provides secure validation for all API inputs with proper error handling.
"""
import re
import uuid
import base64
import json
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime, timedelta
from flask import current_app
import logging

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom exception for validation errors."""
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(self.message)

class InputValidator:
    """Comprehensive input validation for API endpoints."""
    
    # Security limits
    MAX_STRING_LENGTH = 10000
    MAX_LIST_LENGTH = 100
    MAX_DICT_DEPTH = 10
    MAX_USER_ID_LENGTH = 100
    MAX_DID_LENGTH = 200
    MAX_CHALLENGE_LENGTH = 500
    MAX_CREDENTIAL_SIZE = 50000  # 50KB
    
    # Regular expressions for common patterns
    USER_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
    DID_PATTERN = re.compile(r'^did:[a-z0-9]+:[a-zA-Z0-9._-]+$')
    UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    BASE64_PATTERN = re.compile(r'^[A-Za-z0-9+/]*={0,2}$')
    API_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{16,}$')
    
    @classmethod
    def validate_user_id(cls, user_id: Any) -> str:
        """Validate user ID format and length."""
        if not isinstance(user_id, str):
            raise ValidationError("User ID must be a string", "user_id")
        
        if not user_id or len(user_id) == 0:
            raise ValidationError("User ID cannot be empty", "user_id")
        
        if len(user_id) > cls.MAX_USER_ID_LENGTH:
            raise ValidationError(f"User ID too long (max {cls.MAX_USER_ID_LENGTH} characters)", "user_id")
        
        if not cls.USER_ID_PATTERN.match(user_id):
            raise ValidationError("User ID contains invalid characters", "user_id")
        
        return user_id
    
    @classmethod
    def validate_did(cls, did: Any) -> str:
        """Validate DID format."""
        if not isinstance(did, str):
            raise ValidationError("DID must be a string", "did")
        
        if len(did) > cls.MAX_DID_LENGTH:
            raise ValidationError(f"DID too long (max {cls.MAX_DID_LENGTH} characters)", "did")
        
        if not cls.DID_PATTERN.match(did):
            raise ValidationError("Invalid DID format", "did")
        
        return did
    
    @classmethod
    def validate_challenge(cls, challenge: Any) -> str:
        """Validate challenge string."""
        if not isinstance(challenge, str):
            raise ValidationError("Challenge must be a string", "challenge")
        
        if len(challenge) < 8:
            raise ValidationError("Challenge too short (minimum 8 characters)", "challenge")
        
        if len(challenge) > cls.MAX_CHALLENGE_LENGTH:
            raise ValidationError(f"Challenge too long (max {cls.MAX_CHALLENGE_LENGTH} characters)", "challenge")
        
        return challenge
    
    @classmethod
    def validate_credential(cls, credential: Any) -> Dict[str, Any]:
        """Validate verifiable credential structure."""
        if not isinstance(credential, dict):
            raise ValidationError("Credential must be a dictionary", "credential")
        
        # Check size limit
        credential_str = json.dumps(credential)
        if len(credential_str) > cls.MAX_CREDENTIAL_SIZE:
            raise ValidationError(f"Credential too large (max {cls.MAX_CREDENTIAL_SIZE} bytes)", "credential")
        
        # Required fields
        required_fields = ["@context", "type", "issuer", "credentialSubject"]
        for field in required_fields:
            if field not in credential:
                raise ValidationError(f"Missing required field: {field}", "credential")
        
        # Validate types
        if not isinstance(credential["type"], list):
            raise ValidationError("Credential type must be a list", "credential")
        
        if "VerifiableCredential" not in credential["type"]:
            raise ValidationError("Credential must include VerifiableCredential type", "credential")
        
        # Validate issuer
        if isinstance(credential["issuer"], str):
            cls.validate_did(credential["issuer"])
        elif isinstance(credential["issuer"], dict):
            if "id" not in credential["issuer"]:
                raise ValidationError("Issuer object must have id field", "credential")
            cls.validate_did(credential["issuer"]["id"])
        else:
            raise ValidationError("Issuer must be string or object", "credential")
        
        # Validate credential subject
        if not isinstance(credential["credentialSubject"], dict):
            raise ValidationError("Credential subject must be a dictionary", "credential")
        
        return credential
    
    @classmethod
    def validate_presentation(cls, presentation: Any) -> Dict[str, Any]:
        """Validate verifiable presentation structure."""
        if not isinstance(presentation, dict):
            raise ValidationError("Presentation must be a dictionary", "presentation")
        
        # Check size limit
        presentation_str = json.dumps(presentation)
        if len(presentation_str) > cls.MAX_CREDENTIAL_SIZE * 5:  # Allow larger for presentations
            raise ValidationError("Presentation too large", "presentation")
        
        # Required fields
        if "type" not in presentation:
            raise ValidationError("Missing required field: type", "presentation")
        
        if not isinstance(presentation["type"], list):
            raise ValidationError("Presentation type must be a list", "presentation")
        
        if "VerifiablePresentation" not in presentation["type"]:
            raise ValidationError("Presentation must include VerifiablePresentation type", "presentation")
        
        # Validate credentials if present
        if "verifiableCredential" in presentation:
            credentials = presentation["verifiableCredential"]
            if not isinstance(credentials, list):
                raise ValidationError("Verifiable credentials must be a list", "presentation")
            
            if len(credentials) > cls.MAX_LIST_LENGTH:
                raise ValidationError(f"Too many credentials (max {cls.MAX_LIST_LENGTH})", "presentation")
            
            for i, credential in enumerate(credentials):
                try:
                    cls.validate_credential(credential)
                except ValidationError as e:
                    raise ValidationError(f"Invalid credential at index {i}: {e.message}", "presentation")
        
        return presentation
    
    @classmethod
    def validate_api_key(cls, api_key: Any) -> str:
        """Validate API key format."""
        if not isinstance(api_key, str):
            raise ValidationError("API key must be a string", "api_key")
        
        if not cls.API_KEY_PATTERN.match(api_key):
            raise ValidationError("Invalid API key format", "api_key")
        
        return api_key
    
    @classmethod
    def validate_base64(cls, data: Any, field_name: str = "data") -> str:
        """Validate base64 encoded data."""
        if not isinstance(data, str):
            raise ValidationError("Base64 data must be a string", field_name)
        
        if not cls.BASE64_PATTERN.match(data):
            raise ValidationError("Invalid base64 format", field_name)
        
        try:
            base64.b64decode(data)
        except Exception:
            raise ValidationError("Invalid base64 encoding", field_name)
        
        return data
    
    @classmethod
    def validate_uuid(cls, uuid_str: Any, field_name: str = "uuid") -> str:
        """Validate UUID format."""
        if not isinstance(uuid_str, str):
            raise ValidationError("UUID must be a string", field_name)
        
        if not cls.UUID_PATTERN.match(uuid_str.lower()):
            raise ValidationError("Invalid UUID format", field_name)
        
        try:
            uuid.UUID(uuid_str)
        except ValueError:
            raise ValidationError("Invalid UUID", field_name)
        
        return uuid_str
    
    @classmethod
    def validate_string(cls, value: Any, field_name: str, min_length: int = 1, max_length: int = None) -> str:
        """Validate string field with length constraints."""
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field_name)
        
        if len(value) < min_length:
            raise ValidationError(f"{field_name} too short (minimum {min_length} characters)", field_name)
        
        max_len = max_length if max_length is not None else cls.MAX_STRING_LENGTH
        if len(value) > max_len:
            raise ValidationError(f"{field_name} too long (maximum {max_len} characters)", field_name)
        
        return value
    
    @classmethod
    def validate_list(cls, value: Any, field_name: str, max_length: int = None) -> List[Any]:
        """Validate list field with length constraints."""
        if not isinstance(value, list):
            raise ValidationError(f"{field_name} must be a list", field_name)
        
        max_len = max_length if max_length is not None else cls.MAX_LIST_LENGTH
        if len(value) > max_len:
            raise ValidationError(f"{field_name} too long (maximum {max_len} items)", field_name)
        
        return value
    
    @classmethod
    def validate_dict(cls, value: Any, field_name: str, required_keys: List[str] = None) -> Dict[str, Any]:
        """Validate dictionary field with required keys."""
        if not isinstance(value, dict):
            raise ValidationError(f"{field_name} must be a dictionary", field_name)
        
        if required_keys:
            for key in required_keys:
                if key not in value:
                    raise ValidationError(f"Missing required key: {key}", field_name)
        
        # Check for deeply nested objects (security measure)
        def check_depth(obj, depth=0):
            if depth > cls.MAX_DICT_DEPTH:
                raise ValidationError(f"{field_name} has too deep nesting", field_name)
            if isinstance(obj, dict):
                for v in obj.values():
                    check_depth(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    check_depth(item, depth + 1)
        
        check_depth(value)
        return value
    
    @classmethod
    def validate_json_payload(cls, data: Any, required_fields: List[str] = None) -> Dict[str, Any]:
        """Validate JSON payload structure."""
        if not isinstance(data, dict):
            raise ValidationError("Request body must be a JSON object")
        
        if required_fields:
            for field in required_fields:
                if field not in data:
                    raise ValidationError(f"Missing required field: {field}")
        
        return data

def validate_request_data(validator_func):
    """Decorator to validate request data using a validator function."""
    def decorator(f):
        def wrapper(*args, **kwargs):
            from flask import request, jsonify
            
            try:
                # Get request data
                if request.is_json:
                    data = request.get_json()
                    if data is None:
                        return jsonify({"error": "Invalid JSON"}), 400
                elif request.form:
                    data = request.form.to_dict()
                else:
                    data = {}
                
                # Validate data
                validated_data = validator_func(data)
                
                # Add validated data to kwargs
                kwargs['validated_data'] = validated_data
                
                return f(*args, **kwargs)
                
            except ValidationError as e:
                logger.warning(f"Validation error in {f.__name__}: {e.message}")
                return jsonify({
                    "error": "Validation failed",
                    "message": e.message,
                    "field": e.field
                }), 400
            except Exception as e:
                logger.error(f"Unexpected error in validation: {str(e)}")
                return jsonify({"error": "Internal validation error"}), 500
        
        # Preserve function metadata
        wrapper.__name__ = f.__name__
        wrapper.__doc__ = f.__doc__
        
        return wrapper
    return decorator 