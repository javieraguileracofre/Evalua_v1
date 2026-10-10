# core/company_context.py
# -*- coding: utf-8 -*-
"""Contexto de la compañía activa. El frontend no lo autoriza."""
from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class CompanyContext:
    company_id: int
    company_code: str
    legal_name: str
    trade_name: str
    rut: str
    database_id: int
    schema_version: str
    authorized: bool = False
    address: str = ""
    region: str = ""
    commune: str = ""
    phone: str = ""
    email: str = ""


_current: ContextVar[CompanyContext | None] = ContextVar("company_context", default=None)


def set_company_context(ctx: CompanyContext | None) -> Token[CompanyContext | None]:
    return _current.set(ctx)


def reset_company_context(token: Token[CompanyContext | None]) -> None:
    _current.reset(token)


def get_company_context() -> CompanyContext | None:
    return _current.get()


def document_header_text() -> str:
    ctx = get_company_context()
    if ctx is None or not ctx.authorized:
        return ""
    parts = [p for p in (ctx.legal_name.strip(), ctx.rut.strip()) if p]
    return " · ".join(parts)


def document_footer_text() -> str:
    return "Documento generado por EvaluaERP"
