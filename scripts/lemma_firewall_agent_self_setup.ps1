param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$CredentialFile = "",
    [string]$RuntimeId = "lemma-firewall-default",
    [string]$AgentId = "main",
    [string]$WorkspaceId = "default",
    [string]$DisplayName = "Lemma Firewall Runtime",
    [switch]$StartFirewall,
    [string]$FirewallBindHost = "127.0.0.1",
    [int]$FirewallPort = 8787,
    [switch]$UseBreakGlassSelfIssue,
    [string]$PlatformApiKey = "",
    [string]$UserEmail = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$setupScript = Join-Path $repoRoot "scripts\setup_lemma_firewall_authz_seconds.ps1"
$firewallScript = Join-Path $repoRoot "scripts\start_lemma_firewall.ps1"
$cliPath = Join-Path $repoRoot "scripts\lemma_cli.py"
$proofPath = if ([string]::IsNullOrWhiteSpace($CredentialFile)) {
    Join-Path $repoRoot ".lemma-proof.json"
} else {
    $CredentialFile
}

if (-not (Test-Path $setupScript)) {
    throw "Missing setup script: $setupScript"
}
if (-not (Test-Path $cliPath)) {
    throw "Missing CLI script: $cliPath"
}

Write-Host "== Lemma Firewall Agent Self-Setup (Lemma Authz) =="
Write-Host "Repo:      $repoRoot"
Write-Host "Lemma URL: $LemmaUrl"
Write-Host "Runtime:   $RuntimeId ($AgentId/$WorkspaceId)"
Write-Host ""

Write-Host "Step 1/3: Bootstrap proof-first Lemma Firewall authz"
$setupArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $setupScript,
    "-LemmaUrl", $LemmaUrl,
    "-RuntimeId", $RuntimeId,
    "-AgentId", $AgentId,
    "-WorkspaceId", $WorkspaceId,
    "-RuntimeDisplayName", $DisplayName
)
if (-not [string]::IsNullOrWhiteSpace($CredentialFile)) {
    $setupArgs += @("-CredentialFile", $CredentialFile)
}
if ($UseBreakGlassSelfIssue) {
    $setupArgs += "-UseBreakGlassSelfIssue"
    if (-not [string]::IsNullOrWhiteSpace($PlatformApiKey)) {
        $setupArgs += @("-PlatformApiKey", $PlatformApiKey)
    }
    if (-not [string]::IsNullOrWhiteSpace($UserEmail)) {
        $setupArgs += @("-UserEmail", $UserEmail)
    }
}

& powershell @setupArgs
if ($LASTEXITCODE -ne 0) {
    throw "setup_lemma_firewall_authz_seconds.ps1 failed (exit=$LASTEXITCODE)"
}

Write-Host ""
Write-Host "Step 2/3: Confirm runtime connectivity"
& python $cliPath "firewall-connect" `
    "--api-base" $LemmaUrl `
    "--runtime-id" $RuntimeId `
    "--agent-id" $AgentId `
    "--workspace-id" $WorkspaceId `
    "--display-name" $DisplayName `
    "--json" | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "lemma_cli firewall-connect failed (exit=$LASTEXITCODE)"
}

Write-Host ""
Write-Host "Step 3/3: Final operator summary"
Write-Host "  LEMMA_BASE_URL=$LemmaUrl"
Write-Host "  LEMMA_PROOF_FILE=$proofPath"
Write-Host "  Lemma Firewall runtime connected."

if ($StartFirewall) {
    if (-not (Test-Path $firewallScript)) {
        throw "Missing firewall launcher script: $firewallScript"
    }
    Write-Host ""
    Write-Host "Starting local Lemma firewall..."
    & powershell -ExecutionPolicy Bypass -File $firewallScript `
        -LemmaUrl $LemmaUrl `
        -ProofFile $proofPath `
        -RuntimeId $RuntimeId `
        -BindHost $FirewallBindHost `
        -Port $FirewallPort
    if ($LASTEXITCODE -ne 0) {
        throw "start_lemma_firewall.ps1 failed (exit=$LASTEXITCODE)"
    }
}

Write-Host ""
Write-Host "Done. Lemma Firewall is set up with Lemma agent authz."
