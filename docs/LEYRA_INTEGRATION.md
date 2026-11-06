# LEYRA IA — backend foundation

This branch adds an isolated, provider-neutral gateway that LEYRA's web and Android
clients can call through an OpenAI-compatible interface.

## What is included

- `src/leyra_gateway.py`: FastAPI gateway with `/health`, `/v1/models`, and
  `/v1/chat/completions` routes.
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
uvicorn src.leyra_gateway:app --host 127.0.0.1 --port 8010
```

The gateway listens on loopback in this example. Do not expose it publicly without
TLS termination, network restrictions, secret rotation, monitoring, and rate limits.

## LEYRA client connection

Use base URL `http://127.0.0.1:8010/v1` and the `LEYRA_GATEWAY_TOKEN` as the
client Bearer token. Web and Android clients should call the gateway through a
backend-controlled connection; do not embed the upstream provider key in an APK.

## Validation still required

Run the repository test suite and static checks in CI. Verify non-streaming,
streaming, authentication failures, timeout handling, provider errors, and model
listing against a test provider before deployment.
