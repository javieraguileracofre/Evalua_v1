# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from starlette.requests import Request

from routes.ui import postventa as ui_postventa


def _req(path: str = "/postventa") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "session": {},
    }
    req = Request(scope)
    req.state.auth_user = {"uid": 10, "roles": ["ADMIN"]}
    return req


def test_crear_caso_sin_cliente_devuelve_validacion(monkeypatch) -> None:
    req = _req("/postventa/casos/nuevo")
    monkeypatch.setattr(ui_postventa, "guard_operacion_mutacion", lambda _req: None)
    monkeypatch.setattr(
        ui_postventa,
        "_redirect",
        lambda request, route_name, **kwargs: SimpleNamespace(
            status_code=303,
            headers={"location": str(kwargs.get("msg", ""))},
        ),
    )
    resp = ui_postventa.postventa_caso_nuevo_post(
        request=req,
        cliente_id=0,
        titulo="Caso sin cliente",
        descripcion="Detalle",
        categoria="CONSULTA",
        prioridad="MEDIA",
        origen="INTERNO",
        db=None,
    )
    assert resp.status_code == 303
    assert "Debe seleccionar un cliente" in (resp.headers.get("location", ""))


def test_crear_caso_db_error_mensaje_operativo(monkeypatch) -> None:
    req = _req("/postventa/casos/nuevo")
    monkeypatch.setattr(ui_postventa, "guard_operacion_mutacion", lambda _req: None)
    monkeypatch.setattr(
        ui_postventa,
        "_redirect",
        lambda request, route_name, **kwargs: SimpleNamespace(
            status_code=303,
            headers={"location": str(kwargs.get("msg", ""))},
        ),
    )
    monkeypatch.setattr(ui_postventa.crud_cliente, "get_cliente", lambda db, cid: SimpleNamespace(id=cid))

    def _boom(*args, **kwargs):
        raise RuntimeError("column numero_caso does not exist")

    monkeypatch.setattr(ui_postventa.crud_postventa, "crear_caso", _boom)
    resp = ui_postventa.postventa_caso_nuevo_post(
        request=req,
        cliente_id=1,
        titulo="Caso",
        descripcion="Detalle",
        categoria="CONSULTA",
        prioridad="MEDIA",
        origen="INTERNO",
        db=object(),
    )
    assert resp.status_code == 303
    assert "migración Postventa CRM" in (resp.headers.get("location", ""))


def test_cargar_ficha_cliente_con_datos_legacy(monkeypatch) -> None:
    req = _req("/postventa/cliente/1")
    req.scope["method"] = "GET"
    monkeypatch.setattr(ui_postventa, "guard_operacion_consulta", lambda _req: None)
    monkeypatch.setattr(ui_postventa.crud_cliente, "get_cliente", lambda db, cid: SimpleNamespace(id=cid, razon_social="Cliente"))
    monkeypatch.setattr(ui_postventa.crud_postventa, "listar_interacciones", lambda db, **kwargs: [])
    monkeypatch.setattr(ui_postventa.crud_postventa, "listar_solicitudes", lambda db, **kwargs: [])
    monkeypatch.setattr(
        ui_postventa.crud_postventa,
        "contar_por_cliente",
        lambda db, cliente_id: {"interacciones_total": 0, "solicitudes_abiertas": 0},
    )
    monkeypatch.setattr(
        ui_postventa.templates,
        "TemplateResponse",
        lambda name, ctx: SimpleNamespace(status_code=200, template=name, context=ctx),
    )
    resp = ui_postventa.postventa_ficha_cliente(request=req, cliente_id=1, db=object())
    assert resp.status_code == 200


def test_cargar_listado_casos(monkeypatch) -> None:
    req = _req("/postventa/casos")
    req.scope["method"] = "GET"
    monkeypatch.setattr(ui_postventa, "guard_operacion_consulta", lambda _req: None)
    monkeypatch.setattr(ui_postventa.crud_postventa, "listar_casos", lambda db, **kwargs: [])
    monkeypatch.setattr(
        ui_postventa.crud_postventa,
        "metricas_postventa",
        lambda db: {"casos_abiertos": 0, "casos_nuevos_7d": 0, "casos_nuevos_30d": 0, "casos_resueltos_30d": 0,
                    "promedio_horas_primera_respuesta": 0.0, "promedio_horas_resolucion": 0.0, "casos_vencidos_sla": 0,
                    "casos_por_usuario_asignado": [], "casos_por_estado": [], "casos_por_prioridad": [], "backlog_sin_asignar": 0},
    )
    monkeypatch.setattr(ui_postventa.crud_usuarios, "listar_usuarios", lambda db, limite=200: [])
    monkeypatch.setattr(
        ui_postventa.templates,
        "TemplateResponse",
        lambda name, ctx: SimpleNamespace(status_code=200, template=name, context=ctx),
    )
    resp = ui_postventa.postventa_casos_lista(request=req, db=object())
    assert resp.status_code == 200


def test_comentario_asignacion_y_estado(monkeypatch) -> None:
    req = _req("/postventa/casos/1")
    monkeypatch.setattr(ui_postventa, "guard_operacion_mutacion", lambda _req: None)
    monkeypatch.setattr(
        ui_postventa,
        "_redirect_caso",
        lambda request, caso_id, **kwargs: SimpleNamespace(status_code=303, headers={"location": f"/ok/{caso_id}"}),
    )
    caso = SimpleNamespace(id=1, cliente_id=1)
    monkeypatch.setattr(ui_postventa.crud_postventa, "get_caso", lambda db, caso_id: caso)
    monkeypatch.setattr(ui_postventa.crud_postventa, "agregar_evento_caso", lambda db, **kwargs: None)
    resp_com = ui_postventa.postventa_caso_comentario(
        request=req,
        caso_id=1,
        contenido="nota",
        visibilidad="INTERNA",
        db=SimpleNamespace(commit=lambda: None),
    )
    assert resp_com.status_code == 303
    monkeypatch.setattr(ui_postventa.crud_postventa, "asignar_caso", lambda db, **kwargs: caso)
    resp_asig = ui_postventa.postventa_caso_asignar(request=req, caso_id=1, usuario_id=10, db=object())
    assert resp_asig.status_code == 303
    monkeypatch.setattr(ui_postventa.crud_postventa, "cambiar_estado_caso", lambda db, **kwargs: caso)
    resp_est = ui_postventa.postventa_caso_estado(request=req, caso_id=1, estado="EN_PROCESO", comentario=None, db=object())
    assert resp_est.status_code == 303

