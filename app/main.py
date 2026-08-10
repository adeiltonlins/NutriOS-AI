"""
API do chatbot nutricional — MVP com RAG (retrieval por TF-IDF) + Anthropic API.

Rodar localmente:
    export ANTHROPIC_API_KEY=sua_chave_aqui
    uvicorn app.main:app --reload

Depois acesse http://localhost:8000/docs para testar pela interface Swagger.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.knowledge_base import base_conhecimento
from app.llm import gerar_resposta, LINK_AGENDAMENTO, MARCADOR_LINK_PAGAMENTO, NUTRICIONISTA_NOME
from app import leads_store
from app import pagamento
import os

# Contato liberado pro paciente só depois do pagamento confirmado —
# ex: link do WhatsApp pessoal/profissional do nutricionista.
CONTATO_NUTRICIONISTA = os.environ.get("CONTATO_NUTRICIONISTA", LINK_AGENDAMENTO)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Nutri Chatbot API",
    description="Chatbot nutricional com RAG sobre dados TACO e diretrizes de saúde",
    version="0.1.0",
)

# Libera CORS pra facilitar testes com um frontend separado (ajuste em produção)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def servir_interface():
    """Serve a interface de chat (HTML) na URL raiz do site."""
    return FileResponse(STATIC_DIR / "index.html")


class MensagemHistorico(BaseModel):
    autor: str  # "user" ou "bot"
    texto: str


class PerguntaRequest(BaseModel):
    pergunta: str = Field(..., min_length=1, max_length=1000, description="Pergunta do usuário")
    historico: list[MensagemHistorico] = Field(default_factory=list, description="Mensagens anteriores da conversa, em ordem")
    session_id: str = Field(default="", max_length=100, description="Identificador único da conversa, gerado pelo navegador")


class RespostaResponse(BaseModel):
    resposta: str
    fontes_utilizadas: list[str]


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "alimentos_carregados": len(base_conhecimento.alimentos),
        "armazenamento_leads_ativo": leads_store.ARMAZENAMENTO_ATIVO,
    }


@app.post("/chat", response_model=RespostaResponse)
def chat(req: PerguntaRequest):
    if not req.pergunta.strip():
        raise HTTPException(status_code=400, detail="Pergunta vazia.")

    resultados = base_conhecimento.buscar_contexto(req.pergunta, top_k=5)
    contexto = base_conhecimento.formatar_contexto_para_prompt(resultados)

    historico_dict = [{"autor": m.autor, "texto": m.texto} for m in req.historico]

    # ---- Calcula o estado do convite/pagamento ANTES de chamar o modelo ----
    # O modelo nunca vê o link real (só o marcador), então ele sozinho não
    # tem como saber se já convidou ou se o pagamento já caiu — isso é
    # calculado aqui, com base no histórico e no Supabase, e passado pra
    # ele como contexto extra.
    lead_atual = leads_store.buscar_lead(req.session_id) if req.session_id else None
    ja_pago = bool(lead_atual and lead_atual.get("pago"))

    def _mensagem_ja_tem_link(texto: str) -> bool:
        return "mercadopago.com" in texto or (LINK_AGENDAMENTO and LINK_AGENDAMENTO in texto)

    ja_convidou_antes = any(
        m.autor == "bot" and _mensagem_ja_tem_link(m.texto) for m in req.historico
    )

    if ja_pago:
        estado_convite = "pago"
    elif ja_convidou_antes:
        estado_convite = "convidou_pendente"
    else:
        estado_convite = "nunca_convidou"

    try:
        resposta = gerar_resposta(req.pergunta, contexto, historico_dict, estado_convite)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao consultar o modelo de IA: {e}")

    # O Bruce usa um marcador em vez de escrever o link — aqui a gente
    # detecta a intenção de convidar pra consulta e troca pelo link real.
    #
    # TRAVA DE SEGURANÇA (independe do modelo obedecer a instrução ou não):
    # se o pagamento já foi confirmado, NUNCA gera uma preferência nova no
    # Mercado Pago — troca o marcador pelo contato de verdade direto. Isso
    # evita duplicar links/preferências e evita confundir quem já pagou.
    quis_agendar = MARCADOR_LINK_PAGAMENTO in resposta
    if quis_agendar:
        if ja_pago:
            resposta = resposta.replace(MARCADOR_LINK_PAGAMENTO, CONTATO_NUTRICIONISTA)
        else:
            link_real = None
            if pagamento.PAGAMENTO_ATIVO and req.session_id:
                link_real = pagamento.criar_link_pagamento(req.session_id)
            resposta = resposta.replace(MARCADOR_LINK_PAGAMENTO, link_real or LINK_AGENDAMENTO)

    fontes = []
    for r in resultados:
        if r["tipo"] == "alimento":
            fontes.append(r["dado"]["nome"])
        else:
            fontes.append(r["dado"]["titulo"])

    # Salva o histórico atualizado da conversa (não derruba a resposta se falhar)
    if req.session_id:
        historico_completo = historico_dict + [
            {"autor": "user", "texto": req.pergunta},
            {"autor": "bot", "texto": resposta},
        ]
        leads_store.salvar_lead(req.session_id, historico_completo, quis_agendar)

    return RespostaResponse(resposta=resposta, fontes_utilizadas=fontes)


@app.get("/pagamento/sucesso", response_class=HTMLResponse)
def pagamento_sucesso(
    payment_id: str = Query(default="", alias="payment_id"),
    external_reference: str = Query(default=""),
    status: str = Query(default=""),
):
    """
    Página de retorno do Mercado Pago após o pagamento. NUNCA confia só
    nesses parâmetros de URL (dá pra forjar) — sempre confere o status
    real direto na API antes de liberar qualquer contato.
    """
    pagamento_confirmado = False
    dados_pagamento = None

    if payment_id:
        dados_pagamento = pagamento.consultar_pagamento(payment_id)
    elif external_reference:
        resultados = pagamento.buscar_pagamentos_por_referencia(external_reference)
        dados_pagamento = resultados[0] if resultados else None

    if dados_pagamento and dados_pagamento.get("status") == "approved":
        pagamento_confirmado = True
        session_id_confirmado = dados_pagamento.get("external_reference") or external_reference
        if session_id_confirmado:
            leads_store.marcar_pago(session_id_confirmado, str(dados_pagamento.get("id", payment_id)))

    if pagamento_confirmado:
        corpo = f"""
        <h1>✅ Pagamento confirmado!</h1>
        <p>Obrigado! Aqui está o contato de {NUTRICIONISTA_NOME} pra combinar o melhor horário:</p>
        <p><a href="{CONTATO_NUTRICIONISTA}" style="font-size:18px;">Falar agora →</a></p>
        """
    else:
        corpo = """
        <h1>Pagamento em processamento</h1>
        <p>Assim que for confirmado, o contato é liberado automaticamente.
        Se você já pagou e essa mensagem não mudar em alguns minutos, chama a gente.</p>
        """

    return HTMLResponse(f"""
    <html>
    <head><meta charset="UTF-8"><title>Pagamento — Bruce</title></head>
    <body style="font-family: sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; text-align: center;">
        {corpo}
    </body>
    </html>
    """)


@app.get("/pagamento/pendente", response_class=HTMLResponse)
def pagamento_pendente():
    return HTMLResponse("<h2>Pagamento pendente</h2><p>Assim que for aprovado, o contato é liberado.</p>")


@app.get("/pagamento/erro", response_class=HTMLResponse)
def pagamento_erro():
    return HTMLResponse("<h2>Pagamento não concluído</h2><p>Você pode tentar novamente na conversa com o Bruce.</p>")


@app.post("/pagamento/webhook")
async def pagamento_webhook(request: Request):
    """
    Webhook assíncrono do Mercado Pago — é a fonte da verdade sobre
    pagamentos (pode chegar mesmo que a pessoa feche a aba antes do
    redirecionamento). O Mercado Pago manda o id do pagamento como query
    param (?type=payment&data.id=XXXX) ou no corpo, dependendo da
    configuração — tratamos os dois casos.
    """
    # O Mercado Pago manda notificações de tipos diferentes pro mesmo
    # evento (ex: topic=merchant_order e topic=payment). O id que vem
    # junto de merchant_order NÃO é um payment_id — consultar a API de
    # pagamentos com ele sempre dá 404. A notificação topic=payment traz
    # o id certo e cobre o mesmo evento, então só processamos essa.
    topic = request.query_params.get("topic") or request.query_params.get("type")
    if topic == "merchant_order":
        return {"status": "ignorado", "motivo": "topic merchant_order"}

    payment_id = request.query_params.get("data.id") or request.query_params.get("id")

    if not payment_id:
        try:
            body = await request.json()
            payment_id = str(body.get("data", {}).get("id", ""))
        except Exception:
            payment_id = None

    if not payment_id:
        return {"status": "ignorado", "motivo": "sem payment_id"}

    dados = pagamento.consultar_pagamento(payment_id)
    if dados and dados.get("status") == "approved":
        session_id = dados.get("external_reference")
        if session_id:
            leads_store.marcar_pago(session_id, payment_id)

    return {"status": "ok"}


@app.get("/agendar")
def agendar(session_id: str = Query(default="")):
    """
    Usado pelo botão fixo "Agendar consulta" do front-end. Reaproveita a
    MESMA lógica de geração de link do fluxo de chat (nunca cria um
    caminho paralelo sem tracking): se o pagamento estiver ativo e a
    sessão for válida, gera uma preferência real do Mercado Pago
    (com external_reference = session_id, pra manter o webhook
    funcionando); caso contrário, cai no link fixo de agendamento.
    """
    link = None
    if pagamento.PAGAMENTO_ATIVO and session_id:
        link = pagamento.criar_link_pagamento(session_id)
    return {"url": link or LINK_AGENDAMENTO}


@app.get("/contato")
def verificar_contato(session_id: str = Query(default="")):
    """
    Endpoint que o frontend pode consultar pra saber se já pode mostrar o
    contato do nutricionista pra essa sessão (só libera se pago=true).
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id é obrigatório.")

    lead = leads_store.buscar_lead(session_id)
    liberado = bool(lead and lead.get("pago"))

    return {
        "liberado": liberado,
        "contato": CONTATO_NUTRICIONISTA if liberado else None,
    }


@app.get("/painel", response_class=HTMLResponse)
def painel_leads(token: str = Query(default="")):
    """
    Painel simples pro nutricionista ver os leads que conversaram com o Bruce.
    Protegido por um token simples (não é autenticação robusta — dá pra
    melhorar depois, mas serve bem pro MVP).
    """
    token_esperado = os.environ.get("ADMIN_TOKEN", "")
    if not token_esperado or token != token_esperado:
        return HTMLResponse(
            "<h2>Acesso negado</h2><p>Adicione ?token=SEU_TOKEN na URL.</p>",
            status_code=401,
        )

    leads = leads_store.listar_leads(limite=200)

    linhas_html = ""
    for lead in leads:
        agendou = "✅ Sim" if lead.get("quis_agendar") else "—"
        atualizado = lead.get("atualizado_em", "")[:16].replace("T", " ")
        session_curta = lead.get("session_id", "")[:8]
        linhas_html += f"""
        <tr>
            <td>{session_curta}</td>
            <td>{atualizado}</td>
            <td>{agendou}</td>
            <td><a href="/painel/conversa?token={token}&session_id={lead.get('session_id', '')}">Ver conversa</a></td>
        </tr>"""

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Painel de Leads — Bruce</title>
        <style>
            body {{ font-family: sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #ddd; }}
            th {{ background: #f4f4f4; }}
            h1 {{ margin-bottom: 4px; }}
            .total {{ color: #666; }}
        </style>
    </head>
    <body>
        <h1>Painel de Leads</h1>
        <p class="total">{len(leads)} conversas registradas</p>
        <table>
            <tr><th>Sessão</th><th>Última atividade</th><th>Pediu agendamento?</th><th></th></tr>
            {linhas_html if linhas_html else '<tr><td colspan="4">Nenhum lead ainda.</td></tr>'}
        </table>
    </body>
    </html>
    """


@app.get("/painel/conversa", response_class=HTMLResponse)
def painel_conversa(token: str = Query(default=""), session_id: str = Query(default="")):
    """Mostra a conversa completa de um lead específico."""
    token_esperado = os.environ.get("ADMIN_TOKEN", "")
    if not token_esperado or token != token_esperado:
        return HTMLResponse("<h2>Acesso negado</h2>", status_code=401)

    leads = leads_store.listar_leads(limite=200)
    lead = next((l for l in leads if l.get("session_id") == session_id), None)

    if not lead:
        return HTMLResponse("<h2>Conversa não encontrada</h2>", status_code=404)

    import json
    historico = json.loads(lead.get("historico", "[]"))

    mensagens_html = ""
    for msg in historico:
        autor = "Pessoa" if msg.get("autor") == "user" else "Bruce"
        cor = "#EEE" if msg.get("autor") == "user" else "#F2F1E6"
        mensagens_html += f"""
        <div style="background:{cor}; padding:12px; border-radius:8px; margin-bottom:10px;">
            <strong>{autor}:</strong><br>{msg.get('texto', '')}
        </div>"""

    return f"""
    <html>
    <head><meta charset="UTF-8"><title>Conversa — Bruce</title></head>
    <body style="font-family: sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px;">
        <p><a href="/painel?token={token}">&larr; Voltar pro painel</a></p>
        <h1>Conversa completa</h1>
        {mensagens_html}
    </body>
    </html>
    """
