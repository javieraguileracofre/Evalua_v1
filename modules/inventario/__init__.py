# modules/inventario — dueño de stock y movimientos.
from __future__ import annotations

from sqlalchemy.orm import Session

from crud.inventario import inventario as crud_inv


def get_producto(db: Session, producto_id: int):
    if hasattr(crud_inv, "get_producto"):
        return crud_inv.get_producto(db, producto_id)
    return None


def ajustar_stock(db: Session, **kwargs):
    """Entrada pública para ajustes; Taller/Ventas no deben tocar tablas de stock directo."""
    if hasattr(crud_inv, "ajustar_stock"):
        return crud_inv.ajustar_stock(db, **kwargs)
    if hasattr(crud_inv, "registrar_ajuste"):
        return crud_inv.registrar_ajuste(db, **kwargs)
    raise NotImplementedError("No hay operación de ajuste expuesta en crud.inventario.")
