# core/ui_templates.py
# -*- coding: utf-8 -*-
"""Plantillas Jinja con la firma antigua TemplateResponse(nombre, contexto).

Starlette 1.x pide el request como primer argumento. Las rutas siguen
pasando el nombre y un contexto que incluye request.
"""
from __future__ import annotations

from starlette.templating import Jinja2Templates


class EvaluaTemplates(Jinja2Templates):
    def TemplateResponse(self, *args, **kwargs):
        if args and isinstance(args[0], str):
            name = args[0]
            context = {}
            extra: tuple = ()
            if len(args) >= 2 and isinstance(args[1], dict):
                context = args[1]
                extra = args[2:]
            else:
                context = kwargs.pop("context", None) or {}
                extra = args[1:]
            request = context.get("request") or kwargs.pop("request", None)
            if request is None:
                raise RuntimeError("La plantilla necesita el request en el contexto.")
            return super().TemplateResponse(request, name, context, *extra, **kwargs)
        return super().TemplateResponse(*args, **kwargs)
