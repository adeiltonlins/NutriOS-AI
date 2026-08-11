from app.llm import montar_system_prompt


def test_client_identity_reaches_prompt():
    prompt = montar_system_prompt({
        "nome": "Dra. Maria",
        "especialidade": "nutrição esportiva",
        "identidade_ia": "Assistente Maria",
        "mensagem_inicial": "Bem-vindo à clínica",
    })
    assert "Assistente Maria" in prompt
    assert "Dra. Maria" in prompt
    assert "Bem-vindo à clínica" in prompt
