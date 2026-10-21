# modules/inventario — dueño de stock y movimientos.
from __future__ import annotations

from crud.inventario.inventario import (
    crear_producto,
    eliminar_producto,
    get_producto,
    ingresar_stock_producto,
    registrar_ajuste_inventario,
    registrar_movimiento_inventario,
)

ajustar_stock = registrar_ajuste_inventario

__all__ = [
    "ajustar_stock",
    "crear_producto",
    "eliminar_producto",
    "get_producto",
    "ingresar_stock_producto",
    "registrar_ajuste_inventario",
    "registrar_movimiento_inventario",
]
