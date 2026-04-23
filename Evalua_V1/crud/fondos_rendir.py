# crud/fondos_rendir.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, selectinload

from crud.finanzas.contabilidad_asientos import eliminar_asiento_contable
from models.fondos_rendir.empleado import Empleado
from models.fondos_rendir.fondo_rendir import FondoRendir, FondoRendirGasto
from models.fondos_rendir.vehiculo_transporte import VehiculoTransporte

Q2 = Decimal("0.01")

_MESES_CORTO = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


def _months_span(n: int) -> list[tuple[int, int]]:
    """Últimos n meses calendario (año, mes), orden cronológico."""
    now = datetime.utcnow()
    y, m = now.year, now.month
    for _ in range(n - 1):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    keys: list[tuple[int, int]] = []
    for _ in range(n):
        keys.append((y, m))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return keys


RUBROS_GASTO: tuple[str, ...] = (
    "Combustible",
    "Peaje / TAG",
    "Estacionamiento",
    "Alimentación",
    "Mantenimiento menor",
    "Otros",
)


def _d(v: Any) -> Decimal:
    if v is None:
        return Decimal("0.00")
    if isinstance(v, Decimal):
        return v.quantize(Q2, rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(v).strip().replace(",", ".")).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def _parse_dt(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip().replace("T", " ")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[: len(fmt)], fmt)
        except ValueError:
            continue
    return None


def parse_fecha_formulario(value: str | None) -> datetime | None:
    """Expuesto para rutas UI."""
    return _parse_dt(value)


def normalizar_rut(rut: str) -> str:
    s = rut.strip().upper().replace(".", "").replace(" ", "")
    return s


def rut_valido_basico(rut: str) -> bool:
    """Validación liviana: dígitos + dígito verificador."""
    if not rut or len(rut) < 7:
        return False
    return bool(re.match(r"^[0-9]+-[0-9Kk]$", rut))


def siguiente_folio(db: Session) -> str:
    y = datetime.utcnow().year
    pref = f"FR-{y}-"
    # Evita colisiones por concurrencia: serializa el cálculo por año usando
    # un lock transaccional de PostgreSQL.
    lock_key = f"fondos_rendir_folio_{y}"
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": lock_key},
    )
    siguiente = int(
        db.execute(
            text(
                """
                SELECT COALESCE(
                    MAX(
                        CASE
                            WHEN folio ~ :re_folio THEN (regexp_match(folio, :re_folio))[1]::int
                            ELSE NULL
                        END
                    ),
                    0
                ) + 1
                FROM fondos_rendir
                WHERE folio LIKE :pref_like
                """
            ),
            {
                "re_folio": rf"^FR-{y}-(\d+)$",
                "pref_like": f"{pref}%",
            },
        ).scalar_one()
        or 1
    )
    return f"{pref}{siguiente:05d}"


# --- Empleados ---


def listar_empleados(db: Session, *, solo_activos: bool = True) -> list[Empleado]:
    q = select(Empleado).order_by(Empleado.nombre_completo)
    if solo_activos:
        q = q.where(Empleado.activo.is_(True))
    return list(db.scalars(q).all())


def obtener_empleado(db: Session, empleado_id: int) -> Empleado | None:
    return db.get(Empleado, empleado_id)


def crear_empleado(
    db: Session,
    *,
    rut: str,
    nombre_completo: str,
    cargo: str | None = None,
    email: str | None = None,
    telefono: str | None = None,
) -> Empleado:
    r = normalizar_rut(rut)
    if not rut_valido_basico(r):
        raise ValueError("RUT con formato inválido (use 12345678-9 o 12345678-K).")
    if db.scalar(select(Empleado.id).where(Empleado.rut == r)):
        raise ValueError("Ya existe un empleado con ese RUT.")
    e = Empleado(
        rut=r,
        nombre_completo=nombre_completo.strip(),
        cargo=(cargo or "").strip() or None,
        email=(email or "").strip() or None,
        telefono=(telefono or "").strip() or None,
        activo=True,
    )
    db.add(e)
    db.flush()
    return e


def actualizar_empleado(
    db: Session,
    empleado_id: int,
    *,
    rut: str,
    nombre_completo: str,
    cargo: str | None,
    email: str | None,
    telefono: str | None,
    activo: bool,
) -> Empleado:
    e = db.get(Empleado, empleado_id)
    if not e:
        raise ValueError("Empleado no encontrado.")
    r = normalizar_rut(rut)
    if not rut_valido_basico(r):
        raise ValueError("RUT con formato inválido.")
    otro = db.scalar(select(Empleado.id).where(Empleado.rut == r, Empleado.id != empleado_id))
    if otro:
        raise ValueError("Otro empleado ya usa ese RUT.")
    e.rut = r
    e.nombre_completo = nombre_completo.strip()
    e.cargo = (cargo or "").strip() or None
    e.email = (email or "").strip() or None
    e.telefono = (telefono or "").strip() or None
    e.activo = activo
    return e


# --- Vehículos flota ---


def listar_vehiculos_transporte(db: Session, *, solo_activos: bool = True) -> list[VehiculoTransporte]:
    q = select(VehiculoTransporte).order_by(VehiculoTransporte.patente)
    if solo_activos:
        q = q.where(VehiculoTransporte.activo.is_(True))
    return list(db.scalars(q).all())


def obtener_vehiculo(db: Session, vid: int) -> VehiculoTransporte | None:
    return db.get(VehiculoTransporte, vid)


def crear_vehiculo_transporte(
    db: Session,
    *,
    patente: str,
    marca: str,
    modelo: str,
    anio: int | None = None,
    observaciones: str | None = None,
    consumo_referencial_l100km: Decimal | None = None,
) -> VehiculoTransporte:
    p = patente.strip().upper()
    if len(p) < 5:
        raise ValueError("Patente inválida.")
    if db.scalar(select(VehiculoTransporte.id).where(VehiculoTransporte.patente == p)):
        raise ValueError("Ya existe ese vehículo de flota.")
    v = VehiculoTransporte(
        patente=p,
        marca=marca.strip(),
        modelo=modelo.strip(),
        anio=anio,
        observaciones=(observaciones or "").strip() or None,
        consumo_referencial_l100km=consumo_referencial_l100km,
        activo=True,
    )
    db.add(v)
    db.flush()
    return v


def actualizar_vehiculo_transporte(
    db: Session,
    vid: int,
    *,
    patente: str,
    marca: str,
    modelo: str,
    anio: int | None,
    observaciones: str | None,
    activo: bool,
    consumo_referencial_l100km: Decimal | None = None,
) -> VehiculoTransporte:
    v = db.get(VehiculoTransporte, vid)
    if not v:
        raise ValueError("Vehículo no encontrado.")
    p = patente.strip().upper()
    otro = db.scalar(
        select(VehiculoTransporte.id).where(
            VehiculoTransporte.patente == p,
            VehiculoTransporte.id != vid,
        )
    )
    if otro:
        raise ValueError("Otro vehículo ya tiene esa patente.")
    v.patente = p
    v.marca = marca.strip()
    v.modelo = modelo.strip()
    v.anio = anio
    v.observaciones = (observaciones or "").strip() or None
    v.activo = activo
    v.consumo_referencial_l100km = consumo_referencial_l100km
    return v


# --- Gastos JSON ---


def parse_gastos_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("El detalle de gastos no es JSON válido.") from e
    if not isinstance(data, list):
        raise ValueError("Los gastos deben ser una lista.")
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            continue
        rubro = str(row.get("rubro") or "").strip()
        desc = str(row.get("descripcion") or "").strip() or None
        monto = _d(row.get("monto", 0))
        if monto <= 0 and not rubro and not desc:
            continue
        fg = _parse_dt(str(row.get("fecha_gasto") or "")[:16]) or datetime.utcnow()
        out.append(
            {
                "linea": idx,
                "fecha_gasto": fg,
                "rubro": rubro or "Otros",
                "descripcion": desc,
                "monto": monto,
                "nro_documento": str(row.get("nro_documento") or "").strip() or None,
            }
        )
    return out


def sync_gastos_lineas(db: Session, fondo_id: int, rows: list[dict[str, Any]]) -> None:
    db.execute(delete(FondoRendirGasto).where(FondoRendirGasto.fondo_id == fondo_id))
    for i, r in enumerate(rows, start=1):
        db.add(
            FondoRendirGasto(
                fondo_id=fondo_id,
                linea=i,
                fecha_gasto=r["fecha_gasto"],
                rubro=r["rubro"][:80],
                descripcion=r.get("descripcion"),
                monto=r["monto"],
                nro_documento=r.get("nro_documento"),
            )
        )


def total_gastos_orm(lineas: list[FondoRendirGasto]) -> Decimal:
    t = Decimal("0.00")
    for L in lineas:
        t += _d(L.monto)
    return t.quantize(Q2, rounding=ROUND_HALF_UP)


# --- Fondos ---


def obtener_fondo(db: Session, fondo_id: int) -> FondoRendir | None:
    return db.scalars(
        select(FondoRendir)
        .options(
            selectinload(FondoRendir.empleado),
            selectinload(FondoRendir.vehiculo),
            selectinload(FondoRendir.lineas_gasto),
        )
        .where(FondoRendir.id == fondo_id)
    ).first()


def listar_fondos(db: Session, *, limite: int = 200) -> list[FondoRendir]:
    return list(
        db.scalars(
            select(FondoRendir)
            .options(
                selectinload(FondoRendir.empleado),
                selectinload(FondoRendir.vehiculo),
            )
            .order_by(FondoRendir.fecha_entrega.desc(), FondoRendir.id.desc())
            .limit(limite)
        ).all()
    )


def crear_fondo(
    db: Session,
    *,
    empleado_id: int,
    vehiculo_transporte_id: int | None,
    monto_anticipo: Decimal,
    fecha_entrega: datetime,
    observaciones: str | None,
) -> FondoRendir:
    if not db.get(Empleado, empleado_id):
        raise ValueError("Empleado no existe.")
    if vehiculo_transporte_id and not db.get(VehiculoTransporte, vehiculo_transporte_id):
        raise ValueError("Vehículo no existe.")
    if monto_anticipo <= 0:
        raise ValueError("El monto del anticipo debe ser mayor a cero.")
    f = FondoRendir(
        folio=siguiente_folio(db),
        empleado_id=empleado_id,
        vehiculo_transporte_id=vehiculo_transporte_id,
        monto_anticipo=monto_anticipo.quantize(Q2, rounding=ROUND_HALF_UP),
        fecha_entrega=fecha_entrega,
        estado="ABIERTO",
        observaciones=(observaciones or "").strip() or None,
    )
    db.add(f)
    db.flush()
    return f


def dashboard_stats(db: Session) -> dict[str, Any]:
    """KPIs para panel de control."""
    hoy = datetime.utcnow().date()

    n_abiertos = db.scalar(
        select(func.count()).select_from(FondoRendir).where(FondoRendir.estado == "ABIERTO")
    ) or 0
    n_pend_apr = db.scalar(
        select(func.count())
        .select_from(FondoRendir)
        .where(FondoRendir.estado == "PENDIENTE_APROBACION")
    ) or 0

    sum_abiertos = db.scalar(
        select(func.coalesce(func.sum(FondoRendir.monto_anticipo), 0))
        .select_from(FondoRendir)
        .where(FondoRendir.estado == "ABIERTO")
    )
    sum_pend = db.scalar(
        select(func.coalesce(func.sum(FondoRendir.monto_anticipo), 0))
        .select_from(FondoRendir)
        .where(FondoRendir.estado == "PENDIENTE_APROBACION")
    )

    # Fondos ABIERTO con días desde entrega (alerta rendición)
    abiertos = list(
        db.scalars(
            select(FondoRendir)
            .options(selectinload(FondoRendir.empleado))
            .where(FondoRendir.estado == "ABIERTO")
            .order_by(FondoRendir.fecha_entrega.asc())
        ).all()
    )
    alertas: list[dict[str, Any]] = []
    for f in abiertos:
        d = (hoy - f.fecha_entrega.date()).days
        alertas.append(
            {
                "fondo_id": f.id,
                "folio": f.folio,
                "empleado": f.empleado.nombre_completo if f.empleado else "",
                "dias": d,
                "monto": f.monto_anticipo,
            }
        )

    n_total = db.scalar(select(func.count()).select_from(FondoRendir)) or 0
    monto_total = db.scalar(
        select(func.coalesce(func.sum(FondoRendir.monto_anticipo), 0)).select_from(FondoRendir)
    )

    estados_cfg: tuple[tuple[str, str], ...] = (
        ("ABIERTO", "Abierto"),
        ("PENDIENTE_APROBACION", "Pendiente"),
        ("APROBADO", "Aprobado"),
        ("RECHAZADO", "Rechazado"),
    )
    estado_labels: list[str] = []
    estado_montos: list[float] = []
    estado_counts: list[int] = []
    for code, label in estados_cfg:
        estado_labels.append(label)
        n_e = (
            db.scalar(
                select(func.count()).select_from(FondoRendir).where(FondoRendir.estado == code)
            )
            or 0
        )
        estado_counts.append(int(n_e))
        sm = db.scalar(
            select(func.coalesce(func.sum(FondoRendir.monto_anticipo), 0))
            .select_from(FondoRendir)
            .where(FondoRendir.estado == code)
        )
        estado_montos.append(float(_d(sm)))

    mes_keys = _months_span(6)
    keys_set = set(mes_keys)
    cutoff = datetime(mes_keys[0][0], mes_keys[0][1], 1)
    rows_mes = db.execute(
        select(FondoRendir.created_at, FondoRendir.monto_anticipo).where(
            FondoRendir.created_at >= cutoff
        )
    ).all()
    agg_mes: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "monto": Decimal("0")}
    )
    for created_at, monto in rows_mes:
        if not created_at:
            continue
        key = (created_at.year, created_at.month)
        if key not in keys_set:
            continue
        agg_mes[key]["n"] += 1
        agg_mes[key]["monto"] += _d(monto)

    mes_labels: list[str] = []
    mes_montos: list[float] = []
    mes_n: list[int] = []
    for y, m in mes_keys:
        d = agg_mes.get((y, m), {"n": 0, "monto": Decimal("0")})
        mes_labels.append(f"{_MESES_CORTO[m - 1]} {y}")
        mes_montos.append(float(_d(d["monto"])))
        mes_n.append(int(d["n"]))

    return {
        "n_abiertos": int(n_abiertos),
        "n_pendiente_aprobacion": int(n_pend_apr),
        "monto_abiertos": _d(sum_abiertos),
        "monto_pendiente_aprobacion": _d(sum_pend),
        "alertas_rendicion": alertas,
        "n_total": int(n_total),
        "monto_total": _d(monto_total),
        "chart": {
            "estado_labels": estado_labels,
            "estado_montos": estado_montos,
            "estado_counts": estado_counts,
            "mes_labels": mes_labels,
            "mes_montos": mes_montos,
            "mes_n": mes_n,
        },
    }


def enviar_rendicion(db: Session, fondo_id: int) -> FondoRendir:
    f = obtener_fondo(db, fondo_id)
    if not f:
        raise ValueError("Anticipo no encontrado.")
    if f.estado != "ABIERTO":
        raise ValueError("Solo se puede enviar rendición cuando el anticipo está abierto.")
    if not f.lineas_gasto:
        raise ValueError("Registre al menos un gasto antes de enviar la rendición.")
    f.estado = "PENDIENTE_APROBACION"
    f.fecha_envio_rendicion = datetime.utcnow()
    f.motivo_rechazo = None
    return f


def aprobar_rendicion(db: Session, fondo_id: int) -> FondoRendir:
    f = obtener_fondo(db, fondo_id)
    if not f:
        raise ValueError("Anticipo no encontrado.")
    if f.estado != "PENDIENTE_APROBACION":
        raise ValueError("Solo se aprueba una rendición pendiente.")
    f.estado = "APROBADO"
    f.fecha_aprobacion = datetime.utcnow()
    f.motivo_rechazo = None
    return f


def rechazar_rendicion(db: Session, fondo_id: int, motivo: str) -> FondoRendir:
    f = obtener_fondo(db, fondo_id)
    if not f:
        raise ValueError("Anticipo no encontrado.")
    if f.estado != "PENDIENTE_APROBACION":
        raise ValueError("Solo se rechaza una rendición pendiente.")
    m = (motivo or "").strip()
    if len(m) < 3:
        raise ValueError("Indique un motivo de rechazo.")
    f.estado = "RECHAZADO"
    f.motivo_rechazo = m
    f.fecha_aprobacion = None
    return f


def reabrir_tras_rechazo(db: Session, fondo_id: int) -> FondoRendir:
    f = obtener_fondo(db, fondo_id)
    if not f:
        raise ValueError("Anticipo no encontrado.")
    if f.estado != "RECHAZADO":
        raise ValueError("Solo se reabre un anticipo rechazado.")
    f.estado = "ABIERTO"
    f.fecha_envio_rendicion = None
    f.motivo_rechazo = None
    return f


def eliminar_fondo_rendir(db: Session, fondo_id: int) -> None:
    """
    Elimina el anticipo y sus líneas de gasto.
    Quita el asiento de entrega si existe.
    No permitido si está aprobado o ya tiene asiento de liquidación.
    """
    f = obtener_fondo(db, fondo_id)
    if not f:
        raise ValueError("Anticipo no encontrado.")
    if f.estado == "APROBADO":
        raise ValueError(
            "No se puede eliminar un anticipo aprobado: ya existe contabilidad de liquidación. "
            "Use el módulo de contabilidad si debe revertir asientos."
        )
    liq = getattr(f, "asiento_id_liquidacion", None)
    if liq:
        raise ValueError(
            "Este registro tiene asiento de liquidación; no se puede eliminar desde aquí."
        )
    ent = getattr(f, "asiento_id_entrega", None)
    if ent:
        eliminar_asiento_contable(db, int(ent))
    db.delete(f)
    db.flush()
