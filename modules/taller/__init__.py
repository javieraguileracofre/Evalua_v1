# modules/taller — órdenes de trabajo. El stock se mueve por modules.inventario.
from __future__ import annotations

from crud.comercial.taller import (
    actualizar_orden_servicio,
    crear_orden_servicio,
    listar_ordenes,
    obtener_orden,
)

__all__ = [
    "actualizar_orden_servicio",
    "crear_orden_servicio",
    "listar_ordenes",
    "obtener_orden",
]
