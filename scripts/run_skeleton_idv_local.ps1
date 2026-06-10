param(
    [string]$HerokuApp = "lemma-staging",
    [switch]$Handoff,
    [int]$Port = 0,
    [switch]$SkipServer
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$argsList = @("scripts/run_skeleton_idv_local.py", "--heroku-app", $HerokuApp)
if ($Handoff) { $argsList += "--handoff" }
if ($Port -gt 0) { $argsList += @("--port", "$Port") }
if ($SkipServer) { $argsList += "--skip-server" }

python @argsList
exit $LASTEXITCODE
