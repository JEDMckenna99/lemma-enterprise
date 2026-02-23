param(
    [string]$AppName = "lemma-enterprise",
    [string]$SentryAuthToken = "",
    [string]$SentryOrg = "",
    [string]$SentryProject = "",
    [string]$SentryBaseUrl = "https://sentry.io",
    [string]$OutputDir = "docs/launch-evidence"
)

$ErrorActionPreference = "Stop"

function Resolve-Value {
    param(
        [string]$Provided,
        [string]$EnvName
    )
    if ($Provided) {
        return $Provided
    }
    $fromEnv = [System.Environment]::GetEnvironmentVariable($EnvName)
    if ($fromEnv) {
        return $fromEnv
    }
    return ""
}

$sentryDsn = (& heroku config:get SENTRY_DSN -a $AppName).Trim()
if (-not $sentryDsn) {
    throw "Missing SENTRY_DSN in Heroku app '$AppName'."
}

$authToken = Resolve-Value -Provided $SentryAuthToken -EnvName "SENTRY_AUTH_TOKEN"
$org = Resolve-Value -Provided $SentryOrg -EnvName "SENTRY_ORG"
$project = Resolve-Value -Provided $SentryProject -EnvName "SENTRY_PROJECT"

if (-not $authToken) {
    throw "Missing Sentry auth token. Provide -SentryAuthToken or set SENTRY_AUTH_TOKEN."
}
if (-not $org) {
    throw "Missing Sentry org. Provide -SentryOrg or set SENTRY_ORG."
}
if (-not $project) {
    throw "Missing Sentry project. Provide -SentryProject or set SENTRY_PROJECT."
}

python "scripts/run_sentry_alert_routing_drill.py" `
    --output-dir "$OutputDir" `
    --sentry-dsn "$sentryDsn" `
    --sentry-auth-token "$authToken" `
    --sentry-org "$org" `
    --sentry-project "$project" `
    --sentry-base-url "$SentryBaseUrl" `
    --app-label "$AppName"
