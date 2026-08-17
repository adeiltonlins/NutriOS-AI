"""Envio de push notifications via Web Push Protocol (VAPID).
Falhas são registradas, nunca quebram o fluxo principal."""
import os
import json
from pywebpush import webpush, WebPushException


def send_push(subscription: dict, title: str, body: str, url: str = "/app", silent: bool = False) -> bool:
    """Enviauma notificação push para uma subscription salva.
    
    subscription: dict com 'endpoint' e 'keys' (retornado pelo navegador)
    Retorna True se enviado com sucesso.
    """
    vapid_private = os.getenv("VAPID_PRIVATE_KEY", "")
    vapid_public = os.getenv("VAPID_PUBLIC_KEY", "")
    if not (vapid_private and vapid_public):
        print("[push] VAPID não configurado; push pulado")
        return False
    
    if not subscription or not subscription.get("endpoint"):
        print("[push] subscription inválida")
        return False
    
    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "silent": silent,
    })

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=vapid_private,
            vapid_claims={
                "sub": "mailto:suporte@usenutrios.com.br",
                "aud": subscription["endpoint"],
            },
        )
        return True
    except WebPushException as exc:
        print(f"[push] Falha ao enviar: {exc}")
        return False
    except Exception as exc:
        print(f"[push] Erro inesperado: {exc}")
        return False


def send_to_user(client_id: str, title: str, body: str, url: str = "/app", saas_store=None) -> bool:
    """Busca a subscription do usuário no saas_store e envia push."""
    if saas_store is None:
        from app import saas_store
    user = saas_store.get_user(client_id)
    if not user:
        return False
    sub = user.get("push_subscription")
    if not sub:
        return False
    return send_push(sub, title, body, url)
