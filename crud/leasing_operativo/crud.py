# crud/leasing_operativo/crud.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from crud.comercial import credito_riesgo as crud_cr
from crud.finanzas.cuentas_por_pagar import CuentasPorPagarCRUD
from models.comercial.credito_riesgo import CreditoSolicitud
from models.cobranza.cuentas_por_cobrar import CuentaPorCobrar
from models.finanzas.compras_finanzas import APDocumento
from models.maestros.proveedor import Proveedor
from models.leasing_operativo.models import (
    LeasingOpActivoDepreciacion,
    LeasingOpActivoFijo,
    LeasingOpComite,
    LeasingOpContrato,
    LeasingOpCostoPlantilla,
    LeasingOpCuota,
    LeasingOpDocumentoProceso,
    LeasingOpGestionEvento,
    LeasingOpHistorial,
    LeasingOpParametroTipo,
    LeasingOpPolitica,
    LeasingOpRenovacion,
    LeasingOpSimulacion,
    LeasingOpTipoActivo,
)
from schemas.finanzas.cuentas_por_pagar import DocumentoCreate, DocumentoDetalleCreate
from services.leasing_operativo.cronograma import generar_cronograma_cuotas, resumen_cronograma
from services.leasing_operativo.economic_engine import merge_politica, preparar_inputs_simulacion, run_economic_engine
from services.leasing_operativo.amortizacion import calcular_tabla_amortizacion_operacional, totales_amortizacion_operacional
from services.leasing_operativo.gestion_cartera import (
    procesar_mora_cartera,
    registrar_repossession,
    registrar_remarketing,
    registrar_terminacion_anticipada,
)
from services.leasing_operativo_contabilidad import (
    crear_asiento_desde_config_evento,
    facturar_cuota_individual,
    registrar_asiento_activacion,
    resolver_monto_regla_evento,
)


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


def _recompute_stage(wf: dict[str, Any]) -> str:
    hitos = wf.get("hitos") or {}
    cred = wf.get("credito") or {}
    if hitos.get("activacion_contable"):
        return "ACTIVADO_CONTABLE"
    if hitos.get("factura_compra_recepcion"):
        return "FACTURA_COMPRA"
    if hitos.get("acta_entrega_recepcion"):
        return "ENTREGA_RECEPCION"
    if hitos.get("orden_compra_proveedor"):
        return "ORDEN_COMPRA"
    if hitos.get("contrato_confeccionado"):
        return "CONTRATO_CONFECCIONADO"
    d = str(cred.get("dictamen") or "PENDIENTE").upper()
    if d in {"APROBAR", "OBSERVAR"}:
        return "CREDITO_APROBADO"
    if d == "RECHAZAR":
        return "CREDITO_RECHAZADO"
    if cred.get("solicitud_id"):
        return "CREDITO_EN_EVALUACION"
    return "COTIZACION"


def _monto_from_reglas(reglas: list[dict[str, Any]], lado: str, ord_idx: int, default: Decimal) -> Decimal:
    target = [r for r in reglas if str(r.get("lado") or "").upper() == lado and int(r.get("orden") or 0) == ord_idx]
    return default if target else Decimal("0")


def _resolver_monto_regla_evento(
    *,
    codigo_evento: str,
    regla: dict[str, Any],
    monto_base: Decimal,
    monto_iva: Decimal,
) -> Decimal:
    return resolver_monto_regla_evento(
        codigo_evento=codigo_evento,
        regla=regla,
        monto_base=monto_base,
        monto_iva=monto_iva,
    )


def _crear_asiento_desde_config_evento(
    db: Session,
    *,
    modulo: str,
    submodulo: str,
    tipo_documento: str,
    codigo_evento: str,
    monto_base: Decimal,
    monto_iva: Decimal = Decimal("0"),
    fecha: date | None = None,
    origen_tipo: str,
    origen_id: int,
    glosa: str,
    usuario: str | None = None,
) -> int | None:
    return crear_asiento_desde_config_evento(
        db,
        modulo=modulo,
        submodulo=submodulo,
        tipo_documento=tipo_documento,
        codigo_evento=codigo_evento,
        monto_base=monto_base,
        monto_iva=monto_iva,
        fecha=fecha,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        glosa=glosa,
        usuario=usuario,
    )


def _parse_date_iso(raw: Any) -> date:
    s = str(raw or "").strip()
    if not s:
        return datetime.now(timezone.utc).date()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        return datetime.now(timezone.utc).date()


def _resolve_proveedor_id(db: Session, proveedor_id: Any, proveedor_nombre: Any) -> int | None:
    try:
        pid = int(proveedor_id or 0)
    except Exception:
        pid = 0
    if pid > 0:
        p = db.get(Proveedor, pid)
        return int(p.id) if p else None
    nombre = str(proveedor_nombre or "").strip()
    if not nombre:
        return None
    p = db.scalars(
        select(Proveedor)
        .where(Proveedor.razon_social.ilike(nombre), Proveedor.activo.is_(True))
        .order_by(Proveedor.id.desc())
        .limit(1)
    ).first()
    if p:
        return int(p.id)
    p = db.scalars(
        select(Proveedor)
        .where(Proveedor.razon_social.ilike(f"%{nombre}%"), Proveedor.activo.is_(True))
        .order_by(Proveedor.id.desc())
        .limit(1)
    ).first()
    return int(p.id) if p else None


def _registrar_factura_compra_ap(
    db: Session,
    sim: LeasingOpSimulacion,
    *,
    data: dict[str, Any],
    wf: dict[str, Any],
    usuario: str,
) -> dict[str, Any]:
    out = dict(data or {})
    ap_id = out.get("ap_documento_id")
    if ap_id:
        return out
    docs = wf.get("documentos") or {}
    oc = docs.get("orden_compra") or {}
    proveedor_id = _resolve_proveedor_id(
        db,
        out.get("proveedor_id") or oc.get("proveedor_id"),
        out.get("proveedor_nombre") or oc.get("proveedor_nombre"),
    )
    if not proveedor_id:
        raise ValueError(
            "No se pudo resolver proveedor para registrar factura en CxP. "
            "Seleccione proveedor_id válido o registre proveedor maestro."
        )
    fecha_fact = _parse_date_iso(out.get("fecha_factura"))
    neto = Decimal(str(out.get("neto") or 0))
    iva = Decimal(str(out.get("iva") or 0))
    total = Decimal(str(out.get("total") or 0))
    if total <= 0:
        raise ValueError("Factura de compra inválida: total debe ser mayor a 0.")
    if neto <= 0:
        neto = total - iva
    # idempotencia: evitar doble AP para mismo proveedor+folio
    folio = str(out.get("nro_factura") or f"LOP-{sim.id}").strip()
    ap_exist = db.scalars(
        select(APDocumento)
        .where(APDocumento.proveedor_id == proveedor_id, APDocumento.folio == folio)
        .order_by(APDocumento.id.desc())
        .limit(1)
    ).first()
    if ap_exist:
        out["proveedor_id"] = proveedor_id
        out["ap_documento_id"] = int(ap_exist.id)
        out["ap_asiento_id"] = int(ap_exist.asiento_id) if getattr(ap_exist, "asiento_id", None) else None
        return out
    payload = DocumentoCreate(
        proveedor_id=proveedor_id,
        tipo="FACTURA",
        folio=folio,
        fecha_emision=fecha_fact,
        fecha_recepcion=fecha_fact,
        fecha_vencimiento=_add_months(fecha_fact, 1),
        moneda="CLP",
        tipo_cambio=Decimal("1"),
        es_exento="NO" if iva > 0 else "SI",
        referencia=f"LOP {sim.codigo or sim.id}",
        observaciones=f"Compra activo leasing operativo {sim.codigo or sim.id}",
        detalles=[
            DocumentoDetalleCreate(
                descripcion=f"Compra activo leasing operativo {sim.codigo or sim.id}",
                cantidad=Decimal("1"),
                precio_unitario=neto,
                descuento=Decimal("0"),
                categoria_gasto_id=None,
                centro_costo_id=None,
            )
        ],
        impuestos=[],
        tipo_compra_contable="INVENTARIO",
        cuenta_gasto_codigo=None,
        cuenta_proveedores_codigo=None,
        generar_asiento_contable=True,
    )
    ap = CuentasPorPagarCRUD().create_documento(db, payload, user_email=usuario)
    out["proveedor_id"] = proveedor_id
    out["ap_documento_id"] = int(ap.id)
    out["ap_asiento_id"] = int(ap.asiento_id) if getattr(ap, "asiento_id", None) else None
    return out


def _vincular_activos_operacion(
    db: Session,
    sim: LeasingOpSimulacion,
    *,
    contrato: LeasingOpContrato,
    usuario: str,
) -> int:
    """Vincula activos creados en OC a contrato/cliente y marca ARRENDADO."""
    wf = _get_workflow(sim)
    docs = wf.get("documentos") or {}
    oc = docs.get("orden_compra") or {}
    activo_id = oc.get("activo_fijo_id")
    vinculados = 0
    targets: list[int] = []
    if activo_id:
        targets.append(int(activo_id))
    for af in db.scalars(
        select(LeasingOpActivoFijo).where(LeasingOpActivoFijo.simulacion_id == int(sim.id))
    ).all():
        if int(af.id) not in targets:
            targets.append(int(af.id))
    for aid in targets:
        af = db.get(LeasingOpActivoFijo, aid)
        if not af:
            continue
        af.simulacion_id = int(sim.id)
        af.contrato_id = int(contrato.id)
        af.cliente_id = int(sim.cliente_id) if sim.cliente_id else None
        af.estado = "ARRENDADO"
        db.add(af)
        vinculados += 1
    if vinculados:
        db.add(
            LeasingOpHistorial(
                simulacion_id=int(sim.id),
                evento="ACTIVOS_VINCULADOS_CONTRATO",
                detalle_json={"contrato_id": int(contrato.id), "activos": targets},
                usuario=usuario,
            )
        )
    return vinculados


def _registrar_cxc_contrato_legacy_cleanup(db: Session, sim: LeasingOpSimulacion) -> int:
    """Elimina CxC anticipadas del modelo anterior (LOP_CONTRATO) para evitar duplicidad."""
    if not sim.cliente_id:
        return 0
    rows = list(
        db.scalars(
            select(CuentaPorCobrar).where(
                CuentaPorCobrar.cliente_id == int(sim.cliente_id),
                CuentaPorCobrar.observacion.like("LOP_CONTRATO:%"),
            )
        ).all()
    )
    removed = 0
    for r in rows:
        if Decimal(str(r.saldo_pendiente or 0)) >= Decimal(str(r.monto_original or 0)):
            db.delete(r)
            removed += 1
    return removed


def facturar_cuotas_periodo(
    db: Session,
    contrato: LeasingOpContrato,
    *,
    periodo_yyyymm: str,
    usuario: str = "sistema",
) -> dict[str, Any]:
    periodo = (periodo_yyyymm or "").strip()
    if len(periodo) != 6 or not periodo.isdigit():
        raise ValueError("Periodo inválido. Use formato YYYYMM.")
    y = int(periodo[:4])
    m = int(periodo[4:6])
    if m < 1 or m > 12:
        raise ValueError("Periodo inválido. Mes debe estar entre 01 y 12.")
    sim = contrato.simulacion
    if not sim or not sim.cliente_id:
        raise ValueError("Contrato sin simulación/cliente; no se puede facturar.")
    iva_pct = Decimal(str((sim.result_json or {}).get("iva_pct") or 0))
    created = 0
    asiento_ids: list[int] = []
    detalle_cuotas: list[dict[str, Any]] = []
    for q in contrato.cuotas or []:
        if q.fecha_vencimiento.year != y or q.fecha_vencimiento.month != m:
            continue
        out = facturar_cuota_individual(
            db,
            contrato=contrato,
            cuota=q,
            sim=sim,
            iva_pct=iva_pct,
            usuario=usuario,
        )
        if not out:
            continue
        created += 1
        detalle_cuotas.append(out)
        if out.get("asiento_id"):
            asiento_ids.append(int(out["asiento_id"]))
    if created == 0:
        return {"periodo": periodo, "cuotas_facturadas": 0, "asientos": []}
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim.id),
            evento="FACTURACION_MENSUAL_GENERADA",
            detalle_json={"periodo": periodo, "cuotas": created, "asientos": asiento_ids},
            usuario=usuario,
        )
    )
    wf = _get_workflow(sim)
    wf.setdefault("contabilidad", {})["facturacion_mensual"] = {"periodo": periodo, "cuotas": created, "asientos": asiento_ids}
    wf["etapa_actual"] = _recompute_stage(wf)
    rj = dict(sim.result_json or {})
    rj["workflow_v1"] = _json_safe(wf)
    sim.result_json = rj
    db.add(sim)
    db.flush()
    return {"periodo": periodo, "cuotas_facturadas": created, "asientos": asiento_ids}


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


def _dictamen_from_credito_estado(estado: str | None) -> str:
    e = str(estado or "").upper()
    if e == "APROBADA":
        return "APROBAR"
    if e == "RECHAZADA":
        return "RECHAZAR"
    if e == "CONDICIONES":
        return "OBSERVAR"
    return "PENDIENTE"


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


def listar_simulaciones(
    db: Session,
    limit: int = 200,
    *,
    q: str | None = None,
    etapa: str | None = None,
) -> list[LeasingOpSimulacion]:
    stmt = (
        select(LeasingOpSimulacion)
        .options(selectinload(LeasingOpSimulacion.tipo), selectinload(LeasingOpSimulacion.cliente))
        .order_by(LeasingOpSimulacion.id.desc())
        .limit(limit)
    )
    rows = list(db.scalars(stmt).all())
    q_norm = (q or "").strip().lower()
    etapa_norm = (etapa or "").strip().upper()
    if not q_norm and not etapa_norm:
        return rows
    out: list[LeasingOpSimulacion] = []
    for r in rows:
        wf = (r.result_json or {}).get("workflow_v1") or {}
        et = str(wf.get("etapa_actual") or "COTIZACION").upper()
        if etapa_norm and et != etapa_norm:
            continue
        if q_norm:
            blob = " ".join(
                [
                    str(r.codigo or ""),
                    str(r.nombre or ""),
                    str(r.estado or ""),
                    str(r.cliente.razon_social if r.cliente else ""),
                    str(r.tipo.nombre if r.tipo else ""),
                    et,
                ]
            ).lower()
            if q_norm not in blob:
                continue
        out.append(r)
    return out


def segmento_riesgo_cliente(db: Session, cliente_id: int) -> dict[str, Any] | None:
    """Última evaluación de crédito del cliente → segmento LOP."""
    sol = db.scalars(
        select(CreditoSolicitud)
        .where(CreditoSolicitud.cliente_id == int(cliente_id))
        .order_by(CreditoSolicitud.id.desc())
        .limit(1)
    ).first()
    if not sol:
        return None
    evals = list(getattr(sol, "evaluaciones", None) or [])
    score = None
    if evals:
        ult = sorted(evals, key=lambda e: int(getattr(e, "id", 0) or 0), reverse=True)
        score = float(getattr(ult[0], "score_total", 0) or 0)
    elif getattr(sol, "evaluaciones", None) is None:
        from models.comercial.credito_riesgo import CreditoEvaluacion

        ev = db.scalars(
            select(CreditoEvaluacion)
            .where(CreditoEvaluacion.solicitud_id == int(sol.id))
            .order_by(CreditoEvaluacion.id.desc())
            .limit(1)
        ).first()
        if ev:
            score = float(ev.score_total or 0)
    segmento = "MEDIO"
    if score is not None:
        if score >= 700:
            segmento = "BAJO"
        elif score >= 450:
            segmento = "MEDIO"
        elif score >= 300:
            segmento = "ALTO"
        else:
            segmento = "CRITICO"
    estado = str(sol.estado or "").upper()
    if estado in {"RECHAZADA", "RECHAZADO"}:
        segmento = "CRITICO"
    return {
        "cliente_id": int(cliente_id),
        "solicitud_id": int(sol.id),
        "solicitud_codigo": sol.codigo,
        "segmento": segmento,
        "score": score,
        "sector_mult": 1.05 if segmento in {"ALTO", "CRITICO"} else 1.0,
    }


def resimular_operacion(
    db: Session,
    sim: LeasingOpSimulacion,
    *,
    usuario: str = "sistema",
    motivo: str = "RECALCULO",
) -> LeasingOpSimulacion:
    """Re-ejecuta motor v2 y versiona snapshot anterior."""
    tipo = sim.tipo or obtener_tipo(db, int(sim.tipo_activo_id))
    if not tipo:
        raise ValueError("Tipo de activo no encontrado")
    politica = merge_politica(listar_politica(db))
    plantillas = plantillas_por_tipo(db, int(sim.tipo_activo_id))
    inp = dict(sim.inputs_json or {})
    inp = aplicar_segmento_cliente_inputs(db, inp, sim.cliente_id)
    tipo_d = {
        "residual_base_pct": tipo.residual_base_pct,
        "residual_max_pct": tipo.residual_max_pct,
        "liquidez_factor": tipo.liquidez_factor,
        "obsolescencia_factor": tipo.obsolescencia_factor,
        "desgaste_km_factor": tipo.desgaste_km_factor,
        "desgaste_hora_factor": tipo.desgaste_hora_factor,
        "haircut_residual_pct": tipo.haircut_residual_pct,
    }
    prev = sim.result_json or {}
    versions = list(prev.get("result_versions") or [])
    if prev.get("renta_sugerida") is not None:
        versions.append(
            {
                "van": prev.get("van"),
                "tir_anual_pct": prev.get("tir_anual_pct"),
                "renta_sugerida": prev.get("renta_sugerida"),
                "decision": (prev.get("decision") or {}).get("decision_codigo"),
            }
        )
        versions = versions[-8:]
    result = run_economic_engine(inputs=inp, tipo_activo=tipo_d, politica=politica, plantillas_costo=plantillas)
    rj = _json_safe(result)
    wf = prev.get("workflow_v1") or _workflow_default()
    rj["workflow_v1"] = wf
    rj["result_versions"] = versions
    sim.inputs_json = _json_safe(inp)
    sim.result_json = rj
    dec = result.get("decision") or {}
    sim.decision_codigo = str(dec.get("decision_codigo") or sim.decision_codigo)
    sim.decision_detalle = str(dec.get("decision_detalle") or sim.decision_detalle)
    db.add(sim)
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim.id),
            evento=motivo,
            detalle_json={"renta_sugerida": rj.get("renta_sugerida"), "van": rj.get("van")},
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(sim)
    return sim


def aplicar_segmento_cliente_inputs(db: Session, inp: dict[str, Any], cliente_id: int | None) -> dict[str, Any]:
    if not cliente_id:
        return inp
    seg = segmento_riesgo_cliente(db, int(cliente_id))
    if not seg:
        return inp
    riesgo = dict(inp.get("riesgo") or {})
    if not riesgo.get("segmento_cliente"):
        riesgo["segmento_cliente"] = seg["segmento"]
    if riesgo.get("sector_mult") in (None, "", 0, "0", 1, "1", 1.0):
        riesgo["sector_mult"] = seg.get("sector_mult", 1)
    inp["riesgo"] = riesgo
    return inp


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
    indexacion_tipo: str | None = None,
    indexacion_pct: Any | None = None,
    pie_inicial_pct: Any | None = None,
    opcion_compra_pct: Any | None = None,
) -> LeasingOpSimulacion:
    tipo = obtener_tipo(db, tipo_activo_id)
    if not tipo:
        raise ValueError("Tipo de activo inválido")

    politica_rows = listar_politica(db)
    politica = merge_politica(politica_rows)
    plantillas = plantillas_por_tipo(db, tipo_activo_id)
    if not plantillas:
        raise ValueError("El tipo de activo no tiene plantillas de costo operativo configuradas.")

    param_tipo = obtener_parametro_tipo(db, tipo_activo_id)
    inp = preparar_inputs_simulacion(
        inputs=dict(inputs),
        tipo_activo_id=tipo_activo_id,
        param_tipo=param_tipo,
        plazo_meses=plazo_meses,
        escenario=escenario,
        metodo_pricing=metodo_pricing,
        margen_pct=margen_pct,
        spread_pct=spread_pct,
        tir_objetivo=tir_objetivo,
        indexacion_tipo=indexacion_tipo,
        indexacion_pct=indexacion_pct,
        pie_inicial_pct=pie_inicial_pct,
        opcion_compra_pct=opcion_compra_pct,
    )
    inp = aplicar_segmento_cliente_inputs(db, inp, cliente_id)

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


def derivar_a_credito(db: Session, sim: LeasingOpSimulacion, *, usuario: str = "sistema") -> tuple[LeasingOpSimulacion, CreditoSolicitud]:
    wf = _get_workflow(sim)
    cred = wf.get("credito", {})
    solicitud_id = cred.get("solicitud_id")
    if solicitud_id:
        sol = crud_cr.obtener_solicitud(db, int(solicitud_id))
        if sol:
            return sim, sol
    if not sim.cliente_id:
        raise ValueError("La operación requiere cliente para derivar a crédito.")
    res = sim.result_json or {}
    cuota = Decimal(str(res.get("renta_mensual_neta") or res.get("renta_sugerida") or 0))
    capex = Decimal(str(res.get("capex_total") or 0))
    sol = CreditoSolicitud(
        cliente_id=int(sim.cliente_id),
        codigo=None,
        tipo_persona="JURIDICA",
        producto="LEASING_OP",
        sector_actividad=str((sim.inputs_json or {}).get("activo", {}).get("sector") or "TRANSPORTE"),
        moneda=str((sim.inputs_json or {}).get("moneda") or "CLP"),
        monto_solicitado=capex,
        plazo_solicitado=max(int(sim.plazo_meses), 1),
        comercial_lf_cotizacion_id=None,
        ingreso_mensual=Decimal("0"),
        gastos_mensual=Decimal("0"),
        deuda_cuotas_mensual=Decimal("0"),
        cuota_propuesta=cuota,
        tipo_contrato="LEASING_OPERATIVO",
        mora_max_dias_12m=0,
        protestos=0,
        castigos=0,
        reprogramaciones=0,
        ventas_anual=Decimal("0"),
        margen_bruto_pct=Decimal("0"),
        ebitda_anual=Decimal("0"),
        utilidad_neta_anual=Decimal("0"),
        flujo_caja_mensual=Decimal("0"),
        capital_trabajo=Decimal("0"),
        deuda_total=Decimal("0"),
        patrimonio=Decimal("0"),
        liquidez_corriente=None,
        antiguedad_meses_natural=0,
        anios_operacion_empresa=0,
        garantia_tipo="ACTIVO_LEASING",
        garantia_valor_comercial=Decimal(str((res.get("collateral") or {}).get("valor_mercado_estimado") or 0)),
        garantia_valor_liquidacion=Decimal(str((res.get("collateral") or {}).get("valor_recupero_neto") or 0)),
        exposicion_usd_pct=Decimal("0"),
        estado="BORRADOR",
        observaciones=f"Derivada desde LOP {sim.codigo or sim.id}",
    )
    sol = crud_cr.crear_solicitud(db, sol, usuario=usuario)
    cred["solicitud_id"] = int(sol.id)
    cred["solicitud_codigo"] = sol.codigo
    cred["estado_credito"] = sol.estado
    cred["dictamen"] = _dictamen_from_credito_estado(sol.estado)
    wf["credito"] = cred
    wf["etapa_actual"] = "CREDITO_EN_EVALUACION"
    wf["hitos"]["analisis_credito"] = True
    _save_workflow(
        db,
        sim,
        wf,
        usuario,
        "CREDITO_DERIVADO",
        {"solicitud_id": int(sol.id), "solicitud_codigo": sol.codigo},
    )
    return sim, sol


def sincronizar_estado_credito(db: Session, sim: LeasingOpSimulacion, *, usuario: str = "sistema") -> LeasingOpSimulacion:
    wf = _get_workflow(sim)
    cred = wf.get("credito", {})
    sid = cred.get("solicitud_id")
    if not sid:
        return sim
    sol = crud_cr.obtener_solicitud(db, int(sid))
    if not sol:
        return sim
    dictamen = _dictamen_from_credito_estado(sol.estado)
    cred["estado_credito"] = sol.estado
    cred["dictamen"] = dictamen
    cred["solicitud_codigo"] = sol.codigo
    wf["credito"] = cred
    if dictamen in {"APROBAR", "OBSERVAR"}:
        wf["hitos"]["resultado_credito"] = True
        wf["checklist_documental"]["aprobacion_credito"] = True
        wf["etapa_actual"] = "CREDITO_APROBADO"
    elif dictamen == "RECHAZAR":
        wf["hitos"]["resultado_credito"] = True
        wf["checklist_documental"]["aprobacion_credito"] = False
        wf["etapa_actual"] = "CREDITO_RECHAZADO"
    wf["etapa_actual"] = _recompute_stage(wf)
    sim = _save_workflow(db, sim, wf, usuario, "CREDITO_ESTADO_SINCRONIZADO", {"estado_credito": sol.estado, "dictamen": dictamen})
    try:
        return resimular_operacion(db, sim, usuario=usuario, motivo="RECALCULO_POST_CREDITO")
    except Exception:
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
        contrato = obtener_contrato_por_simulacion(db, int(sim.id))
        if not contrato:
            raise ValueError("No existe contrato para activar contablemente.")
        ctr_id = int(contrato.id)
        legacy_removed = _registrar_cxc_contrato_legacy_cleanup(db, sim)
        factura = (wf.get("documentos") or {}).get("factura_compra") or {}
        as_id = registrar_asiento_activacion(
            db, sim, contrato_id=ctr_id, factura_compra=factura, usuario=usuario
        )
        activos_vinc = _vincular_activos_operacion(db, sim, contrato=contrato, usuario=usuario)
        wf.setdefault("contabilidad", {})["modelo_cxc"] = "FACTURACION_MENSUAL"
        wf["contabilidad"]["legacy_cxc_removed"] = legacy_removed
        wf["contabilidad"]["activos_vinculados"] = activos_vinc
        if as_id:
            wf["contabilidad"]["asiento_activacion_id"] = int(as_id)
        ev = "CONTRATO_ACTIVADO_CONTABLE"
    else:
        raise ValueError("Hito operativo inválido.")
    detalle = {"hito": h}
    if h == "activacion_contable":
        detalle["contabilidad"] = wf.get("contabilidad")
    wf["etapa_actual"] = _recompute_stage(wf)
    return _save_workflow(db, sim, wf, usuario, ev, detalle)


def guardar_documento_proceso(
    db: Session,
    sim: LeasingOpSimulacion,
    *,
    modulo: str,
    data: dict[str, Any],
    usuario: str = "sistema",
) -> LeasingOpSimulacion:
    wf = _get_workflow(sim)
    docs = wf.setdefault("documentos", {})
    m = (modulo or "").strip().lower()
    if m not in {"contrato", "orden_compra", "acta_entrega", "factura_compra"}:
        raise ValueError("Módulo documental inválido.")
    hit = wf.setdefault("hitos", {})
    if m == "contrato" and not hit.get("resultado_credito"):
        raise ValueError("Primero debe existir resultado de crédito.")
    if m == "orden_compra" and not hit.get("contrato_confeccionado"):
        raise ValueError("Primero debe confeccionar contrato.")
    if m == "acta_entrega" and not hit.get("orden_compra_proveedor"):
        raise ValueError("Primero debe registrar orden de compra.")
    if m == "factura_compra" and not hit.get("acta_entrega_recepcion"):
        raise ValueError("Primero debe registrar acta de entrega/recepción.")
    clean_data = _json_safe(data) or {}
    if m == "factura_compra":
        clean_data = _registrar_factura_compra_ap(db, sim, data=clean_data, wf=wf, usuario=usuario)
    docs[m] = _json_safe(clean_data)
    wf["documentos"] = docs
    # Persistencia relacional versionada para reimpresión/auditoría.
    ultima = db.scalars(
        select(LeasingOpDocumentoProceso)
        .where(
            LeasingOpDocumentoProceso.simulacion_id == sim.id,
            LeasingOpDocumentoProceso.modulo == m,
        )
        .order_by(LeasingOpDocumentoProceso.version_n.desc())
        .limit(1)
    ).first()
    next_v = int(ultima.version_n) + 1 if ultima else 1
    db.add(
        LeasingOpDocumentoProceso(
            simulacion_id=int(sim.id),
            modulo=m,
            version_n=next_v,
            estado="VIGENTE",
            payload_json=_json_safe(clean_data) or {},
            usuario=usuario,
        )
    )
    # gatillos de checklist/hitos
    if m == "contrato":
        wf["hitos"]["contrato_confeccionado"] = True
        wf["etapa_actual"] = "CONTRATO_CONFECCIONADO"
    elif m == "orden_compra":
        wf["hitos"]["orden_compra_proveedor"] = True
        wf["checklist_documental"]["orden_compra"] = True
        wf["etapa_actual"] = "ORDEN_COMPRA"
    elif m == "acta_entrega":
        wf["hitos"]["acta_entrega_recepcion"] = True
        wf["checklist_documental"]["acta_entrega_firmada"] = True
        wf["etapa_actual"] = "ENTREGA_RECEPCION"
    elif m == "factura_compra":
        wf["hitos"]["factura_compra_recepcion"] = True
        wf["checklist_documental"]["factura_compra"] = True
        wf["etapa_actual"] = "FACTURA_COMPRA"
    wf["etapa_actual"] = _recompute_stage(wf)
    return _save_workflow(db, sim, wf, usuario, f"DOC_{m.upper()}_GUARDADO", {"modulo": m, "data": clean_data})


def obtener_documento_proceso_actual(
    db: Session,
    sim_id: int,
    modulo: str,
) -> LeasingOpDocumentoProceso | None:
    m = (modulo or "").strip().lower()
    if m not in {"contrato", "orden_compra", "acta_entrega", "factura_compra"}:
        return None
    return db.scalars(
        select(LeasingOpDocumentoProceso)
        .where(
            LeasingOpDocumentoProceso.simulacion_id == sim_id,
            LeasingOpDocumentoProceso.modulo == m,
        )
        .order_by(LeasingOpDocumentoProceso.version_n.desc())
        .limit(1)
    ).first()


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
    wf = _get_workflow(sim)
    wf["etapa_actual"] = _recompute_stage(wf)
    rj = dict(sim.result_json or {})
    rj["workflow_v1"] = _json_safe(wf)
    sim.result_json = rj
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
            selectinload(LeasingOpContrato.gestion_eventos),
            selectinload(LeasingOpContrato.activos),
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
    indexacion_tipo: str | None = None,
    indexacion_pct: Decimal | None = None,
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
    inp = sim.inputs_json or {}
    renta = Decimal(str(res.get("renta_sugerida") or "0"))
    if renta <= 0:
        raise ValueError("Resultado sin renta sugerida válida; recalcule la simulación.")
    moneda = str(inp.get("moneda") or res.get("moneda_cotizacion") or "CLP").upper()
    idx_tipo = (indexacion_tipo or inp.get("indexacion_tipo") or "NINGUNA").strip().upper()
    if idx_tipo not in {"NINGUNA", "UF", "IPC"}:
        idx_tipo = "NINGUNA"
    idx_pct = indexacion_pct if indexacion_pct is not None else Decimal(str(inp.get("indexacion_pct") or 0))
    n = max(int(sim.plazo_meses), 1)
    fi = fecha_inicio or datetime.now(timezone.utc).date()
    cronograma = generar_cronograma_cuotas(
        plazo_meses=n,
        renta_base=renta,
        fecha_inicio=fi,
        indexacion_tipo=idx_tipo,
        indexacion_pct=idx_pct,
    )
    piso = Decimal(str(res.get("renta_minima_pico") or res.get("renta_minima") or 0))
    if cronograma and piso > 0:
        primera = Decimal(str(cronograma[0]["monto_renta"]))
        if primera < piso:
            raise ValueError(
                f"Renta indexada del cronograma ({primera:,.0f}) es inferior al piso comercial ({piso:,.0f}). "
                "Recalcule la simulación o ajuste indexación/pricing."
            )
    ctr = LeasingOpContrato(
        simulacion_id=int(sim.id),
        codigo="",
        plazo_meses=n,
        renta_mensual=renta,
        moneda=moneda,
        indexacion_tipo=idx_tipo,
        indexacion_pct=idx_pct,
        fecha_inicio=fi,
        estado="VIGENTE",
    )
    db.add(ctr)
    db.flush()
    y = datetime.now(timezone.utc).year
    ctr.codigo = f"LOC-{y}-{int(ctr.id):05d}"
    for row in cronograma:
        db.add(
            LeasingOpCuota(
                contrato_id=int(ctr.id),
                nro=int(row["nro"]),
                fecha_vencimiento=row["fecha_vencimiento"],
                monto_renta=Decimal(str(row["monto_renta"])),
                monto_renta_base=Decimal(str(row["monto_renta_base"])),
                estado="PENDIENTE",
            )
        )
    sim.estado = "CONTRATO"
    wf["hitos"]["contrato_confeccionado"] = True
    wf["etapa_actual"] = "CONTRATO_CONFECCIONADO"
    docs = wf.get("checklist_documental") or {}
    docs["cotizacion"] = True
    wf["checklist_documental"] = docs
    wf["cronograma_resumen"] = _json_safe(resumen_cronograma(cronograma))
    rj = dict(sim.result_json or {})
    wf["etapa_actual"] = _recompute_stage(wf)
    rj["workflow_v1"] = _json_safe(wf)
    sim.result_json = rj
    db.add(sim)
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim.id),
            evento="CONTRATO_CREADO",
            detalle_json={
                "contrato_id": int(ctr.id),
                "codigo": ctr.codigo,
                "cuotas": n,
                "indexacion_tipo": idx_tipo,
                "indexacion_pct": float(idx_pct),
                "cronograma": wf.get("cronograma_resumen"),
            },
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
    simulacion_id: int | None = None,
    contrato_id: int | None = None,
    cliente_id: int | None = None,
) -> LeasingOpActivoFijo:
    vida = max(int(vida_util_meses_sii or 60), 1)
    dep_m = ((costo_compra - valor_residual_esperado) / Decimal(vida)).quantize(Decimal("0.0001"))
    dep_m = max(dep_m, Decimal("0"))
    af = LeasingOpActivoFijo(
        codigo="",
        tipo_activo_id=tipo_activo_id,
        simulacion_id=simulacion_id,
        contrato_id=contrato_id,
        cliente_id=cliente_id,
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
        estado="ARRENDADO" if contrato_id else "DISPONIBLE",
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
    usuario: str = "sistema",
) -> LeasingOpActivoDepreciacion:
    periodo = (periodo_yyyymm or "").strip()
    if len(periodo) != 6 or not periodo.isdigit():
        raise ValueError("Periodo inválido. Use formato YYYYMM.")
    y = int(periodo[:4])
    m = int(periodo[4:6])
    if m < 1 or m > 12:
        raise ValueError("Periodo inválido. Mes debe estar entre 01 y 12.")
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
    if not row.asiento_ref:
        as_id = _crear_asiento_desde_config_evento(
            db,
            modulo="LEASING_OP",
            submodulo="DEPRECIACION",
            tipo_documento="ACTIVO_FIJO",
            codigo_evento="LOP_DEPRECIACION",
            monto_base=dep,
            monto_iva=Decimal("0"),
            fecha=date(y, m, 1),
            origen_tipo="LOP_DEPRECIACION",
            origen_id=int(activo.id),
            glosa=f"Depreciación activo {activo.codigo} periodo {periodo}",
            usuario=usuario,
        )
        if as_id:
            row.asiento_ref = str(as_id)
    activo.valor_libro = nuevo_libro
    db.add(row)
    db.add(activo)
    db.commit()
    db.refresh(row)
    return row


def get_hub_resumen(db: Session) -> dict[str, Any]:
    """KPIs del pipeline LOP para hub operativo."""
    sims = listar_simulaciones(db, limit=1000)
    contratos = listar_contratos_cartera(db, limit=1000)
    kpis = {
        "abiertas": 0,
        "en_credito": 0,
        "aprobadas": 0,
        "formalizacion": 0,
        "vigentes": 0,
        "rechazadas": 0,
        "activadas": 0,
        "total": len(sims),
    }
    pipeline_montos: dict[str, Decimal] = {"CLP": Decimal("0"), "UF": Decimal("0"), "USD": Decimal("0")}
    cartera_montos: dict[str, Decimal] = {"CLP": Decimal("0"), "UF": Decimal("0"), "USD": Decimal("0")}
    pendientes_credito: list[LeasingOpSimulacion] = []
    pendientes_documentacion: list[LeasingOpSimulacion] = []
    pendientes_activacion: list[LeasingOpSimulacion] = []

    for s in sims:
        wf = (s.result_json or {}).get("workflow_v1") or {}
        et = str(wf.get("etapa_actual") or "COTIZACION").upper()
        cred = wf.get("credito") or {}
        hitos = wf.get("hitos") or {}
        moneda = str((s.inputs_json or {}).get("moneda") or "CLP").upper()
        if moneda not in pipeline_montos:
            moneda = "CLP"
        capex = Decimal(str((s.result_json or {}).get("capex_total") or 0))

        if et in {"COTIZACION", "CREDITO_RECHAZADO"}:
            kpis["abiertas"] += 1
        elif et == "CREDITO_EN_EVALUACION":
            kpis["en_credito"] += 1
            if len(pendientes_credito) < 8:
                pendientes_credito.append(s)
        elif et == "CREDITO_APROBADO":
            kpis["aprobadas"] += 1
        elif et in {"CONTRATO_CONFECCIONADO", "ORDEN_COMPRA", "ENTREGA_RECEPCION", "FACTURA_COMPRA"}:
            kpis["formalizacion"] += 1
            if len(pendientes_documentacion) < 8:
                pendientes_documentacion.append(s)
        elif et == "ACTIVADO_CONTABLE":
            kpis["activadas"] += 1
        if str(cred.get("dictamen") or "").upper() == "RECHAZAR":
            kpis["rechazadas"] += 1

        if et != "ACTIVADO_CONTABLE" and capex > 0:
            pipeline_montos[moneda] += capex
        if hitos.get("contrato_confeccionado") and not hitos.get("activacion_contable"):
            if len(pendientes_activacion) < 8:
                pendientes_activacion.append(s)

    for c in contratos:
        if str(c.estado or "").upper() != "VIGENTE":
            continue
        kpis["vigentes"] += 1
        sim = c.simulacion
        moneda = str(getattr(c, "moneda", None) or (sim.inputs_json or {}).get("moneda") or "CLP").upper()
        if moneda not in cartera_montos:
            moneda = "CLP"
        total = sum((Decimal(str(q.monto_renta or 0)) for q in (c.cuotas or [])), Decimal("0"))
        cartera_montos[moneda] += total

    cerradas = kpis["activadas"] + kpis["rechazadas"]
    tasa_cierre_pct = (
        Decimal(str(kpis["activadas"])) / Decimal(str(cerradas)) * Decimal("100") if cerradas > 0 else None
    )
    margenes: list[Decimal] = []
    tirs: list[Decimal] = []
    observar = 0
    for s in sims:
        r = s.result_json or {}
        if r.get("margen_operacional_promedio_pct") is not None:
            margenes.append(Decimal(str(r["margen_operacional_promedio_pct"])))
        if r.get("tir_anual_pct") is not None:
            tirs.append(Decimal(str(r["tir_anual_pct"])))
        if str((r.get("decision") or {}).get("decision_codigo") or s.decision_codigo or "").upper() == "OBSERVAR":
            observar += 1
    margen_pipeline = float(sum(margenes, Decimal("0")) / Decimal(len(margenes))) if margenes else None
    tir_pipeline = float(sum(tirs, Decimal("0")) / Decimal(len(tirs))) if tirs else None
    funnel = [
        {"key": "cotizacion", "label": "Cotización", "count": kpis["abiertas"], "hint": "Simulaciones abiertas"},
        {"key": "credito", "label": "Crédito", "count": kpis["en_credito"], "hint": "Evaluación crédito y riesgo"},
        {"key": "aprobacion", "label": "Aprobación", "count": kpis["aprobadas"], "hint": "Listas para formalizar"},
        {"key": "formalizacion", "label": "Docs", "count": kpis["formalizacion"], "hint": "Contrato · OC · entrega · factura"},
        {"key": "cartera", "label": "Cartera", "count": kpis["activadas"], "hint": f"{kpis['vigentes']} contratos vigentes"},
    ]
    return {
        "kpis": kpis,
        "funnel": funnel,
        "pipeline_montos": {k: float(v) for k, v in pipeline_montos.items()},
        "cartera_montos": {k: float(v) for k, v in cartera_montos.items()},
        "tasa_cierre_pct": float(tasa_cierre_pct) if tasa_cierre_pct is not None else None,
        "margen_pipeline_pct": margen_pipeline,
        "tir_pipeline_pct": tir_pipeline,
        "alertas_observar": observar,
        "pendientes_credito": pendientes_credito,
        "pendientes_documentacion": pendientes_documentacion,
        "pendientes_activacion": pendientes_activacion,
        "recientes": sims[:12],
    }


def renovar_contrato(
    db: Session,
    contrato: LeasingOpContrato,
    *,
    plazo_meses: int,
    renta_mensual: Decimal,
    indexacion_tipo: str = "NINGUNA",
    indexacion_pct: Decimal = Decimal("0"),
    motivo: str = "",
    usuario: str = "sistema",
) -> LeasingOpContrato:
    """Renueva contrato vigente: cierra origen y genera nuevo contrato + cuotas."""
    if str(contrato.estado or "").upper() != "VIGENTE":
        raise ValueError("Solo se pueden renovar contratos vigentes.")
    sim_orig = contrato.simulacion
    if not sim_orig:
        raise ValueError("Contrato sin simulación origen.")
    pendientes = [q for q in (contrato.cuotas or []) if str(q.estado or "").upper() == "PENDIENTE"]
    if pendientes:
        raise ValueError("Existen cuotas pendientes de facturar; regularice la cartera antes de renovar.")

    contrato.estado = "RENOVADO"
    db.add(contrato)
    fi = datetime.now(timezone.utc).date()
    idx_tipo = (indexacion_tipo or "NINGUNA").strip().upper()
    if idx_tipo not in {"NINGUNA", "UF", "IPC"}:
        idx_tipo = "NINGUNA"
    n = max(int(plazo_meses), 1)
    renta = Decimal(str(renta_mensual))
    cronograma = generar_cronograma_cuotas(
        plazo_meses=n,
        renta_base=renta,
        fecha_inicio=fi,
        indexacion_tipo=idx_tipo,
        indexacion_pct=indexacion_pct,
    )
    sim_nueva = crear_simulacion_y_calcular(
        db,
        tipo_activo_id=int(sim_orig.tipo_activo_id),
        cliente_id=int(sim_orig.cliente_id) if sim_orig.cliente_id else None,
        nombre=f"Renovación {contrato.codigo}",
        plazo_meses=n,
        escenario=sim_orig.escenario,
        metodo_pricing=sim_orig.metodo_pricing,
        margen_pct=sim_orig.margen_pct,
        spread_pct=sim_orig.spread_pct,
        tir_objetivo=sim_orig.tir_objetivo_anual,
        inputs=dict(sim_orig.inputs_json or {}),
        usuario=usuario,
    )
    sim_nueva.estado = "APROBADO"
    wf = _get_workflow(sim_nueva)
    wf["credito"] = dict((_get_workflow(sim_orig).get("credito") or {}))
    wf["hitos"]["resultado_credito"] = True
    wf["checklist_documental"]["aprobacion_credito"] = True
    wf["etapa_actual"] = "CREDITO_APROBADO"
    rj = dict(sim_nueva.result_json or {})
    rj["workflow_v1"] = _json_safe(wf)
    sim_nueva.result_json = rj
    db.add(sim_nueva)
    db.flush()

    ctr_nuevo = LeasingOpContrato(
        simulacion_id=int(sim_nueva.id),
        codigo="",
        plazo_meses=n,
        renta_mensual=renta,
        moneda=str(getattr(contrato, "moneda", None) or "CLP"),
        indexacion_tipo=idx_tipo,
        indexacion_pct=indexacion_pct,
        contrato_origen_id=int(contrato.id),
        fecha_inicio=fi,
        estado="VIGENTE",
    )
    db.add(ctr_nuevo)
    db.flush()
    y = datetime.now(timezone.utc).year
    ctr_nuevo.codigo = f"LOC-{y}-{int(ctr_nuevo.id):05d}"
    for row in cronograma:
        db.add(
            LeasingOpCuota(
                contrato_id=int(ctr_nuevo.id),
                nro=int(row["nro"]),
                fecha_vencimiento=row["fecha_vencimiento"],
                monto_renta=Decimal(str(row["monto_renta"])),
                monto_renta_base=Decimal(str(row["monto_renta_base"])),
                estado="PENDIENTE",
            )
        )
    sim_nueva.estado = "CONTRATO"
    wf2 = _get_workflow(sim_nueva)
    wf2["hitos"]["contrato_confeccionado"] = True
    wf2["etapa_actual"] = "CONTRATO_CONFECCIONADO"
    rj2 = dict(sim_nueva.result_json or {})
    rj2["workflow_v1"] = _json_safe(wf2)
    sim_nueva.result_json = rj2
    db.add(sim_nueva)

    ren = LeasingOpRenovacion(
        contrato_origen_id=int(contrato.id),
        contrato_nuevo_id=int(ctr_nuevo.id),
        simulacion_nueva_id=int(sim_nueva.id),
        plazo_meses=n,
        renta_mensual=renta,
        indexacion_tipo=idx_tipo,
        indexacion_pct=indexacion_pct,
        motivo=(motivo or "").strip()[:2000],
        usuario=usuario,
    )
    db.add(ren)
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim_orig.id),
            evento="CONTRATO_RENOVADO",
            detalle_json={"contrato_nuevo": ctr_nuevo.codigo, "motivo": motivo},
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(ctr_nuevo)
    return ctr_nuevo


def obtener_politica_merged(db: Session) -> dict[str, dict[str, Any]]:
    return merge_politica(listar_politica(db))


def upsert_politica(
    db: Session,
    *,
    clave: str,
    valor_json: dict[str, Any],
    descripcion: str | None = None,
) -> LeasingOpPolitica:
    k = (clave or "").strip()
    if not k:
        raise ValueError("Clave de política requerida.")
    row = db.scalars(select(LeasingOpPolitica).where(LeasingOpPolitica.clave == k).limit(1)).first()
    if not row:
        row = LeasingOpPolitica(clave=k, valor_json={}, descripcion="")
    row.valor_json = _json_safe(valor_json) or {}
    if descripcion is not None:
        row.descripcion = (descripcion or "").strip()
    row.updated_at = datetime.now(timezone.utc)
    row.activo = True
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def obtener_tabla_amortizacion_sim(db: Session, sim_id: int) -> tuple[list[Any], dict[str, Decimal]]:
    sim = obtener_simulacion(db, sim_id)
    if not sim:
        raise ValueError("Simulación no encontrada.")
    res = sim.result_json or {}
    vr = res.get("valor_residual") or {}
    residual = Decimal(str(vr.get("valor_residual_ajustado") or 0))
    fi = None
    if sim.contrato:
        fi = sim.contrato.fecha_inicio
    tabla = calcular_tabla_amortizacion_operacional(
        capex_total=Decimal(str(res.get("capex_total") or 0)),
        valor_residual=residual,
        plazo_meses=int(sim.plazo_meses),
        flujo_mensual=res.get("flujo_mensual") or [],
        fecha_inicio=fi,
    )
    return tabla, totales_amortizacion_operacional(tabla)


def aplicar_mora_cartera_lop(db: Session, *, usuario: str = "sistema") -> dict[str, Any]:
    politica = obtener_politica_merged(db)
    out = procesar_mora_cartera(db, politica=politica, usuario=usuario)
    db.commit()
    return out


def ejecutar_terminacion_anticipada(
    db: Session,
    contrato: LeasingOpContrato,
    *,
    motivo: str,
    usuario: str = "sistema",
) -> dict[str, Any]:
    sim = contrato.simulacion or obtener_simulacion(db, int(contrato.simulacion_id))
    if not sim:
        raise ValueError("Contrato sin simulación.")
    out = registrar_terminacion_anticipada(
        db, contrato=contrato, sim=sim, politica=obtener_politica_merged(db), motivo=motivo, usuario=usuario
    )
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim.id),
            evento="TERMINACION_ANTICIPADA",
            detalle_json=out,
            usuario=usuario,
        )
    )
    db.commit()
    return out


def ejecutar_repossession(
    db: Session,
    contrato: LeasingOpContrato,
    *,
    motivo: str,
    activo_id: int | None = None,
    usuario: str = "sistema",
) -> LeasingOpGestionEvento:
    sim = contrato.simulacion or obtener_simulacion(db, int(contrato.simulacion_id))
    if not sim:
        raise ValueError("Contrato sin simulación.")
    ev = registrar_repossession(db, contrato=contrato, sim=sim, motivo=motivo, activo_id=activo_id, usuario=usuario)
    db.add(
        LeasingOpHistorial(
            simulacion_id=int(sim.id),
            evento="REPOSSESSION",
            detalle_json={"contrato_id": int(contrato.id), "motivo": motivo},
            usuario=usuario,
        )
    )
    db.commit()
    db.refresh(ev)
    return ev


def ejecutar_remarketing(
    db: Session,
    contrato: LeasingOpContrato,
    *,
    valor_venta: Decimal,
    comprador: str,
    activo_id: int | None = None,
    costos_remarketing: Decimal = Decimal("0"),
    usuario: str = "sistema",
) -> dict[str, Any]:
    sim = contrato.simulacion or obtener_simulacion(db, int(contrato.simulacion_id))
    out = registrar_remarketing(
        db,
        contrato=contrato,
        valor_venta=valor_venta,
        comprador=comprador,
        activo_id=activo_id,
        costos_remarketing=costos_remarketing,
        usuario=usuario,
    )
    if sim:
        db.add(
            LeasingOpHistorial(
                simulacion_id=int(sim.id),
                evento="REMARKETING",
                detalle_json=out,
                usuario=usuario,
            )
        )
    db.commit()
    return out


def listar_gestion_eventos(db: Session, contrato_id: int, limit: int = 50) -> list[LeasingOpGestionEvento]:
    stmt = (
        select(LeasingOpGestionEvento)
        .where(LeasingOpGestionEvento.contrato_id == contrato_id)
        .order_by(LeasingOpGestionEvento.creado_en.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
