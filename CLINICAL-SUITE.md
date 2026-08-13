# NutriBot AI — suíte clínica

## Ativação

1. No Supabase, abra **SQL Editor**.
2. Execute integralmente `migrations/015_clinical_suite.sql` uma única vez.
3. Envie os demais arquivos ao GitHub e aguarde o deploy automático do Render.
4. Entre como nutricionista, abra **Pacientes** e selecione um paciente.

## Recursos incluídos

- central clínica isolada por nutricionista e paciente;
- evolução antropométrica e IMC calculado no backend;
- construtor de plano alimentar com a base TACO;
- macros e calorias recalculados no backend;
- aprovação obrigatória antes de publicar o plano;
- diário alimentar do paciente com retorno profissional;
- check-ins, prontuário, agenda, lembretes e PDFs privados;
- lançamentos financeiros da clínica;
- exames e relatórios organizados por categoria;
- portal do paciente com plano aprovado e diário alimentar.

## Segurança clínica

O chatbot público continua sem prescrever dietas fechadas. Um plano alimentar criado na central inicia como rascunho e só aparece ao paciente depois de aprovação explícita do nutricionista.

## Fora desta versão

WhatsApp e outros canais pagos não foram adicionados. As integrações atuais de Gemini, Mercado Pago, Supabase, leads e autenticação permanecem compatíveis.
