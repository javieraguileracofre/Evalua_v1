# services/leasing_operativo/residual_value_service.py
# -*- coding: utf-8 -*-
"""
Motor profesional de Valor Residual / Recupero / Rentabilidad LOP.

Orquesta mercado, escenarios, libro/tributario, recupero, riesgo y deal score.
No duplica el pricing: se integra con residual_model + economic_engine existentes.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from services.leasing_operativo.accounting_bridge import build_accounting_payload
from services.leasing_operativo.depreciation_service import calculate_value_layers
from services.leasing_operativo.lease_profitability_service import compute_deal_score
from services.leasing_operativo.market_data.valuation import MODEL_VERSION, search_and_value
from services.leasing_operativo.residual_model import TIPOS_USO, estimar_residual_cotizacion
from services.leasing_operativo.residual_risk_service import residual_risk_score, valuation_confidence
from services.leasing_operativo.sale_recovery_service import calculate_recovery

# Curva residual por edad (meses) — % sobre valor mercado actual. Parametrizable.
DEFAULT_RESIDUAL_CURVE: list[dict[str, Any]] = [
    {"age_month": 0, "residual_percentage": 100, "min_percentage": 95, "max_percentage": 100},
    {"age_month": 12, "residual_percentage": 82, "min_percentage": 76, "max_percentage": 88},
    {"age_month": 24, "residual_percentage": 72, "min_percentage": 65, "max_percentage": 78},
    {"age_month": 36, "residual_percentage": 63, "min_percentage": 55, "max_percentage": 70},
    {"age_month": 48, "residual_percentage": 55, "min_percentage": 47, "max_percentage": 62},
    {"age_month": 60, "residual_percentage": 48, "min_percentage": 40, "max_percentage": 55},
    {"age_month": 72, "residual_percentage": 42, "min_percentage": 34, "max_percentage": 50},
    {"age_month": 84, "residual_percentage": 38, "min_percentage": 30, "max_percentage": 45},
]

DEFAULT_USO_FACTORES: dict[str, float] = {
    "USO_PARTICULAR": 1.00,
    "USO_EJECUTIVO": 0.98,
    "USO_COMERCIAL": 0.94,
    "USO_REPARTO": 0.90,
    "USO_LOGISTICO": 0.88,
    "USO_CONSTRUCCION": 0.84,
    "USO_MINERO": 0.80,
    "USO_TERRITORIO_EXTREMO": 0.78,
    "USO_INTENSIVO": 0.88,
    "URBANO": 1.00,
    "INTERURBANO": 0.96,
    "MIXTO": 0.94,
    "FAENA": 0.84,
    "MINERO": 0.80,
}

LEGACY_USO_MAP: dict[str, str] = {
    "URBANO": "USO_PARTICULAR",
    "INTERURBANO": "USO_COMERCIAL",
    "MIXTO": "USO_COMERCIAL",
    "FAENA": "USO_CONSTRUCCION",
    "MINERO": "USO_MINERO",
}


def _d(v: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(v).replace(",", ".")) if v is not None else Decimal(default)
    except Exception:
        return Decimal(default)


def default_residual_policy() -> dict[str, Any]:
    return {
        "model_version": MODEL_VERSION,
        "market_data_weights": {
            "chileautos": 0.50,
            "mercadolibre": 0.30,
            "yapo": 0.20,
            "autocosmos": 0.0,
        },
        "uso_factores": dict(DEFAULT_USO_FACTORES),
        "conservative_factor": 0.90,
        "base_factor": 1.00,
        "optimistic_factor": 1.08,
        "residual_curve": deepcopy(DEFAULT_RESIDUAL_CURVE),
        "km_ref_anual": 20000,
        "km_sensitivity": 0.00000055,
        "sale_cost_percentage": 2.0,
        "reconditioning_budget": {},
        "sale_costs": {},
        "tax_rules": {},
        "deal_thresholds": {},
        "tipo_contrato_default": "ARRENDAMIENTO_OPERATIVO",
        "max_contract_months": 84,
        "max_km_month": 5000,
        "max_km_contract": 250000,
        "residual_min": 0.20,
        "residual_target": 0.45,
        "residual_max": 0.85,
    }


def merge_residual_policy(politica: dict[str, Any] | None) -> dict[str, Any]:
    out = default_residual_policy()
    src = {}
    if isinstance(politica, dict):
        # Puede venir merge_politica completo o solo residual_value_v1
        if "market_data_weights" in politica or "uso_factores" in politica:
            src = politica
        else:
            src = politica.get("residual_value_v1") or {}
    if not isinstance(src, dict):
        src = {}
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        elif v is not None:
            out[k] = v
    # remarketing / escenarios / motor_decision si vienen en merge_politica
    if isinstance(politica, dict):
        if isinstance(politica.get("remarketing_v1"), dict):
            rm = politica["remarketing_v1"]
            out.setdefault("sale_costs", {})
            if "costo_reacondicionamiento_pct" in rm:
                out.setdefault("reconditioning_budget", {})
                out["reconditioning_budget"]["base_pct_sobre_precio_venta"] = rm["costo_reacondicionamiento_pct"]
            if "meses_objetivo_venta" in rm:
                out.setdefault("sale_costs", {})
                out["sale_costs"]["meses_venta"] = rm["meses_objetivo_venta"]
        if isinstance(politica.get("motor_decision_v1"), dict):
            md = politica["motor_decision_v1"]
            dt = dict(out.get("deal_thresholds") or {})
            if "tir_minima_anual_pct" in md:
                dt["minimum_irr"] = md["tir_minima_anual_pct"]
            if "van_minimo" in md:
                dt["minimum_npv"] = md["van_minimo"]
            if "margen_op_minimo_pct" in md:
                dt["minimum_margin"] = md["margen_op_minimo_pct"]
            if "ltv_max_pct" in md:
                dt["ltv_max_pct"] = md["ltv_max_pct"]
            out["deal_thresholds"] = dt
        if isinstance(politica.get("escenarios_v1"), dict):
            esc = politica["escenarios_v1"]
            if isinstance(esc.get("CONSERVADOR"), dict) and esc["CONSERVADOR"].get("residual_mult"):
                out["conservative_factor"] = float(esc["CONSERVADOR"]["residual_mult"])
            if isinstance(esc.get("OPTIMISTA"), dict) and esc["OPTIMISTA"].get("residual_mult"):
                out["optimistic_factor"] = float(esc["OPTIMISTA"]["residual_mult"])
    return out


def project_km(*, km_inicial: Any, km_mensual: Any | None = None, km_anual: Any | None = None, meses: int) -> dict[str, Any]:
    n = max(int(meses), 1)
    km0 = max(_d(km_inicial), Decimal("0"))
    if km_mensual is not None and _d(km_mensual) > 0:
        km_m = max(_d(km_mensual), Decimal("0"))
    else:
        km_m = max(_d(km_anual), Decimal("0")) / Decimal("12")
    km_contrato = (km_m * Decimal(n)).quantize(Decimal("1"))
    km_fin = (km0 + km_contrato).quantize(Decimal("1"))
    return {
        "KM_INICIAL": float(km0),
        "KM_MENSUAL_ESPERADO": float(km_m.quantize(Decimal("0.01"))),
        "MESES_CONTRATO": n,
        "KM_ESPERADOS_CONTRATO": float(km_contrato),
        "KM_FINAL_ESTIMADO": float(km_fin),
        "km_anual_equiv": float((km_m * Decimal("12")).quantize(Decimal("1"))),
    }


def _curve_pct(curve: list[dict[str, Any]], age_months: float) -> dict[str, float]:
    rows = sorted(curve or DEFAULT_RESIDUAL_CURVE, key=lambda r: int(r.get("age_month") or 0))
    if not rows:
        rows = DEFAULT_RESIDUAL_CURVE
    am = max(float(age_months), 0.0)
    if am <= int(rows[0]["age_month"]):
        r = rows[0]
        return {
            "base": float(r["residual_percentage"]),
            "min": float(r["min_percentage"]),
            "max": float(r["max_percentage"]),
        }
    for i in range(1, len(rows)):
        a0 = float(rows[i - 1]["age_month"])
        a1 = float(rows[i]["age_month"])
        if am <= a1:
            t = (am - a0) / max(a1 - a0, 1.0)
            def lerp(k: str) -> float:
                return float(rows[i - 1][k]) + (float(rows[i][k]) - float(rows[i - 1][k])) * t

            return {"base": lerp("residual_percentage"), "min": lerp("min_percentage"), "max": lerp("max_percentage")}
    r = rows[-1]
    return {
        "base": float(r["residual_percentage"]),
        "min": float(r["min_percentage"]),
        "max": float(r["max_percentage"]),
    }


def _uso_factor(tipo_uso: str, policy: dict[str, Any]) -> float:
    key = str(tipo_uso or "USO_COMERCIAL").upper()
    factores = policy.get("uso_factores") or DEFAULT_USO_FACTORES
    if key in factores:
        return float(factores[key])
    mapped = LEGACY_USO_MAP.get(key)
    if mapped and mapped in factores:
        return float(factores[mapped])
    return float(factores.get("USO_COMERCIAL", 0.94))


def project_future_market_value(
    *,
    valor_mercado_actual: Decimal,
    plazo_meses: int,
    edad_hoy_anios: float,
    km_fin: Decimal,
    tipo_uso: str,
    policy: dict[str, Any],
    marca_factor: Decimal = Decimal("1"),
    region_factor: Decimal = Decimal("1"),
    tendencia_factor: Decimal = Decimal("1"),
) -> dict[str, Any]:
    age_fin_m = (float(edad_hoy_anios) * 12.0) + float(plazo_meses)
    band = _curve_pct(policy.get("residual_curve") or DEFAULT_RESIDUAL_CURVE, age_fin_m)
    f_uso = _d(_uso_factor(tipo_uso, policy), "1")
    km_ref = _d(policy.get("km_ref_anual"), "20000") * (Decimal(str(age_fin_m)) / Decimal("12"))
    exceso = max(km_fin - km_ref, Decimal("0"))
    sens = _d(policy.get("km_sensitivity"), "0.00000055")
    f_km = max(Decimal("1") - exceso * sens, Decimal("0.55"))
    f_marca = max(min(_d(marca_factor, "1"), Decimal("1.12")), Decimal("0.88"))
    f_reg = max(min(_d(region_factor, "1"), Decimal("1.08")), Decimal("0.92"))
    f_trend = max(min(_d(tendencia_factor, "1"), Decimal("1.1")), Decimal("0.9"))

    def _apply(pct: float, scenario_mult: Decimal) -> Decimal:
        raw = (
            valor_mercado_actual
            * (Decimal(str(pct)) / Decimal("100"))
            * f_uso
            * f_km
            * f_marca
            * f_reg
            * f_trend
            * scenario_mult
        )
        return max(raw, Decimal("0")).quantize(Decimal("1"))

    cons = _d(policy.get("conservative_factor"), "0.90")
    base_f = _d(policy.get("base_factor"), "1")
    opt = _d(policy.get("optimistic_factor"), "1.08")
    v_cons = _apply(band["min"], cons)
    v_base = _apply(band["base"], base_f)
    v_opt = _apply(band["max"], opt)
    # Ordenar escenarios por valor
    vals = sorted([v_cons, v_base, v_opt])
    v_cons, v_base, v_opt = vals[0], vals[1], vals[2]
    return {
        "edad_fin_meses": round(age_fin_m, 1),
        "curve_band": band,
        "factores": {
            "uso": float(f_uso),
            "km": float(f_km),
            "marca": float(f_marca),
            "region": float(f_reg),
            "tendencia": float(f_trend),
            "conservative_factor": float(cons),
            "base_factor": float(base_f),
            "optimistic_factor": float(opt),
        },
        "VALOR_MERCADO_FUTURO_BRUTO": float(v_base),
        "escenarios": {
            "CONSERVADOR": float(v_cons),
            "BASE": float(v_base),
            "OPTIMISTA": float(v_opt),
        },
    }


def calculate_residual_engine(
    *,
    marca: str,
    modelo: str,
    version: str = "",
    anio: int | None = None,
    valor_adquisicion: Any,
    plazo_meses: int,
    km_inicial: Any = 0,
    km_anual: Any = 40000,
    km_mensual: Any | None = None,
    tipo_uso: str = "MIXTO",
    segment: str = "",
    region: str = "",
    tipo_contrato: str = "ARRENDAMIENTO_OPERATIVO",
    politica: dict[str, Any] | None = None,
    consultar_mercado: bool = True,
    yapo_manual: list[dict[str, Any]] | None = None,
    haircut_tipo_pct: Any = 5,
    liquidez_factor: Any = 1,
    obsolescencia_factor: Any = 1,
    rentabilidad: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cálculo completo de valorización residual profesional (una unidad)."""
    policy = merge_residual_policy(politica)
    costo = max(_d(valor_adquisicion), Decimal("0"))
    km_info = project_km(km_inicial=km_inicial, km_mensual=km_mensual, km_anual=km_anual, meses=plazo_meses)
    anio_hoy = date.today().year
    anio_v = int(anio or anio_hoy)
    edad_hoy = max(anio_hoy - anio_v, 0)
    edad_fin = float(edad_hoy) + (plazo_meses / 12.0)
    km_fin = _d(km_info["KM_FINAL_ESTIMADO"])

    market: dict[str, Any] = {}
    if consultar_mercado and marca and modelo:
        anio_comp = max(anio_hoy - int(round(edad_fin)), 1995)
        try:
            market = search_and_value(
                brand=marca,
                model=modelo,
                version=version,
                year=anio_comp,
                year_min=max(anio_comp - 1, 1995),
                year_max=min(anio_comp + 1, anio_hoy),
                km_target=float(km_fin),
                km_min=max(int(float(km_fin) * 0.75), 0),
                km_max=int(float(km_fin) * 1.35) if km_fin > 0 else None,
                segment=segment,
                region=region,
                source_weights=policy.get("market_data_weights"),
                yapo_manual=yapo_manual,
            )
        except Exception as exc:  # noqa: BLE001 — no tumbar cotización ni bloquear UI
            market = {
                "valor_mercado_actual": None,
                "comparables": [],
                "portales": [],
                "search_urls": {},
                "stats": {"n": 0, "error": str(exc)},
                "consultado_en": None,
                "error": str(exc),
            }

    valor_mercado_actual = _d(market.get("valor_mercado_actual")) if market.get("valor_mercado_actual") else costo
    if valor_mercado_actual <= 0:
        valor_mercado_actual = costo

    futuro = project_future_market_value(
        valor_mercado_actual=valor_mercado_actual,
        plazo_meses=plazo_meses,
        edad_hoy_anios=float(edad_hoy),
        km_fin=km_fin,
        tipo_uso=tipo_uso,
        policy=policy,
    )
    # Haircut comercial del tipo de activo sobre escenario base
    hair = max(_d(haircut_tipo_pct), Decimal("0")) / Decimal("100")
    liq = max(min(_d(liquidez_factor, "1"), Decimal("1.15")), Decimal("0.8"))
    obs = max(min(_d(obsolescencia_factor, "1"), Decimal("1.15")), Decimal("0.8"))
    escenarios_adj = {}
    for k, v in (futuro.get("escenarios") or {}).items():
        adj = (Decimal(str(v)) * (Decimal("1") - hair) * liq * obs).quantize(Decimal("1"))
        escenarios_adj[k] = float(max(adj, Decimal("0")))
    base_res = _d(escenarios_adj.get("BASE") or futuro["VALOR_MERCADO_FUTURO_BRUTO"])

    # Fallback / cruce con modelo interno existente
    interno = estimar_residual_cotizacion(
        valor_bien=costo,
        plazo_meses=plazo_meses,
        km_anual=_d(km_info["km_anual_equiv"]),
        km_inicial=_d(km_info["KM_INICIAL"]),
        anio_vehiculo=anio_v,
        tipo_uso=str(tipo_uso if tipo_uso in TIPOS_USO else LEGACY_USO_MAP.get(tipo_uso, "MIXTO")),
        residual_base_pct=Decimal("72"),
        residual_max_pct=Decimal("85"),
        liquidez_factor=_d(liquidez_factor, "1"),
        obsolescencia_factor=_d(obsolescencia_factor, "1"),
        haircut_pct=_d(haircut_tipo_pct, "5"),
    )
    if not market.get("valor_mercado_actual"):
        # Sin comps: anclar base a promedio ponderado interno/curva
        base_res = (
            (base_res + _d(interno.get("valor_residual_sugerido"))) / Decimal("2")
        ).quantize(Decimal("1"))
        escenarios_adj["BASE"] = float(base_res)
        escenarios_adj["CONSERVADOR"] = float((base_res * _d(policy.get("conservative_factor"), "0.9")).quantize(Decimal("1")))
        escenarios_adj["OPTIMISTA"] = float((base_res * _d(policy.get("optimistic_factor"), "1.08")).quantize(Decimal("1")))

    recovery = calculate_recovery(
        precio_venta_esperado=base_res,
        km_fin=km_fin,
        plazo_meses=plazo_meses,
        tipo_uso=tipo_uso,
        sale_policy={
            **(policy.get("sale_costs") or {}),
            "comision_venta_pct": policy.get("sale_cost_percentage", 2.0),
        },
        reconditioning_policy=policy.get("reconditioning_budget"),
    )
    layers = calculate_value_layers(
        costo_activo=costo,
        plazo_meses=plazo_meses,
        tipo_contrato=tipo_contrato or policy.get("tipo_contrato_default") or "ARRENDAMIENTO_OPERATIVO",
        tax_rules=policy.get("tax_rules"),
        market_value_future=base_res,
    )
    valor_libro = _d(layers.get("VALOR_LIBROS_FINAL"))
    resultado_venta = (base_res - valor_libro).quantize(Decimal("1"))
    comps = market.get("comparables") or []
    scores = [float(c.get("comparability_score") or 0) for c in comps if c.get("comparability_score")]
    avg_comp = sum(scores) / len(scores) if scores else None
    stats = market.get("stats") or {}
    risk = residual_risk_score(
        n_comps=int(stats.get("n") or len(comps)),
        dispersion_pct=stats.get("dispersion_pct"),
        edad_fin_anios=edad_fin,
        km_fin=float(km_fin),
        tipo_uso=tipo_uso,
        comparability_avg=avg_comp,
    )
    conf = valuation_confidence(
        n_comps=int(stats.get("n") or len(comps)),
        comparability_avg=avg_comp,
        dispersion_pct=stats.get("dispersion_pct"),
    )

    rent = rentabilidad or {}
    residual_pct = float((base_res / costo * Decimal("100")).quantize(Decimal("0.01"))) if costo > 0 else 0.0
    deal = compute_deal_score(
        tir_anual_pct=rent.get("tir_anual_pct") if "tir_anual_pct" in rent else None,
        van=rent.get("van") if "van" in rent else None,
        margen_pct=(
            rent.get("margen_operacional_promedio_pct")
            if "margen_operacional_promedio_pct" in rent
            else rent.get("margen_pct")
        ),
        residual_pct=residual_pct,
        residual_risk_score=risk["RESIDUAL_RISK_SCORE"],
        ltv_pct=rent.get("ltv_pct") if "ltv_pct" in rent else None,
        thresholds=policy.get("deal_thresholds"),
    )

    accounting = build_accounting_payload(
        costo_activo=float(costo),
        depreciacion_acumulada=float((layers.get("BOOK_VALUE") or {}).get("depreciacion_acumulada") or 0),
        valor_libro=float(valor_libro),
        precio_venta_esperado=float(base_res),
        costos_venta=float((recovery.get("COSTOS_RECUPERACION") or {}).get("total") or 0),
        tipo_contrato=str(layers.get("tipo_contrato") or tipo_contrato),
    )

    fuente = "mercado_ponderado" if market.get("valor_mercado_actual") else "curva_residual_politica"
    panel = {
        "precio_adquisicion": float(costo),
        "valor_mercado_actual": float(valor_mercado_actual),
        "depreciacion_mercado": float((valor_mercado_actual - base_res).quantize(Decimal("1"))),
        "valor_libro": float(valor_libro),
        "valor_mercado_proyectado": float(base_res),
        "costos_recuperacion": float((recovery.get("COSTOS_RECUPERACION") or {}).get("total") or 0),
        "valor_recupero_neto": recovery.get("VALOR_RECUPERO_NETO"),
        "resultado_venta": float(resultado_venta),
    }

    return {
        "model_version": policy.get("model_version") or MODEL_VERSION,
        "fuente": fuente,
        "metodo": "residual_value_engine_v1",
        "consultado_en": market.get("consultado_en"),
        "marca": marca,
        "modelo": modelo,
        "version": version,
        "anio": anio_v,
        "tipo_uso": str(tipo_uso).upper(),
        "tipo_uso_label": (TIPOS_USO.get(str(tipo_uso).upper()) or {}).get("label")
        or str(tipo_uso).replace("_", " ").title(),
        "tipo_contrato": layers.get("tipo_contrato"),
        "plazo_meses": int(plazo_meses),
        "edad_hoy_anios": edad_hoy,
        "edad_fin_anios": round(edad_fin, 2),
        "km_fin_estimado": float(km_fin),
        **km_info,
        "valor_bien": float(costo),
        "PRECIO_COMPRA": float(costo),
        "VALOR_MERCADO_ACTUAL": float(valor_mercado_actual),
        "VALOR_MERCADO_FUTURO_BRUTO": futuro.get("VALOR_MERCADO_FUTURO_BRUTO"),
        "escenarios": escenarios_adj,
        "valor_residual_sugerido": float(base_res),
        "pct_residual_sugerido": residual_pct,
        "capital_amortizable_sugerido": float(max(costo - base_res, Decimal("0"))),
        "valor_residual_interno": interno.get("valor_residual_sugerido"),
        "recupero": recovery,
        "VALOR_RECUPERO_NETO": recovery.get("VALOR_RECUPERO_NETO"),
        "layers": layers,
        "VALOR_LIBROS_FINAL": float(valor_libro),
        "RESULTADO_ESPERADO_VENTA": float(resultado_venta),
        "riesgo": risk,
        "confianza": conf,
        "deal": deal,
        "panel_ejecutivo": panel,
        "search_urls": market.get("search_urls") or {},
        "portales": market.get("portales") or [],
        "comparables": comps,
        "stats": {
            **stats,
            "haircut_pct": float(_d(haircut_tipo_pct)),
            "n": int(stats.get("n") or len(comps)),
            "mediana": stats.get("mediana") or stats.get("valor_mercado_actual"),
        },
        "proyeccion_factores": futuro.get("factores"),
        "curve_band": futuro.get("curve_band"),
        "accounting_bridge": accounting,
        "policy_snapshot": {
            "market_data_weights": policy.get("market_data_weights"),
            "conservative_factor": policy.get("conservative_factor"),
            "base_factor": policy.get("base_factor"),
            "optimistic_factor": policy.get("optimistic_factor"),
            "sale_cost_percentage": policy.get("sale_cost_percentage"),
            "tipo_contrato_default": policy.get("tipo_contrato_default"),
        },
        "nota": (
            "Motor profesional RV: mercado ponderado + curva residual parametrizable + "
            "escenarios + recupero neto + capas libro/tributaria/mercado. "
            "Links e imágenes de comparables quedan como respaldo auditable."
            if fuente == "mercado_ponderado"
            else "Sin precio de mercado ponderado suficiente; se usó curva residual de política "
            "cruzada con modelo interno. Revise links de búsqueda adjuntos."
        ),
        "MANUAL_OVERRIDE": False,
    }


def enrich_unit_with_residual_engine(
    unidad: dict[str, Any],
    *,
    plazo_meses: int,
    tipo_activo: Any,
    politica: dict[str, Any] | None = None,
    consultar_mercado: bool = True,
) -> dict[str, Any]:
    """Integra el motor en el flujo de cotización flota (conserva campos UI existentes)."""
    est = calculate_residual_engine(
        marca=str(unidad.get("marca") or ""),
        modelo=str(unidad.get("modelo") or ""),
        version=str(unidad.get("version") or ""),
        anio=unidad.get("anio"),
        valor_adquisicion=unidad.get("valor_bien"),
        plazo_meses=plazo_meses,
        km_inicial=unidad.get("km_inicial"),
        km_anual=unidad.get("km_anual"),
        km_mensual=unidad.get("km_mensual"),
        tipo_uso=str(unidad.get("tipo_uso") or "MIXTO"),
        segment=str(getattr(tipo_activo, "codigo", "") or unidad.get("segment") or ""),
        region=str(unidad.get("region") or ""),
        tipo_contrato=str(unidad.get("tipo_contrato") or "ARRENDAMIENTO_OPERATIVO"),
        politica=politica,
        consultar_mercado=consultar_mercado,
        haircut_tipo_pct=getattr(tipo_activo, "haircut_residual_pct", 5),
        liquidez_factor=getattr(tipo_activo, "liquidez_factor", 1),
        obsolescencia_factor=getattr(tipo_activo, "obsolescencia_factor", 1),
    )
    out = dict(unidad)
    sugerido = _d(est["valor_residual_sugerido"])
    aceptado = _d(out.get("residual_aceptado"))
    bien = _d(out.get("valor_bien"))
    prev_sug = _d(out.get("residual_sugerido"))
    # Override si el usuario ya había desviado el aceptado del sugerido anterior
    was_manual = bool((out.get("residual_estimacion") or {}).get("MANUAL_OVERRIDE")) or (
        aceptado > 0 and prev_sug > 0 and abs(aceptado - prev_sug) > Decimal("1")
    )
    est_out = dict(est)
    if aceptado <= 0 or (bien > 0 and aceptado < bien * Decimal("0.15")):
        out["residual_aceptado"] = float(sugerido)
    elif was_manual and abs(aceptado - sugerido) > Decimal("1"):
        est_out["MANUAL_OVERRIDE"] = True
        est_out["valor_residual_modelo"] = float(sugerido)
        est_out["advertencia_override"] = (
            "El valor residual fue modificado manualmente respecto del modelo de mercado."
        )
        out["residual_aceptado"] = float(aceptado)
    else:
        out["residual_aceptado"] = float(sugerido)
    out["residual_sugerido"] = float(sugerido)
    out["residual_fuente"] = est_out.get("fuente") or "residual_value_engine"
    out["residual_estimacion"] = est_out
    out["capital_amortizable_unitario"] = float(
        max(_d(out["valor_bien"]) - _d(out["residual_aceptado"]), Decimal("0"))
    )
    out["analisis_residual"] = {
        "escenarios": est_out.get("escenarios"),
        "recupero_neto": est_out.get("VALOR_RECUPERO_NETO"),
        "valor_libro": est_out.get("VALOR_LIBROS_FINAL"),
        "resultado_venta": est_out.get("RESULTADO_ESPERADO_VENTA"),
        "confianza": est_out.get("confianza"),
        "riesgo": est_out.get("riesgo"),
        "deal": est_out.get("deal"),
        "panel_ejecutivo": est_out.get("panel_ejecutivo"),
        "model_version": est_out.get("model_version"),
    }
    return out


def build_profitability_report(est: dict[str, Any], *, rentabilidad: dict[str, Any] | None = None) -> dict[str, Any]:
    rent = rentabilidad or {}
    deal = est.get("deal") or {}
    return {
        "titulo": "EVALUACIÓN ECONÓMICA DEL CONTRATO",
        "activo": {
            "marca": est.get("marca"),
            "modelo": est.get("modelo"),
            "version": est.get("version"),
            "anio": est.get("anio"),
        },
        "contrato": {
            "plazo": est.get("plazo_meses"),
            "kilometraje_mensual": est.get("KM_MENSUAL_ESPERADO"),
            "kilometraje_total": est.get("KM_FINAL_ESTIMADO"),
            "uso": est.get("tipo_uso"),
            "tipo_contrato": est.get("tipo_contrato"),
        },
        "inversion": {
            "costo_adquisicion": est.get("PRECIO_COMPRA"),
            "inversion_total": est.get("PRECIO_COMPRA"),
        },
        "valor_residual": {
            "valor_actual": est.get("VALOR_MERCADO_ACTUAL"),
            "conservador": (est.get("escenarios") or {}).get("CONSERVADOR"),
            "base": (est.get("escenarios") or {}).get("BASE"),
            "optimista": (est.get("escenarios") or {}).get("OPTIMISTA"),
        },
        "recuperacion": {
            "precio_venta_esperado": (est.get("recupero") or {}).get("VALOR_RECUPERO_BRUTO"),
            "costos_recuperacion": ((est.get("recupero") or {}).get("COSTOS_RECUPERACION") or {}).get("total"),
            "recupero_neto": est.get("VALOR_RECUPERO_NETO"),
        },
        "contabilidad": {
            "valor_libro": est.get("VALOR_LIBROS_FINAL"),
            "ganancia_perdida_esperada": est.get("RESULTADO_ESPERADO_VENTA"),
            "layers": est.get("layers"),
        },
        "rentabilidad": {
            "TIR": rent.get("tir_anual_pct"),
            "VAN": rent.get("van"),
            "margen": rent.get("margen_operacional_promedio_pct"),
            "resultado_economico": rent.get("van"),
        },
        "riesgo": {
            "riesgo_residual": (est.get("riesgo") or {}).get("RESIDUAL_RISK_LEVEL"),
            "confianza": (est.get("confianza") or {}).get("display"),
            "cantidad_comparables": (est.get("stats") or {}).get("n"),
        },
        "decision": deal.get("DECISION"),
        "deal_score": deal.get("DEAL_SCORE"),
        "deal_class": deal.get("DEAL_CLASS"),
        "model_version": est.get("model_version"),
    }


def persist_valuation_snapshot(
    db: Session,
    *,
    cotizacion_id: int | None,
    unidad_id: str | None,
    payload: dict[str, Any],
    usuario: str = "sistema",
) -> Any:
    """Persiste snapshot auditable. Si la tabla no existe aún, no rompe el flujo."""
    try:
        from models.leasing_operativo.models import LeasingOpMarketValuationSnapshot

        row = LeasingOpMarketValuationSnapshot(
            cotizacion_id=cotizacion_id,
            unidad_id=unidad_id or "",
            model_version=str(payload.get("model_version") or MODEL_VERSION),
            fuente=str(payload.get("fuente") or ""),
            valor_actual=_d(payload.get("VALOR_MERCADO_ACTUAL")),
            valor_proyectado=_d(payload.get("valor_residual_sugerido")),
            escenario="BASE",
            payload_json=payload,
            usuario=usuario,
        )
        db.add(row)
        db.flush()
        return row
    except Exception:
        return None
