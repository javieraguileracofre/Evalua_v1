# crud/comercial/leasing_credito.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.comercial.leasing_financiero_credito import LeasingFinancieroAnalisisCredito
from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion, LeasingFinancieroHistorial
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

    db.commit()
    db.refresh(analisis)
    return analisis
