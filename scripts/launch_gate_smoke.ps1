param(
    [string]$BaseUrl = "https://lemma.id"
)

$ErrorActionPreference = "Stop"

function Invoke-JsonGet {
    param(
        [string]$Url
    )

    $response = Invoke-WebRequest -Uri $Url -Method GET -UseBasicParsing
    $json = $null
    try {
        $json = $response.Content | ConvertFrom-Json
    } catch {
        # Some endpoints may return non-JSON payloads.
    }

    [PSCustomObject]@{
        Url = $Url
        StatusCode = $response.StatusCode
        Json = $json
    }
}

function Invoke-ExpectedFailurePost {
    param(
        [string]$Url,
        [string]$Body
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method POST -ContentType "application/json" -Body $Body -UseBasicParsing
        [PSCustomObject]@{
            Url = $Url
            StatusCode = $response.StatusCode
            Body = $response.Content
        }
    } catch {
        $status = $null
        $body = ""
        if ($_.Exception.Response) {
            $status = $_.Exception.Response.StatusCode.value__
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $body = $reader.ReadToEnd()
        }
        [PSCustomObject]@{
            Url = $Url
            StatusCode = $status
            Body = $body
        }
    }
}

$timestamp = Get-Date -Format o
Write-Output "Launch gate smoke run: $timestamp"
Write-Output "Base URL: $BaseUrl"
Write-Output ""

# Read-only checks for core availability and revocation data.
$readChecks = @(
    "$BaseUrl/",
    "$BaseUrl/api/revocation/bloom-filter",
    "$BaseUrl/api/v1/revocation/list"
)

foreach ($endpoint in $readChecks) {
    $result = Invoke-JsonGet -Url $endpoint
    Write-Output "GET $($result.Url) -> $($result.StatusCode)"

    if ($result.Json -and $null -ne $result.Json.success) {
        $countValue = ""
        if ($null -ne $result.Json.count) {
            $countValue = " count=$($result.Json.count)"
        }
        Write-Output "  success=$($result.Json.success)$countValue"
    }
}

Write-Output ""

# Phase 2.1: the /wallet/bridge iframe endpoint was removed (popup-only verify).

# Expected-failure checks to verify guardrails without mutating production data.
$expectedFailureChecks = @(
    @{ Url = "$BaseUrl/api/wallet/session-sync"; Body = "{}" },
    @{ Url = "$BaseUrl/api/passkey/authenticate/begin"; Body = "{}" },
    @{ Url = "$BaseUrl/api/passkey/register/begin"; Body = '{"email":"launch-gate-check@lemma.id"}' }
)

foreach ($check in $expectedFailureChecks) {
    $result = Invoke-ExpectedFailurePost -Url $check.Url -Body $check.Body
    Write-Output "POST $($result.Url) -> $($result.StatusCode)"
    if ($result.Body) {
        Write-Output "  body=$($result.Body)"
    }
}

