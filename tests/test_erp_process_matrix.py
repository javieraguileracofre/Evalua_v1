# tests/test_erp_process_matrix.py
# -*- coding: utf-8 -*-
"""
Matriz de procesos ERP: contratos, eventos y fronteras.

Estas pruebas validan el cableado arquitectónico de los procesos críticos
sin requerir PostgreSQL completo. Los flujos E2E con BD permanecen en
suites específicas (leasing_*, cobranza_*, finanzas_*).
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "module_path,symbols",
    [
        ("modules.comercial.sales", ["crear_venta_pos", "anular_venta_pos"]),
        ("modules.cobranza", ["registrar_pago_cliente", "contabilizar_pago_cliente"]),
        ("modules.finanzas", ["registrar_documento_ap", "registrar_pago_ap"]),
        ("modules.leasing.financiero", ["activar_leasing_financiero"]),
        ("modules.leasing.operativo", ["activar_leasing_operativo", "calcular_preview"]),
        ("modules.contabilidad", ["accounting_service"]),
    ],
)
def test_process_contracts_importable(module_path: str, symbols: list[str]):
    import importlib

    mod = importlib.import_module(module_path)
    for name in symbols:
        assert hasattr(mod, name), f"{module_path} falta {name}"


def test_quote_to_cash_emits_venta_events():
    text = (ROOT / "services" / "comercial" / "ventas_service.py").read_text(encoding="utf-8")
    assert "VENTA_CONFIRMADA" in text
    assert "VENTA_ANULADA" in text
    assert "contabilizar_nota_venta" in text


def test_lease_to_asset_emits_contrato_activado():
    lf = (ROOT / "services" / "leasing_financiero_contabilidad.py").read_text(encoding="utf-8")
    lop = (ROOT / "services" / "leasing_operativo_contabilidad.py").read_text(encoding="utf-8")
    assert "CONTRATO_LEASING_ACTIVADO" in lf
    assert "CONTRATO_LEASING_ACTIVADO" in lop
    assert "publish_in_transaction" in lf
    assert "publish_in_transaction" in lop


def test_cobranza_emits_pago_realizado_and_uses_single_tx():
    text = (ROOT / "services" / "cobranza" / "pago_service.py").read_text(encoding="utf-8")
    assert "PAGO_REALIZADO" in text
    assert "publish_in_transaction" in text
    assert "do_commit=False" in text
    assert "db.commit()" in text


def test_bootstrap_registers_core_domain_events():
    from erp_platform.events import clear_subscribers
    from erp_platform.events import types as event_types
    import modules.bootstrap as boot

    clear_subscribers()
    boot._REGISTERED = False
    boot.register_domain_handlers()
    # Re-registro idempotente
    boot.register_domain_handlers()
    from erp_platform.events.bus import _SUBSCRIBERS

    assert event_types.VENTA_CONFIRMADA in _SUBSCRIBERS
    assert event_types.CONTRATO_LEASING_ACTIVADO in _SUBSCRIBERS
    assert event_types.PAGO_REALIZADO in _SUBSCRIBERS


def test_api_v1_meta_contract():
    """Router v1 aislado (evita create_app / AUTO_MIGRATE del entorno local)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.api.v1 import router as api_v1_router

    app = FastAPI()
    app.include_router(api_v1_router)
    client = TestClient(app)
    r = client.get("/api/v1/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["api"] == "evalua"
    assert body["version"] == "v1"
    assert "schema_revision" in body


def test_api_v1_session_requires_auth():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.api.v1 import router as api_v1_router

    app = FastAPI()
    app.include_router(api_v1_router)
    client = TestClient(app)
    r = client.get("/api/v1/session", follow_redirects=False)
    assert r.status_code == 401


def test_api_v1_accounting_requires_contabilidad_view():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.api.v1 import router as api_v1_router

    app = FastAPI()

    @app.middleware("http")
    async def inject_auth(request, call_next):
        # Rol sin CONTABILIDAD.VIEW
        request.state.auth_user = {"id": 9, "roles": ["OPERACIONES"]}
        return await call_next(request)

    app.include_router(api_v1_router)
    client = TestClient(app)
    r = client.get("/api/v1/accounting/entries/1", follow_redirects=False)
    assert r.status_code == 403


def test_api_v1_leasing_capabilities_allows_consulta():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.api.v1 import router as api_v1_router

    app = FastAPI()

    @app.middleware("http")
    async def inject_auth(request, call_next):
        request.state.auth_user = {"id": 3, "roles": ["CONSULTA"]}
        return await call_next(request)

    app.include_router(api_v1_router)
    client = TestClient(app)
    r = client.get("/api/v1/leasing/capabilities")
    assert r.status_code == 200
    assert "LEASING_FINANCIERO" in r.json()["productos"]


def test_observability_sets_request_id_header():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.observability_middleware import ObservabilityMiddleware

    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/ping")
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID")


def test_observability_preserves_client_request_id():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.observability_middleware import ObservabilityMiddleware

    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/ping", headers={"X-Request-ID": "qa-fixed-id-01"})
    assert r.headers.get("X-Request-ID") == "qa-fixed-id-01"