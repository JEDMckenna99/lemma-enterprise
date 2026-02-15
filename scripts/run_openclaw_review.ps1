param(
    [string]$LemmaUrl = "https://lemma.id",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$mcpDir = Join-Path $repoRoot "mcp-server"
$tokenFilePath = Join-Path $repoRoot ".lemma-agent-token"

if (-not (Test-Path $mcpDir)) {
    throw "Missing mcp-server directory at $mcpDir"
}

if (-not (Test-Path $tokenFilePath)) {
    throw "Token file not found at $tokenFilePath. Run scripts\setup_openclaw.ps1 first."
}

$token = (Get-Content $tokenFilePath -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($token) -or -not $token.StartsWith("lm_agent_")) {
    throw "Token file is invalid. Re-run scripts\setup_openclaw.ps1."
}

$env:LEMMA_AGENT_TOKEN = $token
$env:LEMMA_URL = $LemmaUrl
$env:OPENCLAW_REQUIRED_AUDIENCE = "openclaw"

Push-Location $mcpDir
try {
    if (-not $SkipInstall) {
        npm install
    }

    Write-Host "Running comprehensive OpenClaw review suite..."
    node run-tests.js

    Write-Host "Running interaction OpenClaw review suite..."
    node run-interaction-tests.js

    Write-Host "Running OpenClaw conformance suite..."
    node run-openclaw-conformance.js
}
finally {
    Pop-Location
}
