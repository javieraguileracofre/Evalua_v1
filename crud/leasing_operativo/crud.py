# crud/leasing_operativo/crud.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.leasing_operativo.models import (
    LeasingOpActivoDepreciacion,
    LeasingOpActivoFijo,
    LeasingOpComite,
    LeasingOpContrato,
    LeasingOpCostoPlantilla,
    LeasingOpCuota,
    LeasingOpHistorial,
    LeasingOpPolitica,
    LeasingOpSimulacion,
    LeasingOpTipoActivo,
)
from services.leasing_operativo.economic_engine import merge_politica, run_economic_engine


def _add_months(d: date, months: int) -> date:
    m0 = d.month - 1 + months
    y = d.year + m0 // 12
    m = m0 % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def listar_politica(db: Session) -> list[LeasingOpPolitica]:
    return list(db.scalars(select(LeasingOpPolitica).where(LeasingOpPolitica.activo.is_(True))).all())


def listar_tipos_activo(db: Session) -> list[LeasingOpTipoActivo]:
    return list(
        db.scalars(select(LeasingOpTipoActivo).where(LeasingOpTipoActivo.activo.is_(True)).order_by(LeasingOpTipoActivo.nombre)).all()
    )


def obtener_tipo(db: Session, tipo_id: int) -> LeasingOpTipoActivo | None:
    return db.get(LeasingOpTipoActivo, tipo_id)


def plantillas_por_tipo(db: Session, tipo_id: int) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(LeasingOpCostoPlantilla)
            .where(LeasingOpCostoPlantilla.tipo_activo_id == tipo_id)
            .order_by(LeasingOpCostoPlantilla.orden, LeasingOpCostoPlantilla.id)
        ).all()
    )
    return [
        {
            "codigo": r.codigo,
            "descripcion": r.descripcion,
            "periodicidad": r.periodicidad,
            "monto_mensual_equiv": float(r.monto_mensual_equiv),
        }
        for r in rows
    ]


def obtener_simulacion(db: Session, sid: int) -> LeasingOpSimulacion | None:
    stmt = (
        select(LeasingOpSimulacion)
        .options(
            selectinload(LeasingOpSimulacion.tipo),
            selectinload(LeasingOpSimulacion.cliente),
            selectinload(LeasingOpSimulacion.comites),
            selectinload(LeasingOpSimulacion.historial),
            selectinload(LeasingOpSimulacion.contrato).selectinload(LeasingOpContrato.cuotas),
        )
        .where(LeasingOpSimulacion.id == sid)
    )
    return db.scalars(stmt).first()


def listar_simulaciones(db: Session, limit: int = 200) -> list[LeasingOpSimulacion]:
    stmt = (
        select(LeasingOpSimulacion)
        .options(selectinload(LeasingOpSimulacion.tipo), selectinload(LeasingOpSimulacion.cliente))
        .order_by(LeasingOpSimulacion.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def crear_simulacion_y_calcular(
    db: Session,
    *,
    tipo_activo_id: int,
    cliente_id: int | None,
    nombre: str,
    plazo_meses: int,
    escenario: str,
    metodo_pricing: str,
    margen_pct: Any,
    spread_pct: Any,
    tir_objetivo: Any,
    inputs: dict[str, Any],
    usuario: str = "sistema",
) -> LeasingOpSimulacion:
    tipo = obtener_tipo(db, tipo_activo_id)
    if not tipo:
        raise ValueError("Tipo de activo inválido")

    politica_rows = listar_politica(db)
    politica = merge_politica(politica_rows)
    plantillas = plantillas_por_tipo(db, tipo_activo_id)

    inp = dict(inputs)
    inp["plazo_meses"] = plazo_meses
    inp["escenario"] = escenario
    inp["metodo_pricing"] = metodo_pricing
    if margen_pct is not None:
        inp["margen_pct"] = margen_pct
    if spread_pct is not None:
        inp["spread_pct"] = spread_pct
    if tir_objetivo is not None:
        inp["tir_objetivo_anual_pct"] = tir_objetivo

    tipo_d = {
        "residual_base_pct": tipo.residual_base_pct,
        "residual_max_pct": tipo.residual_max_pct,
        "liquidez_factor": tipo.liquidez_factor,
        "obsolescencia_factor": tipo.obsolescencia_factor,
        "desgaste_km_factor": tipo.desgaste_km_factor,
        "desgaste_hora_factor": tipo.desgaste_hora_factor,
        "haircut_residual_pct": tipo.haircut_residual_pct,
    }
    result = run_economic_engine(inputs=inp, tipo_activo=tipo_d, politica=politica, plantillas_costo=plantillas)

    dec = result.get("decision") or {}
    sim = LeasingOpSimulacion(
        codigo=None,
        cliente_id=cliente_id,
        tipo_activo_id=tipo_activo_id,
        nombre=nombre or "Simulación",
        plazo_meses=plazo_meses,
        escenario=escenario,
        metodo_pricing=metodo_pricing,
        margen_pct=margen_pct,
        spread_pct=spread_pct,
        tir_objetivo_anual=tir_objetivo,
        inputs_json=inp,
        result_json=result,
        decision_codigo=str(dec.get("decision_codigo") or "PENDIENTE"),
        decision_detalle=str(dec.get("decision_detalle") or ""),
        estado="COTIZADO",
    )
    db.add(sim)
    db.flush()
    y = datetime.now(timezone.utc).year
    sim.codigo = f"LO-{y}-{int(sim.id):05d}"
    db.add(sim)
    db.flush()
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim.id),
            evento="SIMULACION_CREADA",
            detalle_json={"capex": result.get("capex_total")},
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(sim)
    return sim


def abrir_comite(db: Session, sim: LeasingOpSimulacion, resumen: str, usuario: str = "sistema") -> LeasingOpComite:
    c = LeasingOpComite(simulacion_id=int(sim.id), estado="PENDIENTE", resumen=resumen, analista=usuario)
    sim.estado = "COMITE"
    db.add(c)
    db.add(sim)
    db.flush()
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim.id),
            evento="COMITE_ABIERTO",
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(c)
    return c


def resolver_comite(db: Session, com: LeasingOpComite, decision: str, comentario: str, usuario: str) -> LeasingOpComite:
    com.estado = "RESUELTO"
    com.decision = decision
    com.comentario = comentario
    com.fecha_cierre = datetime.now(timezone.utc)
    com.analista = usuario
    sim = com.simulacion
    if decision == "APROBAR":
        sim.estado = "APROBADO"
    elif decision == "RECHAZAR":
        sim.estado = "RECHAZADO"
    else:
        sim.estado = "COTIZADO"
    db.add(com)
    db.add(sim)
    db.flush()
    db.add(LeasingOpHistorial(simulacion_id=int(sim.id), evento="COMITE_RESUELTO", detalle_json={"decision": decision}, usuario=usuario))
    db.commit()
    db.refresh(com)
    return com


def obtener_comite(db: Session, cid: int) -> LeasingOpComite | None:
    stmt = (
        select(LeasingOpComite)
        .options(
            selectinload(LeasingOpComite.simulacion).selectinload(LeasingOpSimulacion.tipo),
            selectinload(LeasingOpComite.simulacion).selectinload(LeasingOpSimulacion.cliente),
        )
        .where(LeasingOpComite.id == cid)
    )
    return db.scalars(stmt).first()


def obtener_contrato_por_simulacion(db: Session, sim_id: int) -> LeasingOpContrato | None:
    return db.scalars(select(LeasingOpContrato).where(LeasingOpContrato.simulacion_id == sim_id)).first()


def obtener_contrato(db: Session, cid: int) -> LeasingOpContrato | None:
    stmt = (
        select(LeasingOpContrato)
        .options(
            selectinload(LeasingOpContrato.simulacion).selectinload(LeasingOpSimulacion.tipo),
            selectinload(LeasingOpContrato.simulacion).selectinload(LeasingOpSimulacion.cliente),
            selectinload(LeasingOpContrato.cuotas),
        )
        .where(LeasingOpContrato.id == cid)
    )
    return db.scalars(stmt).first()


def listar_contratos_cartera(db: Session, limit: int = 300) -> list[LeasingOpContrato]:
    stmt = (
        select(LeasingOpContrato)
        .options(
            selectinload(LeasingOpContrato.simulacion).selectinload(LeasingOpSimulacion.tipo),
            selectinload(LeasingOpContrato.simulacion).selectinload(LeasingOpSimulacion.cliente),
        )
        .order_by(LeasingOpContrato.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def crear_contrato_y_cuotas(
    db: Session,
    sim: LeasingOpSimulacion,
    *,
    usuario: str = "sistema",
    fecha_inicio: date | None = None,
) -> LeasingOpContrato:
    if sim.estado != "APROBADO":
        raise ValueError("Solo operaciones en estado APROBADO pueden generar contrato.")
    if obtener_contrato_por_simulacion(db, int(sim.id)):
        raise ValueError("Ya existe un contrato vinculado a esta simulación.")
    res = sim.result_json or {}
    renta = Decimal(str(res.get("renta_sugerida") or "0"))
    if renta <= 0:
        raise ValueError("Resultado sin renta sugerida válida; recalcule la simulación.")
    n = max(int(sim.plazo_meses), 1)
    fi = fecha_inicio or datetime.now(timezone.utc).date()
    ctr = LeasingOpContrato(
        simulacion_id=int(sim.id),
        codigo="",
        plazo_meses=n,
        renta_mensual=renta,
        fecha_inicio=fi,
        estado="VIGENTE",
    )
    db.add(ctr)
    db.flush()
    y = datetime.now(timezone.utc).year
    ctr.codigo = f"LOC-{y}-{int(ctr.id):05d}"
    for k in range(1, n + 1):
        fv = _add_months(fi, k)
        db.add(
            LeasingOpCuota(
                contrato_id=int(ctr.id),
                nro=k,
                fecha_vencimiento=fv,
                monto_renta=renta,
                estado="PENDIENTE",
            )
        )
    sim.estado = "CONTRATO"
    db.add(sim)
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim.id),
            evento="CONTRATO_CREADO",
            detalle_json={"contrato_id": int(ctr.id), "codigo": ctr.codigo, "cuotas": n},
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(ctr)
    return ctr


def listar_comite_pendiente(db: Session, limit: int = 100) -> list[LeasingOpComite]:
    stmt = (
        select(LeasingOpComite)
        .options(selectinload(LeasingOpComite.simulacion).selectinload(LeasingOpSimulacion.cliente))
        .where(LeasingOpComite.estado == "PENDIENTE")
        .order_by(LeasingOpComite.fecha_apertura.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def listar_activos_fijos(db: Session, limit: int = 300) -> list[LeasingOpActivoFijo]:
    stmt = (
        select(LeasingOpActivoFijo)
        .options(selectinload(LeasingOpActivoFijo.tipo))
        .order_by(LeasingOpActivoFijo.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def obtener_activo_fijo(db: Session, aid: int) -> LeasingOpActivoFijo | None:
    stmt = (
        select(LeasingOpActivoFijo)
        .options(selectinload(LeasingOpActivoFijo.tipo), selectinload(LeasingOpActivoFijo.depreciaciones))
        .where(LeasingOpActivoFijo.id == aid)
    )
    return db.scalars(stmt).first()


def crear_activo_fijo(
    db: Session,
    *,
    tipo_activo_id: int | None,
    marca: str,
    modelo: str,
    anio: int,
    vin_serie: str | None,
    fecha_compra: date,
    costo_compra: Decimal,
    valor_residual_esperado: Decimal,
    vida_util_meses_sii: int,
) -> LeasingOpActivoFijo:
    vida = max(int(vida_util_meses_sii or 60), 1)
    dep_m = ((costo_compra - valor_residual_esperado) / Decimal(vida)).quantize(Decimal("0.0001"))
    dep_m = max(dep_m, Decimal("0"))
    af = LeasingOpActivoFijo(
        codigo="",
        tipo_activo_id=tipo_activo_id,
        marca=(marca or "").strip(),
        modelo=(modelo or "").strip(),
        anio=anio,
        vin_serie=(vin_serie or "").strip() or None,
        fecha_compra=fecha_compra,
        costo_compra=costo_compra,
        valor_residual_esperado=valor_residual_esperado,
        vida_util_meses_sii=vida,
        depreciacion_mensual_sii=dep_m,
        valor_libro=costo_compra,
        estado="DISPONIBLE",
    )
    db.add(af)
    db.flush()
    y = datetime.now(timezone.utc).year
    af.codigo = f"AFLO-{y}-{int(af.id):05d}"
    db.add(af)
    db.commit()
    db.refresh(af)
    return af


def generar_depreciacion_mensual_activo(
    db: Session,
    *,
    activo: LeasingOpActivoFijo,
    periodo_yyyymm: str,
    asiento_ref: str | None = None,
) -> LeasingOpActivoDepreciacion:
    periodo = (periodo_yyyymm or "").strip()
    if len(periodo) != 6 or not periodo.isdigit():
        raise ValueError("Periodo inválido. Use formato YYYYMM.")
    existing = db.scalars(
        select(LeasingOpActivoDepreciacion).where(
            LeasingOpActivoDepreciacion.activo_id == int(activo.id),
            LeasingOpActivoDepreciacion.periodo_yyyymm == periodo,
        )
    ).first()
    if existing:
        raise ValueError("Ya existe depreciación para ese periodo.")
    dep = Decimal(str(activo.depreciacion_mensual_sii or 0))
    if dep <= 0:
        raise ValueError("Activo sin depreciación mensual configurada.")
    nuevo_libro = (Decimal(str(activo.valor_libro)) - dep).quantize(Decimal("0.0001"))
    if nuevo_libro < Decimal("0"):
        nuevo_libro = Decimal("0")
    row = LeasingOpActivoDepreciacion(
        activo_id=int(activo.id),
        periodo_yyyymm=periodo,
        depreciacion_mes=dep,
        valor_libro_cierre=nuevo_libro,
        asiento_ref=(asiento_ref or "").strip() or None,
    )
    activo.valor_libro = nuevo_libro
    db.add(row)
    db.add(activo)
    db.commit()
    db.refresh(row)
    return row
