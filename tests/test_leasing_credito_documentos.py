# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal

from schemas.comercial.leasing_credito import LeasingCreditoInput
from services.leasing_credito_documentos import parse_documento
from services.leasing_credito_scoring import calcular_ratios, evaluar_credito


def test_ratios_juridica_desde_balance_e_iva():
    inp = LeasingCreditoInput(
        tipo_persona="JURIDICA",
        ventas_anuales=Decimal("120000000"),
        ventas_12m_iva=Decimal("118000000"),
        ebitda_anual=Decimal("18000000"),
        deuda_financiera_total=Decimal("40000000"),
        patrimonio=Decimal("50000000"),
        activo_corriente=Decimal("30000000"),
        pasivo_corriente=Decimal("20000000"),
        pasivo_total=Decimal("45000000"),
        utilidad_neta_anual=Decimal("9000000"),
        gastos_financieros_anual=Decimal("3000000"),
        anios_operacion=6,
        comportamiento_pago="BUENO",
        ltv_pct=Decimal("75"),
        score_buro=720,
    )
    ratios = calcular_ratios(inp)
    assert ratios.dscr is not None and ratios.dscr > 0
    assert ratios.liquidez_corriente == Decimal("1.5000")
    assert ratios.margen_ebitda_pct is not None
    assert ratios.capital_trabajo == Decimal("10000000.00")

    out = evaluar_credito(inp)
    assert out.recomendacion in {"APROBADO", "APROBADA_CONDICIONES", "RECHAZADO"}
    assert out.liquidez_corriente is not None
    assert "dscr" in (out.ratios_json or {})


def test_parse_csv_certificado_iva():
    csv_bytes = (
        "periodo;iva_debito;iva_credito;ventas\n"
        "2025-01;1900000;800000;10000000\n"
        "2025-02;2090000;900000;11000000\n"
    ).encode("utf-8")
    ext = parse_documento(csv_bytes, "ivas.csv", "CERTIFICADO_IVA")
    assert "ventas_anuales" in ext.campos
    assert ext.campos["ventas_anuales"] == Decimal("21000000.00")
    assert ext.campos["iva_debito_12m"] == Decimal("3990000.00")


def test_parse_balance_etiqueta_valor_csv():
    csv_bytes = (
        "concepto;monto\n"
        "Activo corriente;25000000\n"
        "Pasivo corriente;15000000\n"
        "Patrimonio;40000000\n"
        "Deuda financiera;18000000\n"
        "EBITDA;8000000\n"
    ).encode("utf-8")
    ext = parse_documento(csv_bytes, "balance.csv", "BALANCE_GENERAL")
    assert ext.campos["activo_corriente"] == Decimal("25000000.00")
    assert ext.campos["patrimonio"] == Decimal("40000000.00")
    assert ext.campos["deuda_financiera_total"] == Decimal("18000000.00")
