# services/remuneraciones/calculo_service.py
# -*- coding: utf-8 -*-
"""
Reglas de negocio acordadas:
- Un tenant = una BD: sin empresa_id en tablas de nómina.
- Contrato y sueldo base viven en contratos_laborales (ERP).
- Anticipos (fondos_rendir): solo estado APROBADO y fecha_aprobacion en el rango del periodo.
- Bono por viaje: parámetro BONO_VIAJE_PCT_VALOR_FLETE (0 = no automático); si > 0, viajes CERRADO
  con real_salida en rango; suma valor_flete * pct/100.
- CERRADO y PAGADO requieren fin.periodo ABIERTO para el mismo año/mes.
- AFP/salud automáticos: parámetros DESCUENTO_AFP_PCT_IMPOSABLE y DESCUENTO_SALUD_PCT_IMPOSABLE
  sobre la suma de ítems con concepto imponible (MVP; mismo base bruta para ambos).
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from models.finanzas.compras_finanzas import Periodo as PeriodoFinanciero
from models.fondos_rendir.empleado import Empleado
from models.fondos_rendir.fondo_rendir import FondoRendir
from models.remuneraciones.models import (
    ConceptoRemuneracion,
    ContratoLaboral,
    DetalleRemuneracion,
    ItemRemuneracion,
    PeriodoRemuneracion,
    RemuneracionHorasPeriodo,
    RemuneracionParametro,
    RemuneracionParametroPeriodo,
)
from models.transporte.viaje import TransporteViaje

Q2 = Decimal("0.01")

_PARAM_BONO_PCT = "BONO_VIAJE_PCT_VALOR_FLETE"
_PARAM_AFP_PCT = "DESCUENTO_AFP_PCT_IMPOSABLE"
_PARAM_SALUD_PCT = "DESCUENTO_SALUD_PCT_IMPOSABLE"
_PARAM_VALOR_HORA_EXTRA = "VALOR_HORA_EXTRA"
_PARAM_BONO_NOCTURNO_HORA = "BONO_NOCTURNO_VALOR_HORA"


def _d(v: Any) -> Decimal:
    if v is None:
        return Decimal("0.00")
    if isinstance(v, Decimal):
        return v.quantize(Q2, rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(v)).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def _rango_datetime(fecha_inicio: date, fecha_fin: date) -> tuple[datetime, datetime]:
    start = datetime.combine(fecha_inicio, time.min)
    end = datetime.combine(fecha_fin, time.max)
    return start, end


def obtener_parametro_numerico(db: Session, clave: str) -> Decimal:
    row = db.scalars(select(RemuneracionParametro).where(RemuneracionParametro.clave == clave)).first()
    if not row or row.valor_numerico is None:
        return Decimal("0")
    return _d(row.valor_numerico)


def obtener_parametro_numerico_periodo(db: Session, *, periodo_id: int, clave: str) -> Decimal:
    row = db.scalars(
        select(RemuneracionParametroPeriodo).where(
            RemuneracionParametroPeriodo.periodo_remuneracion_id == periodo_id,
            RemuneracionParametroPeriodo.clave == clave,
        )
    ).first()
    if row and row.valor_numerico is not None:
        return _d(row.valor_numerico)
    return obtener_parametro_numerico(db, clave)


def asegurar_periodo_financiero_abierto(db: Session, anio: int, mes: int) -> None:
    """Levanta ValueError si el periodo contable no existe o está CERRADO."""
    p = db.scalars(
        select(PeriodoFinanciero).where(PeriodoFinanciero.anio == anio, PeriodoFinanciero.mes == mes)
    ).first()
    if not p:
        raise ValueError(
            f"No existe periodo contable fin.periodo para {mes:02d}/{anio}. "
            "Créelo en Cierre mensual antes de cerrar o pagar nómina."
        )
    if str(p.estado) != "ABIERTO":
        raise ValueError(
            f"El periodo contable {mes:02d}/{anio} está {p.estado}. "
            "Debe permanecer ABIERTO para cerrar o marcar como pagada la remuneración."
        )


def puede_editar_periodo(pr: PeriodoRemuneracion) -> bool:
    return pr.estado in ("BORRADOR", "CALCULADO")


def _suma_montos_imponibles(
    db: Session,
    detalle_id: int,
    conceptos: dict[int, ConceptoRemuneracion] | None = None,
) -> Decimal:
    """Suma ítems cuyo concepto está marcado imponible (base simple para AFP/salud en MVP)."""
    items = db.scalars(
        select(ItemRemuneracion).where(ItemRemuneracion.detalle_remuneracion_id == detalle_id)
    ).all()
    if conceptos is None:
        ids = {it.concepto_remuneracion_id for it in items}
        conceptos = {}
        if ids:
            conceptos = {
                c.id: c
                for c in db.scalars(select(ConceptoRemuneracion).where(ConceptoRemuneracion.id.in_(ids))).all()
            }
    total = Decimal("0")
    for it in items:
        concepto = conceptos.get(it.concepto_remuneracion_id)
        if concepto is not None and concepto.imponible:
            total += _d(it.monto_total)
    return total


def _contrato_vigente_en_fecha(db: Session, empleado_id: int, ref: date) -> ContratoLaboral | None:
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


def recalcular_totales_detalle_remuneracion(db: Session, detalle_id: int) -> DetalleRemuneracion:
    """Recalcula totales del detalle tras agregar o quitar ítems (ajustes manuales, etc.)."""
    det = db.get(DetalleRemuneracion, detalle_id)
    if not det:
        raise ValueError("Detalle de remuneración no encontrado.")
    _recalcular_totales_detalle(db, det)
    db.flush()
    return det


def _recalcular_totales_detalle(
    db: Session,
    det: DetalleRemuneracion,
    conceptos: dict[int, ConceptoRemuneracion] | None = None,
) -> None:
    items = list(
        db.scalars(select(ItemRemuneracion).where(ItemRemuneracion.detalle_remuneracion_id == det.id)).all()
    )
    if conceptos is None:
        ids = {it.concepto_remuneracion_id for it in items}
        conceptos = {}
        if ids:
            conceptos = {
                c.id: c
                for c in db.scalars(select(ConceptoRemuneracion).where(ConceptoRemuneracion.id.in_(ids))).all()
            }
    hab_imp = Decimal("0")
    hab_no = Decimal("0")
    des_leg = Decimal("0")
    des_otr = Decimal("0")
    ap_emp = Decimal("0")

    for it in items:
        c = conceptos.get(it.concepto_remuneracion_id)
        if not c:
            continue
        m = _d(it.monto_total)
        tipo = (c.tipo or "").strip().lower()
        if tipo == "haber_imponible":
            hab_imp += m
        elif tipo == "haber_no_imponible":
            hab_no += m
        elif tipo == "descuento_legal":
            des_leg += m
        elif tipo == "descuento_interno":
            des_otr += m
        elif tipo == "aporte_empresa":
            ap_emp += m
        elif tipo == "informativo":
            pass
        else:
            if c.afecta_liquido and c.imponible:
                hab_imp += m
            elif c.afecta_liquido:
                hab_no += m

    bruto = hab_imp + hab_no
    # Aportes empresa: costo empleador, no restan del líquido del trabajador en este MVP.
    liquido = bruto - des_leg - des_otr
    det.total_haberes_imponibles = hab_imp
    det.total_haberes_no_imponibles = hab_no
    det.total_descuentos_legales = des_leg
    det.total_otros_descuentos = des_otr
    det.total_aportes_empresa = ap_emp
    det.liquido_a_pagar = liquido.quantize(Q2, rounding=ROUND_HALF_UP)
    db.add(det)


def calcular_periodo(db: Session, periodo_id: int) -> PeriodoRemuneracion:
    """Regenera detalle e ítems (solo periodos editables)."""
    pr = db.get(PeriodoRemuneracion, periodo_id)
    if not pr:
        raise ValueError("Periodo de remuneración no encontrado.")
    if not puede_editar_periodo(pr):
        raise ValueError("Este periodo no admite recálculo en su estado actual.")

    conceptos_activos = list(
        db.scalars(select(ConceptoRemuneracion).where(ConceptoRemuneracion.activo.is_(True))).all()
    )
    por_codigo = {c.codigo: c for c in conceptos_activos}
    por_id = {c.id: c for c in conceptos_activos}
    concepto_sueldo = por_codigo.get("SUELDO_BASE")
    concepto_bono = por_codigo.get("BONO_VIAJE")
    concepto_anticipo = por_codigo.get("ANTICIPO")
    concepto_afp = por_codigo.get("AFP")
    concepto_salud = por_codigo.get("SALUD")
    concepto_horas_extras = por_codigo.get("HORAS_EXTRAS")
    concepto_bono_nocturno = por_codigo.get("BONO_NOCTURNO")
    if not concepto_sueldo or not concepto_bono or not concepto_anticipo:
        raise ValueError(
            "Faltan conceptos activos (SUELDO_BASE, BONO_VIAJE, ANTICIPO). Ejecute el arranque o seeder."
        )

    pct_bono = obtener_parametro_numerico_periodo(db, periodo_id=pr.id, clave=_PARAM_BONO_PCT)
    pct_afp = obtener_parametro_numerico_periodo(db, periodo_id=pr.id, clave=_PARAM_AFP_PCT)
    pct_salud = obtener_parametro_numerico_periodo(db, periodo_id=pr.id, clave=_PARAM_SALUD_PCT)
    valor_hora_extra_cfg = obtener_parametro_numerico_periodo(db, periodo_id=pr.id, clave=_PARAM_VALOR_HORA_EXTRA)
    valor_hora_nocturna = obtener_parametro_numerico_periodo(db, periodo_id=pr.id, clave=_PARAM_BONO_NOCTURNO_HORA)
    t0, t1 = _rango_datetime(pr.fecha_inicio, pr.fecha_fin)

    db.execute(delete(DetalleRemuneracion).where(DetalleRemuneracion.periodo_remuneracion_id == pr.id))
    db.flush()

    empleados = list(
        db.scalars(select(Empleado).where(Empleado.activo.is_(True)).order_by(Empleado.nombre_completo)).all()
    )
    ref_mid = pr.fecha_inicio
    horas_map: dict[int, RemuneracionHorasPeriodo] = {
        h.empleado_id: h
        for h in db.scalars(
            select(RemuneracionHorasPeriodo).where(RemuneracionHorasPeriodo.periodo_remuneracion_id == pr.id)
        ).all()
    }
    contrato_por_empleado: dict[int, ContratoLaboral] = {}
    for contrato_row in db.scalars(
        select(ContratoLaboral)
        .where(
            ContratoLaboral.estado == "VIGENTE",
            ContratoLaboral.fecha_inicio <= ref_mid,
            or_(ContratoLaboral.fecha_fin.is_(None), ContratoLaboral.fecha_fin >= ref_mid),
        )
        .order_by(ContratoLaboral.fecha_inicio.desc())
    ).all():
        contrato_por_empleado.setdefault(contrato_row.empleado_id, contrato_row)
    flete_por_empleado: dict[int, Decimal] = {}
    if pct_bono > 0:
        for emp_id, total in db.execute(
            select(
                TransporteViaje.empleado_id,
                func.coalesce(func.sum(TransporteViaje.valor_flete), 0),
            )
            .where(
                TransporteViaje.estado == "CERRADO",
                TransporteViaje.real_salida.isnot(None),
                TransporteViaje.real_salida >= t0,
                TransporteViaje.real_salida <= t1,
            )
            .group_by(TransporteViaje.empleado_id)
        ).all():
            flete_por_empleado[int(emp_id)] = _d(total)
    anticipo_por_empleado: dict[int, Decimal] = {}
    for emp_id, total in db.execute(
        select(
            FondoRendir.empleado_id,
            func.coalesce(func.sum(FondoRendir.monto_anticipo), 0),
        )
        .where(
            FondoRendir.estado == "APROBADO",
            FondoRendir.fecha_aprobacion.isnot(None),
            FondoRendir.fecha_aprobacion >= t0,
            FondoRendir.fecha_aprobacion <= t1,
        )
        .group_by(FondoRendir.empleado_id)
    ).all():
        anticipo_por_empleado[int(emp_id)] = _d(total)

    for emp in empleados:
        contrato = contrato_por_empleado.get(emp.id)
        if not contrato:
            continue

        horas_input = horas_map.get(emp.id)
        horas_ordinarias = _d(getattr(horas_input, "horas_ordinarias", Decimal("0")))
        horas_extras = _d(getattr(horas_input, "horas_extras", Decimal("0")))
        horas_nocturnas = _d(getattr(horas_input, "horas_nocturnas", Decimal("0")))
        det = DetalleRemuneracion(
            periodo_remuneracion_id=pr.id,
            empleado_id=emp.id,
            contrato_laboral_id=contrato.id,
            cargo_snapshot=(emp.cargo or "").strip() or None,
            centro_costo_id=contrato.centro_costo_id,
            camion_id=None,
            dias_trabajados=0,
            dias_ausencia=0,
            horas_ordinarias=horas_ordinarias,
            horas_extras=horas_extras,
            horas_nocturnas=horas_nocturnas,
            estado="CALCULADO",
        )
        db.add(det)
        db.flush()

        sueldo = _d(contrato.sueldo_base)
        db.add(
            ItemRemuneracion(
                detalle_remuneracion_id=det.id,
                concepto_remuneracion_id=concepto_sueldo.id,
                cantidad=Decimal("1"),
                valor_unitario=sueldo,
                monto_total=sueldo,
                origen="contrato",
                referencia_tipo="contratos_laborales",
                referencia_id=contrato.id,
                es_ajuste_manual=False,
            )
        )
        if concepto_horas_extras is not None and horas_extras > 0:
            valor_hora_extra = valor_hora_extra_cfg
            if valor_hora_extra <= 0:
                valor_hora_extra = ((sueldo / Decimal("180")) * Decimal("1.5")).quantize(Q2, rounding=ROUND_HALF_UP)
            monto_hex = (horas_extras * valor_hora_extra).quantize(Q2, rounding=ROUND_HALF_UP)
            if monto_hex > 0:
                db.add(
                    ItemRemuneracion(
                        detalle_remuneracion_id=det.id,
                        concepto_remuneracion_id=concepto_horas_extras.id,
                        cantidad=horas_extras,
                        valor_unitario=valor_hora_extra,
                        monto_total=monto_hex,
                        origen="asistencia",
                        referencia_tipo="remuneracion_horas_periodo",
                        referencia_id=(horas_input.id if horas_input else None),
                        es_ajuste_manual=bool(getattr(horas_input, "es_ajuste_manual", False)),
                        motivo_ajuste=getattr(horas_input, "motivo_ajuste", None),
                        usuario_ajuste_id=getattr(horas_input, "usuario_ajuste_id", None),
                    )
                )
        if concepto_bono_nocturno is not None and horas_nocturnas > 0 and valor_hora_nocturna > 0:
            monto_noct = (horas_nocturnas * valor_hora_nocturna).quantize(Q2, rounding=ROUND_HALF_UP)
            if monto_noct > 0:
                db.add(
                    ItemRemuneracion(
                        detalle_remuneracion_id=det.id,
                        concepto_remuneracion_id=concepto_bono_nocturno.id,
                        cantidad=horas_nocturnas,
                        valor_unitario=valor_hora_nocturna,
                        monto_total=monto_noct,
                        origen="asistencia",
                        referencia_tipo="remuneracion_horas_periodo",
                        referencia_id=(horas_input.id if horas_input else None),
                        es_ajuste_manual=bool(getattr(horas_input, "es_ajuste_manual", False)),
                        motivo_ajuste=getattr(horas_input, "motivo_ajuste", None),
                        usuario_ajuste_id=getattr(horas_input, "usuario_ajuste_id", None),
                    )
                )

        if pct_bono > 0:
            sum_flete_d = flete_por_empleado.get(emp.id, Decimal("0"))
            if sum_flete_d > 0:
                monto_bono = (sum_flete_d * pct_bono / Decimal("100")).quantize(Q2, rounding=ROUND_HALF_UP)
                if monto_bono > 0:
                    db.add(
                        ItemRemuneracion(
                            detalle_remuneracion_id=det.id,
                            concepto_remuneracion_id=concepto_bono.id,
                            cantidad=Decimal("1"),
                            valor_unitario=monto_bono,
                            monto_total=monto_bono,
                            origen="viaje",
                            referencia_tipo="agregado_viajes",
                            referencia_id=None,
                            es_ajuste_manual=False,
                        )
                    )

        sum_ant_d = anticipo_por_empleado.get(emp.id, Decimal("0"))
        if sum_ant_d > 0:
            db.add(
                ItemRemuneracion(
                    detalle_remuneracion_id=det.id,
                    concepto_remuneracion_id=concepto_anticipo.id,
                    cantidad=Decimal("1"),
                    valor_unitario=sum_ant_d,
                    monto_total=sum_ant_d,
                    origen="anticipo",
                    referencia_tipo="fondos_rendir_agregado",
                    referencia_id=None,
                    es_ajuste_manual=False,
                )
            )

        base_imp = _suma_montos_imponibles(db, det.id, por_id)
        if base_imp > 0 and concepto_afp is not None and pct_afp > 0:
            m_afp = (base_imp * pct_afp / Decimal("100")).quantize(Q2, rounding=ROUND_HALF_UP)
            if m_afp > 0:
                db.add(
                    ItemRemuneracion(
                        detalle_remuneracion_id=det.id,
                        concepto_remuneracion_id=concepto_afp.id,
                        cantidad=Decimal("1"),
                        valor_unitario=m_afp,
                        monto_total=m_afp,
                        origen="sistema",
                        referencia_tipo="parametro_afp",
                        referencia_id=None,
                        es_ajuste_manual=False,
                    )
                )
        if base_imp > 0 and concepto_salud is not None and pct_salud > 0:
            m_sal = (base_imp * pct_salud / Decimal("100")).quantize(Q2, rounding=ROUND_HALF_UP)
            if m_sal > 0:
                db.add(
                    ItemRemuneracion(
                        detalle_remuneracion_id=det.id,
                        concepto_remuneracion_id=concepto_salud.id,
                        cantidad=Decimal("1"),
                        valor_unitario=m_sal,
                        monto_total=m_sal,
                        origen="sistema",
                        referencia_tipo="parametro_salud",
                        referencia_id=None,
                        es_ajuste_manual=False,
                    )
                )

        _recalcular_totales_detalle(db, det, por_id)

    pr.estado = "CALCULADO"
    pr.fecha_calculo = datetime.utcnow()
    db.add(pr)
    db.flush()
    return pr


def transicionar_estado(
    db: Session,
    periodo_id: int,
    nuevo_estado: str,
    *,
    usuario_id: int | None,
) -> PeriodoRemuneracion:
    """Avance de workflow (el paso a CALCULADO lo hace `calcular_periodo`)."""
    pr = db.get(PeriodoRemuneracion, periodo_id)
    if not pr:
        raise ValueError("Periodo no encontrado.")

    actual = pr.estado
    nuevo = nuevo_estado.strip().upper()

    if nuevo == "ANULADO":
        if actual in ("CERRADO", "PAGADO"):
            raise ValueError("No puede anular un periodo cerrado o pagado.")
        pr.estado = "ANULADO"
        db.add(pr)
        db.flush()
        return pr

    if nuevo in ("CERRADO", "PAGADO"):
        asegurar_periodo_financiero_abierto(db, pr.anio, pr.mes)

    permitidos: dict[str, set[str]] = {
        "CALCULADO": {"EN_REVISION", "APROBADO_RRHH"},
        "EN_REVISION": {"APROBADO_RRHH"},
        "APROBADO_RRHH": {"APROBADO_FINANZAS"},
        "APROBADO_FINANZAS": {"CERRADO"},
        "CERRADO": {"PAGADO"},
    }
    if actual not in permitidos or nuevo not in permitidos.get(actual, set()):
        raise ValueError(f"No se permite pasar de {actual} a {nuevo}.")

    if nuevo == "APROBADO_RRHH" and usuario_id:
        pr.usuario_aprobador_rrhh_id = usuario_id
    if nuevo == "APROBADO_FINANZAS" and usuario_id:
        pr.usuario_aprobador_finanzas_id = usuario_id
    if nuevo == "CERRADO":
        pr.fecha_cierre = datetime.utcnow()
    if nuevo == "PAGADO":
        pr.fecha_pago = datetime.utcnow()

    pr.estado = nuevo
    db.add(pr)
    db.flush()
    return pr
