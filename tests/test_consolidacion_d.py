# -*- coding: utf-8 -*-
"""Ola D: libro interno, conciliación, diferencia de cambio, costeo y API."""
from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_costo_promedio_entrada_y_salida():
    from services.inventario.costeo import aplicar_costo_promedio, salida_requiere_asiento

    costo, promedio = aplicar_costo_promedio(
        stock=Decimal("10"),
        promedio=Decimal("100"),
        precio_compra=Decimal("80"),
        tipo="ENTRADA",
        cantidad=Decimal("10"),
        costo_entrada=Decimal("200"),
    )
    assert promedio == Decimal("150.0000")
    assert costo == Decimal("200.0000")

    costo_salida, promedio_salida = aplicar_costo_promedio(
        stock=Decimal("20"),
        promedio=promedio,
        precio_compra=Decimal("80"),
        tipo="SALIDA",
        cantidad=Decimal("4"),
        costo_entrada=Decimal("0"),
    )
    assert costo_salida == Decimal("150.0000")
    assert promedio_salida == Decimal("150.0000")
    assert salida_requiere_asiento("SALIDA", "AJUSTE_MANUAL") is True
    assert salida_requiere_asiento("SALIDA", "VENTA") is False
    assert salida_requiere_asiento("ENTRADA", None) is False


def test_documento_tributario_cuadra_y_no_habla_con_el_sii():
    from services.finanzas.documento_tributario import montos_cuadran, normalizar_tipo

    assert montos_cuadran(Decimal("1000"), Decimal("190"), Decimal("1190"))
    assert montos_cuadran(
        Decimal("1000"),
        Decimal("190"),
        Decimal("1290"),
        exento=Decimal("100"),
    )
    assert not montos_cuadran(Decimal("1000"), Decimal("190"), Decimal("1000"))
    assert normalizar_tipo("NC") == "NOTA_CREDITO"
    texto = (ROOT / "services" / "finanzas" / "documento_tributario.py").read_text(encoding="utf-8")
    assert "httpx" not in texto
    assert "certificado" not in texto
    assert "lxml" not in texto
    assert "sii.cl" not in texto.lower()


def test_diferencia_de_cambio_y_lados():
    from services.finanzas.diferencia_cambio import diferencia_clp, lineas_desde_reglas

    assert diferencia_clp(Decimal("100"), Decimal("900"), Decimal("950")) == Decimal("5000.00")
    assert diferencia_clp(Decimal("100"), Decimal("950"), Decimal("900")) == Decimal("-5000.00")
    reglas = [
        {"lado": "DEBE", "codigo_cuenta": "510199", "nombre_cuenta": "Pérdida"},
        {"lado": "HABER", "codigo_cuenta": "210101", "nombre_cuenta": "Proveedores"},
    ]
    perdida = lineas_desde_reglas(reglas, Decimal("5000"))
    assert perdida[0]["debe"] == Decimal("5000.00")
    assert perdida[1]["haber"] == Decimal("5000.00")
    ganancia = lineas_desde_reglas(reglas, Decimal("-5000"))
    assert ganancia[0]["haber"] == Decimal("5000.00")
    assert ganancia[1]["debe"] == Decimal("5000.00")


def test_propuesta_de_conciliacion_por_monto_y_fecha():
    from services.finanzas.conciliacion_bancaria import proponer_pares

    propuestas = proponer_pares(
        [
            {"id": 1, "fecha": date(2026, 10, 1), "monto": Decimal("-1500"), "estado": "PENDIENTE"},
            {"id": 2, "fecha": date(2026, 10, 2), "monto": Decimal("800"), "estado": "CONCILIADA"},
        ],
        [
            {"tipo": "AP_PAGO", "id": 9, "fecha": date(2026, 10, 3), "monto": Decimal("1500")},
            {"tipo": "PAGO_CLIENTE", "id": 4, "fecha": date(2026, 1, 1), "monto": Decimal("1500")},
        ],
        tolerancia_dias=3,
    )
    assert propuestas == [
        {
            "linea_id": 1,
            "movimiento_tipo": "AP_PAGO",
            "movimiento_id": 9,
            "dias": 2,
            "monto": "1500.00",
        }
    ]


def test_origenes_nuevos_en_indice_y_lista_blanca():
    from crud.finanzas.contabilidad_asientos import ORIGENES_IDEMPOTENTES

    sql = (ROOT / "db" / "psql" / "144_fase_d_libros_tesoreria.sql").read_text(encoding="utf-8")
    for origen in ("DIFERENCIA_CAMBIO", "INVENTARIO_SALIDA", "CONCILIACION_DIF"):
        assert origen in ORIGENES_IDEMPOTENTES
        assert origen in sql
    assert "fin.documento_tributario" in sql
    assert "costo_promedio" in sql
    assert "analytics_cartera_cxc" in sql
    assert "analytics_resultado_mes" in sql


def test_analytics_solo_lee():
    prohibido = ("accounting_service", "crear_asiento", "registrar_movimiento", "post_entry")
    for path in (ROOT / "modules" / "analytics").rglob("*.py"):
        texto = path.read_text(encoding="utf-8")
        for nombre in prohibido:
            assert nombre not in texto, path.name


def test_api_de_escritura_exige_permiso_e_idempotencia():
    texto = (ROOT / "routes" / "api" / "v1" / "operations.py").read_text(encoding="utf-8")
    assert "Idempotency-Key" in texto
    assert "CONTABILIDAD_POST" in texto
    assert "COBRANZA_COLLECT" in texto
    assert "CONTABILIDAD_CLOSE" in texto
    assert "registrar_asiento_manual" in texto
    assert "registrar_pago_cliente" in texto
    assert "do_commit=False" in texto
    arbol = ast.parse(texto)
    importados = {
        nodo.module
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom) and nodo.module
    }
    assert "services.finanzas.documento_tributario" in importados


def test_ganchos_de_negocio_sin_envio_sii():
    ventas = (ROOT / "services" / "finanzas" / "integracion_ventas.py").read_text(encoding="utf-8")
    ap = (ROOT / "crud" / "finanzas" / "cuentas_por_pagar.py").read_text(encoding="utf-8")
    periodos = (ROOT / "crud" / "finanzas" / "periodos.py").read_text(encoding="utf-8")
    inventario = (ROOT / "crud" / "inventario" / "inventario.py").read_text(encoding="utf-8")
    assert "_vincular_libro_venta" in ventas
    assert "costo_promedio" in ventas
    assert "registrar_desde_documento_ap" in ap
    assert "revaluar_saldos_periodo" in periodos
    assert "aplicar_costo_promedio" in inventario
    assert "contabilizar_salida_al_costo" in inventario
    assert "sii.cl" not in ventas.lower()
    operaciones = (ROOT / "routes" / "api" / "v1" / "operations.py").read_text(encoding="utf-8")
    assert "sii.cl" not in operaciones.lower()


def test_api_sin_sesion_responde_401():
    from core.auth_paths import respuesta_sin_sesion

    respuesta = respuesta_sin_sesion("/api/v1/accounting/manual-entries", "/login")
    assert respuesta.status_code == 401
    html = respuesta_sin_sesion("/finanzas/hub", "/login")
    assert html.status_code == 302
