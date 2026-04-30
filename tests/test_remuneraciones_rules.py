# tests/test_remuneraciones_rules.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from services.remuneraciones.calculo_service import (
    asegurar_periodo_financiero_abierto,
    puede_editar_periodo,
)


class _PR:
    def __init__(self, estado: str) -> None:
        self.estado = estado


def test_puede_editar_periodo_abiertos() -> None:
    assert puede_editar_periodo(_PR("BORRADOR")) is True
    assert puede_editar_periodo(_PR("CALCULADO")) is True
    assert puede_editar_periodo(_PR("CERRADO")) is False


def test_asegurar_periodo_financiero_sin_bd_documenta_contrato() -> None:
    """Solo documenta que la función existe (integración real requiere PostgreSQL + fin.periodo)."""
    assert callable(asegurar_periodo_financiero_abierto)
