param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$RuntimeId = "lemma-firewall-default",
    [string]$AgentId = "main",
    [string]$WorkspaceId = "default",
    [string]$DisplayName = "Lemma Firewall Runtime",
    [ValidateSet("starter_safe", "balanced", "advanced")]
    [string]$SecurityProfile = "starter_safe",
    [string]$ProofFile = "",
    [string]$OutputDir = "",
    [switch]$SkipSetup,
    [switch]$SkipLive,
    [switch]$SkipUnit,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ProofFile)) {
    $ProofFile = Join-Path $repoRoot ".lemma-proof.json"
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $repoRoot "docs\launch-evidence"
}
if (-not (Test-Path $OutputDir)) {
    New-Item -Path $OutputDir -ItemType Directory -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$runId = "$timestamp-lemma-firewall-local-first-e2e"
$summaryPath = Join-Path $OutputDir "$runId-summary.md"
$jsonPath = Join-Path $OutputDir "$runId-results.json"

$steps = New-Object System.Collections.Generic.List[object]

function Invoke-Step {
    param(
        [string]$Name,
        [string]$Command,
        [string]$WorkingDirectory = ""
    )
    $startedAt = (Get-Date).ToString("o")
    Write-Host ""
    Write-Host "=== $Name ==="
    Write-Host $Command

    if ($DryRun) {
        $steps.Add([pscustomobject]@{
            name = $Name
            command = $Command
            started_at = $startedAt
            finished_at = (Get-Date).ToString("o")
            exit_code = 0
            dry_run = $true
            ok = $true
            output = @("[dry-run] skipped execution")
        })
        return
    }

    $oldLocation = Get-Location
    if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        Set-Location $WorkingDirectory
    }

    $outputLines = @()
    try {
        $outputLines = Invoke-Expression "$Command 2>&1" | ForEach-Object { "$_" }
        $exitCode = $LASTEXITCODE
        if ($null -eq $exitCode) {
            $exitCode = 0
        }
    } finally {
        if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
            Set-Location $oldLocation
        }
    }

    foreach ($line in $outputLines) {
        Write-Host $line
    }

    $ok = ($exitCode -eq 0)
    $steps.Add([pscustomobject]@{
        name = $Name
        command = $Command
        started_at = $startedAt
        finished_at = (Get-Date).ToString("o")
        exit_code = [int]$exitCode
        dry_run = $false
        ok = $ok
        output = $outputLines
    })

    if (-not $ok) {
        throw "Step failed: $Name (exit=$exitCode)"
    }
}

# Local-first daemon defaults for E2E intent.
$env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT = "1"
$env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED = "1"
if ($SecurityProfile -eq "starter_safe") {
    $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = "critical"
    $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = "critical"
    $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = "0"
    $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = "0"
    $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = "0"
} elseif ($SecurityProfile -eq "balanced") {
    $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = "critical"
    $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = "critical"
    $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = "0"
    $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = "1"
    $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = "1"
} else {
    $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = "high,critical"
    $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = "high,critical"
    $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = "0"
    $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = "1"
    $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = "1"
}

try {
    if (-not $SkipUnit) {
        Invoke-Step -Name "Unit: local-first firewall tests" -Command "pytest -q tests/test_lemma_firewall_local_first.py" -WorkingDirectory $repoRoot
        Invoke-Step -Name "Unit: authz v2 chain controls" -Command "pytest -q tests/test_authz_v2_controls.py -k ""proof_verifier or replay_contract or mode_policy or authz_control_plane""" -WorkingDirectory $repoRoot
        Invoke-Step -Name "Unit: Lemma Firewall authz CLI tests" -Command "pytest -q tests/test_lemma_cli.py -k ""setup_lemma_firewall or authz_latency""" -WorkingDirectory $repoRoot
    }

    if (-not $SkipSetup) {
        Invoke-Step -Name "Setup proof-first Lemma Firewall" -Command "powershell -ExecutionPolicy Bypass -File scripts/setup_lemma_firewall_authz_seconds.ps1 -LemmaUrl $LemmaUrl -RuntimeId $RuntimeId -AgentId $AgentId -WorkspaceId $WorkspaceId -RuntimeDisplayName `"$DisplayName`" -SecurityProfile $SecurityProfile" -WorkingDirectory $repoRoot
    }

    if (-not $SkipLive) {
        if (-not $DryRun -and -not (Test-Path $ProofFile)) {
            throw "Proof file not found: $ProofFile"
        }
        Invoke-Step -Name "Live: proof-first review" -Command "powershell -ExecutionPolicy Bypass -File scripts/run_lemma_firewall_review.ps1 -LemmaUrl $LemmaUrl -CredentialFile `"$ProofFile`"" -WorkingDirectory $repoRoot
        Invoke-Step -Name "Live: runtime kill-switch E2E" -Command "powershell -ExecutionPolicy Bypass -File scripts/run_agent_ops_e2e.ps1 -LemmaUrl $LemmaUrl -RuntimeId $RuntimeId -AgentId $AgentId -WorkspaceId $WorkspaceId -DisplayName `"$DisplayName`" -ProofFile `"$ProofFile`"" -WorkingDirectory $repoRoot
    }

    $status = "PASS"
} catch {
    $status = "FAIL"
    $errorText = "$_"
    Write-Host ""
    Write-Host "E2E failed: $errorText" -ForegroundColor Red
} finally {
    $result = [pscustomobject]@{
        run_id = $runId
        status = $status
        lemma_url = $LemmaUrl
        runtime_id = $RuntimeId
        proof_file = $ProofFile
        dry_run = [bool]$DryRun
        skip_setup = [bool]$SkipSetup
        skip_live = [bool]$SkipLive
        skip_unit = [bool]$SkipUnit
        env = @{
            SECURITY_PROFILE = $SecurityProfile
            LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT = $env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT
            LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED = $env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED
            LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS
            LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS
            LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP
            LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL
            LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY
        }
        steps = $steps
        generated_at = (Get-Date).ToString("o")
    }
    if ($status -eq "FAIL") {
        $result | Add-Member -MemberType NoteProperty -Name error -Value $errorText
    }

    $result | ConvertTo-Json -Depth 20 | Set-Content -Path $jsonPath

    $lines = @(
        "# Lemma Firewall Local-First E2E",
        "",
        "- Run ID: $runId",
        "- Status: **$status**",
        "- Lemma URL: $LemmaUrl",
        "- Runtime: $RuntimeId",
        "- Proof file: $ProofFile",
        "- Dry run: $($DryRun.IsPresent)",
        "",
        "## Steps"
    )
    foreach ($step in $steps) {
        $mark = if ($step.ok) { "PASS" } else { "FAIL" }
        $lines += "- [$mark] $($step.name) (exit=$($step.exit_code))"
    }
    if ($status -eq "FAIL") {
        $lines += ""
        $lines += "## Error"
        $lines += "- $errorText"
    }
    $lines += ""
    $lines += "## Artifact"
    $lines += "- JSON: $jsonPath"
    $lines | Set-Content -Path $summaryPath

    Write-Host ""
    Write-Host "Summary: $summaryPath"
    Write-Host "Results: $jsonPath"
}

if ($status -ne "PASS") {
    exit 1
}
exit 0
