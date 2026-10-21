# erp_platform/events/sweeper.py
# -*- coding: utf-8 -*-
"""Reintenta el outbox en el mismo proceso. Sin broker externo."""
from __future__ import annotations

import logging
import os
import sys
import threading

logger = logging.getLogger("evalua.erp_platform.events.sweeper")

_STARTED = False
_LOCK = threading.Lock()


def sweep_once(*, limit: int = 50) -> dict[str, int]:
    """Despacha pendientes de la base legacy. En multiempresa el flush del request cubre la compañía activa."""
    from sqlalchemy.orm import Session

    from core.config import settings
    from db.session import get_engine
    from erp_platform.events.outbox import dispatch_pending

    if getattr(settings, "database_per_company", False):
        return {"processed": 0, "failed": 0, "skipped": 1, "reclaimed": 0}
    engine = get_engine(None)
    db = Session(bind=engine, autoflush=False, future=True)
    try:
        stats = dispatch_pending(db, limit=limit)
        return stats
    except Exception:
        db.rollback()
        logger.exception("barrido de outbox falló")
        return {"processed": 0, "failed": 0, "skipped": 0, "reclaimed": 0}
    finally:
        db.close()


def start_outbox_sweeper(*, interval_seconds: float = 20.0) -> None:
    """Hilo daemon. No arranca bajo pytest ni si EVALUA_OUTBOX_SWEEP=0."""
    global _STARTED
    if os.environ.get("EVALUA_OUTBOX_SWEEP", "1") == "0":
        return
    if "pytest" in sys.modules:
        return
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True

    def _loop() -> None:
        while True:
            try:
                sweep_once()
            except Exception:
                logger.exception("ciclo de outbox interrumpido")
            threading.Event().wait(interval_seconds)

    threading.Thread(target=_loop, name="evalua-outbox-sweep", daemon=True).start()
    logger.info("Barrido de outbox activo cada %ss", interval_seconds)
