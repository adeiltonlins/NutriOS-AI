from app.main import EnergyCalculationRequest, _energy_targets, _meal_plan_content


def test_energy_calculation_has_consistent_macros():
    result = _energy_targets(EnergyCalculationRequest(weight_kg=70, height_cm=170, age=35, sex="female", activity_factor=1.55, goal="loss"))
    assert result["bmr_kcal"] > 1000
    assert result["target_kcal"] < result["expenditure_kcal"]
    macro_energy = result["protein_g"] * 4 + result["carbohydrate_g"] * 4 + result["fat_g"] * 9
    assert abs(macro_energy - result["target_kcal"]) < 15
    assert result["requires_professional_review"] is True


def test_meal_plan_sanitizes_foods_and_preserves_substitutions():
    content, totals = _meal_plan_content([{"name": "Café", "time": "07:00", "items": [{"food_id": 1, "grams": 100, "substitutions": ["Opção equivalente"]}, {"food_id": 999999, "grams": 100}]}])
    assert len(content) == 1
    assert len(content[0]["items"]) == 1
    assert content[0]["items"][0]["substitutions"] == ["Opção equivalente"]
    assert totals["kcal"] >= 0
