# services/leasing_operativo/market_data/types.py
# -*- coding: utf-8 -*-
"""Estructuras normalizadas de comparables de mercado (desacopladas del HTML)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class VehicleMarketComparable:
    source: str
    source_url: str
    brand: str
    model: str
    version: str = ""
    year: int | None = None
    fuel_type: str = ""
    transmission: str = ""
    body_type: str = ""
    mileage: float | None = None
    region: str = ""
    price: float = 0.0
    publication_date: str | None = None
    seller_type: str = ""
    condition: str = "usado"
    extracted_at: str = ""
    image_url: str = ""
    external_id: str = ""
    title: str = ""
    excluded: bool = False
    incorrect: bool = False
    comparability_score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Compat UI simulador (portal/url/km/price/year/image_url)
        d["portal"] = self.source
        d["url"] = self.source_url
        d["km"] = self.mileage
        d["location"] = self.region
        if not d.get("title"):
            d["title"] = " ".join(
                str(x) for x in (self.year or "", self.brand, self.model, self.version) if x
            ).strip()
        return d

    @classmethod
    def from_legacy_comp(cls, comp: dict[str, Any], *, source: str | None = None) -> "VehicleMarketComparable":
        src = str(source or comp.get("portal") or comp.get("source") or "unknown").lower()
        return cls(
            source=src,
            source_url=str(comp.get("url") or comp.get("source_url") or ""),
            brand=str(comp.get("make") or comp.get("brand") or ""),
            model=str(comp.get("model") or ""),
            version=str(comp.get("version") or ""),
            year=int(comp["year"]) if comp.get("year") else None,
            fuel_type=str(comp.get("fuel_type") or ""),
            transmission=str(comp.get("transmission") or ""),
            body_type=str(comp.get("body_type") or ""),
            mileage=float(comp["km"]) if comp.get("km") is not None else (
                float(comp["mileage"]) if comp.get("mileage") is not None else None
            ),
            region=str(comp.get("location") or comp.get("region") or ""),
            price=float(comp.get("price") or 0),
            publication_date=comp.get("publication_date"),
            seller_type=str(comp.get("seller_type") or ""),
            condition=str(comp.get("condition") or "usado"),
            extracted_at=str(comp.get("extracted_at") or datetime.now(timezone.utc).isoformat()),
            image_url=str(comp.get("image_url") or ""),
            external_id=str(comp.get("external_id") or ""),
            title=str(comp.get("title") or ""),
            excluded=bool(comp.get("excluded")),
            incorrect=bool(comp.get("incorrect")),
            comparability_score=float(comp.get("comparability_score") or 0),
            raw=dict(comp),
        )


@dataclass
class MarketSearchRequest:
    brand: str
    model: str
    version: str = ""
    year_min: int = 1995
    year_max: int | None = None
    km_min: int = 0
    km_max: int | None = None
    fuel_type: str = ""
    transmission: str = ""
    body_type: str = ""
    region: str = ""
    segment: str = ""
