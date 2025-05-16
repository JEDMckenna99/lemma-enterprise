"""
Wallet utility module for the Lemma SSI system.
Provides functions for creating, storing, and retrieving wallet-compatible credentials.
"""
import json
import base64
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from flask import current_app

class LemmaWallet:
    """Lemma SSI Wallet implementation."""
    
    @staticmethod
    def format_for_wallet(credential: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        Format a credential to be wallet-compatible.
        
        Args:
            credential: Original credential
            user_id: User ID
            
        Returns:
            Wallet-formatted credential
        """
        # Create a wallet-friendly version of the credential
        wallet_credential = {
            # Keep the original credential intact
            "credential": credential,
            # Add wallet metadata
            "wallet_metadata": {
                "added_at": datetime.now().isoformat(),
                "holder_id": user_id,
                "status": "active",
                "display_name": "Lemma Human Verification",
                # Generate a fingerprint for this credential
                "fingerprint": LemmaWallet.generate_fingerprint(credential)
            }
        }
        
        return wallet_credential
    
    @staticmethod
    def generate_fingerprint(credential: Dict[str, Any]) -> str:
        """
        Generate a unique fingerprint for a credential.
        
        Args:
            credential: The credential to generate a fingerprint for
            
        Returns:
            A string fingerprint
        """
        # Create a deterministic representation of the credential
        cred_id = credential.get('id', '')
        issuer_id = credential.get('issuer', '')
        issuance_date = credential.get('issuanceDate', '')
        
        # Combine key parts of the credential to create a unique fingerprint
        fingerprint_input = f"{cred_id}:{issuer_id}:{issuance_date}"
        return hashlib.sha256(fingerprint_input.encode()).hexdigest()
    
    @staticmethod
    def create_export_bundle(credentials: List[Dict[str, Any]], password: Optional[str] = None) -> Dict[str, Any]:
        """
        Create an export bundle of credentials that can be saved or transferred.
        
        Args:
            credentials: List of credentials to export
            password: Optional password to protect the export
            
        Returns:
            An export bundle structure
        """
        now = datetime.now().isoformat()
        
        bundle = {
            "format": "lemma-wallet-export",
            "version": "1.0",
            "created_at": now,
            "credentials": credentials,
            "metadata": {
                "credential_count": len(credentials),
                "export_date": now,
                "protected": password is not None
            }
        }
        
        # If a password is provided, we would encrypt the bundle here
        # This is a simplified version without actual encryption
        if password:
            bundle["metadata"]["encryption"] = "password_protected"
        
        return bundle
    
    @staticmethod
    def generate_backup_uri(wallet_credential: Dict[str, Any]) -> str:
        """
        Generate a URI that can be used to back up a credential.
        
        Args:
            wallet_credential: Wallet credential to generate URI for
            
        Returns:
            A URI string for backup/transfer
        """
        # Convert credential to JSON and encode as base64
        credential_json = json.dumps(wallet_credential)
        encoded_credential = base64.urlsafe_b64encode(credential_json.encode()).decode()
        
        # Create a URI with the lemma scheme
        return f"lemma://wallet/import?data={encoded_credential}"
    
    @staticmethod
    def generate_qr_data(wallet_credential: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate data for QR code display of a credential.
        
        Args:
            wallet_credential: Wallet credential to generate QR data for
            
        Returns:
            Data structure for QR code generation
        """
        # Create a compact representation for QR codes
        credential = wallet_credential.get("credential", {})
        
        # Use only essential information to keep QR code simple
        qr_data = {
            "type": "LemmaCredential",
            "id": credential.get("id", ""),
            "issuer": credential.get("issuer", ""),
            "subject": credential.get("credentialSubject", {}).get("id", ""),
            "issued": credential.get("issuanceDate", ""),
            "expires": credential.get("expirationDate", ""),
            "fingerprint": wallet_credential.get("wallet_metadata", {}).get("fingerprint", "")
        }
        
        return qr_data

def format_credential_for_display(credential: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a credential for user-friendly display.
    
    Args:
        credential: Original credential
        
    Returns:
        User-friendly credential representation
    """
    # Extract only the information needed for display
    display_info = {
        "title": "Human Verification",
        "issuer": {
            "id": credential.get("issuer", "Unknown Issuer"),
            "name": "Lemma Verification Service"
        },
        "issuedDate": credential.get("issuanceDate", "Unknown"),
        "expiryDate": credential.get("expirationDate", "Never"),
        "credentialType": ", ".join(credential.get("type", ["Unknown"]))
    }
    
    # Add subject information
    subject = credential.get("credentialSubject", {})
    display_info["subject"] = {
        "id": subject.get("id", "Unknown Subject"),
        "type": subject.get("type", "Unknown Type")
    }
    
    return display_info 