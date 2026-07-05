# -*- coding: utf-8 -*-
"""Tests premium: métricas, tributario, permisos y validaciones LF."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from core.rbac import (
    guard_leasing_fin_aprobar,
    guard_leasing_fin_consulta,
    usuario_puede_aprobar_leasing_financiero,
)
from schemas.comercial.leasing_cotizacion import LeasingSimulacionInput
from services import leasing_financiero
from services.leasing_financiero_metricas import calcular_cae_tir_operacion, calcular_tir_periodica
from services.leasing_financiero_tributario import calcular_desglose_tributario


from routes.ui import leasing_financiero as lf_routes


def test_rutas_api_lf_registradas_con_nombre():
    names = {getattr(r, "name", None) for r in lf_routes.router.routes}
    assert "api_lf_rates_today" in names
    assert "api_lf_cotizacion_simular" in names
    assert "lf_cotizacion_nueva_form" in names


def test_tabla_amortizacion_cierra_en_residual():
    cot = SimpleNamespace(
        plazo=12,
        monto_financiado=Decimal("1000000"),
        valor_neto=None,
        monto=None,
        tasa=Decimal("0.12"),
        periodos_gracia=0,
        periodicidad="MENSUAL",
        opcion_compra=Decimal("100000"),
        fecha_inicio=None,
        fecha_primera_cuota=None,
    )
    tabla = leasing_financiero.calcular_tabla_amortizacion(cot)
    assert tabla[-1].saldo_final == Decimal("0.00")
    assert tabla[-2].saldo_final == Decimal("100000.00")
    suma_amort = sum((c.amortizacion for c in tabla), Decimal("0"))
    assert suma_amort == Decimal("1000000.00")


def test_plazo_incompatible_periodicidad():
    cot = SimpleNamespace(
        plazo=37,
        monto_financiado=Decimal("100000"),
        valor_neto=None,
        monto=None,
        tasa=Decimal("0.1"),
        periodos_gracia=0,
        periodicidad="TRIMESTRAL",
        opcion_compra=Decimal("0"),
        fecha_inicio=None,
        fecha_primera_cuota=None,
    )
    with pytest.raises(ValueError, match="múltiplo"):
        leasing_financiero.calcular_tabla_amortizacion(cot)


def test_simular_incluye_cae_y_tributario():
    inp = LeasingSimulacionInput(
        valor_neto=Decimal("10000000"),
        tasa=Decimal("12"),
        plazo=36,
        opcion_compra=Decimal("1000000"),
        iva_aplica=True,
        iva_tasa=Decimal("19"),
    )
    res = leasing_financiero.simular_cotizacion(inp)
    assert res.monto_financiado > 0
    assert res.renta_mensual is not None
    assert res.cae_anual_pct is not None
    assert res.desglose_tributario.get("iva_monto", 0) > 0


def test_desglose_iva_recuperable():
    d = calcular_desglose_tributario(
        valor_neto=Decimal("1000000"),
        iva_aplica=True,
        iva_tasa=Decimal("19"),
        iva_recuperable=True,
    )
    assert d.iva_monto == Decimal("190000.00")
    assert d.iva_credito_estimado == Decimal("190000.00")


def test_comision_financiada_incrementa_monto():
    monto, _, _, _ = leasing_financiero.calcular_monto_financiado(
        moneda="CLP",
        valor_neto=Decimal("1000000"),
        pago_inicial_tipo="PORCENTAJE",
        pago_inicial_valor=Decimal("10"),
        financia_seguro=False,
        seguro_monto_uf=None,
        otros_montos_pesos=None,
        uf_valor=None,
        dolar_valor=None,
        comision_apertura_tipo="PORCENTAJE",
        comision_apertura=Decimal("2"),
        financia_comision=True,
        gastos_operacionales=Decimal("50000"),
    )
    assert monto == Decimal("970000.00")


def test_tir_periodica_basica():
    flujos = [Decimal("100"), Decimal("-30"), Decimal("-30"), Decimal("-30"), Decimal("-30")]
    tir = calcular_tir_periodica(flujos)
    assert tir is not None
    assert tir > Decimal("0")


def test_estados_lf_incluyen_flujo_comercial():
    from schemas.comercial.leasing_cotizacion import ESTADOS_LF

    assert "BORRADOR" in ESTADOS_LF
    assert "ACTIVADA" in ESTADOS_LF
    assert "ANULADA" in ESTADOS_LF


def test_permiso_aprobar_solo_finanzas():
    assert usuario_puede_aprobar_leasing_financiero({"roles": ["FINANZAS"]})
    assert not usuario_puede_aprobar_leasing_financiero({"roles": ["OPERACIONES"]})
    assert usuario_puede_aprobar_leasing_financiero({"roles": ["ADMIN"]})


def test_guard_leasing_modulo_no_visible():
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    req = Request(scope)
    req.state.auth_user = {"roles": ["RRHH"], "visibleModules": ["RRHH", "PRINCIPAL"]}
    redir = guard_leasing_fin_consulta(req)
    assert redir is not None
    assert redir.status_code == 303


def test_guard_aprobar_bloquea_operaciones():
    from starlette.requests import Request

    scope = {"type": "http", "method": "POST", "path": "/", "headers": []}
    req = Request(scope)
    req.state.auth_user = {"roles": ["OPERACIONES"], "visibleModules": ["COMERCIAL", "PRINCIPAL"]}
    redir = guard_leasing_fin_aprobar(req)
    assert redir is not None
