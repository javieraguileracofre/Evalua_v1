# services/leasing_financiero_metricas.py
# -*- coding: utf-8 -*-
"""Métricas financieras: TIR/CAE aproximado para leasing financiero."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Sequence

from schemas.comercial.leasing_amortizacion import AmortizacionCuota

PERIODICIDAD_PERIODOS_ANUAL = {
    "MENSUAL": 12,
    "TRIMESTRAL": 4,
    "SEMESTRAL": 2,
    "ANUAL": 1,
}


def _q4(v: Decimal | float | int) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _npv(rate: Decimal, flujos: Sequence[Decimal]) -> Decimal:
    total = Decimal("0")
    one = Decimal("1")
    for t, cf in enumerate(flujos):
        total += cf / ((one + rate) ** t)
    return total


def calcular_tir_periodica(flujos: Sequence[Decimal], *, guess: Decimal = Decimal("0.01")) -> Decimal | None:
    """
    TIR periódica por bisección sobre flujos indexados 0..N.
    Flujos negativos = desembolsos del cliente.
    """
    if len(flujos) < 2:
        return None
    tiene_pos = any(cf > 0 for cf in flujos)
    tiene_neg = any(cf < 0 for cf in flujos)
    if not (tiene_pos and tiene_neg):
        return None

    low = Decimal("-0.9999")
    high = Decimal("10")
    f_low = _npv(low, flujos)
    f_high = _npv(high, flujos)
    if f_low * f_high > 0:
        mid = guess
        for _ in range(80):
            f_mid = _npv(mid, flujos)
            if abs(f_mid) < Decimal("0.0001"):
                return _q4(mid)
            deriv = Decimal("0")
            for t, cf in enumerate(flujos):
                if t == 0:
                    continue
                deriv -= Decimal(t) * cf / ((Decimal("1") + mid) ** (t + 1))
            if deriv == 0:
                break
            mid = mid - f_mid / deriv
            if mid <= Decimal("-0.9999") or mid > Decimal("10"):
                break
        return None

    for _ in range(120):
        mid = (low + high) / 2
        f_mid = _npv(mid, flujos)
        if abs(f_mid) < Decimal("0.000001"):
            return _q4(mid)
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return _q4((low + high) / 2)


def tir_a_anual(tir_periodica: Decimal | None, periodicidad: str = "MENSUAL") -> Decimal | None:
    if tir_periodica is None:
        return None
    n = PERIODICIDAD_PERIODOS_ANUAL.get((periodicidad or "MENSUAL").strip().upper(), 12)
    anual = (Decimal("1") + tir_periodica) ** n - Decimal("1")
    return _q4(anual * 100)


def flujos_cliente_desde_tabla(
    *,
    pago_inicial: Decimal,
    tabla: Iterable[AmortizacionCuota],
    monto_financiado: Decimal,
) -> list[Decimal]:
    """
    Flujos desde la óptica del cliente/arrendatario:
    t0 recibe financiamiento neto (positivo) menos pie (negativo).
    Cuotas como desembolsos negativos.
    """
    flujos: list[Decimal] = [monto_financiado - pago_inicial]
    for cuota in tabla:
        if cuota.es_gracia and cuota.cuota == 0 and cuota.interes > 0:
            flujos.append(-cuota.interes)
        elif cuota.cuota > 0:
            flujos.append(-cuota.cuota)
    return flujos


def calcular_cae_tir_operacion(
    *,
    pago_inicial: Decimal,
    monto_financiado: Decimal,
    tabla: list[AmortizacionCuota],
    periodicidad: str = "MENSUAL",
) -> tuple[Decimal | None, Decimal | None]:
    """
    CAE aproximado = TIR anualizada de flujos del cliente.
    No reemplaza cálculo CMF regulado; referencia comercial interna.
    """
    flujos = flujos_cliente_desde_tabla(
        pago_inicial=pago_inicial,
        tabla=tabla,
        monto_financiado=monto_financiado,
    )
    tir_p = calcular_tir_periodica(flujos)
    tir_anual = tir_a_anual(tir_p, periodicidad)
    return tir_anual, tir_anual
