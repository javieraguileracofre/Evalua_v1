# services/leasing_operativo/market_data/comparator.py
# -*- coding: utf-8 -*-
"""Algoritmo de comparabilidad (niveles 1–4) + score 0–100."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.leasing_operativo.market_data.types import VehicleMarketComparable


@dataclass
class SubjectVehicle:
    brand: str
    model: str
    version: str = ""
    year: int | None = None
    fuel_type: str = ""
    transmission: str = ""
    body_type: str = ""
    segment: str = ""
    mileage_target: float | None = None
    region: str = ""


def _eq(a: Any, b: Any) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower() and bool(str(a or "").strip())


def comparability_level(subject: SubjectVehicle, comp: VehicleMarketComparable) -> int:
    """1=directo … 4=sustituto segmento. 0=descartable."""
    same_brand = _eq(subject.brand, comp.brand)
    same_model = _eq(subject.model, comp.model)
    same_version = (not subject.version) or _eq(subject.version, comp.version)
    same_year = subject.year is None or comp.year is None or int(subject.year) == int(comp.year)
    same_fuel = (not subject.fuel_type) or _eq(subject.fuel_type, comp.fuel_type)
    same_tx = (not subject.transmission) or _eq(subject.transmission, comp.transmission)
    same_body = (not subject.body_type) or _eq(subject.body_type, comp.body_type)
    same_seg = (not subject.segment) or _eq(subject.segment, comp.body_type) or _eq(subject.segment, comp.raw.get("segment"))

    if same_brand and same_model and same_version and same_year and same_fuel and same_tx and same_body:
        return 1
    if same_brand and same_model and same_year:
        return 2
    if same_brand and same_year and same_seg:
        return 3
    if same_seg or (same_brand and same_model):
        return 4
    return 0


def score_comparable(subject: SubjectVehicle, comp: VehicleMarketComparable) -> float:
    level = comparability_level(subject, comp)
    if level == 0:
        return 0.0
    base = {1: 92.0, 2: 78.0, 3: 62.0, 4: 45.0}[level]
    # Ajuste km
    if subject.mileage_target is not None and comp.mileage is not None and subject.mileage_target > 0:
        delta = abs(float(comp.mileage) - float(subject.mileage_target)) / float(subject.mileage_target)
        base -= min(delta * 25.0, 22.0)
    # Ajuste año ±1
    if subject.year and comp.year:
        base -= min(abs(int(subject.year) - int(comp.year)) * 4.0, 12.0)
    # Región
    if subject.region and comp.region and _eq(subject.region, comp.region):
        base += 3.0
    return max(0.0, min(100.0, round(base, 1)))


def rank_comparables(
    subject: SubjectVehicle,
    comps: list[VehicleMarketComparable],
    *,
    min_score: float = 40.0,
) -> list[VehicleMarketComparable]:
    scored: list[VehicleMarketComparable] = []
    for c in comps:
        if c.excluded or c.incorrect or c.price <= 0:
            continue
        c.comparability_score = score_comparable(subject, c)
        if c.comparability_score >= min_score:
            scored.append(c)
    scored.sort(key=lambda x: (-x.comparability_score, abs((x.mileage or 0) - (subject.mileage_target or 0))))
    return scored
