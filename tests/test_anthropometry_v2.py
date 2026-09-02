from fastapi import HTTPException

from app import anthropometry_v2


def test_pollock3_male_returns_density_and_fat_percent():
    density, fat = anthropometry_v2._pollock(
        "pollock3", "male", 30,
        {"chest": 12, "abdomen": 20, "thigh": 16},
    )
    assert density is not None and 1.0 < density < 1.2
    assert fat is not None and 0 < fat < 50


def test_pollock3_female_uses_female_sites():
    density, fat = anthropometry_v2._pollock(
        "pollock3", "female", 30,
        {"triceps": 18, "suprailiac": 16, "thigh": 22},
    )
    assert density is not None
    assert fat is not None and 0 < fat < 60


def test_pollock7_requires_all_seven_sites():
    try:
        anthropometry_v2._pollock("pollock7", "male", 30, {"chest": 10})
    except HTTPException as exc:
        assert "Dobras obrigatórias" in str(exc.detail)
        assert "Axilar média" in str(exc.detail)
    else:
        raise AssertionError("Jackson & Pollock 7 deveria exigir as sete dobras")


def test_manual_protocol_does_not_calculate():
    assert anthropometry_v2._pollock("manual", None, None, {}) == (None, None)


def test_protocol_metadata_exposes_full_names_and_required_measures():
    info = anthropometry_v2._protocol_public("pollock7")
    assert info["label"] == "Jackson & Pollock — 7 dobras"
    assert len(info["required_by_sex"]["male"]) == 7
    assert "formula" in info and info["formula"]


def test_protocol_blocks_age_outside_supported_range():
    payload = anthropometry_v2.AdvancedAnthropometryIn(
        protocol="petroski",
        sex="female",
        age=60,
        weight_kg=65,
        height_cm=165,
        skinfolds={"subscapular": 15, "triceps": 18, "suprailiac": 17, "calf": 16},
    )
    try:
        anthropometry_v2._calculate_protocol(payload, payload.skinfolds)
    except HTTPException as exc:
        assert "faixa etária" in str(exc.detail)
    else:
        raise AssertionError("Petroski feminino deveria bloquear idade fora da faixa configurada")


def test_petroski_male_calculates_four_folds():
    payload = anthropometry_v2.AdvancedAnthropometryIn(
        protocol="petroski",
        sex="male",
        age=32,
        weight_kg=82,
        height_cm=178,
        skinfolds={"subscapular": 14, "triceps": 12, "suprailiac": 16, "calf": 10},
    )
    density, fat = anthropometry_v2._calculate_protocol(payload, payload.skinfolds)
    assert 1.0 < density < 1.2
    assert 0 < fat < 50


def test_petroski_female_requires_weight_and_height():
    payload = anthropometry_v2.AdvancedAnthropometryIn(
        protocol="petroski",
        sex="female",
        age=30,
        skinfolds={"subscapular": 18, "triceps": 20, "suprailiac": 17, "calf": 16},
    )
    try:
        anthropometry_v2._calculate_protocol(payload, payload.skinfolds)
    except HTTPException as exc:
        assert "peso" in str(exc.detail)
        assert "altura" in str(exc.detail)
    else:
        raise AssertionError("Petroski feminino deveria exigir peso e altura")
