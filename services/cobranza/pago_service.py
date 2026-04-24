# services/cobranza/pago_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from crud.finanzas.config_contable import obtener_configuracion_evento_modulo
from crud.finanzas.contabilidad_asientos import crear_asiento
from models.cobranza.cuentas_por_cobrar import CuentaPorCobrar, PagoCliente
from models.finanzas.caja import Caja, MovimientoCaja


def _d(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _actualizar_cxc_por_pago(
    db: Session,
    cxc: CuentaPorCobrar,
    monto_pago: Decimal,
) -> None:
    if monto_pago <= 0:
        raise ValueError("El monto de pago debe ser mayor a 0.")

    saldo_actual = _d(cxc.saldo_pendiente)
    if saldo_actual <= 0:
        raise ValueError("La cuenta por cobrar ya se encuentra saldada.")

    nuevo_saldo = saldo_actual - monto_pago
    if nuevo_saldo < Decimal("-0.01"):
        raise ValueError("El pago excede el saldo pendiente.")

    cxc.saldo_pendiente = max(nuevo_saldo, Decimal("0"))

    if _d(cxc.saldo_pendiente) < Decimal("0.01"):
        cxc.estado = "PAGADA"
        cxc.saldo_pendiente = Decimal("0")
    else:
        cxc.estado = "PARCIAL"

    db.add(cxc)
    db.flush()


def _registrar_movimiento_caja_por_pago(
    db: Session,
    pago: PagoCliente,
) -> MovimientoCaja:
    if pago.caja_id is None:
        raise ValueError("El pago no tiene caja asociada.")

    caja = db.get(Caja, pago.caja_id)
    if not caja:
        raise ValueError("Caja no encontrada.")

    mov = MovimientoCaja(
        caja_id=pago.caja_id,
        fecha=pago.fecha_pago,
        tipo_movimiento="INGRESO",
        medio_pago=pago.forma_pago,
        monto=pago.monto_pago,
        referencia_tipo="PAGO_CLIENTE",
        referencia_id=pago.id,
        observacion=f"Pago cliente CxC {pago.cuenta_cobrar_id}",
    )
    db.add(mov)

    caja.saldo_actual = float(_d(caja.saldo_actual) + _d(pago.monto_pago))
    db.add(caja)
    db.flush()

    return mov


def _obtener_configuracion_pago_cliente(db: Session) -> list[dict]:
    reglas = obtener_configuracion_evento_modulo(
        db,
        modulo="COBRANZA",
        submodulo="RECIBO",
        tipo_documento="NORMAL",
        codigo_evento="COBRANZA_CLIENTE",
    )

    if not reglas:
        raise ValueError(
            "No existe configuración contable activa para cobranza: "
            "modulo=COBRANZA, submodulo=RECIBO, tipo_documento=NORMAL, evento=COBRANZA_CLIENTE."
        )

    return reglas


def _construir_detalles_asiento_pago(
    *,
    pago: PagoCliente,
    cxc: CuentaPorCobrar,
    reglas: list[dict],
    monto: Decimal,
) -> list[dict]:
    detalles: list[dict] = []

    for regla in reglas:
        lado = str(regla["lado"]).upper()
        codigo_cuenta = str(regla["codigo_cuenta"]).strip()
        nombre_cuenta = str(regla["nombre_cuenta"]).strip()

        detalles.append(
            {
                "codigo_cuenta": codigo_cuenta,
                "nombre_cuenta": nombre_cuenta,
                "descripcion": f"Pago cliente CxC {cxc.id}",
                "debe": monto if lado == "DEBE" else Decimal("0"),
                "haber": monto if lado == "HABER" else Decimal("0"),
            }
        )

    if not detalles:
        raise ValueError(
            f"No fue posible construir el asiento contable del pago cliente {pago.id}."
        )

    return detalles


def contabilizar_pago_cliente(
    db: Session,
    *,
    pago_id: int,
    usuario: Optional[str] = None,
) -> None:
    pago = db.get(PagoCliente, pago_id)
    if not pago:
        raise ValueError("PagoCliente no encontrado.")

    cxc = pago.cuenta_cobrar
    if not cxc:
        raise ValueError("Pago no vinculado a CuentaPorCobrar.")

    monto = _d(pago.monto_pago)
    if monto <= 0:
        raise ValueError("Monto de pago no válido.")

    try:
        _actualizar_cxc_por_pago(db, cxc, monto)
        _registrar_movimiento_caja_por_pago(db, pago)

        reglas = _obtener_configuracion_pago_cliente(db)
        detalles_asiento = _construir_detalles_asiento_pago(
            pago=pago,
            cxc=cxc,
            reglas=reglas,
            monto=monto,
        )

        crear_asiento(
            db=db,
            fecha=pago.fecha_pago,
            origen_tipo="PAGO_CLIENTE",
            origen_id=pago.id,
            glosa=f"Pago cliente CxC {cxc.id}",
            detalles=detalles_asiento,
            usuario=usuario,
            moneda="CLP",
        )

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise