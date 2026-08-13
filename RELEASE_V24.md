# NutriBot AI v24 — Central clínica avançada

## Entrega

1. Gráficos de evolução antropométrica.
2. Construtor avançado de plano alimentar com refeições, horários, TACO, substituições, modelos e duplicação.
3. Cálculo energético e metas de macronutrientes.
4. Anamnese completa com consentimento LGPD versionado.
5. Dashboard clínico com alertas, prioridades, agenda e visão da carteira.
6. PDFs profissionais de plano, assinatura/CRN e comparação de versões.
7. Monitor clínico global exclusivo do ADMIN mestre.

## Banco

Execute `migrations/016_advanced_clinical_features.sql` no SQL Editor do Supabase depois da migração 015. O script usa `if not exists`, não apaga registros e mantém compatibilidade com pacientes e planos anteriores.

## Validação

- Python compilado sem erro.
- JavaScript validado com `node --check`.
- 26 testes automatizados aprovados.
- PDF renderizado e inspecionado visualmente com acentuação, tabelas, assinatura e margens corretas.
