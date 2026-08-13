# NutriBot AI v25 — expansão clínica

Esta versão adiciona, sempre isolado por `client_id`: alimentos próprios/TBCA/fabricantes e equivalências; biblioteca de prescrições; Google Agenda opcional; questionários clínicos; acompanhamento materno-infantil; diário com fotos privadas; periodização de planos; financeiro avançado; e fotos comparativas de evolução.

## Atualização

1. Envie todos os arquivos ao GitHub e aguarde o deploy do Render.
2. No Supabase, abra **SQL Editor**, cole `migrations/017_clinical_growth_modules.sql` e execute uma única vez.
3. Abra `/app/gestao-avancada` para alimentos, equivalências, finanças, modelos e agenda.
4. Abra um paciente e clique em **Módulos avançados**.

## Google Agenda (opcional)

Cadastre no Render somente quando desejar ativar: `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET` e `CALENDAR_TOKEN_SECRET`. No Google Cloud, autorize `https://SEU-DOMINIO/app/api/google/callback` como redirect URI. Sem essas variáveis, todo o restante continua funcionando.

## Segurança

Fotos e documentos ficam privados; profissionais acessam somente seu `client_id`; pacientes respondem somente os próprios questionários; tokens do Google são criptografados e nunca chegam ao JavaScript.
