# NutriBot AI — arquitetura SaaS incremental

O projeto mantém chat/RAG, Gemini, Supabase, leads, Mercado Pago e o painel legado. A camada SaaS acrescenta usuários `admin`/`client`, códigos temporários de uso único, sessões opacas em cookie HttpOnly e isolamento de leads por `client_id`.

## Estrutura

```text
app/
  main.py          FastAPI, rotas públicas, SaaS e painel legado
  auth.py          códigos, hashes, cookies, sessões e RBAC
  saas_store.py    acesso às tabelas SaaS no Supabase
  leads_store.py   leads existentes + filtro opcional por cliente
  llm.py           Gemini no backend + prompt opcional por cliente
  pagamento.py     Mercado Pago existente
  knowledge_base.py
  static/index.html
  static/login.html
  static/app.html
data/
migrations/001_saas_auth.sql
scripts/create_admin.py
tests/test_auth_unit.py
```

## Migração segura do Supabase

1. Faça backup do banco.
2. Execute `migrations/001_saas_auth.sql` no SQL Editor do Supabase.
3. O script usa `create table if not exists` e `add column if not exists`: não apaga leads nem tabelas existentes.
4. Use em `SUPABASE_KEY` uma chave de backend com permissão para as tabelas (preferencialmente a service role). Ela nunca deve ir ao navegador.

Novas tabelas: `saas_users`, `access_codes`, `user_sessions`. A tabela `leads` recebe a coluna nullable `client_id`, preservando registros antigos.

## Ambiente local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# preencha GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY, MP_ACCESS_TOKEN etc.
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload
```

Gere `SESSION_SECRET` com pelo menos 32 caracteres, por exemplo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Em HTTP local, use `COOKIE_SECURE=false`. No Render/HTTPS, mantenha `true`.

## Primeiro ADMIN

Depois da migração e das variáveis configuradas:

```bash
PYTHONPATH=. python scripts/create_admin.py --name "Adeilton" --identifier "admin@seudominio.com" --hours 24
```

O comando mostra um código uma única vez. Abra `/login`, use o código e entre em `/admin`. O código é salvo apenas como HMAC/hash e fica marcado como usado após o login.

## Primeiro CLIENTE e código

Com a sessão ADMIN:

```bash
curl -X POST http://localhost:8000/admin/clientes \
  -H 'Content-Type: application/json' \
  --cookie 'nutribot_session=COOKIE_DA_SESSAO' \
  -d '{"name":"Dra. Maria","identifier":"maria@clinica.com","plan":"pro"}'

curl -X POST http://localhost:8000/admin/clientes/UUID_DO_CLIENTE/codigos \
  -H 'Content-Type: application/json' \
  --cookie 'nutribot_session=COOKIE_DA_SESSAO' \
  -d '{"hours":720}'
```

Valores comuns: `24` horas, `168` horas (7 dias), `720` horas (30 dias). Para uma data exata, envie `{"expires_at":"2026-09-10T23:59:00-03:00"}`. Só a resposta de criação contém o código em texto puro.

O cliente entra em `/login`. Após autenticar, recebe cookie HttpOnly/Secure e é direcionado a `/app`. Logout: `POST /auth/logout`.

## Revogar, bloquear e desbloquear

- Revogar códigos e todas as sessões: `POST /admin/clientes/{id}/revogar`.
- Bloquear: `PATCH /admin/clientes/{id}` com `{"active":false}`; todas as sessões são invalidadas.
- Desbloquear: a mesma rota com `{"active":true}`; depois gere um código novo.
- Configuração da IA: `PATCH /admin/clientes/{id}` com `{"ai_config":{"nome":"Dra. Maria","especialidade":"...","prompt":"..."}}`.

## Rotas e compatibilidade

- Públicas: `/`, `/chat`, pagamento e webhook continuam existentes.
- Autenticação: `/login`, `/auth/login`, `/auth/logout`, `/api/me`.
- Cliente: `/app`, `/app/leads`, `/app/configuracoes`.
- ADMIN: `/admin`, `/admin/clientes`, geração/revogação.
- Legado: `/painel` e subrotas aceitam sessão ADMIN nova ou `ADMIN_TOKEN` durante a migração.

O frontend pode enviar `client_id` no `/chat`. O backend valida que corresponde a um cliente ativo e aplica o `ai_config`; o lead é gravado com esse `client_id`. A `GEMINI_API_KEY`, chave do Supabase e token do Mercado Pago ficam apenas no backend.

## Testes

```bash
PYTHONPATH=. pytest -q
```

Checklist manual: login ADMIN; criar cliente; gerar/revogar código; bloquear/desbloquear; login CLIENTE; consultar `/api/me`; abrir `/app/leads`; confirmar 403 do cliente em `/admin`; testar código usado/expirado/revogado; logout; testar chat, TACO/RAG, criação/consulta de pagamento, webhook e painel legado.

## Render

- Aplique a migração antes do deploy.
- Configure todas as variáveis do `.env.example` no painel do Render.
- Use `COOKIE_SECURE=true`, HTTPS e `ALLOWED_ORIGINS` com os domínios reais.
- Não exponha `SUPABASE_KEY`, `GEMINI_API_KEY`, `SESSION_SECRET`, `ADMIN_TOKEN` ou `MP_ACCESS_TOKEN` como variáveis de frontend.
- Com múltiplas instâncias, sessões e códigos continuam consistentes porque o estado está no Supabase. O rate limit atual do `slowapi` é por processo; para escala horizontal, migre o contador para Redis.
- `ADMIN_TOKEN` é compatibilidade temporária. Remova-o somente depois de confirmar que ninguém depende dos links antigos do painel.
