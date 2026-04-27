# crud/postventa/postventa.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import json
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from models import Cliente, PostventaCasoEvento, PostventaInteraccion, PostventaSolicitud, Usuario
from services.comunicaciones.email_service import email_service

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
ORIGENES_CASO = {"WEB", "EMAIL", "TELEFONO", "WHATSAPP", "INTERNO", "OTRO"}
ESTADOS_CASO = {
    "NUEVO",
    "ASIGNADO",
    "EN_PROCESO",
    "ESPERA_CLIENTE",
    "ESCALADO",
    "RESUELTO",
    "CERRADO",
    "CANCELADO",
}
SLA_ESTADOS = {"OK", "EN_RIESGO", "VENCIDO"}
TIPOS_EVENTO_CASO = {
    "COMENTARIO",
    "NOTA_INTERNA",
    "CAMBIO_ESTADO",
    "ASIGNACION",
    "EMAIL_ENVIADO",
    "SISTEMA",
}
VISIBILIDAD_EVENTO = {"INTERNA", "PUBLICA"}

TIPOS_INTERACCION_ORDEN: tuple[str, ...] = tuple(sorted(TIPOS_INTERACCION))

ESTADOS_SOLICITUD_ORDEN: tuple[str, ...] = (
    "ABIERTA",
    "EN_PROCESO",
    "ESPERA_CLIENTE",
    "RESUELTA",
    "DESCARTADA",
)
ESTADOS_CASO_ORDEN: tuple[str, ...] = (
    "NUEVO",
    "ASIGNADO",
    "EN_PROCESO",
    "ESPERA_CLIENTE",
    "ESCALADO",
    "RESUELTO",
    "CERRADO",
    "CANCELADO",
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
ESTADO_CASO_LABEL_ES: dict[str, str] = {
    "NUEVO": "Nuevo",
    "ASIGNADO": "Asignado",
    "EN_PROCESO": "En proceso",
    "ESPERA_CLIENTE": "Espera cliente",
    "ESCALADO": "Escalado",
    "RESUELTO": "Resuelto",
    "CERRADO": "Cerrado",
    "CANCELADO": "Cancelado",
}
ORIGEN_LABEL_ES: dict[str, str] = {
    "WEB": "Web",
    "EMAIL": "Email",
    "TELEFONO": "Teléfono",
    "WHATSAPP": "WhatsApp",
    "INTERNO": "Interno",
    "OTRO": "Otro",
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


def _json_meta(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    return json.dumps(data, ensure_ascii=False, default=str)


def _to_case_status(estado_legacy: str | None) -> str:
    e = _norm(estado_legacy).upper()
    if e in ESTADOS_CASO:
        return e
    return {
        "ABIERTA": "NUEVO",
        "RESUELTA": "RESUELTO",
        "DESCARTADA": "CANCELADO",
    }.get(e, "EN_PROCESO" if e == "EN_PROCESO" else "NUEVO")


def _is_closed_status(estado: str) -> bool:
    return estado in {"RESUELTO", "CERRADO", "CANCELADO"}


def _build_numero_caso(db: Session, now: datetime | None = None) -> str:
    ts = now or datetime.utcnow()
    year = ts.year
    prefix = f"PV-{year}-"
    last_num = (
        db.scalar(
            select(func.max(PostventaSolicitud.numero_caso)).where(
                PostventaSolicitud.numero_caso.like(f"{prefix}%")
            )
        )
        or ""
    )
    seq = 1
    if last_num and str(last_num).startswith(prefix):
        tail = str(last_num)[len(prefix) :]
        if tail.isdigit():
            seq = int(tail) + 1
    return f"{prefix}{seq:06d}"


def _touch_case(caso: PostventaSolicitud) -> None:
    caso.fecha_actualizacion = datetime.utcnow()
    caso.ultimo_movimiento_at = datetime.utcnow()


def _present_numero_caso(caso: PostventaSolicitud) -> str:
    if getattr(caso, "numero_caso", None):
        return str(caso.numero_caso)
    return f"PV-{(caso.fecha_apertura or datetime.utcnow()).year}-{int(caso.id):06d}"


def _ensure_case_compat(caso: PostventaSolicitud) -> PostventaSolicitud:
    # Solo para presentación en UI; no persiste cambios en lecturas.
    if not getattr(caso, "numero_caso", None):
        caso.numero_caso = _present_numero_caso(caso)
    if not getattr(caso, "ultimo_movimiento_at", None):
        caso.ultimo_movimiento_at = caso.fecha_actualizacion or caso.fecha_apertura
    if not getattr(caso, "sla_estado", None):
        caso.sla_estado = "OK"
    return caso


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
            .where(PostventaSolicitud.estado.notin_(["RESUELTO", "CERRADO", "CANCELADO", "RESUELTA", "DESCARTADA"]))
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
                PostventaSolicitud.estado.notin_(["RESUELTO", "CERRADO", "CANCELADO", "RESUELTA", "DESCARTADA"]),
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
    try:
        stmt = (
            select(PostventaSolicitud)
            .where(PostventaSolicitud.cliente_id == cliente_id)
            .order_by(PostventaSolicitud.fecha_apertura.desc(), PostventaSolicitud.id.desc())
            .limit(limit)
        )
        rows = list(db.scalars(stmt))
        for row in rows:
            _ensure_case_compat(row)
        return rows
    except Exception:
        # Fallback legacy: evita depender de columnas CRM no presentes.
        sql = """
        SELECT id, cliente_id, titulo, descripcion, categoria, estado, prioridad,
               fecha_apertura, fecha_actualizacion, fecha_cierre
        FROM public.postventa_solicitudes
        WHERE cliente_id = :cliente_id
        ORDER BY fecha_apertura DESC, id DESC
        LIMIT :lim
        """
        rows = db.execute(text(sql), {"cliente_id": int(cliente_id), "lim": int(limit)}).mappings().all()
        out: list[PostventaSolicitud] = []
        for r in rows:
            obj = PostventaSolicitud(
                id=r["id"],
                cliente_id=r["cliente_id"],
                titulo=r["titulo"],
                descripcion=r["descripcion"],
                categoria=r["categoria"],
                estado=r["estado"],
                prioridad=r["prioridad"],
                fecha_apertura=r["fecha_apertura"],
                fecha_actualizacion=r["fecha_actualizacion"],
                fecha_cierre=r["fecha_cierre"],
            )
            _ensure_case_compat(obj)
            out.append(obj)
        return out


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
        estado="NUEVO",
        prioridad=pri,
        origen="INTERNO",
        numero_caso=_build_numero_caso(db),
        sla_estado="OK",
        ultimo_movimiento_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    agregar_evento_caso(
        db,
        caso_id=row.id,
        cliente_id=row.cliente_id,
        usuario_id=None,
        tipo="SISTEMA",
        visibilidad="INTERNA",
        contenido="Caso creado desde ficha de cliente.",
    )
    db.commit()
    db.refresh(row)
    return row


def get_solicitud(db: Session, solicitud_id: int) -> PostventaSolicitud | None:
    row = db.get(PostventaSolicitud, solicitud_id)
    if row:
        _ensure_case_compat(row)
    return row


def actualizar_estado_solicitud(
    db: Session,
    *,
    solicitud_id: int,
    nuevo_estado: str,
) -> PostventaSolicitud | None:
    sol = get_solicitud(db, solicitud_id)
    if not sol:
        return None
    est = _to_case_status(nuevo_estado)
    if est not in ESTADOS_CASO:
        return None
    prev = _to_case_status(sol.estado)
    sol.estado = est
    _touch_case(sol)
    if est in ("RESUELTO", "CERRADO"):
        sol.fecha_resolucion = sol.fecha_resolucion or datetime.utcnow()
        if est == "CERRADO":
            sol.fecha_cierre = sol.fecha_cierre or datetime.utcnow()
    elif est == "CANCELADO":
        sol.fecha_cierre = datetime.utcnow()
    else:
        sol.fecha_cierre = None
        if est not in ("RESUELTO", "CERRADO"):
            sol.fecha_resolucion = None
    agregar_evento_caso(
        db,
        caso_id=sol.id,
        cliente_id=sol.cliente_id,
        usuario_id=None,
        tipo="CAMBIO_ESTADO",
        visibilidad="INTERNA",
        contenido=f"Estado actualizado: {prev} → {est}.",
    )
    db.add(sol)
    db.commit()
    db.refresh(sol)
    return sol


def listar_casos(
    db: Session,
    *,
    estado: str | None = None,
    prioridad: str | None = None,
    asignado_a_id: int | None = None,
    cliente_id: int | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[PostventaSolicitud]:
    try:
        stmt = select(PostventaSolicitud).order_by(
            PostventaSolicitud.ultimo_movimiento_at.desc().nullslast(),
            PostventaSolicitud.fecha_apertura.desc(),
            PostventaSolicitud.id.desc(),
        )
        if estado:
            stmt = stmt.where(PostventaSolicitud.estado == _to_case_status(estado))
        if prioridad:
            stmt = stmt.where(PostventaSolicitud.prioridad == _norm(prioridad).upper())
        if asignado_a_id is not None:
            if int(asignado_a_id) <= 0:
                stmt = stmt.where(PostventaSolicitud.asignado_a_id.is_(None))
            else:
                stmt = stmt.where(PostventaSolicitud.asignado_a_id == int(asignado_a_id))
        if cliente_id is not None:
            stmt = stmt.where(PostventaSolicitud.cliente_id == int(cliente_id))
        if q:
            pat = f"%{_norm(q)}%"
            stmt = stmt.join(Cliente, Cliente.id == PostventaSolicitud.cliente_id).where(
                or_(
                    PostventaSolicitud.titulo.ilike(pat),
                    PostventaSolicitud.descripcion.ilike(pat),
                    PostventaSolicitud.numero_caso.ilike(pat),
                    Cliente.razon_social.ilike(pat),
                    Cliente.rut.ilike(pat),
                )
            )
        rows = list(db.scalars(stmt.limit(limit)))
        for row in rows:
            _ensure_case_compat(row)
        return rows
    except Exception:
        # Fallback legacy para bases aún sin columnas CRM.
        stmt = select(PostventaSolicitud).order_by(PostventaSolicitud.fecha_apertura.desc(), PostventaSolicitud.id.desc())
        if estado:
            stmt = stmt.where(PostventaSolicitud.estado == _to_case_status(estado))
        if prioridad:
            stmt = stmt.where(PostventaSolicitud.prioridad == _norm(prioridad).upper())
        if cliente_id is not None:
            stmt = stmt.where(PostventaSolicitud.cliente_id == int(cliente_id))
        if q:
            pat = f"%{_norm(q)}%"
            stmt = stmt.join(Cliente, Cliente.id == PostventaSolicitud.cliente_id).where(
                or_(
                    PostventaSolicitud.titulo.ilike(pat),
                    PostventaSolicitud.descripcion.ilike(pat),
                    Cliente.razon_social.ilike(pat),
                    Cliente.rut.ilike(pat),
                )
            )
        rows = list(db.scalars(stmt.limit(limit)))
        for row in rows:
            _ensure_case_compat(row)
        return rows


def crear_caso(
    db: Session,
    *,
    cliente_id: int,
    titulo: str,
    descripcion: str,
    categoria: str = "CONSULTA",
    prioridad: str = "MEDIA",
    origen: str = "INTERNO",
    creado_por_id: int | None = None,
    fecha_vencimiento_sla: datetime | None = None,
) -> PostventaSolicitud:
    cat = _norm(categoria, default="CONSULTA").upper()
    if cat not in CATEGORIAS_SOLICITUD:
        cat = "CONSULTA"
    pri = _norm(prioridad, default="MEDIA").upper()
    if pri not in PRIORIDADES_SOLICITUD:
        pri = "MEDIA"
    ori = _norm(origen, default="INTERNO").upper()
    if ori not in ORIGENES_CASO:
        ori = "OTRO"
    caso = PostventaSolicitud(
        cliente_id=cliente_id,
        titulo=_norm(titulo) or "Sin título",
        descripcion=_norm(descripcion) or "—",
        categoria=cat,
        estado="NUEVO",
        prioridad=pri,
        origen=ori,
        creado_por_id=creado_por_id,
        numero_caso=_build_numero_caso(db),
        fecha_vencimiento_sla=fecha_vencimiento_sla,
        sla_estado="OK",
        ultimo_movimiento_at=datetime.utcnow(),
    )
    db.add(caso)
    db.flush()
    agregar_evento_caso(
        db,
        caso_id=caso.id,
        cliente_id=cliente_id,
        usuario_id=creado_por_id,
        tipo="SISTEMA",
        visibilidad="INTERNA",
        contenido=f"Caso creado ({caso.numero_caso}).",
    )
    db.commit()
    db.refresh(caso)
    return caso


def get_caso(db: Session, caso_id: int) -> PostventaSolicitud | None:
    return get_solicitud(db, caso_id)


def agregar_evento_caso(
    db: Session,
    *,
    caso_id: int,
    cliente_id: int,
    usuario_id: int | None,
    tipo: str,
    visibilidad: str = "INTERNA",
    contenido: str,
    metadata: dict[str, Any] | None = None,
) -> PostventaCasoEvento:
    tipo_norm = _norm(tipo, default="SISTEMA").upper()
    if tipo_norm not in TIPOS_EVENTO_CASO:
        tipo_norm = "SISTEMA"
    vis = _norm(visibilidad, default="INTERNA").upper()
    if vis not in VISIBILIDAD_EVENTO:
        vis = "INTERNA"
    row = PostventaCasoEvento(
        caso_id=caso_id,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        tipo=tipo_norm,
        visibilidad=vis,
        contenido=_norm(contenido) or "—",
        metadata_json=_json_meta(metadata),
    )
    db.add(row)
    caso = db.get(PostventaSolicitud, caso_id)
    if caso:
        _touch_case(caso)
        db.add(caso)
    return row


def listar_eventos_caso(db: Session, caso_id: int, *, limit: int = 300) -> list[PostventaCasoEvento]:
    stmt = (
        select(PostventaCasoEvento)
        .where(PostventaCasoEvento.caso_id == int(caso_id))
        .order_by(PostventaCasoEvento.created_at.asc(), PostventaCasoEvento.id.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def asignar_caso(
    db: Session,
    *,
    caso_id: int,
    usuario_id: int | None,
    actor_id: int | None,
) -> PostventaSolicitud | None:
    caso = get_caso(db, caso_id)
    if not caso:
        return None
    prev = caso.asignado_a_id
    caso.asignado_a_id = usuario_id
    if usuario_id and _to_case_status(caso.estado) == "NUEVO":
        caso.estado = "ASIGNADO"
    _touch_case(caso)
    user_name = "Sin asignar"
    if usuario_id:
        u = db.get(Usuario, int(usuario_id))
        user_name = u.nombre_completo if u else f"Usuario {usuario_id}"
    agregar_evento_caso(
        db,
        caso_id=caso.id,
        cliente_id=caso.cliente_id,
        usuario_id=actor_id,
        tipo="ASIGNACION",
        visibilidad="INTERNA",
        contenido=f"Asignación actualizada: {prev or 'Sin asignar'} → {user_name}.",
        metadata={"prev_asignado_a_id": prev, "asignado_a_id": usuario_id},
    )
    db.add(caso)
    db.commit()
    db.refresh(caso)
    return caso


def cambiar_estado_caso(
    db: Session,
    *,
    caso_id: int,
    estado: str,
    actor_id: int | None,
    comentario: str | None = None,
) -> PostventaSolicitud | None:
    caso = get_caso(db, caso_id)
    if not caso:
        return None
    nuevo = _to_case_status(estado)
    if nuevo not in ESTADOS_CASO:
        return None
    previo = _to_case_status(caso.estado)
    caso.estado = nuevo
    now = datetime.utcnow()
    if not caso.fecha_primer_respuesta:
        caso.fecha_primer_respuesta = now
    if nuevo in {"RESUELTO", "CERRADO"} and not caso.fecha_resolucion:
        caso.fecha_resolucion = now
    if nuevo in {"CERRADO", "CANCELADO"} and not caso.fecha_cierre:
        caso.fecha_cierre = now
    if not _is_closed_status(nuevo):
        caso.fecha_cierre = None
    _touch_case(caso)
    agregar_evento_caso(
        db,
        caso_id=caso.id,
        cliente_id=caso.cliente_id,
        usuario_id=actor_id,
        tipo="CAMBIO_ESTADO",
        visibilidad="INTERNA",
        contenido=f"Estado actualizado: {previo} → {nuevo}.",
        metadata={"comentario": _norm(comentario) or None},
    )
    if comentario and _norm(comentario):
        agregar_evento_caso(
            db,
            caso_id=caso.id,
            cliente_id=caso.cliente_id,
            usuario_id=actor_id,
            tipo="NOTA_INTERNA",
            visibilidad="INTERNA",
            contenido=_norm(comentario),
        )
    db.add(caso)
    db.commit()
    db.refresh(caso)
    return caso


def enviar_email_caso(
    db: Session,
    *,
    caso_id: int,
    to: str | None,
    subject: str,
    body: str,
    actor: dict[str, Any] | None,
) -> dict[str, Any]:
    caso = get_caso(db, caso_id)
    if not caso:
        raise ValueError("Caso no encontrado.")
    log = email_service.send_postventa_caso_email(
        db=db,
        caso=caso,
        to=to,
        subject=subject,
        body=body,
        actor=actor,
    )
    actor_id = int(actor.get("uid")) if actor and actor.get("uid") else None
    agregar_evento_caso(
        db,
        caso_id=caso.id,
        cliente_id=caso.cliente_id,
        usuario_id=actor_id,
        tipo="EMAIL_ENVIADO",
        visibilidad="PUBLICA",
        contenido=f"Correo enviado: {subject}",
        metadata={"to": to, "email_log_id": getattr(log, "id", None)},
    )
    if not caso.fecha_primer_respuesta:
        caso.fecha_primer_respuesta = datetime.utcnow()
    _touch_case(caso)
    db.add(caso)
    db.commit()
    return {"ok": True, "email_log_id": getattr(log, "id", None)}


def metricas_postventa(db: Session) -> dict[str, Any]:
    try:
        now = datetime.utcnow()
        d7 = now - timedelta(days=7)
        d30 = now - timedelta(days=30)
        abiertos_filter = PostventaSolicitud.estado.notin_(["RESUELTO", "CERRADO", "CANCELADO", "RESUELTA", "DESCARTADA"])
        abiertos = int(db.scalar(select(func.count()).select_from(PostventaSolicitud).where(abiertos_filter)) or 0)
        nuevos_7 = int(
            db.scalar(select(func.count()).select_from(PostventaSolicitud).where(PostventaSolicitud.fecha_apertura >= d7)) or 0
        )
        nuevos_30 = int(
            db.scalar(select(func.count()).select_from(PostventaSolicitud).where(PostventaSolicitud.fecha_apertura >= d30))
            or 0
        )
        resueltos_30 = int(
            db.scalar(
                select(func.count()).select_from(PostventaSolicitud).where(
                    PostventaSolicitud.fecha_resolucion.is_not(None),
                    PostventaSolicitud.fecha_resolucion >= d30,
                )
            )
            or 0
        )
        avg_primera = db.scalar(
            select(
                func.avg(
                    func.extract("epoch", PostventaSolicitud.fecha_primer_respuesta - PostventaSolicitud.fecha_apertura)
                    / 3600
                )
            ).where(PostventaSolicitud.fecha_primer_respuesta.is_not(None))
        )
        avg_resol = db.scalar(
            select(
                func.avg(
                    func.extract("epoch", PostventaSolicitud.fecha_resolucion - PostventaSolicitud.fecha_apertura) / 3600
                )
            ).where(PostventaSolicitud.fecha_resolucion.is_not(None))
        )
        vencidos = int(
            db.scalar(
                select(func.count()).select_from(PostventaSolicitud).where(
                    abiertos_filter,
                    or_(
                        PostventaSolicitud.sla_estado == "VENCIDO",
                        and_(
                            PostventaSolicitud.fecha_vencimiento_sla.is_not(None),
                            PostventaSolicitud.fecha_vencimiento_sla < now,
                        ),
                    ),
                )
            )
            or 0
        )
        backlog_sin_asignar = int(
            db.scalar(
                select(func.count()).select_from(PostventaSolicitud).where(
                    abiertos_filter, PostventaSolicitud.asignado_a_id.is_(None)
                )
            )
            or 0
        )
        rows_asig = db.execute(
            select(PostventaSolicitud.asignado_a_id, func.count())
            .where(abiertos_filter)
            .group_by(PostventaSolicitud.asignado_a_id)
        ).all()
        casos_por_usuario = [{"asignado_a_id": int(uid) if uid else None, "cantidad": int(cnt)} for uid, cnt in rows_asig]
        rows_estado = db.execute(select(PostventaSolicitud.estado, func.count()).group_by(PostventaSolicitud.estado)).all()
        casos_por_estado = [{"estado": _to_case_status(est), "cantidad": int(cnt)} for est, cnt in rows_estado]
        rows_prior = db.execute(select(PostventaSolicitud.prioridad, func.count()).group_by(PostventaSolicitud.prioridad)).all()
        casos_por_prioridad = [{"prioridad": pri, "cantidad": int(cnt)} for pri, cnt in rows_prior]
        return {
            "casos_abiertos": abiertos,
            "casos_nuevos_7d": nuevos_7,
            "casos_nuevos_30d": nuevos_30,
            "casos_resueltos_30d": resueltos_30,
            "promedio_horas_primera_respuesta": float(avg_primera or 0),
            "promedio_horas_resolucion": float(avg_resol or 0),
            "casos_vencidos_sla": vencidos,
            "casos_por_usuario_asignado": casos_por_usuario,
            "casos_por_estado": casos_por_estado,
            "casos_por_prioridad": casos_por_prioridad,
            "backlog_sin_asignar": backlog_sin_asignar,
        }
    except Exception:
        # Compatibilidad defensiva: si la base aún no tiene columnas CRM, evita 500 en /postventa.
        abiertos = int(
            db.scalar(
                select(func.count())
                .select_from(PostventaSolicitud)
                .where(PostventaSolicitud.estado.notin_(["RESUELTA", "DESCARTADA"]))
            )
            or 0
        )
        nuevos_30 = int(
            db.scalar(
                select(func.count()).select_from(PostventaSolicitud).where(
                    PostventaSolicitud.fecha_apertura >= (datetime.utcnow() - timedelta(days=30))
                )
            )
            or 0
        )
        rows_estado = db.execute(select(PostventaSolicitud.estado, func.count()).group_by(PostventaSolicitud.estado)).all()
        rows_prior = db.execute(select(PostventaSolicitud.prioridad, func.count()).group_by(PostventaSolicitud.prioridad)).all()
        return {
            "casos_abiertos": abiertos,
            "casos_nuevos_7d": 0,
            "casos_nuevos_30d": nuevos_30,
            "casos_resueltos_30d": 0,
            "promedio_horas_primera_respuesta": 0.0,
            "promedio_horas_resolucion": 0.0,
            "casos_vencidos_sla": 0,
            "casos_por_usuario_asignado": [],
            "casos_por_estado": [{"estado": _to_case_status(est), "cantidad": int(cnt)} for est, cnt in rows_estado],
            "casos_por_prioridad": [{"prioridad": pri, "cantidad": int(cnt)} for pri, cnt in rows_prior],
            "backlog_sin_asignar": 0,
        }
