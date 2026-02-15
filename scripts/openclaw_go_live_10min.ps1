param(
    [string]$Token = "",
    [string]$LemmaUrl = "https://lemma.id",
    [switch]$SkipConformance
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "== OpenClaw 10-minute go-live =="

if ([string]::IsNullOrWhiteSpace($Token)) {
    $tokenPath = Join-Path $repoRoot ".lemma-agent-token"
    if (Test-Path $tokenPath) {
        $Token = (Get-Content $tokenPath -Raw).Trim()
    }
}

if ([string]::IsNullOrWhiteSpace($Token) -or -not $Token.StartsWith("lm_agent_")) {
    throw "Provide a valid -Token lm_agent_... (or populate .lemma-agent-token)."
}

Write-Host "Step 1/4: Configure OpenClaw MCP + token"
powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\setup_openclaw.ps1") -Token $Token -LemmaUrl $LemmaUrl -WriteCursorConfig

Write-Host "Step 2/4: Validate token against Lemma.id"
$validation = Invoke-RestMethod -Uri "$LemmaUrl/api/agent/validate" -Method Post -Headers @{
    "X-Agent-Token" = $Token
    "Content-Type" = "application/json"
}
if (-not $validation.valid) {
    throw "Token validation failed: $($validation.error)"
}
Write-Host "Token valid with scopes: $($validation.scope -join ', ')"

Write-Host "Step 3/4: Run OpenClaw review suites"
powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\run_openclaw_review.ps1") -LemmaUrl $LemmaUrl -SkipInstall

if (-not $SkipConformance) {
    Write-Host "Step 4/4: Run standalone conformance pass"
    Push-Location (Join-Path $repoRoot "mcp-server")
    try {
        $env:LEMMA_AGENT_TOKEN = $Token
        $env:LEMMA_BASE_URL = $LemmaUrl
        $env:OPENCLAW_REQUIRED_AUDIENCE = "openclaw"
        node run-openclaw-conformance.js
    }
    finally {
        Pop-Location
    }
}

Write-Host "OpenClaw go-live flow completed."
