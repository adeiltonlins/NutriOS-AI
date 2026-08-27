"""NutriOS backend."""

# Importa módulos que estendem o router antes de main.py incluí-lo.
from app import pwa as _pwa  # noqa: F401,E402
from app import secure_storage as _secure_storage  # noqa: F401,E402
from app import clinical_v2 as _clinical_v2  # noqa: F401,E402
from app import anthropometry_v2 as _anthropometry_v2  # noqa: F401,E402
