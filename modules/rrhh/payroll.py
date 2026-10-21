# modules/rrhh/payroll.py
"""Contrato remuneraciones. Contabilización debe ir por AccountingService."""
from crud.remuneraciones_contabilidad import (
    contabilizar_pago_nomina_periodo,
    contabilizar_provision_nomina_periodo,
)
from services.remuneraciones.calculo_service import calcular_periodo

__all__ = [
    "calcular_periodo",
    "contabilizar_pago_nomina_periodo",
    "contabilizar_provision_nomina_periodo",
]
