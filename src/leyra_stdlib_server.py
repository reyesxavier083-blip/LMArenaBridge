"""Standalone LEYRA gateway using only Python's standard library.

This server mirrors the LEYRA routes without requiring FastAPI or Uvicorn.
It forwards only to an explicitly configured OpenAI-compatible provider.
"""
from __future__ import annotations

import hmac
import json
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


MAX_BODY = 2 * 1024 * 1024
MAX_MESSAGES = 100


class GatewayError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


def settings() -> tuple[str, str, str, float]:
    base = os.getenv("LEYRA_UPSTREAM_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("LEYRA_GATEWAY_TOKEN", "").strip()
    api_key = os.getenv("LEYRA_UPSTREAM_API_KEY", "").strip()
    if not base:
        raise GatewayError(503, "LEYRA provider is not configured.")
    if not token:
        raise GatewayError(503, "LEYRA gateway authentication is not configured.")
    parsed = urlsplit(base)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise GatewayError(503, "Provider URL must use HTTPS (HTTP only for localhost).")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GatewayError(503, "Provider URL is invalid.")
    try:
        parsed.port
        timeout = float(os.getenv("LEYRA_UPSTREAM_TIMEOUT_SECONDS", "90"))
    except (ValueError, TypeError):
        raise GatewayError(503, "Provider URL port or timeout is invalid.")
    if not 5 <= timeout <= 300:
        raise GatewayError(503, "Provider timeout must be between 5 and 300 seconds.")
    return base, token, api_key, timeout


def auth(handler: BaseHTTPRequestHandler, expected: str) -> None:
    scheme, sep, supplied = handler.headers.get("Authorization", "").partition(" ")
    if not sep or scheme.lower() != "bearer" or not hmac.compare_digest(supplied, expected):
        raise GatewayError(401, "Invalid or missing LEYRA gateway token.")


def provider_request(base: str, api_key: str, path: str, method: str = "GET",
                     body: bytes | None = None, timeout: float = 90):
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(f"{base}/{path.lstrip('/')}", data=body, headers=headers, method=method)
    return urlopen(req, timeout=timeout)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LEYRA-stdlib-gateway"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        # Avoid logging headers, tokens, request bodies, or provider responses.
        sys.stderr.write("[LEYRA] " + (fmt % args) + "\n")

    def send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json(status, {"error": {"message": message}})

    def require_settings(self):
        return settings()

    def do_GET(self) -> None:
        try:
            if self.path == "/leyra/health":
                configured = bool(os.getenv("LEYRA_UPSTREAM_BASE_URL", "").strip()
                                  and os.getenv("LEYRA_GATEWAY_TOKEN", "").strip())
                self.send_json(200, {
                    "service": "leyra-gateway",
                    "status": "ready" if configured else "needs_configuration"
                })
                return

            base, token, api_key, timeout = self.require_settings()
            auth(self, token)

            if self.path == "/leyra/connection/test":
                endpoint = "models"
                try:
                    with provider_request(base, api_key, endpoint, timeout=timeout) as upstream:
                        status = upstream.status
                except HTTPError as exc:
                    raise GatewayError(502, f"Provider connection failed with HTTP {exc.code}.")
                except (URLError, TimeoutError, OSError):
                    raise GatewayError(502, "Could not reach the configured model provider.")
                self.send_json(200, {
                    "service": "leyra-gateway",
                    "connection": "connected",
                    "provider_host": urlsplit(base).hostname,
                    "models_endpoint_status": status,
                    "api_key_configured": bool(api_key)
                })
                return

            if self.path == "/leyra/v1/models":
                try:
                    with provider_request(base, api_key, "models", timeout=timeout) as upstream:
                        data = upstream.read(MAX_BODY + 1)
                        if len(data) > MAX_BODY:
                            raise GatewayError(502, "Provider response is too large.")
                        self.send_response(upstream.status)
                        self.send_header("Content-Type", upstream.headers.get(
                            "Content-Type", "application/json"))
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                except HTTPError:
                    raise GatewayError(502, "The configured provider rejected the models request.")
                except (URLError, TimeoutError, OSError):
                    raise GatewayError(502, "Could not reach the configured model provider.")
                return

            raise GatewayError(404, "Not found.")
        except GatewayError as exc:
            self.send_error_json(exc.status, exc.message)

    def do_POST(self) -> None:
        try:
            base, token, api_key, timeout = self.require_settings()
            auth(self, token)
            if self.path != "/leyra/v1/chat/completions":
                raise GatewayError(404, "Not found.")

            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise GatewayError(400, "Invalid Content-Length.")
            if size <= 0 or size > MAX_BODY:
                raise GatewayError(413, "Request body must be between 1 byte and 2 MiB.")
            raw = self.rfile.read(size)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise GatewayError(400, "Request body must be valid JSON.")
            if not isinstance(payload, dict):
                raise GatewayError(400, "Request body must be a JSON object.")
            if not isinstance(payload.get("model"), str) or not payload["model"].strip():
                raise GatewayError(400, "A model name is required.")
            messages = payload.get("messages")
            if not isinstance(messages, list) or not messages:
                raise GatewayError(400, "At least one message is required.")
            if len(messages) > MAX_MESSAGES:
                raise GatewayError(413, "A maximum of 100 messages is allowed.")

            try:
                upstream = provider_request(
                    base, api_key, "chat/completions", method="POST",
                    body=json.dumps(payload).encode("utf-8"), timeout=timeout
                )
            except HTTPError as exc:
                exc.close()
                raise GatewayError(502, "The configured provider rejected the chat request.")
            except (URLError, TimeoutError, OSError):
                raise GatewayError(502, "Could not reach the configured model provider.")

            with upstream:
                content_type = upstream.headers.get("Content-Type", "application/json")
                if payload.get("stream") is True:
                    self.send_response(upstream.status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    try:
                        while True:
                            chunk = upstream.read(8192)
                            if not chunk:
                                break
                            self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                            self.wfile.write(chunk)
                            self.wfile.write(b"\r\n")
                            self.wfile.flush()
                        self.wfile.write(b"0\r\n\r\n")
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                else:
                    data = upstream.read(MAX_BODY * 4)
                    self.send_response(upstream.status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
        except GatewayError as exc:
            self.send_error_json(exc.status, exc.message)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_HEAD(self) -> None:
        self.send_error_json(405, "Method not allowed.")


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"LEYRA Gateway (stdlib) listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping LEYRA Gateway...", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
