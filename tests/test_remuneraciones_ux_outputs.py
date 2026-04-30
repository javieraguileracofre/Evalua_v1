# tests/test_remuneraciones_ux_outputs.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal

from crud.remuneraciones import totales_libro
from services.remuneraciones.liquidacion_pdf import generar_liquidacion_pdf_bytes


def test_totales_libro_agrega_columnas_clave() -> None:
    rows = [
        {
            "haberes_imponibles": Decimal("1000"),
            "haberes_no_imponibles": Decimal("200"),
            "descuentos_legales": Decimal("100"),
            "otros_descuentos": Decimal("30"),
            "liquido": Decimal("1070"),
        },
        {
            "haberes_imponibles": Decimal("500"),
            "haberes_no_imponibles": Decimal("50"),
            "descuentos_legales": Decimal("20"),
            "otros_descuentos": Decimal("10"),
            "liquido": Decimal("520"),
        },
    ]
    t = totales_libro(rows)
    assert t["haberes_imponibles"] == Decimal("1500")
    assert t["haberes_no_imponibles"] == Decimal("250")
    assert t["descuentos_legales"] == Decimal("120")
    assert t["otros_descuentos"] == Decimal("40")
    assert t["liquido"] == Decimal("1590")


def test_liquidacion_pdf_bytes_valido() -> None:
    data = generar_liquidacion_pdf_bytes(
        periodo_label="04/2026",
        empleado_nombre="Juan Perez",
        empleado_cargo="Conductor",
        detalle_resumen={
            "hab_imp": Decimal("1200000"),
            "hab_no": Decimal("50000"),
            "des_leg": Decimal("130000"),
            "des_otr": Decimal("25000"),
            "liquido": Decimal("1095000"),
        },
        items_rows=[
            {
                "concepto": "SUELDO_BASE",
                "origen": "contrato",
                "cantidad": Decimal("1"),
                "valor_unitario": Decimal("1200000"),
                "monto_total": Decimal("1200000"),
            }
        ],
    )
    assert isinstance(data, bytes)
    assert len(data) > 200
    assert data.startswith(b"%PDF")
