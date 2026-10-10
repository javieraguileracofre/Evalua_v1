# platform/events/bus.py
# -*- coding: utf-8 -*-
"""Event bus interno síncrono. Sin broker externo (preparado para evolucionar)."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger("evalua.erp_platform.events")

Handler = Callable[["DomainEvent"], None]


@dataclass(frozen=True)
class DomainEvent:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    company_id: int | None = None
    actor_id: int | None = None
    occurred_at: datetime = field(default_factory=datetime.utcnow)


_SUBSCRIBERS: dict[str, list[Handler]] = defaultdict(list)


def subscribe(event_name: str, handler: Handler) -> None:
    key = (event_name or "").strip()
    if not key:
        raise ValueError("event_name vacío")
    if handler not in _SUBSCRIBERS[key]:
        _SUBSCRIBERS[key].append(handler)


def clear_subscribers(event_name: str | None = None) -> None:
    if event_name is None:
        _SUBSCRIBERS.clear()
        return
    _SUBSCRIBERS.pop(event_name, None)


def emit(event: DomainEvent) -> None:
    handlers = list(_SUBSCRIBERS.get(event.name, ()))
    if not handlers:
        logger.debug("event=%s sin suscriptores", event.name)
        return
    for handler in handlers:
        try:
            handler(event)
        except Exception:
            logger.exception(
                "Handler falló event=%s handler=%s",
                event.name,
                getattr(handler, "__name__", repr(handler)),
            )
            raise
