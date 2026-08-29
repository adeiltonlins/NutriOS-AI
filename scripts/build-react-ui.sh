#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
ARCHIVE_B64="$FRONTEND/full-ui.xz.b64"
ARCHIVE_XZ="$FRONTEND/full-ui.tar.xz"

# Materializa o frontend completo exportado/adaptado do AI Studio.
# Os chunks ficam versionados somente nesta branch de integração para que
# Render/GitHub Actions consigam reconstruir o mesmo fonte de forma determinística.
if compgen -G "$FRONTEND/full-ui.xz.b64.*" > /dev/null; then
  cat "$FRONTEND"/full-ui.xz.b64.* > "$ARCHIVE_B64"
  base64 --decode "$ARCHIVE_B64" > "$ARCHIVE_XZ"
  tar -xJf "$ARCHIVE_XZ" -C "$FRONTEND"
  rm -f "$ARCHIVE_B64" "$ARCHIVE_XZ"
fi

if [[ ! -f "$FRONTEND/package.json" || ! -f "$FRONTEND/src/App.tsx" ]]; then
  echo "Frontend React completo não foi materializado nesta branch." >&2
  exit 1
fi

cd "$FRONTEND"
npm install --no-audit --no-fund
npm run lint
npm run build

test -f "$ROOT/app/static/react-ui/index.html"
echo "React UI completa gerada em app/static/react-ui"
