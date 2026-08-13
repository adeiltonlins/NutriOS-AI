# NutriOS Premium v3 — UX clínico e produto

## O que mudou
- Financeiro do prontuário ganhou resumo de valores a receber, recebidos, despesas e saldo realizado.
- Histórico financeiro agora diferencia visualmente receita prevista, pagamento recebido e despesa.
- Agenda do paciente ganhou leitura visual de data, horário e status.
- Análise Corporal Visual recebeu histórico e indicadores com hierarquia de relatório clínico.
- Portal do paciente ganhou uma home de acompanhamento; NutriOS Intelligence agora aparece como um módulo, não como o produto principal.
- Admin Mestre ganhou refinamentos de produto e comunicação operacional.
- Central de recursos e módulos clínicos receberam nomenclatura e acabamento coerentes com o ecossistema NutriOS.
- Novo design layer `nutrios-premium-v3.css`, preservando rotas e APIs existentes.
- Adicionado `scripts/check_dependencies.py` para validar as dependências essenciais do ambiente.

## Validação executada
- JavaScript inline: válido.
- `clinical-suite.js`: sintaxe válida.
- `patient-clinical.js`: sintaxe válida.
- Python `app/`: compilação sem erros de sintaxe.
- A suíte pytest não pôde ser concluída neste ambiente porque `slowapi` não está instalado e o ambiente não possui acesso de rede para baixá-lo. O projeto já declara `slowapi==0.1.9` e `google-genai==1.2.0` em `requirements.txt`.
