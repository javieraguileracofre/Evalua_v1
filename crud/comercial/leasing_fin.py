# crud/comercial/leasing_fin.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from crud.finanzas.plan_cuentas import obtener_plan_cuenta_por_codigo
from models.comercial.leasing_financiero_cotizacion import (
    LeasingFinancieroCotizacion,
    LeasingFinancieroDocumentoProceso,
    LeasingFinancieroHistorial,
)
from schemas.comercial.leasing_cotizacion import ESTADOS_LF, LeasingCotizacionCreate, LeasingCotizacionUpdate
from services.leasing_financiero_contabilidad import (
    activar_contabilidad_leasing_financiero,
    regenerar_proyeccion_contable,
)

_WORKFLOW_ETAPAS = [
    "ANALISIS_CREDITO",
    "ORDEN_COMPRA",
    "CONTRATO_FIRMADO",
    "ACTA_RECEPCION",
    "ACTIVACION_CONTABLE",
]
_ESTADOS_EDITABLES = ESTADOS_LF - {"ACTIVADA", "VIGENTE"}
_ESTADOS_APROBACION_CREDITO = {"APROBADO", "APROBADA_CONDICIONES"}
_CUENTAS_CONTABLES_REQUERIDAS = ("113701", "210701", "410701", "110201")


def get_cotizacion(db: Session, cotizacion_id: int) -> Optional[LeasingFinancieroCotizacion]:
    stmt = (
        select(LeasingFinancieroCotizacion)
        .options(
            selectinload(LeasingFinancieroCotizacion.cliente),
            selectinload(LeasingFinancieroCotizacion.proyeccion_lineas),
            selectinload(LeasingFinancieroCotizacion.analisis_credito),
        )
        .where(LeasingFinancieroCotizacion.id == cotizacion_id)
    )
    return db.scalars(stmt).first()


def get_cotizaciones(
    db: Session,
    *,
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    ejecutivo: Optional[str] = None,
    moneda: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    limit: int = 200,
) -> List[LeasingFinancieroCotizacion]:
    stmt = select(LeasingFinancieroCotizacion).options(
        selectinload(LeasingFinancieroCotizacion.cliente),
        selectinload(LeasingFinancieroCotizacion.analisis_credito),
    )

    if cliente_id is not None:
        stmt = stmt.where(LeasingFinancieroCotizacion.cliente_id == cliente_id)

    if estado:
        stmt = stmt.where(LeasingFinancieroCotizacion.estado == estado)
    if ejecutivo:
        stmt = stmt.where(LeasingFinancieroCotizacion.ejecutivo.ilike(f"%{ejecutivo}%"))
    if moneda:
        stmt = stmt.where(LeasingFinancieroCotizacion.moneda == moneda.upper())

    if fecha_desde:
        stmt = stmt.where(LeasingFinancieroCotizacion.fecha_cotizacion >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(LeasingFinancieroCotizacion.fecha_cotizacion <= fecha_hasta)

    stmt = stmt.order_by(
        LeasingFinancieroCotizacion.fecha_cotizacion.desc(),
        LeasingFinancieroCotizacion.id.desc(),
    ).limit(limit)

    return list(db.scalars(stmt))


def listar_cotizaciones(db: Session) -> List[LeasingFinancieroCotizacion]:
    return get_cotizaciones(db)


def listar_cotizaciones_por_cliente(db: Session, cliente_id: int) -> List[LeasingFinancieroCotizacion]:
    return get_cotizaciones(db, cliente_id=cliente_id)


def _dump_cotizacion(obj_in: LeasingCotizacionCreate | LeasingCotizacionUpdate, *, creating: bool) -> dict:
    data = obj_in.model_dump(exclude_unset=not creating)
    if "moneda" in data and data["moneda"] is not None:
        data["moneda"] = str(data["moneda"]).strip().upper()
    if "estado" in data and data["estado"] is not None:
        data["estado"] = str(data["estado"]).strip().upper()
        if data["estado"] not in ESTADOS_LF:
            raise ValueError("Estado de leasing financiero inválido.")
    return data


def _registrar_historial(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    tipo_evento: str,
    estado_desde: str | None,
    estado_hasta: str | None,
    comentario: str | None = None,
    usuario: str = "sistema",
    metadata_json: dict[str, Any] | None = None,
) -> None:
    if cotizacion.id is None:
        raise ValueError("No se puede registrar historial sin ID de cotización.")
    db.add(
        LeasingFinancieroHistorial(
            cotizacion_id=int(cotizacion.id),
            tipo_evento=tipo_evento,
            estado_desde=estado_desde,
            estado_hasta=estado_hasta,
            comentario=comentario,
            usuario=(usuario or "sistema").strip() or "sistema",
            metadata_json=metadata_json or {},
        )
    )


def _validar_moneda_y_tipo_cambio(*, moneda: str, uf_valor: object, dolar_valor: object) -> None:
    m = (moneda or "CLP").strip().upper()
    if m not in {"CLP", "USD", "UF"}:
        raise ValueError("Moneda inválida. Use CLP, USD o UF.")
    if m == "USD":
        if dolar_valor is None or Decimal(str(dolar_valor)) <= 0:
            raise ValueError("Para moneda USD debe informar valor dólar mayor a 0.")
    if m == "UF":
        if uf_valor is None or Decimal(str(uf_valor)) <= 0:
            raise ValueError("Para moneda UF debe informar valor UF mayor a 0.")


def crear_cotizacion(db: Session, *, obj_in: LeasingCotizacionCreate) -> LeasingFinancieroCotizacion:
    data = _dump_cotizacion(obj_in, creating=True)
    if data.get("fecha_cotizacion") is None:
        data["fecha_cotizacion"] = date.today()
    _validar_moneda_y_tipo_cambio(
        moneda=str(data.get("moneda") or "CLP"),
        uf_valor=data.get("uf_valor"),
        dolar_valor=data.get("dolar_valor"),
    )

    if not data.get("estado"):
        data["estado"] = "BORRADOR"
    try:
        cot = LeasingFinancieroCotizacion(**data)
        db.add(cot)
        db.flush()

        _registrar_historial(
            db,
            cotizacion=cot,
            tipo_evento="CREACION",
            estado_desde=None,
            estado_hasta=str(data["estado"]),
            comentario="Creación de cotización leasing financiero",
        )

        regenerar_proyeccion_contable(db, cot)

        db.commit()
        db.refresh(cot)
        return get_cotizacion(db, int(cot.id)) or cot
    except Exception:
        db.rollback()
        raise


def actualizar_cotizacion(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    obj_in: LeasingCotizacionUpdate,
) -> LeasingFinancieroCotizacion:
    if str(cotizacion.estado or "").upper() not in _ESTADOS_EDITABLES:
        raise ValueError("No se puede editar una operación activada o vigente.")
    estado_original = str(cotizacion.estado or "").upper()
    update_data = obj_in.model_dump(exclude_unset=True)
    moneda_objetivo = str(update_data.get("moneda") or cotizacion.moneda or "CLP").strip().upper()
    uf_objetivo = update_data.get("uf_valor", cotizacion.uf_valor)
    dolar_objetivo = update_data.get("dolar_valor", cotizacion.dolar_valor)
    _validar_moneda_y_tipo_cambio(
        moneda=moneda_objetivo,
        uf_valor=uf_objetivo,
        dolar_valor=dolar_objetivo,
    )
    if "estado" in update_data and update_data["estado"] is not None:
        update_data["estado"] = str(update_data["estado"]).strip().upper()
    if "moneda" in update_data and update_data["moneda"] is not None:
        update_data["moneda"] = str(update_data["moneda"]).strip().upper()
    if "concesionario" in update_data and update_data["concesionario"] is not None:
        update_data["concesionario"] = update_data["concesionario"].strip() or None
    if "ejecutivo" in update_data and update_data["ejecutivo"] is not None:
        update_data["ejecutivo"] = update_data["ejecutivo"].strip() or None

    for field, value in update_data.items():
        if hasattr(cotizacion, field) and value is not None:
            setattr(cotizacion, field, value)
    estado_nuevo = str(cotizacion.estado or "").upper()
    if estado_nuevo not in ESTADOS_LF:
        raise ValueError("Estado de leasing financiero inválido.")
    if estado_nuevo != estado_original:
        _registrar_historial(
            db,
            cotizacion=cotizacion,
            tipo_evento="CAMBIO_ESTADO",
            estado_desde=estado_original,
            estado_hasta=estado_nuevo,
            comentario="Cambio manual de estado en edición",
        )

    db.add(cotizacion)
    db.commit()
    db.refresh(cotizacion)

    cot = get_cotizacion(db, int(cotizacion.id)) or cotizacion
    regenerar_proyeccion_contable(db, cot)
    db.commit()
    db.refresh(cot)
    return cot


def _workflow_por_defecto() -> dict[str, Any]:
    return {
        "etapa_actual": "ANALISIS_CREDITO",
        "hitos": {
            "analisis_credito": False,
            "orden_compra": False,
            "contrato_firmado": False,
            "acta_recepcion": False,
            "activacion_contable": False,
        },
    }


def obtener_workflow(cotizacion: LeasingFinancieroCotizacion) -> dict[str, Any]:
    raw = cotizacion.workflow_json if isinstance(cotizacion.workflow_json, dict) else {}
    workflow = _workflow_por_defecto()
    workflow.update(raw or {})
    hitos = workflow.get("hitos")
    if not isinstance(hitos, dict):
        hitos = {}
    base_hitos = _workflow_por_defecto()["hitos"]
    base_hitos.update(hitos)
    workflow["hitos"] = base_hitos
    if str(workflow.get("etapa_actual") or "").strip().upper() not in _WORKFLOW_ETAPAS:
        workflow["etapa_actual"] = "ANALISIS_CREDITO"
    return workflow


def _siguiente_etapa(workflow: dict[str, Any]) -> str:
    hitos = workflow.get("hitos") or {}
    if not hitos.get("analisis_credito"):
        return "ANALISIS_CREDITO"
    if not hitos.get("orden_compra"):
        return "ORDEN_COMPRA"
    if not hitos.get("contrato_firmado"):
        return "CONTRATO_FIRMADO"
    if not hitos.get("acta_recepcion"):
        return "ACTA_RECEPCION"
    if not hitos.get("activacion_contable"):
        return "ACTIVACION_CONTABLE"
    return "ACTIVACION_CONTABLE"


def _asegurar_analisis_aprobado(cotizacion: LeasingFinancieroCotizacion) -> None:
    analisis = getattr(cotizacion, "analisis_credito", None)
    rec = str(getattr(analisis, "recomendacion", "") or "").strip().upper()
    if rec not in _ESTADOS_APROBACION_CREDITO:
        raise ValueError("Debe existir análisis de crédito aprobado para avanzar el flujo.")


def listar_documentos_proceso(db: Session, cotizacion_id: int) -> list[LeasingFinancieroDocumentoProceso]:
    stmt = (
        select(LeasingFinancieroDocumentoProceso)
        .where(LeasingFinancieroDocumentoProceso.cotizacion_id == cotizacion_id)
        .order_by(
            LeasingFinancieroDocumentoProceso.modulo.asc(),
            LeasingFinancieroDocumentoProceso.version_n.desc(),
        )
    )
    return list(db.scalars(stmt))


def guardar_documento_proceso(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    modulo: str,
    payload: dict[str, Any],
    usuario: str = "sistema",
) -> LeasingFinancieroDocumentoProceso:
    modulo_norm = str(modulo or "").strip().lower()
    if modulo_norm not in {"orden_compra", "contrato", "acta_recepcion", "factura_proveedor", "pagare", "identidad"}:
        raise ValueError("Módulo de documento inválido.")
    if modulo_norm in {"orden_compra", "contrato", "acta_recepcion", "factura_proveedor", "pagare", "identidad"}:
        _asegurar_analisis_aprobado(cotizacion)

    last_stmt = (
        select(LeasingFinancieroDocumentoProceso)
        .where(
            LeasingFinancieroDocumentoProceso.cotizacion_id == int(cotizacion.id),
            LeasingFinancieroDocumentoProceso.modulo == modulo_norm,
        )
        .order_by(LeasingFinancieroDocumentoProceso.version_n.desc())
        .limit(1)
    )
    prev = db.scalars(last_stmt).first()
    version_n = int(prev.version_n) + 1 if prev else 1
    doc = LeasingFinancieroDocumentoProceso(
        cotizacion_id=int(cotizacion.id),
        modulo=modulo_norm,
        version_n=version_n,
        estado=str((payload or {}).get("estado") or "RECIBIDO").upper(),
        payload_json=payload or {},
        usuario=(usuario or "sistema").strip() or "sistema",
    )
    db.add(doc)

    workflow = obtener_workflow(cotizacion)
    if modulo_norm == "orden_compra":
        workflow["hitos"]["orden_compra"] = True
    elif modulo_norm == "contrato":
        workflow["hitos"]["contrato_firmado"] = True
    elif modulo_norm == "acta_recepcion":
        workflow["hitos"]["acta_recepcion"] = True
    workflow["etapa_actual"] = _siguiente_etapa(workflow)
    cotizacion.workflow_json = workflow
    estado_origen = str(cotizacion.estado or "").upper()
    if str(cotizacion.estado or "").upper() in {"COTIZADA", "EN_ANALISIS_CREDITO", "APROBADA", "APROBADA_CONDICIONES"}:
        cotizacion.estado = "EN_FORMALIZACION"
        if workflow["hitos"]["orden_compra"] and workflow["hitos"]["contrato_firmado"] and workflow["hitos"]["acta_recepcion"]:
            cotizacion.estado = "DOCUMENTACION_COMPLETA"
            if cotizacion.fecha_formalizacion is None:
                cotizacion.fecha_formalizacion = date.today()
    _registrar_historial(
        db,
        cotizacion=cotizacion,
        tipo_evento="DOCUMENTO",
        estado_desde=estado_origen,
        estado_hasta=str(cotizacion.estado or "").upper(),
        comentario=f"Registro documento {modulo_norm}",
        usuario=usuario,
        metadata_json=payload or {},
    )

    db.add(cotizacion)
    db.commit()
    db.refresh(doc)
    return doc


def sincronizar_hito_credito(db: Session, *, cotizacion: LeasingFinancieroCotizacion) -> LeasingFinancieroCotizacion:
    _asegurar_analisis_aprobado(cotizacion)
    workflow = obtener_workflow(cotizacion)
    workflow["hitos"]["analisis_credito"] = True
    workflow["etapa_actual"] = _siguiente_etapa(workflow)
    cotizacion.workflow_json = workflow
    rec = str(getattr(cotizacion.analisis_credito, "recomendacion", "") or "").upper()
    estado_origen = str(cotizacion.estado or "").upper()
    if rec == "APROBADO":
        cotizacion.estado = "APROBADA"
    else:
        cotizacion.estado = "APROBADA_CONDICIONES"
    cotizacion.fecha_aprobacion = date.today()
    _registrar_historial(
        db,
        cotizacion=cotizacion,
        tipo_evento="SCORING",
        estado_desde=estado_origen,
        estado_hasta=str(cotizacion.estado),
        comentario=f"Sincronización de crédito: {rec}",
        metadata_json={"recomendacion": rec},
    )
    db.add(cotizacion)
    db.commit()
    db.refresh(cotizacion)
    return cotizacion


def activar_flujo_contable(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    usuario: str = "sistema",
) -> int:
    workflow = obtener_workflow(cotizacion)
    _asegurar_analisis_aprobado(cotizacion)
    if not workflow["hitos"].get("orden_compra"):
        raise ValueError("Debe registrar orden de compra antes de activar.")
    if not workflow["hitos"].get("contrato_firmado"):
        raise ValueError("Debe registrar contrato firmado antes de activar.")
    if not workflow["hitos"].get("acta_recepcion"):
        raise ValueError("Debe registrar acta de recepción antes de activar.")

    if not cotizacion.monto_financiado or cotizacion.monto_financiado <= 0:
        raise ValueError("Debe informar monto financiado válido antes de activar.")
    if cotizacion.tasa is None:
        raise ValueError("Debe informar tasa válida antes de activar.")
    if Decimal(str(cotizacion.tasa)) <= Decimal("-0.99"):
        raise ValueError("La tasa no puede ser -0.99 o menor.")
    if not cotizacion.plazo or cotizacion.plazo <= 0:
        raise ValueError("Debe informar plazo válido antes de activar.")
    if not cotizacion.fecha_inicio:
        raise ValueError("Debe informar fecha de inicio antes de activar.")
    for codigo in _CUENTAS_CONTABLES_REQUERIDAS:
        cuenta = obtener_plan_cuenta_por_codigo(db, codigo)
        if not cuenta:
            raise ValueError(f"No existe cuenta contable requerida: {codigo}.")
        if str(cuenta.estado or "").upper() != "ACTIVO":
            raise ValueError(f"La cuenta contable requerida {codigo} está inactiva.")

    estado_origen = str(cotizacion.estado or "").upper()
    asiento_id = activar_contabilidad_leasing_financiero(db, cotizacion, usuario=usuario)
    workflow["hitos"]["activacion_contable"] = True
    workflow["etapa_actual"] = "ACTIVACION_CONTABLE"
    cotizacion.workflow_json = workflow
    cotizacion.contrato_activo = True
    cotizacion.estado = "ACTIVADA"
    cotizacion.asiento_id = asiento_id
    cotizacion.fecha_activacion = date.today()
    cotizacion.fecha_vigencia_desde = cotizacion.fecha_inicio
    if cotizacion.numero_operacion is None:
        cotizacion.numero_operacion = f"LF-{int(cotizacion.id):06d}"
    _registrar_historial(
        db,
        cotizacion=cotizacion,
        tipo_evento="ACTIVACION_CONTABLE",
        estado_desde=estado_origen,
        estado_hasta="ACTIVADA",
        comentario=f"Activación contable asiento #{asiento_id}",
        usuario=usuario,
        metadata_json={"asiento_id": asiento_id},
    )
    db.add(cotizacion)
    db.commit()
    return asiento_id


def get_hub_resumen(db: Session) -> dict[str, Any]:
    cotizaciones = get_cotizaciones(db, limit=1000)
    kpis = {
        "abiertas": 0,
        "en_credito": 0,
        "aprobadas": 0,
        "formalizacion": 0,
        "vigentes": 0,
        "rechazadas": 0,
    }
    for c in cotizaciones:
        est = str(c.estado or "").upper()
        if est in {"BORRADOR", "COTIZADA", "EN_ANALISIS_COMERCIAL"}:
            kpis["abiertas"] += 1
        if est == "EN_ANALISIS_CREDITO":
            kpis["en_credito"] += 1
        if est in {"APROBADA", "APROBADA_CONDICIONES"}:
            kpis["aprobadas"] += 1
        if est in {"EN_FORMALIZACION", "DOCUMENTACION_COMPLETA", "ACTIVADA"}:
            kpis["formalizacion"] += 1
        if est == "VIGENTE":
            kpis["vigentes"] += 1
        if est in {"RECHAZADA", "PERDIDA_CLIENTE", "ANULADA"}:
            kpis["rechazadas"] += 1

    pendientes_credito = [c for c in cotizaciones if str(c.estado or "").upper() == "EN_ANALISIS_CREDITO"][:10]
    pendientes_docs = [
        c
        for c in cotizaciones
        if str(c.estado or "").upper() in {"APROBADA", "APROBADA_CONDICIONES", "EN_FORMALIZACION"}
    ][:10]
    pendientes_activacion = [c for c in cotizaciones if str(c.estado or "").upper() == "DOCUMENTACION_COMPLETA"][:10]
    recientes = cotizaciones[:10]
    return {
        "kpis": kpis,
        "recientes": recientes,
        "pendientes_credito": pendientes_credito,
        "pendientes_documentacion": pendientes_docs,
        "pendientes_activacion": pendientes_activacion,
    }


def listar_historial(db: Session, cotizacion_id: int) -> list[LeasingFinancieroHistorial]:
    stmt = (
        select(LeasingFinancieroHistorial)
        .where(LeasingFinancieroHistorial.cotizacion_id == cotizacion_id)
        .order_by(LeasingFinancieroHistorial.created_at.desc())
    )
    return list(db.scalars(stmt))
