# -*- coding: utf-8 -*-
"""Humo HTTP: montaje de app, health y respuesta de hubs críticos sin sesión."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import importlib

    import db.session as db_session_module

    monkeypatch.setattr(db_session_module, "get_engine", lambda tenant=None: object())
    main_module = importlib.import_module("main")
    main_module = importlib.reload(main_module)

    monkeypatch.setattr(main_module, "get_engine", lambda tenant=None: object())
    monkeypatch.setattr(main_module, "apply_startup_schema", lambda *a, **k: None)
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            app_name="EvaluaERP",
            app_env="development",
            app_version="1.0.0",
            is_dev=True,
            secret_key="x" * 64,
            auth_session_max_age_seconds=3600,
            auth_cookie_secure=False,
            default_tenant_code="company_test",
            auto_migrate_on_startup=False,
            allowed_hosts=("testserver", "localhost", "127.0.0.1"),
            trust_x_forwarded_for=False,
            database_per_company=False,
            lop_comercial_v2=True,
        ),
    )

    app = main_module.create_app()
    return TestClient(app, base_url="http://testserver")


def test_health_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


@pytest.mark.parametrize(
    "path",
    [
        "/login",
        "/",
        "/comercial/leasing-operativo/hub",
        "/comercial/leasing/cotizaciones/hub",
        "/finanzas/hub",
        "/seguridad/usuarios",
    ],
)
def test_critical_paths_respond(client: TestClient, path: str) -> None:
    r = client.get(path, follow_redirects=False)
    assert r.status_code in {200, 302, 303, 307}
    if r.status_code in {302, 303, 307}:
        loc = r.headers.get("location", "")
        assert loc.startswith("/")
