# crud/remuneraciones.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from models.fondos_rendir.empleado import Empleado
from models.finanzas.compras_finanzas import CentroCosto
from models.remuneraciones.models import (
    ContratoLaboral,
    DetalleRemuneracion,
    ItemRemuneracion,
    PeriodoRemuneracion,
)


def _ultimo_dia_mes(anio: int, mes: int) -> int:
    return monthrange(anio, mes)[1]


def crear_periodo_remuneracion(
    db: Session,
    *,
    anio: int,
    mes: int,
    usuario_creador_id: int | None,
) -> PeriodoRemuneracion:
    if mes < 1 or mes > 12:
        raise ValueError("Mes inválido.")
    if anio < 2000 or anio > 2100:
        raise ValueError("Año inválido.")
    exists = db.scalars(
        select(PeriodoRemuneracion.id).where(PeriodoRemuneracion.anio == anio, PeriodoRemuneracion.mes == mes)
    ).first()
    if exists is not None:
        raise ValueError(f"Ya existe un periodo de remuneración para {mes:02d}/{anio}.")

    fi = date(anio, mes, 1)
    ff = date(anio, mes, _ultimo_dia_mes(anio, mes))
    pr = PeriodoRemuneracion(
        anio=anio,
        mes=mes,
        fecha_inicio=fi,
        fecha_fin=ff,
        estado="BORRADOR",
        usuario_creador_id=usuario_creador_id,
    )
    db.add(pr)
    db.flush()
    return pr


def listar_periodos_remuneracion(db: Session, *, limite: int = 60) -> list[PeriodoRemuneracion]:
    return list(
        db.scalars(
            select(PeriodoRemuneracion)
            .order_by(PeriodoRemuneracion.anio.desc(), PeriodoRemuneracion.mes.desc())
            .limit(max(1, min(limite, 200)))
        ).all()
    )


def obtener_periodo_remuneracion(db: Session, periodo_id: int) -> PeriodoRemuneracion | None:
    return db.scalars(
        select(PeriodoRemuneracion)
        .options(
            selectinload(PeriodoRemuneracion.detalles).selectinload(DetalleRemuneracion.empleado),
            selectinload(PeriodoRemuneracion.detalles)
            .selectinload(DetalleRemuneracion.items)
            .selectinload(ItemRemuneracion.concepto),
        )
        .where(PeriodoRemuneracion.id == periodo_id)
    ).first()


def crear_contrato_laboral(
    db: Session,
    *,
    empleado_id: int,
    fecha_inicio: date,
    fecha_fin: date | None,
    tipo_contrato: str | None,
    jornada: str | None,
    sueldo_base: Decimal,
    centro_costo_id: int | None,
    observaciones: str | None,
) -> ContratoLaboral:
    if not db.get(Empleado, empleado_id):
        raise ValueError("Empleado no encontrado.")
    if centro_costo_id is not None and not db.get(CentroCosto, centro_costo_id):
        raise ValueError("Centro de costo no encontrado.")
    if sueldo_base < 0:
        raise ValueError("El sueldo base no puede ser negativo.")
    if fecha_fin is not None and fecha_fin < fecha_inicio:
        raise ValueError("La fecha fin no puede ser anterior al inicio.")

    otros = list(
        db.scalars(
            select(ContratoLaboral).where(
                ContratoLaboral.empleado_id == empleado_id,
                ContratoLaboral.estado == "VIGENTE",
            )
        ).all()
    )
    for o in otros:
        o.estado = "TERMINADO"
        db.add(o)

    c = ContratoLaboral(
        empleado_id=empleado_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        tipo_contrato=(tipo_contrato or "").strip() or None,
        jornada=(jornada or "").strip() or None,
        sueldo_base=sueldo_base,
        centro_costo_id=centro_costo_id,
        estado="VIGENTE",
        observaciones=(observaciones or "").strip() or None,
    )
    db.add(c)
    db.flush()
    return c


def obtener_contrato_vigente(db: Session, empleado_id: int, ref: date | None = None) -> ContratoLaboral | None:
    ref = ref or date.today()
    return db.scalars(
        select(ContratoLaboral)
        .where(
            ContratoLaboral.empleado_id == empleado_id,
            ContratoLaboral.estado == "VIGENTE",
            ContratoLaboral.fecha_inicio <= ref,
            or_(ContratoLaboral.fecha_fin.is_(None), ContratoLaboral.fecha_fin >= ref),
        )
        .order_by(ContratoLaboral.fecha_inicio.desc())
    ).first()
