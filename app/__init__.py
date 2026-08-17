"""NutriOS backend."""

# Importa o módulo PWA antes de main.py incluir o router clínico. O módulo
# acrescenta as rotas públicas personalizadas ao mesmo APIRouter já utilizado
# pelo backend, sem precisar reescrever o grande main.py.
from app import pwa as _pwa  # noqa: F401,E402
