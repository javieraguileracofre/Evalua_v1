# core/json_script.py
# -*- coding: utf-8 -*-
"""JSON embebible en <script> sin romper el tag ni permitir XSS."""
from __future__ import annotations

import json
from typing import Any


def json_for_script(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, default=str)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
