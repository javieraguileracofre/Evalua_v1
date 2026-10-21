# services/platform/alembic_support.py
# -*- coding: utf-8 -*-
"""Carga la librería Alembic, no la carpeta de migraciones del proyecto."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

from core.paths import PROJECT_ROOT

_LOADED: tuple | None = None


def load_alembic():
    """Devuelve (alembic.command, alembic.config.Config).

    La carpeta `alembic/` del repositorio no tiene `__init__.py`. Si la raíz
    del proyecto está en sys.path, Python la toma como paquete y tapa la
    librería instalada.
    """
    global _LOADED
    if _LOADED is not None:
        return _LOADED

    root = PROJECT_ROOT.resolve()
    saved_path = list(sys.path)
    shadowed = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name == "alembic" or name.startswith("alembic.")
    }

    def _is_project(entry: str) -> bool:
        if entry in {"", "."}:
            return True
        try:
            return Path(entry).resolve() == root
        except OSError:
            return False

    sys.path[:] = [entry for entry in saved_path if not _is_project(entry)]
    try:
        command = importlib.import_module("alembic.command")
        config_mod = importlib.import_module("alembic.config")
        importlib.import_module("alembic.context")
        if not hasattr(command, "stamp") or not hasattr(command, "upgrade"):
            raise ImportError("La librería Alembic instalada no está completa.")
        _LOADED = (command, config_mod.Config)
        return _LOADED
    except Exception:
        sys.modules.update(shadowed)
        raise
    finally:
        sys.path[:] = saved_path
