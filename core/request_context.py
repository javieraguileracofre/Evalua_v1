# core/request_context.py
# -*- coding: utf-8 -*-
"""Contexto de correlación por request (request_id, company, actor)."""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("evalua_request_id", default=None)
_company_id: ContextVar[int | None] = ContextVar("evalua_company_id", default=None)
_actor_id: ContextVar[int | None] = ContextVar("evalua_actor_id", default=None)
_module: ContextVar[str | None] = ContextVar("evalua_module", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def set_request_context(
    *,
    request_id: str | None = None,
    company_id: int | None = None,
    actor_id: int | None = None,
    module: str | None = None,
) -> None:
    if request_id is not None:
        _request_id.set(request_id)
    if company_id is not None:
        _company_id.set(company_id)
    if actor_id is not None:
        _actor_id.set(actor_id)
    if module is not None:
        _module.set(module)


def clear_request_context() -> None:
    _request_id.set(None)
    _company_id.set(None)
    _actor_id.set(None)
    _module.set(None)


def get_request_context() -> dict[str, Any]:
    return {
        "request_id": _request_id.get(),
        "company_id": _company_id.get(),
        "actor_id": _actor_id.get(),
        "module": _module.get(),
    }
