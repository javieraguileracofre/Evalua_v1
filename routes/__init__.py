# routes/__init__.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from .ui import (
    cliente,
    cobranza,
    cuentas_por_pagar,
    fin_periodos,
    finanzas,
    home,
    inicio,
    inventario,
    ventas_pos,
)

__all__ = [
    "cliente",
    "cobranza",
    "cuentas_por_pagar",
    "fin_periodos",
    "finanzas",
    "home",
    "inicio",
    "inventario",
    "ventas_pos",
]