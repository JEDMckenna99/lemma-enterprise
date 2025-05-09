"""
Data models for the Lemma Human Verification System.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, List

@dataclass
class User:
    """User model for the Lemma system."""
    id: str
    created_at: datetime
    verification_status: str
    verified_at: Optional[datetime] = None
    credential_id: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Create a User from a dictionary."""
        return cls(
            id=data['id'],
            created_at=datetime.fromisoformat(data['created_at']),
            verification_status=data['verification_status'],
            verified_at=datetime.fromisoformat(data['verified_at']) if 'verified_at' in data else None,
            credential_id=data.get('credential_id')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert User to a dictionary."""
        result = {
            'id': self.id,
            'created_at': self.created_at.isoformat(),
            'verification_status': self.verification_status
        }
        
        if self.verified_at:
            result['verified_at'] = self.verified_at.isoformat()
        
        if self.credential_id:
            result['credential_id'] = self.credential_id
        
        return result

@dataclass
class Credential:
    """Credential model for the Lemma system."""
    id: str
    user_id: str
    issued_at: datetime
    expires_at: Optional[datetime] = None
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    proof_type: str = "Ed25519Signature2020"
    hash: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Credential':
        """Create a Credential from a dictionary."""
        return cls(
            id=data['id'],
            user_id=data['user_id'],
            issued_at=datetime.fromisoformat(data['issued_at']),
            expires_at=datetime.fromisoformat(data['expires_at']) if 'expires_at' in data else None,
            revoked=data.get('revoked', False),
            revoked_at=datetime.fromisoformat(data['revoked_at']) if 'revoked_at' in data else None,
            revoked_by=data.get('revoked_by'),
            proof_type=data.get('proof_type', "Ed25519Signature2020"),
            hash=data.get('hash')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Credential to a dictionary."""
        result = {
            'id': self.id,
            'user_id': self.user_id,
            'issued_at': self.issued_at.isoformat(),
            'revoked': self.revoked,
            'proof_type': self.proof_type
        }
        
        if self.expires_at:
            result['expires_at'] = self.expires_at.isoformat()
        
        if self.revoked and self.revoked_at:
            result['revoked_at'] = self.revoked_at.isoformat()
            result['revoked_by'] = self.revoked_by
        
        if self.hash:
            result['hash'] = self.hash
        
        return result
