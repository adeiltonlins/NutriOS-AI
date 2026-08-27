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
    except Exception as exc:
        assert "sete dobras" in str(exc.detail)
    else:
        raise AssertionError("Pollock 7 deveria exigir as sete dobras")


def test_manual_protocol_does_not_calculate():
    assert anthropometry_v2._pollock("manual", None, None, {}) == (None, None)
