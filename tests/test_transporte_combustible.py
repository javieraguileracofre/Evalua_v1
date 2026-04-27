# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from crud import transporte_viajes as tv


def _v(*, km_ini: int, km_fin: int, litros: str, ref_l100: str):
    veh = SimpleNamespace(consumo_referencial_l100km=Decimal(ref_l100), patente="AA")
    emp = SimpleNamespace(nombre_completo="Chofer")
    return SimpleNamespace(
        id=1,
        folio="HR-1",
        odometro_inicio=km_ini,
        odometro_fin=km_fin,
        litros_combustible=Decimal(litros),
        vehiculo=veh,
        vehiculo_transporte_id=1,
        empleado=emp,
        empleado_id=1,
        origen="A",
        destino="B",
    )


def test_unidades_consumo_l100_y_kml_consistentes() -> None:
    v = _v(km_ini=1000, km_fin=1200, litros="50", ref_l100="20")
    l100 = tv.litros_100km(v)
    assert l100 == Decimal("25")
    assert tv.rendimiento_km_l_desde_l100(float(l100)) == 4.0


def test_desvio_consumo_pct_compara_l100_con_l100() -> None:
    v = _v(km_ini=0, km_fin=100, litros="30", ref_l100="20")
    # real=30 L/100, ref=20 L/100 => +50%
    assert tv.desvio_consumo_pct(v) == 50.0

