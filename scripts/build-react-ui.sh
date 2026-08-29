#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
ARCHIVE_B64="$FRONTEND/verified-final.b64"
ARCHIVE_XZ="$FRONTEND/verified-final.tar.xz"

chunks=(
  "$FRONTEND/verified-final.b64.00"
  "$FRONTEND/verified-final.b64.01"
  "$FRONTEND/verified-final.b64.02"
  "$FRONTEND/verified-final.b64.03"
  "$FRONTEND/verified-final.b64.04"
  "$FRONTEND/verified-final.b64.05"
  "$FRONTEND/verified-final.b64.06"
  "$FRONTEND/verified-final.b64.07"
  "$FRONTEND/verified-final.b64.080"
  "$FRONTEND/verified-final.b64.081"
  "$FRONTEND/verified-final.b64.082"
  "$FRONTEND/verified-final.b64.083"
  "$FRONTEND/verified-final.b64.09"
)

for chunk in "${chunks[@]}"; do
  [[ -f "$chunk" ]] || { echo "Chunk ausente: $chunk" >&2; exit 1; }
done

cat "${chunks[@]}" > "$ARCHIVE_B64"

python - "$ARCHIVE_B64" "$ARCHIVE_XZ" <<'PY'
import base64, hashlib, re, sys
from pathlib import Path

src = Path(sys.argv[1]).read_text(encoding="ascii")
clean = re.sub(r"\s+", "", src)
try:
    data = base64.b64decode(clean, validate=True)
except Exception as exc:
    raise SystemExit(f"Falha ao decodificar archive base64: {exc}")

Path(sys.argv[2]).write_bytes(data)
print("Base64 chars:", len(clean))
print("XZ bytes:", len(data))
print("UI archive sha256:", hashlib.sha256(data).hexdigest())
PY

# Validate the compressed tar before touching the source tree.
tar -tJf "$ARCHIVE_XZ" >/dev/null

tar -xJf "$ARCHIVE_XZ" -C "$FRONTEND"
rm -f "$ARCHIVE_B64" "$ARCHIVE_XZ"

if [[ ! -f "$FRONTEND/package.json" || ! -f "$FRONTEND/src/App.tsx" ]]; then
  echo "Frontend React completo nao foi materializado." >&2
  exit 1
fi

cd "$FRONTEND"
npm install --no-audit --no-fund
npm run lint
npm run build

test -f "$ROOT/app/static/react-ui/index.html"
echo "React UI completa gerada em app/static/react-ui"

# Re-run staging validation after canonical archive repair.
