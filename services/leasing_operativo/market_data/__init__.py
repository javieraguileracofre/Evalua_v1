# services/leasing_operativo/market_data/__init__.py
"""
Capa de datos de mercado LOP.

Incluye:
  - Indicadores macro (UF/USD/IPC) — fetch_cl_market_indicators
  - Comparables de portales — search_and_value / providers
"""
from services.leasing_operativo.market_data.indicators import fetch_cl_market_indicators
from services.leasing_operativo.market_data.types import MarketSearchRequest, VehicleMarketComparable
from services.leasing_operativo.market_data.valuation import MODEL_VERSION, search_and_value

__all__ = [
    "fetch_cl_market_indicators",
    "VehicleMarketComparable",
    "MarketSearchRequest",
    "search_and_value",
    "MODEL_VERSION",
]
