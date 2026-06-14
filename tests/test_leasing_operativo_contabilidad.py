# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal

from services.leasing_operativo.cronograma import (
    calcular_monto_cuota_indexada,
    generar_cronograma_cuotas,
    resumen_cronograma,
)
from services.leasing_operativo_contabilidad import resolver_monto_regla_evento


def test_ipc_indexacion_compuesta():
    base = Decimal("1000000")
    m3 = calcular_monto_cuota_indexada(nro=3, renta_base=base, indexacion_tipo="IPC", indexacion_pct=Decimal("0.5"))
    assert m3 > base
    assert m3 == Decimal("1010025.0000")


def test_uf_indexacion_anual():
    base = Decimal("1000000")
    m12 = calcular_monto_cuota_indexada(nro=12, renta_base=base, indexacion_tipo="UF", indexacion_pct=Decimal("3"))
    assert m12 == base
    m13 = calcular_monto_cuota_indexada(nro=13, renta_base=base, indexacion_tipo="UF", indexacion_pct=Decimal("3"))
    assert m13 == Decimal("1030000.0000")


def test_cronograma_genera_plazo_correcto():
    from datetime import date

    rows = generar_cronograma_cuotas(
        plazo_meses=24,
        renta_base=Decimal("500000"),
        fecha_inicio=date(2026, 1, 15),
        indexacion_tipo="IPC",
        indexacion_pct=Decimal("0.3"),
    )
    assert len(rows) == 24
    assert rows[0]["nro"] == 1
    assert rows[-1]["monto_renta"] >= rows[0]["monto_renta"]
    res = resumen_cronograma(rows)
    assert res["cuotas"] == 24
    assert res["total_renta"] > Decimal("500000") * 24


def test_regla_facturacion_cxc_bruto():
    regla = {"lado": "DEBE", "tipo": "ACTIVO", "nombre_cuenta": "Clientes LOP"}
    monto = resolver_monto_regla_evento(
        codigo_evento="LOP_FACTURACION",
        regla=regla,
        monto_base=Decimal("100"),
        monto_iva=Decimal("19"),
    )
    assert monto == Decimal("119.00")
