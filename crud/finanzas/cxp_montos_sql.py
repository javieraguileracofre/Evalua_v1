# crud/finanzas/cxp_montos_sql.py
# -*- coding: utf-8 -*-
"""
Fragmentos SQL reutilizables para totales y saldo CxP desde líneas + impuestos − aplicaciones.
No usar total_linea de BD; coherente con cuentas_por_pagar.list_documentos.
"""
from __future__ import annotations


def cxp_sql_total_desde_lineas(alias: str) -> str:
    """Total documento = Σ(neto_linea + iva_linea) + Σ(impuestos). `alias`: alias de fin.ap_documento (ej. 'd')."""
    a = alias.strip()
    return f"""(
        (
            SELECT COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric
            FROM fin.ap_documento_detalle det
            WHERE det.documento_id = {a}.id
        ) + (
            SELECT COALESCE(SUM(imp.monto), 0)::numeric
            FROM fin.ap_documento_impuesto imp
            WHERE imp.documento_id = {a}.id
        )
    )"""


def cxp_sql_saldo_desde_lineas(alias: str) -> str:
    """Saldo pendiente = GREATEST(total − aplicado, 0)."""
    a = alias.strip()
    tot = cxp_sql_total_desde_lineas(a)
    return f"""GREATEST(
        {tot} - (
            SELECT COALESCE(SUM(ap.monto_aplicado), 0)::numeric
            FROM fin.ap_pago_aplicacion ap
            WHERE ap.documento_id = {a}.id
        ),
        0::numeric
    )"""


def cxp_sql_suma_saldo_por_proveedor(proveedor_id_expr: str) -> str:
    """
    Expresión escalar: suma de saldos pendientes de todos los documentos AP del proveedor.
    Uso: SELECT ... {cxp_sql_suma_saldo_por_proveedor('p.id')} AS saldo_cxp ...
    """
    expr = proveedor_id_expr.strip()
    return f"""COALESCE((
        SELECT SUM(
            GREATEST(
                (
                    (
                        SELECT COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric
                        FROM fin.ap_documento_detalle det
                        WHERE det.documento_id = d.id
                    ) + (
                        SELECT COALESCE(SUM(imp.monto), 0)::numeric
                        FROM fin.ap_documento_impuesto imp
                        WHERE imp.documento_id = d.id
                    )
                ) - (
                    SELECT COALESCE(SUM(ap.monto_aplicado), 0)::numeric
                    FROM fin.ap_pago_aplicacion ap
                    WHERE ap.documento_id = d.id
                ),
                0::numeric
            )
        )::numeric
        FROM fin.ap_documento d
        WHERE d.proveedor_id = {expr}
    ), 0::numeric)"""