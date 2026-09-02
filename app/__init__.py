"""NutriOS backend."""

# Importa módulos que estendem o router antes de main.py incluí-lo.
from app import pwa as _pwa  # noqa: F401,E402
from app import secure_storage as _secure_storage  # noqa: F401,E402
from app import clinical_v2 as _clinical_v2  # noqa: F401,E402
from app import anthropometry_v2 as _anthropometry_v2  # noqa: F401,E402
from app import phytotherapy_v2 as _phytotherapy_v2  # noqa: F401,E402
from app import clinical_copilot_v2 as _clinical_copilot_v2  # noqa: F401,E402
from app import patient_clinical_readonly_v2 as _patient_clinical_readonly_v2  # noqa: F401,E402
from app import meal_template_library_v2 as _meal_template_library_v2  # noqa: F401,E402

# Camada de compatibilidade/serviço do novo frontend React. As rotas de UI só
# passam a substituir as páginas legadas quando o build existe em static/react-ui.
from app import react_ui_api as _react_ui_api  # noqa: F401,E402
from app import react_ui_routes as _react_ui_routes  # noqa: F401,E402
