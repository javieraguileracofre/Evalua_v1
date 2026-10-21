# services/comunicaciones/mail_account_service.py
# -*- coding: utf-8 -*-
"""CRUD, asignación por canal, validación y resolución de cuentas de correo."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.comunicaciones.mail_account import MailAccount, MailChannel, MailValidation
from services.comunicaciones.mail_crypto import MailCryptoError, decrypt_secret, encrypt_secret
from services.comunicaciones.smtp_transport import (
    SmtpConfig,
    ValidationOutcome,
    apply_provider_preset,
    classify_smtp_error,
    send_with_config,
    validate_smtp,
)

CHANNEL_SEED: tuple[tuple[str, str, str], ...] = (
    ("RECUPERACION_CONTRASENA", "Recuperación de contraseña", "Códigos de restablecimiento de clave del portal."),
    ("COBRANZA", "Cobranza", "Recordatorios y gestiones de cobranza."),
    ("POSTVENTA", "Postventa", "Comunicaciones de casos CRM / postventa."),
    ("COMERCIAL", "Comercial", "Cotizaciones, aceptación de crédito y avisos comerciales."),
    ("NOTIFICACIONES", "Notificaciones", "Avisos administrativos generales."),
    ("SOPORTE", "Soporte / TI", "Comunicaciones de soporte técnico."),
    ("SISTEMA", "Sistema", "Mensajes internos del ERP."),
)

STATUSES = ("pendiente_validacion", "activa", "inactiva", "error")
PROVIDERS = ("SMTP", "GMAIL", "MICROSOFT365", "OTRO")
SECURITIES = ("SSL", "STARTTLS", "NONE")


class MailConfigError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ResolvedMail:
    config: SmtpConfig
    account: MailAccount | None
    channel_code: str
    used_fallback: bool
    used_legacy: bool


def seed_channels(db: Session) -> None:
    existing = {c.codigo for c in db.scalars(select(MailChannel)).all()}
    for codigo, nombre, descripcion in CHANNEL_SEED:
        if codigo not in existing:
            db.add(MailChannel(codigo=codigo, nombre=nombre, descripcion=descripcion))
    db.flush()


def list_accounts(db: Session) -> list[MailAccount]:
    return list(db.scalars(select(MailAccount).order_by(MailAccount.nombre.asc())))


def get_account(db: Session, account_id: int) -> MailAccount | None:
    return db.get(MailAccount, int(account_id))


def list_channels(db: Session) -> list[MailChannel]:
    seed_channels(db)
    return list(
        db.scalars(
            select(MailChannel)
            .options(
                selectinload(MailChannel.cuenta_principal),
                selectinload(MailChannel.cuenta_fallback),
            )
            .order_by(MailChannel.nombre.asc())
        )
    )


def list_validations(db: Session, account_id: int, *, limite: int = 8) -> list[MailValidation]:
    return list(
        db.scalars(
            select(MailValidation)
            .where(MailValidation.account_id == int(account_id))
            .order_by(MailValidation.created_at.desc())
            .limit(max(1, min(int(limite), 30)))
        )
    )


def _normalize_account_fields(
    *,
    nombre: str,
    from_email: str,
    from_name: str,
    provider: str,
    host: str,
    port: int | str,
    security: str,
    username: str,
) -> dict[str, object]:
    nombre_n = (nombre or "").strip()
    email_n = (from_email or "").strip().lower()
    user_n = (username or "").strip()
    prov = (provider or "SMTP").strip().upper()
    if prov not in PROVIDERS:
        raise MailConfigError("datos", "Proveedor no reconocido.")
    if not nombre_n:
        raise MailConfigError("datos", "Indique un nombre descriptivo para la cuenta.")
    if not email_n or "@" not in email_n:
        raise MailConfigError("datos", "El correo remitente no es válido.")
    if not user_n:
        raise MailConfigError("datos", "Indique el usuario de autenticación SMTP.")
    try:
        port_n = int(port)
    except (TypeError, ValueError):
        raise MailConfigError("datos", "El puerto debe ser un número.") from None
    if port_n < 1 or port_n > 65535:
        raise MailConfigError("datos", "Puerto SMTP fuera de rango.")
    sec = (security or "SSL").strip().upper()
    if sec not in SECURITIES:
        raise MailConfigError("datos", "Modo de seguridad no válido.")
    host_n, port_n, sec = apply_provider_preset(prov, host, port_n, sec)
    if not host_n:
        raise MailConfigError("datos", "Indique el host SMTP.")
    return {
        "nombre": nombre_n[:120],
        "from_email": email_n[:254],
        "from_name": (from_name or "").strip()[:160] or email_n.split("@")[0],
        "provider": prov,
        "host": host_n[:255],
        "port": port_n,
        "security": sec,
        "username": user_n[:254],
    }


def crear_cuenta(
    db: Session,
    *,
    nombre: str,
    from_email: str,
    from_name: str,
    provider: str,
    host: str,
    port: int | str,
    security: str,
    username: str,
    password: str,
    created_by_id: int | None = None,
) -> MailAccount:
    fields = _normalize_account_fields(
        nombre=nombre,
        from_email=from_email,
        from_name=from_name,
        provider=provider,
        host=host,
        port=port,
        security=security,
        username=username,
    )
    cuenta = MailAccount(
        **fields,
        secret_encrypted=encrypt_secret(password),
        status="pendiente_validacion",
        created_by_id=created_by_id,
    )
    db.add(cuenta)
    db.flush()
    return cuenta


def actualizar_cuenta(
    db: Session,
    account_id: int,
    *,
    nombre: str,
    from_email: str,
    from_name: str,
    provider: str,
    host: str,
    port: int | str,
    security: str,
    username: str,
    password: str | None = None,
) -> MailAccount:
    cuenta = get_account(db, account_id)
    if not cuenta:
        raise MailConfigError("no_encontrada", "La cuenta de correo no existe.")
    fields = _normalize_account_fields(
        nombre=nombre,
        from_email=from_email,
        from_name=from_name,
        provider=provider,
        host=host,
        port=port,
        security=security,
        username=username,
    )
    for key, value in fields.items():
        setattr(cuenta, key, value)
    if password and password.strip():
        cuenta.secret_encrypted = encrypt_secret(password)
        cuenta.status = "pendiente_validacion"
        cuenta.last_ok_at = None
    cuenta.updated_at = datetime.utcnow()
    db.add(cuenta)
    db.flush()
    return cuenta


def cuenta_a_config(cuenta: MailAccount) -> SmtpConfig:
    if not cuenta.tiene_secreto:
        raise MailConfigError("credencial", "La cuenta no tiene contraseña guardada.")
    try:
        secret = decrypt_secret(cuenta.secret_encrypted)
    except MailCryptoError as exc:
        raise MailConfigError("credencial", str(exc)) from exc
    return SmtpConfig(
        host=cuenta.host,
        port=int(cuenta.port),
        username=cuenta.username,
        password=secret,
        from_email=cuenta.from_email,
        from_name=cuenta.from_name,
        security=cuenta.security,
    )


def _registrar_validacion(
    db: Session,
    cuenta: MailAccount,
    outcome: ValidationOutcome,
    *,
    kind: str,
    to_email: str | None = None,
) -> MailValidation:
    row = MailValidation(
        account_id=int(cuenta.id),
        kind=kind,
        ok=outcome.ok,
        error_code=None if outcome.ok else outcome.code,
        error_message=None if outcome.ok else outcome.message[:500],
        latency_ms=outcome.latency_ms,
        to_email=to_email,
    )
    db.add(row)
    cuenta.last_error = None if outcome.ok else outcome.message[:500]
    if outcome.ok:
        cuenta.last_ok_at = datetime.utcnow()
        if cuenta.status == "error":
            cuenta.status = "pendiente_validacion"
    else:
        cuenta.status = "error"
    cuenta.updated_at = datetime.utcnow()
    db.add(cuenta)
    db.flush()
    return row


def validar_conexion(db: Session, account_id: int) -> MailValidation:
    cuenta = get_account(db, account_id)
    if not cuenta:
        raise MailConfigError("no_encontrada", "La cuenta de correo no existe.")
    cfg = cuenta_a_config(cuenta)
    outcome = validate_smtp(cfg)
    return _registrar_validacion(db, cuenta, outcome, kind="CONNECT")


def enviar_correo_prueba(db: Session, account_id: int, to_email: str) -> MailValidation:
    cuenta = get_account(db, account_id)
    if not cuenta:
        raise MailConfigError("no_encontrada", "La cuenta de correo no existe.")
    dest = (to_email or "").strip().lower()
    if not dest or "@" not in dest:
        raise MailConfigError("datos", "Indique un destinatario de prueba válido.")
    cfg = cuenta_a_config(cuenta)
    started = datetime.utcnow()
    try:
        send_with_config(
            cfg,
            to=[dest],
            subject="Prueba de correo · Evalua ERP",
            html_body=(
                "<p>Este es un correo de prueba del módulo de cuentas de Evalua ERP.</p>"
                f"<p>Cuenta: {cuenta.nombre}</p>"
                "<p>Si lo recibió, la configuración SMTP es correcta.</p>"
            ),
            text_body="Correo de prueba de Evalua ERP. La configuración SMTP es correcta.",
        )
        latency = int((datetime.utcnow() - started).total_seconds() * 1000)
        outcome = ValidationOutcome(True, "ok", "Correo de prueba enviado.", max(latency, 1))
    except Exception as exc:
        err = classify_smtp_error(exc)
        outcome = ValidationOutcome(False, err.code, err.message, 0)
    return _registrar_validacion(db, cuenta, outcome, kind="TEST_SEND", to_email=dest)


def cambiar_estado(db: Session, account_id: int, status: str) -> MailAccount:
    cuenta = get_account(db, account_id)
    if not cuenta:
        raise MailConfigError("no_encontrada", "La cuenta de correo no existe.")
    nuevo = (status or "").strip().lower()
    if nuevo not in STATUSES:
        raise MailConfigError("datos", "Estado no válido.")
    if nuevo == "activa":
        if not cuenta.last_ok_at:
            raise MailConfigError(
                "no_validada",
                "Valide la conexión (o envíe un correo de prueba) antes de activar la cuenta.",
            )
        if cuenta.status == "error":
            raise MailConfigError("error", "La última validación falló. Corrija la cuenta y vuelva a validar.")
    cuenta.status = nuevo
    cuenta.updated_at = datetime.utcnow()
    db.add(cuenta)
    db.flush()
    return cuenta


def asignar_canal(
    db: Session,
    codigo: str,
    *,
    cuenta_principal_id: int | None,
    cuenta_fallback_id: int | None,
) -> MailChannel:
    seed_channels(db)
    canal = db.get(MailChannel, (codigo or "").strip().upper())
    if not canal:
        raise MailConfigError("datos", "Tipo de gestión desconocido.")
    principal = get_account(db, cuenta_principal_id) if cuenta_principal_id else None
    fallback = get_account(db, cuenta_fallback_id) if cuenta_fallback_id else None
    if cuenta_principal_id and not principal:
        raise MailConfigError("datos", "La cuenta principal no existe.")
    if cuenta_fallback_id and not fallback:
        raise MailConfigError("datos", "La cuenta alternativa no existe.")
    if principal and fallback and int(principal.id) == int(fallback.id):
        raise MailConfigError("datos", "La cuenta alternativa debe ser distinta de la principal.")
    canal.cuenta_principal_id = int(principal.id) if principal else None
    canal.cuenta_fallback_id = int(fallback.id) if fallback else None
    canal.updated_at = datetime.utcnow()
    db.add(canal)
    db.flush()
    return canal


def _cuenta_usable(cuenta: MailAccount | None) -> bool:
    if cuenta is None:
        return False
    return cuenta.status == "activa" and cuenta.tiene_secreto


def resolve_for_channel(db: Session | None, channel_code: str) -> ResolvedMail | None:
    """
    Devuelve la cuenta asignada al canal.
    None = no hay asignación (el caller puede usar SMTP legado de .env).
    Si hay asignación pero no es usable, lanza MailConfigError.
    """
    code = (channel_code or "").strip().upper()
    if not code or db is None:
        return None
    seed_channels(db)
    canal = db.scalars(
        select(MailChannel)
        .options(
            selectinload(MailChannel.cuenta_principal),
            selectinload(MailChannel.cuenta_fallback),
        )
        .where(MailChannel.codigo == code)
    ).first()
    if not canal:
        return None
    if not canal.cuenta_principal_id and not canal.cuenta_fallback_id:
        return None

    chosen: MailAccount | None = None
    used_fallback = False
    if _cuenta_usable(canal.cuenta_principal):
        chosen = canal.cuenta_principal
    elif _cuenta_usable(canal.cuenta_fallback):
        chosen = canal.cuenta_fallback
        used_fallback = True
    else:
        raise MailConfigError(
            "cuenta_inactiva",
            f"El tipo de gestión {code} tiene una cuenta asignada, pero no está activa o validada.",
        )
    assert chosen is not None
    return ResolvedMail(
        config=cuenta_a_config(chosen),
        account=chosen,
        channel_code=code,
        used_fallback=used_fallback,
        used_legacy=False,
    )
