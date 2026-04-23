# crud/finanzas/contabilidad.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from crud.finanzas.contabilidad_asientos import crear_asiento as crear_asiento_base
from models.finanzas import MovimientoCaja
from models.cobranza import CuentaPorCobrar

IVA_RATE = 0.19


def _to_decimal(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


# ============================================================
# ASIENTOS CONTABLES
# ============================================================

def crear_asiento(
    db: Session,
    *,
    fecha: date | datetime,
    origen: str,
    origen_id: int,
    glosa: str,
    detalles: List[Dict],
    creado_por: Optional[str] = None,
) -> int:
    """
    Wrapper camino dorado para mantener compatibilidad con código legacy.
    Delega en crud.finanzas.contabilidad_asientos.crear_asiento.
    """
    if isinstance(fecha, date) and not isinstance(fecha, datetime):
        fecha = datetime.combine(fecha, datetime.min.time())

    return crear_asiento_base(
        db=db,
        fecha=fecha,
        origen_tipo=origen,
        origen_id=origen_id,
        glosa=glosa,
        detalles=detalles,
        usuario=creado_por,
        moneda="CLP",
    )


# ============================================================
# CUENTAS POR COBRAR
# ============================================================

def crear_cxc_desde_venta(
    db: Session,
    *,
    cliente_id: int,
    documento_id: int,
    fecha_emision: date,
    fecha_vencimiento: date,
    monto_neto: float,
    monto_iva: float,
    documento_tipo: str = "NOTA_VENTA",
) -> CuentaPorCobrar:
    """
    Función legacy conservada por compatibilidad.
    """
    total = round(float(monto_neto or 0) + float(monto_iva or 0), 2)

    cxc = CuentaPorCobrar(
        cliente_id=cliente_id,
        documento_tipo=documento_tipo,
        documento_id=documento_id,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento,
        monto_neto=monto_neto,
        monto_iva=monto_iva,
        monto_total=total,
        saldo_pendiente=total,
        estado="PENDIENTE",
    )

    db.add(cxc)
    db.commit()
    db.refresh(cxc)
    return cxc


# ============================================================
# MOVIMIENTOS DE CAJA
# ============================================================

def registrar_ingreso_caja_desde_venta(
    db: Session,
    *,
    caja_id: int,
    fecha: date | datetime,
    origen: str,
    origen_id: int,
    descripcion: str,
    monto: float,
) -> MovimientoCaja:
    """
    Función legacy conservada por compatibilidad.
    """
    if isinstance(fecha, date) and not isinstance(fecha, datetime):
        fecha = datetime.combine(fecha, datetime.min.time())

    mov = MovimientoCaja(
        caja_id=caja_id,
        fecha=fecha,
        tipo_movimiento="INGRESO",
        origen=origen,
        origen_id=origen_id,
        descripcion=(descripcion or "")[:255],
        monto=_to_decimal(monto),
    )

    db.add(mov)
    db.commit()
    db.refresh(mov)
    return mov