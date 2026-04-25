# crud/comercial/credito_riesgo.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models.comercial.credito_riesgo import (
    CreditoComite,
    CreditoEvaluacion,
    CreditoHistorial,
    CreditoPolitica,
    CreditoSolicitud,
)
from services.credito_riesgo_motor import MACRO_DEFAULT, PONDERACIONES_DEFAULT, evaluar_credito_riesgo, resultado_a_columnas


def get_politica_valor(db: Session, clave: str) -> dict[str, Any] | None:
    row = db.scalars(select(CreditoPolitica).where(CreditoPolitica.clave == clave, CreditoPolitica.activo.is_(True))).first()
    if not row:
        return None
    return dict(row.valor_json) if row.valor_json else {}


def cargar_macro_y_ponderaciones(db: Session) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    raw_m = get_politica_valor(db, "macro_referencia_chile_202602")
    raw_p = get_politica_valor(db, "ponderaciones_v1")
    macro = {
        k: Decimal(str(v))
        for k, v in (raw_m or {}).items()
        if k in MACRO_DEFAULT or k in ("tpm_referencia_anual_pct",)
    }
    for k, v in MACRO_DEFAULT.items():
        macro.setdefault(k, v)
    if "tpm_referencia_anual_pct" not in macro:
        macro["tpm_referencia_anual_pct"] = Decimal("5.25")
    pond: dict[str, Decimal] = {}
    if raw_p:
        for k, v in raw_p.items():
            try:
                pond[k] = Decimal(str(v))
            except Exception:
                continue
    if len(pond) < 7:
        pond = dict(PONDERACIONES_DEFAULT)
    return macro, pond


def listar_solicitudes(db: Session, *, limit: int = 200, estado: str | None = None) -> list[CreditoSolicitud]:
    stmt = (
        select(CreditoSolicitud)
        .options(selectinload(CreditoSolicitud.cliente), selectinload(CreditoSolicitud.evaluaciones))
        .order_by(CreditoSolicitud.id.desc())
        .limit(limit)
    )
    if estado:
        stmt = stmt.where(CreditoSolicitud.estado == estado)
    return list(db.scalars(stmt).all())


def obtener_solicitud(db: Session, solicitud_id: int) -> CreditoSolicitud | None:
    stmt = (
        select(CreditoSolicitud)
        .options(
            selectinload(CreditoSolicitud.cliente),
            selectinload(CreditoSolicitud.evaluaciones),
            selectinload(CreditoSolicitud.garantias),
            selectinload(CreditoSolicitud.documentos),
            selectinload(CreditoSolicitud.comites),
            selectinload(CreditoSolicitud.historial),
        )
        .where(CreditoSolicitud.id == solicitud_id)
    )
    return db.scalars(stmt).first()


def _next_codigo(db: Session) -> str:
    y = datetime.now(timezone.utc).year
    pref = f"CR-{y}-"
    last = db.scalar(select(func.max(CreditoSolicitud.id))) or 0
    return f"{pref}{int(last) + 1:05d}"


def crear_solicitud(db: Session, obj: CreditoSolicitud, *, usuario: str = "sistema") -> CreditoSolicitud:
    if not obj.codigo:
        obj.codigo = _next_codigo(db)
    db.add(obj)
    db.flush()
    db.add(
        CreditoHistorial(
            solicitud_id=int(obj.id),
            evento="SOLICITUD_CREADA",
            detalle_json=None,
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(obj)
    return obj


def actualizar_solicitud(db: Session, sol: CreditoSolicitud, *, usuario: str = "sistema") -> CreditoSolicitud:
    db.add(sol)
    db.flush()
    db.add(
        CreditoHistorial(
            solicitud_id=int(sol.id),
            evento="SOLICITUD_ACTUALIZADA",
            detalle_json=None,
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(sol)
    return sol


def ejecutar_evaluacion(db: Session, sol: CreditoSolicitud, *, usuario: str = "sistema") -> CreditoEvaluacion:
    macro, pond = cargar_macro_y_ponderaciones(db)
    r = evaluar_credito_riesgo(
        ingreso_mensual=sol.ingreso_mensual,
        gastos_mensual=sol.gastos_mensual,
        deuda_cuotas_mensual=sol.deuda_cuotas_mensual,
        cuota_propuesta=sol.cuota_propuesta,
        monto_solicitado=sol.monto_solicitado,
        plazo_solicitado=sol.plazo_solicitado,
        tipo_persona=sol.tipo_persona,
        sector_actividad=sol.sector_actividad,
        mora_max_dias_12m=sol.mora_max_dias_12m,
        protestos=sol.protestos,
        castigos=sol.castigos,
        reprogramaciones=sol.reprogramaciones,
        tipo_contrato=sol.tipo_contrato,
        ventas_anual=sol.ventas_anual,
        deuda_total=sol.deuda_total,
        patrimonio=sol.patrimonio,
        liquidez_corriente=sol.liquidez_corriente,
        flujo_caja_mensual=sol.flujo_caja_mensual,
        antiguedad_meses_natural=sol.antiguedad_meses_natural,
        anios_operacion_empresa=sol.anios_operacion_empresa,
        garantia_valor_liquidacion=sol.garantia_valor_liquidacion,
        exposicion_usd_pct=sol.exposicion_usd_pct,
        macro=macro,
        ponderaciones=pond,
    )
    col = resultado_a_columnas(r)
    ev = CreditoEvaluacion(
        solicitud_id=int(sol.id),
        score_total=col["score_total"],
        categoria=col["categoria"],
        clasificacion_riesgo=col["clasificacion_riesgo"],
        monto_maximo_sugerido=col["monto_maximo_sugerido"],
        plazo_maximo_sugerido=col["plazo_maximo_sugerido"],
        tasa_sugerida_anual=col["tasa_sugerida_anual"],
        recomendacion=col["recomendacion"],
        explicacion=col["explicacion"],
        desglose_json=col["desglose_json"],
        macro_json=col["macro_json"],
        stress_cuotas_json=col["stress_cuotas_json"],
        motor_version=col["motor_version"],
    )
    db.add(ev)
    # El motor no fija estado operativo: queda en evaluación hasta decisión humana o comité.
    sol.estado = "EN_EVALUACION"
    db.add(sol)
    db.flush()
    db.add(
        CreditoHistorial(
            solicitud_id=int(sol.id),
            evento="EVALUACION_EJECUTADA",
            detalle_json={
                "evaluacion_id": int(ev.id),
                "evaluacion_score": float(col["score_total"]),
                "categoria": col["categoria"],
                "recomendacion_motor": col["recomendacion"],
            },
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(ev)
    return ev


def aplicar_decision_manual(
    db: Session,
    sol: CreditoSolicitud,
    estado_objetivo: str,
    *,
    evento: str,
    usuario: str = "sistema",
    nota: str | None = None,
) -> CreditoSolicitud:
    """Registra decisión de riesgo (no automática por el motor)."""
    permitidos = {"APROBADA", "RECHAZADA", "CONDICIONES", "EN_EVALUACION"}
    eo = str(estado_objetivo).strip().upper()
    if eo not in permitidos:
        raise ValueError(f"Estado objetivo no permitido: {eo}")
    sol.estado = eo
    db.add(sol)
    db.flush()
    detalle: dict[str, Any] = {"estado": eo}
    if nota:
        detalle["nota"] = nota[:2000]
    db.add(
        CreditoHistorial(
            solicitud_id=int(sol.id),
            evento=evento,
            detalle_json=detalle,
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(sol)
    return sol


def obtener_evaluacion(db: Session, eval_id: int) -> CreditoEvaluacion | None:
    stmt = select(CreditoEvaluacion).options(selectinload(CreditoEvaluacion.solicitud).selectinload(CreditoSolicitud.cliente)).where(CreditoEvaluacion.id == eval_id)
    return db.scalars(stmt).first()


def listar_evaluaciones_cliente(db: Session, cliente_id: int, limit: int = 50) -> list[CreditoEvaluacion]:
    stmt = (
        select(CreditoEvaluacion)
        .join(CreditoSolicitud, CreditoSolicitud.id == CreditoEvaluacion.solicitud_id)
        .where(CreditoSolicitud.cliente_id == cliente_id)
        .options(selectinload(CreditoEvaluacion.solicitud).selectinload(CreditoSolicitud.cliente))
        .order_by(CreditoEvaluacion.creado_en.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def dashboard_kpis(db: Session) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(CreditoSolicitud)) or 0
    aprob = db.scalar(select(func.count()).select_from(CreditoSolicitud).where(CreditoSolicitud.estado == "APROBADA")) or 0
    rech = db.scalar(select(func.count()).select_from(CreditoSolicitud).where(CreditoSolicitud.estado == "RECHAZADA")) or 0
    comite = db.scalar(select(func.count()).select_from(CreditoSolicitud).where(CreditoSolicitud.estado == "COMITE")) or 0
    monto_sol = db.scalar(select(func.coalesce(func.sum(CreditoSolicitud.monto_solicitado), 0)).select_from(CreditoSolicitud)) or 0

    evs = list(db.scalars(select(CreditoEvaluacion).order_by(CreditoEvaluacion.id.desc()).limit(800)).all())
    latest_by_sol: dict[int, CreditoEvaluacion] = {}
    for e in evs:
        if e.solicitud_id not in latest_by_sol:
            latest_by_sol[int(e.solicitud_id)] = e
    latest_list = list(latest_by_sol.values())
    avg_score = (
        sum(float(x.score_total) for x in latest_list) / len(latest_list) if latest_list else None
    )

    dist = dict.fromkeys(["A", "B", "C", "D", "E"], 0)
    for e in latest_list:
        c = str(e.categoria).strip().upper()
        if c in dist:
            dist[c] += 1

    monto_aprob = Decimal("0")
    for sol in db.scalars(select(CreditoSolicitud).where(CreditoSolicitud.estado == "APROBADA")).all():
        monto_aprob += sol.monto_solicitado

    mora_est = float(comite) * 0.15 + float(rech) * 0.08

    return {
        "total_solicitudes": int(total),
        "aprobadas": int(aprob),
        "rechazadas": int(rech),
        "comite": int(comite),
        "score_promedio": float(avg_score) if avg_score is not None else None,
        "monto_solicitado_total": float(monto_sol),
        "monto_aprobado_total": float(monto_aprob),
        "mora_estimada_pct": round(mora_est, 2),
        "distribucion_categoria": dist,
    }


def listar_comite_pendientes(db: Session, limit: int = 100) -> list[CreditoComite]:
    stmt = (
        select(CreditoComite)
        .options(selectinload(CreditoComite.solicitud).selectinload(CreditoSolicitud.cliente))
        .where(CreditoComite.estado == "PENDIENTE")
        .order_by(CreditoComite.fecha_apertura.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def abrir_comite(db: Session, sol: CreditoSolicitud, resumen: str, *, usuario: str = "sistema") -> CreditoComite:
    c = CreditoComite(solicitud_id=int(sol.id), estado="PENDIENTE", resumen=resumen, analista=usuario)
    sol.estado = "COMITE"
    db.add(c)
    db.add(sol)
    db.flush()
    db.add(
        CreditoHistorial(
            solicitud_id=int(sol.id),
            evento="COMITE_ABIERTO",
            detalle_json=None,
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(c)
    return c


def resolver_comite(
    db: Session,
    comite: CreditoComite,
    decision: str,
    comentario: str,
    *,
    usuario: str = "sistema",
) -> CreditoComite:
    comite.estado = "RESUELTO"
    comite.decision = decision
    comite.comentario = comentario
    comite.fecha_cierre = datetime.now(timezone.utc)
    comite.analista = usuario
    sol = comite.solicitud
    if decision == "APROBAR":
        sol.estado = "APROBADA"
    elif decision == "RECHAZAR":
        sol.estado = "RECHAZADA"
    else:
        sol.estado = "CONDICIONES"
    db.add(comite)
    db.add(sol)
    db.flush()
    db.add(
        CreditoHistorial(
            solicitud_id=int(sol.id),
            evento="COMITE_RESUELTO",
            detalle_json={"decision": decision},
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(comite)
    return comite


def obtener_comite(db: Session, comite_id: int) -> CreditoComite | None:
    stmt = select(CreditoComite).options(selectinload(CreditoComite.solicitud).selectinload(CreditoSolicitud.cliente)).where(CreditoComite.id == comite_id)
    return db.scalars(stmt).first()
