param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$RuntimeId = "lemma-firewall-demo",
    [string]$AgentId = "main",
    [string]$WorkspaceId = "default",
    [string]$DisplayName = "Lemma Firewall Demo Runtime",
    [string]$KillReason = "Demo kill switch validation",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$cliPath = Join-Path $repoRoot "scripts\lemma_cli.py"

function Invoke-LemmaCliJson {
    param([string[]]$CliArgs)
    $raw = (& python $cliPath @CliArgs)
    if ($LASTEXITCODE -ne 0) {
        throw "lemma_cli failed (exit=$LASTEXITCODE): $($CliArgs -join ' ')"
    }
    return ($raw | Out-String | ConvertFrom-Json)
}

Write-Host "== Lemma Agent Authz demo run =="
Write-Host "Base URL: $LemmaUrl"
Write-Host "Runtime:  $RuntimeId"
Write-Host ""

Write-Host "Step 1/5: Acquire wallet unlock token via CLI link"
$sessionArgs = @("session", "link", "--api-base", $LemmaUrl, "--requested-scope", "wallet:control_plane", "--json")
if ($NoBrowser) { $sessionArgs += "--no-browser" }
$sessionLink = Invoke-LemmaCliJson -CliArgs $sessionArgs
if (-not $sessionLink.ok -or -not $sessionLink.unlock_token) {
    throw "Session link did not return unlock_token."
}
$unlockToken = [string]$sessionLink.unlock_token
Write-Host "Unlock token acquired."

Write-Host "Step 2/5: Connect runtime with server-enforced defaults"
$connect = Invoke-LemmaCliJson -CliArgs @(
    "firewall-connect",
    "--api-base", $LemmaUrl,
    "--runtime-id", $RuntimeId,
    "--agent-id", $AgentId,
    "--workspace-id", $WorkspaceId,
    "--display-name", $DisplayName,
    "--unlock-token", $unlockToken,
    "--json"
)
if (-not $connect.ok) {
    throw "firewall-connect failed."
}
Write-Host "Runtime connected."

Write-Host "Step 3/5: List connected runtimes"
$listBefore = Invoke-RestMethod -Method GET -Uri "$LemmaUrl/api/wallet/runtimes" -Headers @{
    "X-Lemma-Unlock" = $unlockToken
    "Content-Type" = "application/json"
}
if (-not $listBefore.success) {
    throw "Runtime list failed."
}
$beforeCount = @($listBefore.runtimes).Count
Write-Host "Runtimes visible: $beforeCount"

Write-Host "Step 4/5: Trigger kill switch on runtime"
$killResp = Invoke-RestMethod -Method POST -Uri "$LemmaUrl/api/wallet/runtimes/$RuntimeId/kill" -Headers @{
    "X-Lemma-Unlock" = $unlockToken
    "Content-Type" = "application/json"
} -Body (@{ reason = $KillReason } | ConvertTo-Json -Compress)
if (-not $killResp.success) {
    throw "Runtime kill failed."
}
Write-Host "Kill switch invoked."

Write-Host "Step 5/5: Re-list runtimes and verify killed state"
$listAfter = Invoke-RestMethod -Method GET -Uri "$LemmaUrl/api/wallet/runtimes" -Headers @{
    "X-Lemma-Unlock" = $unlockToken
    "Content-Type" = "application/json"
}
if (-not $listAfter.success) {
    throw "Post-kill runtime list failed."
}
$target = @($listAfter.runtimes | Where-Object { $_.runtime_id -eq $RuntimeId }) | Select-Object -First 1
if (-not $target) {
    throw "Runtime not found after kill (unexpected)."
}

Write-Host ""
Write-Host "Demo result:"
Write-Host "  runtime_id: $($target.runtime_id)"
Write-Host "  active:     $($target.active)"
Write-Host "  killed_at:  $($target.killed_at)"
Write-Host "  kill_reason:$($target.kill_reason)"
Write-Host ""
Write-Host "Done. Agent authz runtime-level kill path verified."
