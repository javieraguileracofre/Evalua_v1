# tests/test_finanzas_rbac.py
# -*- coding: utf-8 -*-
"""Regresiones en autorización de módulos financieros (sin HTTP)."""
from __future__ import annotations

import pytest

from core.rbac import (
    usuario_es_admin,
    usuario_puede_consultar_modulos_finanzas,
    usuario_puede_mutar_modulos_finanzas,
    usuario_tiene_rol,
)


@pytest.mark.parametrize(
    "roles,es_admin,fin_mut,fin_cons",
    [
        ([], False, False, False),
        (["OPERACIONES"], False, False, False),
        (["CONSULTA"], False, False, True),
        (["FINANZAS"], False, True, True),
        (["ADMIN"], True, True, True),
        (["FINANZAS", "CONSULTA"], False, True, True),
    ],
)
def test_matriz_roles_finanzas(
    roles: list[str],
    es_admin: bool,
    fin_mut: bool,
    fin_cons: bool,
) -> None:
    auth = {"roles": roles}
    assert usuario_es_admin(auth) is es_admin
    assert usuario_puede_mutar_modulos_finanzas(auth) is fin_mut
    assert usuario_puede_consultar_modulos_finanzas(auth) is fin_cons


def test_usuario_tiene_rol_normaliza_vacio() -> None:
    assert usuario_tiene_rol({"roles": ["FINANZAS"]}, "FINANZAS") is True
    assert usuario_tiene_rol({"roles": ["finanzas"]}, "FINANZAS") is False
    assert usuario_tiene_rol(None, "ADMIN") is False
    assert usuario_tiene_rol({"roles": "no-lista"}, "ADMIN") is False
