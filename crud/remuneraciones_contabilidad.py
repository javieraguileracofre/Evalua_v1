# crud/remuneraciones_contabilidad.py
# -*- coding: utf-8 -*-
"""Asiento contable al marcar periodo de remuneración como pagado (pago del líquido)."""
from __future__ import annotations

from datetime import datetime
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


def _q(d: Decimal) -> Decimal:
    return d.quantize(Q2, rounding=ROUND_HALF_UP)


def _cuenta_por_codigos(db: Session, *, env_codigo: str, fallbacks: tuple[str, ...]) -> PlanCuenta:
    for raw in ((env_codigo or "").strip(),) + fallbacks:
        c = (raw or "").strip()
        if not c:
            continue
        cu = obtener_plan_cuenta_por_codigo(db, c)
        if cu and str(cu.estado).upper() == "ACTIVO" and cu.acepta_movimiento:
            return cu
    raise ValueError(
        "Configure cuentas en fin.plan_cuenta o en .env: "
        "REMUNERACION_CUENTA_SUELDOS_POR_PAGAR y REMUNERACION_CUENTA_BANCO "
        f"(códigos probados: sueldos {', '.join(_FALLBACK_SUELDOS_POR_PAGAR)}, banco {', '.join(_FALLBACK_BANCO)})."
    )


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
    )
    cuenta_banco = _cuenta_por_codigos(
        db,
        env_codigo=settings.remuneracion_cuenta_banco,
        fallbacks=_FALLBACK_BANCO,
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
