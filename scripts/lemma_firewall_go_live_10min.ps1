param(
    [string]$Token = "",
    [string]$LemmaUrl = "https://lemma.id",
    [switch]$SkipConformance,
    [string]$CredentialFile = "",
    [string]$PlatformApiKey = "",
    [string]$UserEmail = "",
    [switch]$UseBreakGlassSelfIssue,
    [switch]$UseLegacyToken
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "== Lemma Firewall 10-minute go-live =="

if (-not $UseLegacyToken) {
    Write-Host "Using proof-first flow (Authz API + CLI)."
    if ([string]::IsNullOrWhiteSpace($CredentialFile) -and -not $UseBreakGlassSelfIssue) {
        Write-Host "No credential file provided. Script will use browser wallet approval to mint proof automatically."
    }
    powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\setup_lemma_firewall_authz_seconds.ps1") `
        -LemmaUrl $LemmaUrl `
        -CredentialFile $CredentialFile `
        -PlatformApiKey $PlatformApiKey `
        -UserEmail $UserEmail `
        -UseBreakGlassSelfIssue:$UseBreakGlassSelfIssue
    Write-Host "Go-live proof-first bootstrap completed."
    return
}

Write-Host "Legacy token flow enabled (UseLegacyToken=true)."

if ([string]::IsNullOrWhiteSpace($Token)) {
    $tokenPath = Join-Path $repoRoot ".lemma-agent-token"
    if (Test-Path $tokenPath) {
        $Token = (Get-Content $tokenPath -Raw).Trim()
    }
}

if ([string]::IsNullOrWhiteSpace($Token) -or -not $Token.StartsWith("lm_agent_")) {
    throw "Provide a valid -Token lm_agent_... (or populate .lemma-agent-token)."
}

Write-Host "Step 1/4: Configure Lemma Firewall MCP + token"
powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\setup_lemma_firewall.ps1") -Token $Token -LemmaUrl $LemmaUrl -WriteCursorConfig

Write-Host "Step 2/4: Validate token against Lemma.id"
$validation = Invoke-RestMethod -Uri "$LemmaUrl/api/agent/validate" -Method Post -Headers @{
    "X-Agent-Token" = $Token
    "Content-Type" = "application/json"
}
if (-not $validation.valid) {
    throw "Token validation failed: $($validation.error)"
}
Write-Host "Token valid with scopes: $($validation.scope -join ', ')"

Write-Host "Step 3/4: Run Lemma Firewall review suites"
powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\run_lemma_firewall_review.ps1") -LemmaUrl $LemmaUrl -SkipInstall

if (-not $SkipConformance) {
    Write-Host "Step 4/4: Run standalone conformance pass"
    Push-Location (Join-Path $repoRoot "mcp-server")
    try {
        $env:LEMMA_AGENT_TOKEN = $Token
        $env:LEMMA_BASE_URL = $LemmaUrl
        $env:LEMMA_FIREWALL_REQUIRED_AUDIENCE = "lemma-firewall"
        node run-lemma-firewall-conformance.js
    }
    finally {
        Pop-Location
    }
}

Write-Host "Lemma Firewall go-live flow completed."
