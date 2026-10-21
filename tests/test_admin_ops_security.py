# tests/test_admin_ops_security.py
# -*- coding: utf-8 -*-
"""Seguridad admin, fail-closed módulos, auditoría, backups y system-status."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.nav_visibility import modulos_visibles_en_sesion, usuario_puede_ver_modulo_nav
from services.audit.enterprise import _scrub, audit_event
from services.comunicaciones.email_templates import build_message, render_template
from services.operacion.system_status_service import collect_system_status
from services.platform.access import authorize_company


def test_fail_closed_empty_visible_modules_non_admin():
    auth = {"roles": [], "visibleModules": []}
    # Sin roles y sin módulos: defaults → solo PRINCIPAL (catálogo)
    mods = modulos_visibles_en_sesion(auth)
    assert "FINANZAS" not in mods or "PRINCIPAL" in mods
    assert not usuario_puede_ver_modulo_nav({"roles": ["OPERACIONES"], "visibleModules": []}, "FINANZAS")


def test_admin_sees_all_modules():
    auth = {"roles": ["ADMIN"], "visibleModules": []}
    mods = modulos_visibles_en_sesion(auth)
    assert "ADMINISTRACION" in mods
    assert "FINANZAS" in mods


def test_audit_scrub_strips_secrets():
    cleaned = _scrub(
        {
            "email": "a@b.cl",
            "password": "secret",
            "token": "abc",
            "roles": "ADMIN",
            "smtp_password": "x",
        }
    )
    assert cleaned is not None
    assert "password" not in cleaned
    assert "token" not in cleaned
    assert "smtp_password" not in cleaned
    assert cleaned.get("email") == "a@b.cl"


def test_email_template_no_code_execution():
    out = render_template("Hola {{ user.name }} {{ __import__('os') }}", {"user": {"name": "Ana"}})
    assert "Ana" in out
    assert "__import__" not in out or "Ana" in out
    msg = build_message(
        "password_reset",
        {"code": "12345678", "user": {"name": "Ana", "email": "a@b.cl"}, "company": {"name": "ACME"}},
    )
    assert "12345678" in msg["html"]
    assert "ACME" in msg["subject"]


def test_system_status_payload_has_no_secrets(monkeypatch):
    class FakeResult:
        def __init__(self, val):
            self._val = val

        def scalar(self):
            return self._val

    class FakeDB:
        def __init__(self):
            self.n = 0

        def execute(self, *_a, **_k):
            self.n += 1
            return FakeResult(1 if self.n == 1 else "testdb")

    monkeypatch.setattr(
        "services.operacion.system_status_service._query_windows_service",
        lambda _name: {"online": False, "state": "STOPPED", "detail": "detenido"},
    )
    payload = collect_system_status(FakeDB())
    blob = str(payload).lower()
    for banned in ("password", "token", "credential", "secret", "private_key"):
        assert banned not in blob
    assert "fastapi" in payload
    assert "postgresql" in payload
    assert "cloudflare" in payload


def test_authorize_company_fail_closed():
    class FakeDB:
        def execute(self, *_a, **_k):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        def get(self, *_a, **_k):
            return None

    assert authorize_company(FakeDB(), user_id=1, company_id=99) is None


def test_backup_status_create_disabled_without_pg_dump(monkeypatch):
    from services.operacion import database_backup_service as svc

    monkeypatch.setattr(svc, "pg_dump_available", lambda: False)
    monkeypatch.setattr(svc, "_operational_url", lambda: "postgresql+psycopg://u:p@localhost:5432/demo")

    class FakeScalar:
        def __init__(self, val=None):
            self._val = val

        def first(self):
            return None

    class FakeDB:
        def scalars(self, *_a, **_k):
            return FakeScalar()

        def scalar(self, *_a, **_k):
            return 0

    st = svc.backup_status(FakeDB())
    assert st["toolAvailable"] is False
    assert st["createEnabled"] is False


def test_audit_event_does_not_raise_without_db():
    audit_event(action="login", result="ok", actor_id=1, persist_operational=False)
