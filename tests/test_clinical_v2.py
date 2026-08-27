from app import clinical_extensions, clinical_v2


def test_clinical_v2_routes_are_registered_on_shared_router():
    paths = {route.path for route in clinical_extensions.router.routes}
    assert "/app/api/pacientes/{patient_id}/exames" in paths
    assert "/app/api/pacientes/{patient_id}/suplementos" in paths
    assert "/paciente/api/suplementos" in paths


def test_exam_status_uses_numeric_reference_range():
    low = clinical_v2.LabExamIn(exam_name="Ferritina", value_numeric=10, reference_min=20, reference_max=200)
    normal = clinical_v2.LabExamIn(exam_name="Ferritina", value_numeric=80, reference_min=20, reference_max=200)
    high = clinical_v2.LabExamIn(exam_name="Ferritina", value_numeric=250, reference_min=20, reference_max=200)
    text_only = clinical_v2.LabExamIn(exam_name="Aspecto", value_text="Sem alterações")

    assert clinical_v2._exam_status(low) == "low"
    assert clinical_v2._exam_status(normal) == "normal"
    assert clinical_v2._exam_status(high) == "high"
    assert clinical_v2._exam_status(text_only) == "normal"


def test_partial_exam_update_preserves_range_inputs_for_status():
    assert clinical_v2._exam_status_values(5, 10, 100) == "low"
    assert clinical_v2._exam_status_values(50, 10, 100) == "normal"
    assert clinical_v2._exam_status_values(150, 10, 100) == "high"
