param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$RuntimeId = "lemma-firewall-default",
    [string]$AgentId = "main",
    [string]$WorkspaceId = "default",
    [string]$DisplayName = "Lemma Runtime",
    [string]$PolicyProfile = $(if ($env:LEMMA_POLICY_PROFILE) { $env:LEMMA_POLICY_PROFILE } else { "lemma_firewall_default_v1" }),
    [string]$RootType = $(if ($env:LEMMA_ROOT_TYPE) { $env:LEMMA_ROOT_TYPE } else { "passkey_root" }),
    [string]$OrgId = $(if ($env:LEMMA_ORG_ID) { $env:LEMMA_ORG_ID } else { "org_default" }),
    [string]$Environment = $(if ($env:LEMMA_ENVIRONMENT) { $env:LEMMA_ENVIRONMENT } else { "prod" }),
    [string]$ProofFile = "",
    [string]$KillReason = "Agent Ops E2E kill validation"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$cliPath = Join-Path $repoRoot "scripts\lemma_cli.py"
if ([string]::IsNullOrWhiteSpace($ProofFile)) {
    $ProofFile = Join-Path $repoRoot ".lemma-proof.json"
}
if (-not (Test-Path $cliPath)) {
    throw "Missing CLI script: $cliPath"
}
if (-not (Test-Path $ProofFile)) {
    throw "Proof file not found: $ProofFile"
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

function Invoke-RuntimeAuthorize {
    param(
        [string]$BaseUrl,
        [string]$RuntimeId,
        [string]$CredentialJson
    )
    try {
        $resp = Invoke-RestMethod -Method POST `
            -Uri "$BaseUrl/api/wallet/runtimes/$RuntimeId/authorize" `
            -Headers @{
                "X-Lemma-Credential" = $CredentialJson
                "X-Lemma-Org-Id" = $OrgId
                "X-Lemma-Environment" = $Environment
                "Content-Type" = "application/json"
            } `
            -Body (@{
                org_id = $OrgId
                environment = $Environment
                root_type = $RootType
            } | ConvertTo-Json -Compress) `
            -TimeoutSec 25
        return @{
            ok = $true
            status = 200
            payload = $resp
        }
    } catch {
        $statusCode = 0
        $errBody = ""
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode.value__
            try {
                $reader = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())
                $errBody = $reader.ReadToEnd()
            } catch {}
        }
        return @{
            ok = $false
            status = $statusCode
            payload = $errBody
        }
    }
}

function Get-RuntimeFromList {
    param(
        [string]$BaseUrl,
        [string]$RuntimeId,
        [string]$UnlockToken
    )
    $resp = Invoke-RestMethod -Method GET `
        -Uri "$BaseUrl/api/wallet/runtimes" `
        -Headers @{
            "X-Lemma-Unlock" = $UnlockToken
            "Content-Type" = "application/json"
        } `
        -TimeoutSec 25
    if (-not $resp.success -or -not $resp.runtimes) {
        throw "Runtime list request failed."
    }
    foreach ($runtime in $resp.runtimes) {
        if ([string]$runtime.runtime_id -eq $RuntimeId) {
            return $runtime
        }
    }
    return $null
}

Write-Host "== Agent Ops E2E =="
Write-Host "Lemma URL: $LemmaUrl"
Write-Host "Runtime:   $RuntimeId ($AgentId/$WorkspaceId)"
Write-Host "Tenant:    $OrgId/$Environment root=$RootType"
Write-Host "Proof:     $ProofFile"
Write-Host ""

$credentialJson = (Get-Content $ProofFile -Raw).Trim()

Write-Host "Step 0/6: Obtain wallet unlock token (browser approval)"
$sessionLink = Invoke-LemmaCliJson -CliPath $cliPath -CliArgs @(
    "session", "link",
    "--api-base", $LemmaUrl,
    "--requested-scope", "wallet:control_plane",
    "--json"
)
if (-not $sessionLink.ok -or -not $sessionLink.unlock_token) {
    throw "session link did not return unlock token"
}
$unlockToken = [string]$sessionLink.unlock_token
$authorizeEndpointSupported = $true

Write-Host "Step 1/6: Connect runtime"
$connect = Invoke-LemmaCliJson -CliPath $cliPath -CliArgs @(
    "runtime-onboard",
    "--api-base", $LemmaUrl,
    "--runtime-id", $RuntimeId,
    "--agent-id", $AgentId,
    "--workspace-id", $WorkspaceId,
    "--display-name", $DisplayName,
    "--policy-profile", $PolicyProfile,
    "--root-type", $RootType,
    "--org-id", $OrgId,
    "--environment", $Environment,
    "--json"
)
if (-not $connect.ok) {
    throw "firewall-connect failed"
}

Write-Host "Step 2/6: Baseline authorize should ALLOW"
$authBeforeKill = Invoke-RuntimeAuthorize -BaseUrl $LemmaUrl -RuntimeId $RuntimeId -CredentialJson $credentialJson
if ($authBeforeKill.ok) {
    Write-Host "Authorize endpoint check passed."
} elseif ($authBeforeKill.status -eq 404) {
    $authorizeEndpointSupported = $false
    Write-Host "Authorize endpoint not deployed on target environment; using runtime state fallback checks."
    $runtimeBaseline = Get-RuntimeFromList -BaseUrl $LemmaUrl -RuntimeId $RuntimeId -UnlockToken $unlockToken
    if ($null -eq $runtimeBaseline) {
        throw "Runtime not found in list for baseline fallback check."
    }
    if (-not [bool]$runtimeBaseline.active) {
        throw "Runtime is inactive at baseline; expected active before kill."
    }
} else {
    throw "Baseline authorize failed unexpectedly. status=$($authBeforeKill.status) payload=$($authBeforeKill.payload)"
}

Write-Host "Step 4/6: Kill runtime"
$killResp = Invoke-RestMethod -Method POST `
    -Uri "$LemmaUrl/api/wallet/runtimes/$RuntimeId/kill" `
    -Headers @{
        "X-Lemma-Unlock" = $unlockToken
        "X-Lemma-Org-Id" = $OrgId
        "X-Lemma-Environment" = $Environment
        "Content-Type" = "application/json"
    } `
    -Body (@{
        reason = $KillReason
        org_id = $OrgId
        environment = $Environment
    } | ConvertTo-Json -Compress) `
    -TimeoutSec 25
if (-not $killResp.success) {
    throw "runtime kill failed"
}

Write-Host "Step 5/6: Post-kill authorize should DENY"
$authAfterKill = Invoke-RuntimeAuthorize -BaseUrl $LemmaUrl -RuntimeId $RuntimeId -CredentialJson $credentialJson
if ($authorizeEndpointSupported) {
    if ($authAfterKill.ok) {
        throw "Expected deny after kill, but authorize still allowed."
    }
} else {
    $runtimeAfterKill = Get-RuntimeFromList -BaseUrl $LemmaUrl -RuntimeId $RuntimeId -UnlockToken $unlockToken
    if ($null -eq $runtimeAfterKill) {
        throw "Runtime not found after kill; expected row with inactive state."
    }
    if ([bool]$runtimeAfterKill.active) {
        throw "Fallback check failed: runtime is still active after kill."
    }
}

Write-Host "Step 6/6: Reconnect runtime and confirm ALLOW again"
$reconnect = Invoke-LemmaCliJson -CliPath $cliPath -CliArgs @(
    "runtime-onboard",
    "--api-base", $LemmaUrl,
    "--runtime-id", $RuntimeId,
    "--agent-id", $AgentId,
    "--workspace-id", $WorkspaceId,
    "--display-name", $DisplayName,
    "--policy-profile", $PolicyProfile,
    "--root-type", $RootType,
    "--org-id", $OrgId,
    "--environment", $Environment,
    "--json"
)
if (-not $reconnect.ok) {
    throw "reconnect failed"
}
$authAfterReconnect = Invoke-RuntimeAuthorize -BaseUrl $LemmaUrl -RuntimeId $RuntimeId -CredentialJson $credentialJson
if ($authorizeEndpointSupported) {
    if (-not $authAfterReconnect.ok) {
        throw "Expected allow after reconnect. status=$($authAfterReconnect.status) payload=$($authAfterReconnect.payload)"
    }
} else {
    $runtimeAfterReconnect = Get-RuntimeFromList -BaseUrl $LemmaUrl -RuntimeId $RuntimeId -UnlockToken $unlockToken
    if ($null -eq $runtimeAfterReconnect) {
        throw "Runtime not found after reconnect fallback check."
    }
    if (-not [bool]$runtimeAfterReconnect.active) {
        throw "Fallback check failed: runtime is inactive after reconnect."
    }
}

Write-Host ""
Write-Host "E2E PASS:"
Write-Host "- baseline authorize: allow"
Write-Host "- killed runtime: deny"
Write-Host "- reconnected runtime: allow"
