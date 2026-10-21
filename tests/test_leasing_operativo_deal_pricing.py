# tests/test_leasing_operativo_deal_pricing.py
# -*- coding: utf-8 -*-
from services.leasing_operativo.cotizacion_flota import _enrich_unit_deal_with_pricing, normalizar_unidad
from services.leasing_operativo.lease_profitability_service import compute_deal_score


def test_normalizar_preserva_residual_estimacion():
    raw = {
        "tipo_activo_id": 1,
        "marca": "Toyota",
        "modelo": "RAV4",
        "valor_bien": 25000000,
        "residual_sugerido": 13000000,
        "residual_aceptado": 13000000,
        "residual_estimacion": {
            "comparables": [{"url": "https://example.com/a", "price": 12}],
            "escenarios": {"BASE": 13000000},
            "model_version": "RV-2026.10.01",
        },
        "analisis_residual": {"recupero_neto": 12000000},
    }
    u = normalizar_unidad(raw, 0)
    assert u["residual_sugerido"] == 13000000
    assert u["residual_estimacion"]["comparables"][0]["url"]
    assert u["analisis_residual"]["recupero_neto"] == 12000000


def test_enrich_deal_with_real_pricing():
    unidad = {
        "valor_bien": 25000000,
        "residual_aceptado": 13000000,
        "residual_sugerido": 13000000,
        "residual_estimacion": {
            "valor_residual_sugerido": 13000000,
            "riesgo": {"RESIDUAL_RISK_SCORE": 32},
            "deal": {"DECISION": "PENDIENTE_PRICING"},
        },
    }
    result = {
        "tir_anual_pct": 14.5,
        "van": 2500000,
        "margen_operacional_promedio_pct": 8.2,
        "ltv_pct": 78,
        "renta_sugerida": 450000,
        "decision": {"decision_codigo": "APROBAR"},
    }
    out = _enrich_unit_deal_with_pricing(
        unidad,
        result_unit=result,
        politica={
            "residual_value_v1": {
                "deal_thresholds": {
                    "minimum_irr": 10,
                    "minimum_npv": 0,
                    "minimum_margin": 5,
                    "maximum_residual_risk": 70,
                    "ltv_max_pct": 92,
                }
            }
        },
    )
    est = out["residual_estimacion"]
    assert est["deal_con_pricing"] is True
    assert est["rentabilidad"]["tir_anual_pct"] == 14.5
    assert est["deal"]["DECISION"] in {
        "APROBAR",
        "APROBAR CON CONDICIONES",
        "REVISAR",
        "NO RECOMENDADO",
    }
    assert est["deal"]["DEAL_SCORE"] >= 55


def test_deal_score_with_pricing_not_pending():
    deal = compute_deal_score(
        tir_anual_pct=12,
        van=100000,
        margen_pct=6,
        residual_pct=50,
        residual_risk_score=28,
        ltv_pct=80,
        thresholds={"minimum_irr": 10, "minimum_npv": 0, "minimum_margin": 5},
    )
    assert deal["DECISION"] != "PENDIENTE_PRICING"
