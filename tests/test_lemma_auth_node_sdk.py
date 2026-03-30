import json
import subprocess
from pathlib import Path


def _run_node_contract(required_site: str, verify_mode: str, credential: dict, required_scope: str, site_bound: bool):
    repo_root = Path(__file__).resolve().parents[1]
    sdk_path = repo_root / "sdk" / "node" / "lemma-auth-express" / "index.js"
    sdk_path_js = json.dumps(str(sdk_path).replace("\\", "/"))
    script = f"""
const {{ createLemmaAuth }} = require({sdk_path_js});
const verifyMode = {json.dumps(verify_mode)};
const auth = createLemmaAuth({{
  requiredSite: {json.dumps(required_site)},
  verifyCredential: async (_credential) => {{
    if (verifyMode === "throw") throw new Error("verifier unavailable");
    if (verifyMode === "invalid") return {{ valid: false, reason: "untrusted_issuer" }};
    return {{ valid: true }};
  }}
}});
const credential = {json.dumps(credential)};
const req = {{
  header: (name) => name === "X-Lemma-Credential" ? Buffer.from(JSON.stringify(credential)).toString("base64url") : undefined
}};
let output = null;
const res = {{
  statusCode: 200,
  status(code) {{ this.statusCode = code; return this; }},
  json(body) {{ output = {{ status: this.statusCode, body }}; return this; }}
}};
function finish(result) {{
  process.stdout.write(JSON.stringify(result));
}}
auth.attachPrincipal()(req, res, () => {{
  auth.requireLemma({{ scope: {json.dumps(required_scope)}, siteBound: {str(site_bound).lower()} }})(req, res, () => {{
    finish({{ status: 200, body: {{ ok: true }} }});
  }});
  if (output) finish(output);
}});
if (output) finish(output);
"""
    proc = subprocess.run(
        ["node", "-e", script],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout.strip())


def test_node_sdk_accepts_verified_credential():
    result = _run_node_contract(
        required_site="example.com",
        verify_mode="valid",
        credential={
            "id": "cred_1",
            "subject": "did:lemma:ppid_abc",
            "claims": {"scope": ["read"], "siteId": "example.com"},
        },
        required_scope="read",
        site_bound=True,
    )
    assert result["status"] == 200
    assert result["body"]["ok"] is True


def test_node_sdk_rejects_missing_scope_with_canonical_error_payload():
    result = _run_node_contract(
        required_site="example.com",
        verify_mode="valid",
        credential={
            "id": "cred_2",
            "subject": "did:lemma:ppid_abc",
            "claims": {"scope": ["read"], "siteId": "example.com"},
        },
        required_scope="admin",
        site_bound=True,
    )
    assert result["status"] == 403
    assert result["body"]["success"] is False
    assert result["body"]["error"] == "missing_scope"
    assert result["body"]["message"] == "Insufficient scope"


def test_node_sdk_handles_verifier_exception_as_verification_error():
    result = _run_node_contract(
        required_site="example.com",
        verify_mode="throw",
        credential={
            "id": "cred_3",
            "subject": "did:lemma:ppid_abc",
            "claims": {"scope": ["read"], "siteId": "example.com"},
        },
        required_scope="read",
        site_bound=True,
    )
    assert result["status"] == 401
    assert result["body"]["success"] is False
    assert result["body"]["error"] == "invalid_lemma:verification_error"
    assert result["body"]["message"] == "Credential verification failed"


def test_node_sdk_site_bound_uses_canonical_domain_matching():
    result = _run_node_contract(
        required_site="https://www.example.com",
        verify_mode="valid",
        credential={
            "id": "cred_4",
            "subject": "did:lemma:ppid_abc",
            "claims": {"scope": ["read"], "siteId": "example.com"},
        },
        required_scope="read",
        site_bound=True,
    )
    assert result["status"] == 200
    assert result["body"]["ok"] is True


def test_node_sdk_proof_contract_profile_parity():
    repo_root = Path(__file__).resolve().parents[1]
    sdk_path = repo_root / "sdk" / "node" / "lemma-auth-express" / "index.js"
    sdk_path_js = json.dumps(str(sdk_path).replace("\\", "/"))
    script = f"""
const {{ evaluateProofContract }} = require({sdk_path_js});
const decision = evaluateProofContract(
  {{
    profile: "authz_profile_v2",
    proof_id: "prf_1",
    root_grant_id: "root_1",
    policy_version: "v2-test",
    scope: ["read"]
  }},
  {{ requiredScope: "read" }}
);
process.stdout.write(JSON.stringify(decision));
"""
    proc = subprocess.run(
        ["node", "-e", script],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(proc.stdout.strip())
    assert result["decision"] == "allow"
    assert result["reason_code"] == "OK"
    assert result["profile"] == "authz_profile_v2"
