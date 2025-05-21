#!/usr/bin/env python3
"""
Cascade Builder for Lemma Revocation System

This script builds and publishes the OPRF-cascaded Bloom filter for revoked credentials.
It is designed to be run as a scheduled task, e.g., daily at midnight.

Usage:
    python build_cascade.py [--config CONFIG_FILE] [--force]

Options:
    --config CONFIG_FILE    Path to the configuration file (default: config.json)
    --force                 Force rebuild even if no new revocations
"""

import os
import json
import time
import logging
import argparse
import hashlib
import sys
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

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
logger = logging.getLogger('cascade_builder')

def load_revoked_credentials(storage_dir):
    """
    Load the list of revoked credentials from storage.
    
    Args:
        storage_dir: Directory where the revocation data is stored
        
    Returns:
        list: List of revoked credential IDs
    """
    try:
        # Revocation registry file should be in storage_dir/revocation/registry.json
        registry_file = os.path.join(storage_dir, 'revocation', 'registry.json')
        
        if not os.path.exists(registry_file):
            logger.warning(f"Revocation registry file not found: {registry_file}")
            return []
            
        with open(registry_file, 'r') as f:
            data = json.load(f)
            
        # Extract all revoked credential IDs from all issuers
        revoked_ids = []
        for issuer_id, issuer_data in data.items():
            if 'revoked_ids' in issuer_data:
                revoked_ids.extend(issuer_data['revoked_ids'])
        
        logger.info(f"Loaded {len(revoked_ids)} revoked credentials from registry")
        return revoked_ids
    except Exception as e:
        logger.error(f"Error loading revoked credentials: {e}")
        return []

def get_current_epoch():
    """Get the current epoch string (YYYY-MM-DD)."""
    return datetime.now().strftime('%Y-%m-%d')

def save_cascade_bundle(bundle, storage_dir, epoch):
    """
    Save the cascade bundle to storage.
    
    Args:
        bundle: The cascade bundle to save
        storage_dir: Directory where the cascade bundles are stored
        epoch: The epoch for this bundle
        
    Returns:
        str: Path to the saved bundle file
    """
    try:
        # Ensure the cascade directory exists
        cascade_dir = os.path.join(storage_dir, 'revocation', 'cascades')
        os.makedirs(cascade_dir, exist_ok=True)
        
        # Path for the new bundle
        bundle_file = os.path.join(cascade_dir, f'cascade_{epoch}.json')
        
        # Save the bundle
        with open(bundle_file, 'w') as f:
            json.dump(bundle, f, indent=2)
            
        # Also save as "latest" for convenience
        latest_file = os.path.join(cascade_dir, 'cascade_latest.json')
        with open(latest_file, 'w') as f:
            json.dump(bundle, f, indent=2)
            
        logger.info(f"Saved cascade bundle to {bundle_file}")
        return bundle_file
    except Exception as e:
        logger.error(f"Error saving cascade bundle: {e}")
        return None

def prune_old_cascades(storage_dir, keep_days=7):
    """
    Prune old cascade bundles, keeping only the specified number of days.
    
    Args:
        storage_dir: Directory where the cascade bundles are stored
        keep_days: Number of days of cascades to keep
        
    Returns:
        int: Number of pruned cascade bundles
    """
    try:
        # Cascade bundles directory
        cascade_dir = os.path.join(storage_dir, 'revocation', 'cascades')
        
        if not os.path.exists(cascade_dir):
            return 0
            
        # Current time
        now = datetime.now()
        
        # Find all cascade bundle files
        pruned_count = 0
        for filename in os.listdir(cascade_dir):
            if not filename.startswith('cascade_') or not filename.endswith('.json'):
                continue
                
            # Skip "latest"
            if filename == 'cascade_latest.json':
                continue
                
            # Get file path
            file_path = os.path.join(cascade_dir, filename)
            
            # Get file age
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            age_days = (now - file_time).days
            
            # Delete if older than keep_days
            if age_days > keep_days:
                os.remove(file_path)
                pruned_count += 1
                
        if pruned_count > 0:
            logger.info(f"Pruned {pruned_count} old cascade bundles")
            
        return pruned_count
    except Exception as e:
        logger.error(f"Error pruning old cascades: {e}")
        return 0

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Build and publish OPRF-cascaded Bloom filter")
    parser.add_argument("--config", default="config.json", help="Path to the configuration file")
    parser.add_argument("--force", action="store_true", help="Force rebuild even if no new revocations")
    args = parser.parse_args()
    
    # Load configuration
    try:
        with open(args.config, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        config = {}
        
    # Configuration values
    storage_dir = config.get('storage_dir', '.lemma_enterprise')
    oprf_server_url = config.get('oprf_server_url', 'http://localhost:8080')
    cascade_levels = config.get('cascade_levels', 3)
    error_rate = config.get('error_rate', 0.02)
    issuer_id = config.get('issuer_id', 'did:lemma:default')
    keep_days = config.get('keep_days', 7)
    
    # Get current epoch
    current_epoch = get_current_epoch()
    
    # Check if we already have a cascade for this epoch
    cascade_file = os.path.join(storage_dir, 'revocation', 'cascades', f'cascade_{current_epoch}.json')
    if os.path.exists(cascade_file) and not args.force:
        logger.info(f"Cascade for epoch {current_epoch} already exists, skipping rebuild")
        return
        
    # Load revoked credentials
    revoked_credentials = load_revoked_credentials(storage_dir)
    
    if not revoked_credentials and not args.force:
        logger.info("No revoked credentials found, skipping cascade build")
        return
    
    # Initialize OPRF client
    oprf_client = OPRFClient(server_url=oprf_server_url)
    
    # Build the cascade
    logger.info(f"Building cascade with {len(revoked_credentials)} revoked credentials")
    cascade = build_revocation_cascade(
        revoked_list=revoked_credentials,
        oprf_client=oprf_client,
        issuer_id=issuer_id,
        cascade_levels=cascade_levels,
        error_rate=error_rate
    )
    
    # Create the bundle
    bundle = create_cascade_bundle(
        cascade=cascade,
        epoch=current_epoch,
        expiry_days=1
    )
    
    # Save the bundle
    save_cascade_bundle(bundle, storage_dir, current_epoch)
    
    # Prune old cascades
    prune_old_cascades(storage_dir, keep_days)
    
    logger.info("Cascade build and publish completed successfully")

if __name__ == "__main__":
    main() 