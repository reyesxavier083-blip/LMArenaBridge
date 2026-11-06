# LEYRA IA Cloud Core

This is a separate cloud entry point. It does not replace or modify the LM Arena bridge application.

## Run locally

Use Python 3.12+ and install the lightweight gateway dependencies:

```bash
python -m pip install -r requirements-leyra.txt
export LEYRA_CONTROL_TOKEN='replace-with-a-long-random-secret'
export LEYRA_DATABASE_PATH='./data/leyra.sqlite3'
export LEYRA_UPSTREAM_BASE_URL='https://provider.example/v1'
export LEYRA_UPSTREAM_API_KEY='provider-api-key'
export LEYRA_GATEWAY_TOKEN='separate-client-token'
uvicorn src.leyra.app:app --host 127.0.0.1 --port 8000
```

## Run with Docker Compose

Set the four required environment variables shown in `compose.leyra.yaml`, then run:

```bash
docker compose -f compose.leyra.yaml up --build -d
```

The container binds to localhost by default. Put a managed HTTPS reverse proxy in front before remote access.

## API

- `GET /leyra/core/health` — non-sensitive health check.
- `GET /leyra/core/agents` — registered agents (control token required).
- `POST /leyra/core/tasks` — dispatch a task to a registered agent.
- `POST /leyra/core/memory` — save a memory item.
- `GET /leyra/core/memory` — read memory items.
- `GET /leyra/core/audit` — read audit events.
- `/leyra/health`, `/leyra/connection/test`, `/leyra/v1/*` — existing provider gateway routes.

Control API authentication uses `Authorization: Bearer $LEYRA_CONTROL_TOKEN`. Provider gateway authentication remains separate and uses `LEYRA_GATEWAY_TOKEN`. Never commit secrets.

## Current implementation boundary

The planner, SQLite memory, audit log, API and Docker entry point are implemented. Specialist adapters for research, code execution, WordPress, security scanning, vision, voice, creative generation and automation are registered but intentionally return `not_configured` until their providers and permissions are implemented. This prevents the API from claiming that external work occurred when it did not.

SQLite is the initial persistent store. PostgreSQL and Redis are not wired into this release yet. The existing LM Arena bridge remains a separate application.
