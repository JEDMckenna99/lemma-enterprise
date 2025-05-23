"""
Large test data fixtures for Lemma Human Verification System.
Contains large datasets like cascade data that would otherwise clutter test files.
"""
import os
import json
from typing import Dict, Any, List, Optional


def get_sample_cascade_data() -> Dict[str, Any]:
    """
    Get sample cascade data for testing OPRF revocation functionality.
    
    Returns:
        Dict containing sample cascade bundle data
    """
    # This replaces the large cascade_2025-05-21.json file
    return {
        "version": "1.0",
        "epoch": "2025-05-21",
        "metadata": {
            "created": "2025-05-21T00:00:00Z",
            "expires": "2025-05-22T00:00:00Z",
            "issuer": "did:lemma:test",
            "revoked_count": 1000,
            "hash": "sample_hash_for_testing"
        },
        "cascade": {
            "levels": 3,
            "filters": [
                {
                    "level": 0,
                    "capacity": 1000000,
                    "error_rate": 0.02,
                    "bit_array": "sample_bit_array_base64_encoded",
                    "hash_functions": 7
                },
                {
                    "level": 1,
                    "capacity": 10000,
                    "error_rate": 0.001,
                    "bit_array": "sample_bit_array_level_1",
                    "hash_functions": 10
                },
                {
                    "level": 2,
                    "capacity": 100,
                    "error_rate": 0.0001,
                    "bit_array": "sample_bit_array_level_2",
                    "hash_functions": 13
                }
            ]
        },
        "signature": {
            "type": "Ed25519Signature2020",
            "created": "2025-05-21T00:00:00Z",
            "verificationMethod": "did:lemma:test#keys-1",
            "proofPurpose": "assertionMethod",
            "jws": "sample_signature_for_cascade_bundle"
        }
    }


def get_sample_large_credential_list() -> List[Dict[str, Any]]:
    """
    Get a large list of sample credentials for testing.
    
    Returns:
        List of sample credentials for testing pagination and performance
    """
    credentials = []
    for i in range(1000):  # Generate 1000 sample credentials
        credential = {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://lemmanetwork.org/contexts/lemma/v1"
            ],
            "id": f"vc_test_credential_{i:04d}",
            "type": ["VerifiableCredential", "LemmaCredential", "HumanCredential"],
            "issuer": "did:lemma:test",
            "issuanceDate": f"2024-01-{(i % 28) + 1:02d}T00:00:00Z",
            "expirationDate": f"2025-01-{(i % 28) + 1:02d}T00:00:00Z",
            "credentialSubject": {
                "id": f"did:user:test_user_{i:04d}",
                "type": "Person",
                "isHuman": True,
                "verifiedBy": "admin"
            },
            "proof": {
                "type": "Ed25519Signature2020",
                "created": f"2024-01-{(i % 28) + 1:02d}T00:00:00Z",
                "verificationMethod": "did:lemma:test#keys-1",
                "proofPurpose": "assertionMethod",
                "jws": f"test_signature_base64_{i:04d}"
            }
        }
        credentials.append(credential)
    
    return credentials


def get_sample_revocation_registry() -> Dict[str, Any]:
    """
    Get sample revocation registry data for testing.
    
    Returns:
        Dict containing sample revocation registry structure
    """
    return {
        "issuers": {
            "did:lemma:test": {
                "issuer_id": "did:lemma:test",
                "last_updated": "2024-01-01T00:00:00Z",
                "revoked_count": 50,
                "bitstring": "sample_revocation_bitstring_base64",
                "signature": "sample_signature_for_revocation_data"
            },
            "did:lemma:test2": {
                "issuer_id": "did:lemma:test2",
                "last_updated": "2024-01-02T00:00:00Z",
                "revoked_count": 25,
                "bitstring": "sample_revocation_bitstring_2_base64",
                "signature": "sample_signature_for_revocation_data_2"
            }
        },
        "metadata": {
            "created": "2024-01-01T00:00:00Z",
            "version": "1.0",
            "total_issuers": 2,
            "total_revocations": 75
        }
    }


def get_sample_p2p_peer_list() -> List[Dict[str, Any]]:
    """
    Get sample P2P peer list for testing network functionality.
    
    Returns:
        List of sample peer nodes
    """
    return [
        {
            "peer_id": "did:lemma:peer1",
            "url": "https://peer1.lemma.network",
            "status": "online",
            "features": ["revocation", "did_resolver", "zero_knowledge"],
            "network": "main",
            "last_seen": "2024-01-01T00:00:00Z",
            "reputation": 0.95
        },
        {
            "peer_id": "did:lemma:peer2", 
            "url": "https://peer2.lemma.network",
            "status": "online",
            "features": ["revocation", "hardware_security"],
            "network": "main",
            "last_seen": "2024-01-01T01:00:00Z",
            "reputation": 0.87
        },
        {
            "peer_id": "did:lemma:peer3",
            "url": "https://peer3.lemma.network",
            "status": "offline",
            "features": ["revocation"],
            "network": "test",
            "last_seen": "2024-01-01T00:30:00Z",
            "reputation": 0.72
        }
    ]


def get_malicious_payloads() -> Dict[str, List[str]]:
    """
    Get common malicious payloads for security testing.
    
    Returns:
        Dict containing different types of malicious payloads
    """
    return {
        "xss": [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//",
            "<svg onload=alert('xss')>",
            "data:text/html,<script>alert('xss')</script>"
        ],
        "sql_injection": [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM credentials --",
            "1; DELETE FROM credentials WHERE '1'='1",
            "1' OR 1=1#"
        ],
        "path_traversal": [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "....//....//....//etc/passwd",
            "/etc/passwd%00",
            "..%252f..%252f..%252fetc%252fpasswd"
        ],
        "command_injection": [
            "; cat /etc/passwd",
            "| whoami",
            "& net user",
            "`whoami`",
            "$(whoami)",
            "${7*7}",
            "{{7*7}}"
        ],
        "ldap_injection": [
            "*",
            "*)(&",
            "*))%00",
            "*()|%26'",
            "admin*)((|userPassword=*)",
            "*)(uid=*)"
        ]
    }


def get_performance_test_data() -> Dict[str, Any]:
    """
    Get data for performance testing.
    
    Returns:
        Dict containing various sizes of test data for performance testing
    """
    return {
        "small_payload": "A" * 1024,  # 1KB
        "medium_payload": "B" * (1024 * 100),  # 100KB
        "large_payload": "C" * (1024 * 1024),  # 1MB
        "extra_large_payload": "D" * (1024 * 1024 * 5),  # 5MB
        "concurrent_users": 100,
        "requests_per_user": 10,
        "max_response_time_ms": 5000
    }


def load_cascade_from_file() -> Optional[Dict[str, Any]]:
    """
    Load the actual cascade file if it exists, otherwise return sample data.
    This provides backward compatibility with existing large test data.
    
    Returns:
        Cascade data from file or sample data
    """
    # Check for the original cascade file
    cascade_file_path = os.path.join(
        os.path.dirname(__file__), 
        "..", 
        "..", 
        "test_data", 
        "cascade_2025-05-21.json"
    )
    
    if os.path.exists(cascade_file_path):
        try:
            with open(cascade_file_path, 'r') as f:
                return json.load(f)
        except Exception:
            # If file is corrupted or can't be read, return sample data
            pass
    
    # Return sample data if file doesn't exist or can't be read
    return get_sample_cascade_data()


def get_edge_case_credentials() -> List[Dict[str, Any]]:
    """
    Get credentials with edge case values for thorough testing.
    
    Returns:
        List of edge case credentials
    """
    return [
        # Minimal valid credential
        {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": "minimal-credential",
            "type": ["VerifiableCredential"],
            "issuer": "did:test:minimal",
            "credentialSubject": {"id": "did:user:minimal"}
        },
        
        # Credential with Unicode characters
        {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": "unicode-credential-🎯",
            "type": ["VerifiableCredential"],
            "issuer": "did:test:unicode",
            "credentialSubject": {
                "id": "did:user:unicode",
                "name": "Test User 测试用户 🌟",
                "description": "Credential with émojis and spéciål çhåråctërs"
            }
        },
        
        # Credential with very long values
        {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": "long-value-credential",
            "type": ["VerifiableCredential"],
            "issuer": "did:test:long",
            "credentialSubject": {
                "id": "did:user:long",
                "longField": "A" * 9999,  # Just under the 10K limit
                "description": "Testing maximum length values"
            }
        },
        
        # Credential with many nested objects
        {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "id": "nested-credential",
            "type": ["VerifiableCredential"],
            "issuer": "did:test:nested",
            "credentialSubject": {
                "id": "did:user:nested",
                "level1": {
                    "level2": {
                        "level3": {
                            "level4": {
                                "level5": {
                                    "data": "deep nested value"
                                }
                            }
                        }
                    }
                }
            }
        }
    ] 