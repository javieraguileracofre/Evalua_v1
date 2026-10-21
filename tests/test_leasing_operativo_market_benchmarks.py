# tests/test_leasing_operativo_market_benchmarks.py
# -*- coding: utf-8 -*-
from decimal import Decimal
from types import SimpleNamespace

from services.leasing_operativo.market_benchmarks import (
    comparar_tipo_con_mercado,
    sugerencia_mercado,
)


def test_sugerencia_camioneta_mercado_cl():
    sug = sugerencia_mercado(codigo="CAMIONETA")
    assert sug is not None
    assert sug["params"]["residual_base_pct"] == Decimal("22")
    assert sug["plazo_ref_meses"] == 36
    assert sug["fuentes"]


def test_match_por_nombre():
    sug = sugerencia_mercado(codigo="X", nombre="Camioneta liviana faena")
    assert sug and sug["codigo_benchmark"] == "CAMIONETA"


def test_sugerencias_flota_nueva():
    assert sugerencia_mercado(codigo="VEHICULO_LIVIANO")["params"]["residual_base_pct"] == Decimal("20")
    assert sugerencia_mercado(codigo="VEHICULO_GERENCIAL")["km_anual_tipico"] == 18000
    assert sugerencia_mercado(codigo="GRUA")["params"]["desgaste_hora_factor"] == Decimal("0.00075")
    assert sugerencia_mercado(nombre="Peugeot Partner furgón")["codigo_benchmark"] == "FURGON"


def test_comparar_detecta_desvio():
    tipo = SimpleNamespace(
        codigo="EQUIPO_IT",
        nombre="Equipos TI",
        sector="TECNOLOGIA",
        residual_base_pct=Decimal("20"),
        residual_max_pct=Decimal("25"),
        haircut_residual_pct=Decimal("10"),
        liquidez_factor=Decimal("0.92"),
        obsolescencia_factor=Decimal("1.15"),
        desgaste_km_factor=Decimal("0"),
        desgaste_hora_factor=Decimal("0.0001"),
    )
    cmp = comparar_tipo_con_mercado(tipo)
    assert cmp["tiene_sugerencia"]
    assert not cmp["alineado"]
    assert cmp["diffs_by_key"]["residual_base_pct"]["sugerido"] == Decimal("8")
