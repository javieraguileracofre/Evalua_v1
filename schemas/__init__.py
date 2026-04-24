# schemas/__init__.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from .inventario import inventario
from .maestros import cliente, proveedor

__all__ = [
    "inventario",
    "cliente",
    "proveedor",
]