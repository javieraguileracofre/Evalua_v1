# crud/remuneraciones.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, selectinload

from models.auth.usuario import Usuario
from models.fondos_rendir.empleado import Empleado
from models.finanzas.compras_finanzas import CentroCosto
from models.remuneraciones.models import (
    ConceptoRemuneracion,
    ContratoLaboral,
    DetalleRemuneracion,
    ItemRemuneracion,
    PeriodoRemuneracion,
    RemuneracionAuditLog,
    RemuneracionHorasPeriodo,
    RemuneracionParametro,
    RemuneracionParametroPeriodo,
)
from services.remuneraciones.banco_transfer_csv import exportar_nomina_transfer_csv, normalizar_formato_masivo


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


def listar_conceptos_remuneracion_activos(db: Session) -> list[ConceptoRemuneracion]:
    return list(
        db.scalars(
            select(ConceptoRemuneracion)
            .where(ConceptoRemuneracion.activo.is_(True))
            .order_by(ConceptoRemuneracion.orden, ConceptoRemuneracion.nombre)
        ).all()
    )


def listar_auditoria_periodo(db: Session, periodo_id: int, *, limite: int = 60) -> list[RemuneracionAuditLog]:
    return list(
        db.scalars(
            select(RemuneracionAuditLog)
            .where(RemuneracionAuditLog.periodo_remuneracion_id == periodo_id)
            .order_by(RemuneracionAuditLog.created_at.desc())
            .limit(max(1, min(limite, 200)))
        ).all()
    )


def listar_auditoria_periodo_vista(db: Session, periodo_id: int, *, limite: int = 60) -> list[dict[str, Any]]:
    """Auditoría con etiqueta legible del usuario que ejecutó la acción."""
    lim = max(1, min(limite, 200))
    rows = db.execute(
        select(RemuneracionAuditLog, Usuario.email, Usuario.nombre_completo)
        .outerjoin(Usuario, Usuario.id == RemuneracionAuditLog.actor_usuario_id)
        .where(RemuneracionAuditLog.periodo_remuneracion_id == periodo_id)
        .order_by(RemuneracionAuditLog.created_at.desc())
        .limit(lim)
    ).all()
    out: list[dict[str, Any]] = []
    for log, email, nombre in rows:
        actor = (email or "").strip() or (nombre or "").strip() or None
        if log.actor_usuario_id is not None and not actor:
            actor = f"usuario_id={log.actor_usuario_id}"
        out.append(
            {
                "id": log.id,
                "created_at": log.created_at,
                "accion": log.accion,
                "detalle": log.detalle,
                "actor_label": actor,
            }
        )
    return out


def exportar_transferencias_nomina_csv(
    db: Session,
    periodo_id: int,
    *,
    formato: str = "generico",
) -> str:
    """
    CSV separado por ; (UTF-8, BOM) para cargas masivas en banco.

    Presets: ver ``services.remuneraciones.banco_transfer_csv.FORMATOS_NOMINA``.
    """
    pr = obtener_periodo_remuneracion(db, periodo_id)
    if not pr:
        raise ValueError("Periodo no encontrado.")
    fmt = normalizar_formato_masivo(formato)
    return exportar_nomina_transfer_csv(pr, fmt)


def registrar_auditoria_nomina(
    db: Session,
    *,
    periodo_id: int,
    empleado_id: int | None,
    actor_usuario_id: int | None,
    accion: str,
    detalle: str | None,
) -> RemuneracionAuditLog:
    row = RemuneracionAuditLog(
        periodo_remuneracion_id=periodo_id,
        empleado_id=empleado_id,
        actor_usuario_id=actor_usuario_id,
        accion=(accion or "").strip()[:80],
        detalle=(detalle or "").strip()[:4000] if detalle else None,
    )
    db.add(row)
    db.flush()
    return row


def conteo_periodos_por_estado(db: Session) -> dict[str, int]:
    rows = db.execute(select(PeriodoRemuneracion.estado, func.count()).group_by(PeriodoRemuneracion.estado)).all()
    out: dict[str, int] = {}
    for estado, n in rows:
        out[str(estado)] = int(n or 0)
    return out


def contar_empleados_activos_sin_contrato_vigente(db: Session, ref: date | None = None) -> int:
    ref = ref or date.today()
    tiene_vigente = exists(
        select(1)
        .select_from(ContratoLaboral)
        .where(
            ContratoLaboral.empleado_id == Empleado.id,
            ContratoLaboral.estado == "VIGENTE",
            ContratoLaboral.fecha_inicio <= ref,
            or_(ContratoLaboral.fecha_fin.is_(None), ContratoLaboral.fecha_fin >= ref),
        )
    )
    return int(db.scalar(select(func.count()).select_from(Empleado).where(Empleado.activo.is_(True), ~tiene_vigente)) or 0)


def agregar_item_manual_nomina(
    db: Session,
    *,
    periodo_id: int,
    empleado_id: int,
    concepto_id: int,
    monto: Decimal,
    motivo: str,
    actor_usuario_id: int | None,
) -> ItemRemuneracion:
    from services.remuneraciones.calculo_service import puede_editar_periodo, recalcular_totales_detalle_remuneracion

    pr = db.get(PeriodoRemuneracion, periodo_id)
    if not pr:
        raise ValueError("Periodo no encontrado.")
    if not puede_editar_periodo(pr):
        raise ValueError("Este período no admite ajustes manuales en su estado actual.")

    det = obtener_detalle_periodo_empleado(db, periodo_id, empleado_id)
    if not det:
        raise ValueError("No hay liquidación para este trabajador; calcule el período primero.")

    c = db.get(ConceptoRemuneracion, concepto_id)
    if not c or not c.activo:
        raise ValueError("Concepto no válido o inactivo.")

    m = monto.quantize(Decimal("0.01"))
    if m <= 0:
        raise ValueError("El monto debe ser mayor a cero.")

    motivo_limpio = (motivo or "").strip()
    if len(motivo_limpio) < 3:
        raise ValueError("Indique un motivo del ajuste (mínimo 3 caracteres).")

    it = ItemRemuneracion(
        detalle_remuneracion_id=det.id,
        concepto_remuneracion_id=concepto_id,
        cantidad=Decimal("1"),
        valor_unitario=m,
        monto_total=m,
        origen="manual",
        referencia_tipo="ajuste_rrhh",
        referencia_id=None,
        es_ajuste_manual=True,
        motivo_ajuste=motivo_limpio[:2000],
        usuario_ajuste_id=actor_usuario_id,
    )
    db.add(it)
    db.flush()
    recalcular_totales_detalle_remuneracion(db, det.id)
    try:
        registrar_auditoria_nomina(
            db,
            periodo_id=periodo_id,
            empleado_id=empleado_id,
            actor_usuario_id=actor_usuario_id,
            accion="ITEM_MANUAL_AGREGADO",
            detalle=f"concepto_id={concepto_id} monto={m} motivo={motivo_limpio[:500]}",
        )
    except ProgrammingError:
        pass
    return it


def eliminar_item_manual_nomina(
    db: Session,
    *,
    periodo_id: int,
    empleado_id: int,
    item_id: int,
    actor_usuario_id: int | None,
) -> None:
    from services.remuneraciones.calculo_service import puede_editar_periodo, recalcular_totales_detalle_remuneracion

    pr = db.get(PeriodoRemuneracion, periodo_id)
    if not pr:
        raise ValueError("Periodo no encontrado.")
    if not puede_editar_periodo(pr):
        raise ValueError("Este período no admite eliminar ajustes en su estado actual.")

    det = obtener_detalle_periodo_empleado(db, periodo_id, empleado_id)
    if not det:
        raise ValueError("Detalle no encontrado.")

    it = db.get(ItemRemuneracion, item_id)
    if not it or it.detalle_remuneracion_id != det.id:
        raise ValueError("Ítem no encontrado.")
    if (it.origen or "").strip().lower() != "manual" or not it.es_ajuste_manual:
        raise ValueError("Solo se pueden eliminar líneas marcadas como ajuste manual.")

    db.delete(it)
    db.flush()
    recalcular_totales_detalle_remuneracion(db, det.id)
    try:
        registrar_auditoria_nomina(
            db,
            periodo_id=periodo_id,
            empleado_id=empleado_id,
            actor_usuario_id=actor_usuario_id,
            accion="ITEM_MANUAL_ELIMINADO",
            detalle=f"item_id={item_id}",
        )
    except ProgrammingError:
        pass


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
