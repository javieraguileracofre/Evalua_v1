# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from services import leasing_financiero
from services import leasing_financiero_contabilidad as contab


class _NoExistingAsiento:
    def first(self):
        return None


class _FakeDb:
    def execute(self, *args, **kwargs):
        return _NoExistingAsiento()


def _cotizacion(**kwargs):
    base = {
        "id": 11,
        "monto_financiado": Decimal("228500"),
        "valor_neto": None,
        "monto": None,
        "tasa": Decimal("0.12"),
        "plazo": 7,
        "periodos_gracia": 0,
        "opcion_compra": Decimal("28500"),
        "fecha_inicio": date(2026, 3, 5),
        "fecha_cotizacion": date(2026, 3, 5),
        "moneda": "CLP",
        "dolar_valor": None,
        "uf_valor": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_activacion_contable_reconoce_cartera_contractual_bruta(monkeypatch):
    cotizacion = _cotizacion()
    tabla = leasing_financiero.calcular_tabla_amortizacion(cotizacion)
    cartera = sum((c.cuota for c in tabla), Decimal("0.00"))
    interes_diferido = cartera - Decimal("228500.00")

    captured = {}

    def fake_crear_asiento(db, **kwargs):
        captured.update(kwargs)
        return 987

    monkeypatch.setattr(contab, "crear_asiento", fake_crear_asiento)
    monkeypatch.setattr(contab, "obtener_configuracion_evento_modulo", lambda *args, **kwargs: [])

    asiento_id = contab.activar_contabilidad_leasing_financiero(_FakeDb(), cotizacion, usuario="tester")

    assert asiento_id == 987
    assert captured["do_commit"] is False
    detalles = captured["detalles"]

    assert detalles[0]["codigo_cuenta"] == "113701"
    assert detalles[0]["debe"] == cartera
    assert detalles[1]["codigo_cuenta"] == "210701"
    assert detalles[1]["haber"] == Decimal("228500.00")
    assert detalles[2]["codigo_cuenta"] == "210702"
    assert detalles[2]["haber"] == interes_diferido
    assert interes_diferido > 0
    assert sum((d["debe"] for d in detalles), Decimal("0.00")) == sum(
        (d["haber"] for d in detalles),
        Decimal("0.00"),
    )


def test_activacion_contable_sin_interes_no_crea_interes_diferido(monkeypatch):
    cotizacion = _cotizacion(tasa=Decimal("0"))
    tabla = leasing_financiero.calcular_tabla_amortizacion(cotizacion)
    cartera = sum((c.cuota for c in tabla), Decimal("0.00"))

    captured = {}

    def fake_crear_asiento(db, **kwargs):
        captured.update(kwargs)
        return 988

    monkeypatch.setattr(contab, "crear_asiento", fake_crear_asiento)
    monkeypatch.setattr(contab, "obtener_configuracion_evento_modulo", lambda *args, **kwargs: [])

    contab.activar_contabilidad_leasing_financiero(_FakeDb(), cotizacion, usuario="tester")

    detalles = captured["detalles"]
    assert cartera == Decimal("228500.00")
    assert len(detalles) == 2
    assert detalles[0]["debe"] == Decimal("228500.00")
    assert detalles[1]["haber"] == Decimal("228500.00")
