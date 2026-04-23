# tests/test_finanzas_bulk_limits.py
# -*- coding: utf-8 -*-
"""Límites operativos usados por inventario, clientes y export contable."""
from __future__ import annotations

from core.bulk_limits import (
    BULK_CSV_MAX_BYTES,
    BULK_CSV_MAX_ROWS,
    LIBRO_MAYOR_CONSOLIDADO_MAX_CUENTAS,
    LIST_PAGE_DEFAULT,
    LIST_PAGE_MAX,
)


def test_limites_csv_razonables() -> None:
    assert 262_144 <= BULK_CSV_MAX_BYTES <= 32 * 1024 * 1024
    assert 100 <= BULK_CSV_MAX_ROWS <= 50_000


def test_paginacion_listados_consistente() -> None:
    assert 25 <= LIST_PAGE_DEFAULT <= 500
    assert LIST_PAGE_DEFAULT <= LIST_PAGE_MAX <= 2000


def test_tope_libro_mayor_consolidado() -> None:
    assert 5 <= LIBRO_MAYOR_CONSOLIDADO_MAX_CUENTAS <= 150
