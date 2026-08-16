from pathlib import Path

from app import patient_auth


def test_patient_code_has_distinct_secure_format():
    code = patient_auth.generate_code()
    assert code.startswith("PACI-")
    assert len(code) == 14
    body = code.removeprefix("PACI-").replace("-", "")
    assert "O" not in body and "I" not in body


def test_patient_portal_uses_explicit_name_element_and_refreshes_checkins():
    static_dir = Path(__file__).parents[1] / "app" / "static"
    portal = (static_dir / "patient-portal.html").read_text(encoding="utf-8")
    clinical = (static_dir / "patient-clinical.js").read_text(encoding="utf-8")
    assert "patientName=document.getElementById('name')" in portal
    assert "patientName.textContent=x.name" in portal
    assert "name.textContent=x.name" not in portal
    assert "nutrios:checkin-saved" in portal
    assert 'window.addEventListener("nutrios:checkin-saved", loadClinical)' in clinical
