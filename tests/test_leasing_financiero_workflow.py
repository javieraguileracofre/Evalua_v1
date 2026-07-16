# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from crud.comercial import leasing_fin as crud_lf
from crud.comercial.leasing_fin import _asegurar_analisis_aprobado, _siguiente_etapa
from crud.comercial.leasing_fin_operacion import inicializar_checklist
from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion, LeasingFinancieroHistorial
from models.comercial.leasing_financiero_operacion import LeasingFinancieroChecklistItem
from routes.ui import leasing_financiero as lf_routes
from schemas.comercial.leasing_credito import LeasingCreditoInput
from schemas.comercial.leasing_cotizacion import LeasingCotizacionCreate
from services.leasing_credito_scoring import evaluar_credito
from services.leasing_financiero_workflow import CHECKLIST_DEFINICION


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
                if not hasattr(obj, "amortizacion_lineas"):
                    obj.amortizacion_lineas = []
                if not hasattr(obj, "checklist_items"):
                    obj.checklist_items = []

    def commit(self) -> None:
        self.committed = True

    def refresh(self, _obj: object) -> None:
        return

    def delete(self, _obj: object) -> None:
        return

    def rollback(self) -> None:
        self.rolled_back = True


def test_inicializar_checklist_es_idempotente_en_misma_sesion():
    db = _FakeSession()
    cot = SimpleNamespace(id=38, checklist_items=[])

    inicializar_checklist(db, cot)  # type: ignore[arg-type]
    inicializar_checklist(db, cot)  # type: ignore[arg-type]

    creados = [x for x in db._added if isinstance(x, LeasingFinancieroChecklistItem)]
    assert len(creados) == len(CHECKLIST_DEFINICION)
    assert len({x.codigo for x in creados}) == len(CHECKLIST_DEFINICION)
    assert cot.checklist_items == creados


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


_LF_FORM_DEFAULTS = {
    "bien_descripcion": "",
    "bien_tipo": "",
    "fecha_primera_cuota": "",
    "periodicidad": "MENSUAL",
    "comision_apertura": "",
    "comision_apertura_tipo": "",
    "financia_comision": False,
    "gastos_operacionales": "",
    "iva_aplica": False,
    "iva_tasa": "",
    "iva_recuperable": True,
    "observaciones": "",
    "proveedor_id": "",
    "tasa_fondeo": "",
    "spread_margen": "",
    "activo_marca": "",
    "activo_modelo": "",
    "activo_serie": "",
    "activo_chasis": "",
}


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
        **_LF_FORM_DEFAULTS,
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
            **_LF_FORM_DEFAULTS,
        )
    assert err.value.status_code == 503


def test_parse_decimal_money_thousands_dot():
    assert lf_routes._parse_decimal("228.500", money=True) == Decimal("228500")
    assert lf_routes._parse_decimal("1.234.567,89", money=True) == Decimal("1234567.89")
    assert lf_routes._parse_decimal("1,234,567.89", money=True) == Decimal("1234567.89")
    assert lf_routes._parse_decimal("25.000.000", money=True) == Decimal("25000000")


def test_parse_decimal_rate_keeps_decimal():
    assert lf_routes._parse_decimal("0,1200", money=False) == Decimal("0.1200")
    assert lf_routes._parse_decimal("228.500", money=False) == Decimal("228.500")


def test_aplicar_parametros_corrige_monto_inconsistente():
    """Regresión: Number('250.000')===250 dejaba monto_financiado=250 con neto 25M."""
    from services.leasing_financiero import aplicar_parametros_financieros

    data = aplicar_parametros_financieros(
        {
            "moneda": "CLP",
            "valor_neto": Decimal("25000000"),
            "pago_inicial_tipo": "PORCENTAJE",
            "pago_inicial_valor": Decimal("15"),
            "monto_financiado": Decimal("250"),
            "financia_seguro": False,
        }
    )
    assert data["monto_financiado"] == Decimal("21250000.00")
    assert data["monto"] == Decimal("21250000.00")


def test_metadata_tributaria_es_json_serializable():
    """Regresión: Decimal en metadata_tributaria rompía el flush (JSON encoder)."""
    import json

    cot = LeasingFinancieroCotizacion(
        cliente_id=1,
        moneda="CLP",
        valor_neto=Decimal("25000000"),
        monto_financiado=Decimal("21250000"),
        tasa=Decimal("0.18"),
        plazo=36,
        periodos_gracia=2,
        periodicidad="MENSUAL",
        iva_aplica=True,
        iva_tasa=Decimal("0.19"),
        opcion_compra=Decimal("150000"),
        estado="BORRADOR",
    )
    crud_lf._aplicar_metricas_persistidas(cot)
    assert cot.metadata_tributaria
    json.dumps(cot.metadata_tributaria)  # no debe lanzar TypeError


def test_json_safe_convierte_decimal_y_fechas():
    import json

    out = crud_lf._json_safe(
        {"monto": Decimal("100.50"), "fecha": date(2026, 7, 16), "items": [Decimal("1")], "ok": True}
    )
    json.dumps(out)
    assert out["monto"] == "100.50"
    assert out["fecha"] == "2026-07-16"


def test_hub_resumen_pipeline_y_funnel():
    c1 = SimpleNamespace(
        estado="EN_ANALISIS_CREDITO",
        moneda="CLP",
        monto_financiado=Decimal("1000000"),
        valor_neto=None,
        monto=None,
        cliente=SimpleNamespace(razon_social="ACME"),
        workflow_json={},
        analisis_credito=None,
        ejecutivo=None,
        plazo=36,
        fecha_cotizacion=date.today(),
    )
    c2 = SimpleNamespace(
        estado="ACTIVADA",
        moneda="CLP",
        monto_financiado=Decimal("500000"),
        valor_neto=None,
        monto=None,
        cliente=SimpleNamespace(razon_social="Beta"),
        workflow_json={},
        analisis_credito=None,
        ejecutivo=None,
        plazo=24,
        fecha_cotizacion=date.today(),
    )

    class _Db:
        pass

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(crud_lf, "get_cotizaciones", lambda _db, **kw: [c1, c2])
    res = crud_lf.get_hub_resumen(_Db())
    assert res["kpis"]["en_credito"] == 1
    assert res["kpis"]["activadas"] == 1
    assert res["pipeline_montos"]["CLP"] == Decimal("1000000")
    assert res["cartera_montos"]["CLP"] == Decimal("500000")
    assert len(res["funnel"]) == 5
    monkeypatch.undo()


def test_activar_flujo_permte_tasa_cero_bloquea_menos_099():
    class _DummyDB:
        pass

    cot = SimpleNamespace(
        id=10,
        analisis_credito=SimpleNamespace(recomendacion="APROBADO"),
        workflow_json={
            "hitos": {
                "analisis_credito": True,
                "orden_compra": True,
                "contrato_firmado": True,
                "acta_recepcion": True,
                "factura_compra": True,
                "activacion_contable": False,
            },
            "etapa_actual": "ACTA_RECEPCION",
        },
        monto_financiado=Decimal("1000"),
        tasa=Decimal("-1.00"),
        plazo=12,
        fecha_inicio="2026-01-01",
        estado="DOCUMENTACION_COMPLETA",
        contrato_activo=False,
        asiento_id=None,
        fecha_activacion=None,
        fecha_vigencia_desde=None,
        numero_operacion=None,
        facturas_compra=[],
        checklist_items=[],
    )

    with pytest.raises(ValueError):
        crud_lf.activar_flujo_contable(_DummyDB(), cotizacion=cot)  # type: ignore[arg-type]


def test_puede_eliminar_cotizacion_bloquea_activada():
    cot = SimpleNamespace(estado="ACTIVADA", contrato_activo=False, asiento_id=None)
    assert crud_lf.puede_eliminar_cotizacion(cot) is False  # type: ignore[arg-type]

    cot2 = SimpleNamespace(estado="BORRADOR", contrato_activo=True, asiento_id=None)
    assert crud_lf.puede_eliminar_cotizacion(cot2) is False  # type: ignore[arg-type]

    cot3 = SimpleNamespace(estado="BORRADOR", contrato_activo=False, asiento_id=99)
    assert crud_lf.puede_eliminar_cotizacion(cot3) is False  # type: ignore[arg-type]

    cot4 = SimpleNamespace(estado="BORRADOR", contrato_activo=False, asiento_id=None)
    assert crud_lf.puede_eliminar_cotizacion(cot4) is True  # type: ignore[arg-type]


def test_eliminar_cotizaciones_requiere_seleccion():
    with pytest.raises(ValueError, match="Seleccione"):
        crud_lf.eliminar_cotizaciones(object(), ids=[])  # type: ignore[arg-type]
