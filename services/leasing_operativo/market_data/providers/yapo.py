# services/leasing_operativo/market_data/providers/yapo.py
# -*- coding: utf-8 -*-
"""
YapoAutosProvider.

Arquitectura preparada para:
  - integración autorizada
  - fuente pública / API
  - importación de datos
  - carga manual

NO implementa scraping ni evasión de CAPTCHA/anti-bot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from services.leasing_operativo.market_data.providers.base import MarketDataProvider
from services.leasing_operativo.market_data.types import MarketSearchRequest, VehicleMarketComparable


class YapoAutosProvider(MarketDataProvider):
    source_code = "yapo"
    default_weight = 0.20

    def __init__(self, *, manual_comps: list[dict[str, Any]] | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.manual_comps = list(manual_comps or [])

    def search_url_for(self, request: MarketSearchRequest) -> str:
        q = quote(f"{request.brand} {request.model}".strip())
        return f"https://www.yapo.cl/chile/autos?q={q}"

    def search(self, request: MarketSearchRequest) -> dict[str, Any]:
        url = self.search_url_for(request)
        extracted = datetime.now(timezone.utc).isoformat()
        comps: list[VehicleMarketComparable] = []
        for c in self.manual_comps:
            item = VehicleMarketComparable.from_legacy_comp(c, source=self.source_code)
            if not item.brand:
                item.brand = request.brand
            if not item.model:
                item.model = request.model
            item.extracted_at = item.extracted_at or extracted
            if item.price > 0:
                comps.append(item)
        return {
            "source": self.source_code,
            "portal": self.source_code,
            "ok": True if comps else False,
            "error": None
            if comps
            else (
                "Yapo sin automatización directa: use importación autorizada, "
                "carga manual o proveedor externo. Link de búsqueda disponible."
            ),
            "search_url": url,
            "comps": comps,
            "count": len(comps),
            "mode": "manual_or_authorized_import",
        }
