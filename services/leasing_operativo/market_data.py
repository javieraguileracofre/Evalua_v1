# services/leasing_operativo/market_data.py
# -*- coding: utf-8 -*-
"""Indicadores de mercado para cotización LOP (UF/USD/IPC)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib.request import urlopen


def fetch_cl_market_indicators(timeout_s: float = 4.0) -> dict[str, Any]:
    """
    Obtiene UF/USD/IPC desde fuente pública chilena.
    Retorna valores y metadata de fuente; si falla, devuelve estructura con source=fallback.
    """
    url = "https://mindicador.cl/api"
    try:
        with urlopen(url, timeout=timeout_s) as r:
            payload = json.loads(r.read().decode("utf-8"))
        uf = float((payload.get("uf") or {}).get("valor") or 0)
        usd = float((payload.get("dolar") or {}).get("valor") or 0)
        ipc = float((payload.get("ipc") or {}).get("valor") or 0)
        fecha = payload.get("fecha")
        return {
            "source": "mindicador.cl",
            "as_of": fecha,
            "uf_clp": uf,
            "usd_clp": usd,
            "ipc_pct": ipc,
        }
    except Exception:
        return {
            "source": "fallback",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "uf_clp": 0.0,
            "usd_clp": 0.0,
            "ipc_pct": 0.0,
        }
