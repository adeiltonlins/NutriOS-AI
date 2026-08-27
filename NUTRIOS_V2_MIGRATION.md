# NutriOS V2 — Plano de migração da interface

Objetivo: adotar a experiência visual e os módulos do protótipo `nutrios-ai.zip` sem substituir o backend FastAPI/Supabase existente.

## Regra principal

A migração é de interface, não de dados. Rotas, autenticação, `client_id`, `patient_id`, sessões, Supabase, Gemini, Mercado Pago, Google Calendar, SMTP, PDFs, Storage e regras de negócio existentes continuam como fonte da verdade.

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
| SupplementsPrescriptionView | prescrição clínica / documentos e extensões clínicas |
| WorkoutPrescriptionView | `/app/treinos` + `workout_plans` / `workout_logs` |
| ShoppingListView | derivada do plano alimentar; persistência a conectar quando aplicável |
| AnalyticsView | `/app/metricas` + métricas clínicas/comerciais reais |
| FinancialView | `/app/financeiro` + transações/pagamentos existentes |
| ClinicalNotesView | prontuário / SOAP / notas clínicas |
| LabResultsView | exames e documentos clínicos |
| PdfExportView | ReportLab e rotas de documentos/PDF existentes |
| PublicProfileView | página pública por nutricionista + assistente |
| AdminView | `/admin` e APIs mestre reais |
| AIChatDrawer | Gemini via backend; nunca chave/modelo exposto no browser |

## Garantias de compatibilidade

1. Não colocar `SUPABASE_KEY`, `GEMINI_API_KEY`, `MP_ACCESS_TOKEN` ou qualquer segredo no frontend.
2. Não mover autenticação para o React; cookies HttpOnly e RBAC continuam no FastAPI.
3. Não substituir IDs de elementos consumidos pelo JavaScript atual até o adaptador equivalente estar pronto.
4. Toda consulta de profissional deve continuar filtrada por `client_id`; toda consulta de paciente por `patient_id`.
5. Pagamentos continuam validados no backend e via webhook; a interface apenas apresenta estado e inicia fluxos autorizados.
6. Google Calendar permanece server-side/OAuth atual.
7. PDFs continuam gerados pelo backend para preservar dados reais, idioma e autorização.
8. Recursos novos do protótipo devem primeiro usar dados reais existentes; mocks não entram em produção.

## Fases

### Fase 1 — Shell e dashboard
- Nova identidade visual clínica.
- Sidebar, topbar, cards, prioridades e IA contextual.
- Manter `/api/me` e `/app/api/dashboard-clinico`.

### Fase 2 — Paciente e clínica
- Pacientes, prontuário, anamnese, fotos, exames, diário e evolução.
- Preservar códigos de acesso, documentos e isolamento multi-tenant.

### Fase 3 — Prescrição
- Planejamento alimentar, alimentos, suplementos, treinos, lista de compras e PDF.

### Fase 4 — Gestão
- Agenda, financeiro, analytics, perfil público e conversas.

### Fase 5 — Admin Master
- Contas, planos, consumo, IA, pagamentos, auditoria e testes.

## Estado atual da branch

Branch: `nutrios-v2-ui-integration`

Já adicionado:
- `app/static/nutrios-v2-shell.css`
- carregamento seguro da camada V2 em `nutrios-dashboard-bootstrap-fix.js`
- preservação explícita dos endpoints e fallbacks atuais do dashboard

A branch não altera a `main` nem deve substituir produção antes da validação funcional das telas migradas.
