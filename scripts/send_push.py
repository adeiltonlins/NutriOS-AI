#!/usr/bin/env python3
"""Script administrativo para enviar push (Web Push) do NutriOS.

Uso:
    .venv/Scripts/python scripts/send_push.py --titulo "Olá" --corpo "Lembrete" --url /app
    .venv/Scripts/python scripts/send_push.py --titulo "X" --corpo "Y" --user <client_id>

Requer as variáveis de ambiente VAPID_PUBLIC_KEY e VAPID_PRIVATE_KEY no .env.
Requer também SUPABASE_URL/SUPABASE_KEY para ler as subscriptions.
"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import saas_store  # noqa: E402
from app.push_sender import send_push  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Enviar push para usuários do NutriOS")
    parser.add_argument("--titulo", required=True, help="Título da notificação")
    parser.add_argument("--corpo", required=True, help="Corpo da notificação")
    parser.add_argument("--url", default="/app", help="URL ao clicar (padrão /app)")
    parser.add_argument("--user", default=None, help="ID de um usuário específico (opcional)")
    args = parser.parse_args()

    if not (os.getenv("VAPID_PRIVATE_KEY") and os.getenv("VAPID_PUBLIC_KEY")):
        print("[erro] VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY não configurados no .env")
        sys.exit(1)
    if not saas_store.ATIVO:
        print("[erro] Supabase não configurado (SUPABASE_URL / SUPABASE_KEY)")
        sys.exit(1)

    users = saas_store.list_users()
    alvos = [u for u in users if u.get("active") and u.get("push_subscription")]
    if args.user:
        alvos = [u for u in alvos if u.get("id") == args.user]

    if not alvos:
        print("[aviso] Nenhum usuário com push subscription ativa encontrado.")
        sys.exit(0)

    enviados = 0
    falhas = 0
    for u in alvos:
        nome = u.get("name") or u.get("identifier") or u.get("id")
        ok = send_push(u["push_subscription"], args.titulo, args.corpo, args.url)
        if ok:
            enviados += 1
            print(f"[ok] enviado para {nome}")
        else:
            falhas += 1
            print(f"[falha] {nome}")

    print(f"\nResumo: {enviados} enviados, {falhas} falhas de {len(alvos)} inscritos.")


if __name__ == "__main__":
    main()
