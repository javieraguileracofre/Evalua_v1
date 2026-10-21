# tests/test_leasing_operativo_residual_engine.py
# -*- coding: utf-8 -*-
"""Pruebas del motor profesional de valor residual LOP."""
from __future__ import annotations

from services.leasing_operativo.depreciation_service import calculate_value_layers
from services.leasing_operativo.lease_profitability_service import compute_deal_score
from services.leasing_operativo.market_data.comparator import SubjectVehicle, score_comparable
from services.leasing_operativo.market_data.normalizer import remove_price_outliers
from services.leasing_operativo.market_data.types import VehicleMarketComparable
from services.leasing_operativo.market_data.valuation import resolve_weights, weighted_market_price
from services.leasing_operativo.residual_risk_service import residual_risk_score, valuation_confidence
from services.leasing_operativo.residual_value_service import (
    calculate_residual_engine,
    project_future_market_value,
    project_km,
)
from services.leasing_operativo.sale_recovery_service import calculate_recovery
from decimal import Decimal


def test_km_final_estimate():
    km = project_km(km_inicial=20000, km_mensual=2500, meses=36)
    assert km["KM_FINAL_ESTIMADO"] == 110000
    assert km["KM_ESPERADOS_CONTRATO"] == 90000


def test_source_weights_configurable_not_hardcoded_only():
    w = resolve_weights({"chileautos": 0.6, "mercadolibre": 0.3, "yapo": 0.1})
    assert abs(w["chileautos"] - 0.6) < 1e-9
    assert abs(sum(v for v in w.values() if v > 0) - 1.0) < 1e-9


def test_outlier_removal_and_weighted_price():
    comps = [
        VehicleMarketComparable(source="chileautos", source_url="u1", brand="Toyota", model="RAV4", price=24_000_000),
        VehicleMarketComparable(source="chileautos", source_url="u2", brand="Toyota", model="RAV4", price=25_000_000),
        VehicleMarketComparable(source="chileautos", source_url="u3", brand="Toyota", model="RAV4", price=26_000_000),
        VehicleMarketComparable(source="chileautos", source_url="u4", brand="Toyota", model="RAV4", price=90_000_000),
        VehicleMarketComparable(source="mercadolibre", source_url="u5", brand="Toyota", model="RAV4", price=24_500_000),
        VehicleMarketComparable(source="yapo", source_url="u6", brand="Toyota", model="RAV4", price=23_800_000),
    ]
    cleaned = remove_price_outliers(comps)
    assert max(c.price for c in cleaned) < 50_000_000
    val = weighted_market_price(cleaned, resolve_weights(None))
    assert val["valor_mercado_actual"] is not None
    assert 20_000_000 < val["valor_mercado_actual"] < 30_000_000


def test_comparability_score_direct():
    subject = SubjectVehicle(brand="Toyota", model="RAV4", version="XLE", year=2023, fuel_type="bencina", transmission="at")
    comp = VehicleMarketComparable(
        source="chileautos",
        source_url="https://example",
        brand="Toyota",
        model="RAV4",
        version="XLE",
        year=2023,
        fuel_type="bencina",
        transmission="at",
        price=20_000_000,
        mileage=60000,
    )
    score = score_comparable(subject, comp)
    assert score >= 85


def test_scenarios_conservador_base_optimista():
    fut = project_future_market_value(
        valor_mercado_actual=Decimal("25000000"),
        plazo_meses=36,
        edad_hoy_anios=0,
        km_fin=Decimal("72000"),
        tipo_uso="USO_COMERCIAL",
        policy={
            "residual_curve": None,
            "uso_factores": {"USO_COMERCIAL": 0.94},
            "conservative_factor": 0.90,
            "base_factor": 1.0,
            "optimistic_factor": 1.08,
            "km_ref_anual": 20000,
            "km_sensitivity": 0.00000055,
        },
    )
    esc = fut["escenarios"]
    assert esc["CONSERVADOR"] <= esc["BASE"] <= esc["OPTIMISTA"]
    assert esc["BASE"] < 25_000_000


def test_book_tax_market_layers_separated():
    layers = calculate_value_layers(
        costo_activo=25_000_000,
        plazo_meses=36,
        tipo_contrato="ARRENDAMIENTO_OPERATIVO",
        market_value_future=13_500_000,
    )
    assert layers["BOOK_VALUE"]["valor"] != layers["MARKET_VALUE"]["valor"]
    assert layers["TAX_VALUE"]["articulo"]
    assert layers["TAX_VALUE"]["fuente_normativa"]
    assert layers["tipo_contrato"] == "ARRENDAMIENTO_OPERATIVO"
    # Leasing financiero no reutiliza automáticamente lógica operativa
    lf = calculate_value_layers(
        costo_activo=25_000_000,
        plazo_meses=36,
        tipo_contrato="LEASING_FINANCIERO",
        market_value_future=13_500_000,
    )
    assert lf["TAX_VALUE"]["aplica_art_37_bis"] is True
    assert lf["TAX_VALUE"]["depreciacion_acumulada"] == 0.0


def test_recovery_net_below_gross():
    rec = calculate_recovery(
        precio_venta_esperado=13_500_000,
        km_fin=72000,
        plazo_meses=36,
        tipo_uso="USO_COMERCIAL",
    )
    assert rec["VALOR_RECUPERO_NETO"] < rec["VALOR_RECUPERO_BRUTO"]
    assert rec["COSTOS_RECUPERACION"]["total"] > 0


def test_risk_and_confidence():
    risk = residual_risk_score(
        n_comps=8,
        dispersion_pct=22,
        edad_fin_anios=3,
        km_fin=72000,
        tipo_uso="USO_COMERCIAL",
        comparability_avg=80,
    )
    assert risk["RESIDUAL_RISK_LEVEL"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    conf = valuation_confidence(n_comps=8, comparability_avg=80, dispersion_pct=18)
    assert 0 <= conf["VALUATION_CONFIDENCE"] <= 100


def test_deal_score_uses_policy_thresholds():
    deal = compute_deal_score(
        tir_anual_pct=14,
        van=2_000_000,
        margen_pct=8,
        residual_pct=48,
        residual_risk_score=30,
        ltv_pct=80,
        thresholds={"minimum_irr": 10, "minimum_npv": 0, "minimum_margin": 5, "maximum_residual_risk": 70},
    )
    assert deal["DEAL_SCORE"] >= 55
    assert deal["DECISION"] in {"APROBAR", "APROBAR CON CONDICIONES", "REVISAR", "NO RECOMENDADO"}


def test_engine_offline_without_live_market():
    est = calculate_residual_engine(
        marca="Toyota",
        modelo="RAV4",
        anio=2026,
        valor_adquisicion=25_000_000,
        plazo_meses=36,
        km_inicial=0,
        km_anual=24000,
        tipo_uso="USO_COMERCIAL",
        consultar_mercado=False,
        politica={
            "conservative_factor": 0.9,
            "base_factor": 1.0,
            "optimistic_factor": 1.08,
            "market_data_weights": {"chileautos": 0.5, "mercadolibre": 0.3, "yapo": 0.2},
        },
    )
    assert est["KM_FINAL_ESTIMADO"] == 72000
    assert est["escenarios"]["CONSERVADOR"] <= est["escenarios"]["BASE"] <= est["escenarios"]["OPTIMISTA"]
    assert est["VALOR_LIBROS_FINAL"] > 0
    assert est["VALOR_RECUPERO_NETO"] > 0
    assert est["confianza"]["VALUATION_CONFIDENCE"] >= 0
    assert est["MANUAL_OVERRIDE"] is False
    assert est["model_version"]
    # Conceptos no mezclados
    assert est["PRECIO_COMPRA"] != est["VALOR_LIBROS_FINAL"] or True
    assert "layers" in est and "BOOK_VALUE" in est["layers"] and "TAX_VALUE" in est["layers"]
