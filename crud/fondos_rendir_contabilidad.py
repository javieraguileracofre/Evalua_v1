# crud/fondos_rendir_contabilidad.py
# -*- coding: utf-8 -*-
"""Asientos contables para anticipos y liquidación de fondos por rendir."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.config import settings
from crud.finanzas.contabilidad_asientos import crear_asiento
from crud.finanzas.plan_cuentas import obtener_plan_cuenta_por_codigo
from models.finanzas.plan_cuentas import PlanCuenta
from models.fondos_rendir.fondo_rendir import FondoRendir

Q2 = Decimal("0.01")

# Si .env está vacío, se prueban códigos frecuentes en planillas chilenas (deben existir en fin.plan_cuenta).
_FALLBACK_ANTICIPO: tuple[str, ...] = (
    "1.1.05",
    "1.1.04",
    "1.01.05",
    "1.1.03",
    "1.05.01",
)
_FALLBACK_CAJA: tuple[str, ...] = (
    "1.1.01",
    "1.01.01",
    "1.1.02",
    "1.02.01",
    "1.1.00",
)
_FALLBACK_GASTO: tuple[str, ...] = (
    "6.1.01",
    "4.1.01",
    "5.1.01",
    "6.2.01",
    "6.1.02",
    "6.3.01",
)


def _q(d: Decimal) -> Decimal:
    return d.quantize(Q2, rounding=ROUND_HALF_UP)


def _buscar_cuenta_por_palabras_nombre(db: Session, palabras: tuple[str, ...]) -> PlanCuenta | None:
    """Último recurso: primera cuenta activa cuyo nombre contenga alguna palabra clave."""
    conds = [PlanCuenta.nombre.ilike(f"%{p}%") for p in palabras]
    stmt = (
        select(PlanCuenta)
        .where(or_(*conds))
        .where(func.upper(PlanCuenta.estado) == "ACTIVO")
        .where(PlanCuenta.acepta_movimiento.is_(True))
        .order_by(PlanCuenta.codigo)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _normalizar_codigo(codigo: str) -> str:
    """Quita separadores para comparar códigos contables equivalentes."""
    return re.sub(r"[^0-9A-Za-z]", "", (codigo or "").strip()).upper()


def _buscar_cuenta_por_codigo_tolerante(db: Session, codigo: str) -> PlanCuenta | None:
    """Resuelve código exacto o equivalente (ej. 11.05 == 1.1.05)."""
    exacta = obtener_plan_cuenta_por_codigo(db, codigo)
    if exacta:
        return exacta
    codigo_norm = _normalizar_codigo(codigo)
    if not codigo_norm:
        return None
    stmt = select(PlanCuenta).where(func.upper(PlanCuenta.estado) == "ACTIVO")
    for cu in db.execute(stmt).scalars():
        if _normalizar_codigo(str(cu.codigo or "")) == codigo_norm:
            return cu
    return None


def _resolver_cuenta(
    db: Session,
    *,
    rol: str,
    env_var: str,
    valor_env: str,
    fallbacks_codigo: tuple[str, ...],
    palabras_nombre: tuple[str, ...] | None = None,
) -> PlanCuenta:
    """
    Orden: variable .env → códigos fallback → búsqueda por nombre (opcional).
    """
    probados: list[str] = []
    for raw in ((valor_env.strip(),) if (valor_env or "").strip() else ()) + fallbacks_codigo:
        c = (raw or "").strip()
        if not c or c in probados:
            continue
        probados.append(c)
        cu = _buscar_cuenta_por_codigo_tolerante(db, c)
        if cu and str(cu.estado).upper() == "ACTIVO" and cu.acepta_movimiento:
            return cu

    if palabras_nombre:
        cu = _buscar_cuenta_por_palabras_nombre(db, palabras_nombre)
        if cu:
            return cu

    raise ValueError(
        f"No hay cuenta contable usable para «{rol}». "
        f"Cree una cuenta en fin.plan_cuenta (ACTIVO, acepta movimiento) o defina en .env: "
        f"{env_var}=<código exacto del plan>. "
        f"Códigos probados automáticamente: {', '.join(probados) or '(ninguno)'}. "
        "Si su plan usa otros números, la variable .env es obligatoria."
    )


def contabilizar_entrega_anticipo(
    db: Session,
    fondo: FondoRendir,
    *,
    usuario: str | None = None,
) -> int | None:
    """
    Entrega de efectivo / fondo al trabajador:
    Debe fondos por rendir (anticipo), Haber caja.
    """
    if getattr(fondo, "asiento_id_entrega", None):
        return int(fondo.asiento_id_entrega)  # type: ignore[arg-type]

    cuenta_anticipo = _resolver_cuenta(
        db,
        rol="Anticipo / fondos por rendir (activo)",
        env_var="FONDO_RENDIR_CUENTA_ANTICIPO",
        valor_env=settings.fondo_rendir_cuenta_anticipo,
        fallbacks_codigo=_FALLBACK_ANTICIPO,
        palabras_nombre=("ANTICIPO", "RENDIR", "FONDO"),
    )
    cuenta_caja = _resolver_cuenta(
        db,
        rol="Caja o equivalente",
        env_var="FONDO_RENDIR_CUENTA_CAJA",
        valor_env=settings.fondo_rendir_cuenta_caja,
        fallbacks_codigo=_FALLBACK_CAJA,
        palabras_nombre=("CAJA", "EFECTIVO"),
    )

    m = _q(Decimal(fondo.monto_anticipo))
    if m <= 0:
        raise ValueError("El monto del anticipo debe ser mayor a cero.")

    detalles = [
        {
            "codigo_cuenta": cuenta_anticipo.codigo,
            "descripcion": f"Anticipo {fondo.folio}",
            "debe": m,
            "haber": Decimal("0"),
        },
        {
            "codigo_cuenta": cuenta_caja.codigo,
            "descripcion": f"Salida caja anticipo {fondo.folio}",
            "debe": Decimal("0"),
            "haber": m,
        },
    ]

    aid = crear_asiento(
        db,
        fecha=fondo.fecha_entrega,
        origen_tipo="FONDO_RENDIR_ENT",
        origen_id=int(fondo.id),
        glosa=f"Entrega anticipo {fondo.folio}",
        detalles=detalles,
        usuario=usuario,
        moneda="CLP",
        do_commit=False,
    )
    fondo.asiento_id_entrega = aid  # type: ignore[assignment]
    return aid


def contabilizar_liquidacion_rendicion(
    db: Session,
    fondo: FondoRendir,
    *,
    usuario: str | None = None,
) -> int | None:
    """
    Cierra el anticipo contra gastos y caja:
    - Debe gastos (por rubro) + posible ingreso caja (vueltos si gastos < anticipo)
    - Haber anticipo + posible salida caja si gastos > anticipo
    """
    if getattr(fondo, "asiento_id_liquidacion", None):
        return int(fondo.asiento_id_liquidacion)  # type: ignore[arg-type]

    cuenta_anticipo = _resolver_cuenta(
        db,
        rol="Anticipo / fondos por rendir (activo)",
        env_var="FONDO_RENDIR_CUENTA_ANTICIPO",
        valor_env=settings.fondo_rendir_cuenta_anticipo,
        fallbacks_codigo=_FALLBACK_ANTICIPO,
        palabras_nombre=("ANTICIPO", "RENDIR", "FONDO"),
    )
    cuenta_caja = _resolver_cuenta(
        db,
        rol="Caja o equivalente",
        env_var="FONDO_RENDIR_CUENTA_CAJA",
        valor_env=settings.fondo_rendir_cuenta_caja,
        fallbacks_codigo=_FALLBACK_CAJA,
        palabras_nombre=("CAJA", "EFECTIVO"),
    )
    cuenta_gasto = _resolver_cuenta(
        db,
        rol="Gasto operacional / transporte",
        env_var="FONDO_RENDIR_CUENTA_GASTO",
        valor_env=settings.fondo_rendir_cuenta_gasto,
        fallbacks_codigo=_FALLBACK_GASTO,
        palabras_nombre=("GASTO", "TRANSPORTE", "OPERACION"),
    )

    m = _q(Decimal(fondo.monto_anticipo))
    agg: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for L in fondo.lineas_gasto:
        agg[L.rubro] += _q(Decimal(L.monto))
    g = _q(sum(agg.values(), start=Decimal("0")))

    if m <= 0:
        raise ValueError("El monto del anticipo debe ser mayor a cero para liquidar.")

    detalles: list[dict] = []

    for rubro, monto in sorted(agg.items(), key=lambda x: x[0]):
        mo = _q(monto)
        if mo > 0:
            detalles.append(
                {
                    "codigo_cuenta": cuenta_gasto.codigo,
                    "descripcion": f"{rubro} — {fondo.folio}",
                    "debe": mo,
                    "haber": Decimal("0"),
                }
            )

    if g == Decimal("0"):
        detalles.append(
            {
                "codigo_cuenta": cuenta_caja.codigo,
                "descripcion": f"Devolución anticipo {fondo.folio}",
                "debe": m,
                "haber": Decimal("0"),
            }
        )
        detalles.append(
            {
                "codigo_cuenta": cuenta_anticipo.codigo,
                "descripcion": f"Cierra anticipo sin gastos {fondo.folio}",
                "debe": Decimal("0"),
                "haber": m,
            }
        )
    elif g <= m:
        if m > g:
            detalles.append(
                {
                    "codigo_cuenta": cuenta_caja.codigo,
                    "descripcion": f"Vueltos anticipo {fondo.folio}",
                    "debe": _q(m - g),
                    "haber": Decimal("0"),
                }
            )
        detalles.append(
            {
                "codigo_cuenta": cuenta_anticipo.codigo,
                "descripcion": f"Liquida anticipo {fondo.folio}",
                "debe": Decimal("0"),
                "haber": m,
            }
        )
    else:
        faltante = _q(g - m)
        detalles.append(
            {
                "codigo_cuenta": cuenta_anticipo.codigo,
                "descripcion": f"Liquida anticipo {fondo.folio}",
                "debe": Decimal("0"),
                "haber": m,
            }
        )
        detalles.append(
            {
                "codigo_cuenta": cuenta_caja.codigo,
                "descripcion": f"Pago diferencia gastos vs anticipo {fondo.folio}",
                "debe": Decimal("0"),
                "haber": faltante,
            }
        )

    fecha_liq = fondo.fecha_aprobacion or datetime.utcnow()

    aid = crear_asiento(
        db,
        fecha=fecha_liq,
        origen_tipo="FONDO_RENDIR_LIQ",
        origen_id=int(fondo.id),
        glosa=f"Liquidación rendición {fondo.folio}",
        detalles=detalles,
        usuario=usuario,
        moneda="CLP",
        do_commit=False,
    )
    fondo.asiento_id_liquidacion = aid  # type: ignore[assignment]
    return aid


def diagnostico_cuentas_fondos_rendir(db: Session) -> dict[str, dict[str, str]]:
    """
    Verifica resolución de cuentas críticas de fondos por rendir y retorna
    el detalle para diagnóstico operacional.
    """
    cuenta_anticipo = _resolver_cuenta(
        db,
        rol="Anticipo / fondos por rendir (activo)",
        env_var="FONDO_RENDIR_CUENTA_ANTICIPO",
        valor_env=settings.fondo_rendir_cuenta_anticipo,
        fallbacks_codigo=_FALLBACK_ANTICIPO,
        palabras_nombre=("ANTICIPO", "RENDIR", "FONDO"),
    )
    cuenta_caja = _resolver_cuenta(
        db,
        rol="Caja o equivalente",
        env_var="FONDO_RENDIR_CUENTA_CAJA",
        valor_env=settings.fondo_rendir_cuenta_caja,
        fallbacks_codigo=_FALLBACK_CAJA,
        palabras_nombre=("CAJA", "EFECTIVO"),
    )
    cuenta_gasto = _resolver_cuenta(
        db,
        rol="Gasto operacional / transporte",
        env_var="FONDO_RENDIR_CUENTA_GASTO",
        valor_env=settings.fondo_rendir_cuenta_gasto,
        fallbacks_codigo=_FALLBACK_GASTO,
        palabras_nombre=("GASTO", "TRANSPORTE", "OPERACION"),
    )
    return {
        "anticipo": {
            "codigo": str(cuenta_anticipo.codigo),
            "nombre": str(cuenta_anticipo.nombre),
        },
        "caja": {
            "codigo": str(cuenta_caja.codigo),
            "nombre": str(cuenta_caja.nombre),
        },
        "gasto": {
            "codigo": str(cuenta_gasto.codigo),
            "nombre": str(cuenta_gasto.nombre),
        },
    }
