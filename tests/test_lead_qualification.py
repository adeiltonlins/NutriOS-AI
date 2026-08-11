from app.main import qualificar_lead


def test_hot_lead_from_price_intent():
    result = qualificar_lead([{"autor": "user", "texto": "Quanto custa a consulta? Quero agendar"}], False)
    assert result["lead_status"] == "quente"
    assert result["lead_score"] > 0


def test_simple_question_is_not_hot():
    result = qualificar_lead([{"autor": "user", "texto": "Quantas calorias tem uma banana?"}], False)
    assert result["lead_status"] == "duvida"


def test_paid_lead_is_converted():
    result = qualificar_lead([{"autor": "user", "texto": "Olá"}], True, pago=True)
    assert result["lead_status"] == "convertido"
    assert result["lead_score"] == 100
