# tests/test_credito_cobranzas_module.py
# -*- coding: utf-8 -*-
"""Fase 1: módulo Crédito y cobranzas (catálogo, hub, guards)."""
from __future__ import annotations

from unittest.mock import MagicMock

from core.module_catalog import (
    MODULE_LABELS,
    NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS,
    SUBMODULE_PARENT,
    module_label,
)
from core.rbac import (
    guard_cobranza_consulta,
    guard_credito_cobranzas_hub,
    guard_credito_riesgo_consulta,
)


def _request(auth: dict | None) -> MagicMock:
    req = MagicMock()
    req.state.auth_user = auth
    req.url.path = "/credito-cobranzas"
    return req


def test_catalogo_credito_cobranzas() -> None:
    assert MODULE_LABELS["CREDITO_COBRANZAS"] == "Crédito y cobranzas"
    assert module_label("COBRANZA") == "Cobranza"
    assert SUBMODULE_PARENT["CREDITO_RIESGO"] == "CREDITO_COBRANZAS"
    assert SUBMODULE_PARENT["COBRANZA"] == "CREDITO_COBRANZAS"
    assert "CREDITO_RIESGO" in NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS
    assert "COBRANZA" in NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS


def test_hub_guard_permite_area() -> None:
    auth = {"roles": ["FINANZAS"], "visibleModules": ["PRINCIPAL", "CREDITO_COBRANZAS"]}
    assert guard_credito_cobranzas_hub(_request(auth)) is None


def test_hub_guard_permite_solo_cobranza_legacy_finanzas() -> None:
    auth = {"roles": ["FINANZAS"], "visibleModules": ["PRINCIPAL", "FINANZAS"]}
    assert guard_credito_cobranzas_hub(_request(auth)) is None


def test_credito_guard_no_abre_con_solo_cobranza() -> None:
    auth = {
        "roles": ["FINANZAS"],
        "visibleModules": ["PRINCIPAL", "CREDITO_COBRANZAS", "COBRANZA"],
    }
    assert guard_credito_riesgo_consulta(_request(auth)) is not None
    assert guard_cobranza_consulta(_request(auth)) is None


def test_cobranza_guard_no_abre_con_solo_credito() -> None:
    auth = {
        "roles": ["FINANZAS"],
        "visibleModules": ["PRINCIPAL", "CREDITO_COBRANZAS", "CREDITO_RIESGO"],
    }
    assert guard_cobranza_consulta(_request(auth)) is not None
    assert guard_credito_riesgo_consulta(_request(auth)) is None
