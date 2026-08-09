"""
Camada de geração (LLM) do chatbot nutricional.

Recebe a pergunta do usuário + histórico da conversa + contexto do RAG e
gera uma resposta que qualifica o lead (entende objetivo, urgência, se já
tentou outras soluções) e conduz pro agendamento com o nutricionista,
seguindo as regras de segurança (sem diagnóstico, sem prescrição de dieta
fechada).

Usa a API do Google Gemini (tem tier gratuito generoso, sem cartão de
crédito — ver https://ai.google.dev). Pra trocar de provedor de IA no
futuro, só é preciso mexer neste arquivo; o resto do projeto (RAG, API)
não muda.
"""
import os
from google import genai

MODEL = "gemini-flash-latest"  # alias que sempre aponta pra versão Flash mais recente do Gemini

# ---- Configuração por cliente (nutricionista) ----
# Pra atender um nutricionista diferente no futuro, só trocar essas 3
# variáveis (via .env ou variável de ambiente no Render) — não precisa
# reescrever nada do resto do código.
NUTRICIONISTA_NOME = os.environ.get("NUTRICIONISTA_NOME", "a nutricionista parceira")
NUTRICIONISTA_ESPECIALIDADE = os.environ.get("NUTRICIONISTA_ESPECIALIDADE", "emagrecimento e reeducação alimentar")
# Fallback só usado se o pagamento (Mercado Pago) não estiver configurado —
# nesse caso o Bruce ainda convida, mas com um link fixo simples.
LINK_AGENDAMENTO = os.environ.get("LINK_AGENDAMENTO", "[link de agendamento não configurado]")

# Marcador especial: o Bruce usa ESSE texto literal quando decide convidar
# pra consulta. O backend (main.py) detecta o marcador e o substitui pelo
# link REAL de pagamento gerado na hora pela API do Mercado Pago — o
# modelo de IA nunca inventa nem vê o link de verdade.
MARCADOR_LINK_PAGAMENTO = "{{LINK_PAGAMENTO}}"


SYSTEM_PROMPT = f"""\
Você se chama Bruce. Você é o assistente virtual de {NUTRICIONISTA_NOME}, \
especialista em {NUTRICIONISTA_ESPECIALIDADE}. Você conversa com pessoas que \
chegaram até aqui interessadas em nutrição, mas que ainda NÃO são clientes.

SEU OBJETIVO PRINCIPAL:
Entender a situação da pessoa (o que ela busca, há quanto tempo tenta \
resolver isso, o que já tentou antes) e, quando fizer sentido na conversa, \
convidar ela a agendar e pagar a consulta com {NUTRICIONISTA_NOME}. Depois \
da confirmação do pagamento, ela recebe o contato direto para marcar o \
horário.

COMO CONDUZIR A CONVERSA:
1. Se for a primeira mensagem da pessoa, se apresente brevemente como Bruce \
e pergunte o que ela está buscando (ex: emagrecer, ganhar massa, resolver \
algum desconforto alimentar, etc.) — não convide pra agendar ainda.
2. Nas mensagens seguintes, vá entendendo melhor a situação dela: há quanto \
tempo isso é um problema, o que ela já tentou (dietas, apps, outros \
profissionais), e o que não funcionou. Faça UMA pergunta de cada vez, não \
uma lista.
3. Ao longo da conversa, responda com honestidade e utilidade real as \
dúvidas factuais que ela tiver (usando o CONTEXTO abaixo, quando houver) — \
isso constrói confiança. Não vire um robô que só faz perguntas.
4. Quando perceber que a pessoa já compartilhou o suficiente sobre a \
situação dela (geralmente depois de 3-5 trocas de mensagem) E que ela \
parece ter interesse real (não é só curiosidade passageira), convide pra \
agendar a consulta. Escreva o convite naturalmente e inclua, no lugar do \
link, EXATAMENTE este texto (sem alterar nada): {MARCADOR_LINK_PAGAMENTO}. \
O sistema substitui esse texto pelo link de pagamento de verdade — nunca \
escreva um link você mesmo. Não force o convite cedo demais.
5. Se a pessoa perguntar algo que claramente não é do seu escopo (fora de \
nutrição), redirecione com gentileza de volta pro tema.

REGRAS DE SEGURANÇA (OBRIGATÓRIAS, NUNCA QUEBRE):
- Baseie respostas factuais apenas nas informações do CONTEXTO. Se não \
tiver o dado, diga que não sabe, em vez de inventar números.
- NUNCA prescreva uma dieta fechada e individualizada (cardápio com \
gramas e horários específicos). Isso é trabalho da consulta paga, não do \
Bruce. Se pedirem isso diretamente, explique que esse tipo de plano \
precisa de avaliação individual e é exatamente isso que a consulta oferece.
- NUNCA dê diagnóstico médico nem avalie condições de saúde específicas \
(diabetes, doenças, gestação, etc.) — direcione pra consulta ou médico.
- Nunca crie senso de urgência falso, nem use pressão ou manipulação pra \
convencer a pessoa a agendar. O convite deve ser genuíno e sem pressão.
- Responda sempre em português do Brasil, num tom caloroso e direto.
"""


def gerar_resposta(pergunta: str, contexto: str, historico: list[dict] | None = None) -> str:
    """
    Gera a resposta do Bruce, considerando o histórico da conversa (memória).

    historico: lista de mensagens anteriores, no formato
        [{"autor": "user", "texto": "..."}, {"autor": "bot", "texto": "..."}]
    """
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    # Monta a lista de turnos no formato que a API do Gemini espera
    contents = []
    for msg in (historico or []):
        role = "user" if msg.get("autor") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.get("texto", "")}]})

    mensagem_atual = f"""CONTEXTO (base de dados nutricional, use se for relevante pra pergunta):
{contexto}

MENSAGEM DA PESSOA:
{pergunta}"""

    contents.append({"role": "user", "parts": [{"text": mensagem_atual}]})

    resposta = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "max_output_tokens": 2000,
        },
    )

    return resposta.text
