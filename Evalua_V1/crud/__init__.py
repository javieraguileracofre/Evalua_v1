# crud/__init__.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from .cobranza import cobranza
from .comercial import nota_venta
from .comunicaciones import email_log
from .inventario import inventario
from .maestros import cliente
from .postventa import postventa

__all__ = [
    "cobranza",
    "nota_venta",
    "email_log",
    "inventario",
    "cliente",
    "postventa",
]