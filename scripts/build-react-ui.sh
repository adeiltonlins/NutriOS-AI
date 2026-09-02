#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
WORKDIR="${RUNNER_TEMP:-/tmp}/nutrios-ui-recovery"
mkdir -p "$WORKDIR"
SOURCE_ARCHIVE=""

is_valid_archive(){
  local f="$1"
  [[ -s "$f" ]] && tar -tJf "$f" >/dev/null 2>&1
}

# 1) tenta os arquivos xz diretos já versionados.
for f in \
  "$FRONTEND/nutrios-ui-canonical.tar.xz" \
  "$FRONTEND/frontend-direct-v2.tar.xz" \
  "$FRONTEND/frontend-direct.tar.xz"; do
  if is_valid_archive "$f"; then
    SOURCE_ARCHIVE="$f"
    echo "Fonte React íntegra: $(basename "$f")"
    break
  fi
done

# 2) tenta todas as famílias fragmentadas em base64. Isso evita ficar preso a
# uma cópia truncada e documenta no CI qual backup ainda é íntegro.
if [[ -z "$SOURCE_ARCHIVE" ]]; then
  shopt -s nullglob
  families=(
    "full-ui.xz.b64.*"
    "verified-final.b64.*"
    "integrated-ui.b64.*"
    "integrated-ui-v2.part*"
    "ai-studio-source.b64.part*"
  )
  for pattern in "${families[@]}"; do
    parts=("$FRONTEND"/$pattern)
    ((${#parts[@]} > 0)) || continue
    out="$WORKDIR/${pattern//\*/parts}.tar.xz"
    echo "Testando recuperação: $pattern (${#parts[@]} partes)"
    if printf '%s\n' "${parts[@]}" | sort -V | xargs cat | tr -d '\r\n' | base64 --decode > "$out" 2>/dev/null; then
      if is_valid_archive "$out"; then
        SOURCE_ARCHIVE="$out"
        echo "Recuperação íntegra encontrada: $pattern"
        break
      fi
    fi
  done
fi

[[ -n "$SOURCE_ARCHIVE" ]] || {
  echo "Nenhuma cópia íntegra do frontend React foi encontrada." >&2
  exit 1
}

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

python - "$ROOT/app/static/react-ui/index.html" <<'PY'
from pathlib import Path
import re
import sys

index = Path(sys.argv[1])
html = index.read_text(encoding="utf-8")
tag = '<script src="/static/nutrios-diet-models-fix.js?v=20260902f" defer></script>'
html = re.sub(
    r'<script[^>]+src=["\'][^"\']*nutrios-diet-models-fix\.js[^"\']*["\'][^>]*></script>',
    '',
    html,
    flags=re.IGNORECASE,
)
html = html.replace("</body>", f"{tag}</body>")
index.write_text(html, encoding="utf-8")
PY

grep -q 'nutrios-diet-models-fix.js?v=20260902f' "$ROOT/app/static/react-ui/index.html"
echo "React UI completa gerada em app/static/react-ui"
