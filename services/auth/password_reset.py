# services/auth/password_reset.py
# -*- coding: utf-8 -*-
"""Recuperación de contraseña: códigos de un solo uso, hasheados, con vencimiento y rate limit."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import settings
from crud.auth.usuarios import establecer_password, get_usuario_por_email, validar_politica_password
from models.auth.password_reset import PasswordResetCode


def _code_model():
    if settings.database_per_company:
        from models.identity.models import IdentityPasswordResetCode

        return IdentityPasswordResetCode
    return PasswordResetCode


def _find_account(db: Session, email: str):
    if settings.database_per_company:
        from models.identity.models import IdentityUser

        return db.scalar(select(IdentityUser).where(IdentityUser.email == email))
    return get_usuario_por_email(db, email)


def _store_password(db: Session, user_id: int, password: str) -> None:
    if settings.database_per_company:
        from crud.auth.usuarios import hash_password
        from models.identity.models import IdentityUser

        user = db.get(IdentityUser, int(user_id))
        if user is None:
            return
        user.password_hash = hash_password(password)
        user.session_version = int(user.session_version or 1) + 1
        db.add(user)
        return
    establecer_password(db, int(user_id), password)

logger = logging.getLogger("evalua.auth.reset")

GENERIC_REQUEST_MESSAGE = (
    "Si el correo está registrado, recibirás un código de recuperación."
)
GENERIC_CODE_MESSAGE = "El código es inválido o ha expirado."
RATE_LIMIT_MESSAGE = "Se alcanzó el límite de solicitudes. Intente nuevamente en unos minutos."
PASSWORD_MISMATCH_MESSAGE = "Las contraseñas no coinciden."
RESET_SUCCESS_MESSAGE = "La contraseña se actualizó correctamente. Ya puedes iniciar sesión."

CODE_TTL = timedelta(minutes=5)
CODE_DIGITS = 8
REQUEST_WINDOW = timedelta(minutes=15)
MAX_REQUESTS_PER_EMAIL = 3
MAX_REQUESTS_PER_IP = 10
MAX_FAILED_ATTEMPTS = 5

SendResetEmail = Callable[[str, str], None]


@dataclass(frozen=True)
class ResetRequestResult:
    message: str
    rate_limited: bool = False


@dataclass(frozen=True)
class VerifyResetResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class ResetPasswordResult:
    ok: bool
    message: str


def _now(now: datetime | None) -> datetime:
    return now or datetime.utcnow()


def _resolve_secret(secret: str | None) -> str:
    if secret and secret.strip():
        return secret.strip()
    env = os.getenv("SECRET_KEY", "").strip()
    if env:
        return env
    try:
        from core.config import settings

        return str(settings.secret_key)
    except Exception:
        return "change-me-now"


def _hmac_hex(secret: str, context: str, value: str) -> str:
    msg = f"{context}:{value}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _email_hmac(secret: str, email: str) -> str:
    return _hmac_hex(secret, "pwdreset-email", (email or "").strip().lower())


def _ip_hmac(secret: str, ip: str | None) -> str:
    raw = (ip or "unknown").strip() or "unknown"
    return _hmac_hex(secret, "pwdreset-ip", raw)


def _code_hash(secret: str, user_id: int | None, code: str) -> str:
    uid = int(user_id or 0)
    normalized = "".join(ch for ch in (code or "") if ch.isalnum())
    return _hmac_hex(secret, f"pwdreset-code:{uid}", normalized)


def _dummy_compare(secret: str, code: str) -> None:
    """Trabajo constante cuando no hay usuario/código, para no filtrar existencia por timing."""
    dummy = _code_hash(secret, 0, code or "00000000")
    hmac.compare_digest(dummy, dummy)


def generate_reset_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _count_recent_requests(
    db: Session,
    *,
    column,
    value: str,
    since: datetime,
) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(_code_model())
            .where(column == value, _code_model().created_at >= since)
        )
        or 0
    )


def _is_rate_limited(
    db: Session,
    *,
    secret: str,
    email: str,
    ip: str | None,
    now: datetime,
) -> bool:
    since = now - REQUEST_WINDOW
    email_n = _count_recent_requests(
        db, column=_code_model().email_hmac, value=_email_hmac(secret, email), since=since
    )
    if email_n >= MAX_REQUESTS_PER_EMAIL:
        return True
    if not (ip or "").strip():
        return False
    ip_n = _count_recent_requests(
        db, column=_code_model().request_ip_hmac, value=_ip_hmac(secret, ip), since=since
    )
    return ip_n >= MAX_REQUESTS_PER_IP


def _invalidate_active_codes(db: Session, user_id: int, now: datetime) -> None:
    rows = db.scalars(
        select(_code_model()).where(
            _code_model().user_id == int(user_id),
            _code_model().used_at.is_(None),
            _code_model().invalidated_at.is_(None),
        )
    ).all()
    for row in rows:
        row.invalidated_at = now
        db.add(row)


def _active_code_for_user(db: Session, user_id: int, now: datetime):
    return db.scalars(
        select(_code_model())
        .where(
            _code_model().user_id == int(user_id),
            _code_model().used_at.is_(None),
            _code_model().invalidated_at.is_(None),
            _code_model().expires_at > now,
        )
        .order_by(_code_model().created_at.desc())
    ).first()


def _default_send_email(to_email: str, code: str, db: Session | None = None) -> None:
    from services.comunicaciones.email_service import email_service

    email_service.send_password_reset_code(
        to_email=to_email, code=code, expires_minutes=5, db=db
    )


def request_password_reset(
    db: Session,
    email: str,
    *,
    ip: str | None = None,
    secret: str | None = None,
    send_email: SendResetEmail | None = None,
    now: datetime | None = None,
) -> ResetRequestResult:
    """
    Siempre responde el mismo mensaje genérico (no enumera cuentas).
    Si el correo existe y la cuenta está activa, genera un código, invalida los anteriores y envía email.
    """
    current = _now(now)
    key = _resolve_secret(secret)
    normalized = normalize_email(email)

    if not normalized or "@" not in normalized:
        _dummy_compare(key, "00000000")
        return ResetRequestResult(message=GENERIC_REQUEST_MESSAGE)

    if _is_rate_limited(db, secret=key, email=normalized, ip=ip, now=current):
        logger.info("Recuperación de contraseña limitada por tasa")
        return ResetRequestResult(message=RATE_LIMIT_MESSAGE, rate_limited=True)

    usuario = _find_account(db, normalized)
    email_h = _email_hmac(key, normalized)
    ip_h = _ip_hmac(key, ip)

    if usuario is None or not usuario.activo:
        _dummy_compare(key, "00000000")
        db.add(
            _code_model()(
                user_id=None,
                email_hmac=email_h,
                code_hash=_code_hash(key, None, generate_reset_code()),
                expires_at=current + CODE_TTL,
                used_at=current,
                invalidated_at=current,
                failed_attempts=0,
                request_ip_hmac=ip_h,
                created_at=current,
            )
        )
        db.flush()
        return ResetRequestResult(message=GENERIC_REQUEST_MESSAGE)

    _invalidate_active_codes(db, int(usuario.id), current)
    plain_code = generate_reset_code()
    row = _code_model()(
        user_id=int(usuario.id),
        email_hmac=email_h,
        code_hash=_code_hash(key, int(usuario.id), plain_code),
        expires_at=current + CODE_TTL,
        used_at=None,
        invalidated_at=None,
        failed_attempts=0,
        request_ip_hmac=ip_h,
        created_at=current,
    )
    db.add(row)
    db.flush()

    sender = send_email
    try:
        if sender is not None:
            sender(str(usuario.email), plain_code)
        else:
            _default_send_email(str(usuario.email), plain_code, db=db)
    except Exception:
        logger.exception("No se pudo enviar el correo de recuperación user_id=%s", usuario.id)
        row.invalidated_at = current
        row.used_at = current
        db.add(row)
        db.flush()

    try:
        from core.security_log import security_event

        security_event("password_reset_requested", uid=int(usuario.id))
    except Exception:
        pass
    return ResetRequestResult(message=GENERIC_REQUEST_MESSAGE)


def verify_reset_code(
    db: Session,
    email: str,
    code: str,
    *,
    secret: str | None = None,
    now: datetime | None = None,
) -> VerifyResetResult:
    current = _now(now)
    key = _resolve_secret(secret)
    normalized = normalize_email(email)
    supplied = "".join(ch for ch in (code or "") if ch.isalnum())

    usuario = _find_account(db, normalized) if normalized else None
    if usuario is None or not usuario.activo:
        _dummy_compare(key, supplied)
        return VerifyResetResult(ok=False, message=GENERIC_CODE_MESSAGE)

    row = _active_code_for_user(db, int(usuario.id), current)
    if row is None:
        _dummy_compare(key, supplied)
        return VerifyResetResult(ok=False, message=GENERIC_CODE_MESSAGE)

    expected = row.code_hash
    actual = _code_hash(key, int(usuario.id), supplied)
    if not hmac.compare_digest(expected, actual):
        row.failed_attempts = int(row.failed_attempts or 0) + 1
        if row.failed_attempts >= MAX_FAILED_ATTEMPTS:
            row.invalidated_at = current
            logger.info("Código de recuperación invalidado por intentos fallidos user_id=%s", usuario.id)
        db.add(row)
        db.flush()
        return VerifyResetResult(ok=False, message=GENERIC_CODE_MESSAGE)

    return VerifyResetResult(ok=True, message="Código verificado. Puede definir una nueva contraseña.")


def reset_password_with_code(
    db: Session,
    email: str,
    code: str,
    new_password: str,
    confirm_password: str,
    *,
    secret: str | None = None,
    now: datetime | None = None,
) -> ResetPasswordResult:
    if (new_password or "") != (confirm_password or ""):
        return ResetPasswordResult(ok=False, message=PASSWORD_MISMATCH_MESSAGE)

    try:
        validar_politica_password(new_password)
    except ValueError as exc:
        return ResetPasswordResult(ok=False, message=str(exc))

    current = _now(now)
    key = _resolve_secret(secret)
    normalized = normalize_email(email)
    supplied = "".join(ch for ch in (code or "") if ch.isalnum())

    usuario = _find_account(db, normalized) if normalized else None
    if usuario is None or not usuario.activo:
        _dummy_compare(key, supplied)
        return ResetPasswordResult(ok=False, message=GENERIC_CODE_MESSAGE)

    row = _active_code_for_user(db, int(usuario.id), current)
    if row is None:
        _dummy_compare(key, supplied)
        return ResetPasswordResult(ok=False, message=GENERIC_CODE_MESSAGE)

    expected = row.code_hash
    actual = _code_hash(key, int(usuario.id), supplied)
    if not hmac.compare_digest(expected, actual):
        row.failed_attempts = int(row.failed_attempts or 0) + 1
        if row.failed_attempts >= MAX_FAILED_ATTEMPTS:
            row.invalidated_at = current
        db.add(row)
        db.flush()
        return ResetPasswordResult(ok=False, message=GENERIC_CODE_MESSAGE)

    _store_password(db, int(usuario.id), new_password)
    row.used_at = current
    db.add(row)
    _invalidate_active_codes(db, int(usuario.id), current)
    db.flush()
    try:
        from core.security_log import security_event

        security_event("password_reset_completed", uid=int(usuario.id))
    except Exception:
        pass
    return ResetPasswordResult(ok=True, message=RESET_SUCCESS_MESSAGE)


def issue_reset_ok_token(
    db: Session,
    email: str,
    *,
    secret: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """Prueba HMAC de verificación exitosa; no incluye el PIN en claro."""
    current = _now(now)
    key = _resolve_secret(secret)
    normalized = normalize_email(email)
    usuario = _find_account(db, normalized) if normalized else None
    if usuario is None or not usuario.activo:
        return None
    row = _active_code_for_user(db, int(usuario.id), current)
    if row is None:
        return None
    return _hmac_hex(key, "pwdreset-ok", f"{int(usuario.id)}:{int(row.id)}")


def reset_password_with_ok_token(
    db: Session,
    email: str,
    token: str,
    new_password: str,
    confirm_password: str,
    *,
    secret: str | None = None,
    now: datetime | None = None,
) -> ResetPasswordResult:
    if (new_password or "") != (confirm_password or ""):
        return ResetPasswordResult(ok=False, message=PASSWORD_MISMATCH_MESSAGE)
    try:
        validar_politica_password(new_password)
    except ValueError as exc:
        return ResetPasswordResult(ok=False, message=str(exc))

    current = _now(now)
    key = _resolve_secret(secret)
    normalized = normalize_email(email)
    supplied = (token or "").strip()
    usuario = _find_account(db, normalized) if normalized else None
    if usuario is None or not usuario.activo:
        _dummy_compare(key, supplied or "x")
        return ResetPasswordResult(ok=False, message=GENERIC_CODE_MESSAGE)
    row = _active_code_for_user(db, int(usuario.id), current)
    if row is None:
        _dummy_compare(key, supplied or "x")
        return ResetPasswordResult(ok=False, message=GENERIC_CODE_MESSAGE)
    expected = _hmac_hex(key, "pwdreset-ok", f"{int(usuario.id)}:{int(row.id)}")
    if not supplied or not hmac.compare_digest(expected, supplied):
        _dummy_compare(key, supplied or "x")
        return ResetPasswordResult(ok=False, message=GENERIC_CODE_MESSAGE)

    _store_password(db, int(usuario.id), new_password)
    row.used_at = current
    db.add(row)
    _invalidate_active_codes(db, int(usuario.id), current)
    db.flush()
    try:
        from core.security_log import security_event

        security_event("password_reset_completed", uid=int(usuario.id))
    except Exception:
        pass
    return ResetPasswordResult(ok=True, message=RESET_SUCCESS_MESSAGE)
