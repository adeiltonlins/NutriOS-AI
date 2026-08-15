# Mapa técnico do NutriBot

Data da análise: 2026-08-15.

## Resumo executivo

O NutriBot é um SaaS multi-tenant de nutrição implementado como um monólito FastAPI. O backend também entrega o frontend estático. O Supabase é acessado pelo servidor via REST e Storage; Gemini fornece IA; Mercado Pago atende pagamentos; SMTP e Google Calendar são integrações opcionais.

O projeto está executável em Python 3.12 e a suíte atual passa com 52 testes. A arquitetura é aproveitável, mas há concentração excessiva em `app/main.py`, acúmulo de assets versionados, migrações com numeração duplicada e arquivos divergentes na raiz que podem causar deploy da versão errada.

## Stack

- Runtime: Python 3.12.7.
- API e servidor: FastAPI 0.115.0 + Uvicorn 0.30.6.
- Modelos e validação: Pydantic 2.9.2.
- Banco e arquivos: Supabase REST/Storage acessado com `requests`.
- Autenticação: sessões opacas em cookies HttpOnly, HMAC-SHA256 e Argon2.
- IA: Google Gemini por `google-genai`.
- Pagamentos: Mercado Pago por API HTTP.
- PDF: ReportLab.
- Rate limiting: SlowAPI.
- Frontend: HTML, CSS e JavaScript sem framework ou pipeline de build.
- Testes: Pytest e HTTPX.

## Estrutura principal

- `app/main.py`: aplicação FastAPI, modelos, páginas, APIs e regras de negócio principais. Possui cerca de 174 KB e 154 rotas.
- `app/clinical_extensions.py`: recursos clínicos avançados e Google Calendar. Possui 29 rotas.
- `app/auth.py`: autenticação de ADMIN/NUTRICIONISTA, códigos, sessões e RBAC.
- `app/patient_auth.py`: autenticação e sessões de PACIENTE.
- `app/saas_store.py`: cliente genérico do Supabase REST e Storage.
- `app/business_store.py`: CRUD multi-tenant com filtro por `client_id`.
- `app/leads_store.py`: persistência de leads e conversas.
- `app/llm.py`: Gemini, prompts e respostas do chatbot.
- `app/pagamento.py`: preferências e validação relacionada ao Mercado Pago.
- `app/knowledge_base.py` + `data/`: base TACO/diretrizes para recuperação de conhecimento.
- `app/emailer.py`: SMTP opcional.
- `app/static/`: todas as páginas e assets do frontend.
- `migrations/`: evolução incremental do schema Supabase.
- `tests/`: testes de autenticação, isolamento, fluxos clínicos, pagamentos, métricas e resiliência.
- `scripts/`: criação do ADMIN e verificações locais.

## Perfis e autenticação

### ADMIN

- Registro em `saas_users` com `role=admin`.
- Entrada pelo `ADMIN_TOKEN` e `ADMIN_IDENTIFIER`.
- Sessão no cookie `nutribot_session`.
- Rotas `/admin` protegidas por `auth.require_admin`.

### NUTRICIONISTA

- Representado internamente por `role=client`.
- Primeiro acesso por código temporário; depois usa identificador e senha Argon2.
- Sessões armazenadas em `user_sessions`.
- Rotas `/app` usam `auth.current_user`, que restringe esse prefixo ao papel `client`.
- Dados de negócio são associados a `client_id`.

### PACIENTE

- Conta separada em `patient_accounts`.
- Primeiro acesso por código em `patient_access_codes`; depois pode criar identificador e senha.
- Sessões separadas em `patient_sessions`, mas usam o mesmo nome de cookie.
- Rotas `/paciente` usam `patient_auth.current_patient`.

## Grupos de rotas

Há 183 rotas declaradas (154 principais e 29 extensões), agrupadas em:

- públicas: landing page, chatbot, páginas do nutricionista, anamnese e agenda;
- autenticação: `/login`, `/auth/*` e `/api/me`;
- profissional: `/app/*` para pacientes, prontuário, avaliações, planos, agenda, financeiro, CRM, métricas e configurações;
- paciente: `/paciente/*` para documentos, plano, treino, diário, check-ins e chat;
- administrador: `/admin/*` para contas, códigos, pagamentos, auditoria, testes e saúde do sistema;
- pagamento e legado: `/pagamento/*`, `/contato`, `/agendar` e `/painel/*`.

## Banco de dados

O schema é construído por migrações SQL e inclui:

- SaaS: `saas_users`, `access_codes`, `user_sessions`;
- comercial: `leads`, serviços, disponibilidade, agenda e anamneses;
- conformidade: `audit_logs`, `data_requests`;
- pacientes: `patient_accounts`, códigos, sessões, prontuários, check-ins e documentos;
- clínica: avaliações antropométricas, planos alimentares, diário, alertas, lembretes e transações;
- extensões: alimentos personalizados, equivalências, questionários, materno-infantil, fotos e Google Calendar;
- treino opcional: `workout_plans`, `workout_logs`.

As tabelas têm RLS habilitado, mas o backend usa uma chave privilegiada. Portanto, o isolamento efetivo depende também dos filtros de `client_id` e `patient_id` aplicados pelo código.

## Integrações externas

- Supabase: banco e buckets de logos, documentos e fotos.
- Gemini: respostas do chatbot e apoio por IA.
- Mercado Pago: Checkout Pro, consulta de pagamentos e webhook.
- SMTP: notificações por e-mail.
- Google Calendar: OAuth e sincronização opcional.
- Render: indicado pela documentação como ambiente de produção, mas não existe manifesto de deploy versionado.

## Variáveis de ambiente

Principais variáveis encontradas:

- segurança: `ADMIN_TOKEN`, `ADMIN_IDENTIFIER`, `SESSION_SECRET`, `APP_TOKEN_SECRET`, `COOKIE_SECURE`, `COOKIE_SAMESITE`;
- banco: `SUPABASE_URL`, `SUPABASE_KEY`;
- IA: `GEMINI_API_KEY`, `IA_ATIVA`, `FREE_MESSAGE_LIMIT`;
- pagamento: `MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET`, `VALOR_CONSULTA`, `NOME_ITEM_PAGAMENTO`;
- aplicação: `URL_BASE`, `ALLOWED_ORIGINS`, `MAX_BODY_BYTES`;
- rate limiting: `LOGIN_RATE_LIMIT`, `CODE_GENERATION_RATE_LIMIT`;
- SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`;
- calendário: `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET`, `CALENDAR_TOKEN_SECRET`;
- personalização: `NUTRICIONISTA_NOME`, `NUTRICIONISTA_ESPECIALIDADE`, `LINK_AGENDAMENTO`, `CONTATO_NUTRICIONISTA`.

## Controles de segurança existentes

- Cookies HttpOnly, Secure configurável e SameSite.
- Hashes Argon2 para senhas.
- Tokens e códigos armazenados como HMAC/hash, não em texto puro.
- RBAC para ADMIN e restrição do prefixo `/app` ao NUTRICIONISTA.
- Isolamento de registros por `client_id` em helpers de negócio.
- Limitação de login e geração de códigos.
- CORS restrito e validação de origem em operações mutáveis.
- Limites de corpo e regras especiais para PDFs/imagens.
- Cabeçalhos de segurança, HSTS em HTTPS e proteção contra framing.
- Documentos clínicos servidos por backend autenticado.

## Erros e riscos confirmados

### Prioridade alta

1. **Migração duplicada (corrigida no repositório):** `019_visual_body_analysis.sql` foi renomeada para `020_visual_body_analysis.sql`, preservando `019_optional_training_module.sql`. Antes do deploy, ainda é necessário registrar quais migrações já foram aplicadas no Supabase.
2. **Arquivos divergentes na raiz:** `main.py`, páginas HTML e CSS na raiz não são iguais aos equivalentes usados em `app/`. Um upload manual pode publicar arquivos obsoletos no lugar errado. Confirmar os arquivos canônicos e remover/arquivar duplicatas somente após validação.
3. **Webhook não está plenamente integrado:** `pagamento.validar_assinatura_webhook` existe, mas não é chamado pela rota encontrada. Além disso, `MP_WEBHOOK_SECRET` não aparece no `.env.example`. A rota precisa validar assinatura antes de confiar na notificação.

### Prioridade média

4. **Proteção do Git adicionada:** `.gitignore` agora bloqueia `.env`, `.venv`, caches, logs e pacotes ZIP. Ainda é necessário conferir se algum segredo já entrou no histórico remoto.
5. **Dependências inconsistentes:** os testes exibem `RequestsDependencyWarning` porque as versões instaladas de `urllib3`/`chardet` não correspondem à faixa esperada pelo `requests` fixado. Ajustar pins e testar novamente.
6. **Monólito concentrado:** `app/main.py` mistura páginas, modelos, APIs e regras clínicas. Isso eleva risco de regressão. Extrair routers por domínio incrementalmente, com testes antes e depois; não reescrever o sistema.
7. **Uso síncrono de `requests`:** chamadas externas bloqueiam workers FastAPI. Avaliar timeouts, retries e migração gradual para cliente compartilhado/assíncrono onde houver impacto medido.
8. **Acúmulo de CSS/JS versionado:** diversas versões `v3` a `v32` coexistem. É preciso mapear quais assets cada página carrega antes de remover qualquer um.
9. **Deploy não reproduzível:** não há `render.yaml`, Dockerfile ou Procfile. O comando e as configurações ficam fora do repositório, aumentando risco operacional.

### Lacunas de validação

10. Os 52 testes passam, mas não demonstram funcionamento real de Supabase, Gemini, Mercado Pago, SMTP, Storage ou Google Calendar, pois esses serviços exigem credenciais e ambiente de integração.
11. Não há evidência no repositório de lint, análise estática, cobertura, CI ou teste end-to-end de navegador.
12. A service role do Supabase contorna RLS; qualquer endpoint sem filtro de tenant pode causar vazamento horizontal. É necessário auditar todas as consultas por domínio.

## Ordem recomendada de trabalho

1. Conferir se segredos ou caches já existem no histórico remoto; o `.gitignore` agora protege novos commits.
2. Confirmar no Supabase o estado aplicado das migrações `019` e `020`.
3. Confirmar quais arquivos da raiz são obsoletos e definir uma única fonte canônica.
4. Integrar e testar a assinatura do webhook do Mercado Pago.
5. Corrigir os pins de dependência e manter os 52 testes verdes.
6. Criar CI com testes, verificação de dependências e validação de JavaScript.
7. Adicionar testes de integração para autenticação e isolamento multi-tenant.
8. Auditar consultas com service role para garantir `client_id`/`patient_id` em todas as operações.
9. Modularizar `app/main.py` por domínio, em pequenas etapas.
10. Consolidar assets somente depois de mapear uso real em cada página.
11. Versionar a configuração de deploy sem incluir segredos.

## Validação executada

- Aplicação iniciada localmente com HTTP 200.
- `pytest -q`: 52 testes aprovados.
- `scripts/check_dependencies.py`: dependências essenciais disponíveis.
- `scripts/check_inline_js.js`: JavaScript inline válido.
- Avisos atuais: depreciação do import multipart pelo Starlette e incompatibilidade de versões reportada pelo `requests`.

Nenhuma alteração funcional foi feita durante a criação deste mapa.
