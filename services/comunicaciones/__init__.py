# services/comunicaciones/__init__.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from .email_service import email_service, enviar_recordatorio_cobranza, EmailService

__all__ = [
    "EmailService",
    "email_service",
    "enviar_recordatorio_cobranza",
]