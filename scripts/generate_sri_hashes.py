#!/usr/bin/env python3
"""
Generate Subresource Integrity (SRI) hashes for Lemma SDK files.

SRI allows browsers to verify that fetched resources haven't been tampered with.
Customers can include these hashes when loading the SDK:

<script src="https://lemma.id/sdk/lemma-wallet.js"
        integrity="sha384-<hash>"
        crossorigin="anonymous"></script>

Usage:
    python scripts/generate_sri_hashes.py
    python scripts/generate_sri_hashes.py --output json
    python scripts/generate_sri_hashes.py --file static/js/lemma-wallet.js
"""

import hashlib
import base64
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Files to generate hashes for
SDK_FILES = [
    'static/js/lemma-wallet.js',
    'static/js/lemma-shield.js',
]

# Optional CDN files
CDN_FILES = [
    'cdn/dist/js/lemma-shield-inline.min.js',
]


def generate_sri_hash(file_path: str, algorithm: str = 'sha384') -> dict:
    """
    Generate SRI hash for a file.
    
    Args:
        file_path: Path to the file
        algorithm: Hash algorithm (sha256, sha384, sha512)
    
    Returns:
        dict with hash info or None if file doesn't exist
    """
    path = Path(file_path)
    
    if not path.exists():
        return None
    
    # Read file content
    with open(path, 'rb') as f:
        content = f.read()
    
    # Generate hash
    if algorithm == 'sha256':
        hash_obj = hashlib.sha256(content)
    elif algorithm == 'sha384':
        hash_obj = hashlib.sha384(content)
    elif algorithm == 'sha512':
        hash_obj = hashlib.sha512(content)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    # Base64 encode
    hash_base64 = base64.b64encode(hash_obj.digest()).decode('utf-8')
    
    # SRI format
    sri_hash = f"{algorithm}-{hash_base64}"
    
    # Get file info
    stat = path.stat()
    
    return {
        'file': str(path),
        'algorithm': algorithm,
        'hash': sri_hash,
        'size_bytes': stat.st_size,
        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def generate_all_hashes(files: list = None, algorithm: str = 'sha384') -> dict:
    """
    Generate SRI hashes for all SDK files.
    
    Returns:
        dict with all file hashes and metadata
    """
    if files is None:
        files = SDK_FILES + CDN_FILES
    
    results = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'algorithm': algorithm,
        'files': {}
    }
    
    for file_path in files:
        hash_info = generate_sri_hash(file_path, algorithm)
        if hash_info:
            # Use relative path as key
            key = file_path.replace('static/', '').replace('cdn/dist/', 'cdn/')
            results['files'][key] = hash_info
    
    return results


def get_sdk_version() -> str:
    """Extract SDK version from lemma-wallet.js"""
    try:
        with open('static/js/lemma-wallet.js', 'r', encoding='utf-8') as f:
            content = f.read(5000)  # Version is near the top
        
        # Find version string - handle optional comment after
        import re
        match = re.search(r"static VERSION\s*=\s*['\"]([^'\"]+)['\"]", content)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Warning: Could not extract version: {e}", file=sys.stderr)
    
    return 'unknown'


def print_usage_example(hash_info: dict):
    """Print HTML usage example for a file."""
    if not hash_info:
        return
    
    file_path = hash_info['file']
    sri_hash = hash_info['hash']
    
    # Determine the URL
    if 'lemma-wallet.js' in file_path:
        url = 'https://lemma.id/sdk/lemma-wallet.js'
    elif 'lemma-shield.js' in file_path:
        url = 'https://lemma.id/sdk/lemma-shield.js'
    else:
        url = f'https://lemma.id/{file_path}'
    
    print(f"""
<!-- {file_path} -->
<script src="{url}"
        integrity="{sri_hash}"
        crossorigin="anonymous"></script>
""")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate SRI hashes for Lemma SDK')
    parser.add_argument('--output', choices=['text', 'json', 'html'], default='text',
                       help='Output format')
    parser.add_argument('--file', type=str, help='Generate hash for specific file only')
    parser.add_argument('--algorithm', choices=['sha256', 'sha384', 'sha512'], 
                       default='sha384', help='Hash algorithm')
    parser.add_argument('--save', type=str, help='Save hashes to file')
    
    args = parser.parse_args()
    
    # Get SDK version
    version = get_sdk_version()
    
    if args.file:
        # Single file mode
        hash_info = generate_sri_hash(args.file, args.algorithm)
        if not hash_info:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        
        if args.output == 'json':
            print(json.dumps(hash_info, indent=2))
        elif args.output == 'html':
            print_usage_example(hash_info)
        else:
            print(f"File: {hash_info['file']}")
            print(f"SRI:  {hash_info['hash']}")
            print(f"Size: {hash_info['size_bytes']} bytes")
    else:
        # All files mode
        results = generate_all_hashes(algorithm=args.algorithm)
        results['sdk_version'] = version
        
        if args.output == 'json':
            output = json.dumps(results, indent=2)
            print(output)
            
            if args.save:
                with open(args.save, 'w') as f:
                    f.write(output)
                print(f"\nSaved to {args.save}", file=sys.stderr)
        
        elif args.output == 'html':
            print(f"<!-- Lemma SDK v{version} - SRI Hashes -->")
            print(f"<!-- Generated: {results['generated_at']} -->")
            for key, hash_info in results['files'].items():
                print_usage_example(hash_info)
        
        else:
            print(f"Lemma SDK v{version} - SRI Hashes")
            print(f"Generated: {results['generated_at']}")
            print(f"Algorithm: {args.algorithm}")
            print("-" * 60)
            
            for key, hash_info in results['files'].items():
                print(f"\n{key}:")
                print(f"  SRI:  {hash_info['hash']}")
                print(f"  Size: {hash_info['size_bytes']} bytes")
            
            print("\n" + "=" * 60)
            print("USAGE EXAMPLE:")
            
            # Show main SDK usage
            main_hash = results['files'].get('js/lemma-wallet.js')
            if main_hash:
                print_usage_example(main_hash)


if __name__ == '__main__':
    main()
