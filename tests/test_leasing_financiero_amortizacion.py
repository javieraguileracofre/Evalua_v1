# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from services.leasing_financiero import (
    calcular_monto_financiado,
    calcular_pago_inicial,
    calcular_tabla_amortizacion,
    calcular_tea_anual,
    normalizar_tasa_anual,
    simular_cotizacion,
)
from schemas.comercial.leasing_cotizacion import LeasingSimulacionInput


def _cotizacion_base(**kwargs):
    base = {
        "plazo": 7,
        "monto_financiado": Decimal("228500"),
        "valor_neto": None,
        "monto": None,
        "tasa": Decimal("0"),
        "periodos_gracia": 0,
        "opcion_compra": Decimal("28500"),
        "fecha_inicio": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_amortizacion_tasa_cero_opcion_compra_no_consumir_renta():
    cotizacion = _cotizacion_base()

    tabla = calcular_tabla_amortizacion(cotizacion)

    assert len(tabla) == 8

    lineas_normales = [c for c in tabla if not c.es_gracia and not c.es_opcion_compra]
    assert len(lineas_normales) == 7

    cuota_7 = lineas_normales[-1]
    assert cuota_7.cuota > 0
    assert cuota_7.saldo_final == Decimal("28500.00")

    opcion = tabla[-1]
    assert opcion.es_opcion_compra is True
    assert opcion.cuota == Decimal("28500.00")
    assert opcion.saldo_final == Decimal("0.00")

    suma_amort_rentas = sum((c.amortizacion for c in lineas_normales), Decimal("0.00"))
    suma_amort_total = sum((c.amortizacion for c in tabla), Decimal("0.00"))
    assert suma_amort_rentas == Decimal("200000.00")
    assert suma_amort_total == Decimal("228500.00")


@pytest.mark.parametrize(
    "kwargs,mensaje",
    [
        ({"opcion_compra": Decimal("-1")}, "no puede ser negativa"),
        ({"opcion_compra": Decimal("228500")}, "debe ser menor al monto financiado"),
        ({"periodos_gracia": 7}, "plazo debe ser mayor"),
    ],
)
def test_validaciones_amortizacion(kwargs, mensaje):
    cotizacion = _cotizacion_base(**kwargs)
    with pytest.raises(ValueError, match=mensaje):
        calcular_tabla_amortizacion(cotizacion)


def test_plazo_extremo_con_fecha_no_provoca_year_out_of_range():
    """Evita error críptico tipo 'year 10000 is out of range' en producción."""
    cotizacion = _cotizacion_base(plazo=50_000, fecha_inicio=date(2026, 4, 1))
    with pytest.raises(ValueError, match="excede el máximo permitido"):
        calcular_tabla_amortizacion(cotizacion)


def test_fechas_amortizacion_contrato_tipico():
    cotizacion = _cotizacion_base(fecha_inicio=date(2026, 1, 31))
    tabla = calcular_tabla_amortizacion(cotizacion)
    assert tabla[0].fecha_cuota == date(2026, 2, 28)
    assert tabla[-1].fecha_cuota == date(2026, 9, 30)


def test_normalizar_tasa_porcentaje():
    assert normalizar_tasa_anual(Decimal("12")) == Decimal("0.1200")
    assert normalizar_tasa_anual(Decimal("0.12")) == Decimal("0.1200")


def test_calcular_pago_inicial_porcentaje():
    pie = calcular_pago_inicial(Decimal("1000000"), "PORCENTAJE", Decimal("20"))
    assert pie == Decimal("200000.00")


def test_calcular_monto_financiado_con_pie_y_seguro():
    monto, pie, seguro, otros = calcular_monto_financiado(
        moneda="CLP",
        valor_neto=Decimal("10000000"),
        pago_inicial_tipo="PORCENTAJE",
        pago_inicial_valor=Decimal("10"),
        financia_seguro=True,
        seguro_monto_uf=Decimal("10"),
        otros_montos_pesos=Decimal("150000"),
        uf_valor=Decimal("39000"),
        dolar_valor=None,
    )
    assert pie == Decimal("1000000.00")
    assert seguro == Decimal("390000.00")
    assert otros == Decimal("150000.00")
    assert monto == Decimal("9540000.00")


def test_calcular_monto_financiado_neto_25m_pie_15pct():
    """Caso UI: neto 25.000.000 + pie 15% → financiado 21.250.000."""
    monto, pie, _, _ = calcular_monto_financiado(
        moneda="CLP",
        valor_neto=Decimal("25000000"),
        pago_inicial_tipo="PORCENTAJE",
        pago_inicial_valor=Decimal("15"),
        financia_seguro=False,
        seguro_monto_uf=None,
        otros_montos_pesos=None,
        uf_valor=None,
        dolar_valor=None,
    )
    assert pie == Decimal("3750000.00")
    assert monto == Decimal("21250000.00")


def test_simular_cotizacion_renta_positiva():
    res = simular_cotizacion(
        LeasingSimulacionInput(
            moneda="CLP",
            valor_neto=Decimal("228500"),
            tasa=Decimal("12"),
            plazo=7,
            opcion_compra=Decimal("28500"),
            periodos_gracia=0,
        )
    )
    assert res.monto_financiado == Decimal("228500.00")
    assert res.renta_mensual is not None
    assert res.renta_mensual > 0
    assert res.tea_anual_pct is not None
    assert res.tea_anual_pct > Decimal("12")


def test_calcular_tea_cero():
    assert calcular_tea_anual(Decimal("0")) == Decimal("0.0000")
