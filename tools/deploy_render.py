# tools/deploy_render.py
# -*- coding: utf-8 -*-
"""
Dispara un deploy manual en Render.com sin hacer push a GitHub.

Requisito: URL del Deploy Hook del servicio evalua-v1.
  Render Dashboard → evalua-v1 → Settings → Deploy Hook → Create / Copy

Configure en .env:
  RENDER_DEPLOY_HOOK_URL=https://api.render.com/deploy/srv-XXXX?key=YYYY

Uso:
  python tools/deploy_render.py
  python tools/deploy_render.py --clear-cache
  python tools/deploy_render.py --hook-url "https://api.render.com/deploy/..."
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def _append_query(url: str, key: str, value: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{key}={value}"


def trigger_render_deploy(*, hook_url: str, clear_cache: bool = False) -> tuple[int, str]:
    url = hook_url.strip()
    if not url.startswith("https://api.render.com/deploy/"):
        return 1, "La URL debe ser un Deploy Hook de Render (https://api.render.com/deploy/...)."

    if clear_cache:
        url = _append_query(url, "clearCache", "true")

    try:
        import httpx
    except ImportError as exc:
        return 1, f"Falta httpx: {exc}"

    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.post(url)
        response.raise_for_status()
    except Exception as exc:
        return 1, f"No se pudo disparar el deploy: {exc}"

    return 0, f"Deploy solicitado en Render (HTTP {response.status_code})."


def main() -> int:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="Deploy manual a Render (servicio evalua-v1) vía Deploy Hook.",
    )
    parser.add_argument(
        "--hook-url",
        default=(os.getenv("RENDER_DEPLOY_HOOK_URL") or "").strip(),
        help="Deploy Hook URL (o variable RENDER_DEPLOY_HOOK_URL en .env)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Limpia caché de build en Render (clearCache=true)",
    )
    args = parser.parse_args()

    if not args.hook_url:
        print(
            "ERROR: Defina RENDER_DEPLOY_HOOK_URL en .env o pase --hook-url.\n"
            "  1. Render Dashboard → evalua-v1 → Settings → Deploy Hook\n"
            "  2. Copie la URL y guárdela en .env o en GitHub Secrets (RENDER_DEPLOY_HOOK_URL)",
            file=sys.stderr,
        )
        return 1

    code, message = trigger_render_deploy(hook_url=args.hook_url, clear_cache=args.clear_cache)
    if code == 0:
        print(message)
        print("  Siga el build: https://dashboard.render.com/")
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
