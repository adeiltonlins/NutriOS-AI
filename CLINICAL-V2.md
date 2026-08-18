# NutriOS-AI — fluxo clínico V2

A evolução do produto passa a tratar o atendimento como um fluxo único:

1. **Agendamento** — consulta presencial ou online.
2. **Pré-consulta automática** — ao criar/confirmar uma consulta, o paciente recebe um formulário contextualizado.
3. **Resumo pré-consulta** — respostas são organizadas para o nutricionista antes do atendimento.
4. **Consulta online** — a consulta possui uma sala/link próprio e pode ser iniciada pelo painel.
5. **Registro clínico** — notas estruturadas ficam vinculadas à consulta e ao paciente.
6. **Plano alimentar com IA** — a IA usa o contexto autorizado da consulta para sugerir uma primeira versão; o nutricionista revisa e aprova antes da publicação.
7. **Acompanhamento** — plano, diário, check-ins e evolução continuam no portal do paciente.

## Princípios

- isolamento obrigatório por `client_id`/nutricionista;
- paciente só acessa os próprios dados;
- IA atua como assistente, não como substituta da decisão profissional;
- plano alimentar continua em rascunho até aprovação explícita;
- consulta online é opcional por atendimento;
- identidade white-label/PWA permanece independente por nutricionista.

## Estado atual reaproveitado

O NutriOS-AI já possui agenda, Google Calendar, questionários, prontuário, portal do paciente e construtor de planos. Esta versão adiciona a camada que conecta esses recursos em um fluxo de consulta único.

## Próxima camada de implementação

- endpoints para criar/enviar/responder/revisar pré-consulta;
- geração de resumo pré-consulta;
- criação de sala online por consulta;
- tela de consulta no painel profissional;
- tela pré-consulta no portal do paciente;
- assistente de IA para rascunho do plano alimentar;
- integração visual no dashboard premium/mobile.
