from app import patient_auth


def test_patient_code_has_distinct_secure_format():
    code = patient_auth.generate_code()
    assert code.startswith("PACI-")
    assert len(code) == 14
    body = code.removeprefix("PACI-").replace("-", "")
    assert "O" not in body and "I" not in body
