# services/leasing_operativo/market_data/providers/base.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from services.leasing_operativo.market_data.types import MarketSearchRequest, VehicleMarketComparable


class MarketDataProvider(ABC):
    """Proveedor desacoplado. No acoplar motor financiero a HTML de un sitio."""

    source_code: str = "unknown"
    default_weight: float = 0.0

    def __init__(self, *, timeout_s: float = 7.0, max_retries: int = 0, min_interval_s: float = 0.0):
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.min_interval_s = min_interval_s
        self._last_call_ts = 0.0

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call_ts = time.monotonic()

    @abstractmethod
    def search(self, request: MarketSearchRequest) -> dict[str, Any]:
        """Retorna {source, ok, error, search_url, comps: list[VehicleMarketComparable]}."""

    def search_with_retries(self, request: MarketSearchRequest) -> dict[str, Any]:
        last: dict[str, Any] = {
            "source": self.source_code,
            "portal": self.source_code,
            "ok": False,
            "error": "sin intento",
            "search_url": "",
            "comps": [],
            "count": 0,
        }
        for attempt in range(max(int(self.max_retries), 1) + 1):
            self._rate_limit()
            try:
                last = self.search(request)
                last.setdefault("source", self.source_code)
                last.setdefault("portal", self.source_code)
                if last.get("ok"):
                    return last
            except Exception as exc:  # noqa: BLE001 — auditoría por proveedor
                last = {
                    "source": self.source_code,
                    "portal": self.source_code,
                    "ok": False,
                    "error": str(exc),
                    "search_url": "",
                    "comps": [],
                    "count": 0,
                    "attempt": attempt + 1,
                }
        return last


def comps_to_legacy(comps: list[VehicleMarketComparable]) -> list[dict[str, Any]]:
    return [c.to_dict() for c in comps]
