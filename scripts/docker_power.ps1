param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "up-core",
        "up-full",
        "down",
        "reset",
        "migrate",
        "health",
        "smoke",
        "ishuman-smoke",
        "build-api",
        "build-all",
        "bench-build",
        "logs-api",
        "logs-daemon",
        "cli",
        "scorecard",
        "prune-safe"
    )]
    [string]$Action = "health",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Message)
    Write-Host ("`n=== " + $Message + " ===")
}

function Invoke-DockerCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args,
        [switch]$AllowFailure
    )

    & docker compose @Args
    $exitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "docker compose $($Args -join ' ') failed with exit code $exitCode"
    }
    return $exitCode
}

function Wait-HttpOk {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$MaxAttempts = 25,
        [int]$SleepSeconds = 2
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            $raw = & curl.exe -sS $Url
            if ($LASTEXITCODE -eq 0 -and $raw) {
                return $raw
            }
        } catch {
            # Retry loop handles transient startup failures.
        }
        Start-Sleep -Seconds $SleepSeconds
    }

    throw "Health check never became ready: $Url"
}

function Start-CoreServices {
    Write-Step "Starting core services (postgres, redis, api)"
    Invoke-DockerCompose -Args @("up", "-d", "postgres", "redis", "api") | Out-Null
}

function Start-DaemonService {
    Write-Step "Starting daemon profile"
    Invoke-DockerCompose -Args @("--profile", "daemon", "up", "-d", "daemon") | Out-Null
}

function Test-HealthChecks {
    Write-Step "Checking API health"
    $apiHealth = Wait-HttpOk -Url "http://localhost:5000/health"
    Write-Host $apiHealth

    Write-Step "Checking daemon health"
    $daemonHealth = Wait-HttpOk -Url "http://localhost:8787/aim/health"
    Write-Host $daemonHealth
}

function Invoke-SmokeChecks {
    param([switch]$IncludeMigrations)

    Start-CoreServices
    Start-DaemonService

    if ($IncludeMigrations) {
        Write-Step "Running migrations"
        Invoke-DockerCompose -Args @("--profile", "ops", "run", "--rm", "migrate") | Out-Null
    }

    Test-HealthChecks

    Write-Step "CLI help smoke"
    Invoke-DockerCompose -Args @("--profile", "cli", "run", "--rm", "cli", "--help") | Out-Null

    Write-Step "CLI auth-status smoke (expects auth required when no session)"
    $tmpFile = [System.IO.Path]::GetTempFileName()
    try {
        $cmd = "docker compose --profile cli run --rm cli auth-status --api-base http://api:5000 --json > `"$tmpFile`" 2>&1"
        cmd /c $cmd | Out-Null
        $output = Get-Content -Path $tmpFile -Raw
    } finally {
        Remove-Item -Path $tmpFile -ErrorAction SilentlyContinue
    }

    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 1) {
        throw "Expected auth-status exit code 1 without session; got $exitCode"
    }
    if ($output -notmatch '"error_code"\s*:\s*"E_AUTH_REQUIRED"') {
        throw "auth-status output did not include expected E_AUTH_REQUIRED signal"
    }
    Write-Host $output
    $global:LASTEXITCODE = 0
}

function Invoke-IsHumanSmokeChecks {
    Write-Step "Building api image for latest routes"
    Invoke-DockerCompose -Args @("build", "api") | Out-Null

    Start-CoreServices

    Write-Step "isHuman stats endpoint smoke"
    $statsRaw = $null
    for ($i = 1; $i -le 15; $i++) {
        try {
            $statsRaw = & curl.exe -sS "http://localhost:5000/api/ishuman/stats"
            if ($LASTEXITCODE -eq 0 -and $statsRaw) { break }
        } catch {}
        Start-Sleep -Seconds 2
    }
    if (-not $statsRaw) {
        throw "Failed to read /api/ishuman/stats after retries"
    }
    $stats = $statsRaw | ConvertFrom-Json
    if (-not $stats) {
        throw "Invalid JSON from /api/ishuman/stats: $statsRaw"
    }
    if (
        -not ($stats.PSObject.Properties.Name -contains "success") -or
        -not $stats.success -or
        -not ($stats.PSObject.Properties.Name -contains "network") -or
        $stats.network -ne "isHuman"
    ) {
        throw "Unexpected /api/ishuman/stats payload: $statsRaw"
    }
    Write-Host $statsRaw

    Write-Step "isHuman check endpoint smoke"
    $checkRaw = Wait-HttpOk -Url "http://localhost:5000/api/ishuman/check?ppid=did:lemma:ppid_docker_smoke"
    $check = $checkRaw | ConvertFrom-Json
    if (-not $check) {
        throw "Invalid JSON from /api/ishuman/check: $checkRaw"
    }
    if (
        -not ($check.PSObject.Properties.Name -contains "success") -or
        -not $check.success -or
        -not ($check.PSObject.Properties.Name -contains "ppid") -or
        -not $check.ppid
    ) {
        throw "Unexpected /api/ishuman/check payload: $checkRaw"
    }
    Write-Host $checkRaw

    Write-Step "isHuman start-verification validation smoke"
    $verifyBody = "{}"
    $verifyRaw = & curl.exe -sS -X POST -H "Content-Type: application/json" -d $verifyBody "http://localhost:5000/api/ishuman/start-verification"
    if ($LASTEXITCODE -ne 0) {
        throw "curl failed for /api/ishuman/start-verification validation smoke"
    }
    $verify = $verifyRaw | ConvertFrom-Json
    if ($verify.error -ne "wallet_id required") {
        throw "Unexpected /api/ishuman/start-verification validation response: $verifyRaw"
    }
    Write-Host $verifyRaw
}

function Measure-Build {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Services
    )

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Invoke-DockerCompose -Args (@("build") + $Services) | Out-Null
    $sw.Stop()
    return [Math]::Round($sw.Elapsed.TotalSeconds, 2)
}

function Write-Scorecard {
    $reportDir = "docs"
    $reportPath = Join-Path $reportDir "DOCKER_SCORECARD.md"
    if (-not (Test-Path $reportDir)) {
        New-Item -Path $reportDir -ItemType Directory | Out-Null
    }

    Write-Step "Measuring startup and build timings"
    $startupTimer = [System.Diagnostics.Stopwatch]::StartNew()
    Start-CoreServices
    Start-DaemonService
    Test-HealthChecks
    $startupTimer.Stop()

    $apiBuildSeconds = Measure-Build -Services @("api")
    $fullBuildSeconds = Measure-Build -Services @("api", "daemon", "cli", "migrate")

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $startupSeconds = [Math]::Round($startupTimer.Elapsed.TotalSeconds, 2)

    $content = @"
# Docker Scorecard

Generated: $timestamp

| Metric | Value |
|---|---:|
| Time-to-healthy stack (api+daemon) | ${startupSeconds}s |
| Incremental build (api) | ${apiBuildSeconds}s |
| Full stack build | ${fullBuildSeconds}s |

## Notes

- This scorecard is generated by `scripts/docker_power.ps1 scorecard`.
- Re-run weekly and compare trends to keep Docker workflows fast and reliable.
"@
    Set-Content -Path $reportPath -Value $content -Encoding UTF8
    Write-Host "Scorecard written to $reportPath"
}

switch ($Action) {
    "up-core" {
        Start-CoreServices
    }
    "up-full" {
        Start-CoreServices
        Start-DaemonService
    }
    "down" {
        Write-Step "Stopping all services"
        Invoke-DockerCompose -Args @("--profile", "daemon", "down") | Out-Null
    }
    "reset" {
        Write-Step "Resetting stack (containers + volumes)"
        Invoke-DockerCompose -Args @("--profile", "daemon", "down", "-v") | Out-Null
    }
    "migrate" {
        Write-Step "Running migrations"
        Invoke-DockerCompose -Args @("--profile", "ops", "run", "--rm", "migrate") | Out-Null
    }
    "health" {
        Test-HealthChecks
    }
    "smoke" {
        Invoke-SmokeChecks -IncludeMigrations
    }
    "ishuman-smoke" {
        Invoke-IsHumanSmokeChecks
    }
    "build-api" {
        Write-Step "Building api image"
        Invoke-DockerCompose -Args @("build", "api") | Out-Null
    }
    "build-all" {
        Write-Step "Building api/daemon/cli/migrate images"
        Invoke-DockerCompose -Args @("build", "api", "daemon", "cli", "migrate") | Out-Null
    }
    "bench-build" {
        $api = Measure-Build -Services @("api")
        $full = Measure-Build -Services @("api", "daemon", "cli", "migrate")
        Write-Host ("api build: " + $api + "s")
        Write-Host ("full build: " + $full + "s")
    }
    "logs-api" {
        Invoke-DockerCompose -Args @("logs", "-f", "api")
    }
    "logs-daemon" {
        Invoke-DockerCompose -Args @("logs", "-f", "daemon")
    }
    "cli" {
        if (-not $CliArgs -or $CliArgs.Count -eq 0) {
            $CliArgs = @("--help")
        }
        Invoke-DockerCompose -Args (@("--profile", "cli", "run", "--rm", "cli") + $CliArgs)
    }
    "scorecard" {
        Write-Scorecard
    }
    "prune-safe" {
        Write-Step "Pruning dangling build cache"
        & docker builder prune -f
        if ($LASTEXITCODE -ne 0) {
            throw "docker builder prune failed"
        }
    }
    default {
        throw "Unknown action: $Action"
    }
}
