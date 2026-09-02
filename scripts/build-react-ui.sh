#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
ARCHIVE="$FRONTEND/nutrios-ui-canonical.tar.xz"
RECOVERED="$RUNNER_TEMP/nutrios-ui-recovered.tar.xz"
SOURCE_ARCHIVE="$ARCHIVE"

[[ -f "$ARCHIVE" ]] || { echo "Archive canonico ausente: $ARCHIVE" >&2; exit 1; }

# O arquivo canônico ficou truncado em uma revisão anterior. Quando isso ocorrer,
# reconstrói a cópia verificada versionada em fragmentos base64, em vez de servir
# indefinidamente o bundle React antigo.
if ! tar -tJf "$ARCHIVE" >/dev/null 2>&1; then
  echo "Archive canônico inválido; reconstruindo a partir de verified-final.b64.*"
  shopt -s nullglob
  parts=("$FRONTEND"/verified-final.b64.*)
  ((${#parts[@]} > 0)) || { echo "Fragmentos de recuperação ausentes" >&2; exit 1; }
  printf '%s\n' "${parts[@]}" | sort -V | xargs cat | tr -d '\r\n' | base64 --decode > "$RECOVERED"
  tar -tJf "$RECOVERED" >/dev/null
  SOURCE_ARCHIVE="$RECOVERED"
fi

tar -xJf "$SOURCE_ARCHIVE" -C "$FRONTEND"
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

# Mantém a biblioteca real de modelos fora do pacote legado e injeta o conector
# depois do Vite. A versão força navegador/service worker a buscar o arquivo novo.
python - "$ROOT/app/static/react-ui/index.html" <<'PY'
from pathlib import Path
import re
import sys

index = Path(sys.argv[1])
html = index.read_text(encoding="utf-8")
tag = '<script src="/static/nutrios-diet-models-fix.js?v=20260902e" defer></script>'
html = re.sub(
    r'<script[^>]+src=["\'][^"\']*nutrios-diet-models-fix\.js[^"\']*["\'][^>]*></script>',
    '',
    html,
    flags=re.IGNORECASE,
)
html = html.replace("</body>", f"{tag}</body>")
index.write_text(html, encoding="utf-8")
PY

grep -q 'nutrios-diet-models-fix.js?v=20260902e' "$ROOT/app/static/react-ui/index.html"
echo "React UI completa gerada em app/static/react-ui"
