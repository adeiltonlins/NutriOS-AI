# NutriOS-AI — fundação SaaS

## Objetivo
Transformar o produto em um SaaS multi-tenant comercial, mantendo o branding individual do nutricionista e o PWA personalizado.

## Planos iniciais

| Plano | Mensalidade | Pacientes | IA/mês | Domínio | Equipe |
|---|---:|---:|---:|---|---:|
| Trial | grátis | 10 | 100 | — | 1 |
| Essencial | R$ 79 | 100 | 500 | — | 1 |
| Profissional | R$ 149 | 500 | 2.000 | sim | 3 |
| Premium | R$ 299 | ilimitado | ilimitado | sim | 10 |

Os valores são uma proposta inicial de produto e não representam cobrança ativa.

## Estados da assinatura

`trialing` → `active` → `past_due` → `canceled`

O acesso a recursos pagos deve ser decidido no backend a partir do estado da assinatura, nunca apenas pelo frontend.

## Próximas integrações

1. Adicionar `plan_code`, `subscription_status`, `trial_ends_at`, `current_period_ends_at` e identificadores do gateway ao tenant.
2. Criar middleware/dependency de entitlement para validar limites no backend.
3. Criar onboarding transacional: conta → perfil → branding → slug → primeiro paciente.
4. Integrar gateway de pagamento usando webhooks idempotentes.
5. Criar portal de cobrança e troca de plano.
6. Adicionar testes E2E para isolamento entre dois nutricionistas.
7. Adicionar métricas de onboarding, pacientes ativos, IA e instalação PWA.
8. Só então habilitar cobrança real em produção.

## Regra de segurança
Nenhuma informação de um tenant pode ser retornada usando apenas um identificador fornecido pelo cliente. Consultas clínicas, pacientes, arquivos e métricas devem ser escopadas pelo `user_id`/tenant autenticado no servidor.
