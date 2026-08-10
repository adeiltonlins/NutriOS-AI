"""Cria o primeiro ADMIN e imprime um código de uso único."""
import argparse
from datetime import datetime, timedelta, timezone

from app import auth, saas_store

parser = argparse.ArgumentParser()
parser.add_argument("--name", required=True)
parser.add_argument("--identifier", required=True)
parser.add_argument("--hours", type=int, default=24)
args = parser.parse_args()

existing = saas_store.get_user_by_identifier(args.identifier)
admin = existing or saas_store.create_user({
    "name": args.name,
    "identifier": args.identifier.lower().strip(),
    "role": "admin",
    "active": True,
})
if admin["role"] != "admin":
    raise SystemExit("O identificador já pertence a um cliente.")
code = auth.issue_code(admin["id"], datetime.now(timezone.utc) + timedelta(hours=args.hours), admin["id"])
print(f"ADMIN criado/confirmado. Código (exibido uma única vez): {code}")
