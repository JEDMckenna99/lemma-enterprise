# Lemma Enterprise Revocation System

This document explains how the credential revocation system works in Lemma Enterprise.

## Overview

The revocation system is designed to:

1. Allow issuing authorities to revoke credentials
2. Provide privacy-preserving verification of revocation status
3. Work offline for verifiers (no online checks needed during verification)
4. Scale to millions of revoked credentials with small storage requirements

## System Components

### 1. Revocation Registry

The revocation registry is a database of all revoked credentials, stored in:

```
instance/data/revocation/registry.json
```

This contains lists of revoked credential IDs by issuer. The registry is used to:

- Add newly revoked credentials
- Generate the cascaded bloom filter bundles

### 2. Cascaded Bloom Filters

Cascaded Bloom filters provide a privacy-preserving way to check if a credential is revoked without revealing which credential is being checked.

Key benefits:
- Privacy-preserving: The verifier doesn't learn which credential is being verified
- Compact: Can represent millions of revocations in ~100KB
- False positives but no false negatives: A credential might be incorrectly marked as revoked, but a revoked credential will never be marked as valid

### 3. OPRF (Oblivious Pseudorandom Function)

The OPRF service allows credential IDs to be blindly evaluated, providing privacy:

- Credential holders can get a blinded proof of status without revealing their credential ID
- Verifiers can check revocation status without connecting to a central service

## How It Works

### Revoking a Credential

When a credential needs to be revoked:

1. The issuer adds the credential ID to the revocation registry
2. The cascade builder script (`revoke_and_build.py`) is run to:
   - Load all revoked credential IDs
   - Create OPRF evaluations for each revoked ID
   - Build a cascaded bloom filter containing all revocations
   - Create a signed cascade bundle
   - Save the bundle with the current date as the epoch

### Serving the Cascade

The system serves cascade bundles through these endpoints:

- `/api/cascade/<epoch>` - Get a specific epoch's cascade
- `/api/cascades` - List all available cascades
- `/cascade/<epoch>` - Direct route for testing

### Verification Process

When verifying a credential:

1. The verifier has a cached copy of the cascade bundle
2. The credential holder generates a non-revocation witness (using OPRF)
3. The verifier checks the witness against the cascade
4. If the credential is not in the cascade, it's valid
5. If the credential is in the cascade, it's revoked

## Deployment Instructions

### 1. Setting Up the Directory Structure

First, ensure the revocation directory structure exists:

```
mkdir -p instance/data/revocation/cascades
mkdir -p instance/data/revocation/registry
```

### 2. Creating the Revocation Registry

Initialize the revocation registry:

```
{
  "did:lemma:enterprise": {
    "issuer_id": "did:lemma:enterprise",
    "last_updated": 1716300150,
    "revoked_count": 0,
    "revoked_ids": [],
    "bitstring": "",
    "bitstring_size": 10000,
    "num_hashes": 5
  }
}
```

### 3. Scheduling Daily Cascade Builds

Set up a Windows scheduled task to run `daily_cascade_build.bat` every day at midnight:

1. Open Task Scheduler
2. Create a new task
3. Set the trigger to daily at 12:00 AM
4. Set the action to run `daily_cascade_build.bat`
5. Configure additional settings as needed (run whether user is logged in or not)

### 4. Testing the System

To test the revocation system:

```
python test_revocation.py
```

This will:
1. Revoke a test credential
2. Build a cascade
3. Verify that the credential is correctly marked as revoked

## Troubleshooting

### Cascade Not Found

If tests report "cascade not found" errors:

1. Check that the cascade files exist in `instance/data/revocation/cascades/`
2. Verify that the cascade files for the current date exist
3. Run `python revoke_and_build.py` to generate a new cascade

### OPRF Service Issues

If you encounter OPRF service errors:

1. Ensure your local OPRF service is running
2. Check that the `oprf_server_url` in `config.json` is correct
3. Verify network connectivity to the OPRF service

## Offline Operation

The revocation system is designed to work offline:

1. Cascade bundles are downloaded and cached by verifiers
2. Verification can happen without an internet connection
3. Periodic updates (e.g., daily) keep the verification data current

This makes the system suitable for scenarios with intermittent connectivity while maintaining strong security guarantees. 