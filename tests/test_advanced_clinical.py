import pytest
from fastapi import HTTPException

from app import main
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


def test_resolve_alert_is_scoped_to_authenticated_nutritionist(monkeypatch):
    captured = {}

    def fake_update(table, row_id, client_id, payload):
        captured.update(table=table, row_id=row_id, client_id=client_id, payload=payload)
        return {"id": row_id, "client_id": client_id, **payload}

    monkeypatch.setattr(main.business_store, "update_row", fake_update)
    monkeypatch.setattr(main.business_store, "audit", lambda *_args, **_kwargs: None)

    result = main.resolve_clinical_alert("alert-1", {"id": "nutritionist-1"})

    assert result["status"] == "resolved"
    assert captured["client_id"] == "nutritionist-1"
    assert captured["payload"]["resolved_at"]


def test_resolve_alert_returns_404_when_not_owned(monkeypatch):
    monkeypatch.setattr(main.business_store, "update_row", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as error:
        main.resolve_clinical_alert("alert-from-another-client", {"id": "nutritionist-1"})

    assert error.value.status_code == 404
