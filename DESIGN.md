# NutriOS — Product Design Direction

## Product thesis
NutriOS is the operating system for a nutrition practice: clinical care, patient follow-up, agenda, finance, commercial pipeline and AI in one professional workspace. The UI must feel trustworthy enough for clinical data and efficient enough for daily operational use.

## Audience and primary job
Primary audience: Brazilian nutrition professionals managing an active patient portfolio.
Primary job: understand what needs attention now and move between clinical and business workflows without losing context.

## Visual character
Premium clinical technology — calm, precise, contemporary and human. Avoid generic AI neon/glass aesthetics, excessive gradients, oversized cards, decorative dashboard chrome and hospital-like sterile blue.

## Canonical palette
- Forest / Brand: #0F5132
- Action Green: #22C55E
- Soft Clinical Green: #D1FAE5
- Canvas: #F8FAFC
- Ink: #111827

Use Forest for brand/navigation authority and Action Green selectively for primary actions and positive states. Soft Clinical Green is an accent surface, not a default page background. Canvas and white surfaces carry most of the interface. Semantic warning/error/info colors remain separate from the brand palette.

## Layout contract
Authenticated professional routes use one persistent App Shell. Desktop: stable left sidebar + restrained top context/action area + one content canvas. Mobile: accessible drawer navigation with the same information architecture. Entering Agenda, Patients, Finance, Conversations, Training or Clinical modules must never feel like leaving NutriOS.

## Navigation
Canonical professional IA:
- Início
- Pacientes
- Agenda
- Atendimentos
- Planos alimentares
- Evolução
- Análise corporal
- Financeiro clínico
- Conversas
- Indicações
- Treinos
- Captação e vendas
- Configurações

One canonical route per capability. Legacy aliases may redirect server-side but must not appear as competing links in the UI.

## Dashboard signature
The memorable element is a clinical priority layer: the dashboard should answer “what needs my attention today?” before showing broad analytics. Patient alerts, today's agenda, missing check-ins and actionable AI insights should visually outrank vanity metrics.

## Components
Prefer shared primitives over page-local variants: Button, IconButton, Field, Select, Search, Card, Metric, Table/List, EmptyState, ErrorState, Skeleton, Toast, Modal/Drawer, Badge/Status, PageHeader and AppShell.

Cards use restrained radius and subtle borders/shadows. Avoid nesting cards inside cards unless the inner boundary has a real interaction or semantic purpose.

## Typography and density
Prioritize scanability for long clinic sessions. Strong but compact page titles; sentence-case labels; tabular alignment for financial/data values; generous whitespace between sections but efficient density inside tables/lists. Avoid oversized marketing typography inside authenticated product screens.

## Interaction contract
- Only HTTP 401 means unauthenticated and may redirect to /login.
- HTTP 403 means authenticated but unauthorized: keep the user in context and explain the restriction.
- Network/5xx failures preserve session and show a retryable ErrorState.
- Loading uses skeleton/progress states; never blank the whole application shell.
- Empty states explain what is empty and provide the next meaningful action.
- Destructive actions require clear intent and confirmation where data loss is meaningful.
- Keyboard focus must remain visible; reduced-motion preferences are respected.

## AI behavior
AI is an assistive clinical layer, not visual decoration. AI surfaces must identify generated suggestions, preserve clinician control and never silently commit clinical changes. Use AI emphasis sparingly so it remains meaningful.

## Responsive behavior
The information hierarchy remains the same on mobile. Do not merely stack every desktop card. Prioritize today/attention/actions, collapse secondary analytics, preserve touch targets and keep primary actions reachable.

## Engineering direction
`nutrios-design-system-v1.css` (or its successor) should become the canonical token/component source. Stop adding numbered CSS patch files. Migrate active routes progressively, verify them, then retire unused legacy styles/pages. Shared behavior belongs in shared JS/CSS rather than copied inline implementations.

## Non-goals
- No redesign that removes existing clinical/business capability.
- No visual novelty at the cost of accessibility or comprehension.
- No fake dashboard data in production UI.
- No route-specific sidebar forks.
