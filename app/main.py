"""
API do chatbot nutricional — MVP com RAG (retrieval por TF-IDF) + Anthropic API.

Rodar localmente:
    export ANTHROPIC_API_KEY=sua_chave_aqui
    uvicorn app.main:app --reload

Depois acesse http://localhost:8000/docs para testar pela interface Swagger.
"""
import csv
import html
import io
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel, Field

from app.knowledge_base import base_conhecimento
from app.llm import gerar_resposta, LINK_AGENDAMENTO, MARCADOR_LINK_PAGAMENTO, NUTRICIONISTA_NOME
from app import leads_store
from app import pagamento
import os


def token_valido(token: str) -> bool:
    """Compara o token do admin usando comparação de tempo constante
    (evita timing attack) e nunca autoriza se ADMIN_TOKEN não estiver
    configurado."""
    token_esperado = os.environ.get("ADMIN_TOKEN", "")
    if not token_esperado:
        return False
    return secrets.compare_digest(token, token_esperado)

# Contato liberado pro paciente só depois do pagamento confirmado —
# ex: link do WhatsApp pessoal/profissional do nutricionista.
CONTATO_NUTRICIONISTA = os.environ.get("CONTATO_NUTRICIONISTA", LINK_AGENDAMENTO)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Nutri Chatbot API",
    description="Chatbot nutricional com RAG sobre dados TACO e diretrizes de saúde",
    version="0.1.0",
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Restringe CORS ao(s) domínio(s) reais do site (configure ALLOWED_ORIGINS
# no .env, separado por vírgula, ex: "https://seusite.com,https://www.seusite.com").
# Sem configurar, cai pra URL_BASE (Render) — nunca "*" em produção.
_origens_env = os.environ.get("ALLOWED_ORIGINS", "")
if _origens_env:
    ALLOWED_ORIGINS = [o.strip() for o in _origens_env.split(",") if o.strip()]
else:
    _url_base = os.environ.get("URL_BASE", "").rstrip("/")
    ALLOWED_ORIGINS = [_url_base] if _url_base else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
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
    historico: list[MensagemHistorico] = Field(default_factory=list, max_length=40, description="Mensagens anteriores da conversa, em ordem (limitado pra evitar payloads gigantes)")
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
@limiter.limit("15/minute")
def chat(request: Request, req: PerguntaRequest):
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

    session_id_confirmado = ""
    if dados_pagamento and dados_pagamento.get("status") == "approved":
        pagamento_confirmado = True
        session_id_confirmado = dados_pagamento.get("external_reference") or external_reference
        if session_id_confirmado:
            leads_store.marcar_pago(session_id_confirmado, str(dados_pagamento.get("id", payment_id)))

    # session_id pra usar no polling do lado pendente — o Mercado Pago
    # sempre reenvia o external_reference na URL de retorno (mesmo quando
    # o pagamento ainda não está aprovado), então dá pra usar ele aqui.
    session_id_para_poll = session_id_confirmado or external_reference

    if pagamento_confirmado:
        corpo = f"""
        <div id="conteudo">
            <h1>✅ Pagamento confirmado!</h1>
            <p>Obrigado! Aqui está o contato de {NUTRICIONISTA_NOME} pra combinar o melhor horário:</p>
            <p><a href="{CONTATO_NUTRICIONISTA}" style="font-size:18px;">Falar agora →</a></p>
        </div>
        """
        script_polling = ""
    else:
        corpo = """
        <div id="conteudo">
            <h1>Pagamento em processamento</h1>
            <p>Assim que for confirmado, o contato aparece aqui automaticamente
            — não precisa recarregar a página.</p>
            <p style="color:#888; font-size:14px;">Verificando a cada poucos segundos…</p>
        </div>
        """
        # Consulta /contato periodicamente e troca o conteúdo da página
        # sozinho quando o pagamento for liberado, sem precisar de reload.
        script_polling = f"""
        <script>
        (function() {{
            const sessionId = {session_id_para_poll!r};
            if (!sessionId) return;

            async function checarContato() {{
                try {{
                    const resp = await fetch('/contato?session_id=' + encodeURIComponent(sessionId));
                    const dados = await resp.json();
                    if (dados.liberado && dados.contato) {{
                        document.getElementById('conteudo').innerHTML = `
                            <h1>✅ Pagamento confirmado!</h1>
                            <p>Obrigado! Aqui está o contato de {NUTRICIONISTA_NOME} pra combinar o melhor horário:</p>
                            <p><a href="${{dados.contato}}" style="font-size:18px;">Falar agora →</a></p>
                        `;
                        clearInterval(intervalo);
                    }}
                }} catch (e) {{
                    // silenciosamente tenta de novo no próximo ciclo
                }}
            }}

            const intervalo = setInterval(checarContato, 4000);
            checarContato();
        }})();
        </script>
        """

    return HTMLResponse(f"""
    <html>
    <head><meta charset="UTF-8"><title>Pagamento — Bruce</title></head>
    <body style="font-family: sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; text-align: center;">
        {corpo}
        {script_polling}
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
@limiter.limit("10/minute")
def agendar(request: Request, session_id: str = Query(default="")):
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
    if not token_valido(token):
        return HTMLResponse(
            "<h2>Acesso negado</h2><p>Adicione ?token=SEU_TOKEN na URL.</p>",
            status_code=401,
        )

    leads = leads_store.listar_leads(limite=200)

    total = len(leads)
    total_agendou = sum(1 for l in leads if l.get("quis_agendar"))
    total_pago = sum(1 for l in leads if l.get("pago"))
    # Conversão calculada sobre quem pediu agendamento (base mais justa que
    # o total de conversas, já que nem toda conversa chega a pedir).
    taxa_conversao = (total_pago / total_agendou * 100) if total_agendou else 0

    linhas_html = ""
    for lead in leads:
        agendou = "✅ Sim" if lead.get("quis_agendar") else "—"
        pago = "💰 Sim" if lead.get("pago") else "—"
        atualizado = html.escape(lead.get("atualizado_em", "")[:16].replace("T", " "))
        session_id_raw = lead.get("session_id", "")
        session_curta = html.escape(session_id_raw[:8])
        link_conversa = f"/painel/conversa?token={html.escape(token, quote=True)}&session_id={html.escape(session_id_raw, quote=True)}"
        linhas_html += f"""
        <tr>
            <td>{session_curta}</td>
            <td>{atualizado}</td>
            <td>{agendou}</td>
            <td>{pago}</td>
            <td><a href="{link_conversa}">Ver conversa</a></td>
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
            .stats {{ display: flex; gap: 16px; margin-top: 20px; flex-wrap: wrap; }}
            .card {{ background: #f4f4f4; border-radius: 10px; padding: 16px 20px; min-width: 140px; }}
            .card .valor {{ font-size: 26px; font-weight: bold; }}
            .card .rotulo {{ color: #666; font-size: 13px; }}
            .links {{ margin-top: 16px; font-size: 14px; }}
            .links a {{ margin-right: 16px; }}
        </style>
    </head>
    <body>
        <h1>Painel de Leads</h1>
        <p class="total">{total} conversas registradas</p>

        <div class="stats">
            <div class="card"><div class="valor">{total}</div><div class="rotulo">Conversas totais</div></div>
            <div class="card"><div class="valor">{total_agendou}</div><div class="rotulo">Pediram agendamento</div></div>
            <div class="card"><div class="valor">{total_pago}</div><div class="rotulo">Pagaram</div></div>
            <div class="card"><div class="valor">{taxa_conversao:.0f}%</div><div class="rotulo">Conversão (pediu → pagou)</div></div>
        </div>

        <div class="links">
            <a href="/painel/exportar?token={token}">⬇️ Exportar CSV</a>
            <a href="/painel/lembretes?token={token}">⏰ Quem precisa de lembrete</a>
        </div>

        <table>
            <tr><th>Sessão</th><th>Última atividade</th><th>Pediu agendamento?</th><th>Pagou?</th><th></th></tr>
            {linhas_html if linhas_html else '<tr><td colspan="5">Nenhum lead ainda.</td></tr>'}
        </table>
    </body>
    </html>
    """


@app.get("/painel/exportar")
def exportar_leads_csv(token: str = Query(default="")):
    """Exporta os leads em CSV pro nutricionista abrir no Excel/Sheets."""
    if not token_valido(token):
        raise HTTPException(status_code=401, detail="Acesso negado.")

    def _campo_seguro(valor: str) -> str:
        # Evita "CSV injection": se um campo controlado pelo usuário (ex:
        # session_id) começar com =, +, - ou @, o Excel/Sheets pode
        # interpretar como fórmula ao abrir o arquivo.
        if valor and valor[0] in ("=", "+", "-", "@"):
            return "'" + valor
        return valor

    leads = leads_store.listar_leads(limite=1000)

    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["session_id", "criado_em", "atualizado_em", "quis_agendar", "pago", "payment_id", "pago_em"])
    for lead in leads:
        escritor.writerow([
            _campo_seguro(lead.get("session_id", "")),
            lead.get("criado_em", ""),
            lead.get("atualizado_em", ""),
            lead.get("quis_agendar", False),
            lead.get("pago", False),
            lead.get("payment_id", ""),
            lead.get("pago_em", ""),
        ])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@app.get("/painel/lembretes", response_class=HTMLResponse)
def leads_para_lembrete(token: str = Query(default=""), dias: int = Query(default=2)):
    """
    Lista quem pediu agendamento, ainda não pagou, e está parado há X dias
    (padrão 2) — pra você mandar uma mensagem manual por enquanto. Quando
    quiser automatizar o envio (e-mail/WhatsApp), essa é a lista que serve
    de base.
    """
    if not token_valido(token):
        return HTMLResponse("<h2>Acesso negado</h2>", status_code=401)

    leads = leads_store.listar_leads(limite=1000)
    limite_data = datetime.now(timezone.utc) - timedelta(days=dias)

    candidatos = []
    for lead in leads:
        if not lead.get("quis_agendar") or lead.get("pago"):
            continue
        atualizado_str = lead.get("atualizado_em", "")
        if not atualizado_str:
            continue
        try:
            atualizado_dt = datetime.fromisoformat(atualizado_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if atualizado_dt <= limite_data:
            candidatos.append(lead)

    linhas_html = ""
    for lead in candidatos:
        atualizado = html.escape(lead.get("atualizado_em", "")[:16].replace("T", " "))
        session_id_raw = lead.get("session_id", "")
        session_curta = html.escape(session_id_raw[:8])
        link_conversa = f"/painel/conversa?token={html.escape(token, quote=True)}&session_id={html.escape(session_id_raw, quote=True)}"
        linhas_html += f"""
        <tr>
            <td>{session_curta}</td>
            <td>{atualizado}</td>
            <td><a href="{link_conversa}">Ver conversa</a></td>
        </tr>"""

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Lembretes pendentes — Bruce</title>
        <style>
            body {{ font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #ddd; }}
            th {{ background: #f4f4f4; }}
        </style>
    </head>
    <body>
        <p><a href="/painel?token={token}">&larr; Voltar pro painel</a></p>
        <h1>Precisam de lembrete</h1>
        <p>Pediram agendamento, não pagaram, e estão parados há {dias}+ dias.</p>
        <table>
            <tr><th>Sessão</th><th>Última atividade</th><th></th></tr>
            {linhas_html if linhas_html else '<tr><td colspan="3">Ninguém pendente por enquanto 🎉</td></tr>'}
        </table>
    </body>
    </html>
    """


@app.get("/painel/conversa", response_class=HTMLResponse)
def painel_conversa(token: str = Query(default=""), session_id: str = Query(default="")):
    """Mostra a conversa completa de um lead específico."""
    if not token_valido(token):
        return HTMLResponse("<h2>Acesso negado</h2>", status_code=401)

    leads = leads_store.listar_leads(limite=200)
    lead = next((l for l in leads if l.get("session_id") == session_id), None)

    if not lead:
        return HTMLResponse("<h2>Conversa não encontrada</h2>", status_code=404)

    import json
    historico = json.loads(lead.get("historico", "[]"))

    mensagens_html = ""
    for msg in historico:
        # texto e autor vêm do histórico salvo, que é 100% controlado pelo
        # navegador do visitante — NUNCA jogar direto no HTML sem escapar,
        # ou vira XSS armazenado (rouba o token do admin via document.location).
        autor_raw = msg.get("autor")
        autor = "Pessoa" if autor_raw == "user" else "Bruce"
        cor = "#EEE" if autor_raw == "user" else "#F2F1E6"
        texto_seguro = html.escape(str(msg.get("texto", ""))).replace("\n", "<br>")
        mensagens_html += f"""
        <div style="background:{cor}; padding:12px; border-radius:8px; margin-bottom:10px;">
            <strong>{autor}:</strong><br>{texto_seguro}
        </div>"""

    link_voltar = f"/painel?token={html.escape(token, quote=True)}"
    return f"""
    <html>
    <head><meta charset="UTF-8"><title>Conversa — Bruce</title></head>
    <body style="font-family: sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px;">
        <p><a href="{link_voltar}">&larr; Voltar pro painel</a></p>
        <h1>Conversa completa</h1>
        {mensagens_html}
    </body>
    </html>
    """
