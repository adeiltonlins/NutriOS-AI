"""
Camada de geração (LLM) do chatbot nutricional.

Recebe a pergunta do usuário + o contexto recuperado pelo RAG e gera
uma resposta ancorada nesse contexto, seguindo as regras de segurança
(sem prescrição de dieta fechada, sempre com disclaimer quando cabível).

Usa a API do Google Gemini (tem tier gratuito generoso, sem cartão de
crédito — ver https://ai.google.dev). Pra trocar de provedor de IA no
futuro, só é preciso mexer neste arquivo; o resto do projeto (RAG, API)
não muda.
"""
import os
from google import genai

MODEL = "gemini-flash-latest"  # alias que sempre aponta pra versão Flash mais recente do Gemini

SYSTEM_PROMPT = """\
Você se chama Bruce. Você é um assistente educativo de nutrição. Seu papel é \
tirar dúvidas gerais sobre alimentos e hábitos alimentares, SEMPRE com base \
no CONTEXTO fornecido abaixo, que vem de uma base de dados nutricional \
confiável.

REGRAS OBRIGATÓRIAS:
1. Se perguntarem seu nome, diga que se chama Bruce.
2. Baseie suas respostas apenas nas informações do CONTEXTO. Se o contexto \
não tiver a informação necessária, diga claramente que não tem esse dado na \
base e sugira consultar um nutricionista, em vez de inventar números.
3. NUNCA prescreva uma dieta fechada e individualizada (ex: "coma X gramas \
de Y no café da manhã, Z gramas de W no almoço..."). Você pode informar \
valores nutricionais e dar orientações GERAIS e educativas.
4. Para pedidos que exigem avaliação individual (condições de saúde \
específicas, cálculo de necessidade calórica pessoal, perda de peso \
patológica, gestantes, crianças, atletas de alto rendimento), oriente \
explicitamente a buscar um nutricionista ou médico.
5. Seja direto, claro e cordial. Não é necessário repetir o disclaimer em \
toda resposta — apenas quando a pergunta se aproximar de uma prescrição \
individual ou de uma condição de saúde específica.
6. Responda sempre em português do Brasil.
"""


def gerar_resposta(pergunta: str, contexto: str) -> str:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    mensagem_usuario = f"""CONTEXTO (base de dados nutricional):
{contexto}

PERGUNTA DO USUÁRIO:
{pergunta}"""

    resposta = client.models.generate_content(
        model=MODEL,
        contents=mensagem_usuario,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "max_output_tokens": 2000,
        },
    )

    return resposta.text
