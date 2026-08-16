import re
from pathlib import Path


STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"
CLINICAL_SOURCES = [
    "titanium.css",
    "nutrios-premium.css",
    "clinical-fixes.css",
    "nutrios-premium-v3.css",
    "nutrios-v22-unified.css",
    "nutrios-v23-polish.css",
    "nutrios-v24-final.css",
    "nutrios-v25-final.css",
    "nutrios-datetime.css",
    "nutrios-v26-refine.css",
    "nutrios-v27-polish.css",
    "nutrios-v28-clinical-flow.css",
]
BUNDLE_HEADER = (
    "/* NutriOS clinical dashboard bundle. Generated from the ordered legacy "
    "sources listed below; keep source files until every dependent screen is migrated. */"
)


def test_clinical_dashboard_loads_only_consolidated_css_layers():
    html = (STATIC_DIR / "clinical-dashboard.html").read_text(encoding="utf-8")
    stylesheets = re.findall(r'<link rel="stylesheet" href="([^"]+)">', html)

    assert stylesheets == [
        "/static/clinical-dashboard.bundle.css?v=1",
        "/static/nutrios-design-system-v1.css?v=6",
        "/static/os-component.css?v=1",
    ]


def test_clinical_bundle_matches_legacy_sources_in_cascade_order():
    parts = [BUNDLE_HEADER]
    for source in CLINICAL_SOURCES:
        parts.append(f"\n/* source: {source} */")
        parts.append((STATIC_DIR / source).read_text(encoding="utf-8"))

    expected = "\n".join(parts) + "\n"
    actual = (STATIC_DIR / "clinical-dashboard.bundle.css").read_text(encoding="utf-8")

    assert actual == expected


def test_component_library_references_declared_tokens_only():
    component_css = (STATIC_DIR / "os-component.css").read_text(encoding="utf-8")
    design_system_css = (STATIC_DIR / "nutrios-design-system-v1.css").read_text(
        encoding="utf-8"
    )
    declared = set(re.findall(r"--([a-zA-Z0-9-]+)\s*:", component_css + design_system_css))
    referenced = set(re.findall(r"var\(--([a-zA-Z0-9-]+)", component_css))

    assert referenced <= declared, f"Undefined component tokens: {sorted(referenced - declared)}"
