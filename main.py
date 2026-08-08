"""
API do chatbot nutricional — MVP com RAG (retrieval por TF-IDF) + Anthropic API.

Rodar localmente:
export ANTHROPIC_API_KEY=sua_chave_aqui
uvicorn app.main:app --reload

Depois acesse http://localhost:8000/docs para testar pela interface Swagger.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.knowledge_base import base_conhecimento
from app.llm import gerar_resposta

BASE_DIR = Path(__file__).resolve().parent
if (BASE_DIR / "static").exists():
STATIC_DIR = BASE_DIR / "static"
else:
STATIC_DIR = BASE_DIR.parent / "static"

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

# Servir arquivos estáticos (CSS, JS, imagens)
if STATIC_DIR.exists():
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def servir_interface():
"""Serve a interface de chat (HTML) na URL raiz do site."""
index_path = STATIC_DIR / "index.html"
if not index_path.exists():
raise HTTPException(status_code=404, detail=f"Arquivo index.html não encontrado em {STATIC_DIR}")
return FileResponse(index_path)


class PerguntaRequest(BaseModel):
pergunta: str = Field(..., min_length=1, max_length=1000, description="Pergunta do usuário")


class RespostaResponse(BaseModel):
resposta: str
fontes_utilizadas: list[str]


@app.get("/health")
def health_check():
return {"status": "ok", "alimentos_carregados": len(base_conhecimento.alimentos)}


@app.post("/chat", response_model=RespostaResponse)
def chat(req: PerguntaRequest):
if not req.pergunta.strip():
raise HTTPException(status_code=400, detail="Pergunta vazia.")

resultados = base_conhecimento.buscar_contexto(req.pergunta, top_k=5)
contexto = base_conhecimento.formatar_contexto_para_prompt(resultados)

try:
resposta = gerar_resposta(req.pergunta, contexto)
except Exception as e:
raise HTTPException(status_code=502, detail=f"Erro ao consultar o modelo de IA: {e}")

fontes = []
for r in resultados:
if r["tipo"] == "alimento":
fontes.append(r["dado"]["nome"])
else:
fontes.append(r["dado"]["titulo"])

return RespostaResponse(resposta=resposta, fontes_utilizadas=fontes)
