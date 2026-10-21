# services/leasing_operativo/market_data/normalizer.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any

from services.leasing_operativo.market_data.types import VehicleMarketComparable


def _norm_text(v: Any) -> str:
    s = str(v or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_comparable(comp: VehicleMarketComparable | dict[str, Any]) -> VehicleMarketComparable:
    if isinstance(comp, dict):
        item = VehicleMarketComparable.from_legacy_comp(comp)
    else:
        item = comp
    item.brand = _norm_text(item.brand).title()
    item.model = _norm_text(item.model).title()
    item.version = _norm_text(item.version).title() if item.version else ""
    item.fuel_type = _norm_text(item.fuel_type)
    item.transmission = _norm_text(item.transmission)
    item.body_type = _norm_text(item.body_type)
    item.region = _norm_text(item.region).title() if item.region else ""
    if item.price < 0:
        item.price = 0.0
    if item.mileage is not None and item.mileage < 0:
        item.mileage = 0.0
    return item


def remove_price_outliers(comps: list[VehicleMarketComparable], *, iqr_mult: float = 1.5) -> list[VehicleMarketComparable]:
    prices = sorted(c.price for c in comps if c.price > 0 and not c.excluded and not c.incorrect)
    if len(prices) < 4:
        return comps
    q1 = prices[len(prices) // 4]
    q3 = prices[(3 * len(prices)) // 4]
    iqr = max(q3 - q1, 1.0)
    lo = q1 - iqr_mult * iqr
    hi = q3 + iqr_mult * iqr
    out: list[VehicleMarketComparable] = []
    for c in comps:
        if c.price <= 0 or c.excluded or c.incorrect:
            out.append(c)
            continue
        if lo <= c.price <= hi:
            out.append(c)
    return out if out else comps
