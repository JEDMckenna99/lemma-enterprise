param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$RuntimeId = "lemma-firewall-default",
    [string]$OrgId = $(if ($env:LEMMA_ORG_ID) { $env:LEMMA_ORG_ID } else { "org_default" }),
    [string]$Environment = $(if ($env:LEMMA_ENVIRONMENT) { $env:LEMMA_ENVIRONMENT } else { "prod" }),
    [int]$DenyWindowMinutes = 5,
    [int]$BaselineWindowMinutes = 60,
    [double]$RevocationTargetSeconds = 1.0,
    [double]$RevocationHardMaxSeconds = 5.0,
    [switch]$FailOnCritical
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$cliPath = Join-Path $repoRoot "scripts\lemma_cli.py"
if (-not (Test-Path $cliPath)) {
    throw "Missing CLI script: $cliPath"
}

Write-Host "== Agent Ops Alerts Check =="
Write-Host "Lemma URL: $LemmaUrl"
Write-Host "Runtime:   $RuntimeId"
Write-Host "Tenant:    $OrgId/$Environment"
Write-Host ""

$sessionRaw = (& python $cliPath "session" "link" "--api-base" $LemmaUrl "--requested-scope" "wallet:control_plane" "--json")
if ($LASTEXITCODE -ne 0) {
    throw "session link failed"
}
$sessionObj = $sessionRaw | Out-String | ConvertFrom-Json
$unlockToken = [string]$sessionObj.unlock_token
if ([string]::IsNullOrWhiteSpace($unlockToken)) {
    throw "session link did not return unlock token"
}

$query = "runtime_id=$RuntimeId&org_id=$OrgId&environment=$Environment&deny_window_minutes=$DenyWindowMinutes&baseline_window_minutes=$BaselineWindowMinutes&revocation_target_seconds=$RevocationTargetSeconds&revocation_hard_max_seconds=$RevocationHardMaxSeconds"
$url = "$LemmaUrl/api/wallet/runtimes/alerts/summary?$query"
$resp = Invoke-RestMethod -Method GET -Uri $url -Headers @{
    "X-Lemma-Unlock" = $unlockToken
    "X-Lemma-Org-Id" = $OrgId
    "X-Lemma-Environment" = $Environment
    "Content-Type" = "application/json"
} -TimeoutSec 30

$resp | ConvertTo-Json -Depth 20 | Out-Host

$severity = [string]$resp.overall_severity
if ($FailOnCritical -and $severity -eq "critical") {
    throw "Agent Ops alerts check is critical."
}

Write-Host ""
Write-Host "Alerts check complete. severity=$severity"
