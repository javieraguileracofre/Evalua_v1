# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from crud.comercial import leasing_fin as crud_lf
from crud.comercial.leasing_fin import _asegurar_analisis_aprobado, _siguiente_etapa
from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion, LeasingFinancieroHistorial
from routes.ui import leasing_financiero as lf_routes
from schemas.comercial.leasing_credito import LeasingCreditoInput
from schemas.comercial.leasing_cotizacion import LeasingCotizacionCreate
from services.leasing_credito_scoring import evaluar_credito


def test_scoring_aprobado_condiciones_bucket():
    inp = LeasingCreditoInput(
        tipo_persona="NATURAL",
        ingreso_neto_mensual=Decimal("1000000"),
        carga_financiera_mensual=Decimal("350000"),
        antiguedad_laboral_meses=24,
        score_buro=680,
        comportamiento_pago="REGULAR",
        ltv_pct=Decimal("85"),
    )
    out = evaluar_credito(inp)
    assert out.recomendacion in {"APROBADO", "APROBADA_CONDICIONES", "RECHAZADO"}


def test_siguiente_etapa_workflow():
    wf = {"hitos": {"analisis_credito": True, "orden_compra": True, "contrato_firmado": False, "acta_recepcion": False, "activacion_contable": False}}
    assert _siguiente_etapa(wf) == "CONTRATO_FIRMADO"


def test_gate_credito_aprobado_permite_avanzar():
    cot = SimpleNamespace(analisis_credito=SimpleNamespace(recomendacion="APROBADA_CONDICIONES"))
    _asegurar_analisis_aprobado(cot)


def test_gate_credito_rechazado_bloquea():
    cot = SimpleNamespace(analisis_credito=SimpleNamespace(recomendacion="RECHAZADO"))
    with pytest.raises(ValueError):
        _asegurar_analisis_aprobado(cot)


def test_fx_validation_for_usd_requires_rate():
    with pytest.raises(ValueError):
        crud_lf._validar_moneda_y_tipo_cambio(moneda="USD", uf_valor=None, dolar_valor=Decimal("0"))


class _FakeSession:
    def __init__(self) -> None:
        self._added: list[object] = []
        self.flushed = False
        self.committed = False
        self.rolled_back = False

    def add(self, obj: object) -> None:
        self._added.append(obj)

    def flush(self) -> None:
        self.flushed = True
        for obj in self._added:
            if isinstance(obj, LeasingFinancieroCotizacion) and getattr(obj, "id", None) is None:
                setattr(obj, "id", 123)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, _obj: object) -> None:
        return

    def rollback(self) -> None:
        self.rolled_back = True


def test_crear_cotizacion_flush_before_historial(monkeypatch: pytest.MonkeyPatch):
    db = _FakeSession()
    seen: dict[str, object] = {}

    def _fake_regenerar(_db: object, _cot: LeasingFinancieroCotizacion) -> None:
        return

    def _fake_get(_db: object, _cid: int) -> None:
        return None

    orig_hist = crud_lf._registrar_historial

    def _spy_historial(*args, **kwargs):  # type: ignore[no-untyped-def]
        cot = kwargs["cotizacion"]
        seen["cot_id_at_historial"] = cot.id
        return orig_hist(*args, **kwargs)

    monkeypatch.setattr(crud_lf, "regenerar_proyeccion_contable", _fake_regenerar)
    monkeypatch.setattr(crud_lf, "get_cotizacion", _fake_get)
    monkeypatch.setattr(crud_lf, "_registrar_historial", _spy_historial)

    obj = LeasingCotizacionCreate(
        cliente_id=1,
        monto=Decimal("1000000"),
        moneda="CLP",
        tasa=Decimal("0.12"),
        plazo=24,
        monto_financiado=Decimal("800000"),
        estado="BORRADOR",
    )
    cot = crud_lf.crear_cotizacion(db, obj_in=obj)  # type: ignore[arg-type]

    assert db.flushed is True
    assert db.committed is True
    assert seen["cot_id_at_historial"] == 123
    assert cot.id == 123
    assert any(isinstance(x, LeasingFinancieroHistorial) for x in db._added)


class _Req:
    class _State:
        auth_user = {"roles": ["OPERACIONES"]}

    state = _State()

    @staticmethod
    def url_for(name: str, **params: object) -> str:
        if name == "lf_cotizacion_detalle":
            return f"/comercial/leasing/cotizaciones/{params['cotizacion_id']}"
        return "/"


def test_nueva_cotizacion_post_redirects_and_not_500(monkeypatch: pytest.MonkeyPatch):
    fake_db = object()

    monkeypatch.setattr(lf_routes.crud_cliente, "get_cliente", lambda _db, _id: SimpleNamespace(id=1))
    monkeypatch.setattr(
        lf_routes.crud_lf,
        "crear_cotizacion",
        lambda _db, obj_in: SimpleNamespace(id=99),
    )

    resp = lf_routes.lf_cotizacion_nueva_post(
        request=_Req(),  # type: ignore[arg-type]
        db=fake_db,  # type: ignore[arg-type]
        cliente_id=1,
        monto="",
        moneda="CLP",
        tasa="",
        plazo="",
        opcion_compra="",
        periodos_gracia="",
        fecha_inicio="",
        valor_neto="",
        pago_inicial_tipo="",
        pago_inicial_valor="",
        financia_seguro=False,
        seguro_monto_uf="",
        otros_montos_pesos="",
        concesionario="",
        ejecutivo="",
        fecha_cotizacion="",
        uf_valor="",
        monto_financiado="",
        dolar_valor="",
    )
    assert resp.status_code == 303
    assert "/comercial/leasing/cotizaciones/99" in resp.headers.get("location", "")


def test_nueva_cotizacion_post_handles_sqlalchemy_error(monkeypatch: pytest.MonkeyPatch):
    fake_db = object()

    monkeypatch.setattr(lf_routes.crud_cliente, "get_cliente", lambda _db, _id: SimpleNamespace(id=1))

    def _boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise SQLAlchemyError("db down")

    monkeypatch.setattr(lf_routes.crud_lf, "crear_cotizacion", _boom)
    with pytest.raises(HTTPException) as err:
        lf_routes.lf_cotizacion_nueva_post(
            request=_Req(),  # type: ignore[arg-type]
            db=fake_db,  # type: ignore[arg-type]
            cliente_id=1,
            monto="",
            moneda="CLP",
            tasa="",
            plazo="",
            opcion_compra="",
            periodos_gracia="",
            fecha_inicio="",
            valor_neto="",
            pago_inicial_tipo="",
            pago_inicial_valor="",
            financia_seguro=False,
            seguro_monto_uf="",
            otros_montos_pesos="",
            concesionario="",
            ejecutivo="",
            fecha_cotizacion="",
            uf_valor="",
            monto_financiado="",
            dolar_valor="",
        )
    assert err.value.status_code == 503


def test_parse_decimal_money_thousands_dot():
    assert lf_routes._parse_decimal("228.500", money=True) == Decimal("228500")
    assert lf_routes._parse_decimal("1.234.567,89", money=True) == Decimal("1234567.89")
    assert lf_routes._parse_decimal("1,234,567.89", money=True) == Decimal("1234567.89")


def test_parse_decimal_rate_keeps_decimal():
    assert lf_routes._parse_decimal("0,1200", money=False) == Decimal("0.1200")
    assert lf_routes._parse_decimal("228.500", money=False) == Decimal("228.500")
