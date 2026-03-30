param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$CredentialFile = "",
    [string]$PlatformApiKey = "",
    [string]$UserEmail = "",
    [switch]$UseBreakGlassSelfIssue,
    [string]$SiteId = "lemma.id",
    [string]$SiteDomain = "lemma.id",
    [string]$PermissionLevel = "super_admin",
    [switch]$StartFirewall,
    [string]$FirewallPolicyFile = "",
    [switch]$SkipRuntimeConnect,
    [string]$RuntimeId = "lemma-firewall-default",
    [string]$AgentId = "main",
    [string]$WorkspaceId = "default",
    [string]$RuntimeDisplayName = "Lemma Firewall Runtime",
    [ValidateSet("starter_safe", "balanced", "advanced")]
    [string]$SecurityProfile = "starter_safe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$defaultCredentialPath = Join-Path $repoRoot ".lemma-proof.json"
$lemmaFirewallStateDir = if (-not [string]::IsNullOrWhiteSpace($env:LEMMA_FIREWALL_STATE_DIR)) { $env:LEMMA_FIREWALL_STATE_DIR } else { Join-Path $HOME ".lemma-firewall" }
$lemmaFirewallConfigPath = if (-not [string]::IsNullOrWhiteSpace($env:LEMMA_FIREWALL_CONFIG_PATH)) { $env:LEMMA_FIREWALL_CONFIG_PATH } else { Join-Path $lemmaFirewallStateDir "lemma-firewall.json" }

function Set-LemmaFirewallConfigValue {
    param(
        [string]$Path,
        [object]$Object,
        [string]$Value
    )
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }
    $segments = @($Path.Split('.'))
    $cursor = $Object
    for ($i = 0; $i -lt ($segments.Count - 1); $i++) {
        $segment = $segments[$i]
        $existing = $cursor.PSObject.Properties[$segment]
        if ($null -eq $existing -or $null -eq $existing.Value) {
            $child = [pscustomobject]@{}
            $cursor | Add-Member -MemberType NoteProperty -Name $segment -Value $child
            $cursor = $child
        } else {
            $cursor = $existing.Value
        }
    }
    $leaf = $segments[$segments.Count - 1]
    if ($cursor.PSObject.Properties[$leaf]) {
        $cursor.$leaf = $Value
    } else {
        $cursor | Add-Member -MemberType NoteProperty -Name $leaf -Value $Value
    }
}

function Update-LemmaFirewallConfig {
    param(
        [string]$ConfigPath,
        [string]$LemmaUrl,
        [string]$ProofFile,
        [string]$RuntimeId
    )
    $configDir = Split-Path -Parent $ConfigPath
    if (-not (Test-Path $configDir)) {
        New-Item -Path $configDir -ItemType Directory -Force | Out-Null
    }

    $customConfigTarget = -not [string]::IsNullOrWhiteSpace($env:LEMMA_FIREWALL_CONFIG_PATH) -or -not [string]::IsNullOrWhiteSpace($env:LEMMA_FIREWALL_STATE_DIR)

    $lemmaFirewallCmd = Get-Command lemma-firewall -ErrorAction SilentlyContinue
    if ($lemmaFirewallCmd -and -not $customConfigTarget) {
        try {
            & lemma-firewall config set env.vars.LEMMA_BASE_URL $LemmaUrl | Out-Null
            & lemma-firewall config set env.vars.LEMMA_PROOF_FILE $ProofFile | Out-Null
            & lemma-firewall config set env.vars.LEMMA_FIREWALL_RUNTIME_ID $RuntimeId | Out-Null
            Write-Host "Patched Lemma Firewall config via CLI."
            return
        } catch {
            Write-Host "Lemma Firewall CLI config patch failed, falling back to direct file patch."
        }
    } elseif ($customConfigTarget) {
        Write-Host "Custom LEMMA_FIREWALL_CONFIG_PATH/LEMMA_FIREWALL_STATE_DIR detected; using direct file patch (no global CLI config writes)."
    }

    $baseConfig = [pscustomobject]@{}
    if (Test-Path $ConfigPath) {
        try {
            $baseConfig = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        } catch {
            Write-Host "Warning: could not parse Lemma Firewall config as strict JSON ($ConfigPath)."
            Write-Host "If your config is JSON5, run:"
            Write-Host "  lemma-firewall config set env.vars.LEMMA_BASE_URL $LemmaUrl"
            Write-Host "  lemma-firewall config set env.vars.LEMMA_PROOF_FILE $ProofFile"
            Write-Host "  lemma-firewall config set env.vars.LEMMA_FIREWALL_RUNTIME_ID $RuntimeId"
            return
        }
    }

    Set-LemmaFirewallConfigValue -Path "env.vars.LEMMA_BASE_URL" -Object $baseConfig -Value $LemmaUrl
    Set-LemmaFirewallConfigValue -Path "env.vars.LEMMA_PROOF_FILE" -Object $baseConfig -Value $ProofFile
    Set-LemmaFirewallConfigValue -Path "env.vars.LEMMA_FIREWALL_RUNTIME_ID" -Object $baseConfig -Value $RuntimeId
    $updated = $baseConfig | ConvertTo-Json -Depth 20
    Set-Content -Path $ConfigPath -Value $updated
    Write-Host "Patched Lemma Firewall config file:" $ConfigPath
}

function Get-CompactJson([object]$obj) {
    return ($obj | ConvertTo-Json -Depth 20 -Compress)
}

function Invoke-LemmaCliJson {
    param(
        [string]$CliPath,
        [string[]]$CliArgs
    )
    $raw = (& python $CliPath @CliArgs)
    if ($LASTEXITCODE -ne 0) {
        throw "lemma_cli failed (exit=$LASTEXITCODE): $($CliArgs -join ' ')"
    }
    return ($raw | Out-String | ConvertFrom-Json)
}

function Acquire-WalletIssuedCredentialJson {
    param(
        [string]$LemmaUrl,
        [string]$CliPath,
        [string]$SiteId
    )
    Write-Host "No credential file provided. Starting wallet browser approval..."
    $sessionLink = Invoke-LemmaCliJson -CliPath $CliPath -CliArgs @(
        "session", "link",
        "--api-base", $LemmaUrl,
        "--requested-scope", "wallet:control_plane",
        "--json"
    )
    if (-not $sessionLink.ok -or -not $sessionLink.unlock_token) {
        throw "Wallet session-link failed to return unlock token."
    }
    $unlockToken = [string]$sessionLink.unlock_token

    $issueResp = Invoke-RestMethod -Method POST -Uri "$LemmaUrl/api/wallet/runtimes/issue-proof" -Headers @{
        "X-Lemma-Unlock" = $unlockToken
        "Content-Type" = "application/json"
    } -Body (@{ site_id = $SiteId } | ConvertTo-Json -Compress) -TimeoutSec 45
    if (-not $issueResp.success -or -not $issueResp.credential) {
        throw "Wallet-issued proof generation failed."
    }
    return (Get-CompactJson $issueResp.credential)
}

function Resolve-CredentialJson {
    param(
        [string]$LemmaUrl,
        [string]$CredentialFile,
        [string]$CliPath,
        [string]$PlatformApiKey,
        [string]$UserEmail,
        [switch]$UseBreakGlassSelfIssue,
        [string]$SiteId,
        [string]$SiteDomain,
        [string]$PermissionLevel
    )

    if (-not [string]::IsNullOrWhiteSpace($CredentialFile)) {
        if (-not (Test-Path $CredentialFile)) {
            throw "Credential file not found: $CredentialFile"
        }
        return (Get-Content $CredentialFile -Raw).Trim()
    }

    if (-not $UseBreakGlassSelfIssue) {
        return Acquire-WalletIssuedCredentialJson -LemmaUrl $LemmaUrl -CliPath $CliPath -SiteId $SiteId
    }

    if ([string]::IsNullOrWhiteSpace($PlatformApiKey)) {
        $PlatformApiKey = $env:LEMMA_API_KEY
    }
    if ([string]::IsNullOrWhiteSpace($UserEmail)) {
        $UserEmail = $env:LEMMA_ADMIN_EMAIL
    }
    if ([string]::IsNullOrWhiteSpace($PlatformApiKey) -or [string]::IsNullOrWhiteSpace($UserEmail)) {
        throw "Provide -CredentialFile OR both -PlatformApiKey and -UserEmail."
    }

    $issueBody = @{
        site_id = $SiteId
        site_domain = $SiteDomain
        user_email = $UserEmail
        permission_level = $PermissionLevel
    }

    $compactBody = Get-CompactJson $issueBody
    $issueUri = "$LemmaUrl/api/v1/iam/admin/self-issue"
    $headers = @{ "Authorization" = "Bearer $PlatformApiKey"; "Content-Type" = "application/json" }
    try {
        $resp = Invoke-RestMethod -Method POST -Uri $issueUri -Headers $headers -Body $compactBody -TimeoutSec 45
    } catch {
        $fallbackHeaders = @{ "X-API-Key" = $PlatformApiKey; "Content-Type" = "application/json" }
        $resp = Invoke-RestMethod -Method POST -Uri $issueUri -Headers $fallbackHeaders -Body $compactBody -TimeoutSec 45
    }
    if (-not $resp.success -or -not $resp.credential) {
        throw "Self-issue failed. Response did not include credential."
    }
    return (Get-CompactJson $resp.credential)
}

function Test-LemmaCredential {
    param(
        [string]$LemmaUrl,
        [string]$CredentialJson
    )
    $credentialObj = $null
    try {
        $credentialObj = $CredentialJson | ConvertFrom-Json
    } catch {
        throw "Credential JSON is invalid; expected a JSON credential object."
    }
    if ($null -eq $credentialObj) {
        throw "Credential JSON is empty after parsing."
    }
    $siteId = ""
    if ($credentialObj.credentialSubject -and $credentialObj.credentialSubject.siteId) {
        $siteId = [string]$credentialObj.credentialSubject.siteId
    }
    $exchangeBody = @{
        credential = $credentialObj
    }
    if (-not [string]::IsNullOrWhiteSpace($siteId)) {
        $exchangeBody.site_id = $siteId
    }
    $resp = Invoke-RestMethod -Method POST -Uri "$LemmaUrl/api/auth/exchange-proof" `
        -ContentType "application/json" `
        -Body ($exchangeBody | ConvertTo-Json -Depth 30 -Compress) `
        -TimeoutSec 30
    if (-not $resp.success) {
        throw "Credential exchange failed."
    }
}

function Set-LocalFirstSecurityProfileEnv {
    param(
        [string]$Profile
    )
    $normalized = "starter_safe"
    if (-not [string]::IsNullOrWhiteSpace($Profile)) {
        $normalized = $Profile.ToLowerInvariant()
    }
    switch ($normalized) {
        "starter_safe" {
            $env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT = "1"
            $env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED = "1"
            $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = "critical"
            $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = "critical"
            $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = "0"
            $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = "0"
            $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = "0"
            $env:LEMMA_FIREWALL_MAX_STALENESS_HIGH_MS = "120000"
            $env:LEMMA_FIREWALL_MAX_STALENESS_CRITICAL_MS = "10000"
        }
        "balanced" {
            $env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT = "1"
            $env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED = "1"
            $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = "critical"
            $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = "critical"
            $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = "0"
            $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = "1"
            $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = "1"
            $env:LEMMA_FIREWALL_MAX_STALENESS_HIGH_MS = "60000"
            $env:LEMMA_FIREWALL_MAX_STALENESS_CRITICAL_MS = "10000"
        }
        default {
            # Advanced profile keeps local-first enabled but allows richer telemetry.
            $env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT = "1"
            $env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED = "1"
            $env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS = "high,critical"
            $env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS = "high,critical"
            $env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP = "0"
            $env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL = "1"
            $env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY = "1"
            $env:LEMMA_FIREWALL_MAX_STALENESS_HIGH_MS = "30000"
            $env:LEMMA_FIREWALL_MAX_STALENESS_CRITICAL_MS = "10000"
        }
    }
}

Write-Host "== Lemma Firewall proof-first base tier setup =="
Write-Host "Security profile: $SecurityProfile"
Set-LocalFirstSecurityProfileEnv -Profile $SecurityProfile
Write-Host "Step 1/3: Acquire Lemma credential (proof)"
$cli = Join-Path $repoRoot "scripts\lemma_cli.py"
$credentialJson = Resolve-CredentialJson `
    -LemmaUrl $LemmaUrl `
    -CredentialFile $CredentialFile `
    -CliPath $cli `
    -PlatformApiKey $PlatformApiKey `
    -UserEmail $UserEmail `
    -UseBreakGlassSelfIssue:$UseBreakGlassSelfIssue `
    -SiteId $SiteId `
    -SiteDomain $SiteDomain `
    -PermissionLevel $PermissionLevel

Set-Content -Path $defaultCredentialPath -Value $credentialJson -NoNewline
Write-Host "Saved proof credential:" $defaultCredentialPath
Update-LemmaFirewallConfig -ConfigPath $lemmaFirewallConfigPath -LemmaUrl $LemmaUrl -ProofFile $defaultCredentialPath -RuntimeId $RuntimeId

Write-Host "Step 2/3: Validate proof exchange via Authz API"
Test-LemmaCredential -LemmaUrl $LemmaUrl -CredentialJson $credentialJson
Write-Host "Proof exchange succeeded."

Write-Host "Step 3/3: Run CLI authz latency smoke (proof mode)"
$latencyArgs = @(
    $cli,
    "authz-latency",
    "--api-base", $LemmaUrl,
    "--auth-mode", "proof",
    "--proof-file", $defaultCredentialPath,
    "--requests", "8",
    "--warmup", "2",
    "--budget-p95-ms", "80",
    "--e2e-budget-p95-ms", "500",
    "--json"
)
$maxLatencyAttempts = 3
$latencyPassed = $false
for ($attempt = 1; $attempt -le $maxLatencyAttempts; $attempt++) {
    if ($attempt -gt 1) {
        Write-Host "Retrying latency smoke (attempt $attempt/$maxLatencyAttempts)..."
    }
    $latencyRaw = (& python @latencyArgs)
    $latencyExit = $LASTEXITCODE
    $latencyText = ($latencyRaw | Out-String).Trim()
    if (-not [string]::IsNullOrWhiteSpace($latencyText)) {
        Write-Host $latencyText
    }

    $latencyPayload = $null
    try {
        $latencyPayload = $latencyText | ConvertFrom-Json
    } catch {
        $latencyPayload = $null
    }

    if ($latencyExit -eq 0) {
        $latencyPassed = $true
        break
    }

    # Allow transient network or borderline e2e jitter to retry automatically.
    $retryable = $false
    if ($latencyPayload) {
        $retryable = (
            ($latencyPayload.error_code -eq "E_HTTP_FAILED") -or
            ($null -ne $latencyPayload.authz_p95_ms -and [double]$latencyPayload.authz_p95_ms -lt 5.0)
        )
    }
    if (-not $retryable -or $attempt -ge $maxLatencyAttempts) {
        throw "lemma_cli authz-latency failed (exit=$latencyExit)."
    }
    Start-Sleep -Seconds 2
}
if (-not $latencyPassed) {
    throw "lemma_cli authz-latency failed after retries."
}

if (-not $SkipRuntimeConnect) {
    Write-Host "Step 4/4: Connect Lemma Firewall runtime to wallet controls"
    $connectArgs = @(
        $cli,
        "firewall-connect",
        "--api-base", $LemmaUrl,
        "--runtime-id", $RuntimeId,
        "--agent-id", $AgentId,
        "--workspace-id", $WorkspaceId,
        "--display-name", $RuntimeDisplayName,
        "--json"
    )
    & python @connectArgs | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "lemma_cli firewall-connect failed (exit=$LASTEXITCODE)."
    }
}

Write-Host ""
Write-Host "Ready. Proof-first Lemma Firewall settings:"
Write-Host "  LEMMA_BASE_URL=$LemmaUrl"
Write-Host "  LEMMA_PROOF_FILE=$defaultCredentialPath"
Write-Host "  LEMMA_FIREWALL_RUNTIME_ID=$RuntimeId"
Write-Host "  LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT=$($env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT)"
Write-Host "  LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED=$($env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED)"
Write-Host "  LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS=$($env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS)"
Write-Host "  LEMMA_FIREWALL_PROOF_REQUIRED_TIERS=$($env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS)"
Write-Host "  LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP=$($env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP)"
Write-Host "  LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL=$($env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL)"
Write-Host "  LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY=$($env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY)"
Write-Host ""
Write-Host "Optional AIM firewall start (proof mode):"
Write-Host "  `$env:LEMMA_BASE_URL='$LemmaUrl'"
Write-Host "  `$env:LEMMA_PROOF_FILE='$defaultCredentialPath'"
Write-Host "  `$env:LEMMA_FIREWALL_RUNTIME_ID='$RuntimeId'"
Write-Host "  `$env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT='$($env:LEMMA_FIREWALL_LOCAL_PROOF_ENFORCEMENT)'"
Write-Host "  `$env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED='$($env:LEMMA_FIREWALL_CONTROL_PLANE_SYNC_ENABLED)'"
Write-Host "  `$env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS='$($env:LEMMA_FIREWALL_RUNTIME_AUTHORIZE_REQUIRED_TIERS)'"
Write-Host "  `$env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS='$($env:LEMMA_FIREWALL_PROOF_REQUIRED_TIERS)'"
Write-Host "  `$env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP='$($env:LEMMA_FIREWALL_REQUIRE_FRESH_PASSKEY_STEPUP)'"
Write-Host "  `$env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL='$($env:LEMMA_FIREWALL_ONLINE_CHECK_ON_STALE_NONCRITICAL)'"
Write-Host "  `$env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY='$($env:LEMMA_FIREWALL_LOG_EXTERNAL_ACTIVITY)'"
Write-Host "  python scripts\lemma_firewall.py"

if ($StartFirewall) {
    Write-Host ""
    Write-Host "Starting AIM firewall with proof auth..."
    $env:LEMMA_BASE_URL = $LemmaUrl
    $env:LEMMA_PROOF_FILE = $defaultCredentialPath
    $env:LEMMA_FIREWALL_RUNTIME_ID = $RuntimeId
    if (-not [string]::IsNullOrWhiteSpace($FirewallPolicyFile)) {
        $env:LEMMA_FIREWALL_POLICY_FILE = $FirewallPolicyFile
    }
    & python (Join-Path $repoRoot "scripts\lemma_firewall.py")
}
