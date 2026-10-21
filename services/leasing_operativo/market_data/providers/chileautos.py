# services/leasing_operativo/market_data/providers/chileautos.py
# -*- coding: utf-8 -*-
"""ChileautosProvider — reutiliza fetch existente; normaliza a VehicleMarketComparable."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.leasing_operativo.market_data.providers.base import MarketDataProvider
from services.leasing_operativo.market_data.types import MarketSearchRequest, VehicleMarketComparable


class ChileautosProvider(MarketDataProvider):
    source_code = "chileautos"
    default_weight = 0.50

    def search(self, request: MarketSearchRequest) -> dict[str, Any]:
        from services.leasing_operativo.market_comps import fetch_chileautos_comps

        raw = fetch_chileautos_comps(
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
            if request.version and not item.version:
                item.version = request.version
            comps.append(item)
        return {
            "source": self.source_code,
            "portal": self.source_code,
            "ok": bool(raw.get("ok")),
            "error": raw.get("error"),
            "search_url": raw.get("search_url") or "",
            "comps": comps,
            "count": len(comps),
            "mode": "live_api",
        }
