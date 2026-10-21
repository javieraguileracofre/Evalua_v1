# tests/test_mail_accounts.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core.rbac import usuario_puede_gestionar_correo
from models.auth.password_reset import PasswordResetCode
from models.auth.usuario import Rol, Usuario, usuario_rol
from models.comunicaciones.email_log import EmailLog
from models.comunicaciones.mail_account import MailAccount, MailChannel, MailValidation
from services.comunicaciones import mail_account_service as mail_svc
from services.comunicaciones.mail_account_service import MailConfigError, ResolvedMail
from services.comunicaciones.mail_crypto import decrypt_secret, encrypt_secret
from services.comunicaciones.smtp_transport import (
    MailTransportError,
    SmtpConfig,
    ValidationOutcome,
    classify_smtp_error,
)


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.setenv("SECRET_KEY", "test-mail-crypto-key-please-change")
    monkeypatch.setenv("MAIL_CREDENTIALS_KEY", "test-mail-crypto-key-please-change")
    engine = create_engine("sqlite:///:memory:", future=True)
    Rol.__table__.create(engine, checkfirst=True)
    Usuario.__table__.create(engine, checkfirst=True)
    usuario_rol.create(engine, checkfirst=True)
    PasswordResetCode.__table__.create(engine, checkfirst=True)
    MailAccount.__table__.create(engine, checkfirst=True)
    MailChannel.__table__.create(engine, checkfirst=True)
    MailValidation.__table__.create(engine, checkfirst=True)
    EmailLog.__table__.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        mail_svc.seed_channels(session)
        session.commit()
        yield session
    finally:
        session.close()


def _crear(db: Session, **kwargs) -> MailAccount:
    data = dict(
        nombre="Cobranza Athletic",
        from_email="cobranza@test.cl",
        from_name="Cobranza",
        provider="SMTP",
        host="smtp.test.cl",
        port=465,
        security="SSL",
        username="cobranza@test.cl",
        password="SmtpPassw0rd!",
    )
    data.update(kwargs)
    c = mail_svc.crear_cuenta(db, **data)
    db.commit()
    db.refresh(c)
    return c


def test_permiso_solo_admin() -> None:
    assert usuario_puede_gestionar_correo({"roles": ["ADMIN"]}) is True
    assert usuario_puede_gestionar_correo({"roles": ["FINANZAS"]}) is False
    assert usuario_puede_gestionar_correo(None) is False


def test_hub_correo_rechaza_sin_admin() -> None:
    from starlette.requests import Request

    from routes.ui import admin_correo as ui_correo

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/seguridad/correo",
        "raw_path": b"/seguridad/correo",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    req = Request(scope)
    req.state.auth_user = {"roles": ["FINANZAS"], "uid": 2}
    resp = ui_correo.correo_hub(req, db=None)
    assert resp.status_code == 303
    location = resp.headers.get("location") or ""
    assert location.startswith("/?")
    assert "permiso" in location.lower()


def test_formulario_no_expone_secreto() -> None:
    from core.paths import TEMPLATES_DIR

    html = (TEMPLATES_DIR / "seguridad" / "correo_form.html").read_text(encoding="utf-8")
    assert "secret_encrypted" not in html
    assert "Dejar vacío para no cambiar" in html


def test_crear_cuenta_cifra_password(db: Session) -> None:
    c = _crear(db)
    assert c.secret_encrypted.startswith("evmail1:")
    assert "SmtpPassw0rd!" not in c.secret_encrypted
    assert decrypt_secret(c.secret_encrypted) == "SmtpPassw0rd!"
    dumped = str(c.__dict__)
    assert "SmtpPassw0rd!" not in dumped


def test_editar_sin_password_conserva_secreto(db: Session) -> None:
    c = _crear(db)
    old = c.secret_encrypted
    mail_svc.actualizar_cuenta(
        db,
        int(c.id),
        nombre="Cobranza 2",
        from_email=c.from_email,
        from_name=c.from_name,
        provider=c.provider,
        host=c.host,
        port=c.port,
        security=c.security,
        username=c.username,
        password=None,
    )
    db.commit()
    db.refresh(c)
    assert c.nombre == "Cobranza 2"
    assert c.secret_encrypted == old


def test_reemplazo_seguro_de_password(db: Session) -> None:
    c = _crear(db)
    mail_svc.actualizar_cuenta(
        db,
        int(c.id),
        nombre=c.nombre,
        from_email=c.from_email,
        from_name=c.from_name,
        provider=c.provider,
        host=c.host,
        port=c.port,
        security=c.security,
        username=c.username,
        password="NuevaClaveSMTP1",
    )
    db.commit()
    db.refresh(c)
    assert decrypt_secret(c.secret_encrypted) == "NuevaClaveSMTP1"
    assert c.status == "pendiente_validacion"


def test_validacion_exitosa_con_mock(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _crear(db)

    def _ok(cfg: SmtpConfig) -> ValidationOutcome:
        assert cfg.host == "smtp.test.cl"
        assert cfg.password == "SmtpPassw0rd!"
        return ValidationOutcome(True, "ok", "ok", 42)

    monkeypatch.setattr(mail_svc, "validate_smtp", _ok)
    row = mail_svc.validar_conexion(db, int(c.id))
    db.commit()
    assert row.ok is True
    assert row.latency_ms == 42
    db.refresh(c)
    assert c.last_ok_at is not None
    assert c.last_error is None


def test_validacion_fallida_conexion(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _crear(db)
    monkeypatch.setattr(
        mail_svc,
        "validate_smtp",
        lambda cfg: ValidationOutcome(False, "timeout", "Tiempo de espera agotado.", 12000),
    )
    row = mail_svc.validar_conexion(db, int(c.id))
    db.commit()
    assert row.ok is False
    assert row.error_code == "timeout"
    db.refresh(c)
    assert c.status == "error"


def test_validacion_fallida_autenticacion() -> None:
    err = classify_smtp_error(
        __import__("smtplib").SMTPAuthenticationError(535, b"auth failed")
    )
    assert err.code == "autenticacion"
    assert "contraseña" not in err.message.lower() or "rechazados" in err.message.lower()
    assert "535" not in err.message


def test_asignacion_y_resolucion_por_canal(db: Session) -> None:
    c = _crear(db)
    c.last_ok_at = datetime.utcnow()
    c.status = "activa"
    db.commit()
    mail_svc.asignar_canal(
        db,
        "RECUPERACION_CONTRASENA",
        cuenta_principal_id=int(c.id),
        cuenta_fallback_id=None,
    )
    db.commit()
    resolved = mail_svc.resolve_for_channel(db, "RECUPERACION_CONTRASENA")
    assert resolved is not None
    assert resolved.account is not None
    assert int(resolved.account.id) == int(c.id)
    assert resolved.used_legacy is False
    assert resolved.config.from_email == "cobranza@test.cl"


def test_bloqueo_cuenta_inactiva(db: Session) -> None:
    c = _crear(db)
    c.status = "inactiva"
    db.commit()
    mail_svc.asignar_canal(db, "COBRANZA", cuenta_principal_id=int(c.id), cuenta_fallback_id=None)
    db.commit()
    with pytest.raises(MailConfigError) as ei:
        mail_svc.resolve_for_channel(db, "COBRANZA")
    assert ei.value.code == "cuenta_inactiva"


def test_activar_requiere_validacion(db: Session) -> None:
    c = _crear(db)
    with pytest.raises(MailConfigError) as ei:
        mail_svc.cambiar_estado(db, int(c.id), "activa")
    assert ei.value.code == "no_validada"


def test_canal_sin_asignacion_devuelve_none(db: Session) -> None:
    assert mail_svc.resolve_for_channel(db, "COBRANZA") is None


def test_recuperacion_usa_cuenta_asignada(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from crud.auth.usuarios import hash_password
    from services.auth import password_reset as reset_svc

    c = _crear(db, nombre="TI Soporte", from_email="ti@test.cl", username="ti@test.cl")
    c.last_ok_at = datetime.utcnow()
    c.status = "activa"
    u = Usuario(
        id=1,
        email="user@test.cl",
        password_hash=hash_password("AntiguaClave1"),
        nombre_completo="User",
        activo=True,
    )
    db.add(u)
    db.commit()
    mail_svc.asignar_canal(
        db, "RECUPERACION_CONTRASENA", cuenta_principal_id=int(c.id), cuenta_fallback_id=None
    )
    db.commit()

    sent: list[str] = []

    def _fake_send(cfg: SmtpConfig, **kwargs):
        sent.append(cfg.from_email)
        assert kwargs["to"] == ["user@test.cl"]
        assert "Código de recuperación" in kwargs["subject"]
        body = kwargs.get("text_body") or ""
        assert "SmtpPassw0rd" not in body
        return {"ok": True}

    monkeypatch.setattr("services.comunicaciones.smtp_transport.send_with_config", _fake_send)

    result = reset_svc.request_password_reset(db, "user@test.cl", ip="127.0.0.1", secret="k" * 32)
    db.commit()
    assert result.rate_limited is False
    assert sent == ["ti@test.cl"]


def test_cobranza_usa_cuenta_asignada(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.comunicaciones.email_service import EmailService

    c = _crear(db)
    c.last_ok_at = datetime.utcnow()
    c.status = "activa"
    db.commit()
    mail_svc.asignar_canal(db, "COBRANZA", cuenta_principal_id=int(c.id), cuenta_fallback_id=None)
    db.commit()

    used: list[str] = []

    def _fake_send(cfg: SmtpConfig, **kwargs):
        used.append(cfg.from_email)
        return {"ok": True}

    monkeypatch.setattr("services.comunicaciones.smtp_transport.send_with_config", _fake_send)
    svc = EmailService(host="legacy", port=465, username="legacy@x.cl", password="x", from_name="L")
    svc.send_email(to="cliente@test.cl", subject="Aviso", html_body="<p>x</p>", db=db, channel_code="COBRANZA")
    assert used == ["cobranza@test.cl"]


def test_auditoria_envio_sin_secretos(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.comunicaciones.email_service import EmailService

    c = _crear(db)
    c.last_ok_at = datetime.utcnow()
    c.status = "activa"
    db.commit()
    mail_svc.asignar_canal(db, "COBRANZA", cuenta_principal_id=int(c.id), cuenta_fallback_id=None)
    db.commit()
    monkeypatch.setattr(
        "services.comunicaciones.smtp_transport.send_with_config",
        lambda cfg, **kwargs: {"ok": True},
    )
    svc = EmailService(host="legacy", port=465, username="legacy@x.cl", password="x", from_name="L")
    log = svc.send_and_log(
        db=db,
        modulo="COBRANZA",
        evento="RECORDATORIO",
        to="cliente@test.cl",
        subject="Recordatorio",
        html_body="<p>hola</p>",
        meta={"password": "no-guardar", "code": "123456"},
        include_detalle=False,
    )
    db.commit()
    meta = json.loads(log.meta_json or "{}")
    assert meta.get("channel") == "COBRANZA"
    assert int(meta.get("mail_account_id")) == int(c.id)
    assert log.status == "ENVIADO"
    assert "no-guardar" not in (log.meta_json or "")
    assert "123456" not in (log.meta_json or "")


def test_encrypt_roundtrip() -> None:
    os.environ["MAIL_CREDENTIALS_KEY"] = "unit-test-key"
    token = encrypt_secret("abcDEF12!!")
    assert decrypt_secret(token) == "abcDEF12!!"
    with pytest.raises(Exception):
        encrypt_secret("   ")
