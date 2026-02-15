param(
    [string]$LemmaUrl = "https://lemma.id",
    [string]$Token = "",
    [int]$Samples = 15
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Token)) {
    $tokenPath = Join-Path $repoRoot ".lemma-agent-token"
    if (Test-Path $tokenPath) {
        $Token = (Get-Content $tokenPath -Raw).Trim()
    }
}

if ([string]::IsNullOrWhiteSpace($Token) -or -not $Token.StartsWith("lm_agent_")) {
    throw "Valid lm_agent token required (pass -Token or populate .lemma-agent-token)."
}

$latencies = @()
$success = 0
$failed = 0

for ($i = 0; $i -lt $Samples; $i++) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-RestMethod -Uri "$LemmaUrl/api/agent/validate" -Method Post -Headers @{
            "X-Agent-Token" = $Token
            "Content-Type" = "application/json"
        }
        $sw.Stop()
        $latencies += $sw.ElapsedMilliseconds
        if ($resp.valid -eq $true) { $success++ } else { $failed++ }
    } catch {
        $sw.Stop()
        $latencies += $sw.ElapsedMilliseconds
        $failed++
    }
    Start-Sleep -Milliseconds 150
}

$sorted = $latencies | Sort-Object
$idx95 = [Math]::Floor(($sorted.Count - 1) * 0.95)
$p95 = $sorted[$idx95]
$avg = [Math]::Round((($latencies | Measure-Object -Average).Average), 2)
$availability = [Math]::Round(($success / $Samples) * 100, 2)

$ts = (Get-Date).ToString("yyyy-MM-dd-HHmmss")
$out = Join-Path $repoRoot "docs\launch-evidence\2026-02-15-standalone-slo-snapshot-$ts.md"

@"
# Standalone SLO Snapshot

Timestamp: $(Get-Date -Format o)  
Target: $LemmaUrl  
Samples: $Samples

- Validate availability: $availability% ($success/$Samples)
- Validate latency avg: $avg ms
- Validate latency p95: $p95 ms

Notes:
- This snapshot measures `/api/agent/validate` request behavior from this operator environment.
- Revocation deny p95 should be measured using the revocation drill workflow.
"@ | Set-Content -Path $out -Encoding UTF8

Write-Host "Wrote SLO snapshot:" $out
