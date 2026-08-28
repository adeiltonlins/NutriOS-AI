#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"

if [[ ! -f "$FRONTEND/package.json" ]]; then
  echo "Frontend React ainda não foi materializado nesta branch." >&2
  exit 1
fi

cd "$FRONTEND"
npm install --no-audit --no-fund
npm run lint
npm run build

test -f "$ROOT/app/static/react-ui/index.html"
echo "React UI gerada em app/static/react-ui"
