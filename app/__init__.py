"""NutriOS backend."""

# Importa módulos que estendem o router antes de main.py incluí-lo.
from app import pwa as _pwa  # noqa: F401,E402
from app import secure_storage as _secure_storage  # noqa: F401,E402
from app import clinical_v2 as _clinical_v2  # noqa: F401,E402
from app import anthropometry_v2 as _anthropometry_v2  # noqa: F401,E402
from app import questionnaire_templates_v2 as _questionnaire_templates_v2  # noqa: F401,E402
from app import phytotherapy_v2 as _phytotherapy_v2  # noqa: F401,E402
from app import clinical_copilot_v2 as _clinical_copilot_v2  # noqa: F401,E402
from app import patient_clinical_readonly_v2 as _patient_clinical_readonly_v2  # noqa: F401,E402
