#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
ARCHIVE="$FRONTEND/nutrios-ui-canonical.tar.xz"

[[ -f "$ARCHIVE" ]] || { echo "Archive canonico ausente: $ARCHIVE" >&2; exit 1; }

# Validate the archive structurally instead of trusting a stale expected checksum.
tar -tJf "$ARCHIVE" >/dev/null

tar -xJf "$ARCHIVE" -C "$FRONTEND"
rm -f "$FRONTEND/src/components/PresentationBar.tsx" "$FRONTEND/server.ts"

required=(
  "$FRONTEND/package.json"
  "$FRONTEND/src/App.tsx"
  "$FRONTEND/src/api.ts"
  "$FRONTEND/src/components/LandingPageView.tsx"
  "$FRONTEND/src/components/DashboardView.tsx"
  "$FRONTEND/src/components/PatientsView.tsx"
  "$FRONTEND/src/components/MealPlannerView.tsx"
  "$FRONTEND/src/components/PatientPortalView.tsx"
  "$FRONTEND/src/components/SuperAdminView.tsx"
  "$FRONTEND/src/components/PhytotherapyView.tsx"
)
for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "Frontend completo ausente: $f" >&2; exit 1; }
done

cd "$FRONTEND"
npm install --no-audit --no-fund
npm run lint
npm run build

test -f "$ROOT/app/static/react-ui/index.html"
echo "React UI completa gerada em app/static/react-ui"
