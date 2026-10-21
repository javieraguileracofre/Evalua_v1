# tests/test_security_hardening.py
# -*- coding: utf-8 -*-
"""Regresiones de la fase de endurecimiento: RBAC, sesión, XSS, health, host, rate limit."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from core.json_script import json_for_script
from core.login_throttle import (
    MAX_PER_EMAIL,
    is_login_blocked,
    register_login_failure,
    register_login_success,
    reset_for_tests,
)
from core.rbac import (
    guard_credito_riesgo_aprobar,
    guard_credito_riesgo_consulta,
    guard_credito_riesgo_mutacion,
    guard_transporte_consulta,
    guard_transporte_mutacion,
    require_leasing_fin_consulta_api,
    require_leasing_fin_mutacion_api,
    usuario_puede_ver_kpis_financieros,
)
from core.session_revalidate import revalidar_auth_payload
from crud.auth.usuarios import establecer_password, hash_password, increment_session_version, serializar_sesion_usuario
from models.auth.usuario import Rol, Usuario, usuario_rol
from routes.ui import credito_riesgo as ui_cr
from services.auth import password_reset as svc_reset


def _request(roles: list[str], modules: list[str] | None = None) -> Request:
    req = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )
    auth = {"uid": 9, "roles": roles}
    if modules is not None:
        auth["visibleModules"] = modules
    req.state.auth_user = auth
    return req


def test_consulta_no_muta_credito() -> None:
    req = _request(["CONSULTA"], ["CREDITO_RIESGO"])
    assert guard_credito_riesgo_consulta(req) is None
    deny = guard_credito_riesgo_mutacion(req)
    assert deny is not None and deny.status_code == 303
    deny_ap = guard_credito_riesgo_aprobar(req)
    assert deny_ap is not None and deny_ap.status_code == 303
    resp = ui_cr.solicitud_aprobar(req, solicitud_id=1, db=None)  # type: ignore[arg-type]
    assert resp.status_code == 303


def test_consulta_no_muta_transporte() -> None:
    req = _request(["CONSULTA"], ["OPERACIONES"])
    assert guard_transporte_consulta(req) is None
    deny = guard_transporte_mutacion(req)
    assert deny is not None and deny.status_code == 303


def test_consulta_no_muta_leasing_financiero_api() -> None:
    req = _request(["CONSULTA"], ["LEASING_FINANCIERO"])
    require_leasing_fin_consulta_api(req)
    with pytest.raises(HTTPException) as exc:
        require_leasing_fin_mutacion_api(req)
    assert exc.value.status_code == 403


def test_kpis_financieros_solo_finanzas_admin() -> None:
    assert usuario_puede_ver_kpis_financieros({"roles": ["CONSULTA"]}) is False
    assert usuario_puede_ver_kpis_financieros({"roles": ["OPERACIONES"]}) is False
    assert usuario_puede_ver_kpis_financieros({"roles": ["FINANZAS"]}) is True
    assert usuario_puede_ver_kpis_financieros({"roles": ["ADMIN"]}) is True


def _sqlite_user_db() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Rol.__table__.create(engine, checkfirst=True)
    Usuario.__table__.create(engine, checkfirst=True)
    usuario_rol.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    db.add(Rol(id=1, codigo="ADMIN", nombre="Administrador"))
    db.commit()
    u = Usuario(
        id=1,
        email="admin@test.cl",
        password_hash=hash_password("ClaveSegura99"),
        nombre_completo="Admin",
        activo=True,
        session_version=1,
    )
    u.roles.append(db.get(Rol, 1))
    db.add(u)
    db.commit()
    return db


def test_usuario_desactivado_invalida_sesion() -> None:
    db = _sqlite_user_db()
    try:
        u = db.get(Usuario, 1)
        payload = serializar_sesion_usuario(u, visible_modules=["COMERCIAL"])
        assert revalidar_auth_payload(db, payload) is not None
        u.activo = False
        increment_session_version(db, 1)
        db.commit()
        assert revalidar_auth_payload(db, payload) is None
    finally:
        db.close()


def test_cambio_password_invalida_sesion_anterior() -> None:
    db = _sqlite_user_db()
    try:
        u = db.get(Usuario, 1)
        payload = serializar_sesion_usuario(u, visible_modules=["COMERCIAL"])
        establecer_password(db, 1, "OtraClaveSegura99")
        db.commit()
        assert revalidar_auth_payload(db, payload) is None
        u2 = db.get(Usuario, 1)
        fresh = serializar_sesion_usuario(u2, visible_modules=["COMERCIAL"])
        assert revalidar_auth_payload(db, fresh) is not None
    finally:
        db.close()


def test_json_for_script_escapa_payload_xss() -> None:
    raw = json_for_script({"x": "</script><img onerror=alert(1) src=x>"})
    assert "</script>" not in raw
    assert "<img" not in raw
    assert "\\u003c" in raw


def test_health_produccion_minimo(monkeypatch: pytest.MonkeyPatch) -> None:
    import main as main_module

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(is_dev=False, app_name="EvaluaERP", app_env="production", default_tenant_code="company_test", tenancy_mode="legacy"),
    )
    assert main_module.health_payload() == {"status": "ok"}
    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(is_dev=True, app_name="EvaluaERP", app_env="development", default_tenant_code="company_test", tenancy_mode="legacy"),
    )
    assert main_module.health_payload()["env"] == "development"


def test_trusted_host_rechaza_host_no_permitido() -> None:
    async def home(_request):
        return PlainTextResponse("ok")

    wrapped = Starlette(
        routes=[Route("/", home)],
        middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=["localhost"])],
    )

    c = TestClient(wrapped, base_url="http://evil.example")
    resp = c.get("/")
    assert resp.status_code == 400


def _http_request(
    *,
    headers: list[tuple[str, str]] | None = None,
    client: tuple[str, int] = ("203.0.113.8", 9),
    session: dict | None = None,
) -> Request:
    raw = [(key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in (headers or [])]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": raw,
        "client": client,
        "server": ("testserver", 80),
    }
    if session is not None:
        scope["session"] = session
    return Request(scope)


def test_client_ip_ignora_forwarded_si_no_hay_confianza(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.client_ip as cip

    monkeypatch.setattr(cip, "settings", SimpleNamespace(trust_x_forwarded_for=False))
    req = _http_request(headers=[("x-forwarded-for", "198.51.100.4"), ("cf-connecting-ip", "198.51.100.7")])
    assert cip.client_ip(req) == "203.0.113.8"


def test_client_ip_prioriza_cloudflare_si_hay_confianza(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.client_ip as cip

    monkeypatch.setattr(cip, "settings", SimpleNamespace(trust_x_forwarded_for=True))
    req = _http_request(headers=[("x-forwarded-for", "198.51.100.4"), ("cf-connecting-ip", "198.51.100.7")])
    assert cip.client_ip(req) == "198.51.100.7"
    solo_forwarded = _http_request(headers=[("x-forwarded-for", "198.51.100.4, 10.0.0.1")])
    assert cip.client_ip(solo_forwarded) == "198.51.100.4"


def test_login_rota_la_sesion_previa() -> None:
    from routes.ui.auth import _start_authenticated_session

    req = _http_request(session={"csrf_global": "token-previo", "csrf_login": "pin", "auth": {"uid": 1}})
    _start_authenticated_session(req, {"uid": 9, "email": "a@test.cl"})
    assert req.session["csrf_global"] != "token-previo"
    assert "csrf_login" not in req.session
    assert req.session["auth"]["uid"] == 9


def test_tokens_match_es_constante() -> None:
    from core.csrf_middleware import tokens_match

    assert tokens_match("abc", "abc") is True
    assert tokens_match("abc", "abd") is False
    assert tokens_match("", "abc") is False
    assert tokens_match("abc", None) is False


def test_login_rate_limit_por_email() -> None:
    reset_for_tests()
    assert is_login_blocked(email="a@test.cl", ip="10.0.0.1") is False
    for _ in range(MAX_PER_EMAIL):
        register_login_failure(email="a@test.cl", ip="10.0.0.1")
    assert is_login_blocked(email="a@test.cl", ip="10.0.0.1") is True
    register_login_success(email="a@test.cl", ip="10.0.0.1")
    assert is_login_blocked(email="a@test.cl", ip="10.0.0.1") is False
    reset_for_tests()


def test_login_rate_limit_persiste_entre_conexiones(tmp_path) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from models.auth.login_attempt import LoginAttempt

    url = "sqlite:///" + (tmp_path / "login.db").as_posix()
    engine_a = create_engine(url, future=True)
    LoginAttempt.__table__.create(engine_a)
    engine_b = create_engine(url, future=True)
    make_a = sessionmaker(bind=engine_a, future=True)
    make_b = sessionmaker(bind=engine_b, future=True)
    db_a = make_a()
    db_b = make_b()
    reset_for_tests()
    try:
        assert is_login_blocked(email="a@test.cl", ip="10.0.0.1", db=db_a, model=LoginAttempt) is False
        for _ in range(MAX_PER_EMAIL):
            register_login_failure(email="a@test.cl", ip="10.0.0.8", db=db_a, model=LoginAttempt)
        reset_for_tests()
        assert is_login_blocked(email="a@test.cl", ip="192.0.2.9", db=db_b, model=LoginAttempt) is True
        register_login_success(email="a@test.cl", ip="192.0.2.9", db=db_b, model=LoginAttempt)
        assert is_login_blocked(email="a@test.cl", ip="192.0.2.9", db=db_a, model=LoginAttempt) is False
    finally:
        db_a.close()
        db_b.close()
        engine_a.dispose()
        engine_b.dispose()
        reset_for_tests()


def test_respaldo_rechaza_ruta_fuera_de_carpeta(tmp_path) -> None:
    from services.operacion.database_backup_service import (
        BACKUP_ERROR_PUBLIC,
        _redact_process_output,
        confined_backup_path,
    )

    root = tmp_path / "backups"
    root.mkdir()
    dump = root / "a.dump"
    dump.write_bytes(b"abc")
    secret = tmp_path / "secret.txt"
    secret.write_text("no", encoding="utf-8")
    assert confined_backup_path(str(dump), root=root) == dump.resolve()
    assert confined_backup_path(str(secret), root=root) is None
    assert confined_backup_path(str(root / ".." / "secret.txt"), root=root) is None
    redacted = _redact_process_output("postgresql+psycopg://user:Secreto1@db.internal/erp")
    assert "Secreto1" not in redacted
    assert BACKUP_ERROR_PUBLIC == "No se pudo crear el respaldo."


def test_get_backup_no_abre_fila_de_otra_empresa() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from models.ops.backup import DatabaseBackup
    from services.operacion.database_backup_service import get_backup

    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    DatabaseBackup.__table__.create(engine)
    db = sessionmaker(bind=engine, future=True)()
    try:
        sin_empresa = DatabaseBackup(
            status="success",
            backup_type="manual",
            engine_name="postgresql",
            database_name="erp",
            company_code=None,
        )
        otra = DatabaseBackup(
            status="success",
            backup_type="manual",
            engine_name="postgresql",
            database_name="erp",
            company_code="beta",
        )
        propia = DatabaseBackup(
            status="success",
            backup_type="manual",
            engine_name="postgresql",
            database_name="erp",
            company_code="acme",
        )
        db.add_all([sin_empresa, otra, propia])
        db.commit()
        assert get_backup(db, int(sin_empresa.id), company_code="acme") is None
        assert get_backup(db, int(otra.id), company_code="acme") is None
        assert get_backup(db, int(propia.id), company_code="acme") is not None
        assert get_backup(db, int(propia.id), company_code=None) is not None
    finally:
        db.close()
        engine.dispose()


def test_reset_ok_token_no_es_el_pin() -> None:
    pin = "12345678"
    token_like = svc_reset._hmac_hex("unit-secret", "pwdreset-ok", "1:99")
    assert pin not in token_like
    assert len(token_like) == 64
