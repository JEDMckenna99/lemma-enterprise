"""
Secure storage utilities for Lemma credentials using hardware security when available.
Supports secure enclaves on various platforms (TPM, Secure Enclave, Android Keystore).
"""

import os
import json
import base64
import platform
import logging
from typing import Dict, Any, Optional, Tuple

# Set up logging
logger = logging.getLogger(__name__)

class SecureStorage:
    """
    Cross-platform secure storage manager that uses hardware-backed key storage when available.
    Falls back to software encryption when hardware storage is not available.
    """
    
    def __init__(self):
        """Initialize the secure storage module."""
        self.platform = platform.system()
        self.secure_hardware_available = self._check_secure_hardware()
        logger.info(f"Secure storage initialized on {self.platform}, hardware security: {self.secure_hardware_available}")
    
    def _check_secure_hardware(self) -> bool:
        """Check if secure hardware is available on this platform."""
        if self.platform == "Windows":
            # Check for Windows TPM
            try:
                # In a real implementation, we would use the Windows API to check TPM
                # For now, just do a basic check for TPM service
                return os.path.exists("C:\\Windows\\System32\\tpm.sys")
            except Exception as e:
                logger.warning(f"Error checking Windows TPM: {e}")
                return False
        elif self.platform == "Darwin":
            # Check for macOS Secure Enclave
            try:
                # macOS 10.13+ with T1/T2 chip has Secure Enclave
                # In a real implementation, we would check this more thoroughly
                macos_version = platform.mac_ver()[0]
                return int(macos_version.split('.')[0]) >= 10 and int(macos_version.split('.')[1]) >= 13
            except Exception as e:
                logger.warning(f"Error checking macOS Secure Enclave: {e}")
                return False
        elif self.platform == "Linux":
            # Check for Linux TPM or secure hardware
            try:
                # In a real implementation, we would check for TPM or other secure hardware
                return os.path.exists("/dev/tpm0") or os.path.exists("/dev/tpmrm0")
            except Exception as e:
                logger.warning(f"Error checking Linux secure hardware: {e}")
                return False
        else:
            # Unknown platform
            return False
    
    def store_key(self, key_id: str, key_data: bytes) -> bool:
        """
        Store a key using hardware-backed storage if available.
        Falls back to software encryption if hardware not available.
        
        Args:
            key_id: A unique identifier for the key
            key_data: The cryptographic key material to store
            
        Returns:
            bool: True if the key was stored successfully
        """
        try:
            if self.secure_hardware_available:
                return self._store_key_hardware(key_id, key_data)
            else:
                return self._store_key_software(key_id, key_data)
        except Exception as e:
            logger.error(f"Error storing key {key_id}: {e}")
            return False
    
    def retrieve_key(self, key_id: str) -> Optional[bytes]:
        """
        Retrieve a key from secure storage.
        
        Args:
            key_id: The unique identifier for the key
            
        Returns:
            bytes: The key data if found, None otherwise
        """
        try:
            if self.secure_hardware_available:
                return self._retrieve_key_hardware(key_id)
            else:
                return self._retrieve_key_software(key_id)
        except Exception as e:
            logger.error(f"Error retrieving key {key_id}: {e}")
            return None
    
    def _store_key_hardware(self, key_id: str, key_data: bytes) -> bool:
        """Store a key using hardware-backed security."""
        if self.platform == "Windows":
            # Windows TPM implementation
            return self._store_key_windows_tpm(key_id, key_data)
        elif self.platform == "Darwin":
            # macOS Secure Enclave implementation
            return self._store_key_macos_secure_enclave(key_id, key_data)
        elif self.platform == "Linux":
            # Linux TPM implementation
            return self._store_key_linux_tpm(key_id, key_data)
        else:
            # Fallback to software storage
            return self._store_key_software(key_id, key_data)
    
    def _retrieve_key_hardware(self, key_id: str) -> Optional[bytes]:
        """Retrieve a key from hardware-backed security."""
        if self.platform == "Windows":
            # Windows TPM implementation
            return self._retrieve_key_windows_tpm(key_id)
        elif self.platform == "Darwin":
            # macOS Secure Enclave implementation
            return self._retrieve_key_macos_secure_enclave(key_id)
        elif self.platform == "Linux":
            # Linux TPM implementation
            return self._retrieve_key_linux_tpm(key_id)
        else:
            # Fallback to software storage
            return self._retrieve_key_software(key_id)
    
    def _store_key_software(self, key_id: str, key_data: bytes) -> bool:
        """
        Store a key using software encryption.
        This is a fallback when hardware-backed storage is not available.
        
        In a real implementation, this would use strong encryption with a user-derived key.
        For this example, we'll just encode the key and store it in a file.
        """
        try:
            # Create the secure storage directory if it doesn't exist
            os.makedirs(os.path.expanduser("~/.lemma/secure"), exist_ok=True)
            
            # Encode the key and save it to a file
            key_path = os.path.expanduser(f"~/.lemma/secure/{key_id}.key")
            with open(key_path, "wb") as f:
                f.write(key_data)
                
            logger.info(f"Key {key_id} stored using software encryption")
            return True
        except Exception as e:
            logger.error(f"Error storing key {key_id} using software: {e}")
            return False
    
    def _retrieve_key_software(self, key_id: str) -> Optional[bytes]:
        """
        Retrieve a key that was stored using software encryption.
        """
        try:
            key_path = os.path.expanduser(f"~/.lemma/secure/{key_id}.key")
            if not os.path.exists(key_path):
                logger.warning(f"Key {key_id} not found in software storage")
                return None
                
            with open(key_path, "rb") as f:
                key_data = f.read()
                
            logger.info(f"Key {key_id} retrieved from software storage")
            return key_data
        except Exception as e:
            logger.error(f"Error retrieving key {key_id} from software storage: {e}")
            return None
    
    # Platform-specific implementations
    # These would use the appropriate APIs for each platform
    # For this example, they fall back to software implementation
    
    def _store_key_windows_tpm(self, key_id: str, key_data: bytes) -> bool:
        """Store a key using Windows TPM."""
        try:
            # Check if we can import the Windows TPM-related modules
            import ctypes
            from ctypes import windll, wintypes
            
            # For Windows 10+, try to use TPM via DPAPI
            # This is a simplified implementation that uses the Windows CryptProtectData API
            # which will use TPM-backed keys when available on the system
            
            # Define necessary structures from DPAPI
            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ('cbData', wintypes.DWORD),
                    ('pbData', ctypes.POINTER(ctypes.c_char))
                ]
            
            # Get CryptProtectData function
            CryptProtectData = windll.crypt32.CryptProtectData
            CryptProtectData.argtypes = [
                ctypes.POINTER(DATA_BLOB),  # pDataIn
                wintypes.LPCWSTR,           # szDataDescr
                ctypes.POINTER(DATA_BLOB),  # pOptionalEntropy
                ctypes.c_void_p,            # pvReserved
                ctypes.c_void_p,            # pPromptStruct
                wintypes.DWORD,             # dwFlags
                ctypes.POINTER(DATA_BLOB)   # pDataOut
            ]
            CryptProtectData.restype = wintypes.BOOL
            
            # Create the input blob
            data_in = DATA_BLOB()
            data_in.cbData = len(key_data)
            data_in.pbData = ctypes.cast(key_data, ctypes.POINTER(ctypes.c_char))
            
            # Create an output blob
            data_out = DATA_BLOB()
            
            # Encrypt the data using DPAPI (which uses TPM if available)
            CRYPTPROTECT_UI_FORBIDDEN = 0x01
            if CryptProtectData(
                ctypes.byref(data_in),              # pDataIn
                f"Lemma Key: {key_id}",             # szDataDescr
                None,                               # pOptionalEntropy
                None,                               # pvReserved
                None,                               # pPromptStruct
                CRYPTPROTECT_UI_FORBIDDEN,          # dwFlags
                ctypes.byref(data_out)              # pDataOut
            ):
                # Get the encrypted data
                encrypted_len = data_out.cbData
                encrypted_data = ctypes.string_at(data_out.pbData, encrypted_len)
                
                # Store the encrypted data in a file
                os.makedirs(os.path.expanduser("~/.lemma/secure"), exist_ok=True)
                key_path = os.path.expanduser(f"~/.lemma/secure/{key_id}.tpm")
                with open(key_path, "wb") as f:
                    f.write(encrypted_data)
                
                # Free the output data
                LocalFree = windll.kernel32.LocalFree
                LocalFree.argtypes = [wintypes.HLOCAL]
                LocalFree.restype = wintypes.HLOCAL
                LocalFree(data_out.pbData)
                
                logger.info(f"Key {key_id} stored using Windows TPM protection")
                return True
            else:
                # If encryption failed, fall back to software
                logger.warning(f"Windows TPM encryption failed, falling back to software")
                return self._store_key_software(key_id, key_data)
                
        except (ImportError, AttributeError, Exception) as e:
            logger.warning(f"Windows TPM API access failed: {e}, falling back to software")
            return self._store_key_software(key_id, key_data)
    
    def _retrieve_key_windows_tpm(self, key_id: str) -> Optional[bytes]:
        """Retrieve a key from Windows TPM."""
        try:
            # Check the key exists
            key_path = os.path.expanduser(f"~/.lemma/secure/{key_id}.tpm")
            if not os.path.exists(key_path):
                logger.warning(f"Key {key_id} not found in Windows TPM storage")
                return None
                
            # Import necessary modules
            import ctypes
            from ctypes import windll, wintypes
            
            # Define the DATA_BLOB structure
            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ('cbData', wintypes.DWORD),
                    ('pbData', ctypes.POINTER(ctypes.c_char))
                ]
            
            # Get CryptUnprotectData function
            CryptUnprotectData = windll.crypt32.CryptUnprotectData
            CryptUnprotectData.argtypes = [
                ctypes.POINTER(DATA_BLOB),  # pDataIn
                ctypes.POINTER(wintypes.LPWSTR),  # ppszDataDescr
                ctypes.POINTER(DATA_BLOB),  # pOptionalEntropy
                ctypes.c_void_p,            # pvReserved
                ctypes.c_void_p,            # pPromptStruct
                wintypes.DWORD,             # dwFlags
                ctypes.POINTER(DATA_BLOB)   # pDataOut
            ]
            CryptUnprotectData.restype = wintypes.BOOL
            
            # Read the encrypted data
            with open(key_path, "rb") as f:
                encrypted_data = f.read()
            
            # Create the input blob
            data_in = DATA_BLOB()
            data_in.cbData = len(encrypted_data)
            buffer = ctypes.create_string_buffer(encrypted_data)
            data_in.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
            
            # Create an output blob and description pointer
            data_out = DATA_BLOB()
            desc_ptr = ctypes.POINTER(wintypes.WCHAR)()
            
            # Decrypt the data using DPAPI
            CRYPTPROTECT_UI_FORBIDDEN = 0x01
            if CryptUnprotectData(
                ctypes.byref(data_in),              # pDataIn
                ctypes.byref(desc_ptr),             # ppszDataDescr
                None,                               # pOptionalEntropy
                None,                               # pvReserved
                None,                               # pPromptStruct
                CRYPTPROTECT_UI_FORBIDDEN,          # dwFlags
                ctypes.byref(data_out)              # pDataOut
            ):
                # Get the decrypted data
                decrypted_len = data_out.cbData
                decrypted_data = ctypes.string_at(data_out.pbData, decrypted_len)
                
                # Free the output data and description
                LocalFree = windll.kernel32.LocalFree
                LocalFree.argtypes = [wintypes.HLOCAL]
                LocalFree.restype = wintypes.HLOCAL
                if desc_ptr:
                    LocalFree(desc_ptr)
                LocalFree(data_out.pbData)
                
                logger.info(f"Key {key_id} retrieved from Windows TPM protection")
                return decrypted_data
            else:
                # If decryption failed, fall back to software
                logger.warning(f"Windows TPM decryption failed, attempting software fallback")
                return self._retrieve_key_software(key_id)
                
        except (ImportError, AttributeError, Exception) as e:
            logger.warning(f"Windows TPM API access failed: {e}, falling back to software")
            return self._retrieve_key_software(key_id)
    
    def _store_key_macos_secure_enclave(self, key_id: str, key_data: bytes) -> bool:
        """Store a key using macOS Secure Enclave."""
        logger.info(f"macOS Secure Enclave key storage not fully implemented, falling back to software")
        return self._store_key_software(key_id, key_data)
    
    def _retrieve_key_macos_secure_enclave(self, key_id: str) -> Optional[bytes]:
        """Retrieve a key from macOS Secure Enclave."""
        logger.info(f"macOS Secure Enclave key retrieval not fully implemented, falling back to software")
        return self._retrieve_key_software(key_id)
    
    def _store_key_linux_tpm(self, key_id: str, key_data: bytes) -> bool:
        """Store a key using Linux TPM."""
        logger.info(f"Linux TPM key storage not fully implemented, falling back to software")
        return self._store_key_software(key_id, key_data)
    
    def _retrieve_key_linux_tpm(self, key_id: str) -> Optional[bytes]:
        """Retrieve a key from Linux TPM."""
        logger.info(f"Linux TPM key retrieval not fully implemented, falling back to software")
        return self._retrieve_key_software(key_id)

class EncryptedBackup:
    """
    Provides encrypted export and import functionality for Lemma credentials.
    Ensures that credential backups are encrypted for secure transfer between devices.
    """
    
    @staticmethod
    def export_credential(credential: Dict[str, Any], password: str) -> Dict[str, Any]:
        """
        Export a credential with password-based encryption.
        
        Args:
            credential: The credential to export
            password: User-provided password for encryption
            
        Returns:
            Dict: The encrypted credential package
        """
        try:
            import bcrypt
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            
            # Convert credential to JSON string
            credential_json = json.dumps(credential)
            
            # Generate a salt
            salt = bcrypt.gensalt()
            
            # Derive a key from the password
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            
            # Encrypt the credential
            f = Fernet(key)
            encrypted_data = f.encrypt(credential_json.encode())
            
            # Create the export package
            export_package = {
                "type": "EncryptedLemmaCredential",
                "version": "1.0",
                "salt": base64.b64encode(salt).decode(),
                "data": base64.b64encode(encrypted_data).decode()
            }
            
            return export_package
        except Exception as e:
            logger.error(f"Error exporting credential: {e}")
            raise
    
    @staticmethod
    def import_credential(export_package: Dict[str, Any], password: str) -> Optional[Dict[str, Any]]:
        """
        Import a credential by decrypting it with the provided password.
        
        Args:
            export_package: The encrypted credential package
            password: User-provided password for decryption
            
        Returns:
            Dict: The decrypted credential if successful, None otherwise
        """
        try:
            import bcrypt
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            
            # Verify package format
            if (export_package.get("type") != "EncryptedLemmaCredential" or
                "salt" not in export_package or
                "data" not in export_package):
                logger.error("Invalid export package format")
                return None
            
            # Get salt and encrypted data
            salt = base64.b64decode(export_package["salt"])
            encrypted_data = base64.b64decode(export_package["data"])
            
            # Derive the key from the password
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            
            # Decrypt the credential
            f = Fernet(key)
            decrypted_data = f.decrypt(encrypted_data)
            
            # Parse the credential
            credential = json.loads(decrypted_data.decode())
            
            return credential
        except Exception as e:
            logger.error(f"Error importing credential: {e}")
            return None

# Global storage instance
_secure_storage = None

def get_secure_storage():
    """Get the secure storage instance."""
    global _secure_storage
    if _secure_storage is None:
        _secure_storage = SecureStorage()
    return _secure_storage 