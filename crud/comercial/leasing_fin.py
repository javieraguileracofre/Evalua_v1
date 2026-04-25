# crud/comercial/leasing_fin.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion
from schemas.comercial.leasing_cotizacion import LeasingCotizacionCreate, LeasingCotizacionUpdate
from services.leasing_financiero_contabilidad import regenerar_proyeccion_contable


def get_cotizacion(db: Session, cotizacion_id: int) -> Optional[LeasingFinancieroCotizacion]:
    stmt = (
        select(LeasingFinancieroCotizacion)
        .options(
            selectinload(LeasingFinancieroCotizacion.cliente),
            selectinload(LeasingFinancieroCotizacion.proyeccion_lineas),
        )
        .where(LeasingFinancieroCotizacion.id == cotizacion_id)
    )
    return db.scalars(stmt).first()


def get_cotizaciones(
    db: Session,
    *,
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    limit: int = 200,
) -> List[LeasingFinancieroCotizacion]:
    stmt = select(LeasingFinancieroCotizacion).options(
        selectinload(LeasingFinancieroCotizacion.cliente)
    )

    if cliente_id is not None:
        stmt = stmt.where(LeasingFinancieroCotizacion.cliente_id == cliente_id)

    if estado:
        stmt = stmt.where(LeasingFinancieroCotizacion.estado == estado)

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
    if "estado" in data and data["estado"] is not None:
        data["estado"] = str(data["estado"]).strip().upper()
    return data


def crear_cotizacion(db: Session, *, obj_in: LeasingCotizacionCreate) -> LeasingFinancieroCotizacion:
    data = _dump_cotizacion(obj_in, creating=True)
    if data.get("fecha_cotizacion") is None:
        data["fecha_cotizacion"] = date.today()

    cot = LeasingFinancieroCotizacion(**data)
    db.add(cot)
    db.commit()
    db.refresh(cot)

    cot = get_cotizacion(db, int(cot.id)) or cot
    regenerar_proyeccion_contable(db, cot)
    db.commit()
    db.refresh(cot)
    return cot


def actualizar_cotizacion(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    obj_in: LeasingCotizacionUpdate,
) -> LeasingFinancieroCotizacion:
    update_data = obj_in.model_dump(exclude_unset=True)
    if "estado" in update_data and update_data["estado"] is not None:
        update_data["estado"] = str(update_data["estado"]).strip().upper()
    if "concesionario" in update_data and update_data["concesionario"] is not None:
        update_data["concesionario"] = update_data["concesionario"].strip() or None
    if "ejecutivo" in update_data and update_data["ejecutivo"] is not None:
        update_data["ejecutivo"] = update_data["ejecutivo"].strip() or None

    for field, value in update_data.items():
        if hasattr(cotizacion, field) and value is not None:
            setattr(cotizacion, field, value)

    db.add(cotizacion)
    db.commit()
    db.refresh(cotizacion)

    cot = get_cotizacion(db, int(cotizacion.id)) or cotizacion
    regenerar_proyeccion_contable(db, cot)
    db.commit()
    db.refresh(cot)
    return cot
