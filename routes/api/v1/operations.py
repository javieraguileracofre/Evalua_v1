# routes/api/v1/operations.py
# -*- coding: utf-8 -*-
"""Escrituras y lecturas de la ola D. Sin envío al SII."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.session import get_db
from erp_platform.permissions import (
    COBRANZA_COLLECT,
    CONTABILIDAD_CLOSE,
    CONTABILIDAD_POST,
    CONTABILIDAD_VIEW,
)
from modules.analytics.lecturas import cartera_cxc, contratos_lop_vigentes, resultado_mes
from modules.contabilidad.manual_entries import registrar_asiento_manual
from modules.cobranza import registrar_pago_cliente
from routes.api.v1.deps import require_permission
from services.finanzas.conciliacion_bancaria import confirmar_linea, importar_cartola, proponer_cartola
from services.finanzas.diferencia_cambio import guardar_tipo_cierre, revaluar_saldos_periodo
from services.finanzas.documento_tributario import listar_libro
from services.platform.api_idempotency import (
    IdempotencyConflict,
    IdempotencyUnavailable,
    begin,
    finish,
)

router = APIRouter(tags=["API v1 · Operaciones"])


class LineaAsientoIn(BaseModel):
    codigo_cuenta: str
    debe: Decimal = Decimal("0")
    haber: Decimal = Decimal("0")
    descripcion: str | None = None


class AsientoManualIn(BaseModel):
    fecha: date
    glosa: str = Field(min_length=1, max_length=255)
    es_apertura: bool = False
    detalles: list[LineaAsientoIn] = Field(min_length=2)


class LineaCartolaIn(BaseModel):
    fecha: date
    monto: Decimal
    glosa: str = ""
    referencia: str = ""


class CartolaIn(BaseModel):
    nombre: str = "Cartola"
    lineas: list[LineaCartolaIn] = Field(min_length=1)


class ConfirmarLineaIn(BaseModel):
    movimiento_tipo: str
    movimiento_id: int
    diferencia: Decimal = Decimal("0")
    cuenta_debe: str | None = None
    cuenta_haber: str | None = None


class TipoCierreIn(BaseModel):
    anio: int
    mes: int
    moneda: str
    valor: Decimal


class PeriodoIn(BaseModel):
    anio: int
    mes: int


def _usuario(auth: dict) -> str:
    return str(auth.get("email") or auth.get("uid") or auth.get("id") or "")


def _error_negocio(exc: Exception) -> HTTPException:
    if isinstance(exc, IdempotencyConflict):
        return HTTPException(status_code=409, detail="La clave de idempotencia está en curso. Reintente.")
    if isinstance(exc, IdempotencyUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("/accounting/manual-entries")
def post_asiento_manual(
    payload: AsientoManualIn,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission(CONTABILIDAD_POST)),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict:
    try:
        previo = begin(db, alcance="MANUAL_ENTRY", clave=idempotency_key)
    except (IdempotencyConflict, IdempotencyUnavailable, ValueError) as exc:
        raise _error_negocio(exc) from exc
    if previo:
        return previo
    try:
        asiento_id = registrar_asiento_manual(
            db,
            fecha=payload.fecha,
            glosa=payload.glosa,
            detalles=[linea.model_dump() for linea in payload.detalles],
            usuario=_usuario(auth),
            es_apertura=payload.es_apertura,
            do_commit=False,
        )
        body = {"asiento_id": int(asiento_id), "estado": "contabilizado"}
        finish(db, alcance="MANUAL_ENTRY", clave=idempotency_key, body=body)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return body


@router.post("/cobranza/payments/{pago_id}/post")
def post_pago_cliente(
    pago_id: int,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission(COBRANZA_COLLECT)),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict:
    try:
        previo = begin(db, alcance="PAGO_CLIENTE", clave=idempotency_key)
    except (IdempotencyConflict, IdempotencyUnavailable, ValueError) as exc:
        raise _error_negocio(exc) from exc
    if previo:
        return previo
    body = {"pago_id": int(pago_id), "estado": "contabilizado"}
    finish(db, alcance="PAGO_CLIENTE", clave=idempotency_key, body=body)
    try:
        registrar_pago_cliente(db, pago_id=int(pago_id), usuario=_usuario(auth))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return body


@router.get("/accounting/tax-books/{libro}")
def get_libro(
    libro: str,
    anio: int | None = None,
    mes: int | None = None,
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_permission(CONTABILIDAD_VIEW)),
) -> dict:
    direccion = {"venta": "EMITIDO", "compra": "RECIBIDO"}.get(libro.strip().lower())
    if not direccion:
        raise HTTPException(status_code=404, detail="Libro desconocido. Use venta o compra.")
    try:
        filas = listar_libro(db, direccion, anio=anio, mes=mes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"libro": libro, "filas": filas}


@router.post("/treasury/statements")
def post_cartola(
    payload: CartolaIn,
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_permission(CONTABILIDAD_POST)),
) -> dict:
    try:
        cartola_id = importar_cartola(
            db,
            nombre=payload.nombre,
            lineas=[linea.model_dump() for linea in payload.lineas],
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"cartola_id": cartola_id}


@router.get("/treasury/statements/{cartola_id}/proposals")
def get_propuestas(
    cartola_id: int,
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_permission(CONTABILIDAD_VIEW)),
) -> dict:
    return {"cartola_id": cartola_id, "propuestas": proponer_cartola(db, cartola_id)}


@router.post("/treasury/lines/{linea_id}/confirm")
def post_confirmar_linea(
    linea_id: int,
    payload: ConfirmarLineaIn,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission(CONTABILIDAD_POST)),
) -> dict:
    try:
        resultado = confirmar_linea(
            db,
            linea_id=linea_id,
            movimiento_tipo=payload.movimiento_tipo,
            movimiento_id=payload.movimiento_id,
            diferencia=payload.diferencia,
            cuenta_debe=payload.cuenta_debe,
            cuenta_haber=payload.cuenta_haber,
            usuario=_usuario(auth),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return resultado


@router.put("/accounting/fx-rates")
def put_tipo_cierre(
    payload: TipoCierreIn,
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_permission(CONTABILIDAD_CLOSE)),
) -> dict:
    try:
        guardar_tipo_cierre(
            db,
            anio=payload.anio,
            mes=payload.mes,
            moneda=payload.moneda,
            valor=payload.valor,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"anio": payload.anio, "mes": payload.mes, "moneda": payload.moneda.upper()}


@router.post("/accounting/revaluations")
def post_revaluacion(
    payload: PeriodoIn,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_permission(CONTABILIDAD_CLOSE)),
) -> dict:
    try:
        asientos = revaluar_saldos_periodo(
            db,
            anio=payload.anio,
            mes=payload.mes,
            usuario=_usuario(auth),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {"anio": payload.anio, "mes": payload.mes, "asientos": asientos}


@router.get("/analytics/cartera")
def get_cartera(
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_permission(CONTABILIDAD_VIEW)),
) -> dict:
    try:
        return {"filas": cartera_cxc(db)}
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/analytics/contratos-lop")
def get_contratos(
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_permission(CONTABILIDAD_VIEW)),
) -> dict:
    try:
        return {"filas": contratos_lop_vigentes(db)}
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/analytics/resultado")
def get_resultado(
    anio: int | None = None,
    mes: int | None = None,
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_permission(CONTABILIDAD_VIEW)),
) -> dict:
    try:
        filas = resultado_mes(db, anio=anio, mes=mes)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    periodo = filas[0] if filas else {}
    return {
        "anio": anio or periodo.get("anio"),
        "mes": mes or periodo.get("mes"),
        "filas": filas,
    }
