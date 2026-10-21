# tests/test_leasing_operativo_cotizacion_flota.py
# -*- coding: utf-8 -*-
from decimal import Decimal

from services.leasing_operativo.cotizacion_flota import _agregar_resultados, _escalar_result, normalizar_unidad
from services.leasing_operativo.residual_model import estimar_residual_cotizacion


def test_estimar_residual_proyecta_km_y_capital():
    est = estimar_residual_cotizacion(
        valor_bien=Decimal("30000000"),
        plazo_meses=36,
        km_anual=Decimal("40000"),
        km_inicial=Decimal("10000"),
        anio_vehiculo=2024,
        tipo_uso="INTERURBANO",
    )
    assert est["km_fin_estimado"] == 130000.0  # 10k + 40k*3
    assert est["valor_residual_sugerido"] > 0
    assert est["valor_residual_sugerido"] < 30000000
    assert est["capital_amortizable_sugerido"] == 30000000 - est["valor_residual_sugerido"]
    assert est["fuente"] == "modelo_interno"


def test_uso_minero_reduce_residual_vs_urbano():
    base = dict(
        valor_bien=Decimal("25000000"),
        plazo_meses=48,
        km_anual=Decimal("60000"),
        anio_vehiculo=2023,
    )
    urbano = estimar_residual_cotizacion(**base, tipo_uso="URBANO")
    minero = estimar_residual_cotizacion(**base, tipo_uso="MINERO")
    assert minero["valor_residual_sugerido"] < urbano["valor_residual_sugerido"]


def test_normalizar_unidad_cantidad_y_descripcion():
    u = normalizar_unidad(
        {
            "tipo_activo_id": 3,
            "marca": "Toyota",
            "modelo": "Hilux",
            "anio": 2024,
            "cantidad": 2,
            "valor_bien": 28500000,
            "tipo_uso": "FAENA",
            "km_anual": 50000,
        },
        0,
    )
    assert u["cantidad"] == 2
    assert u["tipo_uso"] == "FAENA"
    assert "Hilux" in u["descripcion"]
    assert u["valor_bien"] > 0


def test_escalar_y_agregar_flota():
    unit = {
        "capex_total": 10_000_000,
        "renta_sugerida": 400_000,
        "renta_mensual_neta": 400_000,
        "capital_amortizable": 6_000_000,
        "van": 100_000,
        "tir_anual_pct": 12.0,
        "margen_operacional_promedio_pct": 8.0,
        "valor_residual": {"valor_residual_ajustado": 4_000_000},
        "decision": {"decision_codigo": "APROBAR"},
        "waterfall": [{"concepto": "Depreciación", "monto": 100}],
        "desglose_renta_mensual": {"depreciacion_economica": 50},
    }
    line_a = {"cantidad": 2, "result": _escalar_result(unit, 2)}
    line_b = {
        "cantidad": 1,
        "result": _escalar_result(
            {
                **unit,
                "capex_total": 5_000_000,
                "renta_sugerida": 200_000,
                "renta_mensual_neta": 200_000,
                "capital_amortizable": 3_000_000,
                "van": 40_000,
                "tir_anual_pct": 10.0,
                "decision": {"decision_codigo": "OBSERVAR"},
            },
            1,
        ),
    }
    agg = _agregar_resultados([line_a, line_b])
    assert agg["flota"]["unidades_totales"] == 3
    assert agg["renta_sugerida"] == 1_000_000  # 800k + 200k
    assert agg["capex_total"] == 25_000_000
    assert agg["decision"]["decision_codigo"] == "OBSERVAR"
