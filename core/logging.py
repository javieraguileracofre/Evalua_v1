# core/logging.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import re

from core.config import settings

_SECRET_URL = re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s'\"<>]+", re.IGNORECASE)
_SECRET_ASSIGN = re.compile(
    r"(?i)\b(password|passwd|encrypted_secret|db_password)\b\s*[:=]\s*\S+"
)


def redact_secrets(text: str) -> str:
    cleaned = _SECRET_URL.sub("postgresql://***", text or "")
    return _SECRET_ASSIGN.sub(r"\1=***", cleaned)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    formatter = RedactingFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)