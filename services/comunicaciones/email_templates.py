# services/comunicaciones/email_templates.py
# -*- coding: utf-8 -*-
"""Plantillas de correo seguras (solo variables, sin ejecución de código)."""
from __future__ import annotations

import re
from html import escape
from typing import Any

_VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def _resolve(path: str, ctx: dict[str, Any]) -> str:
    cur: Any = ctx
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
        if cur is None:
            return ""
    return str(cur)


def render_template(template: str, context: dict[str, Any], *, html: bool = True) -> str:
    """Sustituye {{ var }} / {{ a.b }}. Escapa HTML si html=True."""

    def repl(match: re.Match[str]) -> str:
        value = _resolve(match.group(1), context)
        return escape(value) if html else value

    return _VAR.sub(repl, template or "")


TEMPLATES: dict[str, dict[str, str]] = {
    "password_reset": {
        "subject": "Código de recuperación · {{ company.name }}",
        "html": (
            "<p>Hola {{ user.name }},</p>"
            "<p>Su código de recuperación es <strong>{{ code }}</strong>.</p>"
            "<p>Si no solicitó este cambio, ignore este mensaje.</p>"
            "<p>{{ company.name }}</p>"
        ),
        "text": (
            "Hola {{ user.name }},\n\n"
            "Su código de recuperación es {{ code }}.\n"
            "Si no solicitó este cambio, ignore este mensaje.\n\n"
            "{{ company.name }}\n"
        ),
    },
    "user_welcome": {
        "subject": "Bienvenido a {{ company.name }}",
        "html": (
            "<p>Hola {{ user.name }},</p>"
            "<p>Se creó su acceso a Evalua ERP para <strong>{{ company.name }}</strong>.</p>"
            "<p>Usuario: {{ user.email }}</p>"
        ),
        "text": (
            "Hola {{ user.name }},\n\n"
            "Se creó su acceso a Evalua ERP para {{ company.name }}.\n"
            "Usuario: {{ user.email }}\n"
        ),
    },
}


def build_message(template_key: str, context: dict[str, Any]) -> dict[str, str]:
    tpl = TEMPLATES.get(template_key)
    if not tpl:
        raise ValueError(f"Plantilla de correo desconocida: {template_key}")
    return {
        "subject": render_template(tpl["subject"], context, html=False),
        "html": render_template(tpl["html"], context, html=True),
        "text": render_template(tpl["text"], context, html=False),
    }
