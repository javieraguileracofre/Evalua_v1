# services/leasing_operativo/sale_recovery_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.leasing_operativo.reconditioning_service import estimate_reconditioning


def _d(v: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(v).replace(",", ".")) if v is not None else Decimal(default)
    except Exception:
        return Decimal(default)


DEFAULT_SALE_COSTS: dict[str, Any] = {
    "comision_venta_pct": 2.0,
    "preparacion_fijo": 0,
    "traslado_fijo": 150000,
    "almacenamiento_mensual": 80000,
    "meses_venta": 2,
    "publicacion_fijo": 50000,
    "costo_financiero_mensual_pct": 0.8,
    "descuento_comercial_pct": 1.0,
    "documentacion_fijo": 80000,
    "otros_fijo": 0,
}


def merge_sale_costs(policy: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_SALE_COSTS)
    if isinstance(policy, dict):
        out.update({k: v for k, v in policy.items() if v is not None})
    return out


def calculate_recovery(
    *,
    precio_venta_esperado: Any,
    km_fin: Any,
    plazo_meses: int,
    tipo_uso: str,
    sale_policy: dict[str, Any] | None = None,
    reconditioning_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    venta = max(_d(precio_venta_esperado), Decimal("0"))
    sale = merge_sale_costs(sale_policy)
    recon = estimate_reconditioning(
        precio_venta_esperado=venta,
        km_fin=km_fin,
        plazo_meses=plazo_meses,
        tipo_uso=tipo_uso,
        policy=reconditioning_policy,
    )
    comision = venta * (_d(sale.get("comision_venta_pct"), "2") / Decimal("100"))
    meses = max(int(sale.get("meses_venta") or 2), 0)
    alm = _d(sale.get("almacenamiento_mensual")) * Decimal(meses)
    fin = venta * (_d(sale.get("costo_financiero_mensual_pct"), "0.8") / Decimal("100")) * Decimal(meses)
    desc = venta * (_d(sale.get("descuento_comercial_pct"), "1") / Decimal("100"))
    costos = {
        "comision_venta": float(comision.quantize(Decimal("1"))),
        "reacondicionamiento": recon["reconditioning_cost"],
        "preparacion": float(_d(sale.get("preparacion_fijo"))),
        "traslado": float(_d(sale.get("traslado_fijo"))),
        "almacenamiento": float(alm.quantize(Decimal("1"))),
        "publicacion": float(_d(sale.get("publicacion_fijo"))),
        "costo_financiero_venta": float(fin.quantize(Decimal("1"))),
        "descuento_comercial": float(desc.quantize(Decimal("1"))),
        "documentacion": float(_d(sale.get("documentacion_fijo"))),
        "otros": float(_d(sale.get("otros_fijo"))),
    }
    total_costos = sum(_d(v) for v in costos.values())
    neto = max(venta - total_costos, Decimal("0")).quantize(Decimal("1"))
    return {
        "VALOR_RECUPERO_BRUTO": float(venta.quantize(Decimal("1"))),
        "COSTOS_RECUPERACION": {**costos, "total": float(total_costos.quantize(Decimal("1")))},
        "reconditioning": recon,
        "VALOR_RECUPERO_NETO": float(neto),
    }
