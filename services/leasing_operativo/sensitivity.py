# services/leasing_operativo/sensitivity.py
# -*- coding: utf-8 -*-
"""Análisis de sensibilidad comercial LOP (matriz renta / VAN / TIR)."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from services.leasing_operativo.economic_engine import run_economic_engine


def _pct_delta(base: Decimal, delta_pct: float) -> Decimal:
    return (base * (Decimal("1") + Decimal(str(delta_pct)) / Decimal("100"))).quantize(Decimal("1"))


def run_sensitivity_matrix(
    *,
    inputs: dict[str, Any],
    tipo_activo: dict[str, Any],
    politica: dict[str, dict[str, Any]],
    plantillas_costo: list[dict[str, Any]],
    max_combinaciones: int = 25,
) -> dict[str, Any]:
    """Variaciones ± en CAPEX, spread y plazo sobre escenario BASE."""
    base = run_economic_engine(
        inputs=inputs,
        tipo_activo=tipo_activo,
        politica=politica,
        plantillas_costo=plantillas_costo,
    )
    filas: list[dict[str, Any]] = [
        {
            "variante": "BASE",
            "capex_delta_pct": 0,
            "spread_delta_pp": 0,
            "plazo_delta_meses": 0,
            "renta_sugerida": base.get("renta_sugerida"),
            "van": base.get("van"),
            "tir_anual_pct": base.get("tir_anual_pct"),
            "decision": (base.get("decision") or {}).get("decision_codigo"),
        }
    ]

    capex_in = inputs.get("capex") or {}
    precio = capex_in.get("precio_compra") or inputs.get("precio_compra") or 0
    try:
        precio_d = Decimal(str(precio))
    except Exception:
        precio_d = Decimal("0")

    spread_base = Decimal(str(inputs.get("spread_pct") or 8))
    plazo_base = int(inputs.get("plazo_meses") or 36)

    deltas_capex = [-10, 10]
    deltas_spread = [-2, 2]
    deltas_plazo = [-12, 12]

    for dc in deltas_capex:
        if len(filas) >= max_combinaciones:
            break
        if precio_d <= 0:
            continue
        inp = deepcopy(inputs)
        capex = dict(inp.get("capex") or {})
        capex["precio_compra"] = _pct_delta(precio_d, dc)
        inp["capex"] = capex
        r = run_economic_engine(inputs=inp, tipo_activo=tipo_activo, politica=politica, plantillas_costo=plantillas_costo)
        filas.append(
            {
                "variante": f"CAPEX_{dc:+d}%",
                "capex_delta_pct": dc,
                "spread_delta_pp": 0,
                "plazo_delta_meses": 0,
                "renta_sugerida": r.get("renta_sugerida"),
                "van": r.get("van"),
                "tir_anual_pct": r.get("tir_anual_pct"),
                "decision": (r.get("decision") or {}).get("decision_codigo"),
            }
        )

    for ds in deltas_spread:
        if len(filas) >= max_combinaciones:
            break
        inp = deepcopy(inputs)
        inp["metodo_pricing"] = "COSTO_SPREAD"
        inp["spread_pct"] = max(Decimal("0"), spread_base + Decimal(str(ds)))
        r = run_economic_engine(inputs=inp, tipo_activo=tipo_activo, politica=politica, plantillas_costo=plantillas_costo)
        filas.append(
            {
                "variante": f"SPREAD_{ds:+d}pp",
                "capex_delta_pct": 0,
                "spread_delta_pp": ds,
                "plazo_delta_meses": 0,
                "renta_sugerida": r.get("renta_sugerida"),
                "van": r.get("van"),
                "tir_anual_pct": r.get("tir_anual_pct"),
                "decision": (r.get("decision") or {}).get("decision_codigo"),
            }
        )

    for dp in deltas_plazo:
        if len(filas) >= max_combinaciones:
            break
        nuevo = max(12, plazo_base + dp)
        if nuevo == plazo_base:
            continue
        inp = deepcopy(inputs)
        inp["plazo_meses"] = nuevo
        r = run_economic_engine(inputs=inp, tipo_activo=tipo_activo, politica=politica, plantillas_costo=plantillas_costo)
        filas.append(
            {
                "variante": f"PLAZO_{dp:+d}m",
                "capex_delta_pct": 0,
                "spread_delta_pp": 0,
                "plazo_delta_meses": dp,
                "renta_sugerida": r.get("renta_sugerida"),
                "van": r.get("van"),
                "tir_anual_pct": r.get("tir_anual_pct"),
                "decision": (r.get("decision") or {}).get("decision_codigo"),
            }
        )

    return {"base": base, "filas": filas[:max_combinaciones]}


def run_escenarios_comparados(
    *,
    inputs: dict[str, Any],
    tipo_activo: dict[str, Any],
    politica: dict[str, dict[str, Any]],
    plantillas_costo: list[dict[str, Any]],
) -> dict[str, Any]:
    escenarios = ("CONSERVADOR", "BASE", "OPTIMISTA", "ESTRES")
    out: dict[str, Any] = {}
    for esc in escenarios:
        inp = deepcopy(inputs)
        inp["escenario"] = esc
        r = run_economic_engine(
            inputs=inp,
            tipo_activo=tipo_activo,
            politica=politica,
            plantillas_costo=plantillas_costo,
        )
        out[esc] = {
            "renta_sugerida": r.get("renta_sugerida"),
            "renta_minima_pico": r.get("renta_minima_pico"),
            "van": r.get("van"),
            "tir_anual_pct": r.get("tir_anual_pct"),
            "ltv_pct": r.get("ltv_pct"),
            "decision": r.get("decision"),
            "waterfall": r.get("waterfall"),
        }
    return out
