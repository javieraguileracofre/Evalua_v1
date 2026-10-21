# tests/test_password_reset.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core.auth_paths import is_public_path
from crud.auth.usuarios import autenticar, hash_password, validar_politica_password
from models.auth.password_reset import PasswordResetCode
from models.auth.usuario import Rol, Usuario, usuario_rol
from services.auth import password_reset as svc
from services.auth.password_reset import (
    GENERIC_CODE_MESSAGE,
    GENERIC_REQUEST_MESSAGE,
    MAX_FAILED_ATTEMPTS,
    MAX_REQUESTS_PER_EMAIL,
    PASSWORD_MISMATCH_MESSAGE,
    RATE_LIMIT_MESSAGE,
)

SECRET = "test-secret-key-for-password-reset-hmac"
T0 = datetime(2026, 1, 15, 12, 0, 0)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Rol.__table__.create(engine, checkfirst=True)
    Usuario.__table__.create(engine, checkfirst=True)
    usuario_rol.create(engine, checkfirst=True)
    PasswordResetCode.__table__.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _crear_usuario(
    db: Session,
    *,
    uid: int = 1,
    email: str = "user@test.cl",
    password: str = "AntiguaClave1",
    activo: bool = True,
) -> Usuario:
    u = Usuario(
        id=uid,
        email=email,
        password_hash=hash_password(password),
        nombre_completo=email.split("@")[0],
        activo=activo,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _pedir(db: Session, email: str, sent: list[tuple[str, str]], *, now: datetime = T0, ip: str = "127.0.0.1"):
    def _send(to_email: str, code: str) -> None:
        sent.append((to_email, code))

    result = svc.request_password_reset(
        db,
        email,
        ip=ip,
        secret=SECRET,
        send_email=_send,
        now=now,
    )
    db.commit()
    return result


def test_politica_password_rechaza_debil() -> None:
    with pytest.raises(ValueError, match="10 caracteres"):
        validar_politica_password("corta")
    with pytest.raises(ValueError, match="letra"):
        validar_politica_password("1234567890")
    with pytest.raises(ValueError, match="número"):
        validar_politica_password("sololetrasxx")
    assert validar_politica_password("ClaveSegura1") == "ClaveSegura1"


def test_solicitud_correo_existente_envia_codigo(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    result = _pedir(db, "user@test.cl", sent)
    assert result.message == GENERIC_REQUEST_MESSAGE
    assert len(sent) == 1
    assert sent[0][0] == "user@test.cl"
    assert sent[0][1].isdigit() and len(sent[0][1]) == 8
    row = db.scalars(select(PasswordResetCode)).first()
    assert row is not None
    assert row.code_hash != sent[0][1]
    assert sent[0][1] not in row.code_hash
    assert row.used_at is None
    assert row.expires_at == T0 + timedelta(minutes=5)


def test_solicitud_correo_inexistente_no_revela_ni_envia(db: Session) -> None:
    sent: list[tuple[str, str]] = []
    result = _pedir(db, "nadie@test.cl", sent)
    assert result.message == GENERIC_REQUEST_MESSAGE
    assert sent == []
    rows = list(db.scalars(select(PasswordResetCode)))
    assert len(rows) == 1
    assert rows[0].user_id is None
    assert rows[0].used_at is not None


def test_solicitud_existente_e_inexistente_mismo_mensaje(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    a = _pedir(db, "user@test.cl", sent, ip="10.0.0.1")
    b = _pedir(db, "otro@test.cl", sent, ip="10.0.0.2")
    assert a.message == b.message == GENERIC_REQUEST_MESSAGE


def test_codigo_valido_dentro_de_5_minutos(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    _pedir(db, "user@test.cl", sent)
    code = sent[0][1]
    result = svc.verify_reset_code(
        db, "user@test.cl", code, secret=SECRET, now=T0 + timedelta(minutes=4, seconds=59)
    )
    db.commit()
    assert result.ok is True


def test_codigo_expirado_a_los_5_minutos(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    _pedir(db, "user@test.cl", sent)
    code = sent[0][1]
    result = svc.verify_reset_code(
        db, "user@test.cl", code, secret=SECRET, now=T0 + timedelta(minutes=5)
    )
    db.commit()
    assert result.ok is False
    assert result.message == GENERIC_CODE_MESSAGE


def test_codigo_incorrecto(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    _pedir(db, "user@test.cl", sent)
    result = svc.verify_reset_code(db, "user@test.cl", "00000000", secret=SECRET, now=T0)
    db.commit()
    assert result.ok is False
    assert result.message == GENERIC_CODE_MESSAGE


def test_limite_intentos_fallidos(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    _pedir(db, "user@test.cl", sent)
    real = sent[0][1]
    for i in range(MAX_FAILED_ATTEMPTS):
        r = svc.verify_reset_code(db, "user@test.cl", "11111111", secret=SECRET, now=T0)
        db.commit()
        assert r.ok is False, i
    locked = svc.verify_reset_code(db, "user@test.cl", real, secret=SECRET, now=T0)
    db.commit()
    assert locked.ok is False
    assert locked.message == GENERIC_CODE_MESSAGE


def test_codigo_de_un_solo_uso(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    _pedir(db, "user@test.cl", sent)
    code = sent[0][1]
    first = svc.reset_password_with_code(
        db,
        "user@test.cl",
        code,
        "NuevaClave99",
        "NuevaClave99",
        secret=SECRET,
        now=T0,
    )
    db.commit()
    assert first.ok is True
    second = svc.reset_password_with_code(
        db,
        "user@test.cl",
        code,
        "OtraClave88x",
        "OtraClave88x",
        secret=SECRET,
        now=T0 + timedelta(seconds=30),
    )
    db.commit()
    assert second.ok is False
    assert second.message == GENERIC_CODE_MESSAGE


def test_cambio_password_exitoso_y_login(db: Session) -> None:
    _crear_usuario(db, password="AntiguaClave1")
    sent: list[tuple[str, str]] = []
    _pedir(db, "user@test.cl", sent)
    code = sent[0][1]
    result = svc.reset_password_with_code(
        db,
        "user@test.cl",
        code,
        "NuevaClave99",
        "NuevaClave99",
        secret=SECRET,
        now=T0,
    )
    db.commit()
    assert result.ok is True
    assert autenticar(db, "user@test.cl", "AntiguaClave1") is None
    assert autenticar(db, "user@test.cl", "NuevaClave99") is not None


def test_rechazo_cuando_contrasenas_no_coinciden(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    _pedir(db, "user@test.cl", sent)
    result = svc.reset_password_with_code(
        db,
        "user@test.cl",
        sent[0][1],
        "NuevaClave99",
        "NuevaClave00",
        secret=SECRET,
        now=T0,
    )
    db.commit()
    assert result.ok is False
    assert result.message == PASSWORD_MISMATCH_MESSAGE
    assert autenticar(db, "user@test.cl", "AntiguaClave1") is not None


def test_rechazo_password_debil_no_consume_codigo(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    _pedir(db, "user@test.cl", sent)
    code = sent[0][1]
    result = svc.reset_password_with_code(
        db,
        "user@test.cl",
        code,
        "1234567890",
        "1234567890",
        secret=SECRET,
        now=T0,
    )
    db.commit()
    assert result.ok is False
    assert "letra" in result.message.lower()
    still = svc.verify_reset_code(db, "user@test.cl", code, secret=SECRET, now=T0)
    db.commit()
    assert still.ok is True


def test_codigo_nuevo_invalida_el_anterior(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    _pedir(db, "user@test.cl", sent, now=T0, ip="10.1.1.1")
    old = sent[0][1]
    _pedir(db, "user@test.cl", sent, now=T0 + timedelta(seconds=10), ip="10.1.1.1")
    new = sent[1][1]
    assert old != new
    assert svc.verify_reset_code(db, "user@test.cl", old, secret=SECRET, now=T0 + timedelta(seconds=20)).ok is False
    assert svc.verify_reset_code(db, "user@test.cl", new, secret=SECRET, now=T0 + timedelta(seconds=20)).ok is True


def test_limite_solicitudes_por_correo(db: Session) -> None:
    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    for i in range(MAX_REQUESTS_PER_EMAIL):
        r = _pedir(db, "user@test.cl", sent, now=T0 + timedelta(seconds=i), ip="8.8.8.8")
        assert r.rate_limited is False
    extra = _pedir(db, "user@test.cl", sent, now=T0 + timedelta(seconds=30), ip="8.8.8.8")
    assert extra.rate_limited is True
    assert extra.message == RATE_LIMIT_MESSAGE
    assert len(sent) == MAX_REQUESTS_PER_EMAIL


def test_cuenta_inactiva_no_envia_codigo(db: Session) -> None:
    _crear_usuario(db, activo=False)
    sent: list[tuple[str, str]] = []
    result = _pedir(db, "user@test.cl", sent)
    assert result.message == GENERIC_REQUEST_MESSAGE
    assert sent == []


def test_rutas_publicas_de_recuperacion() -> None:
    from types import SimpleNamespace

    settings = SimpleNamespace(is_dev=True)
    assert is_public_path("/login", settings)
    assert is_public_path("/login/recuperar", settings)
    assert is_public_path("/login/recuperar/codigo", settings)
    assert is_public_path("/auth/forgot-password", settings)
    assert is_public_path("/auth/verify-reset-code", settings)
    assert is_public_path("/auth/reset-password", settings)


def test_login_muestra_olvide_contrasena() -> None:
    from core.paths import TEMPLATES_DIR

    html = (TEMPLATES_DIR / "auth" / "login.html").read_text(encoding="utf-8")
    assert "Olvidé mi contraseña" in html
    assert "auth_recuperar" in html


def test_api_forgot_password_respuesta_generica(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request

    from routes.ui import auth as auth_routes
    from schemas.auth.password_reset import ForgotPasswordIn

    _crear_usuario(db)
    sent: list[tuple[str, str]] = []
    original = svc.request_password_reset

    def _wrapped(db_sess, email, **kwargs):
        kwargs.setdefault("secret", SECRET)
        kwargs.setdefault("send_email", lambda to_email, code: sent.append((to_email, code)))
        kwargs.setdefault("now", T0)
        return original(db_sess, email, **kwargs)

    monkeypatch.setattr(auth_routes.svc_reset, "request_password_reset", _wrapped)

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/forgot-password",
            "headers": [],
            "client": ("127.0.0.1", 9),
        }
    )
    resp_ok = auth_routes.forgot_password_api(ForgotPasswordIn(email="user@test.cl"), req, db)
    resp_miss = auth_routes.forgot_password_api(ForgotPasswordIn(email="no@test.cl"), req, db)

    assert resp_ok.status_code == 200
    assert resp_miss.status_code == 200
    assert resp_ok.body == resp_miss.body
    assert GENERIC_REQUEST_MESSAGE.encode() in resp_ok.body
    assert sent and sent[0][0] == "user@test.cl"
