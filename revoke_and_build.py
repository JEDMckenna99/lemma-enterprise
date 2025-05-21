#!/usr/bin/env python3
"""
Revoke a credential and rebuild the cascade
This script is used to revoke a credential and then rebuild the cascade
"""

import os
import sys
import json
import time
import argparse
import logging
import random
import hashlib
import base64
from datetime import datetime
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption

# Add the current directory to the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import Lemma modules
from lemma.core.cascaded_bloom import (
    OPRFClient, 
    build_revocation_cascade, 
    create_cascade_bundle
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('cascade_builder.log')
    ]
)
logger = logging.getLogger('revoke_and_build')

def setup_storage_dirs(storage_dir):
    """Ensure all necessary storage directories exist."""
    # Main storage directory
    os.makedirs(storage_dir, exist_ok=True)
    
    # Revocation directories
    revocation_dir = os.path.join(storage_dir, 'revocation')
    os.makedirs(revocation_dir, exist_ok=True)
    
    # Cascades directory
    cascades_dir = os.path.join(revocation_dir, 'cascades')
    os.makedirs(cascades_dir, exist_ok=True)
    
    # Registry directory
    registry_dir = os.path.join(revocation_dir, 'registry')
    os.makedirs(registry_dir, exist_ok=True)
    
    return {
        'root': storage_dir,
        'revocation': revocation_dir,
        'cascades': cascades_dir,
        'registry': registry_dir
    }

def get_revocation_registry(storage_dir):
    """Load the revocation registry or create if it doesn't exist."""
    registry_file = os.path.join(storage_dir, 'revocation', 'registry.json')
    
    if os.path.exists(registry_file):
        with open(registry_file, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Corrupted registry file: {registry_file}, creating new")
    
    # Create a new empty registry
    registry = {}
    
    # Save the registry
    with open(registry_file, 'w') as f:
        json.dump(registry, f, indent=2)
        
    return registry

def save_revocation_registry(registry, storage_dir):
    """Save the revocation registry."""
    registry_file = os.path.join(storage_dir, 'revocation', 'registry.json')
    
    # Save the registry
    with open(registry_file, 'w') as f:
        json.dump(registry, f, indent=2)
        
    logger.info(f"Saved revocation registry to {registry_file}")

def revoke_credential(credential_id, issuer_id, registry):
    """Revoke a credential by adding it to the registry."""
    # Initialize issuer if not exists
    if issuer_id not in registry:
        registry[issuer_id] = {
            'revoked_ids': [],
            'last_updated': time.time()
        }
        
    # Check if already revoked
    if credential_id in registry[issuer_id]['revoked_ids']:
        logger.info(f"Credential {credential_id} already revoked by {issuer_id}")
        return False
        
    # Add to revoked list
    registry[issuer_id]['revoked_ids'].append(credential_id)
    registry[issuer_id]['last_updated'] = time.time()
    
    logger.info(f"Revoked credential {credential_id} issued by {issuer_id}")
    return True

def build_test_cascade(registry, storage_dir, epoch=None):
    """Build a cascade for testing purposes."""
    if epoch is None:
        epoch = datetime.now().strftime('%Y-%m-%d')
    
    # Create a list of all revoked credential IDs
    revoked_ids = []
    for issuer_id, issuer_data in registry.items():
        revoked_ids.extend(issuer_data.get('revoked_ids', []))
    
    # If no revoked credentials, create some for testing
    if not revoked_ids:
        logger.info("No revoked credentials found, creating test data")
        # Create 100 random revoked credentials
        issuer_id = "did:lemma:test"
        revoked_ids = [f"credential_{i}" for i in range(100)]
        
        # Add to registry
        if issuer_id not in registry:
            registry[issuer_id] = {
                'revoked_ids': [],
                'last_updated': time.time()
            }
        registry[issuer_id]['revoked_ids'] = revoked_ids
        registry[issuer_id]['last_updated'] = time.time()
        
        # Save the registry
        save_revocation_registry(registry, storage_dir)
    
    # Create OPRF client for evaluations
    oprf_client = OPRFClient()
    
    # Build the cascade
    logger.info(f"Building cascade with {len(revoked_ids)} revoked credentials")
    cascade = build_revocation_cascade(
        revoked_list=revoked_ids,
        oprf_client=oprf_client,
        issuer_id="did:lemma:test",
        cascade_levels=3,
        error_rate=0.01
    )
    
    # Create the bundle
    bundle = create_cascade_bundle(
        cascade=cascade,
        epoch=epoch,
        expiry_days=1
    )
    
    # Make sure the bundle has a proper signature for testing
    # Generate a key for signing that we can also verify
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Create a public key file for verification
    keys = {
        "ed25519_private": base64.b64encode(private_key.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption()
        )).decode('utf-8'),
        "ed25519_public": base64.b64encode(public_key.public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw
        )).decode('utf-8')
    }
    
    # Save the keys
    keys_dir = os.path.join(storage_dir, 'keys')
    os.makedirs(keys_dir, exist_ok=True)
    keys_file = os.path.join(keys_dir, 'cascade_keys.json')
    with open(keys_file, 'w') as f:
        json.dump(keys, f, indent=2)
    
    # Remove existing signature if any
    if "signature" in bundle:
        del bundle["signature"]
    
    # Sign the bundle
    bundle_json = json.dumps(bundle, sort_keys=True)
    signature_bytes = private_key.sign(bundle_json.encode())
    
    # Add the signature to the bundle
    bundle["signature"] = {
        "signature": base64.b64encode(signature_bytes).decode('utf-8'),
        "signer": "did:lemma:test#key-1",
        "created": datetime.now().isoformat()
    }
    
    # Save the bundle
    cascade_dir = os.path.join(storage_dir, 'revocation', 'cascades')
    os.makedirs(cascade_dir, exist_ok=True)
    
    # Save epoch-specific bundle
    bundle_file = os.path.join(cascade_dir, f'cascade_{epoch}.json')
    with open(bundle_file, 'w') as f:
        json.dump(bundle, f, indent=2)
    
    # Save latest bundle
    latest_file = os.path.join(cascade_dir, 'cascade_latest.json')
    with open(latest_file, 'w') as f:
        json.dump(bundle, f, indent=2)
    
    logger.info(f"Created and saved cascade bundle for epoch {epoch}")
    return bundle_file

def main():
    parser = argparse.ArgumentParser(description="Revoke a credential and rebuild the cascade")
    parser.add_argument("--credential", help="Credential ID to revoke")
    parser.add_argument("--issuer", default="did:lemma:test", help="Issuer ID")
    parser.add_argument("--storage", default="instance/data", help="Storage directory")
    parser.add_argument("--test", action="store_true", help="Build a test cascade")
    parser.add_argument("--epoch", help="Epoch for the cascade (default: today)")
    
    args = parser.parse_args()
    
    # Set up storage directories
    dirs = setup_storage_dirs(args.storage)
    
    # Load revocation registry
    registry = get_revocation_registry(args.storage)
    
    # Build test cascade if requested
    if args.test:
        build_test_cascade(registry, args.storage, args.epoch)
        return
    
    # Revoke credential if provided
    if args.credential:
        revoke_credential(args.credential, args.issuer, registry)
        save_revocation_registry(registry, args.storage)
    
    # Build cascade regardless (daily run case)
    build_test_cascade(registry, args.storage, args.epoch)

if __name__ == "__main__":
    main() 