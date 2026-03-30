param(
    [string]$BaseUrl = "https://lemma.id",
    [string]$OutputDir = "docs/launch-evidence",
    [string]$RuntimeId = "lemma-firewall-default",
    [string]$ProofFile = ".lemma-proof.json",
    [string]$OrgId = $(if ($env:LEMMA_ORG_ID) { $env:LEMMA_ORG_ID } else { "org_default" }),
    [string]$Environment = $(if ($env:LEMMA_ENVIRONMENT) { $env:LEMMA_ENVIRONMENT } else { "prod" }),
    [string]$RootType = $(if ($env:LEMMA_ROOT_TYPE) { $env:LEMMA_ROOT_TYPE } else { "passkey_root" }),
    [switch]$SkipLocal,
    [switch]$SkipLive
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$jsonOut = Join-Path $OutputDir "$stamp-pilot-release-gates.json"
$mdOut = Join-Path $OutputDir "$stamp-pilot-release-gates.md"

$results = [ordered]@{
    base_url = $BaseUrl
    runtime_id = $RuntimeId
    org_id = $OrgId
    environment = $Environment
    root_type = $RootType
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    local = @()
    live = @()
    ok = $true
}

function Add-Result {
    param(
        [string]$Track,
        [string]$Name,
        [int]$ExitCode,
        [string]$Artifact
    )
    $ok = ($ExitCode -eq 0)
    $entry = [ordered]@{
        name = $Name
        ok = $ok
        exit_code = $ExitCode
        artifact = $Artifact
    }
    if ($Track -eq "local") {
        $results.local += $entry
    } else {
        $results.live += $entry
    }
    if (-not $ok) {
        $results.ok = $false
    }
}

if (-not $SkipLocal) {
    python -m pytest tests/test_agent_ops_enterprise_hardening.py tests/test_agent_control_plane_buildout.py tests/test_tenant_context_enforcement.py
    Add-Result -Track "local" -Name "targeted_pytest_matrix" -ExitCode $LASTEXITCODE -Artifact "stdout"
}

if (-not $SkipLive) {
    $e2eOut = Join-Path $OutputDir "$stamp-pilot-agent-ops-e2e.txt"
    powershell -ExecutionPolicy Bypass -File "scripts/run_agent_ops_e2e.ps1" `
        -LemmaUrl $BaseUrl -RuntimeId $RuntimeId -ProofFile $ProofFile -OrgId $OrgId -Environment $Environment -RootType $RootType | Tee-Object -FilePath $e2eOut
    Add-Result -Track "live" -Name "agent_ops_e2e" -ExitCode $LASTEXITCODE -Artifact $e2eOut

    $alertsOut = Join-Path $OutputDir "$stamp-pilot-agent-ops-alerts.txt"
    powershell -ExecutionPolicy Bypass -File "scripts/run_agent_ops_alerts_check.ps1" `
        -LemmaUrl $BaseUrl -RuntimeId $RuntimeId -OrgId $OrgId -Environment $Environment | Tee-Object -FilePath $alertsOut
    Add-Result -Track "live" -Name "alerts_check" -ExitCode $LASTEXITCODE -Artifact $alertsOut

    $povOut = Join-Path $OutputDir "$stamp-pilot-pov-loops.txt"
    python scripts/run_agent_ops_pov_loops.py `
        --api-base $BaseUrl `
        --runtime-id $RuntimeId `
        --proof-file $ProofFile `
        --org-id $OrgId `
        --environment $Environment `
        --root-type $RootType `
        --output-dir $OutputDir | Tee-Object -FilePath $povOut
    Add-Result -Track "live" -Name "pov_demo_loops" -ExitCode $LASTEXITCODE -Artifact $povOut
}

$results | ConvertTo-Json -Depth 8 | Out-File -FilePath $jsonOut -Encoding utf8

$md = @()
$md += "# Pilot Release Gates"
$md += ""
$md += "- Base URL: $BaseUrl"
$md += "- Runtime: $RuntimeId"
$md += "- Tenant: $OrgId/$Environment root $RootType"
$md += "- Overall: " + ($(if ($results.ok) { "PASS" } else { "FAIL" }))
$md += ""
$md += "## Local gates"
foreach ($entry in $results.local) {
    $md += "- $($entry.name): " + ($(if ($entry.ok) { "PASS" } else { "FAIL" })) + " (exit=$($entry.exit_code))"
}
$md += ""
$md += "## Live gates"
foreach ($entry in $results.live) {
    $md += "- $($entry.name): " + ($(if ($entry.ok) { "PASS" } else { "FAIL" })) + " (exit=$($entry.exit_code)) artifact $($entry.artifact)"
}
$md += ""
$md += "- JSON artifact: $jsonOut"
$md | Out-File -FilePath $mdOut -Encoding utf8

Write-Host "pilot_release_gates_json=$jsonOut"
Write-Host "pilot_release_gates_md=$mdOut"
if (-not $results.ok) { exit 1 }
