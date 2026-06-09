param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$ProofFile = "",
    [switch]$StrictProof,
    [switch]$RequireLiveCliAuth
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$cliPath = Join-Path $repoRoot "scripts\lemma_cli.py"
$proofContractPath = Join-Path $repoRoot "scripts\proof_exchange_contract_check.py"
$smokePath = Join-Path $repoRoot "scripts\launch_gate_smoke_ci.py"

if (-not (Test-Path $cliPath)) {
    throw "Missing CLI script: $cliPath"
}
if (-not (Test-Path $proofContractPath)) {
    throw "Missing proof contract script: $proofContractPath"
}
if (-not (Test-Path $smokePath)) {
    throw "Missing launch-gate smoke script: $smokePath"
}

if ([string]::IsNullOrWhiteSpace($ProofFile)) {
    $defaultProof = Join-Path $repoRoot ".lemma-proof.json"
    $inCi = $env:GITHUB_ACTIONS -eq "true" -or $env:CI -eq "true"
    if (-not $inCi -and (Test-Path $defaultProof)) {
        $ProofFile = $defaultProof
    }
}

function Invoke-PythonChecked {
    param(
        [string[]]$CommandArgs,
        [string]$StepName
    )
    Write-Host "[$StepName] python $($CommandArgs -join ' ')"
    & python @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed with exit code $LASTEXITCODE"
    }
}

Write-Host "== CLI + API Proof Regression =="
Write-Host "Lemma URL: $LemmaUrl"
if ([string]::IsNullOrWhiteSpace($ProofFile)) {
    Write-Host "Proof file: <none>"
} else {
    Write-Host "Proof file: $ProofFile"
}
Write-Host ""

if ($RequireLiveCliAuth.IsPresent) {
    Invoke-PythonChecked -StepName "1/4 session-status (live)" -CommandArgs @(
        $cliPath, "session", "status",
        "--api-base", $LemmaUrl,
        "--json"
    )

    Invoke-PythonChecked -StepName "2/4 auth-status (live)" -CommandArgs @(
        $cliPath, "auth-status",
        "--api-base", $LemmaUrl,
        "--json"
    )
} else {
    Invoke-PythonChecked -StepName "1/4 session-status (dry-run)" -CommandArgs @(
        $cliPath, "session", "status",
        "--api-base", $LemmaUrl,
        "--json",
        "--dry-run"
    )

    Invoke-PythonChecked -StepName "2/4 auth-status (dry-run)" -CommandArgs @(
        $cliPath, "auth-status",
        "--api-base", $LemmaUrl,
        "--json",
        "--dry-run"
    )
}

$env:LEMMA_BASE_URL = $LemmaUrl
if (-not [string]::IsNullOrWhiteSpace($ProofFile) -and (Test-Path $ProofFile)) {
    $env:LEMMA_PROOF_FIXTURE_PATH = $ProofFile
} else {
    Remove-Item Env:LEMMA_PROOF_FIXTURE_PATH -ErrorAction SilentlyContinue
}
$env:LEMMA_STRICT_POSITIVE = if ($StrictProof.IsPresent) { "1" } else { "0" }

Invoke-PythonChecked -StepName "3/4 proof-exchange-contract" -CommandArgs @($proofContractPath)
Invoke-PythonChecked -StepName "4/4 launch-gate-smoke" -CommandArgs @($smokePath)

Write-Host ""
Write-Host "PASS: CLI + API proof regression checks completed."
