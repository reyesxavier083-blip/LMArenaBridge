#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  python - <<'PY'
from pathlib import Path
import secrets
p=Path(".env")
p.write_text(p.read_text().replace("replace_with_python_secrets_token_urlsafe_48",secrets.token_urlsafe(48)))
PY
  echo "Created .env with a generated token. Edit WordPress settings, then run again."
  exit 0
fi
set -a
. ./.env
set +a
exec python leyra_elementor_bridge.py
