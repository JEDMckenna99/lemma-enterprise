param(
    [string]$BaseUrl = "https://lemma.id",
    [string]$OutputDir = "docs/launch-evidence",
    [string]$ProofFixturePath = "",
    [string]$PlatformApiKey = ""
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$smokeOut = Join-Path $OutputDir "$stamp-post-deploy-smoke.txt"
$contractOut = Join-Path $OutputDir "$stamp-post-deploy-auth-contract.txt"
$scopeMatrixOut = Join-Path $OutputDir "$stamp-post-deploy-auth-scope-matrix.txt"
$transportOut = Join-Path $OutputDir "$stamp-post-deploy-transport.txt"
$originOut = Join-Path $OutputDir "$stamp-post-deploy-origin.txt"
$summaryOut = Join-Path $OutputDir "$stamp-post-deploy-summary.md"

Write-Output "Post-deploy launch gate run"
Write-Output "Base URL: $BaseUrl"
Write-Output "Timestamp: $(Get-Date -Format o)"
Write-Output ""

function Append-Line {
    param(
        [string]$Path,
        [string]$Text
    )
    $Text | Out-File -FilePath $Path -Encoding utf8 -Append
}

function Run-CurlCapture {
    param(
        [string[]]$CurlArgs,
        [string]$OutputPath,
        [string]$Label
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & curl.exe @CurlArgs 2>&1 | Out-File -FilePath $OutputPath -Append -Encoding utf8
        Append-Line -Path $OutputPath -Text "exit_code=$LASTEXITCODE"
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    # Don't hard-fail here because some probes intentionally fail (e.g. TLS1.1).
    Write-Output "$Label exit_code=$LASTEXITCODE"
}

# 1) Core smoke checks
python scripts/launch_gate_smoke_ci.py | Tee-Object -FilePath $smokeOut

# 1b) Auth contract checks (baseline always, strict when fixture provided)
$env:LEMMA_BASE_URL = $BaseUrl
if ($ProofFixturePath) {
    $env:LEMMA_PROOF_FIXTURE_PATH = $ProofFixturePath
    $env:LEMMA_STRICT_POSITIVE = "1"
} else {
    Remove-Item Env:LEMMA_PROOF_FIXTURE_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:LEMMA_STRICT_POSITIVE -ErrorAction SilentlyContinue
}

# Prefer explicit param, then existing env var.
if ($PlatformApiKey) {
    $env:LEMMA_PLATFORM_API_KEY = $PlatformApiKey
}
python scripts/proof_exchange_contract_check.py | Tee-Object -FilePath $contractOut

# 1c) Scope matrix checks (requires platform API key)
if ($env:LEMMA_PLATFORM_API_KEY) {
    python scripts/auth_scope_matrix_check.py | Tee-Object -FilePath $scopeMatrixOut
} else {
    "Scope matrix skipped: set -PlatformApiKey or LEMMA_PLATFORM_API_KEY" | Out-File -FilePath $scopeMatrixOut -Encoding utf8
    Write-Output "Scope matrix skipped (no platform API key provided)."
}

# 2) Transport/TLS checks
"Transport/TLS checks: $(Get-Date -Format o)" | Out-File -FilePath $transportOut -Encoding utf8
"# HTTP to HTTPS redirect" | Out-File -FilePath $transportOut -Append -Encoding utf8
Run-CurlCapture -CurlArgs @("-I","-L","--max-redirs","5",($BaseUrl -replace '^https://','http://')) -OutputPath $transportOut -Label "redirect_check"
"" | Out-File -FilePath $transportOut -Append -Encoding utf8
"# Force old TLS (expect failure if TLS1.2+ only)" | Out-File -FilePath $transportOut -Append -Encoding utf8
Run-CurlCapture -CurlArgs @("-I","--tls-max","1.1",$BaseUrl) -OutputPath $transportOut -Label "tls11_check"
"" | Out-File -FilePath $transportOut -Append -Encoding utf8
"# Force TLS1.2 (expect success)" | Out-File -FilePath $transportOut -Append -Encoding utf8
Run-CurlCapture -CurlArgs @("-I","--tlsv1.2",$BaseUrl) -OutputPath $transportOut -Label "tls12_check"

# 3) Origin/CORS checks (passkey auth begin)
"Origin/CORS checks: $(Get-Date -Format o)" | Out-File -FilePath $originOut -Encoding utf8
function TestReq($method,$url,$origin,$body){
    try {
        $headers=@{Origin=$origin}
        if($method -eq 'OPTIONS'){
            $headers['Access-Control-Request-Method']='POST'
            $headers['Access-Control-Request-Headers']='content-type'
        }

        if($method -eq 'POST'){
            $resp=Invoke-WebRequest -Uri $url -Method POST -Headers $headers -ContentType 'application/json' -Body $body -UseBasicParsing
        } elseif($method -eq 'OPTIONS'){
            $resp=Invoke-WebRequest -Uri $url -Method OPTIONS -Headers $headers -UseBasicParsing
        } else {
            $resp=Invoke-WebRequest -Uri $url -Method GET -Headers $headers -UseBasicParsing
        }

        Append-Line -Path $originOut -Text "$method $url Origin=$origin -> $($resp.StatusCode)"
        Append-Line -Path $originOut -Text "  ACAO=$($resp.Headers['Access-Control-Allow-Origin'])"
        Append-Line -Path $originOut -Text "  ACAC=$($resp.Headers['Access-Control-Allow-Credentials'])"
    } catch {
        $status='ERR'
        $acao=''
        $acac=''
        if($_.Exception.Response){
            $status=$_.Exception.Response.StatusCode.value__
            $acao=$_.Exception.Response.Headers['Access-Control-Allow-Origin']
            $acac=$_.Exception.Response.Headers['Access-Control-Allow-Credentials']
        }
        Append-Line -Path $originOut -Text "$method $url Origin=$origin -> $status"
        Append-Line -Path $originOut -Text "  ACAO=$acao"
        Append-Line -Path $originOut -Text "  ACAC=$acac"
    }
    Append-Line -Path $originOut -Text ""
}

$authnUrl="$BaseUrl/api/passkey/authenticate/begin"
TestReq 'OPTIONS' $authnUrl 'https://lemma.id' '{}'
TestReq 'OPTIONS' $authnUrl 'https://evil.example' '{}'
TestReq 'POST' $authnUrl 'https://lemma.id' '{}'
TestReq 'POST' $authnUrl 'https://evil.example' '{}'

# 4) Summary artifact
@"
# Post-Deploy Launch Gate Summary

- Base URL: \`$BaseUrl\`
- Timestamp: $(Get-Date -Format o)
- Artifacts:
  - \`$smokeOut\`
  - \`$contractOut\`
  - \`$scopeMatrixOut\`
  - \`$transportOut\`
  - \`$originOut\`

## Pass Conditions

- Smoke script exits successfully.
- Auth contract script exits successfully (strict positive when fixture provided).
- Scope matrix script exits successfully when platform API key is provided.
- HTTP redirects to HTTPS, TLS <=1.1 handshake fails, TLS1.2 succeeds.
- Allowed origin returns ACAO for passkey auth begin, disallowed origin does not receive credentialed ACAO on POST.

## Manual Follow-up Required

- Browser/device matrix for passkey registration + algorithm capture.
- Revocation propagation test: revoke credential in deployed build, then verify deny behavior after sync.
"@ | Out-File -FilePath $summaryOut -Encoding utf8

Write-Output "Artifacts generated:"
Write-Output " - $smokeOut"
Write-Output " - $contractOut"
Write-Output " - $scopeMatrixOut"
Write-Output " - $transportOut"
Write-Output " - $originOut"
Write-Output " - $summaryOut"

