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
    LeasingOpParametroTipo,
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


def _default_perfil_param() -> dict[str, Any]:
    return {
        "uso": {"km_anual": 80000, "horas_anual": 0},
        "activo": {
            "marca_modelo_factor": 1,
            "sector_economico_mult": 1,
            "inflacion_activo_pct_anual": 3,
            "condicion_factor": 1,
        },
        "collateral": {
            "descuento_venta_forzada_pct": 12,
            "meses_liquidacion": 4,
            "tasa_fin_liquidacion_mensual": 0.008,
            "costo_repossession": 0,
            "costo_legal": 0,
            "transporte": 0,
            "reacondicionamiento": 0,
        },
        "riesgo": {
            "segmento_cliente": "MEDIO",
            "sector_mult": 1,
            "activo_mult": 1,
            "uso_intensivo_mult": 1,
            "liquidez_mult": 1,
        },
        "comercial": {
            "comision_vendedor": 0,
            "comision_canal": 0,
            "costo_adquisicion": 0,
            "evaluacion": 0,
            "legal": 0,
            "onboarding": 0,
        },
    }


def _json_safe(v: Any) -> Any:
    """Convierte valores a tipos serializables para JSONB."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_json_safe(x) for x in v]
    if isinstance(v, tuple):
        return [_json_safe(x) for x in v]
    return v


def _workflow_default() -> dict[str, Any]:
    return {
        "etapa_actual": "COTIZACION",
        "hitos": {
            "cotizacion_emitida": True,
            "analisis_credito": False,
            "resultado_credito": False,
            "contrato_confeccionado": False,
            "orden_compra_proveedor": False,
            "acta_entrega_recepcion": False,
            "factura_compra_recepcion": False,
            "activacion_contable": False,
        },
        "checklist_documental": {
            "cotizacion": True,
            "aprobacion_credito": False,
            "orden_compra": False,
            "acta_entrega_firmada": False,
            "factura_compra": False,
            "activacion_contable": False,
        },
        "credito": {
            "dictamen": "PENDIENTE",
            "score": None,
            "dscr": None,
            "dpd_max": None,
            "comentario": "",
        },
    }


def _get_workflow(sim: LeasingOpSimulacion) -> dict[str, Any]:
    rj = sim.result_json or {}
    wf = rj.get("workflow_v1") if isinstance(rj, dict) else None
    base = _workflow_default()
    if isinstance(wf, dict):
        # merge shallow controlado
        for k in ("etapa_actual",):
            if k in wf:
                base[k] = wf[k]
        for k in ("hitos", "checklist_documental", "credito"):
            if isinstance(wf.get(k), dict):
                base[k].update(wf[k])
    return base


def _save_workflow(db: Session, sim: LeasingOpSimulacion, wf: dict[str, Any], usuario: str, evento: str, detalle: dict[str, Any] | None = None) -> LeasingOpSimulacion:
    rj = dict(sim.result_json or {})
    rj["workflow_v1"] = _json_safe(wf)
    sim.result_json = rj
    db.add(sim)
    db.flush()
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim.id),
            evento=evento,
            detalle_json=_json_safe(detalle or {}),
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(sim)
    return sim


def listar_politica(db: Session) -> list[LeasingOpPolitica]:
    return list(db.scalars(select(LeasingOpPolitica).where(LeasingOpPolitica.activo.is_(True))).all())


def listar_tipos_activo(db: Session) -> list[LeasingOpTipoActivo]:
    return list(
        db.scalars(select(LeasingOpTipoActivo).where(LeasingOpTipoActivo.activo.is_(True)).order_by(LeasingOpTipoActivo.nombre)).all()
    )


def listar_parametros_tipo(db: Session) -> list[LeasingOpParametroTipo]:
    stmt = select(LeasingOpParametroTipo).order_by(LeasingOpParametroTipo.tipo_activo_id)
    return list(db.scalars(stmt).all())


def asegurar_parametros_tipo_default(db: Session) -> int:
    """Crea filas default faltantes para cada tipo de activo."""
    tipos = listar_tipos_activo(db)
    existentes = {int(x.tipo_activo_id) for x in listar_parametros_tipo(db)}
    created = 0
    for t in tipos:
        tid = int(t.id)
        if tid in existentes:
            continue
        db.add(
            LeasingOpParametroTipo(
                tipo_activo_id=tid,
                moneda="CLP",
                iva_pct=Decimal("19"),
                plazo_default=36,
                spread_default_pct=Decimal("8"),
                margen_default_pct=Decimal("12"),
                tir_default_pct=Decimal("14"),
                perfil_json=_default_perfil_param(),
            )
        )
        created += 1
    if created > 0:
        db.commit()
    return created


def obtener_parametro_tipo(db: Session, tipo_id: int) -> LeasingOpParametroTipo | None:
    stmt = select(LeasingOpParametroTipo).where(LeasingOpParametroTipo.tipo_activo_id == tipo_id)
    return db.scalars(stmt).first()


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


def upsert_parametro_tipo(
    db: Session,
    *,
    tipo_activo_id: int,
    moneda: str,
    iva_pct: Decimal,
    plazo_default: int,
    spread_default_pct: Decimal,
    margen_default_pct: Decimal,
    tir_default_pct: Decimal,
    perfil_json: dict[str, Any],
) -> LeasingOpParametroTipo:
    row = obtener_parametro_tipo(db, tipo_activo_id)
    if not row:
        row = LeasingOpParametroTipo(tipo_activo_id=tipo_activo_id, perfil_json={})
    row.moneda = (moneda or "CLP").upper()
    row.iva_pct = iva_pct
    row.plazo_default = max(int(plazo_default or 36), 1)
    row.spread_default_pct = spread_default_pct
    row.margen_default_pct = margen_default_pct
    row.tir_default_pct = tir_default_pct
    row.perfil_json = perfil_json or {}
    row.actualizado_en = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
    param_tipo = obtener_parametro_tipo(db, tipo_activo_id)
    inp["plazo_meses"] = plazo_meses
    inp["escenario"] = escenario
    inp["metodo_pricing"] = metodo_pricing
    if param_tipo:
        inp.setdefault("moneda", param_tipo.moneda)
        inp.setdefault("iva_pct", float(param_tipo.iva_pct))
        base_perfil = param_tipo.perfil_json or {}
        for k in ("uso", "activo", "collateral", "comercial", "riesgo"):
            if not isinstance(inp.get(k), dict):
                inp[k] = {}
            src = base_perfil.get(k) if isinstance(base_perfil.get(k), dict) else {}
            for ck, cv in src.items():
                if inp[k].get(ck) in (None, "", 0, "0"):
                    inp[k][ck] = cv
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
    inp_json = _json_safe(inp)
    result_json = _json_safe(result)
    result_json["workflow_v1"] = _workflow_default()

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
        inputs_json=inp_json,
        result_json=result_json,
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
            detalle_json={"capex": result_json.get("capex_total")},
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(sim)
    return sim


def registrar_analisis_credito(
    db: Session,
    sim: LeasingOpSimulacion,
    *,
    dictamen: str,
    score: Decimal | None,
    dscr: Decimal | None,
    dpd_max: int | None,
    comentario: str,
    usuario: str = "sistema",
) -> LeasingOpSimulacion:
    wf = _get_workflow(sim)
    d = (dictamen or "").strip().upper()
    if d not in {"APROBAR", "OBSERVAR", "RECHAZAR"}:
        raise ValueError("Dictamen de crédito inválido.")
    wf["credito"] = {
        "dictamen": d,
        "score": float(score) if score is not None else None,
        "dscr": float(dscr) if dscr is not None else None,
        "dpd_max": int(dpd_max) if dpd_max is not None else None,
        "comentario": (comentario or "").strip()[:2000],
    }
    wf["hitos"]["analisis_credito"] = True
    wf["hitos"]["resultado_credito"] = True
    wf["checklist_documental"]["aprobacion_credito"] = d in {"APROBAR", "OBSERVAR"}
    wf["etapa_actual"] = "CREDITO_APROBADO" if d in {"APROBAR", "OBSERVAR"} else "CREDITO_RECHAZADO"
    return _save_workflow(
        db,
        sim,
        wf,
        usuario,
        "ANALISIS_CREDITO_REGISTRADO",
        {"dictamen": d, "score": wf["credito"]["score"], "dscr": wf["credito"]["dscr"], "dpd_max": wf["credito"]["dpd_max"]},
    )


def registrar_hito_operativo(
    db: Session,
    sim: LeasingOpSimulacion,
    *,
    hito: str,
    usuario: str = "sistema",
) -> LeasingOpSimulacion:
    wf = _get_workflow(sim)
    hitos = wf["hitos"]
    docs = wf["checklist_documental"]
    h = (hito or "").strip().lower()
    if h == "orden_compra_proveedor":
        if not hitos.get("resultado_credito"):
            raise ValueError("Primero debe registrarse resultado de crédito.")
        hitos["orden_compra_proveedor"] = True
        docs["orden_compra"] = True
        wf["etapa_actual"] = "ORDEN_COMPRA"
        ev = "ORDEN_COMPRA_REGISTRADA"
    elif h == "acta_entrega_recepcion":
        if not hitos.get("orden_compra_proveedor"):
            raise ValueError("Primero registre orden de compra al proveedor.")
        hitos["acta_entrega_recepcion"] = True
        docs["acta_entrega_firmada"] = True
        wf["etapa_actual"] = "ENTREGA_RECEPCION"
        ev = "ACTA_ENTREGA_RECEPCION_REGISTRADA"
    elif h == "factura_compra_recepcion":
        hitos["factura_compra_recepcion"] = True
        docs["factura_compra"] = True
        wf["etapa_actual"] = "FACTURA_COMPRA"
        ev = "FACTURA_COMPRA_REGISTRADA"
    elif h == "activacion_contable":
        if not hitos.get("contrato_confeccionado"):
            raise ValueError("Primero debe confeccionarse contrato.")
        if not hitos.get("acta_entrega_recepcion"):
            raise ValueError("Primero debe registrarse acta de entrega/recepción.")
        if not hitos.get("factura_compra_recepcion"):
            raise ValueError("Primero debe registrarse recepción de factura de compra.")
        hitos["activacion_contable"] = True
        docs["activacion_contable"] = True
        wf["etapa_actual"] = "ACTIVADO_CONTABLE"
        ev = "CONTRATO_ACTIVADO_CONTABLE"
    else:
        raise ValueError("Hito operativo inválido.")
    return _save_workflow(db, sim, wf, usuario, ev, {"hito": h})


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
    wf = _get_workflow(sim)
    cred = wf.get("credito") or {}
    if str(cred.get("dictamen") or "PENDIENTE").upper() not in {"APROBAR", "OBSERVAR"}:
        raise ValueError("Debe existir análisis de crédito aprobado/observado antes de confeccionar contrato.")
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
    wf["hitos"]["contrato_confeccionado"] = True
    wf["etapa_actual"] = "CONTRATO_CONFECCIONADO"
    docs = wf.get("checklist_documental") or {}
    docs["cotizacion"] = True
    wf["checklist_documental"] = docs
    rj = dict(sim.result_json or {})
    rj["workflow_v1"] = _json_safe(wf)
    sim.result_json = rj
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
