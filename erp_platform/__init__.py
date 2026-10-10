# erp_platform/__init__.py
# -*- coding: utf-8 -*-
"""
PLATFORM / CORE — capacidades transversales de Evalua ERP.

Paquete Python: `erp_platform` (evita sombrear stdlib `platform`).

Identity · Tenancy · RBAC · Security · Audit · Email · Events · Operations

Los módulos ERP deben depender de `erp_platform`, no al revés.
"""
from __future__ import annotations

__all__ = [
    "registry",
    "events",
    "permissions",
]
