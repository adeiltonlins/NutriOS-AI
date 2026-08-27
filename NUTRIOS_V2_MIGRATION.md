# NutriOS V2 — Plano de migração da interface

Objetivo: adotar a experiência visual e os módulos do protótipo `nutrios-ai.zip` sem substituir o backend FastAPI/Supabase existente.

## Regra principal

A migração é de interface e evolução incremental de produto, não uma troca cega de dados. Rotas, autenticação, `client_id`, `patient_id`, sessões, Supabase, Gemini, Mercado Pago, Google Calendar, SMTP, PDFs, Storage e regras de negócio existentes continuam como fonte da verdade.

## Componentes do protótipo e destino real

| Protótipo V2 | NutriOS atual / destino |
| --- | --- |
| DashboardView | `/app` + `/app/api/dashboard-clinico` |
| PatientsView | `/app/pacientes` + APIs de pacientes existentes |
| AppointmentsCalendarView | `/app/gestao` + agenda / Google Calendar |
| AnamnesisAndPhotosView | prontuário, avaliações, fotos de evolução e anamnese |
| FoodLogView | diário alimentar do paciente |
| MealPlanningView | `/app/planos` / plano alimentar por paciente |
| FoodDatabaseView | base TACO + alimentos personalizados/equivalências |
| SupplementsPrescriptionView | `patient_supplements` + APIs V2 + portal do paciente |
| WorkoutPrescriptionView | `/app/treinos` + `workout_plans` / `workout_logs` |
| ShoppingListView | derivada do plano alimentar; persistência ainda não criada |
| AnalyticsView | `/app/metricas` + métricas clínicas/comerciais reais |
| FinancialView | `/app/financeiro` + transações/pagamentos existentes |
| ClinicalNotesView | prontuário / notas clínicas |
| LabResultsView | `patient_lab_exams` + APIs V2 no prontuário |
| PdfExportView | ReportLab e rotas de documentos/PDF existentes |
| PublicProfileView | página pública por nutricionista + assistente |
| AdminView | `/admin` e APIs mestre reais |
| AIChatDrawer | Gemini via backend; nunca chave/modelo exposto no browser |

## Garantias de compatibilidade

1. Não colocar `SUPABASE_KEY`, `GEMINI_API_KEY`, `MP_ACCESS_TOKEN` ou qualquer segredo no frontend.
2. Não mover autenticação para o browser; cookies HttpOnly e RBAC continuam no FastAPI.
3. Não substituir IDs de elementos consumidos pelo JavaScript atual até o adaptador equivalente estar pronto.
4. Toda consulta de profissional continua filtrada por `client_id`; toda consulta de paciente por `patient_id`.
5. Pagamentos continuam validados no backend e via webhook; a interface apenas apresenta estado e inicia fluxos autorizados.
6. Google Calendar permanece server-side/OAuth atual.
7. PDFs continuam gerados pelo backend para preservar dados reais, idioma e autorização.
8. Recursos novos do protótipo usam tabelas e APIs reais; mocks não entram em produção.
9. Apenas HTTP 401 redireciona para login. 403 e falhas de rede preservam contexto e apresentam erro tratável.

## Implementação atual da branch

Branch: `nutrios-v2-ui-integration`

### Interface compartilhada
- `app/static/nutrios-v2-shell.css`
- `app/static/nutrios-v2-suite.css`
- `app/static/nutrios-v2-clinical.css`
- `app/static/nutrios-v2-clinical-modules.css`
- `app/static/nutrios-v2-clinical.js`
- carregamento central pelo `nutrios-v24-theme.js`
- integração com `nutrios-app-shell.js`, `nutribot-ux.js` e o bootstrap do dashboard

### Telas já alcançadas pela V2
- Dashboard profissional e camada de prioridades
- Pacientes
- Prontuário
- Anamnese
- Evolução corporal e fotos privadas
- Plano alimentar
- Diário
- Agenda e financeiro dentro do prontuário
- Documentos/PDF
- Treinos e periodização
- Financeiro clínico
- Admin Master e telas que usam o design system compartilhado
- Portal do paciente
- NutriOS Intelligence do paciente

### Recursos novos persistentes
- Exames laboratoriais por paciente (`patient_lab_exams`)
- Suplementação por paciente (`patient_supplements`)
- criação, leitura, atualização e exclusão autenticadas no profissional
- suplementação ativa/pausada disponível no portal do próprio paciente
- classificação automática básica do exame pela faixa numérica informada; não substitui interpretação clínica
- auditoria de criação/exclusão dos novos recursos

### Banco
Antes de ativar Exames/Suplementação em produção, aplicar e registrar:

`migrations/021_clinical_v2_exams_supplements.sql`

A migração cria apenas tabelas novas e índices; não remove nem altera dados clínicos anteriores.

### Testes adicionados
- `tests/test_clinical_v2.py`: registro das rotas V2 e classificação de faixa dos exames.

## Próximas validações antes da produção

1. Executar a suíte Pytest completa no ambiente de deploy.
2. Aplicar a migração 021 no Supabase de homologação/produção conforme o processo utilizado no projeto.
3. Validar visualmente desktop e mobile em Dashboard, Pacientes, Prontuário, Treinos, Financeiro, Admin e Portal do Paciente.
4. Criar um exame e uma suplementação em conta de teste e confirmar isolamento entre dois nutricionistas.
5. Confirmar que o paciente enxerga somente a própria suplementação.
6. Confirmar PDFs, Mercado Pago, Gemini e Google Calendar após a mudança de frontend.
7. Só depois disso promover a branch para `main`.

A branch não altera a `main` e não deve substituir produção antes dessas validações.
