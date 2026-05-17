param(
    [Parameter(Mandatory = $true)]
    [string]$AppName,

    [ValidateSet("staging", "production")]
    [string]$Environment = "staging",

    [string]$LocalEnvFile = ".env.local",
    [string]$SnapshotPath = "",
    [switch]$SkipHerokuPull
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $SnapshotPath) {
    $safeApp = $AppName -replace '[^A-Za-z0-9_.-]', '_'
    $SnapshotPath = ".env.heroku.$safeApp.snapshot"
}

if (-not $SkipHerokuPull) {
    Write-Host "Pulling Heroku config for $AppName..."
    $raw = & heroku config -a $AppName -s
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to pull Heroku config for app '$AppName'. Ensure Heroku CLI auth is active."
    }
    Set-Content -Path $SnapshotPath -Value ($raw -split "`r?`n") -Encoding UTF8
    Write-Host "Wrote Heroku config snapshot to $SnapshotPath (ignored by git)."
}

$argsList = @(
    "scripts/check_env_parity.py",
    "--environment", $Environment,
    "--env-file", $SnapshotPath
)

if (Test-Path $LocalEnvFile) {
    $argsList += @("--compare-env-file", $LocalEnvFile)
} else {
    Write-Host "Local env file '$LocalEnvFile' not found; validating Heroku config only."
}

python @argsList
exit $LASTEXITCODE
