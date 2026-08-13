"""NutriOS dependency smoke check.
Run with: python scripts/check_dependencies.py
"""
from importlib import import_module

CHECKS = [
    ("fastapi", "FastAPI"),
    ("slowapi", "SlowAPI (rate limiting)"),
    ("google.genai", "Google Gen AI SDK"),
    ("argon2", "Argon2 password hashing"),
    ("cryptography", "Cryptography"),
    ("reportlab", "ReportLab PDF"),
]

failed = []
for module, label in CHECKS:
    try:
        import_module(module)
        print(f"[OK] {label}")
    except Exception as exc:
        failed.append((label, str(exc)))
        print(f"[FALTA] {label}: {exc}")

if failed:
    print("\nInstale as dependências do projeto com: pip install -r requirements.txt")
    raise SystemExit(1)
print("\nNutriOS: dependências essenciais disponíveis.")
