# Interface AI Studio -> NutriOS real

Esta branch recebe a nova camada visual em React sem substituir o motor do SaaS.

Princípios desta integração:

- FastAPI, Supabase, autenticação, cookies, isolamento por `client_id`, Mercado Pago e Gemini permanecem no backend atual.
- O navegador nunca recebe a `GEMINI_API_KEY`.
- Não há login fake, usuário demo nem persistência clínica em `localStorage`.
- As rotas React só substituem as páginas legadas quando o build `app/static/react-ui/index.html` existe.
- Se o build React não existir, as páginas atuais continuam ativas; isso mantém rollback simples e evita quebrar produção durante a migração.

A fonte React adaptada será adicionada e validada nesta mesma branch antes de qualquer merge em `main`.
