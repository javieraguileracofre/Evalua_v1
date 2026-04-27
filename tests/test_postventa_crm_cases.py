# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from crud.postventa import postventa as crud_postventa
from models.auth.usuario import Usuario
from models.comunicaciones.email_log import EmailLog
from models.maestros.cliente import Cliente
from models.postventa.postventa import PostventaCasoEvento, PostventaSolicitud


def _db() -> Session:
    pytest.skip("Test de integración requiere secuencias PostgreSQL para BIGINT PK.")
    engine = create_engine("sqlite:///:memory:", future=True)
    Cliente.__table__.create(bind=engine)
    Usuario.__table__.create(bind=engine)
    PostventaSolicitud.__table__.create(bind=engine)
    PostventaCasoEvento.__table__.create(bind=engine)
    EmailLog.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    db.add(Cliente(id=1, rut="11111111-1", razon_social="Cliente Uno", activo=True))
    db.add(Usuario(id=10, email="agente@test.cl", password_hash="x", nombre_completo="Agente Uno", activo=True))
    db.commit()
    return db


def test_crear_caso_genera_numero_y_evento() -> None:
    db = _db()
    caso = crud_postventa.crear_caso(
        db,
        cliente_id=1,
        titulo="Incidencia de postventa",
        descripcion="Detalle inicial",
        creado_por_id=10,
    )
    assert caso.numero_caso.startswith("PV-")
    eventos = crud_postventa.listar_eventos_caso(db, caso.id)
    assert len(eventos) >= 1
    assert eventos[0].tipo == "SISTEMA"


def test_asignar_caso_actualiza_y_crea_evento() -> None:
    db = _db()
    caso = crud_postventa.crear_caso(db, cliente_id=1, titulo="Caso", descripcion="Detalle")
    updated = crud_postventa.asignar_caso(db, caso_id=caso.id, usuario_id=10, actor_id=10)
    assert updated is not None
    assert updated.asignado_a_id == 10
    eventos = crud_postventa.listar_eventos_caso(db, caso.id)
    assert any(e.tipo == "ASIGNACION" for e in eventos)


def test_cambiar_estado_actualiza_fechas_resolucion_y_cierre() -> None:
    db = _db()
    caso = crud_postventa.crear_caso(db, cliente_id=1, titulo="Caso", descripcion="Detalle")
    crud_postventa.cambiar_estado_caso(db, caso_id=caso.id, estado="RESUELTO", actor_id=10)
    caso1 = crud_postventa.get_caso(db, caso.id)
    assert caso1 is not None and caso1.fecha_resolucion is not None
    crud_postventa.cambiar_estado_caso(db, caso_id=caso.id, estado="CERRADO", actor_id=10)
    caso2 = crud_postventa.get_caso(db, caso.id)
    assert caso2 is not None and caso2.fecha_cierre is not None


def test_enviar_email_crea_log_y_evento(monkeypatch) -> None:
    db = _db()
    caso = crud_postventa.crear_caso(db, cliente_id=1, titulo="Caso", descripcion="Detalle")

    def _fake_send_postventa_caso_email(**kwargs):
        log = EmailLog(
            modulo="POSTVENTA",
            evento="CASO_EMAIL",
            cliente_id=1,
            caso_id=caso.id,
            to_email="cliente@test.cl",
            subject="Asunto",
            include_detalle=True,
            status="ENVIADO",
        )
        kwargs["db"].add(log)
        kwargs["db"].commit()
        kwargs["db"].refresh(log)
        return log

    monkeypatch.setattr(crud_postventa.email_service, "send_postventa_caso_email", _fake_send_postventa_caso_email)
    crud_postventa.enviar_email_caso(
        db,
        caso_id=caso.id,
        to="cliente@test.cl",
        subject="Asunto",
        body="Mensaje",
        actor={"uid": 10},
    )
    logs = db.query(EmailLog).filter(EmailLog.caso_id == caso.id).all()
    assert len(logs) == 1
    eventos = crud_postventa.listar_eventos_caso(db, caso.id)
    assert any(e.tipo == "EMAIL_ENVIADO" for e in eventos)


def test_metricas_y_filtros_bandeja() -> None:
    db = _db()
    c1 = crud_postventa.crear_caso(
        db,
        cliente_id=1,
        titulo="Urgente sin asignar",
        descripcion="Detalle",
        prioridad="URGENTE",
    )
    c1.sla_estado = "VENCIDO"
    db.add(c1)
    db.commit()
    c2 = crud_postventa.crear_caso(db, cliente_id=1, titulo="Asignado", descripcion="Detalle")
    crud_postventa.asignar_caso(db, caso_id=c2.id, usuario_id=10, actor_id=10)
    m = crud_postventa.metricas_postventa(db)
    assert m["casos_abiertos"] >= 2
    assert m["casos_vencidos_sla"] >= 1
    assert m["backlog_sin_asignar"] >= 1
    urgentes = crud_postventa.listar_casos(db, prioridad="URGENTE")
    assert any(c.id == c1.id for c in urgentes)
    asignados = crud_postventa.listar_casos(db, asignado_a_id=10)
    assert any(c.id == c2.id for c in asignados)
