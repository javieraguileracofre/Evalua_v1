# core/bulk_limits.py
# -*- coding: utf-8 -*-
"""Límites de cargas masivas y consultas pesadas (configurables por variables de entorno)."""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw, 10)
    except ValueError:
        return default


# CSV: tamaño máximo en bytes (defecto 8 MiB).
BULK_CSV_MAX_BYTES = max(262_144, min(_int_env("BULK_CSV_MAX_BYTES", 8 * 1024 * 1024), 32 * 1024 * 1024))

# CSV: máximo de filas de datos procesadas por petición (cabecera no cuenta).
BULK_CSV_MAX_ROWS = max(100, min(_int_env("BULK_CSV_MAX_ROWS", 5000), 50_000))

# Listados HTML: tamaño de página (clientes, productos).
LIST_PAGE_DEFAULT = min(max(_int_env("LIST_PAGE_DEFAULT", 200), 25), 500)
LIST_PAGE_MAX = min(max(_int_env("LIST_PAGE_MAX", 500), LIST_PAGE_DEFAULT), 2000)

# Libro mayor consolidado (una hoja por cuenta + resumen).
LIBRO_MAYOR_CONSOLIDADO_MAX_CUENTAS = max(5, min(_int_env("LIBRO_MAYOR_CONSOLIDADO_MAX_CUENTAS", 75), 150))
