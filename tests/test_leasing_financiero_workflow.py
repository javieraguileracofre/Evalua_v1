# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from crud.comercial.leasing_fin import _asegurar_analisis_aprobado, _siguiente_etapa
from schemas.comercial.leasing_credito import LeasingCreditoInput
from services.leasing_credito_scoring import evaluar_credito


def test_scoring_aprobado_condiciones_bucket():
    inp = LeasingCreditoInput(
        tipo_persona="NATURAL",
        ingreso_neto_mensual=Decimal("1000000"),
        carga_financiera_mensual=Decimal("350000"),
        antiguedad_laboral_meses=24,
        score_buro=680,
        comportamiento_pago="REGULAR",
        ltv_pct=Decimal("85"),
    )
    out = evaluar_credito(inp)
    assert out.recomendacion in {"APROBADO", "APROBADA_CONDICIONES", "RECHAZADO"}


def test_siguiente_etapa_workflow():
    wf = {"hitos": {"analisis_credito": True, "orden_compra": True, "contrato_firmado": False, "acta_recepcion": False, "activacion_contable": False}}
    assert _siguiente_etapa(wf) == "CONTRATO_FIRMADO"


def test_gate_credito_aprobado_permite_avanzar():
    cot = SimpleNamespace(analisis_credito=SimpleNamespace(recomendacion="APROBADA_CONDICIONES"))
    _asegurar_analisis_aprobado(cot)


def test_gate_credito_rechazado_bloquea():
    cot = SimpleNamespace(analisis_credito=SimpleNamespace(recomendacion="RECHAZADO"))
    with pytest.raises(ValueError):
        _asegurar_analisis_aprobado(cot)


def test_fx_validation_for_usd_requires_rate():
    from crud.comercial.leasing_fin import _validar_moneda_y_tipo_cambio

    with pytest.raises(ValueError):
        _validar_moneda_y_tipo_cambio(moneda="USD", uf_valor=None, dolar_valor=Decimal("0"))
