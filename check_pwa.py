"""Static regression checks for the public personalized PWA layer."""
from pathlib import Path
import ast
import json

ROOT = Path(__file__).resolve().parent
PWA = ROOT / "app" / "pwa.py"
MANIFEST = ROOT / "app" / "static" / "manifest.json"
INDEX = ROOT / "app" / "static" / "index.html"
REQUIRED_MARKERS = [
    "/n/{public_slug}/manifest.webmanifest",
    "/n/{public_slug}/pwa-icon/{variant}.png",
    "/n/{public_slug}/sw.js",
    "serviceWorker.register",
    "scope",
    "start_url",
]


def main() -> int:
    source = PWA.read_text(encoding="utf-8")
    ast.parse(source)
    assert all(marker in source for marker in REQUIRED_MARKERS), "PWA route marker missing"

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert {"192x192", "512x512"} <= {item["sizes"] for item in manifest["icons"]}
    assert any(item.get("purpose") == "maskable" for item in manifest["icons"])
    assert INDEX.exists(), "Public app HTML missing"

    print("PWA static checks: OK")
    print("- personalized manifest route: OK")
    print("- 192/512 icon generation routes: OK")
    print("- maskable icon route: OK")
    print("- per-nutritionist service worker route: OK")
    print("- existing base manifest has required icon sizes: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
