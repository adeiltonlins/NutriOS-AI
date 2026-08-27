from app import clinical_extensions, phytotherapy_v2


def test_phytotherapy_routes_registered():
    paths = {route.path for route in clinical_extensions.router.routes}
    assert "/app/api/pacientes/{patient_id}/fitoterapia" in paths
    assert "/app/api/pacientes/{patient_id}/fitoterapia/{row_id}/status" in paths


def test_phytotherapy_payload_accepts_multiple_items():
    payload = phytotherapy_v2.PhytoPrescriptionIn(
        title="Fórmula noturna",
        prescription_type="formula",
        items=[
            {"active_name": "Passiflora incarnata", "concentration": "200 mg", "dose": "1 cápsula"},
            {"active_name": "Withania somnifera", "concentration": "300 mg", "dose": "1 cápsula"},
        ],
    )
    assert len(payload.items) == 2
    assert payload.items[0].active_name == "Passiflora incarnata"
