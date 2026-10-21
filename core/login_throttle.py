# core/login_throttle.py
# -*- coding: utf-8 -*-
"""Cupo de login por correo y por IP.

El contador de referencia vive en base (auth_login_attempts o
identity_login_attempts) para que varios procesos compartan el bloqueo.
Si la tabla no está disponible, se usa la memoria del proceso.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.config import settings

logger = logging.getLogger("evalua.auth.throttle")

WINDOW_SECONDS = 15 * 60
MAX_PER_EMAIL = 5
MAX_PER_IP = 20
LOCKOUT_SECONDS = 15 * 60

GENERIC_FAILURE = "Credenciales incorrectas o cuenta desactivada."
RATE_LIMITED_MESSAGE = GENERIC_FAILURE

_lock = threading.Lock()
_email_hits: dict[str, list[float]] = defaultdict(list)
_ip_hits: dict[str, list[float]] = defaultdict(list)
_email_lockout_until: dict[str, float] = {}
_ip_lockout_until: dict[str, float] = {}


def reset_for_tests() -> None:
    with _lock:
        _email_hits.clear()
        _ip_hits.clear()
        _email_lockout_until.clear()
        _ip_lockout_until.clear()


def _prune(bucket: list[float], now: float) -> list[float]:
    cutoff = now - WINDOW_SECONDS
    return [t for t in bucket if t >= cutoff]


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _normalize_ip(ip: str | None) -> str | None:
    raw = (ip or "").strip()
    return raw or None


def _digest(kind: str, value: str) -> str:
    secret = (settings.secret_key or "change-me-now").encode("utf-8")
    msg = f"login-{kind}:{value}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _attempt_model(explicit: type | None):
    if explicit is not None:
        return explicit
    if settings.database_per_company:
        from models.identity.models import IdentityLoginAttempt

        return IdentityLoginAttempt
    from models.auth.login_attempt import LoginAttempt

    return LoginAttempt


def _memory_blocked(*, email: str, ip: str | None, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    em = _normalize_email(email)
    ipk = _normalize_ip(ip)
    with _lock:
        if em and _email_lockout_until.get(em, 0) > current:
            return True
        if ipk and _ip_lockout_until.get(ipk, 0) > current:
            return True
        email_n = len(_prune(_email_hits.get(em, []), current)) if em else 0
        ip_n = len(_prune(_ip_hits.get(ipk, []), current)) if ipk else 0
        return email_n >= MAX_PER_EMAIL or ip_n >= MAX_PER_IP


def _memory_failure(*, email: str, ip: str | None) -> None:
    now = time.monotonic()
    em = _normalize_email(email)
    ipk = _normalize_ip(ip)
    with _lock:
        if em:
            hits = _prune(_email_hits[em], now)
            hits.append(now)
            _email_hits[em] = hits
            if len(hits) >= MAX_PER_EMAIL:
                _email_lockout_until[em] = now + LOCKOUT_SECONDS
        if ipk:
            ip_hits = _prune(_ip_hits[ipk], now)
            ip_hits.append(now)
            _ip_hits[ipk] = ip_hits
            if len(ip_hits) >= MAX_PER_IP:
                _ip_lockout_until[ipk] = now + LOCKOUT_SECONDS


def _memory_success(*, email: str, ip: str | None) -> None:
    em = _normalize_email(email)
    ipk = _normalize_ip(ip)
    with _lock:
        if em:
            _email_hits.pop(em, None)
            _email_lockout_until.pop(em, None)
        if ipk:
            _ip_hits.pop(ipk, None)
            _ip_lockout_until.pop(ipk, None)


def _count_recent(db: Session, model, column, value: str, since: datetime) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
            .where(column == value, model.created_at >= since)
        )
        or 0
    )


def _db_blocked(db: Session, model, *, email: str, ip: str | None) -> bool | None:
    since = datetime.utcnow() - timedelta(seconds=WINDOW_SECONDS)
    try:
        em = _normalize_email(email)
        if em:
            email_n = _count_recent(db, model, model.email_hmac, _digest("email", em), since)
            if email_n >= MAX_PER_EMAIL:
                return True
        ipk = _normalize_ip(ip)
        if not ipk:
            return False
        ip_n = _count_recent(db, model, model.ip_hmac, _digest("ip", ipk), since)
        return ip_n >= MAX_PER_IP
    except SQLAlchemyError:
        db.rollback()
        logger.warning("No se pudo leer el cupo de login; se usa la memoria del proceso.")
        return None


def is_login_blocked(
    *,
    email: str,
    ip: str | None,
    db: Session | None = None,
    model: type | None = None,
) -> bool:
    memory = _memory_blocked(email=email, ip=ip)
    if db is None:
        return memory
    stored = _db_blocked(db, _attempt_model(model), email=email, ip=ip)
    if stored is None:
        return memory
    return stored or memory


def register_login_failure(
    *,
    email: str,
    ip: str | None,
    db: Session | None = None,
    model: type | None = None,
) -> None:
    if db is None:
        _memory_failure(email=email, ip=ip)
        return
    attempt_model = _attempt_model(model)
    since = datetime.utcnow() - timedelta(seconds=WINDOW_SECONDS)
    em = _normalize_email(email)
    ipk = _normalize_ip(ip)
    try:
        db.execute(delete(attempt_model).where(attempt_model.created_at < since))
        db.add(
            attempt_model(
                email_hmac=_digest("email", em or "-"),
                ip_hmac=_digest("ip", ipk) if ipk else None,
                created_at=datetime.utcnow(),
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("No se pudo registrar el fallo de login; se usa la memoria del proceso.")
        _memory_failure(email=email, ip=ip)


def register_login_success(
    *,
    email: str,
    ip: str | None,
    db: Session | None = None,
    model: type | None = None,
) -> None:
    _memory_success(email=email, ip=ip)
    if db is None:
        return
    attempt_model = _attempt_model(model)
    em = _normalize_email(email)
    ipk = _normalize_ip(ip)
    try:
        with db.begin_nested():
            if em:
                db.execute(delete(attempt_model).where(attempt_model.email_hmac == _digest("email", em)))
            if ipk:
                db.execute(delete(attempt_model).where(attempt_model.ip_hmac == _digest("ip", ipk)))
    except SQLAlchemyError:
        logger.warning("No se pudo limpiar el cupo de login tras un acceso correcto.")
    db.commit()
