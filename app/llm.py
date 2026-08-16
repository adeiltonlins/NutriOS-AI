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
from google.genai import errors

# Modelo estável por padrão. O alias ``latest`` pode mudar sem deploy e é
# menos previsível para uma aplicação clínica em produção.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")

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


SYSTEM_PROMPT_TEMPLATE = """\
Você se chama {ASSISTENTE_NOME}. Você é a assistente virtual de {NUTRICIONISTA_NOME}, \
especialista em {NUTRICIONISTA_ESPECIALIDADE}. Você conversa com pessoas que \
chegaram até aqui interessadas em nutrição, mas que ainda NÃO são clientes.

SEU OBJETIVO PRINCIPAL:
Ser genuinamente útil em cada resposta — isso já é, por si só, o que \
constrói confiança e leva a pessoa a querer uma consulta. Você entende a \
situação dela (o que busca, há quanto tempo tenta resolver isso, o que já \
tentou) e, quando fizer sentido, convida pra agendar e pagar a consulta com \
{NUTRICIONISTA_NOME}. Depois da confirmação do pagamento, ela recebe o \
contato direto para marcar o horário.

ESTRUTURA DE CADA RESPOSTA COM CONTEÚDO (quando a pessoa faz uma pergunta \
factual, não quando ela só está batendo papo ou respondendo algo simples):
1. Responda a pergunta de verdade, com informação útil (usando o CONTEXTO \
abaixo, quando houver).
2. Explique de forma simples o porquê, sem jargão técnico desnecessário.
3. Deixe claro, com naturalidade, que a resposta ideal varia de pessoa pra \
pessoa (rotina, corpo, histórico) — isso não é uma desculpa vazia, é \
verdade, e é o que justifica um acompanhamento individual.
4. SÓ NESSE MOMENTO, e não em toda mensagem, deixe uma abertura leve pra \
consulta — nunca uma cobrança. Algo como "se quiser, posso te orientar \
melhor por aqui, ou você pode marcar um horário pra algo mais \
personalizado" — nunca insista ou repita esse convite em seguida se a \
pessoa não demonstrar interesse.

COMO CALIBRAR A INSISTÊNCIA (crítico — os dois perfis abaixo merecem uma \
boa experiência):
- Se a pessoa está só tirando dúvidas pontuais, sem sinal de querer avançar, \
responda bem e siga o papo normalmente. NÃO force nem repita o convite pra \
consulta em toda resposta — isso afasta. Uma abertura leve a cada poucas \
trocas de mensagem, no máximo, já é suficiente.
- Se a pessoa demonstra dúvida, frustração com tentativas anteriores, ou \
pergunta algo que sinaliza interesse real em resolver o problema de vez, aí \
sim conduza com mais intenção pro agendamento — sempre de forma genuína, \
nunca com pressão, urgência falsa ou tom de vendedor.
- NUNCA soe como um robô de vendas repetindo o mesmo gancho. Varie a forma \
como você abre espaço pra consulta, e só faça isso quando fizer sentido no \
fluxo natural da conversa.

COMO CONDUZIR A CONVERSA:
1. Se for a primeira mensagem da pessoa, se apresente brevemente e pergunte \
o que ela está buscando (ex: emagrecer, ganhar massa, resolver algum \
desconforto alimentar, etc.) — não convide pra agendar ainda.
2. Nas mensagens seguintes, vá entendendo melhor a situação dela: há quanto \
tempo isso é um problema, o que ela já tentou (dietas, apps, outros \
profissionais), e o que não funcionou. Faça UMA pergunta de cada vez, não \
uma lista.
3. Quando decidir convidar pra consulta (seguindo a calibragem acima), \
escreva o convite naturalmente e inclua, no lugar do link, EXATAMENTE este \
texto (sem alterar nada): {MARCADOR_LINK_PAGAMENTO}. O sistema substitui \
esse texto pelo link de pagamento de verdade — nunca escreva um link você \
mesmo.
4. Se a pessoa perguntar algo que claramente não é do seu escopo (fora de \
nutrição), redirecione com gentileza de volta pro tema.

REGRA CRÍTICA — NÃO REPETIR CONVITE JÁ ENVIADO:
Se o bloco "SITUAÇÃO DO CONVITE NESTA CONVERSA" (mais abaixo, junto da \
mensagem da pessoa) disser que você já convidou ou que o pagamento já foi \
confirmado, siga a instrução dele à risca: NÃO envie o marcador \
{MARCADOR_LINK_PAGAMENTO} de novo nem repita o convite por conta própria. \
Só volte a mandar o marcador se a pessoa pedir isso explicitamente (ex: \
"perdi o link", "manda de novo", "quero pagar agora", "já paguei mas não \
recebi o contato"). Uma mensagem neutra da pessoa (ex: "ok", "obrigado", \
"beleza", "entendi") NUNCA é motivo pra reconvidar.

REGRAS DE SEGURANÇA (OBRIGATÓRIAS, NUNCA QUEBRE):
- Priorize as informações do CONTEXTO. Quando ele não trouxer um valor \
exato para uma dúvida comum e de baixo risco (por exemplo calorias \
aproximadas de uma fruta), use conhecimento nutricional geral, deixe claro \
que é uma estimativa e explique o que faz o valor variar. Não use a falta de \
um dado exato como desculpa para deixar a pessoa sem uma resposta útil.
- Quando a pergunta estiver incompleta, ambígua ou escrita com erros, tente \
entender a intenção, responda o que for seguro e faça UMA pergunta curta de \
confirmação. Nunca repreenda a pessoa pela forma como escreveu.
- NUNCA prescreva uma dieta fechada e individualizada (cardápio com \
gramas e horários específicos). Isso é trabalho da consulta paga, não seu. \
Se pedirem isso diretamente, explique que esse tipo de plano precisa de \
avaliação individual e é exatamente isso que a consulta oferece.
- NUNCA dê diagnóstico médico nem avalie condições de saúde específicas \
(diabetes, doenças, gestação, etc.) — direcione pra consulta ou médico.
- Nunca crie senso de urgência falso, nem use pressão ou manipulação pra \
convencer a pessoa a agendar. O convite deve ser genuíno e sem pressão.
- NUNCA mencione fontes de dados técnicas (ex: "tabela TACO", "base de \
dados") na conversa — fale como uma pessoa que sabe do assunto, não como \
um sistema citando sua fonte.
- Responda sempre em português do Brasil, num tom caloroso, direto e \
confiante — nunca hesitante ou robótico.
"""


def montar_system_prompt(config: dict | None = None) -> str:
    config = config or {}
    return SYSTEM_PROMPT_TEMPLATE.format(
        ASSISTENTE_NOME=config.get("identidade_ia") or "NutriOS",
        NUTRICIONISTA_NOME=config.get("nome") or NUTRICIONISTA_NOME,
        NUTRICIONISTA_ESPECIALIDADE=config.get("especialidade") or NUTRICIONISTA_ESPECIALIDADE,
        MARCADOR_LINK_PAGAMENTO=MARCADOR_LINK_PAGAMENTO,
    ) + (f"\nMENSAGEM DE BOAS-VINDAS PREFERIDA:\n{config.get('mensagem_inicial', '')}" if config.get("mensagem_inicial") else "") + (f"\nIDENTIDADE/MENSAGEM ADICIONAL DO CLIENTE:\n{config.get('prompt', '')}" if config.get("prompt") else "")

SYSTEM_PROMPT = montar_system_prompt()

PATIENT_SYSTEM_PROMPT_TEMPLATE = """\
Você se chama {ASSISTENTE_NOME}. Você acompanha os pacientes ativos de {NUTRICIONISTA_NOME}, especialista em {NUTRICIONISTA_ESPECIALIDADE}.
Este é um portal privado: a pessoa já é paciente. Responda apenas sobre alimentação, rotina, adesão e orientações gerais do acompanhamento, usando o contexto fornecido sem inventar dados.
Nunca fale sobre venda, cobrança, pagamento, contratação, lead ou convite para consulta. Nunca gere links, ofertas ou chamadas comerciais.
Não prescreva nem altere dieta, quantidades, restrições ou medicações. Em sintomas, alergias, piora clínica ou decisões individuais, oriente a falar com o nutricionista ou procurar atendimento adequado.
Responda em português do Brasil, com clareza, acolhimento e objetividade.
"""


def montar_patient_system_prompt(config: dict | None = None) -> str:
    config = config or {}
    return PATIENT_SYSTEM_PROMPT_TEMPLATE.format(
        ASSISTENTE_NOME=config.get("identidade_ia") or "NutriOS",
        NUTRICIONISTA_NOME=config.get("nome") or NUTRICIONISTA_NOME,
        NUTRICIONISTA_ESPECIALIDADE=config.get("especialidade") or NUTRICIONISTA_ESPECIALIDADE,
    )


def gerar_resposta_paciente(pergunta: str, contexto: str, historico: list[dict] | None = None, client_config: dict | None = None) -> str:
    """Gera orientação para paciente ativo sem atravessar o funil comercial."""
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    contents = []
    for msg in (historico or []):
        role = "user" if msg.get("autor") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.get("texto", "")}]})
    contents.append({"role": "user", "parts": [{"text": f"CONTEXTO DO ACOMPANHAMENTO:\n{contexto}\n\nPERGUNTA DO PACIENTE:\n{pergunta}"}]})
    models = [MODEL] + ([FALLBACK_MODEL] if FALLBACK_MODEL and FALLBACK_MODEL != MODEL else [])
    last_error = None
    for model in models:
        try:
            resposta = client.models.generate_content(model=model, contents=contents, config={"system_instruction": montar_patient_system_prompt(client_config), "max_output_tokens": 2000})
            if str(resposta.text or "").strip():
                return resposta.text
            last_error = RuntimeError("Resposta vazia do provedor")
        except errors.APIError as exc:
            last_error = exc
            if exc.code in {400, 401, 403, 429}:
                break
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("Nenhum modelo de IA disponível")


def gerar_resposta(
    pergunta: str,
    contexto: str,
    historico: list[dict] | None = None,
    estado_convite: str = "nunca_convidou",
    client_config: dict | None = None,
) -> str:
    """
    Gera a resposta do Bruce, considerando o histórico da conversa (memória).

    historico: lista de mensagens anteriores, no formato
        [{"autor": "user", "texto": "..."}, {"autor": "bot", "texto": "..."}]

    estado_convite: calculado pelo backend (main.py) a cada request, com
    base no que já aconteceu nesta sessão — o modelo NÃO tem como saber
    isso sozinho olhando só o texto da conversa (o link real nunca aparece
    pra ele, só o marcador). Valores possíveis:
        "nunca_convidou"   — ainda não convidou pra consulta nesta conversa
        "convidou_pendente" — já convidou, mas o pagamento ainda não foi
                               confirmado
        "pago"              — o pagamento já foi confirmado
    """
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    # Monta a lista de turnos no formato que a API do Gemini espera
    contents = []
    for msg in (historico or []):
        role = "user" if msg.get("autor") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.get("texto", "")}]})

    situacao_convite = {
        "nunca_convidou": "Você ainda NÃO convidou essa pessoa pra consulta "
            "nesta conversa. Pode convidar quando fizer sentido, seguindo "
            "suas instruções normais.",
        "convidou_pendente": "Você JÁ convidou essa pessoa pra consulta "
            "nesta conversa e o link já foi enviado. O pagamento ainda não "
            "foi confirmado. NÃO reenvie o marcador nem repita o convite "
            "por conta própria — só se ela pedir explicitamente. Se ela só "
            "mandar algo neutro, responda normalmente sem tocar no assunto "
            "pagamento.",
        "pago": "O pagamento dessa pessoa JÁ foi confirmado! NÃO convide "
            "pra pagar de novo e NÃO envie o marcador de link em hipótese "
            "nenhuma. Se ela perguntar sobre o contato, diga que ele "
            "aparece automaticamente na tela assim que a confirmação "
            "processa, com tranquilidade.",
    }.get(estado_convite, "")

    mensagem_atual = f"""CONTEXTO (base de dados nutricional, use se for relevante pra pergunta):
{contexto}

SITUAÇÃO DO CONVITE NESTA CONVERSA:
{situacao_convite}

MENSAGEM DA PESSOA:
{pergunta}"""

    contents.append({"role": "user", "parts": [{"text": mensagem_atual}]})

    config = {
        "system_instruction": montar_system_prompt(client_config),
        "max_output_tokens": 2000,
    }
    models = [MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL not in models:
        models.append(FALLBACK_MODEL)

    last_error = None
    for model in models:
        try:
            resposta = client.models.generate_content(model=model, contents=contents, config=config)
            if str(resposta.text or "").strip():
                return resposta.text
            last_error = RuntimeError("Resposta vazia do provedor")
        except errors.APIError as exc:
            last_error = exc
            # Chave inválida ou sem cota também falhará no segundo modelo.
            if exc.code in {400, 401, 403, 429}:
                break
        except Exception as exc:
            last_error = exc

    raise last_error or RuntimeError("Nenhum modelo de IA disponível")


def resposta_contingencia(pergunta: str, client_config: dict | None = None) -> str:
    """Entrega orientação segura quando o provedor externo está indisponível."""
    texto = pergunta.casefold()
    profissional = (client_config or {}).get("nome") or "seu nutricionista"

    if "lactose" in texto:
        return (
            "Em geral, você pode considerar iogurte e leite sem lactose, bebidas vegetais sem açúcar, "
            "ovos, frutas, aveia e tapioca com um recheio proteico. Confira o rótulo para evitar leite, "
            "soro de leite ou lactose quando houver sensibilidade. A melhor combinação depende do seu plano "
            f"e da sua tolerância; confirme quantidades e substituições com {profissional}."
        )
    if any(term in texto for term in ("café da manhã", "cafe da manha", "desjejum")):
        return (
            "Uma base segura para o café da manhã é combinar uma fonte de proteína, uma fruta e uma fonte "
            "de carboidrato ou fibra. Exemplos gerais incluem ovos com fruta e aveia, ou iogurte com fruta "
            f"e sementes. As porções devem seguir o plano definido por {profissional}."
        )
    if any(term in texto for term in ("água", "agua", "hidrata")):
        return (
            "Distribua a ingestão de água ao longo do dia e observe sede, cor da urina, clima e atividade "
            f"física. Necessidades individuais variam; {profissional} pode ajustar uma meta ao seu caso."
        )
    if any(term in texto for term in ("emagrecer", "perder peso", "ganhar massa", "massa muscular")):
        return (
            "O resultado costuma depender da regularidade das refeições, qualidade do sono, atividade física "
            "e de um plano compatível com sua rotina. Evite mudanças extremas ou cortar grupos alimentares sem "
            f"avaliação; registre sua dificuldade para {profissional} ajustar o acompanhamento."
        )
    return (
        "A conexão com a inteligência nutricional está temporariamente limitada. Enquanto ela se restabelece, "
        "mantenha as orientações do seu plano e não altere quantidades ou restrições por conta própria. "
        f"Se a dúvida envolver sintomas, alergias ou mudança clínica, fale diretamente com {profissional}."
    )
