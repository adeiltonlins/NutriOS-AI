# NutriBot AI v27 — Portal do paciente

O nutricionista escolhe a validade do convite (24 horas, 7 dias, 30 dias ou personalizada). No primeiro acesso, o paciente cria identificador e senha; depois usa a área **Já tenho senha** em `/paciente/login`.

Antes do deploy, execute `migrations/018_patient_credentials.sql` no SQL Editor do Supabase.

Código, senha e sessão nunca ficam em texto puro; a senha usa Argon2 e a sessão permanece em cookie HttpOnly.
