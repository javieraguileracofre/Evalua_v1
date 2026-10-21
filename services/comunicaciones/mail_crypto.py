# services/comunicaciones/mail_crypto.py
# -*- coding: utf-8 -*-
"""Cifrado en reposo de secretos SMTP (Fernet). Nunca loguear el plaintext."""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "evmail1:"


class MailCryptoError(ValueError):
    pass


def _fernet() -> Fernet:
    raw = (os.getenv("MAIL_CREDENTIALS_KEY") or os.getenv("SECRET_KEY") or "").strip()
    if not raw:
        try:
            from core.config import settings

            raw = str(settings.secret_key or "").strip()
        except Exception:
            raw = ""
    if not raw:
        raise MailCryptoError("No hay clave de cifrado (MAIL_CREDENTIALS_KEY o SECRET_KEY).")
    digest = hashlib.sha256(f"evalua-mail-v1:{raw}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    value = (plain or "").strip()
    if not value:
        raise MailCryptoError("La contraseña de la cuenta de correo no puede estar vacía.")
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_secret(stored: str) -> str:
    raw = (stored or "").strip()
    if not raw:
        raise MailCryptoError("La cuenta no tiene credencial guardada.")
    if not raw.startswith(_PREFIX):
        raise MailCryptoError("El secreto almacenado no es un valor cifrado válido.")
    token = raw[len(_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise MailCryptoError(
            "No se pudo descifrar la credencial. Si rotó MAIL_CREDENTIALS_KEY, vuelva a guardar la contraseña."
        ) from exc
