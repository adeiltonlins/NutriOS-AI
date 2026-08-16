from types import SimpleNamespace

from app import llm


def test_llm_tries_stable_fallback_model(monkeypatch):
    calls = []

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            calls.append(model)
            if len(calls) == 1:
                raise RuntimeError("primary unavailable")
            return SimpleNamespace(text="Resposta recuperada com segurança.")

    monkeypatch.setattr(llm, "MODEL", "primary-model")
    monkeypatch.setattr(llm, "FALLBACK_MODEL", "fallback-model")
    monkeypatch.setattr(llm.genai, "Client", lambda **_kwargs: SimpleNamespace(models=FakeModels()))

    answer = llm.gerar_resposta("Como organizar o café da manhã?", "")

    assert answer == "Resposta recuperada com segurança."
    assert calls == ["primary-model", "fallback-model"]
