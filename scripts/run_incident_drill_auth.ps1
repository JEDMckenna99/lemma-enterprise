param(
    [string]$BaseUrl = "https://lemma.id",
    [string]$OutputDir = "ops/evidence/launch",
    [string]$AppName = "lemma-enterprise",
    [string]$PlatformApiKey = "",
    [string]$ProofFixturePath = "",
    [string]$SimulatedInvalidKey = "invalid_incident_drill_key",
    [switch]$EnableWalletCliLink,
    [switch]$WalletCliNoBrowser,
    [int]$WalletLinkTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

function Resolve-PlatformApiKey {
    param([string]$AppName, [string]$ProvidedKey)
    if ($ProvidedKey) {
        return $ProvidedKey
    }

    $key = (& heroku config:get LEMMA_API_KEY -a $AppName).Trim()
    if (-not $key) {
        $key = (& heroku config:get LEMMA_PLATFORM_API_KEY -a $AppName).Trim()
    }
    if (-not $key) {
        throw "Missing platform API key. Provide -PlatformApiKey or configure LEMMA_API_KEY / LEMMA_PLATFORM_API_KEY in Heroku."
    }
    return $key
}

function Ensure-ProofFixture {
    param(
        [string]$BaseUrl,
        [string]$ApiKey,
        [string]$ExistingFixturePath
    )
    if ($ExistingFixturePath) {
        if (-not (Test-Path $ExistingFixturePath)) {
            throw "Provided ProofFixturePath not found: $ExistingFixturePath"
        }
        return (Resolve-Path $ExistingFixturePath).Path
    }

    $ts = Get-Date -Format "yyyyMMddHHmmss"
    $email = "incident-drill-admin+$ts@lemma.id"
    $headers = @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" }
    $body = @{
        site_id = "lemma.id"
        user_email = $email
        permission_level = "admin"
        expiry_days = 7
    } | ConvertTo-Json -Compress

    $resp = Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/platform/issue-site-permission" -Headers $headers -Body $body -TimeoutSec 60
    if (-not $resp.success -or -not $resp.permission_lemma) {
        throw "Failed to generate trusted proof fixture."
    }

    $fixturePath = Join-Path $env:TEMP "lemma_incident_drill_fixture_$ts.json"
    ($resp.permission_lemma | ConvertTo-Json -Depth 15) | Out-File -FilePath $fixturePath -Encoding ascii
    return $fixturePath
}

function Invoke-GateRun {
    param(
        [string]$Label,
        [string]$BaseUrl,
        [string]$OutputDir,
        [string]$ProofFixturePath,
        [string]$ApiKey
    )

    $runStamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
    $logPath = Join-Path $OutputDir "$runStamp-incident-drill-$Label-gate.txt"
    $gateScript = Join-Path $PSScriptRoot "post_deploy_launch_gate.ps1"

    $shellCmd = Get-Command pwsh.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $shellCmd) {
        $shellCmd = Get-Command powershell.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if (-not $shellCmd) {
        throw "Neither pwsh.exe nor powershell.exe is available on PATH."
    }

    $start = Get-Date
    $exitCode = 0
    $succeeded = $true

    try {
        & $shellCmd.Source -NoProfile -ExecutionPolicy Bypass -File $gateScript -BaseUrl $BaseUrl -OutputDir $OutputDir -ProofFixturePath $ProofFixturePath -PlatformApiKey $ApiKey 2>&1 |
            Tee-Object -FilePath $logPath | Out-Null
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            $succeeded = $false
        }
    } catch {
        $succeeded = $false
        $exitCode = 1
        $_ | Out-File -FilePath $logPath -Append -Encoding utf8
    }
    $end = Get-Date

    return [PSCustomObject]@{
        Label = $Label
        Start = $start
        End = $end
        DurationSeconds = [int][Math]::Round(($end - $start).TotalSeconds)
        Succeeded = $succeeded
        ExitCode = $exitCode
        LogPath = $logPath
    }
}

function Invoke-WalletCliLink {
    param(
        [string]$BaseUrl,
        [switch]$NoBrowser,
        [int]$TimeoutSeconds
    )
    $cliPath = Join-Path $PSScriptRoot "lemma_cli.py"
    if (-not (Test-Path $cliPath)) {
        throw "lemma_cli.py not found at $cliPath"
    }
    $cliArgs = @(
        $cliPath,
        "session",
        "link",
        "--api-base", $BaseUrl,
        "--link-timeout", "$TimeoutSeconds",
        "--timeout", "10",
        "--json"
    )
    if ($NoBrowser) {
        $cliArgs += "--no-browser"
    }
    $output = & python @cliArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Wallet CLI link failed (exit $LASTEXITCODE): $output"
    }
    $raw = ($output -join "`n").Trim()
    if (-not $raw) {
        throw "Wallet CLI link returned empty output."
    }
    try {
        return $raw | ConvertFrom-Json
    } catch {
        throw "Wallet CLI link returned non-JSON output: $raw"
    }
}

function Invoke-WalletAuthProbe {
    param(
        [string]$BaseUrl,
        [string]$UnlockToken
    )
    $headers = @{
        "Content-Type" = "application/json"
        "X-Lemma-Unlock" = $UnlockToken
    }
    try {
        $resp = Invoke-WebRequest -Method POST -Uri "$BaseUrl/api/wallet/retrieve" -Headers $headers -Body "{}" -TimeoutSec 30
        return [PSCustomObject]@{
            StatusCode = [int]$resp.StatusCode
            Ok = [bool]($resp.StatusCode -ne 401)
            Note = "wallet_auth_accepted"
        }
    } catch {
        $statusCode = 0
        try {
            $statusCode = [int]$_.Exception.Response.StatusCode.value__
        } catch {
            $statusCode = 0
        }
        return [PSCustomObject]@{
            StatusCode = $statusCode
            Ok = [bool]($statusCode -ne 401 -and $statusCode -ne 0)
            Note = "wallet_auth_probe_error"
        }
    }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$apiKey = Resolve-PlatformApiKey -AppName $AppName -ProvidedKey $PlatformApiKey
$fixturePath = Ensure-ProofFixture -BaseUrl $BaseUrl -ApiKey $apiKey -ExistingFixturePath $ProofFixturePath
$stamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$walletLinkResult = $null
$walletProbe = $null

if ($EnableWalletCliLink) {
    Write-Output "Running wallet CLI popup link flow..."
    $walletLinkResult = Invoke-WalletCliLink -BaseUrl $BaseUrl -NoBrowser:$WalletCliNoBrowser -TimeoutSeconds $WalletLinkTimeoutSeconds
    if (-not $walletLinkResult.ok -or -not $walletLinkResult.unlock_token) {
        throw "Wallet CLI link did not return unlock token."
    }
    $walletProbe = Invoke-WalletAuthProbe -BaseUrl $BaseUrl -UnlockToken "$($walletLinkResult.unlock_token)"
    if (-not $walletProbe.Ok) {
        throw "Wallet auth probe failed after CLI link (status=$($walletProbe.StatusCode))."
    }
}

Write-Output "Running incident drill baseline gate..."
$baseline = Invoke-GateRun -Label "baseline" -BaseUrl $BaseUrl -OutputDir $OutputDir -ProofFixturePath $fixturePath -ApiKey $apiKey
if (-not $baseline.Succeeded) {
    throw "Baseline gate failed. See log: $($baseline.LogPath)"
}

Write-Output "Running incident drill simulated failure gate..."
$failure = Invoke-GateRun -Label "simulated-failure" -BaseUrl $BaseUrl -OutputDir $OutputDir -ProofFixturePath $fixturePath -ApiKey $SimulatedInvalidKey
if ($failure.Succeeded) {
    throw "Simulated failure unexpectedly passed. Adjust -SimulatedInvalidKey."
}

Write-Output "Running incident drill recovery gate..."
$recovery = Invoke-GateRun -Label "recovery" -BaseUrl $BaseUrl -OutputDir $OutputDir -ProofFixturePath $fixturePath -ApiKey $apiKey
if (-not $recovery.Succeeded) {
    throw "Recovery gate failed. See log: $($recovery.LogPath)"
}

$mttdSeconds = $failure.DurationSeconds
$mttrSeconds = $recovery.DurationSeconds
$evidencePath = Join-Path $OutputDir "$stamp-incident-drill-auth-control-plane.md"

@"
# Incident Drill Evidence (Auth Control-Plane)

- Drill ID: incident-drill-$stamp
- Date (UTC): $((Get-Date).ToUniversalTime().ToString("o"))
- Scenario: A (Auth Control-Plane Outage)
- Base URL: $BaseUrl
- App: $AppName
- Detection source: automated gate failure on simulated invalid key
- MTTD: ${mttdSeconds}s
- MTTR: ${mttrSeconds}s
- Gate rerun result: PASS
- Wallet CLI link enabled: $EnableWalletCliLink
- Wallet auth probe status: $($(if ($walletProbe) { $walletProbe.StatusCode } else { "not-run" }))

## Timeline (UTC)

- Baseline start: $($baseline.Start.ToUniversalTime().ToString("o"))
- Baseline end: $($baseline.End.ToUniversalTime().ToString("o"))
- Failure injection start: $($failure.Start.ToUniversalTime().ToString("o"))
- Failure detected end: $($failure.End.ToUniversalTime().ToString("o"))
- Recovery start: $($recovery.Start.ToUniversalTime().ToString("o"))
- Recovery verified end: $($recovery.End.ToUniversalTime().ToString("o"))

## Command Results

- Baseline gate: exit_code=$($baseline.ExitCode), duration=$($baseline.DurationSeconds)s
- Simulated failure gate: exit_code=$($failure.ExitCode), duration=$($failure.DurationSeconds)s
- Recovery gate: exit_code=$($recovery.ExitCode), duration=$($recovery.DurationSeconds)s

## Artifacts

- Baseline log: $($baseline.LogPath)
- Simulated failure log: $($failure.LogPath)
- Recovery log: $($recovery.LogPath)
- Proof fixture: $fixturePath
- Wallet link result: $($(if ($walletLinkResult) { "ok=$($walletLinkResult.ok), wallet_id=$($walletLinkResult.wallet_id)" } else { "not-run" }))

## Follow-up

- If MTTD > 300s or MTTR > 1200s, open follow-up action items before launch sign-off.
"@ | Out-File -FilePath $evidencePath -Encoding utf8

Write-Output "Incident drill completed."
Write-Output "MTTD=${mttdSeconds}s"
Write-Output "MTTR=${mttrSeconds}s"
Write-Output "Evidence: $evidencePath"
