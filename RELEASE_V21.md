# NutriBot AI v21 — Future UX

## Melhorias visuais

- identidade metálica/futurista compartilhada pelo admin mestre e painel profissional;
- painéis em vidro, gradientes discretos, foco acessível e melhor responsividade;
- animações suaves de entrada, ripple nos botões e skeleton durante carregamentos;
- explicações automáticas ao passar o mouse ou navegar pelo teclado nos principais botões;
- feedback de erro, progresso e conexão sem expor detalhes técnicos.

## Nova central de saúde

O admin mestre agora visualiza se IA, Supabase, Mercado Pago e notificações por e-mail estão configurados. A verificação retorna somente estados booleanos e nunca envia chaves ou tokens ao navegador.

## Chat protegido contra regressões

- resposta comum validada;
- intenção de consulta funciona sem depender da interpretação do Gemini;
- falha transitória do provedor retorna uma mensagem amigável;
- os testes não consomem a chave real nem gravam leads.

## Implantação

Suba todo o conteúdo desta pasta para a raiz do repositório GitHub conectado ao Render. Esta versão não exige nova migration nem novas variáveis de ambiente.
