# services/finanzas/integracion_inventario.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from crud.finanzas.config_contable import obtener_configuracion_evento_modulo
from modules.contabilidad import accounting_service
from models.inventario.inventario import InventarioMovimiento


logger = logging.getLogger(__name__)


def _d(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _obtener_reglas_ingreso_compra_sin_factura(db: Session) -> list[dict]:
    reglas = obtener_configuracion_evento_modulo(
        db,
        modulo="INVENTARIO",
        submodulo="RECEPCION",
        tipo_documento="COMPRA_SIN_FACTURA",
        codigo_evento="INGRESO_COMPRA_SIN_FACTURA",
    )

    if not reglas:
        raise ValueError(
            "No existe configuración contable activa para INVENTARIO / RECEPCION / COMPRA_SIN_FACTURA."
        )

    return reglas


def _resolver_monto_movimiento(movimiento: InventarioMovimiento) -> Decimal:
    """
    Camino dorado:
    - monto = cantidad * costo_unitario
    - si el costo es 0, no se contabiliza
    """
    cantidad = _d(getattr(movimiento, "cantidad", None))
    costo_unitario = _d(getattr(movimiento, "costo_unitario", None))
    monto = cantidad * costo_unitario

    if monto <= 0:
        raise ValueError(
            "No fue posible determinar el monto contable del movimiento de inventario. "
            "Se requiere cantidad y costo_unitario mayor a 0."
        )

    return monto.quantize(Decimal("0.01"))


def _descripcion_movimiento(movimiento: InventarioMovimiento) -> str:
    producto = getattr(movimiento, "producto", None)
    nombre_producto = getattr(producto, "nombre", None) if producto else None

    referencia_tipo = getattr(movimiento, "referencia_tipo", None) or "INVENTARIO"
    referencia_id = getattr(movimiento, "referencia_id", None)
    observacion = getattr(movimiento, "observacion", None)

    if observacion:
        return str(observacion)

    if nombre_producto:
        return f"{referencia_tipo} #{referencia_id or ''} · {nombre_producto}".strip()

    return f"{referencia_tipo} #{referencia_id or ''}".strip()


def _construir_detalles_asiento(
    *,
    reglas: list[dict],
    monto: Decimal,
    descripcion: str,
) -> list[dict]:
    detalles: list[dict] = []

    for regla in reglas:
        lado = str(regla["lado"]).upper().strip()
        codigo_cuenta = str(regla["codigo_cuenta"]).strip()
        nombre_cuenta = str(regla["nombre_cuenta"]).strip()

        detalles.append(
            {
                "codigo_cuenta": codigo_cuenta,
                "nombre_cuenta": nombre_cuenta,
                "descripcion": descripcion,
                "debe": monto if lado == "DEBE" else Decimal("0"),
                "haber": monto if lado == "HABER" else Decimal("0"),
            }
        )

    if not detalles:
        raise ValueError("No fue posible construir el asiento contable del movimiento de inventario.")

    return detalles


def contabilizar_salida_al_costo(
    db: Session,
    *,
    movimiento_id: int,
    usuario: str | None = None,
) -> int | None:
    """Asiento de salida al costo promedio. No corre para referencia VENTA.

    Si no hay configuración INVENTARIO / SALIDA / SALIDA_INVENTARIO, no inventa
    cuentas: el movimiento igual queda valorizado. No hace commit ni rollback.
    """
    movimiento: InventarioMovimiento | None = db.get(InventarioMovimiento, movimiento_id)
    if not movimiento:
        raise ValueError("Movimiento de inventario no encontrado.")
    if str(getattr(movimiento, "referencia_tipo", "") or "").upper() == "VENTA":
        return None

    monto = (_d(movimiento.cantidad) * _d(movimiento.costo_unitario)).quantize(Decimal("0.01"))
    if monto <= 0:
        return None

    try:
        reglas = obtener_configuracion_evento_modulo(
            db,
            modulo="INVENTARIO",
            submodulo="SALIDA",
            tipo_documento="SALIDA_COSTO",
            codigo_evento="SALIDA_INVENTARIO",
        )
    except SQLAlchemyError:
        logger.info(
            "No se pudo leer la configuración de salida de inventario; el movimiento %s queda valorizado sin asiento.",
            movimiento_id,
        )
        return None
    if not reglas:
        logger.info(
            "Sin configuración INVENTARIO/SALIDA/SALIDA_INVENTARIO; la salida %s queda valorizada sin asiento.",
            movimiento_id,
        )
        return None

    detalles = _construir_detalles_asiento(
        reglas=reglas,
        monto=monto,
        descripcion=f"Salida inventario {movimiento_id}",
    )
    return accounting_service.post_entry(
        db=db,
        fecha=getattr(movimiento, "fecha", None),
        origen_tipo="INVENTARIO_SALIDA",
        origen_id=int(movimiento.id),
        glosa=f"Salida de inventario al costo · movimiento {movimiento.id}"[:255],
        detalles=detalles,
        usuario=usuario,
        moneda="CLP",
        do_commit=False,
    )


def contabilizar_ingreso_compra_sin_factura(
    db: Session,
    *,
    movimiento_id: int,
    usuario: str | None = None,
) -> None:
    """
    Integra un movimiento de inventario de recepción física sin factura.

    Asiento esperado:
    - Debe  : 110401 Inventario mercadería
    - Haber : 210110 Proveedores por facturar
    """
    movimiento: InventarioMovimiento | None = db.get(InventarioMovimiento, movimiento_id)
    if not movimiento:
        raise ValueError("Movimiento de inventario no encontrado.")

    monto = _resolver_monto_movimiento(movimiento)
    descripcion = _descripcion_movimiento(movimiento)
    referencia_tipo = getattr(movimiento, "referencia_tipo", None) or "INVENTARIO_MOV"
    # 1 asiento por movimiento: usar id del movimiento como origen.
    referencia_id = movimiento.id
    fecha = getattr(movimiento, "fecha", None)

    try:
        reglas = _obtener_reglas_ingreso_compra_sin_factura(db)
        detalles_asiento = _construir_detalles_asiento(
            reglas=reglas,
            monto=monto,
            descripcion=descripcion,
        )

        accounting_service.post_entry(
            db=db,
            fecha=fecha,
            origen_tipo=str(referencia_tipo),
            origen_id=int(referencia_id),
            glosa=f"Recepción mercadería sin factura · {descripcion}",
            detalles=detalles_asiento,
            usuario=usuario,
            moneda="CLP",
            do_commit=False,
        )

        logger.info(
            "Asiento contable de inventario generado correctamente para movimiento id=%s.",
            movimiento.id,
        )

    except SQLAlchemyError as exc:
        logger.exception(
            "No fue posible contabilizar el movimiento de inventario id=%s: %s",
            movimiento.id,
            exc,
        )
        db.rollback()
        raise ValueError(
            "No fue posible generar el asiento contable del ingreso de inventario."
        ) from exc

    except Exception as exc:
        logger.exception(
            "Error inesperado al contabilizar el movimiento de inventario id=%s: %s",
            movimiento.id,
            exc,
        )
        db.rollback()
        raise ValueError(
            "No fue posible generar el asiento contable del ingreso de inventario."
        ) from exc