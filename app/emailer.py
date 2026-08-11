"""Notificações por SMTP. Falhas são registradas, nunca quebram o atendimento."""
import os
import smtplib
from email.message import EmailMessage


def send_notification(to_email: str, subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST", "")
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", user)
    port = int(os.getenv("SMTP_PORT", "587"))
    if not (host and user and password and sender and to_email):
        print("[emailer] SMTP não configurado; notificação registrada apenas no painel")
        return False
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, to_email, subject
    message.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=12) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(message)
        return True
    except Exception as exc:
        print(f"[emailer] Falha ao enviar: {exc}")
        return False
