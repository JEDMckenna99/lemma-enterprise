param(
    [string]$BaseUrl = "https://lemma.id",
    [string]$OutputDir = "ops/evidence/launch",
    [string]$ProofFixturePath = "",
    [string]$PlatformApiKey = "",
    [string]$AgentToken = "",
    [switch]$StrictScopePolicy,
    [switch]$RelaxedScopePolicy,
    [switch]$RequirePlatformApiKey,
    [double]$AuthzBudgetP95Ms = 5.0,
    [double]$E2EBudgetP95Ms = 0.0,
    [switch]$RequireAgentToken,
    [string]$Proof = "",
    [string]$ProofFile = "",
    [string]$PoP = "",
    [string]$PoPFile = "",
    [string]$CompatBearerSunsetUtc = "",
    [switch]$RequireCompatBearerSunset,
    [switch]$IncludePilotReleaseGates
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$smokeOut = Join-Path $OutputDir "$stamp-post-deploy-smoke.txt"
$cliApiRegressionOut = Join-Path $OutputDir "$stamp-post-deploy-cli-api-proof-regression.txt"
$scopePolicyOut = Join-Path $OutputDir "$stamp-post-deploy-auth-scope-policy.txt"
$contractOut = Join-Path $OutputDir "$stamp-post-deploy-auth-contract.txt"
$scopeMatrixOut = Join-Path $OutputDir "$stamp-post-deploy-auth-scope-matrix.txt"
$redisDegradeOut = Join-Path $OutputDir "$stamp-post-deploy-redis-degrade.txt"
$transportOut = Join-Path $OutputDir "$stamp-post-deploy-transport.txt"
$originOut = Join-Path $OutputDir "$stamp-post-deploy-origin.txt"
$latencyOut = Join-Path $OutputDir "$stamp-post-deploy-authz-latency.json"
$compatSunsetOut = Join-Path $OutputDir "$stamp-post-deploy-compat-sunset.txt"
$pilotGatesOut = Join-Path $OutputDir "$stamp-post-deploy-pilot-release-gates.txt"
$summaryOut = Join-Path $OutputDir "$stamp-post-deploy-summary.md"

Write-Output "Post-deploy launch gate run"
Write-Output "Base URL: $BaseUrl"
Write-Output "Timestamp: $(Get-Date -Format o)"
Write-Output ""

function Append-Line {
    param(
        [string]$Path,
        [string]$Text
    )
    $Text | Out-File -FilePath $Path -Encoding utf8 -Append
}

function Run-CurlCapture {
    param(
        [string[]]$CurlArgs,
        [string]$OutputPath,
        [string]$Label
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & curl.exe @CurlArgs 2>&1 | Out-File -FilePath $OutputPath -Append -Encoding utf8
        Append-Line -Path $OutputPath -Text "exit_code=$LASTEXITCODE"
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    # Don't hard-fail here because some probes intentionally fail (e.g. TLS1.1).
    Write-Output "$Label exit_code=$LASTEXITCODE"
}

# 0) MCP-free default CLI+API proof regression bundle
$cliApiArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "scripts/run_cli_api_proof_regression.ps1",
    "-LemmaUrl", $BaseUrl
)
if ($ProofFixturePath) {
    $cliApiArgs += @("-ProofFile", $ProofFixturePath, "-StrictProof")
}
powershell @cliApiArgs | Tee-Object -FilePath $cliApiRegressionOut

# 1) Core smoke checks
python scripts/launch_gate_smoke_ci.py | Tee-Object -FilePath $smokeOut

# 1a) Auth scope policy baseline generation + review
python scripts/generate_auth_scope_matrix.py | Tee-Object -FilePath $scopePolicyOut
$enforceStrictScopePolicy = $true
if ($RelaxedScopePolicy) {
    $enforceStrictScopePolicy = $false
} elseif ($PSBoundParameters.ContainsKey('StrictScopePolicy')) {
    $enforceStrictScopePolicy = [bool]$StrictScopePolicy
}

if ($enforceStrictScopePolicy) {
    python scripts/review_auth_scope_matrix.py --strict-state-changing | Tee-Object -FilePath $scopePolicyOut -Append
} else {
    python scripts/review_auth_scope_matrix.py | Tee-Object -FilePath $scopePolicyOut -Append
}

# 1b) Auth contract checks (baseline always, strict when fixture provided)
$env:LEMMA_BASE_URL = $BaseUrl
if ($ProofFixturePath) {
    $env:LEMMA_PROOF_FIXTURE_PATH = $ProofFixturePath
    $env:LEMMA_STRICT_POSITIVE = "1"
} else {
    Remove-Item Env:LEMMA_PROOF_FIXTURE_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:LEMMA_STRICT_POSITIVE -ErrorAction SilentlyContinue
}

# Prefer explicit param, then existing env var.
if ($PlatformApiKey) {
    $env:LEMMA_PLATFORM_API_KEY = $PlatformApiKey
}
python scripts/proof_exchange_contract_check.py | Tee-Object -FilePath $contractOut

# 1c) Scope matrix checks (requires platform API key)
if ($env:LEMMA_PLATFORM_API_KEY) {
    python scripts/auth_scope_matrix_check.py | Tee-Object -FilePath $scopeMatrixOut
} else {
    if ($RequirePlatformApiKey) {
        throw "Scope matrix check requires platform API key. Set -PlatformApiKey or LEMMA_PLATFORM_API_KEY."
    }
    "Scope matrix skipped: set -PlatformApiKey or LEMMA_PLATFORM_API_KEY" | Out-File -FilePath $scopeMatrixOut -Encoding utf8
    Write-Output "Scope matrix skipped (no platform API key provided)."
}

# 1d) Redis degradation resilience checks (must be non-500 structured health)
python scripts/redis_degrade_gate_check.py | Tee-Object -FilePath $redisDegradeOut

# 2) Transport/TLS checks
"Transport/TLS checks: $(Get-Date -Format o)" | Out-File -FilePath $transportOut -Encoding utf8
"# HTTP to HTTPS redirect" | Out-File -FilePath $transportOut -Append -Encoding utf8
Run-CurlCapture -CurlArgs @("-I","-L","--max-redirs","5",($BaseUrl -replace '^https://','http://')) -OutputPath $transportOut -Label "redirect_check"
"" | Out-File -FilePath $transportOut -Append -Encoding utf8
"# Force old TLS (expect failure if TLS1.2+ only)" | Out-File -FilePath $transportOut -Append -Encoding utf8
Run-CurlCapture -CurlArgs @("-I","--tls-max","1.1",$BaseUrl) -OutputPath $transportOut -Label "tls11_check"
"" | Out-File -FilePath $transportOut -Append -Encoding utf8
"# Force TLS1.2 (expect success)" | Out-File -FilePath $transportOut -Append -Encoding utf8
Run-CurlCapture -CurlArgs @("-I","--tlsv1.2",$BaseUrl) -OutputPath $transportOut -Label "tls12_check"

# 3) Origin/CORS checks (passkey auth begin)
"Origin/CORS checks: $(Get-Date -Format o)" | Out-File -FilePath $originOut -Encoding utf8
function TestReq($method,$url,$origin,$body){
    try {
        $headers=@{Origin=$origin}
        if($method -eq 'OPTIONS'){
            $headers['Access-Control-Request-Method']='POST'
            $headers['Access-Control-Request-Headers']='content-type'
        }

        if($method -eq 'POST'){
            $resp=Invoke-WebRequest -Uri $url -Method POST -Headers $headers -ContentType 'application/json' -Body $body -UseBasicParsing
        } elseif($method -eq 'OPTIONS'){
            $resp=Invoke-WebRequest -Uri $url -Method OPTIONS -Headers $headers -UseBasicParsing
        } else {
            $resp=Invoke-WebRequest -Uri $url -Method GET -Headers $headers -UseBasicParsing
        }

        Append-Line -Path $originOut -Text "$method $url Origin=$origin -> $($resp.StatusCode)"
        Append-Line -Path $originOut -Text "  ACAO=$($resp.Headers['Access-Control-Allow-Origin'])"
        Append-Line -Path $originOut -Text "  ACAC=$($resp.Headers['Access-Control-Allow-Credentials'])"
    } catch {
        $status='ERR'
        $acao=''
        $acac=''
        if($_.Exception.Response){
            $status=$_.Exception.Response.StatusCode.value__
            $acao=$_.Exception.Response.Headers['Access-Control-Allow-Origin']
            $acac=$_.Exception.Response.Headers['Access-Control-Allow-Credentials']
        }
        Append-Line -Path $originOut -Text "$method $url Origin=$origin -> $status"
        Append-Line -Path $originOut -Text "  ACAO=$acao"
        Append-Line -Path $originOut -Text "  ACAC=$acac"
    }
    Append-Line -Path $originOut -Text ""
}

$authnUrl="$BaseUrl/api/passkey/authenticate/begin"
TestReq 'OPTIONS' $authnUrl 'https://lemma.id' '{}'
TestReq 'OPTIONS' $authnUrl 'https://evil.example' '{}'
TestReq 'POST' $authnUrl 'https://lemma.id' '{}'
TestReq 'POST' $authnUrl 'https://evil.example' '{}'

# 3b) Authz + end-to-end latency budget gate (token or proof-native)
$effectiveAgentToken = if ($AgentToken) { $AgentToken } elseif ($env:LEMMA_AGENT_TOKEN) { $env:LEMMA_AGENT_TOKEN } else { "" }
$effectiveProof = if ($Proof) { $Proof } elseif ($env:LEMMA_PROOF) { $env:LEMMA_PROOF } else { "" }
$effectiveProofFile = if ($ProofFile) { $ProofFile } elseif ($env:LEMMA_PROOF_FILE) { $env:LEMMA_PROOF_FILE } else { "" }
$effectivePoP = if ($PoP) { $PoP } elseif ($env:LEMMA_POP) { $env:LEMMA_POP } else { "" }
$effectivePoPFile = if ($PoPFile) { $PoPFile } elseif ($env:LEMMA_POP_FILE) { $env:LEMMA_POP_FILE } else { "" }
if ($effectiveAgentToken -or $effectiveProof -or $effectiveProofFile) {
    $latencyArgs = @(
        "scripts/latency_budget_gate.py",
        "--base-url", $BaseUrl,
        "--authz-budget-p95-ms", $AuthzBudgetP95Ms,
        "--e2e-budget-p95-ms", $E2EBudgetP95Ms,
        "--output-path", $latencyOut
    )
    if ($effectiveAgentToken) { $latencyArgs += @("--agent-token", $effectiveAgentToken) }
    if ($effectiveProof) { $latencyArgs += @("--proof", $effectiveProof) }
    if ($effectiveProofFile) { $latencyArgs += @("--proof-file", $effectiveProofFile) }
    if ($effectivePoP) { $latencyArgs += @("--pop", $effectivePoP) }
    if ($effectivePoPFile) { $latencyArgs += @("--pop-file", $effectivePoPFile) }
    python @latencyArgs
} else {
    if ($RequireAgentToken) {
        throw "Latency gate requires auth input. Set -AgentToken or -Proof/-ProofFile."
    }
    '{"ok": false, "skipped": true, "reason": "no agent token or proof provided"}' | Out-File -FilePath $latencyOut -Encoding utf8
    Write-Output "Latency gate skipped (no agent token/proof provided)."
}

# 3c) Compatibility bearer sunset gate
$effectiveCompatSunset = if ($CompatBearerSunsetUtc) { $CompatBearerSunsetUtc } elseif ($env:LEMMA_COMPAT_BEARER_SUNSET_UTC) { $env:LEMMA_COMPAT_BEARER_SUNSET_UTC } else { "" }
if ($effectiveCompatSunset) {
    python scripts/check_compat_bearer_sunset.py --sunset-utc $effectiveCompatSunset | Tee-Object -FilePath $compatSunsetOut
} else {
    if ($RequireCompatBearerSunset) {
        throw "Compat bearer sunset gate requires -CompatBearerSunsetUtc or LEMMA_COMPAT_BEARER_SUNSET_UTC."
    }
    "Compat sunset skipped: set -CompatBearerSunsetUtc or LEMMA_COMPAT_BEARER_SUNSET_UTC" | Out-File -FilePath $compatSunsetOut -Encoding utf8
    Write-Output "Compat sunset gate skipped (no sunset configured)."
}

# 3d) Pilot release gates (optional, combines local + live checks)
if ($IncludePilotReleaseGates) {
    powershell -ExecutionPolicy Bypass -File "scripts/run_pilot_release_gates.ps1" `
        -BaseUrl $BaseUrl `
        -OutputDir $OutputDir `
        -RuntimeId "lemma-firewall-default" | Tee-Object -FilePath $pilotGatesOut
} else {
    "Pilot release gates skipped. Use -IncludePilotReleaseGates to run combined local+live pilot checks." | Out-File -FilePath $pilotGatesOut -Encoding utf8
}

# 4) Summary artifact
@"
# Post-Deploy Launch Gate Summary

- Base URL: $BaseUrl
- Timestamp: $(Get-Date -Format o)
- Artifacts:
  - $cliApiRegressionOut
  - $smokeOut
  - $scopePolicyOut
  - $contractOut
  - $scopeMatrixOut
  - $redisDegradeOut
  - $transportOut
  - $originOut
  - $latencyOut
  - $compatSunsetOut
  - $pilotGatesOut

## Pass Conditions

- Smoke script exits successfully.
- CLI+API proof regression bundle exits successfully.
- Scope matrix generation/review exits successfully.
- Auth contract script exits successfully (strict positive when fixture provided).
- Scope matrix script exits successfully when platform API key is provided.
- Redis degradation gate script exits successfully and `/api/health/check` is non-500 structured response.
- HTTP redirects to HTTPS, TLS <=1.1 handshake fails, TLS1.2 succeeds.
- Allowed origin returns ACAO for passkey auth begin, disallowed origin does not receive credentialed ACAO on POST.
- Latency gate passes authz p95 budget and optional end-to-end p95 budget when token is provided.
- Compatibility bearer sunset gate passes when sunset is configured.
- Optional: pilot release gate bundle passes when `-IncludePilotReleaseGates` is enabled.

## Manual Follow-up Required

- Browser/device matrix for passkey registration + algorithm capture.
- Revocation propagation test: revoke credential in deployed build, then verify deny behavior after sync.
"@ | Out-File -FilePath $summaryOut -Encoding utf8

Write-Output "Artifacts generated:"
Write-Output " - $cliApiRegressionOut"
Write-Output " - $smokeOut"
Write-Output " - $scopePolicyOut"
Write-Output " - $contractOut"
Write-Output " - $scopeMatrixOut"
Write-Output " - $redisDegradeOut"
Write-Output " - $transportOut"
Write-Output " - $originOut"
Write-Output " - $summaryOut"

