# services/tesoreria/crypto.py
# -*- coding: utf-8 -*-
"""Cifrado en reposo de la clave tributaria. Nunca loguear el plaintext."""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "evsii1:"


class SiiCryptoError(ValueError):
    pass


def _fernet() -> Fernet:
    raw = (os.getenv("SII_CREDENTIALS_KEY") or os.getenv("SECRET_KEY") or "").strip()
    if not raw:
        try:
            from core.config import settings

            raw = str(settings.secret_key or "").strip()
        except Exception:
            raw = ""
    if not raw:
        raise SiiCryptoError("No hay clave de cifrado (SII_CREDENTIALS_KEY o SECRET_KEY).")
    digest = hashlib.sha256(f"evalua-sii-v1:{raw}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    value = plain or ""
    if not value.strip():
        raise SiiCryptoError("La clave tributaria no puede estar vacía.")
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_secret(stored: str) -> str:
    raw = (stored or "").strip()
    if not raw:
        raise SiiCryptoError("La empresa no tiene clave tributaria guardada.")
    if not raw.startswith(_PREFIX):
        raise SiiCryptoError("El secreto almacenado no es un valor cifrado válido.")
    token = raw[len(_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise SiiCryptoError(
            "No se pudo descifrar la clave tributaria. Si rotó SII_CREDENTIALS_KEY, vuelva a guardarla."
        ) from exc
