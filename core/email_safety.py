# core/email_safety.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def strip_header_injection(value: str | None, *, max_len: int = 200) -> str:
    s = (value or "").replace("\r", " ").replace("\n", " ").replace("\x00", "")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[:max_len]
    return s


def is_valid_email_address(value: str | None) -> bool:
    s = strip_header_injection(value, max_len=254)
    if not s or len(s) > 254:
        return False
    return bool(_EMAIL_RE.match(s))
