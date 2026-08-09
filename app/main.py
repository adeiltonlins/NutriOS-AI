"""
API do chatbot nutricional — MVP com RAG (retrieval por TF-IDF) + Anthropic API.

Rodar localmente:
    export ANTHROPIC_API_KEY=sua_chave_aqui
    uvicorn app.main:app --reload

Depois acesse http://localhost:8000/docs para testar pela interface Swagger.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.knowledge_base import base_conhecimento
from app.llm import gerar_resposta, LINK_AGENDAMENTO
from app import leads_store
import os

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

    try:
        resposta = gerar_resposta(req.pergunta, contexto, historico_dict)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao consultar o modelo de IA: {e}")

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
        leads_store.salvar_lead(req.session_id, historico_completo, resposta, LINK_AGENDAMENTO)

    return RespostaResponse(resposta=resposta, fontes_utilizadas=fontes)


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
