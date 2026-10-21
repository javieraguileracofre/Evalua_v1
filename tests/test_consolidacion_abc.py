# -*- coding: utf-8 -*-
"""Olas A, B y C: integridad contable, frontera de casos de uso y operación."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_asiento_contabilizado_no_se_borra():
    from core.domain_errors import AsientoInmutableError
    from crud.finanzas.contabilidad_asientos import eliminar_asiento_contable
    from modules.contabilidad import accounting_service

    with pytest.raises(AsientoInmutableError):
        eliminar_asiento_contable(None, 1)  # type: ignore[arg-type]
    assert not hasattr(accounting_service, "delete_entry")
    assert hasattr(accounting_service, "reverse_business_entry")
    assert hasattr(accounting_service, "release_origin_key")


def test_reversiones_estan_en_el_indice_y_en_la_lista_blanca():
    from crud.finanzas.contabilidad_asientos import ORIGENES_IDEMPOTENTES

    sql = (ROOT / "db" / "psql" / "143_asientos_reversion_origen.sql").read_text(encoding="utf-8")
    for origen in ("AP_DOCUMENTO_REVERSA", "NOTA_VENTA_REVERSA", "FONDO_RENDIR_ENT_REVERSA"):
        assert origen in ORIGENES_IDEMPOTENTES
        assert origen in sql
    assert "DELETE FROM asientos" not in sql
    ventas = (ROOT / "services" / "finanzas" / "integracion_ventas.py").read_text(encoding="utf-8")
    assert "delete_entry" not in ventas
    assert "reverse_business_entry" in ventas


def test_emision_de_factura_usa_outbox_no_el_bus_en_memoria():
    text = (ROOT / "modules" / "contabilidad" / "accounting_service.py").read_text(encoding="utf-8")
    assert "publish_in_transaction" in text
    assert "from erp_platform.events import DomainEvent, emit" not in text


def test_stock_se_bloquea_y_el_ingreso_tiene_un_solo_commit():
    text = (ROOT / "crud" / "inventario" / "inventario.py").read_text(encoding="utf-8")
    assert "with_for_update" in text
    assert "StockInsuficienteError" in text
    fn = text.split("def ingresar_stock_producto", 1)[1].split("\ndef ", 1)[0]
    assert fn.count("db.commit()") == 1
    assert "do_commit=False" in fn


def test_folio_de_viaje_se_serializa_en_postgres():
    text = (ROOT / "crud" / "transporte_viajes.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in text
    assert "transporte_folio_viaje_" in text


def test_arranque_no_aplica_parches_sql():
    text = (ROOT / "db" / "startup_schema.py").read_text(encoding="utf-8")
    body = text.split("def apply_startup_schema", 1)[1]
    assert "STARTUP_DDL_ENSURES" not in body
    assert "upgrade_database_url" in body
    assert "_run_ensures(engine, STARTUP_SEED_ENSURES" in body


def test_casos_de_uso_de_escritura_salen_de_modules():
    from modules.finanzas import anular_documento_ap, registrar_documento_ap, registrar_pago_ap
    from modules.fondos import eliminar_fondo_rendir
    from modules.inventario import ajustar_stock, ingresar_stock_producto
    from modules.leasing.financiero import activar_contrato_financiero
    from modules.rrhh.payroll import contabilizar_provision_nomina_periodo
    from modules.taller import actualizar_orden_servicio, crear_orden_servicio

    for fn in (
        anular_documento_ap,
        registrar_documento_ap,
        registrar_pago_ap,
        eliminar_fondo_rendir,
        ajustar_stock,
        ingresar_stock_producto,
        activar_contrato_financiero,
        contabilizar_provision_nomina_periodo,
        actualizar_orden_servicio,
        crear_orden_servicio,
    ):
        assert callable(fn)


def test_rutas_de_escritura_delegan_en_modules():
    cxp = (ROOT / "routes" / "ui" / "cuentas_por_pagar.py").read_text(encoding="utf-8")
    inv = (ROOT / "routes" / "ui" / "inventario.py").read_text(encoding="utf-8")
    taller = (ROOT / "routes" / "ui" / "taller.py").read_text(encoding="utf-8")
    rem = (ROOT / "routes" / "ui" / "remuneraciones.py").read_text(encoding="utf-8")
    lf = (ROOT / "routes" / "ui" / "leasing_financiero.py").read_text(encoding="utf-8")
    assert "registrar_documento_ap" in cxp
    assert "anular_documento_ap" in cxp
    assert "crud_cxp.create_documento" not in cxp
    assert "crud_cxp.eliminar_documento" not in cxp
    assert "ingresar_stock_uc" in inv
    assert "crear_orden_servicio(" in taller
    assert "modules.rrhh.payroll" in rem
    assert "activar_contrato_financiero" in lf


def test_eventos_de_negocio_tienen_handler():
    from erp_platform.events import clear_subscribers
    from erp_platform.events import types as event_types
    import modules.bootstrap as boot
    from erp_platform.events.bus import _SUBSCRIBERS

    clear_subscribers()
    boot._REGISTERED = False
    boot.register_domain_handlers()
    for name in (
        event_types.PAGO_REALIZADO,
        event_types.CUOTA_PAGADA,
        event_types.LIQUIDACION_GENERADA,
        event_types.ORDEN_TRABAJO_CERRADA,
        event_types.DOCUMENTO_AP_REGISTRADO,
        event_types.PAGO_AP_REGISTRADO,
    ):
        assert name in _SUBSCRIBERS


def test_cxp_publica_en_outbox():
    text = (ROOT / "crud" / "finanzas" / "cuentas_por_pagar.py").read_text(encoding="utf-8")
    assert "DOCUMENTO_AP_REGISTRADO" in text
    assert "PAGO_AP_REGISTRADO" in text
    assert "eliminar_asiento_contable" not in text


def test_rol_de_aplicacion_no_puede_hacer_ddl():
    from services.platform.db_role import app_role_is_safe

    ok, _ = app_role_is_safe(can_create=False, can_insert=True)
    assert ok
    bad, message = app_role_is_safe(can_create=True, can_insert=True)
    assert not bad
    assert "CREATE" in message
    sin_dml, _ = app_role_is_safe(can_create=False, can_insert=False)
    assert not sin_dml


def test_explain_no_crea_indices():
    text = (ROOT / "tools" / "explain_candidate_queries.py").read_text(encoding="utf-8")
    catalogo = text.split("CANDIDATE_QUERIES", 1)[1].split("def main", 1)[0].upper()
    assert "CREATE INDEX" not in catalogo
    assert "ALTER TABLE" not in catalogo
    assert "asientos por fecha" in text


def test_periodo_cerrado_es_error_de_dominio():
    from core.domain_errors import DomainError, PeriodoCerradoError
    from core.public_errors import public_error_message
    from core.request_context import set_request_context

    set_request_context(request_id="abc123")
    msg = public_error_message(PeriodoCerradoError("El período contable 2026-01 está cerrado."))
    assert isinstance(PeriodoCerradoError("x"), DomainError)
    assert "abc123" in msg


def test_activacion_leasing_financiero_tiene_un_commit_de_caso_de_uso():
    text = (ROOT / "crud" / "comercial" / "leasing_fin.py").read_text(encoding="utf-8")
    fn = text.split("def activar_flujo_contable", 1)[1].split("\ndef ", 1)[0]
    assert fn.count("db.commit()") == 1
    contab = (ROOT / "services" / "leasing_financiero_contabilidad.py").read_text(encoding="utf-8")
    assert "do_commit=False" in contab
