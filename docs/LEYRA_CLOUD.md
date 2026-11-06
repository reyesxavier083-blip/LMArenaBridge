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
export LEYRA_EMBEDDING_MODEL='text-embedding-3-small'
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

- `GET /leyra/core/health` — health, storage and provider configuration status.
- `GET /leyra/core/models` — list models from the configured OpenAI-compatible provider (viewer+).
- `GET /leyra/core/memory/search?query=...` — retrieve relevant saved context (viewer+).
- `POST /leyra/core/chat` — send a chat completion request to the configured provider (operator+).
- `GET /leyra/core/agents` — registered agents (control token required).
- `POST /leyra/core/tasks` — dispatch a task.
- `POST /leyra/core/memory` and `GET /leyra/core/memory` — persistent memory.
- `GET /leyra/core/audit` — audit events.
- Existing provider gateway: `/leyra/health`, `/leyra/connection/test`, `/leyra/v1/*`.

Memory supports optional semantic retrieval. Set `LEYRA_EMBEDDING_MODEL` to an embeddings model available at the configured provider's `/embeddings` endpoint. On memory writes, LEYRA stores the vector with the owner and namespace; searches embed the query and rank matching vectors with cosine similarity. If embeddings are not configured, unavailable, or return no usable matches, LEYRA falls back to lexical keyword retrieval. Disable chat retrieval with `use_memory: false`. Vectors are stored in a portable table supported by SQLite and PostgreSQL; pgvector is not required. Embedding requests send memory text to the explicitly configured upstream provider.

The model engine uses `LEYRA_UPSTREAM_BASE_URL` and `LEYRA_UPSTREAM_API_KEY` to call an explicitly configured OpenAI-compatible HTTPS endpoint. It does not hardcode a provider or expose provider credentials to clients. The provider must implement `/models` and `/chat/completions`.

The core also supports JWT login at `POST /leyra/core/auth/login`. Bootstrap the first administrator with `LEYRA_BOOTSTRAP_ADMIN_EMAIL` and `LEYRA_BOOTSTRAP_ADMIN_PASSWORD`; set a strong `LEYRA_JWT_SECRET`. Administrators create accounts with `POST /leyra/core/users`. Roles are `viewer`, `operator` and `admin`: viewers can inspect agents, operators can dispatch tasks and use memory, and admins can manage users and inspect audit events. Passwords are stored as PBKDF2-SHA256 hashes; access tokens expire after eight hours. The legacy `LEYRA_CONTROL_TOKEN` remains an admin-level emergency credential. Provider gateway authentication remains separate via `LEYRA_GATEWAY_TOKEN`.

## Current implementation boundary

Planner, persistent memory, audit logging, API and container deployment are implemented in code. Specialist adapters for research, code execution, WordPress, security scanning, vision, voice, creative generation and automation remain `not_configured` until real providers and permission controls are added. No external execution is claimed for those adapters.

### Long-term memory

Memory records can be classified as `episodic`, `semantic`, `preference` or `procedural`. Each record has an importance score from 1 to 5 (default 3). Optional `ttl_days` sets an expiration from 1 to 3650 days; omitted means no automatic expiration. Expired records are excluded from list, lexical search and vector retrieval without exposing another user's records.

Example `POST /leyra/core/memory` body:

```json
{
  "namespace": "profile",
  "content": "Prefers concise responses",
  "memory_type": "preference",
  "importance": 5,
  "ttl_days": 365
}
```

Existing database rows are migrated with safe defaults: semantic type, importance 3, and no expiration.
