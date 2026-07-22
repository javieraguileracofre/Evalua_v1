# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from schemas.comercial.leasing_cotizacion import LeasingSimulacionInput
from services.leasing_financiero import calcular_monto_financiado, simular_cotizacion
from services.leasing_financiero_cotizacion_pdf import build_cotizador_pdf


def test_gps_y_gastos_admin_financiados_suman_al_monto():
    monto, pie, _, _, gps, admin = calcular_monto_financiado(
        moneda="CLP",
        valor_neto=Decimal("10000000"),
        pago_inicial_tipo="PORCENTAJE",
        pago_inicial_valor=Decimal("10"),
        financia_seguro=False,
        seguro_monto_uf=None,
        otros_montos_pesos=None,
        uf_valor=None,
        dolar_valor=None,
        gps_monto=Decimal("200000"),
        financia_gps=True,
        gastos_administrativos=Decimal("150000"),
        financia_gastos_admin=True,
    )
    assert pie == Decimal("1000000.00")
    assert gps == Decimal("200000.00")
    assert admin == Decimal("150000.00")
    assert monto == Decimal("9350000.00")


def test_gps_al_contado_no_entra_en_financiamiento():
    monto, _, _, _, gps, admin = calcular_monto_financiado(
        moneda="CLP",
        valor_neto=Decimal("10000000"),
        pago_inicial_tipo="MONTO",
        pago_inicial_valor=Decimal("0"),
        financia_seguro=False,
        seguro_monto_uf=None,
        otros_montos_pesos=None,
        uf_valor=None,
        dolar_valor=None,
        gps_monto=Decimal("200000"),
        financia_gps=False,
        gastos_administrativos=Decimal("150000"),
        financia_gastos_admin=False,
    )
    assert gps == Decimal("0.00")
    assert admin == Decimal("0.00")
    assert monto == Decimal("10000000.00")


def test_simular_incluye_gps_financiado():
    res = simular_cotizacion(
        LeasingSimulacionInput(
            moneda="CLP",
            valor_neto=Decimal("12000000"),
            pago_inicial_tipo="PORCENTAJE",
            pago_inicial_valor=Decimal("20"),
            tasa=Decimal("0.12"),
            plazo=36,
            gps_monto=Decimal("100000"),
            financia_gps=True,
            gastos_administrativos=Decimal("50000"),
            financia_gastos_admin=True,
        )
    )
    assert res.gps_financiado == Decimal("100000.00")
    assert res.gastos_admin_financiados == Decimal("50000.00")
    assert res.monto_financiado == Decimal("9750000.00")


def test_pdf_cotizador_genera_bytes():
    cot = SimpleNamespace(
        id=99,
        estado="COTIZADA",
        moneda="CLP",
        bien_descripcion="Camión demo",
        ejecutivo="Ana",
        fecha_cotizacion="2026-07-21",
        valor_neto=Decimal("10000000"),
        plazo=36,
        periodicidad="MENSUAL",
        tasa=Decimal("0.12"),
        cliente=SimpleNamespace(razon_social="Cliente Demo SpA", rut="76.123.456-7"),
        condiciones_aceptadas="",
    )
    res = simular_cotizacion(
        LeasingSimulacionInput(
            moneda="CLP",
            valor_neto=Decimal("10000000"),
            tasa=Decimal("0.12"),
            plazo=36,
            pago_inicial_tipo="PORCENTAJE",
            pago_inicial_valor=Decimal("10"),
        )
    )
    pdf = build_cotizador_pdf(cotizacion=cot, resumen=res, tabla=[], condiciones="Condiciones de prueba")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500
