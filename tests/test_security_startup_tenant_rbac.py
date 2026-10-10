# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.responses import PlainTextResponse
from starlette.requests import Request

from core.config import Settings
from core.tenant import TenantResolutionMiddleware, get_current_tenant_code
from routes.ui import cliente as ui_cliente
from routes.ui import inventario as ui_inventario


def _fake_request(method: str = "POST", path: str = "/") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    req = Request(scope)
    req.state.auth_user = {"roles": ["CONSULTA"]}
    return req


def test_post_operativo_clientes_restringe_mutacion_sin_rol() -> None:
    req = _fake_request(path="/clientes")
    resp = ui_cliente.clientes_create(
        request=req,
        rut="11111111-1",
        razon_social="Cliente Test",
        nombre_fantasia=None,
        giro=None,
        direccion=None,
        comuna=None,
        ciudad=None,
        telefono=None,
        email=None,
        activo="true",
        db=None,  # No se usa porque debe cortar por RBAC.
    )
    assert resp.status_code == 303
    assert resp.headers.get("location", "").startswith("/?")


def test_post_operativo_inventario_restringe_mutacion_sin_rol() -> None:
    req = _fake_request(path="/inventario/productos")
    resp = ui_inventario.producto_create(
        request=req,
        nombre="Producto Test",
        codigo=None,
        codigo_barra=None,
        categoria_id=None,
        unidad_medida_id=None,
        precio_compra="0",
        precio_venta="0",
        stock_minimo="0",
        stock_actual="0",
        descripcion=None,
        controla_stock=None,
        permite_venta_fraccionada=None,
        es_servicio=None,
        activo=None,
        db=None,  # No se usa porque debe cortar por RBAC.
    )
    assert resp.status_code == 303
    assert resp.headers.get("location", "").startswith("/?")


def test_settings_rechaza_auto_migrate_en_produccion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("PLATFORM_DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("AUTO_MIGRATE_ON_STARTUP", "true")
    with pytest.raises(RuntimeError, match="AUTO_MIGRATE_ON_STARTUP=true"):
        Settings.load()


def test_tenant_middleware_resetea_contextvar(monkeypatch: pytest.MonkeyPatch) -> None:
    from core import tenant as tenant_module

    monkeypatch.setattr(
        tenant_module,
        "settings",
        SimpleNamespace(default_tenant_code="company_test", app_debug=False),
    )

    middleware = TenantResolutionMiddleware(app=lambda *args, **kwargs: None)

    async def _run() -> None:
        req = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/ok",
                "raw_path": b"/ok",
                "query_string": b"",
                "headers": [],
                "session": {},
            }
        )

        async def _call_next(_request: Request):
            return PlainTextResponse("ok", status_code=200)

        res = await middleware.dispatch(req, _call_next)
        assert res.status_code == 200
        assert "X-Resolved-Tenant" not in res.headers
        assert get_current_tenant_code() is None

    asyncio.run(_run())


def test_tenant_middleware_resetea_contextvar_si_hay_excepcion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core import tenant as tenant_module

    monkeypatch.setattr(
        tenant_module,
        "settings",
        SimpleNamespace(default_tenant_code="company_test", app_debug=False),
    )

    middleware = TenantResolutionMiddleware(app=lambda *args, **kwargs: None)

    async def _run() -> None:
        req = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/boom",
                "raw_path": b"/boom",
                "query_string": b"",
                "headers": [],
                "session": {},
            }
        )

        async def _call_next(_request: Request):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await middleware.dispatch(req, _call_next)
        assert get_current_tenant_code() is None

    asyncio.run(_run())


def test_create_app_no_ejecuta_migraciones_si_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    import db.session as db_session_module

    # Evita conexiones reales al importar main (main crea app en import-time).
    monkeypatch.setattr(db_session_module, "get_engine", lambda tenant: object())
    main_module = importlib.import_module("main")
    main_module = importlib.reload(main_module)

    calls: dict[str, object] = {"create_all": 0, "startup": []}

    def _mark_create_all(*args, **kwargs):
        calls["create_all"] = int(calls["create_all"]) + 1

    def _mark_startup(engine, *, allow_ddl, create_all=None):
        calls["startup"].append({"allow_ddl": allow_ddl, "has_create_all": create_all is not None})
        if create_all is not None:
            create_all(bind=engine)

    monkeypatch.setattr(main_module.Base.metadata, "create_all", _mark_create_all)
    monkeypatch.setattr(main_module, "apply_startup_schema", _mark_startup)
    monkeypatch.setattr(main_module, "get_engine", lambda tenant: object())
    monkeypatch.setattr(main_module, "include_ui_routers", lambda app: None)
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            app_name="EvaluaERP",
            app_env="production",
            app_version="1.0.0",
            is_dev=False,
            secret_key="x" * 64,
            auth_session_max_age_seconds=3600,
            auth_cookie_secure=True,
            default_tenant_code="company_test",
            auto_migrate_on_startup=False,
            allowed_hosts=("testserver", "localhost"),
            trust_x_forwarded_for=False,
            database_per_company=False,
        ),
    )

    app = main_module.create_app()
    assert app is not None
    assert calls["create_all"] == 0
    assert calls["startup"] == [{"allow_ddl": False, "has_create_all": False}]
