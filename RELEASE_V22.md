# NutriBot AI v22 — Chat real, limites e monitor de conversas

## Vitrine do SaaS

- os quatro atalhos continuam disponíveis depois de cada clique;
- cada atalho e o novo campo livre chamam a IA real;
- o histórico permanece na mesma conversa;
- removido o texto público sobre consumo da API;
- a vitrine respeita limites definidos pelo admin mestre.

## Controle mestre

Em **Admin mestre → Laboratório e limites → Meu chatbot mestre** agora é possível configurar:

- nome e identidade da assistente;
- mensagem inicial e prompt;
- WhatsApp;
- link fixo de pagamento opcional;
- limite de mensagens por pessoa;
- limite de novas pessoas por dia;
- duração máxima de cada conversa;
- chatbot público ligado ou pausado.

Se o link fixo ficar vazio, o chatbot mestre usa a API do Mercado Pago já configurada no Render. O bloqueio de limite acontece no backend antes de chamar o Gemini.

## Experiência do nutricionista

- nova tela **Conversas ao vivo**;
- lista de visitantes, origem, interesse e última atividade;
- indicador “online” quando houve atividade nos últimos cinco minutos;
- histórico completo isolado por nutricionista;
- atualização automática a cada dez segundos.

## Identidade e respostas

- o avatar preserva “NB”, assinatura visual do NutriBot, e cada mensagem exibe o nome configurado da assistente;
- removidas as etiquetas técnicas de alimentos/fontes abaixo das respostas;
- perguntas incompletas ou com erro de escrita são interpretadas com tolerância;
- dúvidas comuns podem receber estimativas educativas com ressalvas, sem inventar diagnóstico ou dieta individual.

## Correções

- corrigida a tela branca do laboratório: a prévia aceita iframe somente da mesma origem;
- sites externos continuam bloqueados;
- falha do Gemini mantém resposta amigável;
- fluxo de consulta não depende da interpretação do modelo.

## Banco e ambiente

Esta versão usa o JSON `ai_config` existente. Não exige migration nem nova variável no Render.
