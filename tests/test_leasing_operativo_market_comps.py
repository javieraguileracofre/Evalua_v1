# tests/test_leasing_operativo_market_comps.py
# -*- coding: utf-8 -*-
from services.leasing_operativo.market_comps import (
    build_search_urls,
    fetch_autocosmos_comps,
    fetch_chileautos_comps,
    estimar_residual_con_mercado,
)


def test_build_search_urls_hilux():
    urls = build_search_urls(marca="Toyota", modelo="Hilux", anio_min=2023, km_min=100000)
    assert "chileautos.cl" in urls["chileautos"]
    assert "Hilux" in urls["chileautos"] or "hilux" in urls["chileautos"].lower()
    assert "autocosmos.cl" in urls["autocosmos"]
    assert "mercadolibre.cl" in urls["mercadolibre"]


def test_chileautos_live_comps_hilux():
    res = fetch_chileautos_comps(
        marca="Toyota",
        modelo="Hilux",
        anio_min=2023,
        anio_max=2025,
        km_min=80000,
        km_max=180000,
    )
    assert res["portal"] == "chileautos"
    if not res["ok"]:
        # Entorno bloqueado: no fallar el suite, pero dejar trazabilidad
        assert res.get("error")
        return
    assert res["count"] >= 3
    prices = [c["price"] for c in res["comps"]]
    assert min(prices) > 10_000_000
    assert max(prices) < 50_000_000
    sample = res["comps"][0]
    assert sample.get("url")
    assert sample.get("image_url")


def test_autocosmos_live_comps_hilux():
    res = fetch_autocosmos_comps(marca="Toyota", modelo="Hilux", anio_min=2022, anio_max=2025)
    assert res["portal"] == "autocosmos"
    if not res["ok"]:
        assert res.get("error")
        return
    assert any(c.get("image_url") for c in res["comps"])
    assert any(c.get("price", 0) > 5_000_000 for c in res["comps"])


def test_estimar_residual_mercado_orden_magnitud():
    est = estimar_residual_con_mercado(
        marca="Toyota",
        modelo="Hilux",
        valor_bien=27_000_000,
        plazo_meses=36,
        km_anual=36000,
        km_inicial=0,
        anio_vehiculo=2024,
        tipo_uso="MIXTO",
    )
    assert est["km_fin_estimado"] == 108000
    assert est["valor_residual_sugerido"] > 8_000_000
    assert est["valor_residual_sugerido"] < 27_000_000
    assert est["search_urls"]["chileautos"]
    assert isinstance(est.get("comparables"), list)
    assert isinstance(est.get("portales"), list)
