from app import patient_clinical_readonly_v2 as module


def test_patient_lab_exams_are_scoped_to_patient_and_client(monkeypatch):
    captured = {}

    def fake_request(method, table, params=None, **kwargs):
        captured.update({"method": method, "table": table, "params": params})
        return [{"id": "exam-1", "exam_name": "Ferritina"}]

    monkeypatch.setattr(module.saas_store, "_request", fake_request)
    patient = {"id": "patient-a", "client_id": "client-a"}
    rows = module.patient_lab_exams(patient)

    assert rows[0]["id"] == "exam-1"
    assert captured["table"] == "patient_lab_exams"
    assert captured["params"]["patient_id"] == "eq.patient-a"
    assert captured["params"]["client_id"] == "eq.client-a"
    assert "notes" not in captured["params"]["select"]


def test_patient_phytotherapy_hides_drafts_and_professional_notes(monkeypatch):
    calls = []

    def fake_request(method, table, params=None, **kwargs):
        calls.append((table, params))
        if table == "patient_phytotherapy_prescriptions":
            return [{"id": "rx-1", "title": "Prescrição", "status": "active"}]
        return [{"id": "item-1", "active_name": "Curcuma", "sort_order": 0}]

    monkeypatch.setattr(module.saas_store, "_request", fake_request)
    patient = {"id": "patient-b", "client_id": "client-b"}
    rows = module.patient_phytotherapy(patient)

    assert rows[0]["items"][0]["id"] == "item-1"
    prescriptions = calls[0][1]
    items = calls[1][1]
    assert prescriptions["patient_id"] == "eq.patient-b"
    assert prescriptions["client_id"] == "eq.client-b"
    assert prescriptions["status"] == "in.(active,completed)"
    assert "professional_notes" not in prescriptions["select"]
    assert items["patient_id"] == "eq.patient-b"
    assert items["client_id"] == "eq.client-b"
    assert items["prescription_id"] == "eq.rx-1"
