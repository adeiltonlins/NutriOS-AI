# NutriBot AI v24 — Central clínica avançada

## Entrega

1. Gráficos de evolução antropométrica.
2. Construtor avançado de plano alimentar com refeições, horários, TACO, substituições, modelos e duplicação.
3. Cálculo energético e metas de macronutrientes.
4. Anamnese completa com consentimento LGPD versionado.
5. Dashboard clínico com alertas, prioridades, agenda e visão da carteira.
6. PDFs profissionais de plano, assinatura/CRN e comparação de versões.
7. Monitor clínico global exclusivo do ADMIN mestre.

## Atualização UX do prontuário

- Cabeçalho completo do paciente, indicadores clínicos e navegação fixa.
- Formulários agrupados por contexto e responsivos em computador, tablet e celular.
- Estados de carregamento, confirmação e erro nas ações principais.
- Busca TACO validada, plano alimentar com feedback e documentos com limite visível.
- Categoria de documento `prescription` preservada corretamente no backend.

## Banco

Execute `migrations/016_advanced_clinical_features.sql` no SQL Editor do Supabase depois da migração 015. O script usa `if not exists`, não apaga registros e mantém compatibilidade com pacientes e planos anteriores.

## Validação

- Python compilado sem erro.
- JavaScript validado com `node --check`.
- 26 testes automatizados aprovados.
- PDF renderizado e inspecionado visualmente com acentuação, tabelas, assinatura e margens corretas.

## Atualização UX do ADMIN mestre

- Central de comando redesenhada para computador, tablet e celular.
- Resumo executivo com receita recorrente, nutricionistas, conversas, pacientes, alertas clínicos, uso do chatbot e vendas.
- Navegação organizada entre gestão, monitor clínico, laboratório, conversas e chatbot público.
- Busca instantânea de nutricionistas, avatares, status legíveis e indicador de capacidade por plano.
- Ações administrativas agrupadas sem remover geração de código, mensalidade, limites, senha, renovação, bloqueio, arquivamento e exclusão.
- Feedback visual moderno nas operações e painel de pagamentos preservado.

## Correção final — clínica e receitas

- Monitor clínico global e dashboard do nutricionista reconstruídos com a mesma identidade visual premium do produto.
- Layout fluido e responsivo, sem recortes horizontais, fontes serifadas acidentais ou botões cinza sem hierarquia.
- Prontuário, avaliação antropométrica e plano alimentar ajustados para respeitar a largura disponível.
- Status técnicos traduzidos: rascunho, publicado, pago, pendente, agendada e prioridades clínicas.
- Receita recorrente SaaS separada da receita gerada pelos chatbots.
- Uma mensalidade entra na Receita recorrente SaaS somente quando o nutricionista está ativo, possui valor mensal e está marcado como Em dia.
- Pagamentos feitos por pacientes continuam contabilizados separadamente em Receita dos chatbots.
