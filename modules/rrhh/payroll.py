# modules/rrhh/payroll.py
"""Contrato remuneraciones. Contabilización debe ir por AccountingService."""
from services.remuneraciones.calculo_service import calcular_periodo  # noqa: F401

__all__ = ["calcular_periodo"]
