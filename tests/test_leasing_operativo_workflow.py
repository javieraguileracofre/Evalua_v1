# -*- coding: utf-8 -*-
from __future__ import annotations

from crud.leasing_operativo.crud import _parse_date_iso, _recompute_stage


def test_recompute_stage_prioritizes_activation():
    wf = {
        "hitos": {
            "contrato_confeccionado": True,
            "orden_compra_proveedor": True,
            "acta_entrega_recepcion": True,
            "factura_compra_recepcion": True,
            "activacion_contable": True,
        },
        "credito": {"dictamen": "APROBAR"},
    }
    assert _recompute_stage(wf) == "ACTIVADO_CONTABLE"


def test_recompute_stage_credit_rejected_when_no_hitos():
    wf = {"hitos": {}, "credito": {"dictamen": "RECHAZAR"}}
    assert _recompute_stage(wf) == "CREDITO_RECHAZADO"


def test_parse_date_iso_fallback_is_valid_date():
    d = _parse_date_iso("not-a-date")
    assert d.year >= 2000
