"""
AWS KMS Manager for Lemma IAM Signing Keys
FIPS 140-2 Level 2/3 compliant key storage using AWS Key Management Service

This module provides HSM-backed encryption for site-specific Ed25519 signing keys.
Private keys are encrypted by AWS KMS and stored in PostgreSQL, ensuring that keys
are protected even if the database is compromised.

Security Features:
- Keys encrypted by AWS KMS (FIPS 140-2 validated HSMs)
- Encryption context for additional security
- Automatic key rotation support
- Full audit trail via AWS CloudTrail
- Fine-grained access control via IAM policies
"""

import boto3
import os
import logging
import base64
from typing import Tuple, Optional
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime

logger = logging.getLogger(__name__)


class LemmaKMSManager:
    """
    AWS KMS integration for site-specific signing key encryption
    
    This class manages the encryption and decryption of Ed25519 signing keys
    using AWS KMS. Each site's private key is encrypted with a Customer Master Key (CMK)
    and stored securely in the database.
    
    Security Properties:
    - Private keys NEVER stored in plaintext
    - Encryption context prevents key misuse
    - AWS CloudTrail logs all key operations
    - IAM policies control who can decrypt keys
    """
    
    def __init__(self):
        """
        Initialize KMS client
        
        Environment Variables Required:
        - AWS_ACCESS_KEY_ID: AWS access key
        - AWS_SECRET_ACCESS_KEY: AWS secret key
        - AWS_REGION: AWS region (default: us-east-1)
        - LEMMA_KMS_KEY_ID: KMS Customer Master Key ID or ARN
        """
        # Check for required environment variables
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        self.master_key_id = os.getenv('LEMMA_KMS_KEY_ID')
        
        # Validate configuration
        if not self.master_key_id:
            logger.warning("⚠️ LEMMA_KMS_KEY_ID not configured - KMS disabled")
            self.kms_enabled = False
            self.kms = None
            return
        
        if not self.aws_access_key or not self.aws_secret_key:
            logger.warning("⚠️ AWS credentials not configured - KMS disabled")
            self.kms_enabled = False
            self.kms = None
            return
        
        try:
            # Initialize KMS client
            self.kms = boto3.client(
                'kms',
                region_name=self.aws_region,
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key
            )
            
            self.kms_enabled = True
            logger.info(f"✅ KMS manager initialized with key: {self.master_key_id[:50]}...")
            logger.info(f"🔐 Region: {self.aws_region}")
            
        except (ClientError, BotoCoreError) as e:
            logger.error(f"❌ Failed to initialize KMS client: {e}")
            self.kms_enabled = False
            self.kms = None
    
    def is_enabled(self) -> bool:
        """Check if KMS is properly configured and enabled"""
        return self.kms_enabled and self.kms is not None
    
    def encrypt_signing_key(self, signing_key_bytes: bytes, site_id: str) -> Tuple[str, str]:
        """
        Encrypt site signing key using AWS KMS
        
        Args:
            signing_key_bytes: 32-byte Ed25519 private key
            site_id: Site identifier for audit trail and encryption context
            
        Returns:
            Tuple of (encrypted_key_base64, kms_key_id)
            
        Raises:
            RuntimeError: If KMS is not enabled
            ClientError: If KMS encryption fails
        """
        if not self.is_enabled():
            raise RuntimeError("KMS is not enabled - check AWS credentials and LEMMA_KMS_KEY_ID")
        
        if len(signing_key_bytes) != 32:
            raise ValueError(f"Invalid signing key length: {len(signing_key_bytes)} (expected 32 bytes)")
        
        try:
            # Encrypt using KMS with encryption context
            # Encryption context provides additional authenticated data (AAD)
            # and is logged in CloudTrail for audit purposes
            response = self.kms.encrypt(
                KeyId=self.master_key_id,
                Plaintext=signing_key_bytes,
                EncryptionContext={
                    'site_id': site_id,
                    'key_type': 'ed25519_signing_key',
                    'purpose': 'lemma_iam_credential_signing',
                    'version': '1.0',
                    'timestamp': str(int(datetime.utcnow().timestamp()))
                }
            )
            
            # Encode ciphertext as base64 for storage
            encrypted_key = response['CiphertextBlob']
            encrypted_key_b64 = base64.b64encode(encrypted_key).decode('utf-8')
            
            logger.info(f"🔐 Encrypted signing key for site {site_id} using KMS")
            logger.info(f"   Key ID: {response['KeyId'][:50]}...")
            logger.info(f"   Ciphertext size: {len(encrypted_key)} bytes")
            
            return encrypted_key_b64, response['KeyId']
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"❌ KMS encryption failed for site {site_id}")
            logger.error(f"   Error code: {error_code}")
            logger.error(f"   Error message: {error_msg}")
            raise
    
    def decrypt_signing_key(self, encrypted_key_b64: str, site_id: str) -> bytes:
        """
        Decrypt site signing key using AWS KMS
        
        Args:
            encrypted_key_b64: Base64-encoded encrypted key from database
            site_id: Site identifier (must match encryption context)
            
        Returns:
            32-byte Ed25519 private key (plaintext)
            
        Raises:
            RuntimeError: If KMS is not enabled
            ClientError: If KMS decryption fails or encryption context doesn't match
        """
        if not self.is_enabled():
            raise RuntimeError("KMS is not enabled - check AWS credentials and LEMMA_KMS_KEY_ID")
        
        try:
            # Decode base64 ciphertext
            encrypted_key = base64.b64decode(encrypted_key_b64)
            
            # Decrypt using KMS
            # The encryption context MUST match what was used during encryption
            # This prevents using the ciphertext for a different site
            response = self.kms.decrypt(
                CiphertextBlob=encrypted_key,
                EncryptionContext={
                    'site_id': site_id,
                    'key_type': 'ed25519_signing_key',
                    'purpose': 'lemma_iam_credential_signing',
                    'version': '1.0'
                    # Note: timestamp is omitted as it changes per encryption
                }
            )
            
            plaintext = response['Plaintext']
            
            if len(plaintext) != 32:
                raise ValueError(f"Decrypted key has invalid length: {len(plaintext)} (expected 32 bytes)")
            
            logger.info(f"🔓 Decrypted signing key for site {site_id} using KMS")
            logger.info(f"   Key ID: {response['KeyId'][:50]}...")
            
            return plaintext
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"❌ KMS decryption failed for site {site_id}")
            logger.error(f"   Error code: {error_code}")
            logger.error(f"   Error message: {error_msg}")
            
            if error_code == 'InvalidCiphertextException':
                logger.error("   This usually means the encryption context doesn't match")
            
            raise
    
    def rotate_master_key(self) -> bool:
        """
        Enable automatic key rotation for the master CMK
        
        AWS KMS will automatically rotate the CMK every year.
        Old key versions remain available to decrypt existing ciphertexts.
        
        Returns:
            True if rotation was enabled successfully
        """
        if not self.is_enabled():
            logger.warning("⚠️ Cannot enable rotation - KMS not enabled")
            return False
        
        try:
            self.kms.enable_key_rotation(KeyId=self.master_key_id)
            logger.info(f"✅ Enabled automatic rotation for master key {self.master_key_id}")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.error(f"❌ Failed to enable key rotation: {error_code}")
            return False
    
    def get_key_info(self) -> Optional[dict]:
        """
        Get information about the master CMK
        
        Returns:
            Dictionary with key metadata, or None if KMS is disabled
        """
        if not self.is_enabled():
            return None
        
        try:
            response = self.kms.describe_key(KeyId=self.master_key_id)
            key_metadata = response['KeyMetadata']
            
            return {
                'key_id': key_metadata['KeyId'],
                'arn': key_metadata['Arn'],
                'creation_date': key_metadata['CreationDate'],
                'enabled': key_metadata['Enabled'],
                'key_state': key_metadata['KeyState'],
                'key_usage': key_metadata['KeyUsage'],
                'description': key_metadata.get('Description', 'N/A')
            }
            
        except ClientError as e:
            logger.error(f"❌ Failed to get key info: {e}")
            return None


# Global KMS manager instance (singleton)
_kms_manager: Optional[LemmaKMSManager] = None


def get_kms_manager() -> LemmaKMSManager:
    """
    Get or create the global KMS manager instance
    
    Returns:
        LemmaKMSManager instance
    """
    global _kms_manager
    if _kms_manager is None:
        _kms_manager = LemmaKMSManager()
    return _kms_manager


def is_kms_available() -> bool:
    """
    Check if KMS is properly configured and available
    
    Returns:
        True if KMS can be used, False otherwise
    """
    manager = get_kms_manager()
    return manager.is_enabled()

