# crud/remuneraciones_contabilidad.py
# -*- coding: utf-8 -*-
"""Asientos contables: provisión (devengo) y pago del líquido de nómina."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import settings
from crud.finanzas.contabilidad_asientos import crear_asiento
from crud.finanzas.plan_cuentas import obtener_plan_cuenta_por_codigo
from models.finanzas.plan_cuentas import PlanCuenta
from models.remuneraciones.models import DetalleRemuneracion, PeriodoRemuneracion

Q2 = Decimal("0.01")

_FALLBACK_SUELDOS_POR_PAGAR: tuple[str, ...] = ("210101", "210301", "210201")
_FALLBACK_BANCO: tuple[str, ...] = ("110201", "110101", "110301")
_FALLBACK_GASTO_SUELDOS: tuple[str, ...] = ("610104", "510101", "620101")


def _q(d: Decimal) -> Decimal:
    return d.quantize(Q2, rounding=ROUND_HALF_UP)


def _cuenta_por_codigos(
    db: Session,
    *,
    env_codigo: str,
    fallbacks: tuple[str, ...],
    ayuda: str,
) -> PlanCuenta:
    for raw in ((env_codigo or "").strip(),) + fallbacks:
        c = (raw or "").strip()
        if not c:
            continue
        cu = obtener_plan_cuenta_por_codigo(db, c)
        if cu and str(cu.estado).upper() == "ACTIVO" and cu.acepta_movimiento:
            return cu
    raise ValueError(
        f"Configure cuentas en fin.plan_cuenta o en .env: {ayuda} "
        f"(códigos probados: {', '.join(fallbacks[:5])}{'…' if len(fallbacks) > 5 else ''})."
    )


def contabilizar_provision_nomina_periodo(
    db: Session,
    periodo: PeriodoRemuneracion,
    *,
    usuario: str | None = None,
) -> int | None:
    """
    Devengo del costo de personal: Debe gasto (por centro de costo del detalle), Haber sueldos por pagar.
    Idempotente si ya existe asiento_provision_id.
    """
    if getattr(periodo, "asiento_provision_id", None):
        return int(periodo.asiento_provision_id)  # type: ignore[arg-type]

    detalles = list(
        db.scalars(
            select(DetalleRemuneracion).where(DetalleRemuneracion.periodo_remuneracion_id == periodo.id)
        ).all()
    )
    by_cc: defaultdict[int | None, Decimal] = defaultdict(lambda: Decimal("0"))
    for d in detalles:
        liq = _q(Decimal(str(d.liquido_a_pagar or 0)))
        if liq <= 0:
            continue
        by_cc[d.centro_costo_id] += liq

    total = _q(sum(by_cc.values(), start=Decimal("0")))
    if total <= 0:
        return None

    cuenta_gasto = _cuenta_por_codigos(
        db,
        env_codigo=settings.remuneracion_cuenta_gasto_sueldos,
        fallbacks=_FALLBACK_GASTO_SUELDOS,
        ayuda="REMUNERACION_CUENTA_GASTO_SUELDOS",
    )
    cuenta_pasivo = _cuenta_por_codigos(
        db,
        env_codigo=settings.remuneracion_cuenta_sueldos_por_pagar,
        fallbacks=_FALLBACK_SUELDOS_POR_PAGAR,
        ayuda="REMUNERACION_CUENTA_SUELDOS_POR_PAGAR",
    )

    label = f"{periodo.mes:02d}/{periodo.anio}"
    detalles_asiento: list[dict] = []
    for cc_id in sorted(by_cc.keys(), key=lambda x: (x is None, x or 0)):
        m = _q(by_cc[cc_id])
        if m <= 0:
            continue
        desc_cc = "sin centro de costo" if cc_id is None else f"CC {cc_id}"
        detalles_asiento.append(
            {
                "codigo_cuenta": cuenta_gasto.codigo,
                "descripcion": f"Devengo nómina {label} ({desc_cc})",
                "debe": m,
                "haber": Decimal("0"),
            }
        )
    detalles_asiento.append(
        {
            "codigo_cuenta": cuenta_pasivo.codigo,
            "descripcion": f"Devengo nómina {label} — sueldos por pagar",
            "debe": Decimal("0"),
            "haber": total,
        }
    )

    fecha_base: date | datetime = periodo.fecha_cierre or periodo.fecha_fin
    fecha_asiento = (
        datetime.combine(fecha_base, datetime.min.time())
        if isinstance(fecha_base, date) and not isinstance(fecha_base, datetime)
        else fecha_base
    )

    aid = crear_asiento(
        db,
        fecha=fecha_asiento,
        origen_tipo="REMUNERACION_PROVISION",
        origen_id=int(periodo.id),
        glosa=f"Provisión remuneraciones {label}",
        detalles=detalles_asiento,
        usuario=usuario,
        moneda="CLP",
        do_commit=False,
    )
    periodo.asiento_provision_id = aid  # type: ignore[assignment]
    return aid


def contabilizar_pago_nomina_periodo(
    db: Session,
    periodo: PeriodoRemuneracion,
    *,
    usuario: str | None = None,
) -> int | None:
    """
    Registra el pago agregado del periodo: Debe sueldos por pagar, Haber banco/caja.
    Idempotente si ya existe asiento_pago_id.
    """
    if getattr(periodo, "asiento_pago_id", None):
        return int(periodo.asiento_pago_id)  # type: ignore[arg-type]

    total = db.scalar(
        select(func.coalesce(func.sum(DetalleRemuneracion.liquido_a_pagar), 0)).where(
            DetalleRemuneracion.periodo_remuneracion_id == periodo.id
        )
    )
    m = _q(Decimal(str(total or 0)))
    if m <= 0:
        return None

    cuenta_pasivo = _cuenta_por_codigos(
        db,
        env_codigo=settings.remuneracion_cuenta_sueldos_por_pagar,
        fallbacks=_FALLBACK_SUELDOS_POR_PAGAR,
        ayuda="REMUNERACION_CUENTA_SUELDOS_POR_PAGAR",
    )
    cuenta_banco = _cuenta_por_codigos(
        db,
        env_codigo=settings.remuneracion_cuenta_banco,
        fallbacks=_FALLBACK_BANCO,
        ayuda="REMUNERACION_CUENTA_BANCO",
    )

    label = f"{periodo.mes:02d}/{periodo.anio}"
    detalles = [
        {
            "codigo_cuenta": cuenta_pasivo.codigo,
            "descripcion": f"Pago nómina {label} (reduce pasivo)",
            "debe": m,
            "haber": Decimal("0"),
        },
        {
            "codigo_cuenta": cuenta_banco.codigo,
            "descripcion": f"Pago nómina {label} salida banco",
            "debe": Decimal("0"),
            "haber": m,
        },
    ]

    fecha_asiento = periodo.fecha_pago or datetime.utcnow()
    aid = crear_asiento(
        db,
        fecha=fecha_asiento,
        origen_tipo="REMUNERACION_PAGO",
        origen_id=int(periodo.id),
        glosa=f"Pago remuneraciones {label}",
        detalles=detalles,
        usuario=usuario,
        moneda="CLP",
        do_commit=False,
    )
    periodo.asiento_pago_id = aid  # type: ignore[assignment]
    return aid
