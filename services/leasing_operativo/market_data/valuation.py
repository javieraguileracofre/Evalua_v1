# services/leasing_operativo/market_data/valuation.py
# -*- coding: utf-8 -*-
"""Valorización ponderada por fuente (pesos configurables, no hardcodeados en motor)."""
from __future__ import annotations

import logging
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from services.leasing_operativo.market_data.comparator import SubjectVehicle, rank_comparables
from services.leasing_operativo.market_data.normalizer import normalize_comparable, remove_price_outliers
from services.leasing_operativo.market_data.providers import (
    AutocosmosProvider,
    ChileautosProvider,
    MercadoLibreAutosProvider,
    YapoAutosProvider,
)
from services.leasing_operativo.market_data.providers.base import MarketDataProvider
from services.leasing_operativo.market_data.types import MarketSearchRequest, VehicleMarketComparable

logger = logging.getLogger("evalua.lop.market")

DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "chileautos": 0.50,
    "mercadolibre": 0.30,
    "yapo": 0.20,
    "autocosmos": 0.0,
}

MODEL_VERSION = "RV-2026.10.01"

# Evita bloquear el worker único de Uvicorn (causa típica de 503 en la UI).
PROVIDER_TIMEOUT_S = 7.0
MARKET_WALL_TIMEOUT_S = 12.0
PROVIDER_RETRIES = 0


def resolve_weights(policy_weights: dict[str, Any] | None) -> dict[str, float]:
    raw = dict(DEFAULT_SOURCE_WEIGHTS)
    if isinstance(policy_weights, dict):
        for k, v in policy_weights.items():
            key = str(k).strip().lower()
            try:
                raw[key] = float(v)
            except (TypeError, ValueError):
                continue
    positive = {k: max(float(v), 0.0) for k, v in raw.items()}
    total = sum(positive.values())
    if total <= 0:
        return dict(DEFAULT_SOURCE_WEIGHTS)
    return {k: (v / total if v > 0 else 0.0) for k, v in positive.items()}


def default_providers(*, yapo_manual: list[dict[str, Any]] | None = None) -> list[MarketDataProvider]:
    kw = {"timeout_s": PROVIDER_TIMEOUT_S, "max_retries": PROVIDER_RETRIES, "min_interval_s": 0.0}
    return [
        ChileautosProvider(**kw),
        MercadoLibreAutosProvider(**kw),
        YapoAutosProvider(manual_comps=yapo_manual, **kw),
        AutocosmosProvider(**kw),
    ]


def weighted_market_price(
    comps: list[VehicleMarketComparable],
    weights: dict[str, float],
) -> dict[str, Any]:
    by_src: dict[str, list[float]] = {}
    for c in comps:
        if c.price <= 0 or c.excluded or c.incorrect:
            continue
        by_src.setdefault(c.source, []).append(float(c.price))
    contrib: dict[str, Any] = {}
    num = 0.0
    den = 0.0
    for src, prices in by_src.items():
        w = float(weights.get(src, 0.0))
        if w <= 0 or not prices:
            contrib[src] = {
                "n": len(prices),
                "median": statistics.median(prices) if prices else None,
                "weight": w,
                "used": False,
            }
            continue
        med = float(statistics.median(prices))
        num += med * w
        den += w
        contrib[src] = {"n": len(prices), "median": med, "weight": w, "used": True}
    valor = (num / den) if den > 0 else None
    all_prices = [c.price for c in comps if c.price > 0 and not c.excluded and not c.incorrect]
    return {
        "valor_mercado_actual": round(valor, 0) if valor else None,
        "mediana_global": float(statistics.median(all_prices)) if all_prices else None,
        "n": len(all_prices),
        "min": min(all_prices) if all_prices else None,
        "max": max(all_prices) if all_prices else None,
        "por_fuente": contrib,
        "dispersion_pct": (
            round((max(all_prices) - min(all_prices)) / statistics.median(all_prices) * 100, 2)
            if all_prices and statistics.median(all_prices) > 0
            else None
        ),
    }


def _portal_stub(
    *,
    source: str,
    search_url: str,
    weight: float,
    error: str,
    mode: str = "skipped",
) -> dict[str, Any]:
    return {
        "portal": source,
        "ok": False,
        "error": error,
        "search_url": search_url,
        "count": 0,
        "mode": mode,
        "weight": weight,
    }


def _run_provider(provider: MarketDataProvider, request: MarketSearchRequest) -> dict[str, Any]:
    try:
        return provider.search_with_retries(request)
    except Exception as exc:  # noqa: BLE001
        return {
            "source": provider.source_code,
            "portal": provider.source_code,
            "ok": False,
            "error": str(exc),
            "search_url": "",
            "comps": [],
            "count": 0,
        }


def search_and_value(
    *,
    brand: str,
    model: str,
    version: str = "",
    year: int | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    km_target: float | None = None,
    km_min: int = 0,
    km_max: int | None = None,
    fuel_type: str = "",
    transmission: str = "",
    body_type: str = "",
    segment: str = "",
    region: str = "",
    source_weights: dict[str, Any] | None = None,
    providers: list[MarketDataProvider] | None = None,
    yapo_manual: list[dict[str, Any]] | None = None,
    wall_timeout_s: float = MARKET_WALL_TIMEOUT_S,
) -> dict[str, Any]:
    weights = resolve_weights(source_weights)
    a_min = int(year_min if year_min is not None else max((year or 1995) - 1, 1995))
    a_max = int(year_max if year_max is not None else (year or datetime.now(timezone.utc).year))
    req = MarketSearchRequest(
        brand=brand,
        model=model,
        version=version,
        year_min=a_min,
        year_max=a_max,
        km_min=int(km_min or 0),
        km_max=int(km_max) if km_max is not None else None,
        fuel_type=fuel_type,
        transmission=transmission,
        body_type=body_type,
        region=region,
        segment=segment,
    )

    from services.leasing_operativo.market_comps import build_search_urls

    search_urls = build_search_urls(
        marca=brand,
        modelo=model,
        anio_min=a_min,
        anio_max=a_max,
        km_min=int(km_min or 0),
        km_max=km_max,
    )
    search_urls["yapo"] = f"https://www.yapo.cl/chile/autos?q={quote(f'{brand} {model}'.strip())}"

    all_providers = providers or default_providers(yapo_manual=yapo_manual)
    portal_rows: list[dict[str, Any]] = []
    raw_comps: list[VehicleMarketComparable] = []

    # Portales con peso 0: no fetchear (evita bloquear); conservar link auditable.
    live: list[MarketDataProvider] = []
    for p in all_providers:
        w = float(weights.get(p.source_code, 0.0))
        # Yapo sin comps manuales es instantáneo; se mantiene para link.
        is_fast_stub = p.source_code == "yapo" and not getattr(p, "manual_comps", None)
        if w <= 0 and p.source_code != "yapo":
            portal_rows.append(
                _portal_stub(
                    source=p.source_code,
                    search_url=search_urls.get(p.source_code, ""),
                    weight=w,
                    error="Consulta omitida (peso 0). Link de búsqueda disponible como respaldo.",
                    mode="skipped_zero_weight",
                )
            )
            continue
        if is_fast_stub:
            row = _run_provider(p, req)
            portal_rows.append(
                {
                    "portal": p.source_code,
                    "ok": bool(row.get("ok")),
                    "error": row.get("error"),
                    "search_url": row.get("search_url") or search_urls.get("yapo", ""),
                    "count": int(row.get("count") or 0),
                    "mode": row.get("mode") or "manual_or_authorized_import",
                    "weight": w,
                }
            )
            continue
        live.append(p)

    # Consultas live en paralelo con techo de tiempo (no secuencial 25s×N).
    if live:
        max_workers = min(len(live), 3)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run_provider, p, req): p for p in live}
            try:
                for fut in as_completed(futures, timeout=max(float(wall_timeout_s), 1.0)):
                    p = futures[fut]
                    try:
                        row = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        row = {
                            "portal": p.source_code,
                            "ok": False,
                            "error": str(exc),
                            "search_url": search_urls.get(p.source_code, ""),
                            "comps": [],
                            "count": 0,
                        }
                    comps = [normalize_comparable(c) for c in (row.get("comps") or [])]
                    portal_rows.append(
                        {
                            "portal": row.get("portal") or p.source_code,
                            "ok": bool(row.get("ok")),
                            "error": row.get("error"),
                            "search_url": row.get("search_url") or search_urls.get(p.source_code, ""),
                            "count": int(row.get("count") or len(comps)),
                            "mode": row.get("mode"),
                            "weight": weights.get(p.source_code, 0.0),
                        }
                    )
                    raw_comps.extend(comps)
            except TimeoutError:
                logger.warning(
                    "market search wall timeout brand=%s model=%s timeout=%ss",
                    brand,
                    model,
                    wall_timeout_s,
                )
                for fut, p in futures.items():
                    if fut.done():
                        continue
                    fut.cancel()
                    portal_rows.append(
                        _portal_stub(
                            source=p.source_code,
                            search_url=search_urls.get(p.source_code, ""),
                            weight=float(weights.get(p.source_code, 0.0)),
                            error=f"Timeout global de mercado ({wall_timeout_s:.0f}s). Use links de búsqueda.",
                            mode="timeout",
                        )
                    )

    # Orden estable de portales
    order = {"chileautos": 0, "mercadolibre": 1, "yapo": 2, "autocosmos": 3}
    portal_rows.sort(key=lambda r: order.get(str(r.get("portal") or ""), 99))

    subject = SubjectVehicle(
        brand=brand,
        model=model,
        version=version,
        year=year or a_max,
        fuel_type=fuel_type,
        transmission=transmission,
        body_type=body_type,
        segment=segment,
        mileage_target=km_target,
        region=region,
    )
    cleaned = remove_price_outliers(raw_comps)
    ranked = rank_comparables(subject, cleaned)
    valuation = weighted_market_price(ranked, weights)

    return {
        "model_version": MODEL_VERSION,
        "consultado_en": datetime.now(timezone.utc).isoformat(),
        "subject": {
            "brand": brand,
            "model": model,
            "version": version,
            "year": year,
            "km_target": km_target,
        },
        "weights": weights,
        "search_urls": search_urls,
        "portales": portal_rows,
        "comparables": [c.to_dict() for c in ranked[:18]],
        "stats": {
            "n": valuation["n"],
            "mediana": valuation["mediana_global"],
            "valor_mercado_actual": valuation["valor_mercado_actual"],
            "min": valuation["min"],
            "max": valuation["max"],
            "dispersion_pct": valuation["dispersion_pct"],
            "por_fuente": valuation["por_fuente"],
        },
        "valor_mercado_actual": valuation["valor_mercado_actual"],
    }
