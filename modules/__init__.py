# modules/__init__.py
# -*- coding: utf-8 -*-
"""
Módulos ERP (bounded contexts) — modular monolith.

Cada paquete expone servicios públicos. La UI/API debe preferir
`modules.<dominio>` frente a imports cruzados de models internos.
"""
from __future__ import annotations
