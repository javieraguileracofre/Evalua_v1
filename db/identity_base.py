# db/identity_base.py
# -*- coding: utf-8 -*-
"""Base declarativa de erp_identity. No mezcla tablas operacionales del ERP."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class IdentityBase(DeclarativeBase):
    pass
