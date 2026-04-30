# crud/remuneraciones.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from models.fondos_rendir.empleado import Empleado
from models.finanzas.compras_finanzas import CentroCosto
from models.remuneraciones.models import (
    ContratoLaboral,
    DetalleRemuneracion,
    ItemRemuneracion,
    PeriodoRemuneracion,
    RemuneracionHorasPeriodo,
    RemuneracionParametro,
    RemuneracionParametroPeriodo,
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
            selectinload(PeriodoRemuneracion.horas_periodo),
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


def listar_parametros_globales(db: Session) -> list[RemuneracionParametro]:
    return list(db.scalars(select(RemuneracionParametro).order_by(RemuneracionParametro.clave)).all())


def listar_parametros_periodo(db: Session, periodo_id: int) -> list[RemuneracionParametroPeriodo]:
    return list(
        db.scalars(
            select(RemuneracionParametroPeriodo)
            .where(RemuneracionParametroPeriodo.periodo_remuneracion_id == periodo_id)
            .order_by(RemuneracionParametroPeriodo.clave)
        ).all()
    )


def upsert_parametro_global(
    db: Session,
    *,
    clave: str,
    valor_numerico: Decimal | None,
    valor_texto: str | None,
    descripcion: str | None,
) -> RemuneracionParametro:
    c = (clave or "").strip().upper()
    if not c:
        raise ValueError("Clave obligatoria.")
    row = db.scalars(select(RemuneracionParametro).where(RemuneracionParametro.clave == c)).first()
    if row is None:
        row = RemuneracionParametro(clave=c)
    row.valor_numerico = valor_numerico
    row.valor_texto = (valor_texto or "").strip() or None
    row.descripcion = (descripcion or "").strip() or None
    db.add(row)
    db.flush()
    return row


def upsert_parametro_periodo(
    db: Session,
    *,
    periodo_id: int,
    clave: str,
    valor_numerico: Decimal | None,
    valor_texto: str | None,
    descripcion: str | None,
) -> RemuneracionParametroPeriodo:
    if not db.get(PeriodoRemuneracion, periodo_id):
        raise ValueError("Periodo no encontrado.")
    c = (clave or "").strip().upper()
    if not c:
        raise ValueError("Clave obligatoria.")
    row = db.scalars(
        select(RemuneracionParametroPeriodo).where(
            RemuneracionParametroPeriodo.periodo_remuneracion_id == periodo_id,
            RemuneracionParametroPeriodo.clave == c,
        )
    ).first()
    if row is None:
        row = RemuneracionParametroPeriodo(periodo_remuneracion_id=periodo_id, clave=c)
    row.valor_numerico = valor_numerico
    row.valor_texto = (valor_texto or "").strip() or None
    row.descripcion = (descripcion or "").strip() or None
    db.add(row)
    db.flush()
    return row


def listar_horas_periodo(db: Session, periodo_id: int) -> list[RemuneracionHorasPeriodo]:
    return list(
        db.scalars(
            select(RemuneracionHorasPeriodo)
            .options(selectinload(RemuneracionHorasPeriodo.empleado))
            .where(RemuneracionHorasPeriodo.periodo_remuneracion_id == periodo_id)
            .order_by(RemuneracionHorasPeriodo.empleado_id)
        ).all()
    )


def guardar_horas_periodo(
    db: Session,
    *,
    periodo_id: int,
    empleado_id: int,
    horas_ordinarias: Decimal,
    horas_extras: Decimal,
    horas_nocturnas: Decimal,
    es_ajuste_manual: bool,
    motivo_ajuste: str | None,
    usuario_ajuste_id: int | None,
) -> RemuneracionHorasPeriodo:
    if not db.get(PeriodoRemuneracion, periodo_id):
        raise ValueError("Periodo no encontrado.")
    if not db.get(Empleado, empleado_id):
        raise ValueError("Empleado no encontrado.")
    row = db.scalars(
        select(RemuneracionHorasPeriodo).where(
            RemuneracionHorasPeriodo.periodo_remuneracion_id == periodo_id,
            RemuneracionHorasPeriodo.empleado_id == empleado_id,
        )
    ).first()
    if row is None:
        row = RemuneracionHorasPeriodo(periodo_remuneracion_id=periodo_id, empleado_id=empleado_id)
    row.horas_ordinarias = max(Decimal("0"), horas_ordinarias)
    row.horas_extras = max(Decimal("0"), horas_extras)
    row.horas_nocturnas = max(Decimal("0"), horas_nocturnas)
    row.es_ajuste_manual = bool(es_ajuste_manual)
    row.motivo_ajuste = (motivo_ajuste or "").strip() or None
    row.usuario_ajuste_id = usuario_ajuste_id
    db.add(row)
    db.flush()
    return row


def obtener_libro_periodo(db: Session, periodo_id: int) -> PeriodoRemuneracion | None:
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


def obtener_detalle_periodo_empleado(db: Session, periodo_id: int, empleado_id: int) -> DetalleRemuneracion | None:
    return db.scalars(
        select(DetalleRemuneracion)
        .options(
            selectinload(DetalleRemuneracion.empleado),
            selectinload(DetalleRemuneracion.items).selectinload(ItemRemuneracion.concepto),
            selectinload(DetalleRemuneracion.periodo),
        )
        .where(
            DetalleRemuneracion.periodo_remuneracion_id == periodo_id,
            DetalleRemuneracion.empleado_id == empleado_id,
        )
    ).first()


def construir_libro_rows(periodo: PeriodoRemuneracion) -> list[dict[str, Decimal | str | int]]:
    rows: list[dict[str, Decimal | str | int]] = []
    for d in sorted(periodo.detalles, key=lambda x: (x.empleado.nombre_completo if x.empleado else "")):
        rows.append(
            {
                "empleado_id": d.empleado_id,
                "empleado": (d.empleado.nombre_completo if d.empleado else f"ID {d.empleado_id}"),
                "cargo": d.cargo_snapshot or "",
                "horas_extras": d.horas_extras,
                "haberes_imponibles": d.total_haberes_imponibles,
                "haberes_no_imponibles": d.total_haberes_no_imponibles,
                "descuentos_legales": d.total_descuentos_legales,
                "otros_descuentos": d.total_otros_descuentos,
                "liquido": d.liquido_a_pagar,
            }
        )
    return rows


def exportar_libro_xlsx(periodo: PeriodoRemuneracion) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Libro"
    ws.append(
        [
            "Empleado",
            "Cargo",
            "Horas extras",
            "Haberes imponibles",
            "Haberes no imponibles",
            "Descuentos legales",
            "Otros descuentos",
            "Liquido a pagar",
        ]
    )
    for r in construir_libro_rows(periodo):
        ws.append(
            [
                str(r["empleado"]),
                str(r["cargo"]),
                float(r["horas_extras"] or 0),
                float(r["haberes_imponibles"] or 0),
                float(r["haberes_no_imponibles"] or 0),
                float(r["descuentos_legales"] or 0),
                float(r["otros_descuentos"] or 0),
                float(r["liquido"] or 0),
            ]
        )
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def totales_libro(rows: list[dict[str, Decimal | str | int]]) -> dict[str, Decimal]:
    zero = Decimal("0")
    out = {
        "haberes_imponibles": zero,
        "haberes_no_imponibles": zero,
        "descuentos_legales": zero,
        "otros_descuentos": zero,
        "liquido": zero,
    }
    for r in rows:
        out["haberes_imponibles"] += Decimal(str(r["haberes_imponibles"] or 0))
        out["haberes_no_imponibles"] += Decimal(str(r["haberes_no_imponibles"] or 0))
        out["descuentos_legales"] += Decimal(str(r["descuentos_legales"] or 0))
        out["otros_descuentos"] += Decimal(str(r["otros_descuentos"] or 0))
        out["liquido"] += Decimal(str(r["liquido"] or 0))
    return out
