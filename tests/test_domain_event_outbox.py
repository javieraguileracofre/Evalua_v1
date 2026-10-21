# tests/test_domain_event_outbox.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from erp_platform.events import types as event_types
from erp_platform.events.publish import publish_in_transaction
from erp_platform.events.outbox import enqueue


def test_publish_falls_back_to_emit_when_outbox_missing():
    db = MagicMock()
    with patch("erp_platform.events.publish.enqueue", return_value=None) as enq:
        with patch("erp_platform.events.publish.emit") as em:
            publish_in_transaction(
                db,
                event_name=event_types.PAGO_REALIZADO,
                payload={"pago_id": 1},
            )
            enq.assert_called_once()
            em.assert_called_once()


def test_publish_skips_sync_emit_when_outbox_enqueued():
    db = MagicMock()
    with patch("erp_platform.events.publish.enqueue", return_value=77):
        with patch("erp_platform.events.publish.emit") as em:
            publish_in_transaction(
                db,
                event_name=event_types.CONTRATO_LEASING_ACTIVADO,
                payload={"producto": "LF"},
            )
            em.assert_not_called()


def test_enqueue_noop_without_table():
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    assert enqueue(db, event_name="X", payload={}) is None


def test_dispatch_uses_skip_locked_claim():
    src = Path(__file__).resolve().parents[1] / "erp_platform" / "events" / "outbox.py"
    text = src.read_text(encoding="utf-8")
    assert "FOR UPDATE SKIP LOCKED" in text
    assert "UPDATE domain_event_outbox AS o" in text
    assert "reclaim_stale_processing" in text
    assert "stale PROCESSING" in text
    assert "ux_domain_event_outbox_correlation" in (
        Path(__file__).resolve().parents[1]
        / "db"
        / "psql"
        / "142_outbox_correlation_unique.sql"
    ).read_text(encoding="utf-8")


def test_reclaim_stale_processing_sql_uses_skip_locked():
    from erp_platform.events.outbox import reclaim_stale_processing

    db = MagicMock()
    db.execute.return_value.fetchall.return_value = [(1,), (2,)]
    assert reclaim_stale_processing(db) == 2
    sql = str(db.execute.call_args[0][0])
    assert "PROCESSING" in sql
    assert "SKIP LOCKED" in sql


def test_fase3_validation_script_exits_3_without_url(monkeypatch):
    import tools.run_fase3_postgres_validation as script

    monkeypatch.delenv("EVALUA_TEST_DATABASE_URL", raising=False)
    assert script.main() == 3
