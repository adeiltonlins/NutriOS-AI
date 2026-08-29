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
import base64, hashlib, sys
from pathlib import Path

src = Path(sys.argv[1]).read_text(encoding="ascii")
if len(src) != 149808:
    raise SystemExit(f"Base64 incompleto: {len(src)} chars; esperado 149808")

data = base64.b64decode(src, validate=True)
if len(data) != 112356:
    raise SystemExit(f"Arquivo xz invalido: {len(data)} bytes; esperado 112356")

digest = hashlib.sha256(data).hexdigest()
expected = "5b582991f33136ba8d90a4bd8991c32ab0f44f3cd108a6c928d6d67a540718bf"
if digest != expected:
    raise SystemExit(f"SHA256 divergente: {digest}; esperado {expected}")

Path(sys.argv[2]).write_bytes(data)
print("UI archive sha256:", digest)
PY

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
