param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$ProofFile = "",
    [string]$RuntimeId = "lemma-firewall-default",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8787,
    [string]$PolicyFile = "",
    [ValidateSet("starter_safe", "balanced", "advanced")]
    [string]$SecurityProfile = "starter_safe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$defaultProofPath = Join-Path $repoRoot ".lemma-proof.json"

if ([string]::IsNullOrWhiteSpace($ProofFile)) {
    $ProofFile = $defaultProofPath
}

if (-not (Test-Path $ProofFile)) {
    throw "Proof file not found at $ProofFile. Run scripts\setup_lemma_firewall_authz_seconds.ps1 first."
}

function Set-LocalFirstSecurityProfileEnv {
    param(
        [string]$Profile
    )
    $normalized = "starter_safe"
    if (-not [string]::IsNullOrWhiteSpace($Profile)) {
        $normalized = $Profile.ToLowerInvariant()
    }
    switch ($normalized) {
        "starter_safe" {
            $env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT = "1"
            $env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED = "1"
            $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = "critical"
            $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = "critical"
            $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = "0"
            $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = "0"
            $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = "0"
        }
        "balanced" {
            $env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT = "1"
            $env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED = "1"
            $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = "critical"
            $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = "critical"
            $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = "0"
            $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = "1"
            $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = "1"
        }
        default {
            $env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT = "1"
            $env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED = "1"
            $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = "high,critical"
            $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = "high,critical"
            $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = "0"
            $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = "1"
            $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = "1"
        }
    }
}

$env:LEMMA_BASE_URL = $LemmaUrl
$env:LEMMA_PROOF_FILE = $ProofFile
$env:LEMMA_FIREWALL_RUNTIME_ID = $RuntimeId
$env:LEMMA_FIREWALL_HOST = $BindHost
$env:LEMMA_FIREWALL_PORT = [string]$Port
Set-LocalFirstSecurityProfileEnv -Profile $SecurityProfile
if (-not [string]::IsNullOrWhiteSpace($PolicyFile)) {
    $env:LEMMA_FIREWALL_POLICY_FILE = $PolicyFile
}

Write-Host "Starting Lemma Firewall..."
Write-Host "  SECURITY_PROFILE=$SecurityProfile"
Write-Host "  LEMMA_BASE_URL=$LemmaUrl"
Write-Host "  LEMMA_PROOF_FILE=$ProofFile"
Write-Host "  LEMMA_FIREWALL_RUNTIME_ID=$RuntimeId"
Write-Host "  LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT=$($env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT)"
Write-Host "  LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED=$($env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED)"
Write-Host "  LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS=$($env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS)"
Write-Host "  LEMMA_FIREWALL_PROOF_REQUIRED_TIERS=$($env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS)"
Write-Host "  LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP=$($env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP)"
Write-Host "  LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL=$($env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL)"
Write-Host "  LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY=$($env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY)"
Write-Host "  URL=http://$BindHost`:$Port"
Write-Host ""
Write-Host "Health: http://$BindHost`:$Port/aim/health"
Write-Host "Policy: http://$BindHost`:$Port/aim/policy"

& python (Join-Path $repoRoot "scripts\lemma_firewall.py")
