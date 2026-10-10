# core/paths.py
# -*- coding: utf-8 -*-
"""Rutas de archivos del proyecto (independientes del cwd al arrancar Uvicorn)."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"


def operational_storage(*parts: str) -> Path:
    """Archivos de una compañía. En database_per_company no comparten carpeta."""
    import re

    from core.company_context import get_company_context
    from core.config import settings

    root = PROJECT_ROOT / "storage"
    if settings.database_per_company:
        ctx = get_company_context()
        code = ctx.company_code if ctx is not None and ctx.authorized else ""
        if not re.fullmatch(r"[a-z][a-z0-9_]*", code or ""):
            raise RuntimeError("No hay una compañía activa para almacenar el archivo.")
        root = root / "companies" / code
    return root.joinpath(*parts)
