param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$CredentialFile = "",
    [switch]$SkipInstall,
    [switch]$UseLegacyToken
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$mcpDir = Join-Path $repoRoot "mcp-server"
$defaultProofPath = Join-Path $repoRoot ".lemma-proof.json"

if ($UseLegacyToken) {
    $tokenFilePath = Join-Path $repoRoot ".lemma-agent-token"
    if (-not (Test-Path $mcpDir)) {
        throw "Missing mcp-server directory at $mcpDir"
    }
    if (-not (Test-Path $tokenFilePath)) {
        throw "Token file not found at $tokenFilePath. Run scripts\setup_lemma_firewall.ps1 first."
    }

    $token = (Get-Content $tokenFilePath -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($token) -or -not $token.StartsWith("lm_agent_")) {
        throw "Token file is invalid. Re-run scripts\setup_lemma_firewall.ps1."
    }

    $env:LEMMA_AGENT_TOKEN = $token
    $env:LEMMA_URL = $LemmaUrl
    $env:LEMMA_FIREWALL_REQUIRED_AUDIENCE = "lemma-firewall"

    Push-Location $mcpDir
    try {
        if (-not $SkipInstall) {
            npm install
        }

        Write-Host "Running legacy token-based Lemma Firewall review suite..."
        node run-tests.js
        node run-interaction-tests.js
        node run-lemma-firewall-conformance.js
    }
    finally {
        Pop-Location
    }
    return
}

if ([string]::IsNullOrWhiteSpace($CredentialFile)) {
    $CredentialFile = $defaultProofPath
}

if (-not (Test-Path $CredentialFile)) {
    throw "Proof credential file not found at $CredentialFile. Run scripts\setup_lemma_firewall_authz_seconds.ps1 first."
}

function Invoke-LemmaCliJson {
    param(
        [string]$CliPath,
        [string[]]$CliArgs
    )
    $raw = (& python $CliPath @CliArgs)
    $exitCode = $LASTEXITCODE
    $parsed = $null
    try {
        $parsed = ($raw | Out-String | ConvertFrom-Json)
    } catch {
        $parsed = $null
    }
    return @{
        exit_code = $exitCode
        raw = $raw
        parsed = $parsed
    }
}

$credentialJson = (Get-Content $CredentialFile -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($credentialJson)) {
    throw "Proof credential file is empty: $CredentialFile"
}
$credentialObj = $null
try {
    $credentialObj = $credentialJson | ConvertFrom-Json
} catch {
    throw "Proof credential file must contain valid JSON object: $CredentialFile"
}
if ($null -eq $credentialObj) {
    throw "Proof credential file parsed to null object: $CredentialFile"
}
$exchangeBody = @{
    credential = $credentialObj
}
if ($credentialObj.credentialSubject -and $credentialObj.credentialSubject.siteId) {
    $exchangeBody.site_id = [string]$credentialObj.credentialSubject.siteId
}

Write-Host "Running proof-first Lemma Firewall review checks..."

Write-Host "Step 1/3: Exchange proof through Authz API"
$exchangeResp = Invoke-RestMethod -Method POST -Uri "$LemmaUrl/api/auth/exchange-proof" `
    -ContentType "application/json" `
    -Body ($exchangeBody | ConvertTo-Json -Depth 30 -Compress) `
    -TimeoutSec 45
if (-not $exchangeResp.success) {
    throw "Proof exchange failed."
}

Write-Host "Step 2/3: Run proof-native latency gate"
$latencyArgs = @(
    (Join-Path $repoRoot "scripts\lemma_cli.py"),
    "authz-latency",
    "--api-base", $LemmaUrl,
    "--auth-mode", "proof",
    "--proof-file", $CredentialFile,
    "--requests", "20",
    "--warmup", "3",
    "--budget-p95-ms", "80",
    "--e2e-budget-p95-ms", "500",
    "--json"
)
& python @latencyArgs | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Proof-native latency gate failed (exit=$LASTEXITCODE)."
}

Write-Host "Step 3/3: Run proof login/status smoke"
$cliPath = (Join-Path $repoRoot "scripts\lemma_cli.py")
$loginArgs = @(
    $cliPath,
    "login",
    "--api-base", $LemmaUrl,
    "--credential-file", $CredentialFile,
    "--non-interactive",
    "--json"
)
$loginResult = Invoke-LemmaCliJson -CliPath $cliPath -CliArgs $loginArgs[1..($loginArgs.Count - 1)]
if ($loginResult.raw) {
    $loginResult.raw | Out-Host
}
if ($loginResult.exit_code -ne 0) {
    $unlockRequired = $false
    if ($loginResult.parsed -and $loginResult.parsed.error_code -eq "E_LOGIN_FAILED") {
        if ($loginResult.parsed.response -and $loginResult.parsed.response.error -eq "wallet_unlock_required") {
            $unlockRequired = $true
        }
    }
    if ($unlockRequired) {
        Write-Host "Wallet login requires an interactive browser wallet session cookie."
        Write-Host "Proof-first checks already passed (exchange + latency), so continuing without forcing fresh passkey."
        Write-Host "Use lemma session start/status only when you explicitly want interactive wallet-gated actions."
    } else {
        throw "Proof login check failed (exit=$($loginResult.exit_code))."
    }
}

$statusArgs = @(
    $cliPath,
    "auth-status",
    "--api-base", $LemmaUrl,
    "--json"
)
& python @statusArgs | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host "Auth-status did not return an active local session; non-fatal for proof-first review."
}

Write-Host "Proof-first Lemma Firewall review completed."
