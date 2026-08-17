"""PWA por nutricionista para as páginas públicas /n/{slug}."""
from __future__ import annotations

import io
import json
import re
from urllib.parse import quote

import requests
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageOps

from app import clinical_extensions, saas_store

router = clinical_extensions.router
STATIC_DIR = clinical_extensions.STATIC_DIR
DEFAULT_192 = "/static/icons/icon-192.png"
DEFAULT_512 = "/static/icons/icon-512.png"


def _client(slug: str) -> dict:
    client = saas_store.get_user_by_slug(slug)
    if not client or client.get("role") != "client" or not client.get("active"):
        raise HTTPException(404, "Assistente indisponível")
    if client.get("expires_at"):
        from datetime import datetime, timezone
        if datetime.fromisoformat(str(client["expires_at"]).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise HTTPException(404, "Assistente indisponível")
    return client


def _brand(slug: str) -> dict:
    client = _client(slug)
    config = dict(client.get("ai_config") or {})
    name = str(config.get("nome") or client.get("name") or "NutriOS").strip()[:80]
    short = name if len(name) <= 24 else name[:24].rstrip()
    logo = config.get("logo_url") if str(config.get("logo_url") or "").startswith("https://") else None
    return {"name": name, "short_name": short, "logo_url": logo, "theme_color": str(config.get("cor_principal") or "#168f43")}


def _safe_color(value: str) -> str:
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else "#168f43"


@router.get("/n/{public_slug}/manifest.webmanifest")
def personalized_manifest(public_slug: str):
    brand = _brand(public_slug)
    icon_base = f"/n/{quote(public_slug, safe='')}/pwa-icon"
    payload = {
        "name": brand["name"],
        "short_name": brand["short_name"],
        "description": f"Atendimento nutricional de {brand['name']}",
        "start_url": f"/n/{public_slug}",
        "scope": f"/n/{public_slug}",
        "id": f"/n/{public_slug}",
        "display": "standalone",
        "background_color": "#f7faf8",
        "theme_color": _safe_color(brand["theme_color"]),
        "orientation": "portrait-primary",
        "icons": [
            {"src": f"{icon_base}/192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": f"{icon_base}/512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": f"{icon_base}/512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "categories": ["health", "medical", "productivity"],
        "lang": "pt-BR",
        "dir": "ltr",
        "prefer_related_applications": False,
    }
    return Response(json.dumps(payload, ensure_ascii=False), media_type="application/manifest+json", headers={"Cache-Control": "no-store, max-age=0"})


def _load_brand_image(slug: str):
    logo_url = _brand(slug).get("logo_url")
    if not logo_url:
        return None
    try:
        response = requests.get(logo_url, timeout=8, allow_redirects=True)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGBA")
    except Exception:
        return None


def _render_logo(slug: str, size: int, maskable: bool = False) -> bytes:
    image = _load_brand_image(slug)
    if image is None:
        path = STATIC_DIR / "icons" / ("icon-192.png" if size == 192 else "icon-512.png")
        return path.read_bytes()
    canvas = Image.new("RGBA", (size, size), (247, 250, 248, 255))
    target = int(size * (0.68 if maskable else 0.82))
    fitted = ImageOps.contain(image, (target, target), Image.Resampling.LANCZOS)
    canvas.alpha_composite(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


@router.get("/n/{public_slug}/pwa-icon/{variant}.png")
def personalized_icon(public_slug: str, variant: str):
    variants = {"192": (192, False), "512": (512, False), "512-maskable": (512, True)}
    if variant not in variants:
        raise HTTPException(404, "Ícone não encontrado")
    size, maskable = variants[variant]
    return Response(_render_logo(public_slug, size, maskable), media_type="image/png", headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=86400"})


@router.get("/n/{public_slug}/sw.js")
def personalized_service_worker(public_slug: str):
    _client(public_slug)
    scope = f"/n/{public_slug}"
    script = f"""const CACHE='nutrios-pwa-{public_slug}-v1';\nconst SCOPE={scope!r};\nself.addEventListener('install',event=>{{event.waitUntil(caches.open(CACHE).then(cache=>cache.add(SCOPE)).catch(()=>{{}}));self.skipWaiting();}});\nself.addEventListener('activate',event=>{{event.waitUntil(self.clients.claim());}});\nself.addEventListener('fetch',event=>{{const url=new URL(event.request.url);if(url.origin!==self.location.origin)return;if(!url.pathname.startsWith(SCOPE))return;event.respondWith(fetch(event.request).catch(()=>caches.match(event.request).then(r=>r||caches.match(SCOPE))));}});\n"""
    return Response(script, media_type="application/javascript", headers={"Cache-Control": "no-store", "Service-Worker-Allowed": scope})


# Registrada antes da rota pública homônima de main.py porque este router é
# incluído pelo FastAPI antes das rotas declaradas diretamente no main.
@router.get("/n/{public_slug}")
def personalized_public_chat(public_slug: str):
    _client(public_slug)
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    manifest = f"/n/{quote(public_slug, safe='')}/manifest.webmanifest"
    worker = f"/n/{quote(public_slug, safe='')}/sw.js"
    brand = _brand(public_slug)
    theme = _safe_color(brand["theme_color"])
    icon = f"/n/{quote(public_slug, safe='')}/pwa-icon/192.png"
    scope = f"/n/{public_slug}"
    head = (
        f'<link rel="manifest" href="{manifest}">'
        f'<meta name="theme-color" content="{theme}">'
        f'<link rel="apple-touch-icon" href="{icon}">'
        f'<script>window.__NUTRIOS_PUBLIC_SLUG__={json.dumps(public_slug)};'
        f'if("serviceWorker" in navigator){{window.addEventListener("load",()=>navigator.serviceWorker.register({json.dumps(worker)},{{scope:{json.dumps(scope)}}}).catch(()=>{{}}));}}</script>'
    )
    html = html.replace("</head>", head + "</head>", 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
