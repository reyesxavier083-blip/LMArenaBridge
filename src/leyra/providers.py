"""OpenAI-compatible model provider client used by the LEYRA core."""
from __future__ import annotations
import os
from urllib.parse import urlsplit
import httpx
from fastapi import HTTPException

class ModelProvider:
    def __init__(self) -> None:
        self.base_url = os.getenv("LEYRA_UPSTREAM_BASE_URL", "").strip().rstrip("/")
        self.api_key = os.getenv("LEYRA_UPSTREAM_API_KEY", "").strip()
        self.embedding_model = os.getenv("LEYRA_EMBEDDING_MODEL", "").strip()
        try:
            self.timeout = float(os.getenv("LEYRA_UPSTREAM_TIMEOUT_SECONDS", "90"))
        except ValueError:
            self.timeout = 90.0
        if not 5 <= self.timeout <= 300:
            self.timeout = 90.0

    def configured(self) -> bool:
        if not self.base_url: return False
        parsed = urlsplit(self.base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        return bool(parsed.hostname and (parsed.scheme == "https" or local_http) and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)

    def _require_config(self) -> None:
        if not self.configured():
            raise HTTPException(status_code=503, detail="Model provider is not configured with a valid HTTPS endpoint.")

    def headers(self) -> dict[str, str]:
        result = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key: result["Authorization"] = "Bearer " + self.api_key
        return result


    async def embed(self, text: str) -> list[float] | None:
        if not self.embedding_model or not self.configured():
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10)) as client:
                response = await client.post(
                    self.base_url + "/embeddings",
                    headers=self.headers(),
                    json={"model": self.embedding_model, "input": text[:12000]},
                )
            response.raise_for_status()
            payload = response.json()
            vector = payload["data"][0]["embedding"]
            if not isinstance(vector, list) or not vector or len(vector) > 10000:
                return None
            values = [float(value) for value in vector]
            if not all(__import__("math").isfinite(value) for value in values):
                return None
            return values
        except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
            return None

    async def models(self) -> dict:
        self._require_config()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10)) as client:
                response = await client.get(self.base_url + "/models", headers=self.headers())
        except httpx.TimeoutException as exc:
            raise HTTPException(504, "Model provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Could not reach the model provider.") from exc
        if response.is_error: raise HTTPException(502, "Model provider rejected the models request.")
        try: return response.json()
        except ValueError as exc: raise HTTPException(502, "Model provider returned invalid JSON.") from exc

    async def chat(self, payload: dict) -> dict:
        self._require_config()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10)) as client:
                response = await client.post(self.base_url + "/chat/completions", headers=self.headers(), json=payload)
        except httpx.TimeoutException as exc:
            raise HTTPException(504, "Model provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Could not reach the model provider.") from exc
        if response.is_error: raise HTTPException(502, "Model provider rejected the chat request.")
        try: return response.json()
        except ValueError as exc: raise HTTPException(502, "Model provider returned invalid JSON.") from exc
