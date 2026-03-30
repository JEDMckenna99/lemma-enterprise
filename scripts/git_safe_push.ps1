param(
    [Parameter(Mandatory = $true)]
    [string]$Message,

    [Parameter(Mandatory = $true)]
    [string[]]$Files,

    [string]$GithubRemote = "github",
    [string]$HerokuRemote = "production",
    [string]$HerokuRef = "HEAD:main",

    [switch]$PushGithub,
    [switch]$PushHeroku,
    [switch]$NoCommit
)

$ErrorActionPreference = "Stop"

function Normalize-PathString([string]$p) {
    return ($p -replace "\\", "/").Trim()
}

if (-not $PushGithub -and -not $PushHeroku) {
    $PushGithub = $true
    $PushHeroku = $true
}

$null = git rev-parse --is-inside-work-tree

# Start from a known staging state so previous agents do not leak files into this commit.
git restore --staged . | Out-Null

$normalizedRequested = @{}
foreach ($file in $Files) {
    $normalizedRequested[(Normalize-PathString $file)] = $true
}

git add -- @Files

$staged = @(git diff --staged --name-only)
if ($staged.Count -eq 0) {
    throw "No staged changes for requested file list."
}

$normalizedStaged = @($staged | ForEach-Object { Normalize-PathString $_ })
$unexpected = @($normalizedStaged | Where-Object { -not $normalizedRequested.ContainsKey($_) })
if ($unexpected.Count -gt 0) {
    throw ("Unexpected staged files detected: " + ($unexpected -join ", "))
}

Write-Host "Staged files:"
$staged | ForEach-Object { Write-Host " - $_" }

if (-not $NoCommit) {
    git commit -m $Message
}

if ($PushGithub) {
    git push $GithubRemote HEAD
}

if ($PushHeroku) {
    git push $HerokuRemote $HerokuRef
}

