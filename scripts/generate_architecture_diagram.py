#!/usr/bin/env python3
"""
Lemma Architecture Diagram Generator
=====================================
Generates architecture diagrams for nogic.dev and other visualization tools.

Outputs:
- Mermaid diagram (for nogic.dev, GitHub, documentation)
- JSON graph (for custom tooling)
- DOT/Graphviz (for image generation)

Usage:
    python scripts/generate_architecture_diagram.py
    python scripts/generate_architecture_diagram.py --format mermaid
    python scripts/generate_architecture_diagram.py --format json
    python scripts/generate_architecture_diagram.py --format dot
    python scripts/generate_architecture_diagram.py --format all
"""

import os
import json
import argparse
from datetime import datetime
from pathlib import Path

# =============================================================================
# ARCHITECTURE DEFINITION
# =============================================================================

NODES = {
    # Client-side components
    "wallet": {
        "id": "wallet",
        "label": "User Wallet",
        "type": "client",
        "description": "Browser IndexedDB storage for credentials and secrets",
        "files": ["static/js/lemma-wallet.js"],
        "stores": ["passkey", "secrets", "lemmas", "revocations", "session", "profiles"],
        "boundary": "client"
    },
    "crypto_wasm": {
        "id": "crypto_wasm",
        "label": "Crypto Engine (WASM)",
        "type": "library",
        "description": "Client-side Ed25519 verification and Bloom filter",
        "files": [
            "lemma-crypto/src/lib.rs",
            "lemma-crypto/src/minimal_core.rs",
            "lemma-crypto/src/bloom.rs"
        ],
        "boundary": "client"
    },
    
    # External parties
    "site": {
        "id": "site",
        "label": "Third-Party Site",
        "type": "external",
        "description": "Customer sites using Lemma SDK",
        "files": [],
        "boundary": "external"
    },
    "device_b": {
        "id": "device_b",
        "label": "New Device",
        "type": "client",
        "description": "Device being linked to existing wallet",
        "files": [],
        "boundary": "client"
    },
    
    # Server-side components
    "backend": {
        "id": "backend",
        "label": "Lemma Backend",
        "type": "server",
        "description": "Flask API server - auth, issuance, revocation",
        "files": [
            "app.py",
            "api/lemma_shield.py",
            "api/passkey_auth.py",
            "api/revocation_api.py",
            "api/services/wallet_service.py",
            "api/ppid.py",
            "api/wallet_transfer_session.py"
        ],
        "boundary": "server"
    },
    "postgres": {
        "id": "postgres",
        "label": "PostgreSQL",
        "type": "storage",
        "description": "Persistent storage for sites, passkeys, revocations",
        "files": ["api/database.py", "database_schema.sql"],
        "tables": ["passkeys", "sites", "revocation_list", "federated_sites"],
        "boundary": "server"
    },
    "redis": {
        "id": "redis",
        "label": "Redis",
        "type": "storage",
        "description": "Ephemeral storage for sessions and transfers",
        "files": [],
        "keys": ["transfer_session:{id}", "wallet_session:{id}"],
        "boundary": "server"
    }
}

EDGES = [
    # Authentication flow
    {
        "from": "wallet",
        "to": "backend",
        "label": "1. Passkey registration/auth",
        "flow": "auth",
        "data": "WebAuthn challenge/response",
        "privacy": "public_key only (private key never leaves device)"
    },
    {
        "from": "backend",
        "to": "wallet",
        "label": "2. Session token",
        "flow": "auth",
        "data": "JWT or session cookie",
        "privacy": "Identifies wallet_id, not user identity"
    },
    
    # PPID derivation (local)
    {
        "from": "site",
        "to": "crypto_wasm",
        "label": "7. Derive PPID",
        "flow": "ppid",
        "data": "HMAC(wallet_secret, site_domain)",
        "privacy": "LOCAL ONLY - no network call"
    },
    
    # Credential verification (local)
    {
        "from": "site",
        "to": "crypto_wasm",
        "label": "8. Verify credential",
        "flow": "verify",
        "data": "Ed25519 signature check",
        "privacy": "LOCAL ONLY - no network call"
    },
    {
        "from": "site",
        "to": "wallet",
        "label": "9. Check revocation",
        "flow": "verify",
        "data": "Bloom filter lookup",
        "privacy": "LOCAL ONLY - uses cached bloom filter"
    },
    
    # Revocation sync
    {
        "from": "wallet",
        "to": "backend",
        "label": "10. Fetch bloom filter",
        "flow": "revocation",
        "data": "GET /api/v1/revocation/bloom",
        "privacy": "Public data, no user identification"
    },
    {
        "from": "backend",
        "to": "postgres",
        "label": "11. Read revocation list",
        "flow": "revocation",
        "data": "SELECT from revocation_list",
        "privacy": "Server-side only"
    },
    {
        "from": "backend",
        "to": "wallet",
        "label": "12. Return bloom filter",
        "flow": "revocation",
        "data": "Bloom filter bytes + metadata",
        "privacy": "Public data, cached 1 hour"
    },
    
    # Device linking flow
    {
        "from": "wallet",
        "to": "backend",
        "label": "13. Create transfer session",
        "flow": "device_link",
        "data": "Encrypted wallet_secret",
        "privacy": "Encrypted, only recipient can decrypt"
    },
    {
        "from": "backend",
        "to": "redis",
        "label": "14. Store transfer session",
        "flow": "device_link",
        "data": "transfer_session:{id}",
        "privacy": "5 minute TTL, auto-deleted"
    },
    {
        "from": "device_b",
        "to": "backend",
        "label": "15. Poll transfer session",
        "flow": "device_link",
        "data": "GET /api/wallet/transfer/{id}",
        "privacy": "Requires session ID from QR/link"
    },
    {
        "from": "backend",
        "to": "device_b",
        "label": "16. Return encrypted wallet",
        "flow": "device_link",
        "data": "Encrypted wallet_secret",
        "privacy": "Decrypted locally on Device B"
    },
    
    # Backend to database
    {
        "from": "backend",
        "to": "postgres",
        "label": "Data persistence",
        "flow": "data",
        "data": "Sites, passkeys, revocations",
        "privacy": "Server-side storage"
    }
]

BOUNDARIES = [
    {
        "id": "client",
        "label": "Client-Side (Private)",
        "nodes": ["wallet", "crypto_wasm", "device_b"],
        "color": "#d4edda",
        "description": "Data stays on user's device"
    },
    {
        "id": "server",
        "label": "Lemma Backend",
        "nodes": ["backend", "postgres", "redis"],
        "color": "#cce5ff",
        "description": "Lemma infrastructure"
    },
    {
        "id": "external",
        "label": "Third-Party Sites",
        "nodes": ["site"],
        "color": "#fff3cd",
        "description": "Customer sites using SDK"
    }
]

DATA_STORAGE = {
    "client": {
        "location": "User's Browser (IndexedDB)",
        "data": {
            "wallet_secret": "32-byte hex - NEVER transmitted",
            "passkey": "WebAuthn credential ID + public key",
            "lemmas": "Signed credentials from issuers",
            "revocations": "Bloom filter cache",
            "session": "Auth state (unlocked_at, expires_at)"
        }
    },
    "server_postgres": {
        "location": "PostgreSQL",
        "data": {
            "passkeys": "credential_id, public_key (can verify, can't sign)",
            "sites": "domain, api_key, signing_key",
            "revocation_list": "revoked credential IDs"
        }
    },
    "server_redis": {
        "location": "Redis (Ephemeral)",
        "data": {
            "transfer_session": "Encrypted wallet (5 min TTL)",
            "wallet_session": "Unlock timestamp (24 hour TTL)"
        }
    }
}

PRIVACY_GUARANTEES = [
    {
        "property": "Pairwise Unlinkability",
        "mechanism": "PPID = HMAC(wallet_secret, site_domain)",
        "result": "Same user has different ID per site"
    },
    {
        "property": "No Central Tracking",
        "mechanism": "Verification is local (Ed25519 in WASM)",
        "result": "Lemma cannot see which sites user visits"
    },
    {
        "property": "Wallet Secret Protection",
        "mechanism": "Never leaves IndexedDB, derived from passkey",
        "result": "Only user can derive their PPIDs"
    },
    {
        "property": "Revocation Privacy",
        "mechanism": "Bloom filter (probabilistic, no queries)",
        "result": "Lemma cannot see revocation checks"
    }
]

# =============================================================================
# DIAGRAM GENERATORS
# =============================================================================

def generate_mermaid():
    """Generate Mermaid diagram syntax"""
    lines = [
        "%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#667eea'}}}%%",
        "flowchart TB",
        "",
        "    %% === BOUNDARIES ===",
    ]
    
    # Add subgraphs for boundaries
    for boundary in BOUNDARIES:
        lines.append(f"    subgraph {boundary['id']}[\"{boundary['label']}\"]")
        lines.append(f"        direction TB")
        for node_id in boundary['nodes']:
            node = NODES[node_id]
            shape_start, shape_end = _get_mermaid_shape(node['type'])
            lines.append(f"        {node_id}{shape_start}\"{node['label']}\"{shape_end}")
        lines.append("    end")
        lines.append("")
    
    lines.append("    %% === FLOWS ===")
    lines.append("")
    
    # Group edges by flow type
    flow_groups = {}
    for edge in EDGES:
        flow = edge.get('flow', 'default')
        if flow not in flow_groups:
            flow_groups[flow] = []
        flow_groups[flow].append(edge)
    
    for flow_type, edges in flow_groups.items():
        lines.append(f"    %% {flow_type.upper()} FLOW")
        for edge in edges:
            arrow = _get_mermaid_arrow(flow_type)
            label = edge['label'].replace('"', "'")
            lines.append(f"    {edge['from']} {arrow}|\"{label}\"| {edge['to']}")
        lines.append("")
    
    # Add styling
    lines.extend([
        "    %% === STYLING ===",
        "    classDef client fill:#d4edda,stroke:#28a745,stroke-width:2px",
        "    classDef server fill:#cce5ff,stroke:#007bff,stroke-width:2px",
        "    classDef storage fill:#e2e3e5,stroke:#6c757d,stroke-width:2px",
        "    classDef external fill:#fff3cd,stroke:#ffc107,stroke-width:2px",
        "",
        "    class wallet,crypto_wasm,device_b client",
        "    class backend server",
        "    class postgres,redis storage",
        "    class site external"
    ])
    
    return "\n".join(lines)


def _get_mermaid_shape(node_type):
    """Get Mermaid shape delimiters based on node type"""
    shapes = {
        "client": ("[", "]"),
        "server": ("[[", "]]"),
        "storage": ("[(", ")]"),
        "library": ("{{", "}}"),
        "external": ("([", "])"),
    }
    return shapes.get(node_type, ("[", "]"))


def _get_mermaid_arrow(flow_type):
    """Get arrow style based on flow type"""
    arrows = {
        "auth": "-->",
        "sso": "-.->",
        "ppid": "==>",
        "verify": "==>",
        "revocation": "-->",
        "device_link": "-.->",
        "data": "-->",
    }
    return arrows.get(flow_type, "-->")


def generate_json():
    """Generate JSON graph structure"""
    return {
        "meta": {
            "name": "Lemma Platform Architecture",
            "version": "1.0.0",
            "generated": datetime.now().isoformat(),
            "generator": "generate_architecture_diagram.py"
        },
        "nodes": list(NODES.values()),
        "edges": EDGES,
        "boundaries": BOUNDARIES,
        "data_storage": DATA_STORAGE,
        "privacy_guarantees": PRIVACY_GUARANTEES
    }


def generate_dot():
    """Generate DOT/Graphviz diagram"""
    lines = [
        'digraph LemmaArchitecture {',
        '    rankdir=TB;',
        '    node [fontname="Helvetica", fontsize=12];',
        '    edge [fontname="Helvetica", fontsize=10];',
        '    compound=true;',
        '',
    ]
    
    # Add subgraphs for boundaries
    for boundary in BOUNDARIES:
        lines.append(f'    subgraph cluster_{boundary["id"]} {{')
        lines.append(f'        label="{boundary["label"]}";')
        lines.append(f'        style=filled;')
        lines.append(f'        color="{boundary["color"]}";')
        lines.append(f'        fillcolor="{boundary["color"]}";')
        
        for node_id in boundary['nodes']:
            node = NODES[node_id]
            shape = _get_dot_shape(node['type'])
            lines.append(f'        {node_id} [label="{node["label"]}", shape={shape}];')
        
        lines.append('    }')
        lines.append('')
    
    # Add edges
    lines.append('    // Edges')
    for edge in EDGES:
        label = edge['label'].replace('"', '\\"')
        style = _get_dot_edge_style(edge.get('flow', 'default'))
        lines.append(f'    {edge["from"]} -> {edge["to"]} [label="{label}", {style}];')
    
    lines.append('}')
    return "\n".join(lines)


def _get_dot_shape(node_type):
    """Get DOT shape based on node type"""
    shapes = {
        "client": "box",
        "server": "box3d",
        "storage": "cylinder",
        "library": "component",
        "external": "ellipse",
    }
    return shapes.get(node_type, "box")


def _get_dot_edge_style(flow_type):
    """Get DOT edge style based on flow type"""
    styles = {
        "auth": 'color="blue"',
        "sso": 'style="dashed", color="green"',
        "ppid": 'color="purple", penwidth=2',
        "verify": 'color="purple", penwidth=2',
        "revocation": 'color="orange"',
        "device_link": 'style="dashed", color="red"',
        "data": 'color="gray"',
    }
    return styles.get(flow_type, 'color="black"')


def generate_markdown_docs():
    """Generate markdown documentation of the architecture"""
    lines = [
        "# Lemma Platform Architecture",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "## Components",
        "",
        "| Component | Type | Description | Files |",
        "|-----------|------|-------------|-------|",
    ]
    
    for node in NODES.values():
        files = ", ".join([f"`{f}`" for f in node.get('files', [])[:2]]) or "-"
        lines.append(f"| **{node['label']}** | {node['type']} | {node['description']} | {files} |")
    
    lines.extend([
        "",
        "## Data Flows",
        "",
    ])
    
    # Group by flow type
    flow_groups = {}
    for edge in EDGES:
        flow = edge.get('flow', 'default')
        if flow not in flow_groups:
            flow_groups[flow] = []
        flow_groups[flow].append(edge)
    
    for flow_type, edges in flow_groups.items():
        lines.append(f"### {flow_type.replace('_', ' ').title()} Flow")
        lines.append("")
        lines.append("| Step | From | To | Data | Privacy |")
        lines.append("|------|------|-----|------|---------|")
        for edge in edges:
            lines.append(f"| {edge['label']} | {edge['from']} | {edge['to']} | {edge.get('data', '-')} | {edge.get('privacy', '-')} |")
        lines.append("")
    
    lines.extend([
        "## Data Storage",
        "",
    ])
    
    for location, info in DATA_STORAGE.items():
        lines.append(f"### {info['location']}")
        lines.append("")
        lines.append("| Data | Description |")
        lines.append("|------|-------------|")
        for key, desc in info['data'].items():
            lines.append(f"| `{key}` | {desc} |")
        lines.append("")
    
    lines.extend([
        "## Privacy Guarantees",
        "",
        "| Property | Mechanism | Result |",
        "|----------|-----------|--------|",
    ])
    
    for guarantee in PRIVACY_GUARANTEES:
        lines.append(f"| **{guarantee['property']}** | {guarantee['mechanism']} | {guarantee['result']} |")
    
    return "\n".join(lines)


def generate_c4_dsl():
    """Generate C4 model DSL (Structurizr compatible)"""
    lines = [
        "workspace {",
        "    model {",
        "        user = person \"User\" \"A user with a Lemma wallet\"",
        "        ",
    ]
    
    # Software systems
    lines.extend([
        "        lemmaSystem = softwareSystem \"Lemma Platform\" {",
        "            wallet = container \"User Wallet\" \"IndexedDB\" \"Browser Storage\" {",
        "                tags \"Client\"",
        "            }",
        "            backend = container \"Lemma Backend\" \"Flask API\" \"Python\" {",
        "                tags \"Server\"",
        "            }",
        "            postgres = container \"PostgreSQL\" \"Persistent Storage\" \"Database\" {",
        "                tags \"Storage\"",
        "            }",
        "            redis = container \"Redis\" \"Session Storage\" \"Cache\" {",
        "                tags \"Storage\"",
        "            }",
        "        }",
        "        ",
        "        thirdPartySite = softwareSystem \"Third-Party Site\" \"Customer site using Lemma SDK\" {",
        "            tags \"External\"",
        "        }",
        "        ",
    ])
    
    # Relationships
    lines.extend([
        "        # Relationships",
        "        user -> wallet \"Unlocks via passkey\"",
        "        wallet -> backend \"Passkey auth\"",
        "        wallet -> backend \"Syncs revocation bloom\"",
        "        backend -> postgres \"Reads/writes\"",
        "        backend -> redis \"Session storage\"",
        "    }",
        "    ",
        "    views {",
        "        systemContext lemmaSystem {",
        "            include *",
        "            autolayout lr",
        "        }",
        "        container lemmaSystem {",
        "            include *",
        "            autolayout lr",
        "        }",
        "    }",
        "}",
    ])
    
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate Lemma architecture diagrams")
    parser.add_argument(
        "--format", 
        choices=["mermaid", "json", "dot", "markdown", "c4", "all"],
        default="all",
        help="Output format"
    )
    parser.add_argument(
        "--output-dir",
        default="docs/architecture",
        help="Output directory"
    )
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    formats_to_generate = {
        "mermaid": ("architecture.mmd", generate_mermaid),
        "json": ("architecture.json", lambda: json.dumps(generate_json(), indent=2)),
        "dot": ("architecture.dot", generate_dot),
        "markdown": ("ARCHITECTURE.md", generate_markdown_docs),
        "c4": ("architecture.dsl", generate_c4_dsl),
    }
    
    if args.format == "all":
        selected = formats_to_generate.keys()
    else:
        selected = [args.format]
    
    for fmt in selected:
        filename, generator = formats_to_generate[fmt]
        output_path = output_dir / filename
        content = generator()
        output_path.write_text(content, encoding="utf-8")
        print(f"Generated: {output_path}")
    
    print(f"\nAll diagrams saved to: {output_dir}/")
    print("\nUsage:")
    print("  - Mermaid (.mmd): Paste into nogic.dev, GitHub, or mermaid.live")
    print("  - JSON (.json): Import into custom tooling or nogic.dev")
    print("  - DOT (.dot): Generate images with 'dot -Tpng architecture.dot -o architecture.png'")
    print("  - Markdown (.md): Documentation for README or docs site")
    print("  - C4 DSL (.dsl): Import into Structurizr")


if __name__ == "__main__":
    main()
