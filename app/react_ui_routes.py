"""Serve o novo frontend React quando o build está presente.

Se o build ainda não foi gerado, nenhuma rota é registrada e o frontend legado
continua sendo servido por app.main.py. Isso permite rollout/rollback seguro.
"""
from pathlib import Path

from fastapi import Depends
from fastapi.responses import HTMLResponse

from app import auth, clinical_extensions, patient_auth

router = clinical_extensions.router
STATIC_DIR = Path(__file__).resolve().parent / "static"
UI_INDEX = STATIC_DIR / "react-ui" / "index.html"
DIET_MODELS_FIX = "/static/nutrios-diet-models-fix.js?v=20260902c"


def _ui():
    html = UI_INDEX.read_text(encoding="utf-8")
    tag = f'<script src="{DIET_MODELS_FIX}" defer></script>'
    if "nutrios-diet-models-fix.js" not in html:
        html = html.replace("</body>", f"{tag}</body>")
    else:
        # Troca versões antigas do patch para evitar cache de navegador/service worker.
        import re
        html = re.sub(
            r'<script[^>]+src=["\'][^"\']*nutrios-diet-models-fix\.js[^"\']*["\'][^>]*></script>',
            tag,
            html,
            flags=re.IGNORECASE,
        )
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


if UI_INDEX.exists():
    @router.get("/")
    def react_landing():
        return _ui()

    @router.get("/login")
    def react_login():
        return _ui()

    @router.get("/app")
    def react_app(user: dict = Depends(auth.current_user)):
        return _ui()

    @router.get("/app/primeiro-acesso")
    def react_first_access(user: dict = Depends(auth.current_user)):
        return _ui()

    for _path in (
        "/app/clinica", "/app/pacientes", "/app/planos", "/app/cardapios", "/app/treinos",
        "/app/metabolico", "/app/analise-corporal", "/app/evolucao", "/app/fitoterapia",
        "/app/msq", "/app/equivalencias", "/app/exames", "/app/alimentos", "/app/agenda",
        "/app/financeiro", "/app/relatorios", "/app/leads", "/app/conversas", "/app/metricas",
        "/app/crm", "/app/gestao", "/app/onboarding", "/app/configuracoes", "/app/chat",
    ):
        router.add_api_route(_path, _ui, methods=["GET"], dependencies=[Depends(auth.current_user)])

    @router.get("/app/pacientes/{patient_id}")
    def react_patient_record(patient_id: str, user: dict = Depends(auth.current_user)):
        clinical_extensions.owned_patient(patient_id, user["id"])
        return _ui()

    @router.get("/admin")
    def react_admin(user: dict = Depends(auth.require_admin)):
        return _ui()

    for _path in ("/admin/clinica", "/admin/leads", "/admin/testes"):
        router.add_api_route(_path, _ui, methods=["GET"], dependencies=[Depends(auth.require_admin)])

    @router.get("/paciente/login")
    def react_patient_login():
        return _ui()

    @router.get("/paciente/primeiro-acesso")
    def react_patient_first_access(patient: dict = Depends(patient_auth.current_patient)):
        return _ui()

    @router.get("/paciente")
    def react_patient_portal(patient: dict = Depends(patient_auth.current_patient)):
        return _ui()
