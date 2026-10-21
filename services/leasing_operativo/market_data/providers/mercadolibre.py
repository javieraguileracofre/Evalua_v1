# services/leasing_operativo/market_data/providers/mercadolibre.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.leasing_operativo.market_data.providers.base import MarketDataProvider
from services.leasing_operativo.market_data.types import MarketSearchRequest, VehicleMarketComparable


class MercadoLibreAutosProvider(MarketDataProvider):
    source_code = "mercadolibre"
    default_weight = 0.30

    def search(self, request: MarketSearchRequest) -> dict[str, Any]:
        from services.leasing_operativo.market_comps import fetch_mercadolibre_comps

        raw = fetch_mercadolibre_comps(
            marca=request.brand,
            modelo=request.model,
            anio_min=request.year_min,
            anio_max=request.year_max,
            km_min=request.km_min,
            km_max=request.km_max,
            timeout_s=self.timeout_s,
        )
        extracted = datetime.now(timezone.utc).isoformat()
        comps: list[VehicleMarketComparable] = []
        for c in raw.get("comps") or []:
            item = VehicleMarketComparable.from_legacy_comp(c, source=self.source_code)
            item.extracted_at = extracted
            comps.append(item)
        return {
            "source": self.source_code,
            "portal": self.source_code,
            "ok": bool(raw.get("ok")),
            "error": raw.get("error"),
            "search_url": raw.get("search_url") or "",
            "comps": comps,
            "count": len(comps),
            "mode": "public_api",
        }
