# NutriOS Premium v2 — Release V28

## Posicionamento
- NutriOS passa a ser apresentado como plataforma de gestão nutricional, não como chatbot.
- IA reposicionada como Assistente IA / camada de inteligência da plataforma.
- Nomenclatura comercial revisada em painel profissional, clínica, portal do paciente e administração.

## UX/UI
- Design system premium unificado em `app/static/nutrios-premium.css`.
- Hierarquia visual, espaçamento, cards, tabelas, formulários, diálogos, navegação e estados vazios refinados.
- Dashboard profissional redesenhado visualmente como central operacional.
- Central clínica e prontuário harmonizados com a mesma linguagem visual.
- Portal do paciente recebeu visual mais limpo e clínico, com IA como recurso de apoio.
- Melhorias responsivas para desktop, tablet e celular.

## Compatibilidade
- Rotas internas antigas com `chatbot` foram mantidas quando fazem parte do contrato atual do backend, evitando quebra de integração.
- JavaScript inline validado com `scripts/check_inline_js.js`.
- Python compilado sem erros de sintaxe.

## Qualidade
- A suíte pytest depende das bibliotecas do `requirements.txt`. No ambiente de inspeção atual faltam `slowapi` e o pacote `google-genai`, portanto a coleção completa não pôde ser concluída aqui.
