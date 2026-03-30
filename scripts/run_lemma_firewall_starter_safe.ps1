param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$RuntimeId = "lemma-firewall-default",
    [string]$AgentId = "main",
    [string]$WorkspaceId = "default",
    [string]$DisplayName = "Lemma Firewall Runtime",
    [string]$ProofFile = "",
    [string]$OutputDir = "",
    [string]$BindHost = "127.0.0.1",
    [int]$FirewallPort = 8787,
    [switch]$SkipSetup,
    [switch]$SkipFirewall,
    [switch]$SkipReview,
    [switch]$SkipKillCheck,
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
$runId = "$timestamp-openclaw-starter-safe"
$summaryPath = Join-Path $OutputDir "$runId-summary.md"
$jsonPath = Join-Path $OutputDir "$runId-results.json"
$steps = New-Object System.Collections.Generic.List[object]
$firewallProc = $null
$health = $null

function Add-StepResult {
    param(
        [string]$Name,
        [string]$Command,
        [int]$ExitCode,
        [bool]$Ok,
        [string[]]$Output,
        [bool]$IsDryRun = $false
    )
    $steps.Add([pscustomobject]@{
        name = $Name
        command = $Command
        exit_code = $ExitCode
        ok = $Ok
        dry_run = $IsDryRun
        output = $Output
        finished_at = (Get-Date).ToString("o")
    })
}

function Invoke-Step {
    param(
        [string]$Name,
        [string]$Command
    )
    Write-Host ""
    Write-Host "=== $Name ==="
    Write-Host $Command

    if ($DryRun) {
        Add-StepResult -Name $Name -Command $Command -ExitCode 0 -Ok $true -Output @("[dry-run] skipped execution") -IsDryRun $true
        return
    }

    $outputLines = @(Invoke-Expression "$Command 2>&1" | ForEach-Object { "$_" })
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
    foreach ($line in $outputLines) { Write-Host $line }

    $ok = ($exitCode -eq 0)
    Add-StepResult -Name $Name -Command $Command -ExitCode ([int]$exitCode) -Ok $ok -Output $outputLines
    if (-not $ok) {
        throw "Step failed: $Name (exit=$exitCode)"
    }
}

function Start-FirewallProcess {
    param(
        [string]$BindAddress,
        [int]$Port
    )
    if ($DryRun) {
        Add-StepResult -Name "Start local firewall" -Command "powershell -ExecutionPolicy Bypass -File scripts/start_lemma_firewall.ps1 ..." -ExitCode 0 -Ok $true -Output @("[dry-run] firewall start skipped") -IsDryRun $true
        return $null
    }
    $startArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", "scripts/start_lemma_firewall.ps1",
        "-LemmaUrl", $LemmaUrl,
        "-ProofFile", $ProofFile,
        "-RuntimeId", $RuntimeId,
        "-BindHost", $BindAddress,
        "-Port", [string]$Port,
        "-SecurityProfile", "starter_safe"
    )
    $proc = Start-Process -FilePath "powershell" -ArgumentList $startArgs -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden
    Add-StepResult -Name "Start local firewall" -Command "powershell -ExecutionPolicy Bypass -File scripts/start_lemma_firewall.ps1 -SecurityProfile starter_safe" -ExitCode 0 -Ok $true -Output @("started pid=$($proc.Id)")
    return $proc
}

function Wait-FirewallHealth {
    param(
        [string]$BindAddress,
        [int]$Port,
        [int]$TimeoutSeconds = 45
    )
    if ($DryRun) {
        Add-StepResult -Name "Check local firewall health" -Command "GET /aim/health" -ExitCode 0 -Ok $true -Output @("[dry-run] health check skipped") -IsDryRun $true
        return @{
            ok = $true
            local_proof_enforcement = $true
            sync = @{ enabled = $true }
            runtime_authorize_required_tiers = @("critical")
            online_check_on_stale_noncritical = $false
            auth_mode = "proof"
        }
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $url = "http://$BindAddress`:$Port/aim/health"
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod -Method GET -Uri $url -TimeoutSec 5
            if ($resp -and $resp.ok) {
                Add-StepResult -Name "Check local firewall health" -Command "GET $url" -ExitCode 0 -Ok $true -Output @("health ready")
                return $resp
            }
        } catch {}
        Start-Sleep -Seconds 2
    }
    Add-StepResult -Name "Check local firewall health" -Command "GET $url" -ExitCode 1 -Ok $false -Output @("health timeout")
    throw "Firewall health check timed out: $url"
}

try {
    if (-not $SkipSetup) {
        Invoke-Step -Name "Setup starter-safe OpenClaw" -Command "powershell -ExecutionPolicy Bypass -File scripts/setup_lemma_firewall_authz_seconds.ps1 -LemmaUrl $LemmaUrl -RuntimeId $RuntimeId -AgentId $AgentId -WorkspaceId $WorkspaceId -RuntimeDisplayName `"$DisplayName`" -SecurityProfile starter_safe"
    }

    if (-not $SkipFirewall) {
        $firewallProc = Start-FirewallProcess -BindAddress $BindHost -Port $FirewallPort
        $health = Wait-FirewallHealth -BindAddress $BindHost -Port $FirewallPort
    }

    if (-not $SkipReview) {
        Invoke-Step -Name "Run proof-first review" -Command "powershell -ExecutionPolicy Bypass -File scripts/run_lemma_firewall_review.ps1 -LemmaUrl $LemmaUrl -CredentialFile `"$ProofFile`""
    }

    if (-not $SkipKillCheck) {
        Invoke-Step -Name "Run runtime kill-switch E2E" -Command "powershell -ExecutionPolicy Bypass -File scripts/run_agent_ops_e2e.ps1 -LemmaUrl $LemmaUrl -RuntimeId $RuntimeId -AgentId $AgentId -WorkspaceId $WorkspaceId -DisplayName `"$DisplayName`" -ProofFile `"$ProofFile`""
    }

    $safetyStatus = "safe"
    $safetyReasons = @()
    if ($health) {
        if (-not [bool]$health.local_proof_enforcement) { $safetyStatus = "degraded"; $safetyReasons += "local_proof_enforcement_disabled" }
        if (-not [bool]$health.sync.enabled) { $safetyStatus = "degraded"; $safetyReasons += "control_plane_sync_disabled" }
        $tiers = @($health.runtime_authorize_required_tiers)
        if (-not ($tiers -contains "critical")) { $safetyStatus = "degraded"; $safetyReasons += "critical_tier_not_forced_online" }
        if ([bool]$health.online_check_on_stale_noncritical) { $safetyReasons += "noncritical_stale_online_enabled" }
    }
} catch {
    $safetyStatus = "unsafe"
    $safetyReasons = @("execution_failed")
    $errorText = "$_"
    Write-Host ""
    Write-Host "Starter-safe run failed: $errorText" -ForegroundColor Red
} finally {
    if ($firewallProc -and -not $DryRun) {
        try {
            if (-not $firewallProc.HasExited) {
                Stop-Process -Id $firewallProc.Id -Force
                Add-StepResult -Name "Stop local firewall" -Command "Stop-Process $($firewallProc.Id)" -ExitCode 0 -Ok $true -Output @("stopped pid=$($firewallProc.Id)")
            }
        } catch {
            Add-StepResult -Name "Stop local firewall" -Command "Stop-Process $($firewallProc.Id)" -ExitCode 1 -Ok $false -Output @("$($_)")
        }
    }

    $okSteps = @($steps | Where-Object { $_.ok }).Count
    $totalSteps = $steps.Count
    $result = [pscustomobject]@{
        run_id = $runId
        status = $safetyStatus
        reasons = $safetyReasons
        lemma_url = $LemmaUrl
        runtime_id = $RuntimeId
        proof_file = $ProofFile
        dry_run = [bool]$DryRun
        checks = @{
            setup = -not $SkipSetup
            firewall = -not $SkipFirewall
            review = -not $SkipReview
            kill_check = -not $SkipKillCheck
        }
        safety_profile = "starter_safe"
        summary = @{
            passed_steps = $okSteps
            total_steps = $totalSteps
        }
        firewall_health = $health
        steps = $steps
        generated_at = (Get-Date).ToString("o")
    }
    if ($errorText) {
        $result | Add-Member -MemberType NoteProperty -Name error -Value $errorText
    }
    $result | ConvertTo-Json -Depth 20 | Set-Content -Path $jsonPath

    $lines = @(
        "# OpenClaw Starter-Safe Run",
        "",
        "- Run ID: $runId",
        "- Safety status: **$safetyStatus**",
        "- Safety profile: starter_safe",
        "- Lemma URL: $LemmaUrl",
        "- Runtime: $RuntimeId",
        "- Dry run: $($DryRun.IsPresent)",
        "",
        "## Safety Reasons"
    )
    if ($safetyReasons.Count -eq 0) {
        $lines += "- none"
    } else {
        foreach ($reason in $safetyReasons) { $lines += "- $reason" }
    }
    $lines += ""
    $lines += "## Steps"
    foreach ($step in $steps) {
        $mark = if ($step.ok) { "PASS" } else { "FAIL" }
        $lines += "- [$mark] $($step.name) (exit=$($step.exit_code))"
    }
    if ($errorText) {
        $lines += ""
        $lines += "## Error"
        $lines += "- $errorText"
    }
    $lines += ""
    $lines += "## Artifacts"
    $lines += "- JSON: $jsonPath"
    $lines += "- Summary: $summaryPath"
    $lines | Set-Content -Path $summaryPath

    Write-Host ""
    Write-Host "Safety status: $safetyStatus"
    Write-Host "Summary: $summaryPath"
    Write-Host "Results: $jsonPath"
}

if ($safetyStatus -eq "unsafe") { exit 1 }
exit 0
