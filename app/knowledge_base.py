"""
Camada de RAG (retrieval) do chatbot nutricional.

MVP: TF-IDF + similaridade de cosseno implementados em Python puro (sem
scikit-learn), pra evitar problemas de compilação em ambientes Windows com
versões novas do Python que ainda não têm pacotes pré-compilados disponíveis.
Se a base crescer muito, dá pra trocar por embeddings + banco vetorial sem
mudar a interface pública (buscar_contexto).
"""
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)


def _tokenizar(texto: str) -> List[str]:
    return TOKEN_RE.findall(texto.lower())


def _texto_alimento(a: Dict[str, Any]) -> str:
    """Concatena os campos relevantes de um alimento em um texto pesquisável."""
    tags = " ".join(a.get("tags", []))
    return (
        f"{a['nome']} {a['categoria']} {tags} "
        f"{a['kcal']} kcal {a['proteina_g']}g proteina "
        f"{a['carboidrato_g']}g carboidrato {a['lipideos_g']}g gordura "
        f"{a['fibra_g']}g fibra {a['sodio_mg']}mg sodio"
    )


def _texto_diretriz(d: Dict[str, Any]) -> str:
    tags = " ".join(d.get("tags", []))
    return f"{d['titulo']} {d['conteudo']} {tags}"


class BaseConhecimento:
    """Carrega os dados e monta o índice TF-IDF (Python puro) uma única vez."""

    def __init__(self, data_dir: Path = DATA_DIR):
        with open(data_dir / "alimentos_taco.json", encoding="utf-8") as f:
            self.alimentos: List[Dict[str, Any]] = json.load(f)
        with open(data_dir / "diretrizes.json", encoding="utf-8") as f:
            self.diretrizes: List[Dict[str, Any]] = json.load(f)

        self.documentos: List[Dict[str, Any]] = (
            [{"tipo": "alimento", "dado": a, "texto": _texto_alimento(a)} for a in self.alimentos]
            + [{"tipo": "diretriz", "dado": d, "texto": _texto_diretriz(d)} for d in self.diretrizes]
        )

        self._construir_indice()

    def _construir_indice(self) -> None:
        tokens_por_doc: List[List[str]] = [_tokenizar(doc["texto"]) for doc in self.documentos]
        n_docs = len(tokens_por_doc)

        df: Counter = Counter()
        for tokens in tokens_por_doc:
            for termo in set(tokens):
                df[termo] += 1

        # IDF suavizado (evita divisão por zero e termos únicos dominarem demais)
        self._idf: Dict[str, float] = {
            termo: math.log((1 + n_docs) / (1 + freq)) + 1.0 for termo, freq in df.items()
        }

        self._vetores_doc: List[Dict[str, float]] = [
            self._vetorizar(tokens) for tokens in tokens_por_doc
        ]

    def _vetorizar(self, tokens: List[str]) -> Dict[str, float]:
        tf_counter = Counter(tokens)
        vetor = {termo: freq * self._idf.get(termo, 0.0) for termo, freq in tf_counter.items()}
        norma = math.sqrt(sum(peso ** 2 for peso in vetor.values())) or 1.0
        return {termo: peso / norma for termo, peso in vetor.items()}

    @staticmethod
    def _similaridade_cosseno(v1: Dict[str, float], v2: Dict[str, float]) -> float:
        menor, maior = (v1, v2) if len(v1) < len(v2) else (v2, v1)
        return sum(peso * maior.get(termo, 0.0) for termo, peso in menor.items())

    def buscar_contexto(self, pergunta: str, top_k: int = 5, limiar: float = 0.05) -> List[Dict[str, Any]]:
        """
        Retorna os documentos mais relevantes para a pergunta do usuário.
        `limiar` filtra resultados com similaridade muito baixa (ruído).
        """
        vetor_pergunta = self._vetorizar(_tokenizar(pergunta))

        pontuados = [
            (self._similaridade_cosseno(vetor_pergunta, vetor_doc), i)
            for i, vetor_doc in enumerate(self._vetores_doc)
        ]
        pontuados.sort(key=lambda par: par[0], reverse=True)

        resultados = []
        for score, i in pontuados[:top_k]:
            if score < limiar:
                continue
            doc = self.documentos[i]
            resultados.append({"score": float(score), "tipo": doc["tipo"], "dado": doc["dado"]})
        return resultados

    def formatar_contexto_para_prompt(self, resultados: List[Dict[str, Any]]) -> str:
        """Transforma os resultados da busca em texto estruturado pro prompt do LLM."""
        if not resultados:
            return "Nenhuma informação relevante encontrada na base de dados local."

        blocos = []
        for r in resultados:
            if r["tipo"] == "alimento":
                a = r["dado"]
                blocos.append(
                    f"[ALIMENTO] {a['nome']} (porção {a['porcao_g']}g) — "
                    f"{a['kcal']} kcal, proteína {a['proteina_g']}g, "
                    f"carboidrato {a['carboidrato_g']}g, gordura {a['lipideos_g']}g, "
                    f"fibra {a['fibra_g']}g, sódio {a['sodio_mg']}mg. "
                    f"Categoria: {a['categoria']}."
                )
            else:
                d = r["dado"]
                blocos.append(f"[DIRETRIZ: {d['titulo']}] {d['conteudo']}")
        return "\n".join(blocos)


# Instância única carregada na subida da aplicação
base_conhecimento = BaseConhecimento()
