# crud/finanzas/cxp_montos_sql.py
# -*- coding: utf-8 -*-
"""
Totales CxP en una agregación por documento.

Las consultas hacen LEFT JOIN a tres subconsultas agrupadas
(líneas, impuestos, aplicaciones). El total y el saldo se leen
de esos alias (`ln`, `im`, `ap`), sin una subconsulta por fila.
"""
from __future__ import annotations


def cxp_agregados_joins(doc_alias: str = "d") -> str:
    """JOINs agrupados. El alias del documento debe ser el de la consulta externa."""
    a = doc_alias.strip()
    return f"""
LEFT JOIN (
    SELECT
        documento_id,
        COALESCE(SUM(neto_linea + iva_linea), 0)::numeric AS sum_tl,
        COALESCE(SUM(neto_linea), 0)::numeric AS sum_nl,
        COALESCE(SUM(iva_linea), 0)::numeric AS sum_il
    FROM fin.ap_documento_detalle
    GROUP BY documento_id
) ln ON ln.documento_id = {a}.id
LEFT JOIN (
    SELECT documento_id, COALESCE(SUM(monto), 0)::numeric AS sum_imp
    FROM fin.ap_documento_impuesto
    GROUP BY documento_id
) im ON im.documento_id = {a}.id
LEFT JOIN (
    SELECT documento_id, COALESCE(SUM(monto_aplicado), 0)::numeric AS sum_app
    FROM fin.ap_pago_aplicacion
    GROUP BY documento_id
) ap ON ap.documento_id = {a}.id
"""


def cxp_sql_total_desde_lineas(alias: str = "d") -> str:
    """Total = Σ(neto_linea + iva_linea) + Σ(impuestos). Requiere `cxp_agregados_joins`."""
    del alias
    return "(COALESCE(ln.sum_tl, 0::numeric) + COALESCE(im.sum_imp, 0::numeric))"


def cxp_sql_saldo_desde_lineas(alias: str = "d") -> str:
    """Saldo = GREATEST(total − aplicado, 0). Requiere `cxp_agregados_joins`."""
    del alias
    return (
        "GREATEST("
        "COALESCE(ln.sum_tl, 0::numeric) + COALESCE(im.sum_imp, 0::numeric)"
        " - COALESCE(ap.sum_app, 0::numeric), 0::numeric)"
    )


def cxp_saldo_proveedor_join(proveedor_alias: str = "p") -> str:
    """Un agregado de saldo por proveedor, unido una sola vez."""
    p = proveedor_alias.strip()
    saldo = cxp_sql_saldo_desde_lineas("d")
    return f"""
LEFT JOIN (
    SELECT
        d.proveedor_id,
        COALESCE(SUM({saldo}), 0)::numeric AS saldo_cxp
    FROM fin.ap_documento d
    {cxp_agregados_joins("d")}
    GROUP BY d.proveedor_id
) cxp_prov ON cxp_prov.proveedor_id = {p}.id
"""
