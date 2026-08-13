# NutriBot AI — arquitetura SaaS incremental

O projeto mantém chat/RAG, Gemini, Supabase, leads, Mercado Pago e o painel legado. A camada SaaS acrescenta usuários `admin`/`client`, códigos temporários de uso único, sessões opacas em cookie HttpOnly e isolamento de leads por `client_id`.

## Rotas do produto

- `/` — página comercial pública do SaaS, com demonstração guiada sem consumo do Gemini.
- `/login` — primeiro acesso por código e acessos seguintes do nutricionista por e-mail/identificador e senha.
- `/admin` — painel mestre protegido; o administrador entra pelo código mestre na tela `/login`.
- `/admin/testes` — laboratório mestre para validar chatbot, WhatsApp, pagamento e configuração de cada nutricionista sem criar leads de teste.
- `/n/{slug}` — página pública personalizada de cada nutricionista.
- `/paciente/login?nutri={slug}` — entrada do paciente com identidade do nutricionista.
- `/paciente` — canal privado do paciente enquanto seu acompanhamento estiver ativo.

O código do paciente é uma concessão de acesso de uso único. Depois do login, o navegador usa uma sessão HttpOnly. Se a sessão for encerrada ou o paciente trocar de aparelho, o nutricionista deve gerar um novo código; o plano e o prazo do acompanhamento permanecem os mesmos.

No laboratório, comandos como “quero marcar uma consulta” são tratados pelo backend. Assim, o caminho de atendimento continua previsível mesmo quando o provedor de IA estiver temporariamente instável. O modo de teste usa as configurações reais selecionadas, mas não consome o limite público nem grava a conversa como lead.

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

## ADMIN mestre

O ADMIN mestre não usa e-mail/senha e não aparece como nutricionista. Ele entra em `/login`, na aba **Código de acesso**, usando exclusivamente o valor secreto de `ADMIN_TOKEN` configurado no Render. Depois é direcionado para `/admin`. Trocar `ADMIN_TOKEN` no Render invalida o código mestre anterior após o novo deploy.

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
- Arquivar uma conta: `POST /admin/clientes/{id}/arquivar`; bloqueia acesso e preserva histórico.
- Restaurar: `POST /admin/clientes/{id}/restaurar`; a conta volta bloqueada para revisão antes de liberar.
- Contas arquivadas não são excluídas, preservando leads, vendas e métricas históricas.

Antes do deploy desta versão, execute `migrations/010_admin_archive_analytics.sql` e `migrations/011_public_brand_assets.sql` no SQL Editor do Supabase. O painel mestre exibe conversas, vendas, conversão e receita dos últimos seis meses. A migração 011 cria o armazenamento público de fotos/logos; o upload aceita JPG, PNG e WebP de até 1 MB.

## Portal privado de pacientes

Execute também `migrations/012_patient_followup_portal.sql`. No painel do nutricionista, a rota `/app/pacientes` permite cadastrar pacientes, registrar o contexto da dieta, definir validade e limite de mensagens, gerar código individual, renovar, bloquear e arquivar. O paciente entra em `/paciente/login`; a sessão é HttpOnly e deixa de funcionar automaticamente quando o acompanhamento vence. `PATIENT_SESSION_DURATION` controla a duração máxima da sessão, sempre limitada pela validade do plano.

Execute por último `migrations/013_patient_records_checkins_documents.sql`. Ela cria prontuário evolutivo, check-ins semanais, metadados de documentos e o bucket privado `patient-documents`. O nutricionista abre o prontuário pela rota `/app/pacientes/{id}`, registra evolução e envia dietas em PDF de até 10 MB. O paciente visualiza os PDFs e responde ao check-in em `/paciente`. Os arquivos nunca recebem URL pública: todo download passa pelo backend e exige uma sessão autorizada.

Depois execute `migrations/014_plan_limits_safe_removal.sql`. O ADMIN mestre passa a definir o limite de pacientes de cada nutricionista (`-1` = ilimitado); o backend impede novos cadastros quando o teto é atingido. O profissional pode arquivar e ocultar pacientes sem apagar histórico. A exclusão permanente de uma conta profissional fica restrita ao ADMIN mestre, exige novamente o `ADMIN_TOKEN`, a confirmação `EXCLUIR identificador` e também remove leads e PDFs privados vinculados.

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

## Fluxo profissional no GitHub

O repositório agora possui modelos em `.github/ISSUE_TEMPLATE`, checklist de Pull Request e a esteira `.github/workflows/quality.yml`. Para cada melhoria:

1. Crie uma Issue com problema, critérios de aceite e testes.
2. Abra uma branch, por exemplo `feature/skeleton-dashboard`.
3. Faça a alteração e abra uma Pull Request mencionando `Closes #NUMERO`.
4. Aguarde a esteira verificar compilação, testes, JavaScript, dependências e possíveis segredos.
5. Integre na `main` somente quando as verificações estiverem verdes.

Nas configurações do GitHub, proteja a branch `main` e exija o status **Quality Gate** antes do merge. O frontend inclui `nutribot-ux.js` e `nutribot-ux.css` para feedback de conexão, estado de progresso nos formulários, skeleton inicial e respeito à preferência de movimento reduzido.

## Render

- Aplique a migração antes do deploy.
- Configure todas as variáveis do `.env.example` no painel do Render.
- Use `COOKIE_SECURE=true`, HTTPS e `ALLOWED_ORIGINS` com os domínios reais.
- Não exponha `SUPABASE_KEY`, `GEMINI_API_KEY`, `SESSION_SECRET`, `ADMIN_TOKEN` ou `MP_ACCESS_TOKEN` como variáveis de frontend.
- Com múltiplas instâncias, sessões e códigos continuam consistentes porque o estado está no Supabase. O rate limit atual do `slowapi` é por processo; para escala horizontal, migre o contador para Redis.
- `ADMIN_TOKEN` é compatibilidade temporária. Remova-o somente depois de confirmar que ninguém depende dos links antigos do painel.
# Módulos de clínica

Após executar `migrations/007_clinic_management.sql`, cada nutricionista passa a ter CRM visual, serviços/planos, anamnese interna, disponibilidade e agenda. As notificações por e-mail usam `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` e `SMTP_FROM`; sem SMTP, o restante do sistema continua funcionando normalmente.

## Central clínica avançada (v24)

Execute, nessa ordem, `migrations/015_clinical_suite.sql` e `migrations/016_advanced_clinical_features.sql`. A central do paciente passa a incluir:

- gráficos de peso, gordura corporal e massa muscular;
- cálculo de TMB, gasto energético, meta calórica e macronutrientes (Mifflin-St Jeor, sempre sujeito à revisão profissional);
- anamnese clínica e nutricional completa, com registro versionado do consentimento LGPD;
- planos por refeição e horário, alimentos TACO, quantidades, substituições, modelos reutilizáveis, duplicação e publicação;
- PDF de plano alimentar com identidade do nutricionista, assinatura/CRN e acesso privado do paciente;
- diário alimentar, alertas automáticos, prontuário, agenda, financeiro e documentos versionados;
- dashboard clínico do nutricionista em `/app/clinica`;
- monitor operacional global do ADMIN mestre em `/admin/clinica`, sem quebrar o isolamento entre contas.

O ADMIN mestre visualiza contagens globais por nutricionista. Cada nutricionista continua autorizado somente sobre seus próprios pacientes e registros. O cálculo energético e os totais nutricionais são auxiliares e não substituem avaliação clínica.
