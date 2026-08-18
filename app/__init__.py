"""NutriOS backend."""

# Importa os módulos que estendem o router antes de main.py incluí-lo.
# Isso mantém o main.py estável e permite evoluir o produto por módulos.
from app import pwa as _pwa  # noqa: F401,E402
from app import consultation_api as _consultation_api  # noqa: F401,E402
