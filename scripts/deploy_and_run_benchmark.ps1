param(
    [string]$DeployRemote = "production",
    [string]$DeployRef = "HEAD:main",
    [string]$BaseUrl = "https://lemma.id",
    [string]$ProofFile = ".lemma-proof.json",
    [string[]]$Scenarios = @("normal"),
    [int]$Repetitions = 5,
    [int]$Requests = 60,
    [int]$Warmup = 10,
    [double]$AuthzBudgetP95Ms = 5.0,
    [double]$E2EBudgetP95Ms = 0.0,
    [int]$HealthPollTimeoutSeconds = 180,
    [int]$HealthPollIntervalSeconds = 5,
    [switch]$SkipPush,
    [switch]$SkipHealthWait
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Invoke-CheckedCommand {
    param(
        [string]$Description,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host "== $Description =="
    & $Action
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

function Resolve-HerokuAppName {
    param(
        [string]$RemoteName
    )
    $remoteUrl = (git remote get-url $RemoteName 2>$null) | Out-String
    $remoteUrl = $remoteUrl.Trim()
    if ([string]::IsNullOrWhiteSpace($remoteUrl)) {
        return ""
    }
    if ($remoteUrl -match "git\.heroku\.com/([^/]+)\.git$") {
        return $Matches[1]
    }
    return ""
}

function Wait-ForHealth {
    param(
        [string]$Url,
        [int]$TimeoutSeconds,
        [int]$IntervalSeconds
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod -Method GET -Uri "$Url/api/health" -TimeoutSec 15
            if ($resp -and $resp.status -eq "ok") {
                Write-Host "Health check returned status=ok"
                return
            }
            Write-Host "Health endpoint reachable, waiting for status=ok..."
        } catch {
            Write-Host "Health check not ready yet..."
        }
        Start-Sleep -Seconds $IntervalSeconds
    }
    throw "Timed out waiting for $Url/api/health to become ready."
}

$proofPath = if ([System.IO.Path]::IsPathRooted($ProofFile)) {
    $ProofFile
} else {
    Join-Path $repoRoot $ProofFile
}
if (-not (Test-Path $proofPath)) {
    throw "Proof file not found: $proofPath"
}

$timestamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$outputDir = Join-Path $repoRoot "docs\launch-evidence"
if (-not (Test-Path $outputDir)) {
    New-Item -Path $outputDir -ItemType Directory -Force | Out-Null
}
$runLog = Join-Path $outputDir "$timestamp-deploy-and-benchmark.txt"

Write-Host "Deploy remote: $DeployRemote"
Write-Host "Deploy ref:    $DeployRef"
Write-Host "Base URL:      $BaseUrl"
Write-Host "Proof file:    $proofPath"
Write-Host "Scenarios:     $($Scenarios -join ', ')"
Write-Host "Repetitions:   $Repetitions"

if (-not $SkipPush) {
    Invoke-CheckedCommand -Description "Push to deployment remote" -Action {
        git push $DeployRemote $DeployRef
    }
} else {
    Write-Host "Skipping git push (--SkipPush)."
}

$herokuApp = Resolve-HerokuAppName -RemoteName $DeployRemote
if (-not [string]::IsNullOrWhiteSpace($herokuApp)) {
    Write-Host "Detected Heroku app from remote: $herokuApp"
    Invoke-CheckedCommand -Description "Fetch latest Heroku release (best effort)" -Action {
        heroku releases -a $herokuApp
    }
} else {
    Write-Host "Remote '$DeployRemote' is not a Heroku git URL or app name could not be derived."
}

if (-not $SkipHealthWait) {
    Invoke-CheckedCommand -Description "Wait for deployment health" -Action {
        Wait-ForHealth -Url $BaseUrl -TimeoutSeconds $HealthPollTimeoutSeconds -IntervalSeconds $HealthPollIntervalSeconds
    }
} else {
    Write-Host "Skipping health wait (--SkipHealthWait)."
}

$benchmarkArgs = @(
    "scripts/run_revocation_benchmark_matrix.py",
    "--base-url", $BaseUrl,
    "--proof-file", $proofPath,
    "--repetitions", $Repetitions,
    "--requests", $Requests,
    "--warmup", $Warmup,
    "--authz-budget-p95-ms", $AuthzBudgetP95Ms,
    "--e2e-budget-p95-ms", $E2EBudgetP95Ms
)
foreach ($scenario in $Scenarios) {
    $benchmarkArgs += @("--scenario", $scenario)
}

Invoke-CheckedCommand -Description "Run benchmark matrix" -Action {
    python @benchmarkArgs | Tee-Object -FilePath $runLog
}

Write-Host ""
Write-Host "Deploy + benchmark complete."
Write-Host "Run log: $runLog"
