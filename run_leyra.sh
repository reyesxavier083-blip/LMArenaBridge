#!/data/data/com.termux/files/usr/bin/bash
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python}"
if ! "$PYTHON_BIN" -c 'import fastapi, httpx, uvicorn' >/dev/null 2>&1; then
  echo "Faltan dependencias del gateway LEYRA. Ejecuta:"
  echo "$PYTHON_BIN -m pip install -r requirements-leyra.txt"
  exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
exec "$PYTHON_BIN" -m uvicorn src.leyra_gateway:app --host "$HOST" --port "$PORT"
