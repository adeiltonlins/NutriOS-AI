from app import clinical_copilot_v2, clinical_extensions


def test_copilot_route_is_registered():
    paths = {route.path for route in clinical_extensions.router.routes}
    assert "/app/api/pacientes/{patient_id}/copiloto" in paths


def test_clean_removes_internal_identifiers_recursively():
    payload = {
        "client_id": "tenant-secret",
        "patient_id": "patient-secret",
        "name": "Paciente",
        "nested": {"id": "row-secret", "value": 42, "storage_path": "private/file.pdf"},
    }
    cleaned = clinical_copilot_v2._clean(payload)
    assert "client_id" not in cleaned
    assert "patient_id" not in cleaned
    assert "id" not in cleaned["nested"]
    assert "storage_path" not in cleaned["nested"]
    assert cleaned["nested"]["value"] == 42


def test_copilot_prompt_requires_fact_inference_separation():
    prompt = clinical_copilot_v2.COPILOT_SYSTEM_PROMPT.lower()
    assert "não emita diagnóstico" in prompt
    assert "diferencie fato registrado de inferência" in prompt
    assert "não altere automaticamente" in prompt
