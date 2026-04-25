# services/leasing_operativo/pricing_model.py
# -*- coding: utf-8 -*-
"""Tres métodos de pricing: costo+spread, margen sobre venta, TIR objetivo."""
from __future__ import annotations

from decimal import Decimal
from typing import Callable


def renta_costo_mas_spread(costo_total_mensual: Decimal, spread_pct: Decimal) -> Decimal:
    sp = spread_pct / Decimal("100")
    return (costo_total_mensual * (Decimal("1") + sp)).quantize(Decimal("1"))


def renta_margen_sobre_venta(costo_total_mensual: Decimal, margen_pct: Decimal) -> Decimal:
    m = margen_pct / Decimal("100")
    if m >= Decimal("1"):
        m = Decimal("0.5")
    if m <= 0:
        return costo_total_mensual
    return (costo_total_mensual / (Decimal("1") - m)).quantize(Decimal("1"))


def npv_mensual(flujos: list[Decimal], tasa_mensual: Decimal) -> Decimal:
    s = Decimal("0")
    one_plus = Decimal("1") + tasa_mensual
    for t, cf in enumerate(flujos):
        s += cf / (one_plus**t)
    return s


def tir_mensual_bisec(flujos: list[Decimal], low: Decimal = Decimal("-0.95"), high: Decimal = Decimal("2"), iters: int = 120) -> Decimal | None:
    """TIR mensual implícita (raíz de NPV=0)."""
    f_lo = npv_mensual(flujos, low)
    f_hi = npv_mensual(flujos, high)
    if f_lo * f_hi > 0:
        return None
    a, b = low, high
    fa, fb = f_lo, f_hi
    for _ in range(iters):
        mid = (a + b) / Decimal("2")
        fm = npv_mensual(flujos, mid)
        if abs(fm) < Decimal("0.0001"):
            return mid
        if fa * fm <= 0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return (a + b) / Decimal("2")


def tir_anual_desde_mensual(tir_m: Decimal) -> Decimal:
    return (((Decimal("1") + tir_m) ** 12) - Decimal("1")) * Decimal("100")


def construir_flujos_inversionista(
    capex: Decimal,
    plazo: int,
    renta: Decimal,
    *,
    costo_fondo_m: list[Decimal],
    depreciacion_m: Decimal,
    op_m: list[Decimal],
    riesgo_m: Decimal,
    comercial_m: Decimal,
) -> list[Decimal]:
    """Flujo contable / resultado operacional (incluye depreciación económica)."""
    fl: list[Decimal] = [-capex]
    for t in range(plazo):
        cf = (
            renta
            - costo_fondo_m[t]
            - depreciacion_m
            - op_m[t]
            - riesgo_m
            - comercial_m
        )
        fl.append(cf)
    return fl


def construir_flujos_caja_inversionista(
    capex: Decimal,
    plazo: int,
    renta: Decimal,
    *,
    op_m: list[Decimal],
    riesgo_m: Decimal,
    comercial_m: Decimal,
    valor_residual_terminal: Decimal = Decimal("0"),
) -> list[Decimal]:
    """Flujo de caja para VAN/TIR: sin depreciación ni costo de fondo explícito (el descuento a WACC
    ya incorpora el costo del capital; restarlo además sería doble conteo). Último mes incluye
    recuperación esperada del activo (valor residual económico)."""
    fl: list[Decimal] = [-capex]
    n = max(int(plazo), 1)
    for t in range(n):
        cf = renta - op_m[t] - riesgo_m - comercial_m
        if t == n - 1:
            cf += valor_residual_terminal
        fl.append(cf)
    return fl


def buscar_renta_por_tir(
    renta_min: Decimal,
    capex: Decimal,
    plazo: int,
    tir_objetivo_anual_pct: Decimal,
    build_flujos: Callable[[Decimal], list[Decimal]],
) -> Decimal:
    """Incrementa renta desde el mínimo hasta alcanzar TIR anual objetivo (o el máximo alcanzable)."""
    target_a = tir_objetivo_anual_pct
    r = max(renta_min, Decimal("1"))
    last_ok = r
    for _ in range(250):
        fl = build_flujos(r)
        tir_m = tir_mensual_bisec(fl)
        if tir_m is None:
            r = r * Decimal("1.03")
            continue
        tir_a = tir_anual_desde_mensual(tir_m)
        if tir_a >= target_a:
            last_ok = r
            break
        r = r * Decimal("1.02")
        if r > capex * Decimal("4"):
            break
    return last_ok.quantize(Decimal("1"))
