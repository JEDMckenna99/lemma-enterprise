# Docker Power User Playbook

This playbook operationalizes Docker usage for this platform as a single-developer workflow.

## Phase 1: Stable Daily Workflow

Use the golden-path commands from project root:

```powershell
./scripts/docker_power.ps1 up-full
./scripts/docker_power.ps1 migrate
./scripts/docker_power.ps1 health
```

Outcome: deterministic startup for API, daemon, Postgres, and Redis.

## Phase 2: Fast Debug and Recovery

Use focused diagnostics and reset actions:

```powershell
./scripts/docker_power.ps1 logs-api
./scripts/docker_power.ps1 logs-daemon
./scripts/docker_power.ps1 reset
./scripts/docker_power.ps1 up-full
```

Outcome: recover local environment quickly from bad state.

## Phase 3: Build Performance Discipline

Measure before optimizing:

```powershell
./scripts/docker_power.ps1 build-api
./scripts/docker_power.ps1 bench-build
```

Keep context lean via `.dockerignore` and build only required services.

## Phase 4: Reproducible Automation

Use wrapper actions for all recurring ops:

```powershell
./scripts/docker_power.ps1 smoke
./scripts/docker_power.ps1 cli auth-status --api-base http://api:5000 --json
```

Outcome: one command per workflow, less environment drift and fewer manual mistakes.

## Phase 5: Ongoing Power-User Hygiene

Run weekly scorecard and maintenance:

```powershell
./scripts/docker_power.ps1 scorecard
./scripts/docker_power.ps1 prune-safe
```

Scorecard output: `docs/DOCKER_SCORECARD.md`

## Recommended Weekly Cadence

1. `up-full` and `smoke`
2. `bench-build`
3. `scorecard`
4. Review scorecard deltas and remove slow/manual steps
