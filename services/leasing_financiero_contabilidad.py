# services/leasing_financiero_contabilidad.py
# -*- coding: utf-8 -*-
"""Proyeccion contable automatica para leasing financiero."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from crud.finanzas.config_contable import obtener_configuracion_evento_modulo
from crud.finanzas.contabilidad_asientos import crear_asiento
from models.comercial.leasing_financiero_cotizacion import (
    LeasingFinancieroCotizacion,
    LeasingFinancieroProyeccionLinea,
)
from services import leasing_financiero

CUENTA_CXC = "113701"
CUENTA_PASIVO = "210701"
CUENTA_INTERES_DIFERIDO = "210702"
CUENTA_INTERES = "410701"
CUENTA_BANCO = "110201"


def _q2(v: Decimal | float | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _monto_base(cotizacion: "LeasingFinancieroCotizacion") -> Decimal | None:
    monto_base = cotizacion.monto_financiado or cotizacion.valor_neto or cotizacion.monto
    if monto_base is None:
        return None
    monto = _q2(monto_base)
    if monto <= 0:
        return None
    return monto


def _factor_moneda_a_clp(cotizacion: "LeasingFinancieroCotizacion") -> Decimal:
    moneda = str(getattr(cotizacion, "moneda", "CLP") or "CLP").strip().upper()
    if moneda == "CLP":
        return Decimal("1")
    if moneda == "USD":
        fx = getattr(cotizacion, "dolar_valor", None)
        if fx is None or Decimal(str(fx)) <= 0:
            raise ValueError(
                "La cotizacion en USD requiere 'dolar_valor' > 0 para generar proyeccion contable en CLP."
            )
        return Decimal(str(fx))
    if moneda == "UF":
        fx = getattr(cotizacion, "uf_valor", None)
        if fx is None or Decimal(str(fx)) <= 0:
            raise ValueError(
                "La cotizacion en UF requiere 'uf_valor' > 0 para generar proyeccion contable en CLP."
            )
        return Decimal(str(fx))
    raise ValueError(f"Moneda no soportada para proyeccion contable: {moneda}.")


def _a_clp(monto: Decimal, factor: Decimal) -> Decimal:
    return _q2(monto * factor)


def _totales_contractuales(
    cotizacion: "LeasingFinancieroCotizacion",
    tabla,
) -> dict[str, Decimal]:
    principal = _monto_base(cotizacion)
    if principal is None:
        raise ValueError("La cotizacion no tiene monto financiado valido.")

    cartera = _q2(sum((_q2(c.cuota) for c in tabla), Decimal("0")))
    intereses_tabla = _q2(sum((_q2(c.interes) for c in tabla), Decimal("0")))
    intereses_por_diferir = _q2(cartera - principal)

    if intereses_por_diferir < 0:
        intereses_por_diferir = Decimal("0.00")

    return {
        "cartera": cartera,
        "principal": principal,
        "interes": intereses_por_diferir,
        "interes_tabla": intereses_tabla,
        "opcion": _q2(sum((_q2(c.cuota) for c in tabla if c.es_opcion_compra), Decimal("0"))),
        "rentas": _q2(
            sum(
                (
                    _q2(c.cuota)
                    for c in tabla
                    if not c.es_gracia and not c.es_opcion_compra
                ),
                Decimal("0"),
            )
        ),
    }


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
    """Elimina lineas previas y genera originacion + cobros proyectados por cuota."""
    db.execute(
        delete(LeasingFinancieroProyeccionLinea).where(
            LeasingFinancieroProyeccionLinea.cotizacion_id == cotizacion.id
        )
    )

    if _monto_base(cotizacion) is None:
        db.flush()
        return

    try:
        tabla = leasing_financiero.calcular_tabla_amortizacion(cotizacion)
    except ValueError:
        db.flush()
        return

    factor_clp = _factor_moneda_a_clp(cotizacion)
    totales = _totales_contractuales(cotizacion, tabla)
    cartera_clp = _a_clp(totales["cartera"], factor_clp)
    principal_clp = _a_clp(totales["principal"], factor_clp)
    interes_diferido_clp = _a_clp(totales["interes"], factor_clp)

    if cartera_clp <= 0:
        db.flush()
        return

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
    cuenta_interes_diferido_originacion = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="ORIGINACION",
        codigo_evento="LEASING_FIN_ORIGINACION",
        lado="HABER",
        orden=2,
        fallback=CUENTA_INTERES_DIFERIDO,
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
    cuenta_interes_diferido_cobro = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="COBRO_CUOTA",
        codigo_evento="LEASING_FIN_COBRO_CUOTA",
        lado="DEBE",
        orden=2,
        fallback=CUENTA_INTERES_DIFERIDO,
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
        glosa="Originacion: cartera contractual bruta leasing",
        cuenta=cuenta_cxc,
        debe=cartera_clp,
        haber=Decimal("0"),
    )
    add_line(
        etapa="ORIGINACION",
        ref_cuota=None,
        glosa="Originacion: capital financiado leasing",
        cuenta=cuenta_pasivo,
        debe=Decimal("0"),
        haber=principal_clp,
    )
    if interes_diferido_clp > 0:
        add_line(
            etapa="ORIGINACION",
            ref_cuota=None,
            glosa="Originacion: intereses financieros diferidos leasing",
            cuenta=cuenta_interes_diferido_originacion,
            debe=Decimal("0"),
            haber=interes_diferido_clp,
        )

    interest_indexes = [
        idx
        for idx, cuota in enumerate(tabla)
        if _a_clp(_q2(cuota.interes), factor_clp) > 0
    ]
    last_interest_idx = interest_indexes[-1] if interest_indexes else None
    interes_pendiente_clp = interes_diferido_clp

    for idx, cuota in enumerate(tabla):
        total = _q2(cuota.cuota)
        inter_clp = _a_clp(_q2(cuota.interes), factor_clp)
        if inter_clp > 0:
            if idx == last_interest_idx:
                inter_clp = interes_pendiente_clp
            else:
                inter_clp = min(inter_clp, interes_pendiente_clp)
            interes_pendiente_clp = _q2(interes_pendiente_clp - inter_clp)

        if cuota.es_gracia and total == 0:
            if inter_clp > 0:
                add_line(
                    etapa="DEVENGO_GRACIA",
                    ref_cuota=cuota.numero_cuota,
                    glosa=f"Devengo intereses periodo de gracia #{cuota.numero_cuota}",
                    cuenta=cuenta_interes_diferido_cobro,
                    debe=inter_clp,
                    haber=Decimal("0"),
                )
                add_line(
                    etapa="DEVENGO_GRACIA",
                    ref_cuota=cuota.numero_cuota,
                    glosa=f"Ingreso financiero periodo de gracia #{cuota.numero_cuota}",
                    cuenta=cuenta_interes,
                    debe=Decimal("0"),
                    haber=inter_clp,
                )
            continue

        if total <= 0 and not cuota.es_opcion_compra:
            continue

        total_clp = _a_clp(total, factor_clp)

        if cuota.es_opcion_compra:
            add_line(
                etapa="OPCION_COMPRA",
                ref_cuota=cuota.numero_cuota,
                glosa=f"Opcion de compra cuota #{cuota.numero_cuota}",
                cuenta=cuenta_banco,
                debe=total_clp,
                haber=Decimal("0"),
            )
            add_line(
                etapa="OPCION_COMPRA",
                ref_cuota=cuota.numero_cuota,
                glosa=f"Baja CxC contractual opcion de compra #{cuota.numero_cuota}",
                cuenta=cuenta_cxc_cobro,
                debe=Decimal("0"),
                haber=total_clp,
            )
            continue

        add_line(
            etapa="COBRO_CUOTA",
            ref_cuota=cuota.numero_cuota,
            glosa=f"Cobro proyectado cuota #{cuota.numero_cuota} (tesoreria)",
            cuenta=cuenta_banco,
            debe=total_clp,
            haber=Decimal("0"),
        )
        add_line(
            etapa="COBRO_CUOTA",
            ref_cuota=cuota.numero_cuota,
            glosa=f"Baja CxC contractual cuota #{cuota.numero_cuota}",
            cuenta=cuenta_cxc_cobro,
            debe=Decimal("0"),
            haber=total_clp,
        )
        if inter_clp > 0:
            add_line(
                etapa="COBRO_CUOTA",
                ref_cuota=cuota.numero_cuota,
                glosa=f"Liberacion intereses diferidos cuota #{cuota.numero_cuota}",
                cuenta=cuenta_interes_diferido_cobro,
                debe=inter_clp,
                haber=Decimal("0"),
            )
            add_line(
                etapa="COBRO_CUOTA",
                ref_cuota=cuota.numero_cuota,
                glosa=f"Ingreso financiero intereses cuota #{cuota.numero_cuota}",
                cuenta=cuenta_interes,
                debe=Decimal("0"),
                haber=inter_clp,
            )

    db.flush()


def activar_contabilidad_leasing_financiero(
    db: Session,
    cotizacion: LeasingFinancieroCotizacion,
    *,
    usuario: str | None = None,
) -> int:
    row = db.execute(
        text(
            """
            SELECT id
            FROM asientos_contables
            WHERE origen_tipo = 'LEASING_FIN_ACTIVACION'
              AND origen_id = :oid
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"oid": int(cotizacion.id)},
    ).first()
    if row:
        return int(row[0])

    if _monto_base(cotizacion) is None:
        raise ValueError("La cotizacion no tiene monto financiado valido para activar contabilidad.")

    try:
        tabla = leasing_financiero.calcular_tabla_amortizacion(cotizacion)
    except ValueError as exc:
        raise ValueError(f"No se pudo calcular la cartera contractual del leasing: {exc}") from exc

    factor_clp = _factor_moneda_a_clp(cotizacion)
    totales = _totales_contractuales(cotizacion, tabla)
    cartera_clp = _a_clp(totales["cartera"], factor_clp)
    principal_clp = _a_clp(totales["principal"], factor_clp)
    interes_diferido_clp = _a_clp(totales["interes"], factor_clp)

    debe = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="ORIGINACION",
        codigo_evento="LEASING_FIN_ORIGINACION",
        lado="DEBE",
        orden=1,
        fallback=CUENTA_CXC,
    )
    haber_principal = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="ORIGINACION",
        codigo_evento="LEASING_FIN_ORIGINACION",
        lado="HABER",
        orden=1,
        fallback=CUENTA_PASIVO,
    )
    haber_interes_diferido = _cuenta_desde_config(
        db,
        submodulo="LEASING_FIN",
        tipo_documento="ORIGINACION",
        codigo_evento="LEASING_FIN_ORIGINACION",
        lado="HABER",
        orden=2,
        fallback=CUENTA_INTERES_DIFERIDO,
    )

    detalles = [
        {
            "codigo_cuenta": debe,
            "descripcion": f"Activacion LF cartera contractual cotizacion {cotizacion.id}",
            "debe": cartera_clp,
            "haber": Decimal("0"),
        },
        {
            "codigo_cuenta": haber_principal,
            "descripcion": f"Activacion LF capital financiado cotizacion {cotizacion.id}",
            "debe": Decimal("0"),
            "haber": principal_clp,
        },
    ]
    if interes_diferido_clp > 0:
        detalles.append(
            {
                "codigo_cuenta": haber_interes_diferido,
                "descripcion": f"Activacion LF intereses diferidos cotizacion {cotizacion.id}",
                "debe": Decimal("0"),
                "haber": interes_diferido_clp,
            }
        )

    return crear_asiento(
        db,
        fecha=cotizacion.fecha_inicio or cotizacion.fecha_cotizacion or date.today(),
        origen_tipo="LEASING_FIN_ACTIVACION",
        origen_id=int(cotizacion.id),
        glosa=f"Activacion leasing financiero cotizacion {cotizacion.id}",
        detalles=detalles,
        usuario=usuario,
        moneda="CLP",
        do_commit=False,
    )
