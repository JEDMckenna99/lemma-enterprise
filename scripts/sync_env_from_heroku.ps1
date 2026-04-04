param(
    [string]$AppName = "lemma-enterprise",
    [string]$OutputPath = ".env.docker.local",
    [string]$SnapshotPath = ".env.heroku.snapshot",
    [switch]$PreviewOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Message)
    Write-Host ("`n=== " + $Message + " ===")
}

function ConvertTo-EnvMap {
    param([string[]]$Lines)
    $map = @{}
    foreach ($line in $Lines) {
        if (-not $line) { continue }
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $idx = $trimmed.IndexOf("=")
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1)
        if ($key) {
            $map[$key] = $value
        }
    }
    return $map
}

function Format-EnvMap {
    param([hashtable]$Map)
    $keys = @($Map.Keys) | Sort-Object
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($k in $keys) {
        $lines.Add("$k=$($Map[$k])")
    }
    return $lines
}

Write-Step "Pulling Heroku config vars"
$raw = & heroku config -a $AppName -s
if ($LASTEXITCODE -ne 0) {
    throw "Failed to pull Heroku config for app '$AppName'. Ensure Heroku CLI auth is active."
}

$rawLines = @($raw -split "`r?`n")
if ($rawLines.Count -eq 0) {
    throw "Heroku returned no config lines for app '$AppName'."
}

Write-Step "Writing raw snapshot"
Set-Content -Path $SnapshotPath -Value $rawLines -Encoding UTF8
Write-Host "Snapshot written: $SnapshotPath"

$config = ConvertTo-EnvMap -Lines $rawLines

# Remove vars that should never be copied from Heroku runtime into local Docker.
$excludeKeys = @(
    "DATABASE_URL",
    "REDIS_URL",
    "REDIS_TLS_URL",
    "PORT",
    "DYNO",
    "HOST",
    "HEROKU_APP_NAME",
    "HEROKU_RELEASE_VERSION",
    "SOURCE_VERSION",
    "STACK",
    "HOME",
    "PWD",
    "SHLVL"
)
foreach ($k in $excludeKeys) {
    if ($config.ContainsKey($k)) {
        $null = $config.Remove($k)
    }
}

# Local Docker-safe overrides.
$overrides = @{
    "FLASK_ENV" = "development"
    "ENVIRONMENT" = "development"
    "PORT" = "5000"
    "DATABASE_URL" = "postgresql://lemma:lemma@postgres:5432/lemma"
    "REDIS_URL" = "redis://redis:6379/0"
    "LEMMA_BASE_URL" = "http://api:5000"
    "ISHUMAN_RETURN_URL" = "http://localhost:5000/app"
}
foreach ($k in $overrides.Keys) {
    $config[$k] = $overrides[$k]
}

$lines = Format-EnvMap -Map $config

Write-Step "Prepared merged env"
Write-Host ("Total keys: " + $lines.Count)
Write-Host "Excluded runtime-only keys:"
Write-Host (" - " + ($excludeKeys -join ", "))
Write-Host "Applied overrides:"
Write-Host (" - " + (($overrides.Keys | Sort-Object) -join ", "))

if ($PreviewOnly) {
    Write-Step "Preview mode enabled (no file write)"
    $previewKeys = @($config.Keys) | Sort-Object
    $previewSample = $previewKeys | Select-Object -First 25
    Write-Host ("Sample keys: " + ($previewSample -join ", "))
    exit 0
}

Write-Step "Writing Docker env output"
Set-Content -Path $OutputPath -Value $lines -Encoding UTF8
Write-Host "Docker env written: $OutputPath"
Write-Host "Next step: copy or link this file to .env.docker before docker compose up."
