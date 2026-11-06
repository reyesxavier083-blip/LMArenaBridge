# LEYRA IA — backend foundation

This branch adds a provider-neutral gateway mounted into the existing LMArenaBridge
FastAPI application. LEYRA web and Android clients can call it through an
OpenAI-compatible interface.

## What is included

- `src/leyra_gateway.py`: reusable FastAPI router with `/leyra/health`,
  `/leyra/connection/test`, `/leyra/v1/models`, and `/leyra/v1/chat/completions` routes.
- `src/main.py` mounts the router into the existing server, so no second server is
  required.
- Streaming responses are forwarded as bytes so Server-Sent Events remain intact.
- The LEYRA client token and upstream provider key are read from environment variables.
- HTTPS is required for remote providers. Plain HTTP is accepted only for loopback
  development endpoints.
- Provider errors are sanitized; credentials and upstream response bodies are not
  copied into error messages.

## What is intentionally not included

This gateway does not automate a third-party website, scrape private endpoints,
reuse browser cookies, solve CAPTCHA/Turnstile challenges, or bypass access controls.
Configure it only with an API endpoint you are authorized to use.

## Configuration

Set these variables in the server environment (never commit real values):

- `LEYRA_UPSTREAM_BASE_URL`: provider base URL, including its API prefix, e.g.
  `https://api.example.com/v1`.
- `LEYRA_UPSTREAM_API_KEY`: provider credential. Optional for local providers that
  do not require one.
- `LEYRA_GATEWAY_TOKEN`: a separate, high-entropy token required from LEYRA clients.
- `LEYRA_UPSTREAM_TIMEOUT_SECONDS`: optional, 5–300 seconds; defaults to 90.

Example for local development only:

```bash
export LEYRA_UPSTREAM_BASE_URL="http://127.0.0.1:9000/v1"
export LEYRA_UPSTREAM_API_KEY=""
export LEYRA_GATEWAY_TOKEN="replace-with-a-long-random-secret"
export LEYRA_UPSTREAM_TIMEOUT_SECONDS="90"
python -m src.main
```

The existing server listens according to its own configuration. For development,
keep it bound to loopback. Do not expose it publicly without TLS termination,
network restrictions, secret rotation, monitoring, and rate limits.

## OpenAI provider configuration

For the official OpenAI API, configure the gateway with:

- `LEYRA_UPSTREAM_BASE_URL=https://api.openai.com/v1`
- `LEYRA_UPSTREAM_API_KEY`: an API key supplied and managed by the authorized account owner.
- `LEYRA_GATEWAY_TOKEN`: a separate random secret used only by LEYRA clients.

The gateway then calls OpenAI's `GET /v1/models` and
`POST /v1/chat/completions` endpoints. It does not use a ChatGPT web-session
cookie or a ChatGPT subscription login. API usage is billed separately according
to the API account's billing and model rates. Have the account owner review usage
limits and billing before enabling requests.

Example server environment (replace the placeholders locally; never commit actual
secrets to GitHub):

```bash
export LEYRA_UPSTREAM_BASE_URL="https://api.openai.com/v1"
export LEYRA_UPSTREAM_API_KEY="YOUR_OPENAI_API_KEY"
export LEYRA_GATEWAY_TOKEN="YOUR_SEPARATE_LONG_RANDOM_GATEWAY_SECRET"
export LEYRA_UPSTREAM_TIMEOUT_SECONDS="90"
```

Do not paste either secret into chat, source code, screenshots, or the mobile app.
If a key is ever exposed, revoke it through the account owner's API settings.

## Verify the real provider connection

After setting the environment variables and starting the server, call the connection
test. This makes a real authenticated GET request to the provider's `/models`
endpoint; it does not simulate a connection.

```bash
curl -i "http://127.0.0.1:8000/leyra/connection/test" \
  -H "Authorization: Bearer $LEYRA_GATEWAY_TOKEN"
```

A successful response includes `"connection": "connected"` and the provider host.
HTTP 401/403 from the provider means its credential or access is not accepted;
a timeout or network error means the server cannot reach the provider. The route
does not reveal credentials or forward the provider's raw error body.

## LEYRA client connection

Use base URL `http://127.0.0.1:8000/leyra/v1` (adjust host/port to match the
server configuration) and the `LEYRA_GATEWAY_TOKEN` as the client Bearer token. Web and Android clients should call the gateway through a
backend-controlled connection; do not embed the upstream provider key in an APK.

## Validation still required

Run the repository test suite and static checks in CI. The connection-test route has
mocked success and provider-auth-failure tests; a real deployment still requires
valid provider credentials and a successful live call to `/leyra/connection/test`.
Then verify non-streaming and streaming chat requests and model listing.
