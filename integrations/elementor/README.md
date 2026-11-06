# LEYRA Elementor Bridge 1.0.0

Independent, dependency-free bridge from LEYRA to Elementor 4.3.6's WordPress MCP proxy. It does not modify Elementor or LEYRA CORE.

## Requirements
- Python 3.9+ (standard library only; Termux supported).
- WordPress with Elementor and REST endpoint `/wp-json/elementor/v1/mcp-proxy`.
- Dedicated WordPress user with `edit_posts` capability and an Application Password.
- HTTPS for remote WordPress (HTTP is allowed only for localhost).

## Setup
1. Copy `.env.example` to `.env` and generate a private token:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Set WordPress URL, username, Application Password and token.
3. Set only verified Elementor MCP proxy slugs in `LEYRA_ELEMENTOR_ALLOWED_TOOLS`.
4. Start: `set -a; . ./.env; set +a; python leyra_elementor_bridge.py`

## Routes
- `GET /health` — local health check.
- `GET /leyra/elementor/status` — authenticated configuration status.
- `POST /leyra/elementor/tool` — authenticated, allowlisted MCP tool call.
- `GET /leyra/elementor/resource?uri=...` — authenticated resource read.

Use `Authorization: Bearer YOUR_TOKEN` for all routes except health.

## Safe defaults
- No tool calls unless the exact tool slug is allowlisted.
- Mutating tool names are blocked unless `LEYRA_ELEMENTOR_ALLOW_MUTATIONS=true`.
- Never expose port 8011 directly to the public internet.
- Keep credentials in local environment variables, never in frontend code or Git.
- Remote WordPress must use HTTPS.

## Elementor endpoint verified in supplied 4.3.6 archive
The plugin registers `POST` and `GET` on `elementor/v1/mcp-proxy`, requires `current_user_can('edit_posts')`, and dispatches tools/resources through its MCP ability registry. Tool slugs must be read from the actual installed registry; this bridge intentionally does not guess them.

## Connection status
The bridge is ready to run, but a real WordPress connection remains pending valid site credentials and an explicit tool allowlist. Do not mark it connected until the authenticated status and a harmless read-only tool succeed.
