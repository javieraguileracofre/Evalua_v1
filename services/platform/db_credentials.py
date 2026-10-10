# services/platform/db_credentials.py
# -*- coding: utf-8 -*-
"""Cifrado de secretos PostgreSQL. Prefijo distinto al de mail_crypto."""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "evdb1:"


class DbCredentialError(ValueError):
    pass


def _fernet() -> Fernet:
    raw = (os.getenv("DB_CREDENTIALS_KEY") or "").strip()
    if not raw:
        try:
            from core.config import settings

            raw = str(settings.db_credentials_key or "").strip()
        except Exception:
            raw = ""
    if not raw:
        raise DbCredentialError("DB_CREDENTIALS_KEY no está configurada.")
    digest = hashlib.sha256(f"evalua-db-v1:{raw}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_db_secret(plain: str) -> str:
    value = plain or ""
    if not value.strip():
        raise DbCredentialError("El secreto de base de datos está vacío.")
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_db_secret(stored: str) -> str:
    raw = (stored or "").strip()
    if not raw.startswith(_PREFIX):
        raise DbCredentialError("El secreto almacenado no es un valor cifrado válido.")
    try:
        return _fernet().decrypt(raw[len(_PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise DbCredentialError("No se pudo descifrar la credencial de la base.") from exc
