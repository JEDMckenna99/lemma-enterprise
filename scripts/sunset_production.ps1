# Safe lemma.id sunset. Requires `heroku login`.
# Keeps lemma-enterprise web up for the tombstone + privacy pages.
# Scales workers and satellite apps to zero. Does not destroy apps or databases.

$ErrorActionPreference = "Stop"

$Primary = "lemma-enterprise"
$Satellites = @(
    "lemma-staging",
    "lemma-signing",
    "lemma-identity-network",
    "lemma-demo-tickets",
    "lemma-demo-trials"
)

Write-Host "=== Confirm Heroku auth ==="
heroku auth:whoami

Write-Host "`n=== Enable sunset on $Primary ==="
heroku config:set LEMMA_SUNSET=1 LEMMA_ISHUMAN_DIDIT_ENABLED=false -a $Primary

Write-Host "`n=== Stop workers on $Primary (keep web) ==="
heroku ps:scale billing_worker=0 retention_worker=0 -a $Primary

foreach ($app in $Satellites) {
    Write-Host "`n=== Scale down $app ==="
    heroku ps:scale web=0 -a $app
}

Write-Host "`nSunset flags set. Deploy the tombstone commit to $Primary if it is not already live."
Write-Host "Do not destroy apps, Postgres, Redis, or KMS until you have a DB dump."
