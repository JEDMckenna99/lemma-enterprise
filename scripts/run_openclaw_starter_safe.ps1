param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ForwardArgs
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$targetScript = Join-Path $repoRoot "scripts\run_lemma_firewall_starter_safe.ps1"

if (-not (Test-Path $targetScript)) {
    throw "Missing target script: $targetScript"
}

& powershell -ExecutionPolicy Bypass -File $targetScript @ForwardArgs
exit $LASTEXITCODE
