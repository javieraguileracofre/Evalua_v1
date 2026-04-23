# routes/ui/__init__.py
# -*- coding: utf-8 -*-

from . import inicio
from . import home
from . import cliente
from . import inventario
from . import ventas_pos
from . import cobranza
from . import finanzas
from . import fin_periodos
from . import cuentas_por_pagar
from . import taller

__all__ = [
    "inicio",
    "home",
    "cliente",
    "inventario",
    "ventas_pos",
    "cobranza",
    "finanzas",
    "fin_periodos",
    "cuentas_por_pagar",
    "taller",
]