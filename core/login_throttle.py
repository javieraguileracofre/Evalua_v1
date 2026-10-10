# core/login_throttle.py
# -*- coding: utf-8 -*-
"""Límite de intentos de login por IP y por email (memoria de proceso)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict

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


def is_login_blocked(*, email: str, ip: str | None) -> bool:
    now = time.monotonic()
    em = (email or "").strip().lower()
    ipk = (ip or "unknown").strip() or "unknown"
    with _lock:
        if em and _email_lockout_until.get(em, 0) > now:
            return True
        if _ip_lockout_until.get(ipk, 0) > now:
            return True
        email_n = len(_prune(_email_hits.get(em, []), now)) if em else 0
        ip_n = len(_prune(_ip_hits.get(ipk, []), now))
        return email_n >= MAX_PER_EMAIL or ip_n >= MAX_PER_IP


def register_login_failure(*, email: str, ip: str | None) -> None:
    now = time.monotonic()
    em = (email or "").strip().lower()
    ipk = (ip or "unknown").strip() or "unknown"
    with _lock:
        if em:
            hits = _prune(_email_hits[em], now)
            hits.append(now)
            _email_hits[em] = hits
            if len(hits) >= MAX_PER_EMAIL:
                _email_lockout_until[em] = now + LOCKOUT_SECONDS
        ip_hits = _prune(_ip_hits[ipk], now)
        ip_hits.append(now)
        _ip_hits[ipk] = ip_hits
        if len(ip_hits) >= MAX_PER_IP:
            _ip_lockout_until[ipk] = now + LOCKOUT_SECONDS


def register_login_success(*, email: str, ip: str | None) -> None:
    em = (email or "").strip().lower()
    ipk = (ip or "unknown").strip() or "unknown"
    with _lock:
        if em:
            _email_hits.pop(em, None)
            _email_lockout_until.pop(em, None)
        _ip_hits.pop(ipk, None)
        _ip_lockout_until.pop(ipk, None)
