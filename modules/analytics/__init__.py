# modules/analytics — read models / KPIs (no mutar operación).
"""Dashboards y reportes. Solo lectura: no contabilizan ni mueven stock."""
from modules.analytics.lecturas import cartera_cxc, contratos_lop_vigentes, leer_vista, resultado_mes

__all__ = [
    "cartera_cxc",
    "contratos_lop_vigentes",
    "leer_vista",
    "resultado_mes",
]
