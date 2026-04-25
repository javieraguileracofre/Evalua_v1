# services/indicadores_mercado.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def _q4(v: float | Decimal | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def obtener_uf_dolar_hoy(timeout_s: float = 6.0) -> dict[str, str]:
    """
    Obtiene UF y USD diarios desde `mindicador.cl` (serie basada en BCCh).
    Retorna strings para JSON estable.
    """
    import httpx

    url = "https://mindicador.cl/api"
    with httpx.Client(timeout=timeout_s) as client:
        res = client.get(url)
        res.raise_for_status()
        data = res.json()

    uf = data.get("uf", {}).get("valor")
    usd = data.get("dolar", {}).get("valor")
    fecha_raw = data.get("uf", {}).get("fecha") or data.get("fecha")

    if uf is None or usd is None:
        raise ValueError("No se pudo leer UF/USD desde el proveedor.")

    try:
        fecha = date.fromisoformat(str(fecha_raw)[:10]).isoformat()
    except Exception:
        fecha = date.today().isoformat()

    return {
        "fecha": fecha,
        "uf": str(_q4(uf)),
        "dolar": str(_q4(usd)),
        "fuente": "mindicador.cl (serie BCCh)",
    }
