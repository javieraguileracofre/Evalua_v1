# services/leasing_financiero_contabilidad.py
# -*- coding: utf-8 -*-
"""Proyección contable automática alineada a cuentas LEASING (113701, 210701, 410701, 110201)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete
from sqlalchemy.orm import Session

from crud.finanzas.config_contable import obtener_configuracion_evento_modulo
from models.comercial.leasing_financiero_cotizacion import (
    LeasingFinancieroCotizacion,
    LeasingFinancieroProyeccionLinea,
)
from services import leasing_financiero

CUENTA_CXC = "113701"
CUENTA_PASIVO = "210701"
CUENTA_INTERES = "410701"
CUENTA_BANCO = "110201"


def _q2(v: Decimal | float | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _cuenta_desde_config(
    db: Session,
    *,
    submodulo: str,
    tipo_documento: str,
    codigo_evento: str,
    lado: str,
    orden: int,
    fallback: str,
) -> str:
    reglas = obtener_configuracion_evento_modulo(
        db,
        modulo="COMERCIAL",
        submodulo=submodulo,
        tipo_documento=tipo_documento,
        codigo_evento=codigo_evento,
    )
    for r in reglas:
        if (
            str(r.get("lado") or "").strip().upper() == lado
            and int(r.get("orden") or 0) == orden
            and str(r.get("codigo_cuenta") or "").strip()
        ):
            return str(r["codigo_cuenta"]).strip()
    return fallback


def regenerar_proyeccion_contable(db: Session, cotizacion: LeasingFinancieroCotizacion) -> None:
    """Elimina líneas previas y genera originación + cobros proyectados por cuota."""
    db.execute(
        delete(LeasingFinancieroProyeccionLinea).where(
            LeasingFinancieroProyeccionLinea.cotizacion_id == cotizacion.id
        )
    )

    monto_base = cotizacion.monto_financiado or cotizacion.valor_neto or cotizacion.monto
    if not monto_base or monto_base <= 0:
        db.flush()
        return

    principal = _q2(monto_base)
    seq = 0
    cuenta_cxc = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="ORIGINACION",
        codigo_evento="LEASING_FIN_ORIGINACION",
        lado="DEBE",
        orden=1,
        fallback=CUENTA_CXC,
    )
    cuenta_pasivo = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="ORIGINACION",
        codigo_evento="LEASING_FIN_ORIGINACION",
        lado="HABER",
        orden=1,
        fallback=CUENTA_PASIVO,
    )
    cuenta_banco = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="COBRO_CUOTA",
        codigo_evento="LEASING_FIN_COBRO_CUOTA",
        lado="DEBE",
        orden=1,
        fallback=CUENTA_BANCO,
    )
    cuenta_cxc_cobro = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="COBRO_CUOTA",
        codigo_evento="LEASING_FIN_COBRO_CUOTA",
        lado="HABER",
        orden=1,
        fallback=CUENTA_CXC,
    )
    cuenta_interes = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="COBRO_CUOTA",
        codigo_evento="LEASING_FIN_COBRO_CUOTA",
        lado="HABER",
        orden=2,
        fallback=CUENTA_INTERES,
    )

    def add_line(
        *,
        etapa: str,
        ref_cuota: int | None,
        glosa: str,
        cuenta: str,
        debe: Decimal,
        haber: Decimal,
    ) -> None:
        nonlocal seq
        seq += 1
        db.add(
            LeasingFinancieroProyeccionLinea(
                cotizacion_id=cotizacion.id,
                secuencia=seq,
                etapa=etapa,
                ref_cuota=ref_cuota,
                glosa=glosa,
                cuenta_codigo=cuenta,
                debe=_q2(debe),
                haber=_q2(haber),
            )
        )

    add_line(
        etapa="ORIGINACION",
        ref_cuota=None,
        glosa="Originación: reconocimiento CxC leasing",
        cuenta=cuenta_cxc,
        debe=principal,
        haber=Decimal("0"),
    )
    add_line(
        etapa="ORIGINACION",
        ref_cuota=None,
        glosa="Originación: contrapartida obligación leasing",
        cuenta=cuenta_pasivo,
        debe=Decimal("0"),
        haber=principal,
    )

    try:
        tabla = leasing_financiero.calcular_tabla_amortizacion(cotizacion)
    except ValueError:
        db.flush()
        return

    for cuota in tabla:
        if cuota.es_gracia and cuota.cuota == 0:
            continue
        if cuota.cuota <= 0 and not cuota.es_opcion_compra:
            continue

        total = _q2(cuota.cuota)
        cap = _q2(cuota.amortizacion)
        inter = _q2(cuota.interes)

        if cuota.es_opcion_compra:
            add_line(
                etapa="OPCION_COMPRA",
                ref_cuota=cuota.numero_cuota,
                glosa=f"Opción de compra cuota #{cuota.numero_cuota}",
                cuenta=cuenta_banco,
                debe=total,
                haber=Decimal("0"),
            )
            add_line(
                etapa="OPCION_COMPRA",
                ref_cuota=cuota.numero_cuota,
                glosa=f"Baja CxC por opción de compra #{cuota.numero_cuota}",
                cuenta=cuenta_cxc_cobro,
                debe=Decimal("0"),
                haber=total,
            )
            continue

        add_line(
            etapa="COBRO_CUOTA",
            ref_cuota=cuota.numero_cuota,
            glosa=f"Cobro proyectado cuota #{cuota.numero_cuota} (tesorería)",
            cuenta=cuenta_banco,
            debe=total,
            haber=Decimal("0"),
        )
        if cap > 0:
            add_line(
                etapa="COBRO_CUOTA",
                ref_cuota=cuota.numero_cuota,
                glosa=f"Amortización capital cuota #{cuota.numero_cuota}",
                cuenta=cuenta_cxc_cobro,
                debe=Decimal("0"),
                haber=cap,
            )
        if inter > 0:
            add_line(
                etapa="COBRO_CUOTA",
                ref_cuota=cuota.numero_cuota,
                glosa=f"Ingreso financiero intereses cuota #{cuota.numero_cuota}",
                cuenta=cuenta_interes,
                debe=Decimal("0"),
                haber=inter,
            )

    db.flush()
