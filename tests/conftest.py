# tests/conftest.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _default_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita validaciones estrictas de producción al importar Settings en tests."""
    if not os.getenv("APP_ENV"):
        monkeypatch.setenv("APP_ENV", "development")
