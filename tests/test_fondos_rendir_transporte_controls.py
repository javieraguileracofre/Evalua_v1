# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from crud import fondos_rendir as fr
from crud import fondos_rendir_contabilidad as frc


def test_bloqueo_anticipo_con_fondos_abiertos_antiguos(monkeypatch) -> None:
    monkeypatch.setattr(
        fr,
        "fondos_abiertos_antiguos_por_empleado",
        lambda *_args, **_kwargs: [SimpleNamespace(id=1)],
    )
    with pytest.raises(ValueError, match="15 días"):
        fr.crear_fondo(
            SimpleNamespace(get=lambda *_: object()),
            empleado_id=1,
            vehiculo_transporte_id=None,
            monto_anticipo=Decimal("100"),
            fecha_entrega=datetime.utcnow(),
            observaciones=None,
        )


def test_detecta_gasto_combustible_sin_viaje(monkeypatch) -> None:
    f = SimpleNamespace(
        id=1,
        folio="FR-1",
        empleado=SimpleNamespace(nombre_completo="A"),
        empleado_id=1,
        vehiculo_transporte_id=None,
        lineas_gasto=[SimpleNamespace(rubro="Combustible", monto=Decimal("100"))],
        viajes_transporte=[],
    )

    class _FakeScalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _DB:
        def scalars(self, stmt):
            sql = str(stmt)
            if "FROM fondos_rendir" in sql:
                return _FakeScalars([f])
            return _FakeScalars([])

    monkeypatch.setattr(fr, "dashboard_stats", lambda _db: {"alertas_rendicion": []})
    res = fr.dashboard_conciliacion_transporte(_DB())
    assert len(res["gastos_combustible_sin_viaje"]) == 1


def test_liquidacion_contable_mapea_rubro(monkeypatch) -> None:
    cuentas = {
        "Gasto combustible": SimpleNamespace(codigo="610102"),
        "Gasto operacional / transporte": SimpleNamespace(codigo="610100"),
        "Anticipo / fondos por rendir (activo)": SimpleNamespace(codigo="110500"),
        "Caja o equivalente": SimpleNamespace(codigo="110100"),
    }
    monkeypatch.setattr(frc, "_resolver_cuenta", lambda _db, **kw: cuentas[kw["rol"]])
    capt = {}
    monkeypatch.setattr(frc, "crear_asiento", lambda *_a, **kw: capt.setdefault("detalles", kw["detalles"]) or 99)
    f = SimpleNamespace(
        id=1,
        folio="FR-1",
        monto_anticipo=Decimal("100"),
        lineas_gasto=[SimpleNamespace(rubro="Combustible", monto=Decimal("50"))],
        fecha_aprobacion=datetime.utcnow(),
        asiento_id_liquidacion=None,
    )
    frc.contabilizar_liquidacion_rendicion(SimpleNamespace(), f)
    assert any(d["codigo_cuenta"] == "610102" for d in capt["detalles"])


def test_alertas_mantencion_vencida_proxima(monkeypatch) -> None:
    hoy = datetime.utcnow().date()
    v1 = SimpleNamespace(fecha_proxima_mantencion=hoy - timedelta(days=1), odometro_actual=10000, km_proxima_mantencion=12000, fecha_revision_tecnica=None, fecha_permiso_circulacion=None, fecha_seguro=None)
    v2 = SimpleNamespace(fecha_proxima_mantencion=hoy + timedelta(days=5), odometro_actual=10000, km_proxima_mantencion=10300, fecha_revision_tecnica=None, fecha_permiso_circulacion=None, fecha_seguro=None)
    monkeypatch.setattr(fr, "listar_vehiculos_transporte", lambda *_a, **_k: [v1, v2])
    out = fr.alertas_mantencion(SimpleNamespace())
    assert len(out["mantenciones_vencidas"]) >= 1
    assert len(out["mantenciones_proximas"]) >= 1
