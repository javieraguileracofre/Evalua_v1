# tests/test_credito_riesgo_motor.py
# -*- coding: utf-8 -*-
from decimal import Decimal

import pytest

from services.credito_riesgo.decision import nivel_riesgo_desde_categoria
from services.credito_riesgo.evaluacion_financiera import evaluar_financiero
from services.credito_riesgo.evaluacion_cualitativa import evaluar_cualitativo
from services.credito_riesgo.segmentacion import clasificar_segmento
from services.credito_riesgo_motor import evaluar_credito_riesgo


def test_clasificar_pyme_por_ventas():
    res = clasificar_segmento(ventas_anual=500_000_000, numero_trabajadores=10)
    assert res.segmento == "PYME"


def test_clasificar_gran_empresa():
    res = clasificar_segmento(ventas_anual=50_000_000_000, numero_trabajadores=500)
    assert res.segmento == "GRAN_EMPRESA"


def test_evaluar_financiero_dscr_alerta():
    fin = evaluar_financiero(
        segmento="MEDIANA",
        ventas_anual=1_000_000_000,
        ebitda_anual=100_000_000,
        utilidad_neta_anual=50_000_000,
        deuda_total=400_000_000,
        deuda_financiera=300_000_000,
        patrimonio=500_000_000,
        liquidez_corriente=Decimal("1.2"),
        flujo_caja_mensual=5_000_000,
        capital_trabajo=20_000_000,
        gastos_financieros_anual=30_000_000,
        cuota_propuesta=6_000_000,
        mora_max_dias_12m=0,
    )
    assert fin.dscr is not None
    assert float(fin.dscr) < 1.15
    assert any("DSCR" in a for a in fin.alertas)


def test_evaluar_cualitativo_dependencia_clientes():
    cual = evaluar_cualitativo(
        segmento="PYME",
        input_json={},
        concentracion_ingresos_pct=80,
        historial_tributario="AL_DIA",
    )
    assert cual.score_total < Decimal("70")
    assert any("clientes" in a.lower() for a in cual.alertas)


def test_motor_v2_pyme_aprobacion_base():
    r = evaluar_credito_riesgo(
        ingreso_mensual=8_000_000,
        gastos_mensual=3_000_000,
        deuda_cuotas_mensual=500_000,
        cuota_propuesta=800_000,
        monto_solicitado=50_000_000,
        plazo_solicitado=36,
        tipo_persona="JURIDICA",
        sector_actividad="servicios",
        mora_max_dias_12m=0,
        protestos=0,
        castigos=0,
        reprogramaciones=0,
        tipo_contrato=None,
        ventas_anual=600_000_000,
        deuda_total=100_000_000,
        patrimonio=200_000_000,
        liquidez_corriente=Decimal("1.5"),
        flujo_caja_mensual=2_500_000,
        antiguedad_meses_natural=0,
        anios_operacion_empresa=5,
        garantia_valor_liquidacion=60_000_000,
        exposicion_usd_pct=0,
        concentracion_ingresos_pct=30,
        historial_tributario="AL_DIA",
        flujo_evaluacion="PROFUNDO",
        numero_trabajadores=15,
        deuda_financiera=80_000_000,
        gastos_financieros_anual=10_000_000,
        ebitda_anual=80_000_000,
        utilidad_neta_anual=40_000_000,
        capital_trabajo=30_000_000,
        concentracion_proveedores_pct=25,
        score_buro_estado="FAVORABLE",
    )
    assert r.segmento_cliente == "PYME"
    assert r.score_total > 0
    assert r.nivel_riesgo in ("BAJO", "MEDIO", "ALTO", "CRITICO")
    assert r.recomendacion in ("APROBAR", "CONDICIONES", "COMITE", "RECHAZAR", "SOLICITAR_ANTECEDENTES")
    assert r.evaluacion_financiera_json
    assert r.evaluacion_cualitativa_json
    assert isinstance(r.condiciones_sugeridas, list)


def test_motor_solicitar_antecedentes_sin_docs():
    r = evaluar_credito_riesgo(
        ingreso_mensual=5_000_000,
        gastos_mensual=2_000_000,
        deuda_cuotas_mensual=0,
        cuota_propuesta=500_000,
        monto_solicitado=20_000_000,
        plazo_solicitado=24,
        tipo_persona="JURIDICA",
        sector_actividad="retail",
        mora_max_dias_12m=0,
        protestos=0,
        castigos=0,
        reprogramaciones=0,
        tipo_contrato=None,
        ventas_anual=400_000_000,
        deuda_total=50_000_000,
        patrimonio=100_000_000,
        liquidez_corriente=Decimal("1.1"),
        flujo_caja_mensual=1_000_000,
        antiguedad_meses_natural=0,
        anios_operacion_empresa=3,
        garantia_valor_liquidacion=25_000_000,
        exposicion_usd_pct=0,
        concentracion_ingresos_pct=40,
        historial_tributario="SIN_INFO",
        documentos_pendientes=["CARPETA_TRIBUTARIA", "IVA_F29", "BALANCE"],
    )
    assert r.recomendacion == "SOLICITAR_ANTECEDENTES"


@pytest.mark.parametrize(
    "cat,expected",
    [("A", "BAJO"), ("C", "MEDIO"), ("D", "ALTO"), ("E", "CRITICO")],
)
def test_nivel_riesgo(cat, expected):
    assert nivel_riesgo_desde_categoria(cat) == expected
