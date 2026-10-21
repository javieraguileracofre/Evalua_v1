# -*- coding: utf-8 -*-
from services.leasing_operativo.politicas_ui import (
    build_politica_cards,
    build_summary,
    defaults_for,
    parse_form_valor,
)


class _Form(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def test_parse_motor_decision_fields():
    form = _Form(
        {
            "edit_mode": "fields",
            "van_minimo": "0",
            "tir_minima_anual_pct": "12.5",
            "margen_op_minimo_pct": "6",
            "ltv_max_pct": "90",
        }
    )
    out = parse_form_valor("motor_decision_v1", form)
    assert out["tir_minima_anual_pct"] == 12.5
    assert out["ltv_max_pct"] == 90.0
    assert out["van_minimo"] == 0


def test_parse_escenarios():
    form = _Form({"edit_mode": "fields"})
    for esc in ("CONSERVADOR", "BASE", "OPTIMISTA", "ESTRES"):
        for mk in ("residual_mult", "costo_mult", "riesgo_mult", "tasa_fondo_mult"):
            form[f"esc_{esc}_{mk}"] = "1" if esc == "BASE" else "1,05"
    out = parse_form_valor("escenarios_v1", form)
    assert out["BASE"]["residual_mult"] == 1.0
    assert out["OPTIMISTA"]["costo_mult"] == 1.05


def test_parse_json_mode():
    form = _Form({"edit_mode": "json", "valor_json": '{"dias_gracia": 7, "generar_cxc_mora": true}'})
    out = parse_form_valor("mora_v1", form)
    assert out["dias_gracia"] == 7
    assert out["generar_cxc_mora"] is True


def test_build_cards_and_summary():
    class Row:
        def __init__(self, clave, valor, activo=True):
            self.clave = clave
            self.valor_json = valor
            self.descripcion = "x"
            self.activo = activo
            self.updated_at = None

    rows = [
        Row("motor_decision_v1", defaults_for("motor_decision_v1")),
        Row("mora_v1", {**defaults_for("mora_v1"), "dias_gracia": 10}),
    ]
    cards = build_politica_cards(rows)
    assert any(c["clave"] == "motor_decision_v1" and c["alineado_default"] for c in cards)
    assert any(c["clave"] == "mora_v1" and not c["alineado_default"] for c in cards)
    summary = build_summary({r.clave: r.valor_json for r in rows})
    assert any(s["clave"] == "mora_v1" and s["value"] == "10" for s in summary)
