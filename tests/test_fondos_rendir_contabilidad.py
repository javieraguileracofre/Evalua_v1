# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from crud import fondos_rendir_contabilidad as cont


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        return _FakeResult(self._rows)


def test_normalizar_codigo_equivalente() -> None:
    assert cont._normalizar_codigo("11.05") == "1105"
    assert cont._normalizar_codigo("1.1.05") == "1105"
    assert cont._normalizar_codigo(" 1-1/05 ") == "1105"


def test_buscar_cuenta_tolerante_usa_match_exacto(monkeypatch) -> None:
    exacta = SimpleNamespace(codigo="11.05", estado="ACTIVO", acepta_movimiento=True)
    monkeypatch.setattr(cont, "obtener_plan_cuenta_por_codigo", lambda _db, _c: exacta)
    db = _FakeSession(rows=[])
    got = cont._buscar_cuenta_por_codigo_tolerante(db, "11.05")
    assert got is exacta


def test_buscar_cuenta_tolerante_acepta_formato_alterno(monkeypatch) -> None:
    monkeypatch.setattr(cont, "obtener_plan_cuenta_por_codigo", lambda _db, _c: None)
    cuenta = SimpleNamespace(codigo="1.1.05", estado="ACTIVO", acepta_movimiento=True)
    db = _FakeSession(rows=[cuenta])
    got = cont._buscar_cuenta_por_codigo_tolerante(db, "11.05")
    assert got is cuenta
