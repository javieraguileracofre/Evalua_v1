# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from services.leasing_operativo.amortizacion import calcular_tabla_amortizacion_operacional, totales_amortizacion_operacional
from services.leasing_operativo.gestion_cartera import calcular_mora_cuota, calcular_penalidad_terminacion


def test_amortizacion_operacional_recupero_inversion():
    flujo = [
        {"mes": 1, "venta": 100, "costo_fondo": 20, "depreciacion": 30, "costos_operativos": 5, "prima_riesgo": 3, "comercial": 2, "resultado_operacional": 40},
        {"mes": 2, "venta": 100, "costo_fondo": 18, "depreciacion": 30, "costos_operativos": 5, "prima_riesgo": 3, "comercial": 2, "resultado_operacional": 42},
    ]
    tabla = calcular_tabla_amortizacion_operacional(
        capex_total=Decimal("1000"),
        valor_residual=Decimal("100"),
        plazo_meses=2,
        flujo_mensual=flujo,
        fecha_inicio=date(2026, 1, 1),
    )
    assert len(tabla) == 2
    assert tabla[0].saldo_inversion_inicial == Decimal("1000.00")
    assert tabla[-1].saldo_inversion_final >= Decimal("100.00")
    tot = totales_amortizacion_operacional(tabla)
    assert tot["total_rentas"] == Decimal("200.00")


def test_calcular_mora_cuota():
    q = MagicMock()
    q.monto_renta = Decimal("1000000")
    mora = calcular_mora_cuota(
        cuota=q,
        dias_mora=10,
        politica_mora={"tasa_mora_diaria_pct": 0.05, "mora_sobre": "NETO"},
    )
    assert mora == Decimal("5000.00")


def test_penalidad_terminacion():
    ctr = MagicMock()
    ctr.cuotas = [
        MagicMock(estado="PENDIENTE", monto_renta=Decimal("100")),
        MagicMock(estado="PAGADA", monto_renta=Decimal("100")),
    ]
    sim = MagicMock()
    sim.result_json = {"capex_total": 1000}
    pen = calcular_penalidad_terminacion(
        contrato=ctr,
        sim=sim,
        politica_term={"penalidad_pct_rentas_pendientes": 50, "penalidad_pct_capex_remanente": 10},
    )
    assert pen > Decimal("0")
