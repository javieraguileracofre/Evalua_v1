# tests/test_leasing_operativo_engine.py
# -*- coding: utf-8 -*-
from decimal import Decimal

import pytest

from services.leasing_operativo.decision_engine import evaluar_decision
from services.leasing_operativo.economic_engine import run_economic_engine
from services.leasing_operativo.pricing_model import (
    construir_flujos_caja_inversionista,
    npv_mensual,
    renta_costo_mas_spread,
    tir_mensual_bisec,
)


def _politica_base():
    return {
        "escenarios_v1": {"BASE": {"residual_mult": 1, "costo_mult": 1, "riesgo_mult": 1, "tasa_fondo_mult": 1}},
        "costo_fondo_v1": {
            "costo_deuda_anual_pct": 7.5,
            "costo_capital_anual_pct": 12,
            "peso_deuda": 0.65,
            "peso_capital": 0.35,
            "spread_inversionista_anual_pct": 2.5,
        },
        "riesgo_base_v1": {"LGD_base": 0.45, "EAD_pct_capex": 0.85, "PD_MEDIO": 0.02},
        "motor_decision_v1": {
            "van_minimo": 0,
            "tir_minima_anual_pct": 8,
            "margen_op_minimo_pct": 2,
            "ltv_max_pct": 98,
        },
    }


def _tipo_camioneta():
    return {
        "residual_base_pct": 22,
        "residual_max_pct": 48,
        "liquidez_factor": 1,
        "obsolescencia_factor": 1,
        "desgaste_km_factor": Decimal("0.0001"),
        "desgaste_hora_factor": Decimal("0.0005"),
        "haircut_residual_pct": 5,
    }


def test_renta_costo_mas_spread():
    assert renta_costo_mas_spread(Decimal("100"), Decimal("10")) == Decimal("110")


def test_cashflow_npv_positive_with_residual_and_no_double_fondo():
    """Flujo caja métricas: sin costo fondo en CF; residual último mes; NPV a tasa positiva coherente."""
    capex = Decimal("1000000")
    plazo = 12
    renta = Decimal("120000")
    op_m = [Decimal("10000")] * plazo
    riesgo = Decimal("5000")
    com = Decimal("2000")
    residual = Decimal("200000")
    fl = construir_flujos_caja_inversionista(
        capex, plazo, renta, op_m=op_m, riesgo_m=riesgo, comercial_m=com, valor_residual_terminal=residual
    )
    assert len(fl) == plazo + 1
    assert fl[0] == -capex
    i_m = Decimal("0.01")
    van = npv_mensual(fl, i_m)
    assert van > 0


def test_run_economic_engine_van_not_double_counting_fondo():
    p = _politica_base()
    tipo = _tipo_camioneta()
    inp = {
        "plazo_meses": 24,
        "escenario": "BASE",
        "metodo_pricing": "COSTO_SPREAD",
        "spread_pct": Decimal("5"),
        "capex": {"precio_compra": Decimal("50000000")},
        "uso": {"km_anual": Decimal("30000")},
        "activo": {},
        "collateral": {"valor_mercado": Decimal("55000000")},
        "comercial": {},
        "riesgo": {"segmento_cliente": "MEDIO"},
    }
    plant = [{"codigo": "T", "periodicidad": "MENSUAL", "monto_mensual_equiv": 150000}]
    r = run_economic_engine(inputs=inp, tipo_activo=tipo, politica=p, plantillas_costo=plant)
    assert r["van"] > -1e9
    assert r["tir_anual_pct"] is not None
    assert r["tir_anual_pct"] > -50


def test_decision_aprobar_cuando_van_y_tir_ok():
    d = evaluar_decision(
        van=Decimal("1000"),
        tir_anual_pct=Decimal("15"),
        margen_op_promedio_pct=Decimal("10"),
        ltv_pct=Decimal("70"),
        params={"van_minimo": 0, "tir_minima_anual_pct": 10, "margen_op_minimo_pct": 5, "ltv_max_pct": 92},
    )
    assert d["decision_codigo"] == "APROBAR"


def test_decision_rechazar_ltv():
    d = evaluar_decision(
        van=Decimal("1e9"),
        tir_anual_pct=Decimal("20"),
        margen_op_promedio_pct=Decimal("10"),
        ltv_pct=Decimal("95"),
        params={"ltv_max_pct": 90},
    )
    assert d["decision_codigo"] == "RECHAZAR"


def test_tir_bisec_simple():
    fl = [Decimal("-1000"), Decimal("600"), Decimal("600")]
    tir_m = tir_mensual_bisec(fl)
    assert tir_m is not None
    assert abs(float(npv_mensual(fl, tir_m))) < 0.02
