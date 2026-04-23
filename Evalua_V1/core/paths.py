# core/paths.py
# -*- coding: utf-8 -*-
"""Rutas de archivos del proyecto (independientes del cwd al arrancar Uvicorn)."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
