# Nutri Chatbot — MVP com RAG

Protótipo de chatbot nutricional que usa RAG (Retrieval-Augmented Generation)
para ancorar as respostas em dados nutricionais confiáveis (amostra da tabela
TACO) e diretrizes de saúde, em vez de depender só do conhecimento geral do
modelo de IA.

## Como funciona

1. O usuário faz uma pergunta em `/chat`.
2. `app/knowledge_base.py` busca, por similaridade de texto (TF-IDF), os
   alimentos e diretrizes mais relevantes na base local (`data/`).
3. `app/llm.py` manda a pergunta + esse contexto para a API do Google Gemini
   (tem tier gratuito, sem cartão de crédito), com um system prompt que
   **obriga o modelo a responder com base no contexto** e a nunca prescrever
   dieta fechada — só orientar e educar.
4. A API retorna a resposta e as fontes usadas (transparência).

Esse desenho evita alucinação (o bot não inventa valores nutricionais) e dá
controle sobre o que o bot pode/não pode afirmar — importante numa área
sensível como saúde.

## Estrutura

```
nutri-chatbot/
├── app/
│   ├── main.py            # API FastAPI (endpoints /health e /chat)
│   ├── knowledge_base.py  # Retrieval (RAG) sobre os dados locais
│   └── llm.py              # Integração com a API da Anthropic
├── data/
│   ├── alimentos_taco.json # ~20 alimentos de exemplo (formato TACO)
│   └── diretrizes.json     # ~7 diretrizes gerais de nutrição
├── requirements.txt
└── .env.example
```

## Como rodar localmente

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edite o .env e coloque sua GEMINI_API_KEY (crie uma grátis em https://aistudio.google.com/apikey)

export $(cat .env | xargs)
uvicorn app.main:app --reload
```

Acesse `http://localhost:8000/docs` para testar pela interface Swagger, ou:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"pergunta": "Quantas calorias tem uma banana?"}'
```

## Próximos passos sugeridos (pós-MVP)

- **Expandir a base**: sair de ~20 para 200-300 alimentos (dá pra baixar a
  tabela TACO completa em CSV e converter pro mesmo formato JSON).
- **Trocar TF-IDF por embeddings** se a base crescer muito ou a busca por
  palavra-chave começar a falhar em perguntas mais abstratas — usar
  `pgvector` (se já tiver Postgres) ou Pinecone/Weaviate como serviço gerenciado.
- **Guardrails extras**: um segundo prompt/classificador que detecta se a
  pergunta pede prescrição individual (ex: "monta uma dieta pra mim") e
  responde com uma mensagem padrão orientando buscar um nutricionista, antes
  mesmo de chamar o LLM principal.
- **Canal de entrega**: embutir esse backend num widget web (React) ou
  conectar a um número de WhatsApp via API oficial/Twilio.
- **Camada de negócio**: autenticação de usuários, limite de mensagens por
  plano (free x pago) e integração com Stripe para assinatura.
- **Revisão humana**: ter um nutricionista revisando o conteúdo de
  `data/diretrizes.json` antes de ir pra produção — também vira diferencial
  de marketing ("conteúdo revisado por nutricionista").

## Aviso legal

Este chatbot é uma ferramenta educativa e não substitui o acompanhamento de
um nutricionista ou médico. O `SYSTEM_PROMPT` em `app/llm.py` já instrui o
modelo a não prescrever dietas fechadas e a recomendar acompanhamento
profissional em casos que exigem avaliação individual.

## Sobre o tier gratuito do Gemini

O plano gratuito do Gemini não pede cartão de crédito e não expira, mas tem
dois pontos de atenção: (1) há um limite diário de requisições (gira em
torno de 1.500/dia no modelo Flash, que é o usado aqui — mais que suficiente
pra testar e validar o MVP); (2) o Google pode usar as perguntas e respostas
do tier gratuito pra melhorar os modelos deles, então evite mandar dados
sensíveis de usuários reais enquanto estiver nesse plano. Se o projeto virar
produto de verdade, vale considerar o tier pago (ou a Vertex AI, que não usa
os dados pra treinamento).
