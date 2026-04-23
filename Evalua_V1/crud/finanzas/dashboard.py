# crud/finanzas/dashboard.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from crud.finanzas.cxp_montos_sql import cxp_sql_saldo_desde_lineas, cxp_sql_total_desde_lineas

logger = logging.getLogger("evalua.fin.dashboard")

_CXP_TOT = cxp_sql_total_desde_lineas("d")
_CXP_SAL = cxp_sql_saldo_desde_lineas("d")

_RATIO_TOL = Decimal("0.01")


def _dec_ratio(x: Any) -> Decimal:
    if x is None:
        return Decimal("0")
    return Decimal(str(x))


def _ratio_div(num: Decimal, den: Decimal) -> Decimal | None:
    if den is None or abs(den) < _RATIO_TOL:
        return None
    return num / den


def _sum_por_clasificacion(rows: list[dict[str, Any]], *, clasifs: frozenset[str]) -> Decimal:
    s = Decimal("0")
    for r in rows:
        cl = str(r.get("clasificacion") or "").strip().upper()
        if cl in clasifs:
            s += _dec_ratio(r.get("monto"))
    return s


def _zeros_kpi() -> dict[str, Any]:
    return {
        "docs_total": 0,
        "monto_total": 0,
        "saldo_pendiente": 0,
        "saldo_vencido": 0,
        "pagado_mes": 0,
        "gasto_mes": 0,
    }


def get_kpis(db: Session) -> dict[str, Any]:
    """
    KPIs alineados con la lista de CxP (`cuentas_por_pagar.get_resumen`), no con `fin.vw_kpi_dashboard_fin`
    (la vista puede quedar desactualizada tras cambios de DDL y mostraría ceros con datos reales).
    Pagado del mes: `fin.ap_pago` en estado APLICADO (misma regla que la vista 095).
    """
    try:
        from crud.finanzas.cuentas_por_pagar import cuentas_por_pagar as crud_cxp_mod

        r = crud_cxp_mod.get_resumen(db)
    except Exception:
        logger.exception("Dashboard KPI: get_resumen CxP falló")
        return _zeros_kpi()

    pagado_mes = 0.0
    try:
        row_p = db.execute(
            text(
                """
                SELECT COALESCE(SUM(p.monto_total), 0)::numeric(18, 2) AS pagado_mes
                FROM fin.ap_pago p
                WHERE p.estado::text = 'APLICADO'
                  AND date_trunc('month', p.fecha_pago::timestamp) = date_trunc('month', CURRENT_TIMESTAMP)
                """
            )
        ).mappings().first()
        if row_p and row_p.get("pagado_mes") is not None:
            pagado_mes = float(row_p["pagado_mes"])
    except Exception:
        logger.exception("Dashboard KPI: lectura pagado_mes desde ap_pago")

    return {
        "docs_total": int(r.get("documentos") or 0),
        "monto_total": float(r.get("total_documentado") or 0),
        "saldo_pendiente": float(r.get("saldo_pendiente") or 0),
        "saldo_vencido": float(r.get("saldo_vencido") or 0),
        "pagado_mes": pagado_mes,
        "gasto_mes": 0.0,
    }


def get_aging(db: Session, limit: int = 80) -> list[dict[str, Any]]:
    try:
        rows = db.execute(
            text(
                f"""
                SELECT
                    d.id,
                    d.proveedor_id,
                    COALESCE(p.razon_social, 'Proveedor ' || d.proveedor_id::text) AS proveedor_nombre,
                    d.folio,
                    d.fecha_emision,
                    d.fecha_vencimiento,
                    ({_CXP_TOT}) AS total,
                    ({_CXP_SAL}) AS saldo_pendiente,
                    GREATEST(0, CURRENT_DATE - d.fecha_vencimiento)::int AS dias_mora
                FROM fin.ap_documento d
                LEFT JOIN public.proveedor p ON p.id = d.proveedor_id
                WHERE ({_CXP_SAL}) > 0
                  AND d.fecha_vencimiento IS NOT NULL
                  AND d.fecha_vencimiento <= CURRENT_DATE
                  AND COALESCE(d.estado::text, '') <> 'ANULADO'
                ORDER BY dias_mora DESC, ({_CXP_SAL}) DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()

        return [dict(r) for r in rows]
    except Exception:
        return []


def get_docs_recientes(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    try:
        rows = db.execute(
            text(
                f"""
                SELECT
                    d.id,
                    d.proveedor_id,
                    COALESCE(p.razon_social, 'Proveedor ' || d.proveedor_id::text) AS proveedor_nombre,
                    d.folio,
                    d.fecha_emision,
                    d.fecha_vencimiento,
                    d.estado,
                    ({_CXP_TOT}) AS total,
                    ({_CXP_SAL}) AS saldo_pendiente
                FROM fin.ap_documento d
                LEFT JOIN public.proveedor p ON p.id = d.proveedor_id
                ORDER BY d.created_at DESC, d.id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()

        return [dict(r) for r in rows]
    except Exception:
        return []


def get_resumen_por_estado(db: Session) -> list[dict[str, Any]]:
    try:
        rows = db.execute(
            text(
                f"""
                SELECT
                    COALESCE(d.estado::text, 'SIN_ESTADO') AS estado,
                    COUNT(*)::bigint AS cantidad,
                    COALESCE(SUM(({_CXP_TOT})), 0) AS monto_total,
                    COALESCE(SUM(({_CXP_SAL})), 0) AS saldo_total
                FROM fin.ap_documento d
                GROUP BY COALESCE(d.estado::text, 'SIN_ESTADO')
                ORDER BY cantidad DESC, monto_total DESC
                """
            )
        ).mappings().all()

        return [dict(r) for r in rows]
    except Exception:
        return []


def get_top_proveedores_saldo(db: Session, limit: int = 10) -> list[dict[str, Any]]:
    try:
        rows = db.execute(
            text(
                f"""
                SELECT
                    p.id AS proveedor_id,
                    p.razon_social,
                    COUNT(d.id)::bigint AS documentos,
                    COALESCE(SUM(({_CXP_SAL})), 0) AS saldo_total
                FROM fin.ap_documento d
                JOIN public.proveedor p
                  ON p.id = d.proveedor_id
                WHERE ({_CXP_SAL}) > 0
                GROUP BY p.id, p.razon_social
                ORDER BY saldo_total DESC, documentos DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()

        return [dict(r) for r in rows]
    except Exception:
        return []


def get_flujo_caja_efectivo(db: Session) -> dict[str, Any]:
    """
    Flujo de caja efectivo (egresos) al día vía CxP: solo pagos `fin.ap_pago` en estado APLICADO.
    Compromisos de salida: saldos pendientes por ventana de vencimiento (misma regla de saldo que el resto del módulo).
    Incluye documentos en BORRADOR con saldo (igual que la lista CxP); no exige estado contable final.
    """
    sal = _CXP_SAL
    out = {
        "egreso_hoy": 0,
        "n_pagos_hoy": 0,
        "egreso_mes": 0,
        "n_pagos_mes": 0,
        "egreso_30d": 0,
        "n_pagos_30d": 0,
        "egreso_ytd": 0,
        "exigible_vencido": 0,
        "exigible_7d": 0,
        "exigible_8_30d": 0,
        "exigible_mas_30d": 0,
        "exigible_sin_fecha": 0,
    }
    try:
        row_pagos = db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(CASE
                        WHEN p.estado::text = 'APLICADO' AND p.fecha_pago = CURRENT_DATE
                        THEN p.monto_total ELSE 0::numeric END), 0)::numeric(18, 2) AS egreso_hoy,
                    COUNT(*) FILTER (
                        WHERE p.estado::text = 'APLICADO' AND p.fecha_pago = CURRENT_DATE
                    )::bigint AS n_pagos_hoy,
                    COALESCE(SUM(CASE
                        WHEN p.estado::text = 'APLICADO'
                         AND date_trunc('month', p.fecha_pago::timestamp) = date_trunc('month', CURRENT_TIMESTAMP)
                        THEN p.monto_total ELSE 0::numeric END), 0)::numeric(18, 2) AS egreso_mes,
                    COUNT(*) FILTER (
                        WHERE p.estado::text = 'APLICADO'
                          AND date_trunc('month', p.fecha_pago::timestamp) = date_trunc('month', CURRENT_TIMESTAMP)
                    )::bigint AS n_pagos_mes,
                    COALESCE(SUM(CASE
                        WHEN p.estado::text = 'APLICADO'
                         AND p.fecha_pago >= (CURRENT_DATE - INTERVAL '29 days')
                         AND p.fecha_pago <= CURRENT_DATE
                        THEN p.monto_total ELSE 0::numeric END), 0)::numeric(18, 2) AS egreso_30d,
                    COUNT(*) FILTER (
                        WHERE p.estado::text = 'APLICADO'
                          AND p.fecha_pago >= (CURRENT_DATE - INTERVAL '29 days')
                          AND p.fecha_pago <= CURRENT_DATE
                    )::bigint AS n_pagos_30d,
                    COALESCE(SUM(CASE
                        WHEN p.estado::text = 'APLICADO'
                         AND EXTRACT(YEAR FROM p.fecha_pago) = EXTRACT(YEAR FROM CURRENT_DATE)
                        THEN p.monto_total ELSE 0::numeric END), 0)::numeric(18, 2) AS egreso_ytd
                FROM fin.ap_pago p
                """
            )
        ).mappings().first()
        if row_pagos:
            rp = dict(row_pagos)
            for k in ("egreso_hoy", "egreso_mes", "egreso_30d", "egreso_ytd"):
                out[k] = float(rp.get(k) or 0)
            for k in ("n_pagos_hoy", "n_pagos_mes", "n_pagos_30d"):
                out[k] = int(rp.get(k) or 0)
    except Exception:
        logger.exception("Flujo caja: error leyendo egresos (ap_pago)")

    try:
        row_comp = db.execute(
            text(
                f"""
                SELECT
                    COALESCE(SUM(CASE
                        WHEN ({sal}) > 0::numeric AND d.fecha_vencimiento < CURRENT_DATE
                        THEN ({sal}) ELSE 0::numeric END), 0)::numeric(18, 2) AS exigible_vencido,
                    COALESCE(SUM(CASE
                        WHEN ({sal}) > 0::numeric
                         AND d.fecha_vencimiento >= CURRENT_DATE
                         AND d.fecha_vencimiento <= (CURRENT_DATE + INTERVAL '7 days')::date
                        THEN ({sal}) ELSE 0::numeric END), 0)::numeric(18, 2) AS exigible_7d,
                    COALESCE(SUM(CASE
                        WHEN ({sal}) > 0::numeric
                         AND d.fecha_vencimiento > (CURRENT_DATE + INTERVAL '7 days')::date
                         AND d.fecha_vencimiento <= (CURRENT_DATE + INTERVAL '30 days')::date
                        THEN ({sal}) ELSE 0::numeric END), 0)::numeric(18, 2) AS exigible_8_30d,
                    COALESCE(SUM(CASE
                        WHEN ({sal}) > 0::numeric
                         AND d.fecha_vencimiento > (CURRENT_DATE + INTERVAL '30 days')::date
                        THEN ({sal}) ELSE 0::numeric END), 0)::numeric(18, 2) AS exigible_mas_30d,
                    COALESCE(SUM(CASE
                        WHEN ({sal}) > 0::numeric AND d.fecha_vencimiento IS NULL
                        THEN ({sal}) ELSE 0::numeric END), 0)::numeric(18, 2) AS exigible_sin_fecha
                FROM fin.ap_documento d
                WHERE COALESCE(d.estado::text, '') <> 'ANULADO'
                """
            )
        ).mappings().first()
        if row_comp:
            for k, v in dict(row_comp).items():
                out[k] = float(v or 0)
    except Exception:
        logger.exception("Flujo caja: error leyendo compromisos por vencimiento (ap_documento)")

    return out


def get_tesoreria_cajas(db: Session) -> dict[str, Any]:
    """Saldos de cajas físicas / punto de venta (`public.cajas`), solo activas."""
    try:
        from sqlalchemy import select

        from models.finanzas.caja import Caja

        rows = list(
            db.scalars(select(Caja).where(Caja.activa.is_(True)).order_by(Caja.nombre.asc())).all()
        )
        total = sum(float(c.saldo_actual or 0) for c in rows)
        return {
            "disponible": True,
            "total_saldo": total,
            # clave "cajas": en Jinja `tc.items` colisiona con dict.items()
            "cajas": [
                {
                    "id": int(c.id),
                    "nombre": str(c.nombre or ""),
                    "saldo": float(c.saldo_actual or 0),
                    "estado": str(c.estado or ""),
                }
                for c in rows
            ],
        }
    except Exception:
        logger.exception("Dashboard tesorería: lectura de cajas")
        return {"disponible": False, "total_saldo": 0.0, "cajas": []}


def get_tesoreria_efectivo_bancos_contable(db: Session, *, fecha_hasta: str | None = None) -> dict[str, Any]:
    """
    Saldos de **activo** en cuentas de caja y bancos según el plan de cuentas y los asientos
    (misma lógica de signo que el balance general). Incluye patrones típicos Chile (1101*, 1102*)
    y el seed premium (1.1.1, 1.1.2 y subcuentas).
    Complementa el maestro `public.cajas` (POS) y es independiente de `fin.mov_banco`.
    """
    vacio: dict[str, Any] = {
        "disponible": False,
        "total_saldo": 0.0,
        "cuentas": [],
        "mensaje": "",
    }
    try:
        hasta = fecha_hasta or date.today().isoformat()
        extra = "AND ac.fecha <= :fecha_hasta"
        rows = db.execute(
            text(
                f"""
                SELECT
                    TRIM(COALESCE(ad.codigo_cuenta, ad.cuenta_contable)) AS codigo,
                    COALESCE(NULLIF(TRIM(ad.nombre_cuenta), ''), pc.nombre) AS nombre,
                    SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0))::numeric(18, 2) AS saldo
                FROM asientos_detalle ad
                INNER JOIN asientos_contables ac
                    ON ac.id = ad.asiento_id
                INNER JOIN fin.plan_cuenta pc
                    ON pc.codigo = COALESCE(ad.codigo_cuenta, ad.cuenta_contable)
                WHERE pc.tipo = 'ACTIVO'
                  {extra}
                  AND (
                        TRIM(pc.codigo) IN ('1.1.1', '1.1.2')
                     OR pc.codigo LIKE '1.1.1.%'
                     OR pc.codigo LIKE '1.1.2.%'
                     OR pc.codigo LIKE '1101%'
                     OR pc.codigo LIKE '1102%'
                  )
                GROUP BY 1, 2
                HAVING ABS(SUM(COALESCE(ad.debe, 0) - COALESCE(ad.haber, 0))) >= 0.005
                ORDER BY 1
                """
            ),
            {"fecha_hasta": hasta},
        ).mappings().all()
        cuentas = [
            {
                "codigo": str(r["codigo"] or ""),
                "nombre": str(r["nombre"] or ""),
                "saldo": float(r["saldo"] or 0),
            }
            for r in rows
        ]
        total = sum(c["saldo"] for c in cuentas)
        return {
            "disponible": True,
            "total_saldo": total,
            "cuentas": cuentas,
            "mensaje": "",
        }
    except Exception:
        logger.exception("Dashboard tesorería: saldos contables caja/banco")
        vacio["mensaje"] = (
            "No se pudieron leer saldos contables de caja/banco (tablas de asientos o plan de cuentas)."
        )
        return vacio


def get_tesoreria_banco_cartola(db: Session, *, limite_movs: int = 10) -> dict[str, Any]:
    """
    Cartola importada en `fin.mov_banco` (script 84_fin_conciliacion_bancaria.sql).
    No es saldo contable de cuenta corriente sin saldo inicial: muestra flujo neto del período y últimos movimientos.
    """
    lim = max(1, min(int(limite_movs), 50))
    vacio: dict[str, Any] = {
        "disponible": False,
        "tabla_existe": False,
        "flujo_neto_30d": 0.0,
        "flujo_neto_hoy": 0.0,
        "ultimos": [],
        "mensaje": "",
    }
    try:
        ok = db.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'fin' AND table_name = 'mov_banco'
                LIMIT 1
                """
            )
        ).scalar()
        if not ok:
            vacio["mensaje"] = "Instale la cartola (`db/psql/84_fin_conciliacion_bancaria.sql`) para ver bancos aquí."
            return vacio

        row30 = db.execute(
            text(
                """
                SELECT COALESCE(SUM(monto), 0)::numeric(18, 2) AS n
                FROM fin.mov_banco
                WHERE fecha >= (CURRENT_DATE - INTERVAL '29 days')
                  AND fecha <= CURRENT_DATE
                """
            )
        ).mappings().first()
        row_hoy = db.execute(
            text(
                """
                SELECT COALESCE(SUM(monto), 0)::numeric(18, 2) AS n
                FROM fin.mov_banco
                WHERE fecha = CURRENT_DATE
                """
            )
        ).mappings().first()
        rows = db.execute(
            text(
                """
                SELECT
                    id,
                    fecha,
                    LEFT(descripcion, 52) AS descripcion,
                    monto,
                    estado::text AS estado
                FROM fin.mov_banco
                ORDER BY fecha DESC, id DESC
                LIMIT :lim
                """
            ),
            {"lim": lim},
        ).mappings().all()

        return {
            "disponible": True,
            "tabla_existe": True,
            "flujo_neto_30d": float(row30["n"] or 0) if row30 else 0.0,
            "flujo_neto_hoy": float(row_hoy["n"] or 0) if row_hoy else 0.0,
            "ultimos": [dict(r) for r in rows],
            "mensaje": "",
        }
    except Exception:
        logger.exception("Dashboard tesorería: lectura fin.mov_banco")
        vacio["mensaje"] = "No se pudo leer la cartola bancaria."
        return vacio


def get_ratios_financieros(db: Session) -> dict[str, Any]:
    """
    Seis ratios ejecutivos: liquidez y prueba ácida (balance), endeudamiento, ROA, ROE y margen
    operacional (estado de resultados YTD). ROA/ROE usan resultado operacional como aproximación
    de utilidad cuando no hay utilidad neta explícita en el ER generado.
    """
    vacio: dict[str, Any] = {
        "disponible": False,
        "mensaje": "",
        "periodo_er": "",
        "balance_cuadra": None,
        "ratios": [],
    }
    try:
        from crud.finanzas.contabilidad_asientos import (
            obtener_balance_general,
            obtener_estado_resultados,
        )

        hoy = date.today()
        desde = hoy.replace(month=1, day=1).isoformat()
        hasta = hoy.isoformat()

        bal = obtener_balance_general(db, fecha_hasta=hasta)
        er = obtener_estado_resultados(db, fecha_desde=desde, fecha_hasta=hasta)

        activos = list(bal.get("activos") or [])
        pasivos = list(bal.get("pasivos") or [])
        t_act = _dec_ratio(bal.get("total_activos"))
        t_pas = _dec_ratio(bal.get("total_pasivos"))
        t_pat = _dec_ratio(bal.get("total_patrimonio"))

        ac = _sum_por_clasificacion(activos, clasifs=frozenset({"ACTIVO_CORRIENTE"}))
        pc = _sum_por_clasificacion(pasivos, clasifs=frozenset({"PASIVO_CORRIENTE"}))
        inv = _sum_por_clasificacion(
            activos,
            clasifs=frozenset(
                {
                    "INVENTARIO",
                    "INVENTARIOS",
                    "ACTIVO_INVENTARIO",
                    "EXISTENCIAS",
                }
            ),
        )

        ing = _dec_ratio(er.get("total_ingresos"))
        rop = _dec_ratio(er.get("resultado_operacional"))

        liq = _ratio_div(ac, pc)
        acida = _ratio_div(ac - inv, pc)
        endeud = _ratio_div(t_pas, t_pat)
        roa = _ratio_div(rop, t_act)
        roe = _ratio_div(rop, t_pat)
        margen = _ratio_div(rop, ing)

        def _f(v: Decimal | None) -> float | None:
            if v is None:
                return None
            return float(v)

        ratios: list[dict[str, Any]] = [
            {
                "id": "liquidez_corriente",
                "titulo": "Liquidez corriente",
                "detalle": "Activo corriente ÷ pasivo corriente (balance al día).",
                "valor": _f(liq),
                "formato": "veces",
            },
            {
                "id": "prueba_acida",
                "titulo": "Prueba ácida",
                "detalle": "(Activo corriente − inventario*) ÷ pasivo corriente. *Inventario según clasificación en plan de cuentas.",
                "valor": _f(acida),
                "formato": "veces",
            },
            {
                "id": "endeudamiento",
                "titulo": "Endeudamiento",
                "detalle": "Pasivo total ÷ patrimonio (apalancamiento).",
                "valor": _f(endeud),
                "formato": "veces",
            },
            {
                "id": "roa",
                "titulo": "ROA (YTD)",
                "detalle": "Resultado operacional acumulado año ÷ activo total (balance al día).",
                "valor": _f(roa),
                "formato": "porcentaje",
            },
            {
                "id": "roe",
                "titulo": "ROE (YTD)",
                "detalle": "Resultado operacional acumulado año ÷ patrimonio (rentabilidad del capital).",
                "valor": _f(roe),
                "formato": "porcentaje",
            },
            {
                "id": "margen_operacional",
                "titulo": "Margen operacional (YTD)",
                "detalle": "Resultado operacional ÷ ingresos del mismo período.",
                "valor": _f(margen),
                "formato": "porcentaje",
            },
        ]

        return {
            "disponible": True,
            "mensaje": "",
            "periodo_er": f"Estado de resultados: 01-01-{hoy.year} a {hoy.strftime('%d-%m-%Y')}",
            "balance_cuadra": bool(bal.get("cuadra")),
            "ratios": ratios,
        }
    except Exception:
        logger.exception("Dashboard: ratios financieros")
        vacio["mensaje"] = (
            "No se pudieron calcular ratios (revise plan de cuentas, asientos y tablas de contabilidad)."
        )
        return vacio


def get_movimientos_caja_recientes(db: Session, limit: int = 18) -> list[dict[str, Any]]:
    """Últimos pagos a proveedores considerados efectivos (APLICADO)."""
    try:
        rows = db.execute(
            text(
                """
                SELECT
                    p.id,
                    p.fecha_pago,
                    p.monto_total,
                    p.medio_pago::text AS medio_pago,
                    COALESCE(p.referencia, '') AS referencia,
                    pr.razon_social AS proveedor_nombre
                FROM fin.ap_pago p
                INNER JOIN public.proveedor pr ON pr.id = p.proveedor_id
                WHERE p.estado::text = 'APLICADO'
                ORDER BY p.fecha_pago DESC, p.id DESC
                LIMIT :lim
                """
            ),
            {"lim": max(1, min(int(limit), 100))},
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []