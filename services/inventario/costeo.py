# services/inventario/costeo.py
# -*- coding: utf-8 -*-
"""Costo promedio ponderado. Una sola política para entradas y salidas."""
from __future__ import annotations

from decimal import Decimal

Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")

TIPOS_ENTRADA = frozenset(
    {
        "ENTRADA",
        "AJUSTE_POSITIVO",
        "INVENTARIO_INICIAL",
        "DEVOLUCION_CLIENTE",
    }
)

TIPOS_SALIDA = frozenset(
    {
        "SALIDA",
        "AJUSTE_NEGATIVO",
        "MERMA",
        "DEVOLUCION_PROVEEDOR",
    }
)


def _d(value: object, quantum: Decimal = Q4) -> Decimal:
    try:
        raw = Decimal(str(value if value is not None else "0"))
    except Exception:
        raw = Decimal("0")
    return raw.quantize(quantum)


def aplicar_costo_promedio(
    *,
    stock: Decimal,
    promedio: Decimal,
    precio_compra: Decimal,
    tipo: str,
    cantidad: Decimal,
    costo_entrada: Decimal,
) -> tuple[Decimal, Decimal]:
    """Devuelve (costo unitario del movimiento, promedio vigente después).

    Las entradas recalculan el promedio. Las salidas lo consumen y no lo cambian.
    """
    stock_q = _d(stock, Q2)
    promedio_q = _d(promedio)
    if promedio_q <= 0:
        promedio_q = _d(precio_compra)
    cantidad_q = _d(cantidad, Q2)
    entrada = _d(costo_entrada)
    tipo_n = (tipo or "").strip().upper()

    if tipo_n in TIPOS_ENTRADA:
        if entrada <= 0:
            entrada = promedio_q
        nuevo_stock = stock_q + cantidad_q
        if nuevo_stock > 0 and entrada > 0:
            promedio_q = (
                (stock_q * promedio_q) + (cantidad_q * entrada)
            ) / nuevo_stock
            promedio_q = promedio_q.quantize(Q4)
        costo_mov = entrada if entrada > 0 else promedio_q
        return costo_mov.quantize(Q4), promedio_q.quantize(Q4)

    if tipo_n in TIPOS_SALIDA:
        costo_mov = promedio_q if promedio_q > 0 else _d(precio_compra)
        return costo_mov.quantize(Q4), promedio_q.quantize(Q4)

    return entrada.quantize(Q4), promedio_q.quantize(Q4)


def salida_requiere_asiento(tipo: str, referencia_tipo: str | None) -> bool:
    """La venta ya contabiliza el costo en la nota. El resto de salidas, aquí."""
    tipo_n = (tipo or "").strip().upper()
    if tipo_n not in TIPOS_SALIDA:
        return False
    return (referencia_tipo or "").strip().upper() != "VENTA"
