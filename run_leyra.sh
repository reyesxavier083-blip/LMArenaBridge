#!/usr/bin/env bash
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

# Allow an explicit interpreter, otherwise prefer python3 and fall back to python.
if [ -n "${PYTHON_BIN:-}" ]; then
  PYTHON="$PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "No se encontró Python. Instala Python 3.10 o superior."
  exit 1
fi

if ! "$PYTHON" -c 'import fastapi, httpx, uvicorn' >/dev/null 2>&1; then
  echo "Faltan dependencias del gateway LEYRA. Ejecuta:"
  echo "$PYTHON -m pip install -r requirements-leyra.txt"
  exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
exec "$PYTHON" -m uvicorn src.leyra_gateway:app --host "$HOST" --port "$PORT"
