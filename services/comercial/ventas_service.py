# services/comercial/ventas_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from crud.comercial import nota_venta as crud_nota_venta
from erp_platform.events import types as event_types
from services.finanzas.integracion_ventas import (
    ContabilizacionVentaError,
    contabilizar_anulacion_nota_venta,
    contabilizar_nota_venta,
    eliminar_movimiento_contable_nota_venta,
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
    stock_extra_por_producto: dict[int, Decimal] | None = None,
) -> None:
    if not items:
        raise ValueError("Debes agregar al menos un producto a la venta.")

    acumulado_por_producto: dict[int, Decimal] = {}
    extras = stock_extra_por_producto or {}

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

        stock_actual = _to_decimal(getattr(producto, "stock_actual", 0)) + extras.get(
            producto_id, Decimal("0")
        )

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
        from erp_platform.events import flush_outbox_after_commit, publish_in_transaction

        publish_in_transaction(
            db,
            event_name=event_types.VENTA_CONFIRMADA,
            payload={
                "nota_venta_id": int(nota.id),
                "cliente_id": int(nota.cliente_id) if getattr(nota, "cliente_id", None) else None,
                "numero": str(getattr(nota, "numero", "") or ""),
            },
            correlation_id=f"NOTA_VENTA:{int(nota.id)}",
        )
        db.commit()
        flush_outbox_after_commit(db)
    except ContabilizacionVentaError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return nota


def actualizar_venta_pos(
    db: Session,
    nota: NotaVenta,
    *,
    cliente_id: int,
    fecha_emision,
    fecha_vencimiento,
    tipo_pago: str,
    items: list[dict],
    afecta_iva: bool = True,
    usuario: str | None = None,
) -> NotaVenta:
    if not crud_nota_venta.puede_editar_nota(nota):
        raise ValueError(
            crud_nota_venta.motivo_bloqueo_edicion(nota)
            or "No se puede editar esta nota de venta."
        )

    # Stock aún comprometido por la nota actual: se suma al disponible para validar.
    stock_extra: dict[int, Decimal] = {}
    for det in getattr(nota, "detalles", None) or []:
        pid = int(det.producto_id)
        stock_extra[pid] = stock_extra.get(pid, Decimal("0")) + _to_decimal(det.cantidad)

    _validar_stock_disponible(
        db,
        items=items,
        stock_extra_por_producto=stock_extra,
    )

    try:
        nota_actualizada = crud_nota_venta.actualizar_nota_venta_desde_form(
            db=db,
            nota=nota,
            cliente_id=cliente_id,
            fecha_emision=fecha_emision,
            fecha_vencimiento=fecha_vencimiento,
            tipo_pago=tipo_pago,
            items=items,
            afecta_iva=afecta_iva,
            auto_commit=False,
        )
        eliminar_movimiento_contable_nota_venta(
            db,
            nota_venta_id=nota_actualizada.id,
        )
        contabilizar_nota_venta(
            db,
            nota_venta_id=nota_actualizada.id,
            usuario=usuario,
        )
        from core.request_context import get_request_context
        from erp_platform.events import flush_outbox_after_commit, publish_in_transaction

        # correlation distinta a la creación (outbox idempotente por correlation_id);
        # sufijo por request para permitir múltiples ediciones.
        req_suffix = get_request_context().get("request_id") or "manual"
        publish_in_transaction(
            db,
            event_name=event_types.VENTA_CONFIRMADA,
            payload={
                "nota_venta_id": int(nota_actualizada.id),
                "cliente_id": int(nota_actualizada.cliente_id)
                if getattr(nota_actualizada, "cliente_id", None)
                else None,
                "numero": str(getattr(nota_actualizada, "numero", "") or ""),
                "accion": "actualizacion",
            },
            correlation_id=f"NOTA_VENTA:{int(nota_actualizada.id)}:upd:{req_suffix}",
        )
        db.commit()
        flush_outbox_after_commit(db)
    except ContabilizacionVentaError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    db.refresh(nota_actualizada)
    return nota_actualizada


def anular_venta_pos(
    db: Session,
    nota: NotaVenta,
    *,
    usuario: str | None = None,
) -> NotaVenta:
    if nota.estado == "ANULADA":
        raise ValueError("La nota ya está anulada.")

    if not crud_nota_venta.puede_anular_nota(nota):
        raise ValueError("No se puede anular esta nota de venta.")

    try:
        nota_anulada = crud_nota_venta.anular_nota_venta(db, nota, auto_commit=False)
        # Regla contable: al anular no se borra historial, se genera un asiento reverso.
        contabilizar_anulacion_nota_venta(
            db=db,
            nota_venta_id=nota_anulada.id,
            usuario=usuario,
        )
        from erp_platform.events import flush_outbox_after_commit, publish_in_transaction

        publish_in_transaction(
            db,
            event_name=event_types.VENTA_ANULADA,
            payload={"nota_venta_id": int(nota_anulada.id)},
            correlation_id=f"NOTA_VENTA_ANULACION:{int(nota_anulada.id)}",
        )
        from services.audit.financial import audit_financial_fact

        audit_financial_fact(
            db,
            action="VENTA_ANULADA",
            module="comercial",
            entity="nota_venta",
            entity_id=int(nota_anulada.id),
        )
        db.commit()
        flush_outbox_after_commit(db)
    except ContabilizacionVentaError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return nota_anulada


def eliminar_venta_pos(
    db: Session,
    nota: NotaVenta,
) -> None:
    if not crud_nota_venta.puede_eliminar_nota(nota):
        raise ValueError(
            crud_nota_venta.motivo_bloqueo_eliminacion(nota)
            or "No se puede eliminar esta nota de venta."
        )

    try:
        eliminar_movimiento_contable_nota_venta(
            db,
            nota_venta_id=nota.id,
        )
        crud_nota_venta.eliminar_nota_venta(db, nota, auto_commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
