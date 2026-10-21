# modules/cobranza — contrato público de cobranzas / CxC.
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from services.cobranza.pago_service import contabilizar_pago_cliente as _contabilizar_pago_cliente


def registrar_pago_cliente(
    db: Session,
    *,
    pago_id: int,
    usuario: Optional[str] = None,
    actualizar_cxc: bool = True,
) -> None:
    """
    Caso de uso: aplicar pago a CxC + caja + asiento en una sola transacción,
    y emitir PagoRealizado tras confirmar.
    """
    return _contabilizar_pago_cliente(
        db,
        pago_id=pago_id,
        usuario=usuario,
        actualizar_cxc=actualizar_cxc,
    )


# Alias retrocompatible
contabilizar_pago_cliente = registrar_pago_cliente

__all__ = ["registrar_pago_cliente", "contabilizar_pago_cliente"]
