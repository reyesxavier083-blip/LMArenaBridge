# LEYRA IA Cloud Core

This is an isolated cloud entry point; the existing LM Arena bridge remains unchanged.

## Local development (SQLite)

Install Python 3.12+, then:

```bash
python -m pip install -r requirements-leyra.txt
export LEYRA_CONTROL_TOKEN='use-a-long-random-secret'
export LEYRA_DATABASE_PATH='./data/leyra.sqlite3'
export LEYRA_UPSTREAM_BASE_URL='https://api.openai.com/v1'
export LEYRA_UPSTREAM_API_KEY='load-from-a-secret-manager'
export LEYRA_GATEWAY_TOKEN='use-a-different-client-secret'
uvicorn src.leyra.app:app --host 127.0.0.1 --port 8000
```

SQLite is the default for local development and tests.

## Cloud deployment (PostgreSQL + Redis)

Copy `.env.leyra.example` to `.env`, replace every placeholder with unique secrets, then run:

```bash
docker compose -f compose.leyra.yaml up --build -d
```

Compose starts PostgreSQL 16, Redis 7 and LEYRA. PostgreSQL stores memory and audit events; Redis is an optional, short-lived cache for memory reads. The API continues to use the database if Redis is unavailable. Data is held in named Docker volumes.

The application binds to 127.0.0.1:8000. Use a managed HTTPS reverse proxy before enabling remote access. Do not commit `.env` or provider keys.

## Storage configuration

- `LEYRA_DATABASE_URL`: PostgreSQL URL. If absent, SQLite at `LEYRA_DATABASE_PATH` is used.
- `LEYRA_REDIS_URL`: Redis URL. If absent, caching is disabled.
- `GET /leyra/core/health` reports the active database and cache state.

## API

- `GET /leyra/core/health` — health and storage status.
- `GET /leyra/core/agents` — registered agents (control token required).
- `POST /leyra/core/tasks` — dispatch a task.
- `POST /leyra/core/memory` and `GET /leyra/core/memory` — persistent memory.
- `GET /leyra/core/audit` — audit events.
- Existing provider gateway: `/leyra/health`, `/leyra/connection/test`, `/leyra/v1/*`.

The core also supports JWT login at `POST /leyra/core/auth/login`. Bootstrap the first administrator with `LEYRA_BOOTSTRAP_ADMIN_EMAIL` and `LEYRA_BOOTSTRAP_ADMIN_PASSWORD`; set a strong `LEYRA_JWT_SECRET`. Administrators create accounts with `POST /leyra/core/users`. Roles are `viewer`, `operator` and `admin`: viewers can inspect agents, operators can dispatch tasks and use memory, and admins can manage users and inspect audit events. Passwords are stored as PBKDF2-SHA256 hashes; access tokens expire after eight hours. The legacy `LEYRA_CONTROL_TOKEN` remains an admin-level emergency credential. Provider gateway authentication remains separate via `LEYRA_GATEWAY_TOKEN`.

## Current implementation boundary

Planner, persistent memory, audit logging, API and container deployment are implemented in code. Specialist adapters for research, code execution, WordPress, security scanning, vision, voice, creative generation and automation remain `not_configured` until real providers and permission controls are added. No external execution is claimed for those adapters.
