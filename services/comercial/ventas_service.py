# services/comercial/ventas_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from crud.comercial import nota_venta as crud_nota_venta
from services.finanzas.integracion_ventas import (
    ContabilizacionVentaError,
    contabilizar_anulacion_nota_venta,
    contabilizar_nota_venta,
)

from models import NotaVenta, Producto


def _to_decimal(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _producto_controla_stock(producto: Producto) -> bool:
    return bool(getattr(producto, "controla_stock", True)) and not bool(
        getattr(producto, "es_servicio", False)
    )


def _validar_stock_disponible(
    db: Session,
    *,
    items: list[dict],
) -> None:
    if not items:
        raise ValueError("Debes agregar al menos un producto a la venta.")

    acumulado_por_producto: dict[int, Decimal] = {}

    for item in items:
        producto_id = int(item["producto_id"])
        cantidad = _to_decimal(item.get("cantidad"))

        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor a 0.")

        acumulado_por_producto[producto_id] = (
            acumulado_por_producto.get(producto_id, Decimal("0")) + cantidad
        )

    for producto_id, cantidad_total in acumulado_por_producto.items():
        producto: Producto | None = db.get(Producto, producto_id)
        if not producto:
            raise ValueError(f"Producto ID {producto_id} no existe.")

        if not bool(getattr(producto, "activo", True)):
            raise ValueError(f"El producto '{producto.nombre}' está inactivo.")

        if not _producto_controla_stock(producto):
            continue

        stock_actual = _to_decimal(getattr(producto, "stock_actual", 0))

        if stock_actual < cantidad_total:
            raise ValueError(
                f"Stock insuficiente para '{producto.nombre}'. "
                f"Disponible: {stock_actual}, requerido: {cantidad_total}."
            )


def crear_venta_pos(
    db: Session,
    *,
    cliente_id: int,
    fecha_emision,
    fecha_vencimiento,
    tipo_pago: str,
    items: list[dict],
    afecta_iva: bool = True,
    usuario: str | None = None,
) -> NotaVenta:
    _validar_stock_disponible(
        db,
        items=items,
    )

    nota = crud_nota_venta.crear_nota_venta_desde_form(
        db=db,
        cliente_id=cliente_id,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento,
        tipo_pago=tipo_pago,
        items=items,
        afecta_iva=afecta_iva,
        auto_commit=False,
    )

    try:
        contabilizar_nota_venta(
            db,
            nota_venta_id=nota.id,
            usuario=usuario,
        )
        db.commit()
    except ContabilizacionVentaError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return nota


def anular_venta_pos(
    db: Session,
    nota: NotaVenta,
    *,
    usuario: str | None = None,
) -> NotaVenta:
    if nota.estado == "ANULADA":
        raise ValueError("La nota ya está anulada.")

    nota_anulada = crud_nota_venta.anular_nota_venta(db, nota)

    # Regla contable: al anular no se borra historial, se genera un asiento reverso.
    contabilizar_anulacion_nota_venta(
        db=db,
        nota_venta_id=nota_anulada.id,
        usuario=usuario,
    )

    return nota_anulada