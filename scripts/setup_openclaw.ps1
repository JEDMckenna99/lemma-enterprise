param(
    [string]$Token = "",
    [string]$LemmaUrl = "https://lemma.id",
    [switch]$WriteCursorConfig
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$mcpServerPath = Join-Path $repoRoot "mcp-server\index.js"
$tokenFilePath = Join-Path $repoRoot ".lemma-agent-token"
$generatedConfigPath = Join-Path $repoRoot "mcp-server\openclaw-mcp-config.generated.json"
$cursorConfigPath = Join-Path $repoRoot ".cursor\mcp.json"

if (-not (Test-Path $mcpServerPath)) {
    throw "Missing MCP server entrypoint at $mcpServerPath"
}

if ([string]::IsNullOrWhiteSpace($Token)) {
    if (Test-Path $tokenFilePath) {
        $Token = (Get-Content $tokenFilePath -Raw).Trim()
    }
}

if ([string]::IsNullOrWhiteSpace($Token)) {
    $Token = Read-Host "Enter Lemma agent token (lm_agent_...)"
}

if ([string]::IsNullOrWhiteSpace($Token) -or -not $Token.StartsWith("lm_agent_")) {
    throw "Invalid token format. Expected value starting with 'lm_agent_'."
}

Set-Content -Path $tokenFilePath -Value $Token -NoNewline

$configObject = @{
    mcpServers = @{
        "lemma-openclaw" = @{
            command = "cmd"
            args    = @(
                "/c",
                "node",
                ($mcpServerPath -replace "\\", "\\")
            )
            env     = @{
                LEMMA_URL         = $LemmaUrl
                LEMMA_AGENT_TOKEN = $Token
                OPENCLAW_REQUIRED_AUDIENCE = "openclaw"
            }
        }
    }
}

$configJson = $configObject | ConvertTo-Json -Depth 8
Set-Content -Path $generatedConfigPath -Value $configJson

if ($WriteCursorConfig) {
    $cursorDir = Split-Path -Parent $cursorConfigPath
    if (-not (Test-Path $cursorDir)) {
        New-Item -Path $cursorDir -ItemType Directory | Out-Null
    }
    Set-Content -Path $cursorConfigPath -Value $configJson
    Write-Host "Wrote Cursor MCP config:" $cursorConfigPath
}

Write-Host "Saved token to:" $tokenFilePath
Write-Host "Wrote generated OpenClaw MCP config:" $generatedConfigPath
Write-Host ""
Write-Host "Next:"
Write-Host "1) Use the generated config in OpenClaw/Cursor MCP settings."
Write-Host "2) Run scripts\run_openclaw_review.ps1 to execute review suites."
