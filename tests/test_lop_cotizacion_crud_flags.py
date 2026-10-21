# -*- coding: utf-8 -*-
"""Flags de edición/eliminación de cotizaciones LOP."""
from __future__ import annotations

from types import SimpleNamespace

from crud.leasing_operativo import crud as lo_crud


def _sim(*, etapa: str = "COTIZACION", contrato=None, hitos=None):
    wf = {
        "etapa_actual": etapa,
        "hitos": hitos
        or {
            "contrato_confeccionado": False,
            "activacion_contable": False,
        },
    }
    return SimpleNamespace(result_json={"workflow_v1": wf}, contrato=contrato)


def test_puede_editar_en_cotizacion():
    assert lo_crud.puede_editar_simulacion(_sim()) is True
    assert lo_crud.puede_eliminar_simulacion(_sim()) is True


def test_bloquea_con_contrato():
    sim = _sim(contrato=object())
    assert lo_crud.puede_editar_simulacion(sim) is False
    assert lo_crud.puede_eliminar_simulacion(sim) is False


def test_bloquea_etapa_formalizacion():
    sim = _sim(etapa="ACTIVADO_CONTABLE")
    assert lo_crud.puede_editar_simulacion(sim) is False
    assert lo_crud.puede_eliminar_simulacion(sim) is False


def test_etiqueta_etapa():
    assert lo_crud.etiqueta_etapa("COTIZACION") == "Cotización"
    assert lo_crud.etiqueta_etapa("CREDITO_EN_EVALUACION") == "En crédito"
