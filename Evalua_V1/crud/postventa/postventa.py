# crud/postventa/postventa.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models import Cliente, PostventaInteraccion, PostventaSolicitud

TIPOS_INTERACCION = {"LLAMADA", "EMAIL", "WHATSAPP", "VISITA", "REUNION", "OTRO"}
RESULTADOS_INTERACCION = {
    "CONTACTADO",
    "SIN_RESPUESTA",
    "VOICEMAIL",
    "SEGUIMIENTO",
    "CERRADO_POSITIVO",
    "CERRADO_NEGATIVO",
    "OTRO",
}
CATEGORIAS_SOLICITUD = {"RECLAMO", "CONSULTA", "GARANTIA", "MEJORA", "PEDIDO", "OTRO"}
ESTADOS_SOLICITUD = {"ABIERTA", "EN_PROCESO", "ESPERA_CLIENTE", "RESUELTA", "DESCARTADA"}
PRIORIDADES_SOLICITUD = {"BAJA", "MEDIA", "ALTA", "URGENTE"}

TIPOS_INTERACCION_ORDEN: tuple[str, ...] = tuple(sorted(TIPOS_INTERACCION))

ESTADOS_SOLICITUD_ORDEN: tuple[str, ...] = (
    "ABIERTA",
    "EN_PROCESO",
    "ESPERA_CLIENTE",
    "RESUELTA",
    "DESCARTADA",
)

PRIORIDAD_ORDEN: tuple[str, ...] = ("URGENTE", "ALTA", "MEDIA", "BAJA")

TIPO_LABEL_ES: dict[str, str] = {
    "LLAMADA": "Llamada",
    "EMAIL": "Email",
    "WHATSAPP": "WhatsApp",
    "VISITA": "Visita",
    "REUNION": "Reunión",
    "OTRO": "Otro",
}

ESTADO_SOL_LABEL_ES: dict[str, str] = {
    "ABIERTA": "Abierta",
    "EN_PROCESO": "En proceso",
    "ESPERA_CLIENTE": "Espera cliente",
    "RESUELTA": "Resuelta",
    "DESCARTADA": "Descartada",
}

PRIORIDAD_LABEL_ES: dict[str, str] = {
    "URGENTE": "Urgente",
    "ALTA": "Alta",
    "MEDIA": "Media",
    "BAJA": "Baja",
}

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


def _norm(s: str | None, *, default: str = "") -> str:
    return (s or default).strip()


def listar_clientes_resumen_postventa(
    db: Session,
    *,
    busqueda: str | None = None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    """Clientes con conteo de interacciones recientes y solicitudes abiertas (vista hub)."""
    desde = datetime.combine(date.today() - timedelta(days=30), time.min)

    sub_int = (
        select(func.count(PostventaInteraccion.id))
        .where(
            PostventaInteraccion.cliente_id == Cliente.id,
            PostventaInteraccion.fecha_evento >= desde,
        )
        .scalar_subquery()
    )

    sub_sol = (
        select(func.count(PostventaSolicitud.id))
        .where(
            PostventaSolicitud.cliente_id == Cliente.id,
            PostventaSolicitud.estado.notin_(["RESUELTA", "DESCARTADA"]),
        )
        .scalar_subquery()
    )

    stmt = (
        select(
            Cliente,
            sub_int.label("interacciones_30d"),
            sub_sol.label("solicitudes_abiertas"),
        )
        .where(Cliente.activo.is_(True))
        .order_by(Cliente.razon_social.asc())
        .limit(limit)
    )

    if busqueda:
        pat = f"%{_norm(busqueda)}%"
        stmt = stmt.where(
            or_(
                Cliente.razon_social.ilike(pat),
                Cliente.rut.ilike(pat),
                Cliente.nombre_fantasia.ilike(pat),
                Cliente.email.ilike(pat),
                Cliente.telefono.ilike(pat),
            )
        )

    rows = db.execute(stmt).all()
    out: list[dict[str, Any]] = []
    for cliente, n_int, n_sol in rows:
        out.append(
            {
                "cliente": cliente,
                "interacciones_30d": int(n_int or 0),
                "solicitudes_abiertas": int(n_sol or 0),
            }
        )
    return out


def hub_dashboard_stats(db: Session) -> dict[str, Any]:
    """KPIs y series para gráficos en la portada Postventa."""
    hoy = date.today()
    desde_30 = datetime.combine(hoy - timedelta(days=30), time.min)
    desde_90 = datetime.combine(hoy - timedelta(days=90), time.min)

    n_int_30 = (
        db.scalar(
            select(func.count())
            .select_from(PostventaInteraccion)
            .where(PostventaInteraccion.fecha_evento >= desde_30)
        )
        or 0
    )
    n_int_total = db.scalar(select(func.count()).select_from(PostventaInteraccion)) or 0

    n_sol_abiertas = (
        db.scalar(
            select(func.count())
            .select_from(PostventaSolicitud)
            .where(PostventaSolicitud.estado.notin_(["RESUELTA", "DESCARTADA"]))
        )
        or 0
    )
    n_sol_total = db.scalar(select(func.count()).select_from(PostventaSolicitud)) or 0

    tipo_labels: list[str] = []
    tipo_counts: list[int] = []
    for code in TIPOS_INTERACCION_ORDEN:
        tipo_labels.append(TIPO_LABEL_ES.get(code, code))
        n_t = (
            db.scalar(
                select(func.count())
                .select_from(PostventaInteraccion)
                .where(
                    PostventaInteraccion.tipo == code,
                    PostventaInteraccion.fecha_evento >= desde_90,
                )
            )
            or 0
        )
        tipo_counts.append(int(n_t))

    estado_labels: list[str] = []
    estado_counts: list[int] = []
    for code in ESTADOS_SOLICITUD_ORDEN:
        estado_labels.append(ESTADO_SOL_LABEL_ES.get(code, code))
        n_e = (
            db.scalar(
                select(func.count())
                .select_from(PostventaSolicitud)
                .where(PostventaSolicitud.estado == code)
            )
            or 0
        )
        estado_counts.append(int(n_e))

    prioridad_labels: list[str] = []
    prioridad_counts: list[int] = []
    for code in PRIORIDAD_ORDEN:
        prioridad_labels.append(PRIORIDAD_LABEL_ES.get(code, code))
        n_p = (
            db.scalar(
                select(func.count())
                .select_from(PostventaSolicitud)
                .where(
                    PostventaSolicitud.prioridad == code,
                    PostventaSolicitud.estado.notin_(["RESUELTA", "DESCARTADA"]),
                )
            )
            or 0
        )
        prioridad_counts.append(int(n_p))

    mes_keys = _months_span(6)
    keys_set = set(mes_keys)
    cutoff = datetime(mes_keys[0][0], mes_keys[0][1], 1)

    rows_i = db.execute(
        select(PostventaInteraccion.fecha_evento).where(
            PostventaInteraccion.fecha_evento >= cutoff
        )
    ).all()
    agg_i: dict[tuple[int, int], int] = defaultdict(int)
    for (fe,) in rows_i:
        if not fe:
            continue
        key = (fe.year, fe.month)
        if key in keys_set:
            agg_i[key] += 1

    rows_s = db.execute(
        select(PostventaSolicitud.fecha_apertura).where(PostventaSolicitud.fecha_apertura >= cutoff)
    ).all()
    agg_s: dict[tuple[int, int], int] = defaultdict(int)
    for (fa,) in rows_s:
        if not fa:
            continue
        key = (fa.year, fa.month)
        if key in keys_set:
            agg_s[key] += 1

    mes_labels: list[str] = []
    mes_int: list[int] = []
    mes_sol: list[int] = []
    for y, m in mes_keys:
        mes_labels.append(f"{_MESES_CORTO[m - 1]} {y}")
        mes_int.append(int(agg_i.get((y, m), 0)))
        mes_sol.append(int(agg_s.get((y, m), 0)))

    return {
        "n_interacciones_30d": int(n_int_30),
        "n_interacciones_total": int(n_int_total),
        "n_solicitudes_abiertas": int(n_sol_abiertas),
        "n_solicitudes_total": int(n_sol_total),
        "chart": {
            "tipo_labels": tipo_labels,
            "tipo_counts": tipo_counts,
            "estado_labels": estado_labels,
            "estado_counts": estado_counts,
            "prioridad_labels": prioridad_labels,
            "prioridad_counts": prioridad_counts,
            "mes_labels": mes_labels,
            "mes_int": mes_int,
            "mes_sol": mes_sol,
        },
    }


def contar_por_cliente(db: Session, cliente_id: int) -> dict[str, int]:
    n_int = int(
        db.scalar(
            select(func.count()).select_from(PostventaInteraccion).where(
                PostventaInteraccion.cliente_id == cliente_id
            )
        )
        or 0
    )
    n_sol_abiertas = int(
        db.scalar(
            select(func.count()).select_from(PostventaSolicitud).where(
                PostventaSolicitud.cliente_id == cliente_id,
                PostventaSolicitud.estado.notin_(["RESUELTA", "DESCARTADA"]),
            )
        )
        or 0
    )
    return {"interacciones_total": n_int, "solicitudes_abiertas": n_sol_abiertas}


def listar_interacciones(db: Session, *, cliente_id: int, limit: int = 80) -> list[PostventaInteraccion]:
    stmt = (
        select(PostventaInteraccion)
        .where(PostventaInteraccion.cliente_id == cliente_id)
        .order_by(PostventaInteraccion.fecha_evento.desc(), PostventaInteraccion.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def crear_interaccion(
    db: Session,
    *,
    cliente_id: int,
    tipo: str,
    asunto: str | None,
    detalle: str,
    duracion_minutos: int | None,
    resultado: str | None,
    registrado_por: str | None,
    fecha_evento: datetime | None,
) -> PostventaInteraccion:
    t = _norm(tipo, default="LLAMADA").upper()
    if t not in TIPOS_INTERACCION:
        t = "LLAMADA"
    res_raw = _norm(resultado) or None
    res = None
    if res_raw:
        res = res_raw.upper()
        if res not in RESULTADOS_INTERACCION:
            res = "OTRO"

    ev = fecha_evento or datetime.utcnow()
    row = PostventaInteraccion(
        cliente_id=cliente_id,
        tipo=t,
        asunto=_norm(asunto) or None,
        detalle=_norm(detalle) or "—",
        duracion_minutos=duracion_minutos,
        resultado=res,
        registrado_por=_norm(registrado_por) or None,
        fecha_evento=ev,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def listar_solicitudes(db: Session, *, cliente_id: int, limit: int = 100) -> list[PostventaSolicitud]:
    stmt = (
        select(PostventaSolicitud)
        .where(PostventaSolicitud.cliente_id == cliente_id)
        .order_by(PostventaSolicitud.fecha_apertura.desc(), PostventaSolicitud.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def crear_solicitud(
    db: Session,
    *,
    cliente_id: int,
    titulo: str,
    descripcion: str,
    categoria: str,
    prioridad: str,
) -> PostventaSolicitud:
    cat = _norm(categoria, default="CONSULTA").upper()
    if cat not in CATEGORIAS_SOLICITUD:
        cat = "CONSULTA"
    pri = _norm(prioridad, default="MEDIA").upper()
    if pri not in PRIORIDADES_SOLICITUD:
        pri = "MEDIA"

    row = PostventaSolicitud(
        cliente_id=cliente_id,
        titulo=_norm(titulo) or "Sin título",
        descripcion=_norm(descripcion) or "—",
        categoria=cat,
        estado="ABIERTA",
        prioridad=pri,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_solicitud(db: Session, solicitud_id: int) -> PostventaSolicitud | None:
    return db.get(PostventaSolicitud, solicitud_id)


def actualizar_estado_solicitud(
    db: Session,
    *,
    solicitud_id: int,
    nuevo_estado: str,
) -> PostventaSolicitud | None:
    sol = get_solicitud(db, solicitud_id)
    if not sol:
        return None
    est = _norm(nuevo_estado).upper()
    if est not in ESTADOS_SOLICITUD:
        return None
    sol.estado = est
    sol.fecha_actualizacion = datetime.utcnow()
    if est in ("RESUELTA", "DESCARTADA"):
        sol.fecha_cierre = datetime.utcnow()
    else:
        sol.fecha_cierre = None
    db.add(sol)
    db.commit()
    db.refresh(sol)
    return sol
