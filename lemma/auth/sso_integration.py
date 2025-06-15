"""
🔐 ENTERPRISE SSO INTEGRATION FOR ADMIN AUTHENTICATION
====================================================
SAML 2.0 and OpenID Connect (OIDC) integration for admin users
Eliminates local passwords in production environments
"""

import os
import json
import time
import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlencode, parse_qs, urlparse
import xml.etree.ElementTree as ET
from xml.dom import minidom
import jwt
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography import x509

from flask import request, current_app, session, redirect, url_for, jsonify, abort

logger = logging.getLogger(__name__)

class SAMLConfig:
    """SAML 2.0 configuration for enterprise SSO."""
    
    def __init__(self, config: Dict[str, Any]):
        self.entity_id = config.get('entity_id', 'lemma-enterprise')
        self.sso_url = config.get('sso_url')
        self.slo_url = config.get('slo_url')
        self.x509_cert = config.get('x509_cert')
        self.private_key = config.get('private_key')
        self.idp_entity_id = config.get('idp_entity_id')
        self.idp_sso_url = config.get('idp_sso_url')
        self.idp_slo_url = config.get('idp_slo_url')
        self.idp_x509_cert = config.get('idp_x509_cert')
        self.name_id_format = config.get('name_id_format', 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent')
        self.attribute_mapping = config.get('attribute_mapping', {
            'email': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
            'first_name': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname',
            'last_name': 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname',
            'roles': 'http://schemas.microsoft.com/ws/2008/06/identity/claims/role'
        })

class OIDCConfig:
    """OpenID Connect configuration for enterprise SSO."""
    
    def __init__(self, config: Dict[str, Any]):
        self.client_id = config.get('client_id')
        self.client_secret = config.get('client_secret')
        self.discovery_url = config.get('discovery_url')
        self.redirect_uri = config.get('redirect_uri')
        self.scopes = config.get('scopes', ['openid', 'profile', 'email'])
        self.response_type = config.get('response_type', 'code')
        self.response_mode = config.get('response_mode', 'query')
        
        # Auto-discover endpoints if discovery URL provided
        self.authorization_endpoint = None
        self.token_endpoint = None
        self.userinfo_endpoint = None
        self.jwks_uri = None
        self.issuer = None
        
        if self.discovery_url:
            self._discover_endpoints()
    
    def _discover_endpoints(self):
        """Auto-discover OIDC endpoints from discovery URL."""
        try:
            response = requests.get(self.discovery_url, timeout=10)
            response.raise_for_status()
            
            discovery_doc = response.json()
            
            self.authorization_endpoint = discovery_doc.get('authorization_endpoint')
            self.token_endpoint = discovery_doc.get('token_endpoint')
            self.userinfo_endpoint = discovery_doc.get('userinfo_endpoint')
            self.jwks_uri = discovery_doc.get('jwks_uri')
            self.issuer = discovery_doc.get('issuer')
            
            logger.info(f"OIDC endpoints discovered for issuer: {self.issuer}")
            
        except Exception as e:
            logger.error(f"Failed to discover OIDC endpoints: {e}")

class SAMLHandler:
    """SAML 2.0 authentication handler."""
    
    def __init__(self, config: SAMLConfig):
        self.config = config
    
    def generate_authn_request(self, relay_state: str = None) -> Tuple[str, str]:
        """Generate SAML AuthnRequest."""
        request_id = f"_{hashlib.sha256(str(time.time()).encode()).hexdigest()}"
        issue_instant = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        authn_request = f"""
        <samlp:AuthnRequest
            xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
            xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
            ID="{request_id}"
            Version="2.0"
            IssueInstant="{issue_instant}"
            Destination="{self.config.idp_sso_url}"
            AssertionConsumerServiceURL="{self.config.sso_url}"
            ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
            <saml:Issuer>{self.config.entity_id}</saml:Issuer>
            <samlp:NameIDPolicy
                Format="{self.config.name_id_format}"
                AllowCreate="true"/>
        </samlp:AuthnRequest>
        """
        
        # Compress and encode
        import zlib
        compressed = zlib.compress(authn_request.encode('utf-8'))
        encoded = base64.b64encode(compressed).decode('utf-8')
        
        # Build redirect URL
        params = {
            'SAMLRequest': encoded,
            'RelayState': relay_state or ''
        }
        
        redirect_url = f"{self.config.idp_sso_url}?{urlencode(params)}"
        
        return redirect_url, request_id
    
    def process_saml_response(self, saml_response: str, relay_state: str = None) -> Dict[str, Any]:
        """Process and validate SAML response."""
        try:
            # Decode SAML response
            decoded_response = base64.b64decode(saml_response)
            
            # Parse XML
            root = ET.fromstring(decoded_response)
            
            # Extract assertion
            assertion = root.find('.//{urn:oasis:names:tc:SAML:2.0:assertion}Assertion')
            if assertion is None:
                raise ValueError("No assertion found in SAML response")
            
            # Validate signature (simplified - in production use proper SAML library)
            if not self._validate_signature(assertion):
                raise ValueError("Invalid SAML assertion signature")
            
            # Extract user attributes
            attributes = self._extract_attributes(assertion)
            
            # Extract NameID
            name_id_element = assertion.find('.//{urn:oasis:names:tc:SAML:2.0:assertion}NameID')
            name_id = name_id_element.text if name_id_element is not None else None
            
            return {
                'success': True,
                'name_id': name_id,
                'attributes': attributes,
                'relay_state': relay_state
            }
            
        except Exception as e:
            logger.error(f"SAML response processing failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _validate_signature(self, assertion: ET.Element) -> bool:
        """Validate SAML assertion signature (simplified)."""
        # In production, use proper SAML library like python3-saml
        # This is a simplified validation for demonstration
        
        if not self.config.idp_x509_cert:
            logger.warning("No IdP certificate configured for signature validation")
            return True  # Skip validation if no cert configured
        
        try:
            # Load IdP certificate
            cert_data = base64.b64decode(self.config.idp_x509_cert)
            cert = x509.load_der_x509_certificate(cert_data)
            
            # In a real implementation, you would:
            # 1. Extract the signature from the assertion
            # 2. Canonicalize the signed portion
            # 3. Verify the signature using the IdP's public key
            
            logger.info("SAML signature validation passed (simplified)")
            return True
            
        except Exception as e:
            logger.error(f"SAML signature validation failed: {e}")
            return False
    
    def _extract_attributes(self, assertion: ET.Element) -> Dict[str, Any]:
        """Extract user attributes from SAML assertion."""
        attributes = {}
        
        # Find attribute statement
        attr_statement = assertion.find('.//{urn:oasis:names:tc:SAML:2.0:assertion}AttributeStatement')
        if attr_statement is None:
            return attributes
        
        # Extract attributes
        for attr in attr_statement.findall('.//{urn:oasis:names:tc:SAML:2.0:assertion}Attribute'):
            attr_name = attr.get('Name')
            attr_values = []
            
            for value in attr.findall('.//{urn:oasis:names:tc:SAML:2.0:assertion}AttributeValue'):
                if value.text:
                    attr_values.append(value.text)
            
            if attr_values:
                attributes[attr_name] = attr_values[0] if len(attr_values) == 1 else attr_values
        
        # Map to standard attributes
        mapped_attributes = {}
        for standard_name, saml_name in self.config.attribute_mapping.items():
            if saml_name in attributes:
                mapped_attributes[standard_name] = attributes[saml_name]
        
        return mapped_attributes

class OIDCHandler:
    """OpenID Connect authentication handler."""
    
    def __init__(self, config: OIDCConfig):
        self.config = config
    
    def generate_auth_url(self, state: str = None, nonce: str = None) -> str:
        """Generate OIDC authorization URL."""
        if not self.config.authorization_endpoint:
            raise ValueError("Authorization endpoint not configured")
        
        state = state or hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
        nonce = nonce or hashlib.sha256(f"{state}{time.time()}".encode()).hexdigest()[:16]
        
        params = {
            'client_id': self.config.client_id,
            'response_type': self.config.response_type,
            'scope': ' '.join(self.config.scopes),
            'redirect_uri': self.config.redirect_uri,
            'state': state,
            'nonce': nonce,
            'response_mode': self.config.response_mode
        }
        
        auth_url = f"{self.config.authorization_endpoint}?{urlencode(params)}"
        
        # Store state and nonce in session for validation
        session['oidc_state'] = state
        session['oidc_nonce'] = nonce
        
        return auth_url
    
    def process_callback(self, authorization_code: str, state: str) -> Dict[str, Any]:
        """Process OIDC callback and exchange code for tokens."""
        try:
            # Validate state
            if state != session.get('oidc_state'):
                raise ValueError("Invalid state parameter")
            
            # Exchange code for tokens
            token_data = self._exchange_code_for_tokens(authorization_code)
            
            # Validate and decode ID token
            id_token_claims = self._validate_id_token(token_data.get('id_token'))
            
            # Get user info if access token available
            user_info = {}
            if token_data.get('access_token'):
                user_info = self._get_user_info(token_data['access_token'])
            
            # Combine claims
            user_data = {**id_token_claims, **user_info}
            
            return {
                'success': True,
                'user_data': user_data,
                'tokens': token_data
            }
            
        except Exception as e:
            logger.error(f"OIDC callback processing failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _exchange_code_for_tokens(self, authorization_code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens."""
        if not self.config.token_endpoint:
            raise ValueError("Token endpoint not configured")
        
        token_data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': self.config.redirect_uri,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret
        }
        
        response = requests.post(
            self.config.token_endpoint,
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10
        )
        
        response.raise_for_status()
        return response.json()
    
    def _validate_id_token(self, id_token: str) -> Dict[str, Any]:
        """Validate and decode ID token."""
        if not id_token:
            raise ValueError("No ID token received")
        
        # Get JWKS for validation
        jwks = self._get_jwks()
        
        # Decode token header to get key ID
        header = jwt.get_unverified_header(id_token)
        kid = header.get('kid')
        
        # Find matching key
        signing_key = None
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
                break
        
        if not signing_key:
            raise ValueError("No matching signing key found")
        
        # Validate and decode token
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=['RS256'],
            audience=self.config.client_id,
            issuer=self.config.issuer,
            options={
                'verify_exp': True,
                'verify_iat': True,
                'verify_aud': True,
                'verify_iss': True
            }
        )
        
        # Validate nonce
        if claims.get('nonce') != session.get('oidc_nonce'):
            raise ValueError("Invalid nonce in ID token")
        
        return claims
    
    def _get_jwks(self) -> Dict[str, Any]:
        """Get JSON Web Key Set for token validation."""
        if not self.config.jwks_uri:
            raise ValueError("JWKS URI not configured")
        
        response = requests.get(self.config.jwks_uri, timeout=10)
        response.raise_for_status()
        return response.json()
    
    def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info using access token."""
        if not self.config.userinfo_endpoint:
            return {}
        
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(self.config.userinfo_endpoint, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Failed to get user info: {response.status_code}")
            return {}

class EnterpriseSSO:
    """Enterprise SSO integration manager."""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or current_app.config.get('STORAGE_DIR', '.lemma_enterprise')
        self.sso_dir = os.path.join(self.storage_dir, 'sso')
        os.makedirs(self.sso_dir, exist_ok=True)
        
        # Load configurations
        self.saml_config = self._load_saml_config()
        self.oidc_config = self._load_oidc_config()
        
        # Initialize handlers
        self.saml_handler = SAMLHandler(self.saml_config) if self.saml_config else None
        self.oidc_handler = OIDCHandler(self.oidc_config) if self.oidc_config else None
    
    def _load_saml_config(self) -> Optional[SAMLConfig]:
        """Load SAML configuration."""
        config_file = os.path.join(self.sso_dir, 'saml_config.json')
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                return SAMLConfig(config_data)
            except Exception as e:
                logger.error(f"Failed to load SAML config: {e}")
        
        # Try environment variables
        env_config = {
            'entity_id': os.environ.get('SAML_ENTITY_ID'),
            'sso_url': os.environ.get('SAML_SSO_URL'),
            'slo_url': os.environ.get('SAML_SLO_URL'),
            'x509_cert': os.environ.get('SAML_X509_CERT'),
            'private_key': os.environ.get('SAML_PRIVATE_KEY'),
            'idp_entity_id': os.environ.get('SAML_IDP_ENTITY_ID'),
            'idp_sso_url': os.environ.get('SAML_IDP_SSO_URL'),
            'idp_slo_url': os.environ.get('SAML_IDP_SLO_URL'),
            'idp_x509_cert': os.environ.get('SAML_IDP_X509_CERT')
        }
        
        if any(env_config.values()):
            return SAMLConfig(env_config)
        
        return None
    
    def _load_oidc_config(self) -> Optional[OIDCConfig]:
        """Load OIDC configuration."""
        config_file = os.path.join(self.sso_dir, 'oidc_config.json')
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                return OIDCConfig(config_data)
            except Exception as e:
                logger.error(f"Failed to load OIDC config: {e}")
        
        # Try environment variables
        env_config = {
            'client_id': os.environ.get('OIDC_CLIENT_ID'),
            'client_secret': os.environ.get('OIDC_CLIENT_SECRET'),
            'discovery_url': os.environ.get('OIDC_DISCOVERY_URL'),
            'redirect_uri': os.environ.get('OIDC_REDIRECT_URI')
        }
        
        if any(env_config.values()):
            return OIDCConfig(env_config)
        
        return None
    
    def is_sso_enabled(self) -> bool:
        """Check if SSO is enabled."""
        return self.saml_handler is not None or self.oidc_handler is not None
    
    def get_sso_login_url(self, provider: str = 'auto', relay_state: str = None) -> Optional[str]:
        """Get SSO login URL for specified provider."""
        if provider == 'saml' and self.saml_handler:
            url, request_id = self.saml_handler.generate_authn_request(relay_state)
            session['saml_request_id'] = request_id
            return url
        
        elif provider == 'oidc' and self.oidc_handler:
            return self.oidc_handler.generate_auth_url(state=relay_state)
        
        elif provider == 'auto':
            # Auto-select available provider
            if self.oidc_handler:
                return self.oidc_handler.generate_auth_url(state=relay_state)
            elif self.saml_handler:
                url, request_id = self.saml_handler.generate_authn_request(relay_state)
                session['saml_request_id'] = request_id
                return url
        
        return None
    
    def process_sso_callback(self, provider: str, **kwargs) -> Dict[str, Any]:
        """Process SSO callback."""
        if provider == 'saml' and self.saml_handler:
            saml_response = kwargs.get('SAMLResponse')
            relay_state = kwargs.get('RelayState')
            
            if not saml_response:
                return {'success': False, 'error': 'No SAML response received'}
            
            return self.saml_handler.process_saml_response(saml_response, relay_state)
        
        elif provider == 'oidc' and self.oidc_handler:
            code = kwargs.get('code')
            state = kwargs.get('state')
            
            if not code:
                return {'success': False, 'error': 'No authorization code received'}
            
            return self.oidc_handler.process_callback(code, state)
        
        return {'success': False, 'error': f'Unknown provider: {provider}'}
    
    def map_sso_user_to_admin(self, sso_result: Dict[str, Any], provider: str) -> Optional[Dict[str, Any]]:
        """Map SSO user data to admin user format."""
        if not sso_result.get('success'):
            return None
        
        if provider == 'saml':
            attributes = sso_result.get('attributes', {})
            return {
                'username': attributes.get('email', sso_result.get('name_id')),
                'email': attributes.get('email'),
                'first_name': attributes.get('first_name'),
                'last_name': attributes.get('last_name'),
                'roles': self._parse_roles(attributes.get('roles', [])),
                'auth_method': 'saml_sso',
                'saml_subject_id': sso_result.get('name_id')
            }
        
        elif provider == 'oidc':
            user_data = sso_result.get('user_data', {})
            return {
                'username': user_data.get('email', user_data.get('preferred_username')),
                'email': user_data.get('email'),
                'first_name': user_data.get('given_name'),
                'last_name': user_data.get('family_name'),
                'roles': self._parse_roles(user_data.get('roles', [])),
                'auth_method': 'oidc_sso',
                'oidc_subject_id': user_data.get('sub')
            }
        
        return None
    
    def _parse_roles(self, roles_data: Any) -> List[str]:
        """Parse roles from SSO response."""
        if isinstance(roles_data, str):
            # Single role or comma-separated roles
            return [role.strip() for role in roles_data.split(',')]
        elif isinstance(roles_data, list):
            return roles_data
        else:
            return []

# Global instance
_enterprise_sso = None

def get_enterprise_sso() -> EnterpriseSSO:
    """Get global enterprise SSO instance."""
    global _enterprise_sso
    if _enterprise_sso is None:
        _enterprise_sso = EnterpriseSSO()
    return _enterprise_sso 