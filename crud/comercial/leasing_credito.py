# crud/comercial/leasing_credito.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.comercial.leasing_financiero_credito import (
    LeasingFinancieroAnalisisCredito,
    LeasingFinancieroCreditoDocumento,
)
from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion, LeasingFinancieroHistorial
from crud.comercial.leasing_fin_operacion import (
    inicializar_checklist,
    persistir_amortizacion_oficial,
    sincronizar_checklist_automatico,
)
from models.maestros.cliente import Cliente
from schemas.comercial.leasing_credito import LeasingCreditoInput, LeasingCreditoResultado


def get_cotizacion(db: Session, cotizacion_id: int) -> LeasingFinancieroCotizacion | None:
    stmt = (
        select(LeasingFinancieroCotizacion)
        .options(
            selectinload(LeasingFinancieroCotizacion.cliente),
            selectinload(LeasingFinancieroCotizacion.analisis_credito),
        )
        .where(LeasingFinancieroCotizacion.id == cotizacion_id)
    )
    return db.scalars(stmt).first()


def listar_documentos(db: Session, cotizacion_id: int) -> list[LeasingFinancieroCreditoDocumento]:
    stmt = (
        select(LeasingFinancieroCreditoDocumento)
        .where(LeasingFinancieroCreditoDocumento.cotizacion_id == cotizacion_id)
        .where(LeasingFinancieroCreditoDocumento.estado != "OBSOLETO")
        .order_by(LeasingFinancieroCreditoDocumento.creado_en.desc())
    )
    return list(db.scalars(stmt))


def crear_documento(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    tipo_documento: str,
    nombre_archivo: str,
    mime_type: str,
    storage_path: str,
    hash_sha256: str | None,
    tamano_bytes: int,
    datos_extraidos: dict[str, Any] | None = None,
    periodo_desde: date | None = None,
    periodo_hasta: date | None = None,
    observaciones: str = "",
    cargado_por: str = "sistema",
) -> LeasingFinancieroCreditoDocumento:
    # Marcar versiones previas del mismo tipo como obsoletas
    prevs = db.scalars(
        select(LeasingFinancieroCreditoDocumento).where(
            LeasingFinancieroCreditoDocumento.cotizacion_id == int(cotizacion.id),
            LeasingFinancieroCreditoDocumento.tipo_documento == tipo_documento,
            LeasingFinancieroCreditoDocumento.estado != "OBSOLETO",
        )
    ).all()
    for prev in prevs:
        prev.estado = "OBSOLETO"
        db.add(prev)

    doc = LeasingFinancieroCreditoDocumento(
        cotizacion_id=int(cotizacion.id),
        cliente_id=int(cotizacion.cliente_id),
        tipo_documento=tipo_documento,
        nombre_archivo=nombre_archivo,
        mime_type=mime_type or "application/octet-stream",
        storage_path=storage_path,
        hash_sha256=hash_sha256,
        tamano_bytes=int(tamano_bytes or 0),
        estado="RECIBIDO",
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
        datos_extraidos=datos_extraidos or {},
        observaciones=observaciones or "",
        cargado_por=cargado_por,
    )
    db.add(doc)
    db.add(
        LeasingFinancieroHistorial(
            cotizacion_id=int(cotizacion.id),
            tipo_evento="DOCUMENTO_CREDITO",
            estado_desde=str(cotizacion.estado or "").upper(),
            estado_hasta=str(cotizacion.estado or "").upper(),
            comentario=f"Documento crédito cargado: {tipo_documento} · {nombre_archivo}",
            usuario=cargado_por,
            metadata_json={"tipo_documento": tipo_documento, "nombre_archivo": nombre_archivo},
        )
    )
    db.commit()
    db.refresh(doc)
    return doc


def aplicar_datos_extraidos_a_analisis(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    campos: dict[str, Decimal],
    analista: str = "sistema",
) -> LeasingFinancieroAnalisisCredito:
    """Persiste campos financieros extraídos sin recalcular scoring todavía."""
    analisis = get_analisis_por_cotizacion(db, int(cotizacion.id))
    if not analisis:
        analisis = LeasingFinancieroAnalisisCredito(
            cotizacion_id=int(cotizacion.id),
            cliente_id=int(cotizacion.cliente_id),
            tipo_persona="JURIDICA",
            analista=analista,
        )
        db.add(analisis)

    allowed = {
        "ventas_anuales",
        "ebitda_anual",
        "deuda_financiera_total",
        "patrimonio",
        "activo_corriente",
        "pasivo_corriente",
        "activo_total",
        "pasivo_total",
        "utilidad_neta_anual",
        "gastos_financieros_anual",
        "ventas_12m_iva",
        "iva_debito_12m",
        "iva_credito_12m",
    }
    for key, val in campos.items():
        if key in allowed:
            setattr(analisis, key, val)

    docs = listar_documentos(db, int(cotizacion.id))
    resumen = {
        d.tipo_documento: {
            "id": int(d.id),
            "nombre_archivo": d.nombre_archivo,
            "estado": d.estado,
            "creado_en": d.creado_en.isoformat() if d.creado_en else None,
        }
        for d in docs
        if d.estado != "OBSOLETO"
    }
    analisis.documentos_resumen_json = resumen
    analisis.analista = analista
    db.add(analisis)
    db.commit()
    db.refresh(analisis)
    return analisis


def listar_cotizaciones_para_credito(
    db: Session,
    *,
    limit: int = 200,
    estado: str | None = "EN_ANALISIS_CREDITO",
    recomendacion: str | None = None,
) -> list[LeasingFinancieroCotizacion]:
    stmt = (
        select(LeasingFinancieroCotizacion)
        .options(
            selectinload(LeasingFinancieroCotizacion.cliente),
            selectinload(LeasingFinancieroCotizacion.analisis_credito),
        )
    )
    if estado:
        stmt = stmt.where(LeasingFinancieroCotizacion.estado == estado)
    if recomendacion:
        stmt = stmt.join(LeasingFinancieroCotizacion.analisis_credito).where(
            LeasingFinancieroAnalisisCredito.recomendacion == recomendacion
        )
    stmt = stmt.order_by(LeasingFinancieroCotizacion.id.desc()).limit(limit)
    return list(db.scalars(stmt))


def get_analisis_por_cotizacion(db: Session, cotizacion_id: int) -> LeasingFinancieroAnalisisCredito | None:
    stmt = select(LeasingFinancieroAnalisisCredito).where(LeasingFinancieroAnalisisCredito.cotizacion_id == cotizacion_id)
    return db.scalars(stmt).first()


def upsert_analisis(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    data: LeasingCreditoInput,
    resultado: LeasingCreditoResultado,
    analista: str = "sistema",
) -> LeasingFinancieroAnalisisCredito:
    analisis = get_analisis_por_cotizacion(db, int(cotizacion.id))

    payload = data.model_dump()
    payload_result = resultado.model_dump()
    payload_result["score_total"] = float(payload_result["score_total"])
    if payload_result.get("dscr_calculado") is not None:
        payload_result["dscr"] = payload_result.pop("dscr_calculado")
    if payload_result.get("leverage_calculado") is not None:
        payload_result["leverage_ratio"] = payload_result.pop("leverage_calculado")
    payload_result.pop("dscr_calculado", None)
    payload_result.pop("leverage_calculado", None)

    docs = listar_documentos(db, int(cotizacion.id))
    payload_result["documentos_resumen_json"] = {
        d.tipo_documento: {
            "id": int(d.id),
            "nombre_archivo": d.nombre_archivo,
            "estado": d.estado,
        }
        for d in docs
        if d.estado != "OBSOLETO"
    }

    estado_origen = str(cotizacion.estado or "").upper()
    if analisis:
        for k, v in payload.items():
            setattr(analisis, k, v)
        for k, v in payload_result.items():
            setattr(analisis, k, v)
        analisis.analista = analista
    else:
        analisis = LeasingFinancieroAnalisisCredito(
            cotizacion_id=int(cotizacion.id),
            cliente_id=int(cotizacion.cliente_id),
            analista=analista,
            **payload,
            **payload_result,
        )
        db.add(analisis)

    rec = str(payload_result.get("recomendacion") or "").upper()
    if rec == "APROBADO":
        cotizacion.estado = "APROBADA"
    elif rec == "APROBADA_CONDICIONES":
        cotizacion.estado = "APROBADA_CONDICIONES"
    elif rec == "RECHAZADO":
        cotizacion.estado = "RECHAZADA"
    db.add(cotizacion)
    db.add(
        LeasingFinancieroHistorial(
            cotizacion_id=int(cotizacion.id),
            tipo_evento="SCORING",
            estado_desde=estado_origen,
            estado_hasta=str(cotizacion.estado or "").upper(),
            comentario=f"Scoring crédito actualizado: {rec}",
            usuario=analista,
            metadata_json={"recomendacion": rec, "score_total": payload_result.get("score_total")},
        )
    )

    cliente = db.get(Cliente, int(cotizacion.cliente_id))
    if cliente and payload.get("tipo_persona"):
        cliente.tipo_persona = str(payload["tipo_persona"]).upper()

    if not getattr(cotizacion, "checklist_items", None):
        inicializar_checklist(db, cotizacion)
    if rec in {"APROBADO", "APROBADA_CONDICIONES"}:
        persistir_amortizacion_oficial(db, cotizacion, usuario=analista, congelar=True)
        workflow = cotizacion.workflow_json if isinstance(cotizacion.workflow_json, dict) else {}
        hitos = workflow.get("hitos") or {}
        hitos["analisis_credito"] = True
        workflow["hitos"] = hitos
        workflow["etapa_actual"] = "ORDEN_COMPRA"
        cotizacion.workflow_json = workflow
    sincronizar_checklist_automatico(db, cotizacion, usuario=analista)

    db.commit()
    db.refresh(analisis)
    return analisis
