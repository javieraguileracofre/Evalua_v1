# tests/test_fondos_rendir_domain.py
# -*- coding: utf-8 -*-
"""Lógica de negocio de fondos por rendir (JSON de gastos, RUT, totales)."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from crud import fondos_rendir as fr


def test_parse_gastos_json_vacio() -> None:
    assert fr.parse_gastos_json(None) == []
    assert fr.parse_gastos_json("   ") == []


def test_parse_gastos_json_invalido() -> None:
    with pytest.raises(ValueError, match="JSON"):
        fr.parse_gastos_json("{no-json")


def test_parse_gastos_json_lista_valida() -> None:
    raw = (
        '[{"fecha_gasto":"2024-06-01T10:00","rubro":"Combustible",'
        '"descripcion":"Full","monto":"12.5","nro_documento":"1"}]'
    )
    rows = fr.parse_gastos_json(raw)
    assert len(rows) == 1
    assert rows[0]["rubro"] == "Combustible"
    assert rows[0]["monto"] == Decimal("12.50")
    assert rows[0]["nro_documento"] == "1"


def test_parse_gastos_json_no_es_lista() -> None:
    with pytest.raises(ValueError, match="lista"):
        fr.parse_gastos_json('{"a":1}')


def test_normalizar_rut() -> None:
    assert fr.normalizar_rut(" 12.345.678-9 ") == "12345678-9"


@pytest.mark.parametrize(
    "rut,ok",
    [
        ("12345678-9", True),
        ("1234567-K", True),
        ("1234567-k", True),
        ("sin-guion", False),
        ("12-3", False),
        ("", False),
    ],
)
def test_rut_valido_basico(rut: str, ok: bool) -> None:
    assert fr.rut_valido_basico(rut) is ok


def test_total_gastos_orm() -> None:
    lineas = [
        SimpleNamespace(monto=Decimal("10.00")),
        SimpleNamespace(monto="5,25"),
    ]
    assert fr.total_gastos_orm(lineas) == Decimal("15.25")


def test_parse_fecha_formulario_iso() -> None:
    dt = fr.parse_fecha_formulario("2024-03-15T08:30")
    assert dt is not None
    assert dt.year == 2024 and dt.month == 3 and dt.day == 15
