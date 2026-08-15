# Regras de desenvolvimento do NutriBot

Este projeto deve evoluir incrementalmente, preservando os fluxos existentes e sem reescritas amplas por conveniência.

Antes de qualquer mudança funcional:

1. analisar a estrutura e localizar os arquivos responsáveis;
2. avaliar impactos em frontend, backend, banco, autenticação e integrações;
3. propor a menor alteração suficiente;
4. preservar compatibilidade e dados existentes;
5. testar o fluxo alterado e possíveis regressões;
6. registrar arquivos modificados, forma de teste, riscos e pendências.

## Segurança e perfis

- Manter ADMIN, NUTRICIONISTA (`client` no código) e PACIENTE segregados.
- Validar autorização no backend e aplicar isolamento por `client_id`/`patient_id`.
- Usar sessões seguras, hashing de senha, RBAC, rate limiting e variáveis de ambiente.
- Nunca expor chaves, tokens ou dados clínicos no frontend ou em logs.
- Tratar dados de saúde conforme princípios de LGPD: minimização, consentimento, rastreabilidade, segregação e exclusão/anonimização segura.

## Banco e deploy

- Usar migrações incrementais e reversíveis; nunca apagar dados sem alerta e autorização.
- Inspecionar o estado existente antes de alterar schema, configuração ou produção.
- Nunca versionar `.env` ou segredos e nunca fazer force push sem autorização.
- Antes do deploy, verificar variáveis, migrações, testes, rotas críticas e serviços externos.

## Produto e interface

- Preservar identidade visual e corrigir causas reais, não apenas sintomas visuais.
- Usar dados reais em dashboards e garantir ações funcionais para check-ins, agenda e financeiro.
- Manter o portal do paciente separado da área profissional.
- Tratar IA como apoio sujeito à revisão profissional.
- Não apresentar análise corporal visual como escaneamento 3D.
- Manter o módulo de treino opcional e isolado do fluxo principal.

O mapa técnico inicial e as prioridades de manutenção estão em `TECHNICAL-MAP.md`.
