# models/comunicaciones/__init__.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from .email_log import EmailLog
from .mail_account import MailAccount, MailChannel, MailValidation

__all__ = ["EmailLog", "MailAccount", "MailChannel", "MailValidation"]