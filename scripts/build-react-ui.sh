#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
ARCHIVE="$FRONTEND/nutrios-ui-canonical.tar.xz"
EXPECTED_SHA="3aa86112ec408a1440e19e440a4b3d1edf134080bc040a3d59e93c343d672f3e"

[[ -f "$ARCHIVE" ]] || { echo "Archive canonico ausente: $ARCHIVE" >&2; exit 1; }

ACTUAL_SHA="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || {
  echo "SHA256 divergente: $ACTUAL_SHA; esperado $EXPECTED_SHA" >&2
  exit 1
}

tar -tJf "$ARCHIVE" >/dev/null

tar -xJf "$ARCHIVE" -C "$FRONTEND"
rm -f "$FRONTEND/src/components/PresentationBar.tsx" "$FRONTEND/server.ts"

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
