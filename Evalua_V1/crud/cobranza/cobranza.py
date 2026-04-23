# crud/cobranza/cobranza.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from models import Cliente, CuentaPorCobrar, PagoCliente

try:
    from models.comunicaciones.email_log import EmailLog  # type: ignore
except Exception:  # pragma: no cover
    EmailLog = None


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _to_int_money(value: Any) -> int:
    try:
        return int(_to_decimal(value))
    except Exception:
        return 0


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _fmt_clp(n: int) -> str:
    return f"$ {_fmt_int(n)}"


def _get_email_log_attr(*names: str):
    if EmailLog is None:
        return None
    for name in names:
        if hasattr(EmailLog, name):
            return getattr(EmailLog, name)
    return None


def listar_cuentas_por_cobrar(
    db: Session,
    *,
    solo_con_saldo: bool = True,
) -> list[CuentaPorCobrar]:
    stmt = select(CuentaPorCobrar)

    if solo_con_saldo:
        stmt = stmt.where(CuentaPorCobrar.saldo_pendiente > 0)

    stmt = stmt.order_by(CuentaPorCobrar.fecha_vencimiento.asc())
    return list(db.scalars(stmt))


def listar_cuentas_por_cobrar_por_cliente(
    db: Session,
    *,
    cliente_id: int,
    solo_con_saldo: bool = True,
    incluir_pagos: bool = False,
) -> list[CuentaPorCobrar]:
    stmt = select(CuentaPorCobrar).where(CuentaPorCobrar.cliente_id == cliente_id)

    if incluir_pagos:
        stmt = stmt.options(selectinload(CuentaPorCobrar.pagos))

    if solo_con_saldo:
        stmt = stmt.where(CuentaPorCobrar.saldo_pendiente > 0)

    stmt = stmt.order_by(CuentaPorCobrar.fecha_vencimiento.asc())
    return list(db.scalars(stmt))


def get_cuenta_por_cobrar(db: Session, cxc_id: int) -> CuentaPorCobrar | None:
    return db.get(CuentaPorCobrar, cxc_id)


def listar_pagos_por_cuenta(
    db: Session,
    *,
    cxc_id: int,
) -> list[PagoCliente]:
    stmt = (
        select(PagoCliente)
        .where(PagoCliente.cuenta_cobrar_id == cxc_id)
        .order_by(PagoCliente.fecha_pago.asc())
    )
    return list(db.scalars(stmt))


def crear_pago(
    db: Session,
    *,
    cxc: CuentaPorCobrar,
    fecha_pago: date,
    monto_pago: float,
    forma_pago: str,
    caja_id: int | None = None,
    referencia: str | None = None,
    observacion: str | None = None,
) -> PagoCliente:
    monto = Decimal(str(monto_pago or 0))
    if monto <= 0:
        raise ValueError("El monto de pago debe ser mayor a 0.")

    saldo_actual = Decimal(str(cxc.saldo_pendiente or 0))
    if monto > saldo_actual:
        raise ValueError("El monto de pago no puede exceder el saldo pendiente.")

    pago_dt = datetime.combine(fecha_pago, time.min)

    pago = PagoCliente(
        cuenta_cobrar_id=cxc.id,
        fecha_pago=pago_dt,
        monto_pago=monto,
        forma_pago=forma_pago,
        caja_id=caja_id,
        referencia=referencia,
        observacion=observacion,
    )

    nuevo_saldo = saldo_actual - monto
    if nuevo_saldo <= 0:
        cxc.saldo_pendiente = Decimal("0.00")
        cxc.estado = "PAGADA"
    else:
        cxc.saldo_pendiente = nuevo_saldo
        cxc.estado = "PARCIAL"

    db.add(pago)
    db.add(cxc)
    db.commit()
    db.refresh(pago)
    db.refresh(cxc)
    return pago


def export_cuentas_por_cobrar(
    db: Session,
    *,
    cliente_id: int | None = None,
    solo_con_saldo: bool | None = None,
) -> list[dict]:
    stmt = (
        select(
            CuentaPorCobrar.id.label("cxc_id"),
            Cliente.id.label("cliente_id"),
            Cliente.razon_social.label("cliente"),
            CuentaPorCobrar.fecha_emision.label("fecha_emision"),
            CuentaPorCobrar.fecha_vencimiento.label("fecha_vencimiento"),
            CuentaPorCobrar.estado.label("estado"),
            CuentaPorCobrar.monto_original.label("monto_original"),
            CuentaPorCobrar.saldo_pendiente.label("saldo_pendiente"),
            CuentaPorCobrar.observacion.label("observacion"),
        )
        .join(Cliente, Cliente.id == CuentaPorCobrar.cliente_id)
    )

    if cliente_id is not None:
        stmt = stmt.where(CuentaPorCobrar.cliente_id == cliente_id)

    if solo_con_saldo is True:
        stmt = stmt.where(CuentaPorCobrar.saldo_pendiente > 0)

    stmt = stmt.order_by(
        Cliente.razon_social.asc(),
        CuentaPorCobrar.fecha_vencimiento.asc(),
    )
    return list(db.execute(stmt).mappings())


def export_pagos_clientes(
    db: Session,
    *,
    cliente_id: int | None = None,
    cxc_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> list[dict]:
    stmt = (
        select(
            PagoCliente.id.label("pago_id"),
            PagoCliente.fecha_pago.label("fecha_pago"),
            PagoCliente.monto_pago.label("monto_pago"),
            PagoCliente.forma_pago.label("forma_pago"),
            PagoCliente.referencia.label("referencia"),
            PagoCliente.observacion.label("observacion"),
            PagoCliente.caja_id.label("caja_id"),
            CuentaPorCobrar.id.label("cxc_id"),
            CuentaPorCobrar.fecha_vencimiento.label("fecha_vencimiento"),
            CuentaPorCobrar.estado.label("estado_cxc"),
            Cliente.id.label("cliente_id"),
            Cliente.razon_social.label("cliente"),
        )
        .join(CuentaPorCobrar, CuentaPorCobrar.id == PagoCliente.cuenta_cobrar_id)
        .join(Cliente, Cliente.id == CuentaPorCobrar.cliente_id)
        .order_by(PagoCliente.fecha_pago.asc())
    )

    if cliente_id is not None:
        stmt = stmt.where(Cliente.id == cliente_id)

    if cxc_id is not None:
        stmt = stmt.where(CuentaPorCobrar.id == cxc_id)

    if desde is not None:
        stmt = stmt.where(PagoCliente.fecha_pago >= datetime.combine(desde, time.min))

    if hasta is not None:
        stmt = stmt.where(PagoCliente.fecha_pago <= datetime.combine(hasta, time.max))

    return list(db.execute(stmt).mappings())


def resumen_cobranza_por_cliente(db: Session) -> list[dict]:
    stmt = (
        select(
            Cliente.id.label("cliente_id"),
            Cliente.razon_social.label("razon_social"),
            func.sum(CuentaPorCobrar.saldo_pendiente).label("monto_total"),
            func.sum(CuentaPorCobrar.saldo_pendiente).label("saldo_pendiente"),
            func.count(CuentaPorCobrar.id).label("documentos"),
        )
        .join(Cliente, Cliente.id == CuentaPorCobrar.cliente_id)
        .where(CuentaPorCobrar.saldo_pendiente > 0)
        .group_by(Cliente.id, Cliente.razon_social)
        .order_by(Cliente.razon_social.asc())
    )
    return list(db.execute(stmt).mappings())


def resumen_cobranza_general(db: Session) -> dict:
    stmt = (
        select(
            func.count(CuentaPorCobrar.id).label("total_documentos"),
            func.sum(CuentaPorCobrar.saldo_pendiente).label("total_monto"),
            func.sum(CuentaPorCobrar.saldo_pendiente).label("total_saldo"),
        )
        .where(CuentaPorCobrar.saldo_pendiente > 0)
    )
    row = db.execute(stmt).mappings().first()
    return row or {"total_documentos": 0, "total_monto": 0, "total_saldo": 0}


def obtener_kpis_dashboard_cobranza(
    db: Session,
    *,
    hoy: date | None = None,
) -> dict:
    hoy = hoy or date.today()

    stmt = (
        select(
            func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0).label("saldo_total_num"),
            func.coalesce(func.count(CuentaPorCobrar.id), 0).label("docs_con_saldo"),
            func.coalesce(func.count(func.distinct(CuentaPorCobrar.cliente_id)), 0).label("clientes_con_saldo"),
        )
        .where(CuentaPorCobrar.saldo_pendiente > 0)
    )
    row = db.execute(stmt).mappings().one()

    saldo_total_num = float(row["saldo_total_num"] or 0)
    docs_con_saldo = int(row["docs_con_saldo"] or 0)
    clientes_con_saldo = int(row["clientes_con_saldo"] or 0)

    stmt_vencidos = (
        select(func.coalesce(func.count(CuentaPorCobrar.id), 0))
        .where(
            CuentaPorCobrar.saldo_pendiente > 0,
            CuentaPorCobrar.fecha_vencimiento < hoy,
        )
    )
    docs_vencidos = int(db.execute(stmt_vencidos).scalar() or 0)

    return {
        "saldo_total_num": saldo_total_num,
        "saldo_total_fmt": _fmt_clp(_to_int_money(saldo_total_num)),
        "docs_con_saldo": docs_con_saldo,
        "clientes_con_saldo": clientes_con_saldo,
        "docs_vencidos": docs_vencidos,
    }


def obtener_top_deudores_dashboard(
    db: Session,
    *,
    limit: int = 10,
) -> list[dict]:
    stmt = (
        select(
            Cliente.id.label("cliente_id"),
            Cliente.razon_social.label("cliente"),
            func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0).label("saldo_num"),
            func.count(CuentaPorCobrar.id).label("docs"),
        )
        .join(Cliente, Cliente.id == CuentaPorCobrar.cliente_id)
        .where(CuentaPorCobrar.saldo_pendiente > 0)
        .group_by(Cliente.id, Cliente.razon_social)
        .order_by(func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0).desc())
        .limit(limit)
    )

    rows = db.execute(stmt).mappings().all()
    result: list[dict] = []

    for row in rows:
        saldo_num = float(row["saldo_num"] or 0)
        result.append(
            {
                "cliente_id": int(row["cliente_id"]),
                "cliente": row["cliente"],
                "saldo_num": saldo_num,
                "saldo_fmt": _fmt_clp(_to_int_money(saldo_num)),
                "docs": int(row["docs"] or 0),
            }
        )

    return result


def obtener_kpis_email_dashboard(
    db: Session,
    *,
    ahora: datetime | None = None,
) -> dict:
    if EmailLog is None:
        return {
            "enviados_24h": 0,
            "errores_24h": 0,
            "enviados_7d": 0,
            "errores_7d": 0,
        }

    ahora = ahora or datetime.utcnow()
    dt_24h = ahora - timedelta(hours=24)
    dt_7d = ahora - timedelta(days=7)

    fecha_attr = _get_email_log_attr("fecha_creacion", "created_at", "creado_en", "fecha", "created_on")
    estado_attr = _get_email_log_attr("estado", "status")

    if fecha_attr is None or estado_attr is None:
        return {
            "enviados_24h": 0,
            "errores_24h": 0,
            "enviados_7d": 0,
            "errores_7d": 0,
        }

    enviado_case = case(
        (estado_attr.in_(["ENVIADO", "SENT", "OK", "ENVIADO_OK"]), 1),
        else_=0,
    )
    error_case = case(
        (estado_attr.in_(["ERROR", "FAILED", "FALLIDO"]), 1),
        else_=0,
    )

    stmt_24h = select(
        func.coalesce(func.sum(enviado_case), 0).label("enviados"),
        func.coalesce(func.sum(error_case), 0).label("errores"),
    ).where(fecha_attr >= dt_24h)

    stmt_7d = select(
        func.coalesce(func.sum(enviado_case), 0).label("enviados"),
        func.coalesce(func.sum(error_case), 0).label("errores"),
    ).where(fecha_attr >= dt_7d)

    row_24h = db.execute(stmt_24h).mappings().one()
    row_7d = db.execute(stmt_7d).mappings().one()

    return {
        "enviados_24h": int(row_24h["enviados"] or 0),
        "errores_24h": int(row_24h["errores"] or 0),
        "enviados_7d": int(row_7d["enviados"] or 0),
        "errores_7d": int(row_7d["errores"] or 0),
    }


def obtener_aging_saldos_dashboard(
    db: Session,
    *,
    hoy: date | None = None,
) -> dict[str, Any]:
    """
    Distribución de saldo pendiente por antigüedad respecto a fecha_vencimiento.
    Corriente: vence después de hoy+7. Próx. 7 días: (hoy, hoy+7]. Buckets de mora por días vencidos.
    """
    hoy = hoy or date.today()
    fv = CuentaPorCobrar.fecha_vencimiento
    saldo = CuentaPorCobrar.saldo_pendiente
    filt = CuentaPorCobrar.saldo_pendiente > 0

    def _sum_case(when) -> Any:
        return func.coalesce(func.sum(case((when, saldo), else_=0)), 0)

    def _cnt_case(when) -> Any:
        return func.coalesce(func.sum(case((when, 1), else_=0)), 0)

    corriente = fv > hoy + timedelta(days=7)
    prox_7 = (fv >= hoy) & (fv <= hoy + timedelta(days=7))
    v_1_30 = (fv < hoy) & (fv >= hoy - timedelta(days=30))
    v_31_60 = (fv < hoy - timedelta(days=30)) & (fv >= hoy - timedelta(days=60))
    v_61_90 = (fv < hoy - timedelta(days=60)) & (fv >= hoy - timedelta(days=90))
    v_m90 = fv < hoy - timedelta(days=90)

    stmt = (
        select(
            _sum_case(corriente).label("saldo_corriente"),
            _cnt_case(corriente).label("docs_corriente"),
            _sum_case(prox_7).label("saldo_proximos_7"),
            _cnt_case(prox_7).label("docs_proximos_7"),
            _sum_case(v_1_30).label("saldo_venc_1_30"),
            _cnt_case(v_1_30).label("docs_venc_1_30"),
            _sum_case(v_31_60).label("saldo_venc_31_60"),
            _cnt_case(v_31_60).label("docs_venc_31_60"),
            _sum_case(v_61_90).label("saldo_venc_61_90"),
            _cnt_case(v_61_90).label("docs_venc_61_90"),
            _sum_case(v_m90).label("saldo_venc_mas_90"),
            _cnt_case(v_m90).label("docs_venc_mas_90"),
        )
        .where(filt)
    )
    row = db.execute(stmt).mappings().one()

    def _f(key: str) -> float:
        return float(row.get(key) or 0)

    def _i(key: str) -> int:
        return int(row.get(key) or 0)

    saldo_vencido_total = (
        _f("saldo_venc_1_30")
        + _f("saldo_venc_31_60")
        + _f("saldo_venc_61_90")
        + _f("saldo_venc_mas_90")
    )
    docs_vencidos_total = (
        _i("docs_venc_1_30")
        + _i("docs_venc_31_60")
        + _i("docs_venc_61_90")
        + _i("docs_venc_mas_90")
    )

    return {
        "saldo_corriente": _f("saldo_corriente"),
        "saldo_corriente_fmt": _fmt_clp(_to_int_money(_f("saldo_corriente"))),
        "docs_corriente": _i("docs_corriente"),
        "saldo_proximos_7": _f("saldo_proximos_7"),
        "saldo_proximos_7_fmt": _fmt_clp(_to_int_money(_f("saldo_proximos_7"))),
        "docs_proximos_7": _i("docs_proximos_7"),
        "saldo_venc_1_30": _f("saldo_venc_1_30"),
        "saldo_venc_1_30_fmt": _fmt_clp(_to_int_money(_f("saldo_venc_1_30"))),
        "docs_venc_1_30": _i("docs_venc_1_30"),
        "saldo_venc_31_60": _f("saldo_venc_31_60"),
        "saldo_venc_31_60_fmt": _fmt_clp(_to_int_money(_f("saldo_venc_31_60"))),
        "docs_venc_31_60": _i("docs_venc_31_60"),
        "saldo_venc_61_90": _f("saldo_venc_61_90"),
        "saldo_venc_61_90_fmt": _fmt_clp(_to_int_money(_f("saldo_venc_61_90"))),
        "docs_venc_61_90": _i("docs_venc_61_90"),
        "saldo_venc_mas_90": _f("saldo_venc_mas_90"),
        "saldo_venc_mas_90_fmt": _fmt_clp(_to_int_money(_f("saldo_venc_mas_90"))),
        "docs_venc_mas_90": _i("docs_venc_mas_90"),
        "saldo_vencido_total": saldo_vencido_total,
        "saldo_vencido_total_fmt": _fmt_clp(_to_int_money(saldo_vencido_total)),
        "docs_vencidos_total": docs_vencidos_total,
    }


def obtener_recuperacion_reciente_dashboard(
    db: Session,
    *,
    hoy: date | None = None,
    dias_ventana: int = 30,
) -> dict[str, Any]:
    """Monto y cantidad de pagos registrados en la ventana vs periodo anterior (misma duración)."""
    hoy = hoy or date.today()
    inicio_actual = datetime.combine(hoy - timedelta(days=dias_ventana), time.min)
    inicio_prev = datetime.combine(hoy - timedelta(days=dias_ventana * 2), time.min)
    fin_prev = inicio_actual

    stmt_act = select(
        func.coalesce(func.sum(PagoCliente.monto_pago), 0).label("monto"),
        func.coalesce(func.count(PagoCliente.id), 0).label("cant"),
    ).where(PagoCliente.fecha_pago >= inicio_actual)

    stmt_prev = select(
        func.coalesce(func.sum(PagoCliente.monto_pago), 0).label("monto"),
        func.coalesce(func.count(PagoCliente.id), 0).label("cant"),
    ).where(PagoCliente.fecha_pago >= inicio_prev, PagoCliente.fecha_pago < fin_prev)

    r_act = db.execute(stmt_act).mappings().one()
    r_prev = db.execute(stmt_prev).mappings().one()

    m_act = float(r_act["monto"] or 0)
    m_prev = float(r_prev["monto"] or 0)
    variacion_pct = ((m_act - m_prev) / m_prev * 100.0) if m_prev > 0 else (100.0 if m_act > 0 else 0.0)

    return {
        "recuperado_monto": m_act,
        "recuperado_monto_fmt": _fmt_clp(_to_int_money(m_act)),
        "recuperado_cant_pagos": int(r_act["cant"] or 0),
        "recuperado_prev_monto": m_prev,
        "recuperado_prev_monto_fmt": _fmt_clp(_to_int_money(m_prev)),
        "recuperado_variacion_pct": variacion_pct,
        "recuperado_dias": dias_ventana,
    }


def obtener_proximos_vencimientos_dashboard(
    db: Session,
    *,
    hoy: date | None = None,
    limit: int = 14,
) -> list[dict[str, Any]]:
    """Documentos con saldo ordenados por vencimiento (los más urgentes primero)."""
    hoy = hoy or date.today()
    stmt = (
        select(
            CuentaPorCobrar.id.label("cxc_id"),
            Cliente.id.label("cliente_id"),
            Cliente.razon_social.label("cliente"),
            CuentaPorCobrar.fecha_vencimiento.label("fecha_vencimiento"),
            CuentaPorCobrar.saldo_pendiente.label("saldo"),
            CuentaPorCobrar.estado.label("estado"),
        )
        .join(Cliente, Cliente.id == CuentaPorCobrar.cliente_id)
        .where(CuentaPorCobrar.saldo_pendiente > 0)
        .order_by(CuentaPorCobrar.fecha_vencimiento.asc(), CuentaPorCobrar.id.asc())
        .limit(limit)
    )
    rows = db.execute(stmt).mappings().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        fv = r["fecha_vencimiento"]
        if fv is None:
            continue
        dias = (fv - hoy).days
        if dias > 0:
            urgencia = f"Vence en {dias} día{'s' if dias != 1 else ''}"
            badge = "proximo"
        elif dias == 0:
            urgencia = "Vence hoy"
            badge = "hoy"
        else:
            dv = abs(dias)
            urgencia = f"Vencido hace {dv} día{'s' if dv != 1 else ''}"
            badge = "vencido"

        saldo_f = float(r["saldo"] or 0)
        out.append(
            {
                "cxc_id": int(r["cxc_id"]),
                "cliente_id": int(r["cliente_id"]),
                "cliente": r["cliente"],
                "fecha_vencimiento": fv,
                "saldo_num": saldo_f,
                "saldo_fmt": _fmt_clp(_to_int_money(saldo_f)),
                "estado": r.get("estado") or "",
                "urgencia": urgencia,
                "badge": badge,
                "dias": dias,
            }
        )
    return out


def obtener_ultimos_emails_dashboard(
    db: Session,
    *,
    limit: int = 20,
) -> list[dict]:
    if EmailLog is None:
        return []

    fecha_attr = _get_email_log_attr("fecha_creacion", "created_at", "creado_en", "fecha", "created_on")
    estado_attr = _get_email_log_attr("estado", "status")

    if fecha_attr is None:
        return []

    stmt = select(EmailLog).order_by(fecha_attr.desc()).limit(limit)
    logs = list(db.scalars(stmt))

    result: list[dict] = []
    for log in logs:
        cliente_id = getattr(log, "cliente_id", None)
        cliente = db.get(Cliente, cliente_id) if cliente_id else None

        fecha_val = getattr(log, getattr(fecha_attr, "key", "fecha_creacion"), None)
        if not fecha_val:
            fecha_val = (
                getattr(log, "fecha_creacion", None)
                or getattr(log, "created_at", None)
                or getattr(log, "fecha", None)
            )

        estado_val = None
        if estado_attr is not None:
            estado_val = getattr(log, getattr(estado_attr, "key", "estado"), None)
        if not estado_val:
            estado_val = getattr(log, "estado", None) or getattr(log, "status", None) or "—"

        destino = (
            getattr(log, "to_email", None)
            or getattr(log, "destino", None)
            or getattr(log, "email", None)
            or "—"
        )

        error_val = (
            getattr(log, "error", None)
            or getattr(log, "error_msg", None)
            or getattr(log, "mensaje_error", None)
            or "—"
        )

        result.append(
            {
                "id": getattr(log, "id", None),
                "fecha": fecha_val,
                "cliente": cliente.razon_social if cliente else (getattr(log, "cliente_nombre", None) or "—"),
                "destino": destino,
                "estado": estado_val,
                "error": (str(error_val)[:180] + "…") if error_val and len(str(error_val)) > 180 else error_val,
            }
        )

    return result