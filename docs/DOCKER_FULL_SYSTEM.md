# Docker Full System (API + CLI + Daemon)

This setup runs the complete local platform using Docker Compose:

- `api` - Flask/Gunicorn app (`app.py`)
- `daemon` - local firewall daemon (`scripts/lemma_firewall.py`)
- `cli` - Lemma CLI (`scripts/lemma_cli.py`)
- `postgres` - state store
- `redis` - cache/event bus

## 1) Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)

## 2) Start core platform (API + DB + Redis)

```bash
docker compose up -d postgres redis api
```

API health:

```bash
curl http://localhost:5000/health
```

## 3) Start daemon profile

```bash
docker compose --profile daemon up -d daemon
```

Daemon health:

```bash
curl http://localhost:8787/aim/health
```

## 4) Use CLI inside container

Run help:

```bash
docker compose run --rm --profile cli cli --help
```

Run a command against the API service:

```bash
docker compose run --rm --profile cli cli auth-status --api-base http://api:5000 --json
```

## 5) Run migrations

```bash
docker compose --profile ops run --rm migrate
```

## 6) One-command operator workflow (PowerShell)

Use the Docker power-user wrapper:

```powershell
./scripts/docker_power.ps1 up-full
./scripts/docker_power.ps1 migrate
./scripts/docker_power.ps1 smoke
```

Common actions:

- `./scripts/docker_power.ps1 up-core`
- `./scripts/docker_power.ps1 up-full`
- `./scripts/docker_power.ps1 health`
- `./scripts/docker_power.ps1 cli --help`
- `./scripts/docker_power.ps1 reset`
- `./scripts/docker_power.ps1 scorecard`
- `./scripts/docker_power.ps1 ishuman-smoke`

## 7) isHuman network Docker smoke check

Run:

```powershell
./scripts/docker_power.ps1 ishuman-smoke
```

What it verifies:

- `GET /api/ishuman/stats` is reachable and returns `network: "isHuman"`
- `GET /api/ishuman/check` returns a valid response shape
- `POST /api/ishuman/start-verification` rejects invalid payloads predictably

Optional Stripe Identity local config (only needed for full verification flow):

- `STRIPE_SECRET_KEY`
- `STRIPE_IDENTITY_WEBHOOK_SECRET` (or legacy `STRIPE_WEBHOOK_SECRET`)
- `ISHUMAN_RETURN_URL`

## Notes

- Environment values are loaded from `.env.docker`.
- `api` and `daemon` use a shared image from `Dockerfile.platform`.
- The daemon defaults to policy file `scripts/lemma_firewall_policy.example.json`.
- For production, replace all dev keys and remove direct secret files from images.
- See `docs/DOCKER_POWER_USER_PLAYBOOK.md` for phased operating practices.
