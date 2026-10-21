# services/leasing_operativo/reconditioning_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from typing import Any


def _d(v: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(v).replace(",", ".")) if v is not None else Decimal(default)
    except Exception:
        return Decimal(default)


DEFAULT_RECONDITIONING: dict[str, Any] = {
    "base_pct_sobre_precio_venta": 2.5,
    "por_km_exceso": {
        "umbral_km_anio": 20000,
        "costo_por_1000_km_exceso": 18000,
    },
    "por_uso": {
        "USO_PARTICULAR": 1.0,
        "USO_EJECUTIVO": 1.05,
        "USO_COMERCIAL": 1.15,
        "USO_REPARTO": 1.25,
        "USO_LOGISTICO": 1.3,
        "USO_CONSTRUCCION": 1.45,
        "USO_MINERO": 1.6,
        "USO_TERRITORIO_EXTREMO": 1.7,
        "USO_INTENSIVO": 1.55,
        # alias legacy simulador
        "URBANO": 1.0,
        "INTERURBANO": 1.08,
        "MIXTO": 1.15,
        "FAENA": 1.45,
        "MINERO": 1.6,
    },
    "desglose_pct": {
        "mantencion": 0.25,
        "neumaticos": 0.18,
        "frenos": 0.08,
        "latoneria": 0.12,
        "pintura": 0.08,
        "detailing": 0.07,
        "interior": 0.06,
        "documentacion": 0.05,
        "revision_tecnica": 0.04,
        "otros": 0.07,
    },
}


def merge_reconditioning_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_RECONDITIONING)
    if not isinstance(policy, dict):
        return out
    for k, v in policy.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def estimate_reconditioning(
    *,
    precio_venta_esperado: Any,
    km_fin: Any,
    plazo_meses: int,
    tipo_uso: str,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = merge_reconditioning_policy(policy)
    venta = max(_d(precio_venta_esperado), Decimal("0"))
    base = venta * (_d(cfg.get("base_pct_sobre_precio_venta"), "2.5") / Decimal("100"))
    uso_key = str(tipo_uso or "USO_COMERCIAL").upper()
    uso_map = cfg.get("por_uso") or {}
    uso_f = _d(uso_map.get(uso_key, uso_map.get("USO_COMERCIAL", 1.15)), "1.15")
    km = max(_d(km_fin), Decimal("0"))
    anios = max(Decimal(str(max(plazo_meses, 1))) / Decimal("12"), Decimal("0.5"))
    umbral = _d((cfg.get("por_km_exceso") or {}).get("umbral_km_anio"), "20000") * anios
    exceso = max(km - umbral, Decimal("0"))
    costo_1k = _d((cfg.get("por_km_exceso") or {}).get("costo_por_1000_km_exceso"), "18000")
    extra_km = (exceso / Decimal("1000")) * costo_1k
    total = (base * uso_f + extra_km).quantize(Decimal("1"))
    desg_pct = cfg.get("desglose_pct") or {}
    desglose = {k: float((total * _d(v)).quantize(Decimal("1"))) for k, v in desg_pct.items()}
    return {
        "reconditioning_cost": float(total),
        "base": float(base.quantize(Decimal("1"))),
        "factor_uso": float(uso_f),
        "extra_km": float(extra_km.quantize(Decimal("1"))),
        "desglose": desglose,
        "tipo_uso": uso_key,
    }
