from app.main import _visual_body_metrics


def test_visual_body_metrics_are_derived_from_professional_measurements():
    result = _visual_body_metrics({
        "weight_kg": 80,
        "height_cm": 180,
        "waist_cm": 90,
        "hip_cm": 100,
        "body_fat_percent": 20,
        "body_water_percent": 55,
        "evaluation_method": "Bioimpedância",
        "front_photo_id": "front",
        "side_photo_id": "side",
    })
    assert result["bmi"] == 24.69
    assert result["waist_height_ratio"] == 0.5
    assert result["waist_hip_ratio"] == 0.9
    assert result["fat_mass_kg"] == 16
    assert result["lean_mass_kg"] == 64
    assert result["body_water_kg"] == 44
    assert result["assessment_completeness"] == 100


def test_visual_completeness_is_not_a_health_score():
    result = _visual_body_metrics({"weight_kg": 70, "height_cm": 170})
    assert result["assessment_completeness"] == 25
    assert "fotos usadas somente como apoio visual" in result["method_notice"]
