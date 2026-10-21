# services/leasing_operativo/market_comps.py
# -*- coding: utf-8 -*-
"""
Comparables de mercado para residual LOP.

Portales (Chile):
  1) Chileautos — API Merlin `/_api/search-core`
  2) Autocosmos — HTML con microdata de listados
  3) Mercado Libre Autos — API pública sites/MLC (si el entorno lo permite)

Devuelve avisos con precio, año, km, imagen y link como respaldo de la estimación.
"""
from __future__ import annotations

import re
import statistics
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _abs_url(base: str, path: str | None) -> str:
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")


def _parse_price(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw)
    m = re.search(r"([\d\.]+)", s.replace(" ", ""))
    if not m:
        return None
    token = m.group(1)
    # CLP miles: 23.970.000
    if token.count(".") >= 1 and "," not in token:
        token = token.replace(".", "")
    try:
        v = float(token)
    except ValueError:
        return None
    return v if v > 0 else None


def _parse_km(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).lower().replace(" ", "")
    m = re.search(r"([\d\.]+)\s*km", s) or re.search(r"kmt\s*([\d\.]+)", s) or re.search(r"([\d\.]+)", s)
    if not m:
        return None
    token = m.group(1).replace(".", "") if m.group(1).count(".") > 0 else m.group(1)
    try:
        return float(token)
    except ValueError:
        return None


def build_search_urls(
    *,
    marca: str,
    modelo: str,
    anio_min: int,
    anio_max: int | None = None,
    km_min: int = 0,
    km_max: int | None = None,
) -> dict[str, str]:
    marca_c = (marca or "").strip() or "Toyota"
    modelo_c = (modelo or "").strip() or "Hilux"
    amax = anio_max if anio_max else ""
    kmax = "" if km_max is None else str(int(km_max))
    q_ca = (
        f"(And.Tipo.Usado._.(C.Marca.{marca_c}._.Modelo.{modelo_c}.)_"
        f".Ano.range({int(anio_min)}..{amax})._.Kilometraje.range({int(km_min)}..{kmax}).)"
    )
    return {
        "chileautos": f"https://www.chileautos.cl/vehiculos/?q={quote(q_ca)}",
        "autocosmos": (
            f"https://www.autocosmos.cl/auto/usado/{quote(marca_c.lower())}/{quote(modelo_c.lower())}"
            f"?anodesde={int(anio_min)}"
            + (f"&anohasta={int(anio_max)}" if anio_max else "")
        ),
        "mercadolibre": (
            "https://listado.mercadolibre.cl/vehiculos/"
            f"{quote(marca_c.lower())}-{quote(modelo_c.lower())}"
            f"_YearRange_{int(anio_min)}-{int(anio_max or date.today().year)}"
        ),
    }


def _chileautos_query(marca: str, modelo: str, anio_min: int, anio_max: int | None, km_min: int, km_max: int | None) -> str:
    amax = "" if anio_max is None else str(int(anio_max))
    kmax = "" if km_max is None else str(int(km_max))
    return (
        f"(And.Tipo.Usado._.(C.Marca.{marca}._.Modelo.{modelo}.)_"
        f".Ano.range({int(anio_min)}..{amax})._.Kilometraje.range({int(km_min)}..{kmax}).)"
    )


def fetch_chileautos_comps(
    *,
    marca: str,
    modelo: str,
    anio_min: int,
    anio_max: int | None = None,
    km_min: int = 0,
    km_max: int | None = None,
    timeout_s: float = 25.0,
) -> dict[str, Any]:
    q = _chileautos_query(marca, modelo, anio_min, anio_max, km_min, km_max)
    page = f"https://www.chileautos.cl/vehiculos/?q={quote(q)}"
    api = f"https://www.chileautos.cl/_api/search-core?q={quote(q)}"
    comps: list[dict[str, Any]] = []
    try:
        with httpx.Client(
            timeout=timeout_s,
            headers={"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9"},
            follow_redirects=True,
        ) as client:
            client.get(page, headers={"Accept": "text/html"})
            raw = client.get(
                api,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Referer": page,
                    "Origin": "https://www.chileautos.cl",
                },
            ).text
    except Exception as exc:
        return {"portal": "chileautos", "ok": False, "error": str(exc), "search_url": page, "comps": []}

    nids = list(dict.fromkeys(re.findall(r'"tracking/item/networkId":"([^"]+)"', raw)))
    url_by_nid: dict[str, str] = {}
    for m in re.finditer(
        r'(/vehiculos/detalles/[^"\\]+?/(CP-AD-\d+|GI-AD-\d+|CL-AD-\d+)/?)',
        raw,
    ):
        url_by_nid.setdefault(m.group(2), m.group(1))
    imgs = list(dict.fromkeys(re.findall(r"https://chileautos\.pxcrush\.net/[^\"\\]+", raw)))
    # Pares (nid, km) desde bloques de texto cercanos al id
    km_by_nid: dict[str, int] = {}
    for nid in nids:
        i = raw.find(nid)
        if i < 0:
            continue
        window = raw[max(0, i - 1200) : i + 1200]
        mkm = re.search(r"([\d\.]+)\s*km", window, flags=re.I)
        if mkm:
            try:
                km_by_nid[nid] = int(mkm.group(1).replace(".", ""))
            except ValueError:
                pass

    for idx, nid in enumerate(nids):
        i = raw.find(f'"tracking/item/networkId":"{nid}"')
        window = raw[max(0, i - 80) : i + 650]

        def _g(key: str) -> str | None:
            m = re.search(rf'"tracking/item/{key}":"([^"]*)"', window)
            return m.group(1) if m else None

        price = _parse_price(_g("price"))
        year = int(_g("year") or 0) or None
        make = _g("make") or marca
        model = _g("model") or modelo
        state = _g("state") or ""
        detail = url_by_nid.get(nid)
        url = _abs_url("https://www.chileautos.cl", detail) if detail else page
        img = imgs[idx] if idx < len(imgs) else (imgs[0] if imgs else "")
        km = km_by_nid.get(nid)
        if not price:
            continue
        comps.append(
            {
                "portal": "chileautos",
                "title": f"{year or ''} {make} {model}".strip(),
                "price": price,
                "year": year,
                "km": km,
                "currency": "CLP",
                "location": state,
                "image_url": img,
                "url": url,
                "external_id": nid,
            }
        )

    return {
        "portal": "chileautos",
        "ok": bool(comps),
        "error": None if comps else "Sin avisos parseables",
        "search_url": page,
        "comps": comps[:24],
        "count": len(comps),
    }


def fetch_autocosmos_comps(
    *,
    marca: str,
    modelo: str,
    anio_min: int,
    anio_max: int | None = None,
    km_min: int = 0,
    km_max: int | None = None,
    timeout_s: float = 25.0,
) -> dict[str, Any]:
    marca_l = (marca or "toyota").strip().lower()
    modelo_l = (modelo or "hilux").strip().lower()
    url = f"https://www.autocosmos.cl/auto/usado/{quote(marca_l)}/{quote(modelo_l)}?anodesde={int(anio_min)}"
    if anio_max:
        url += f"&anohasta={int(anio_max)}"
    try:
        with httpx.Client(timeout=timeout_s, headers={"User-Agent": UA, "Accept-Language": "es-CL"}, follow_redirects=True) as client:
            html = client.get(url, headers={"Accept": "text/html"}).text
    except Exception as exc:
        return {"portal": "autocosmos", "ok": False, "error": str(exc), "search_url": url, "comps": []}

    comps: list[dict[str, Any]] = []
    # Cards: meta description + link + image + year/km spans
    pattern = re.compile(
        r'<meta\s+itemprop="description"\s+content="(?P<title>[^"]*?precio\s*\$(?P<price>[\d\.]+)[^"]*)"\s*/?>'
        r'.{0,400}?<a\s+itemprop="url"\s+href="(?P<href>[^"]+)"'
        r'.{0,500}?<img[^>]+(?:content|src)="(?P<img>https://[^"]+)"'
        r'.{0,500}?itemprop="modelDate"[^>]*>(?P<year>\d{4})<'
        r'.{0,200}?itemprop="mileageFromOdometer"[^>]*>(?P<km>[\d\.\s]+)\s*km',
        re.I | re.S,
    )
    for m in pattern.finditer(html):
        price = _parse_price(m.group("price"))
        year = int(m.group("year"))
        km = _parse_km(m.group("km"))
        if anio_max and year > int(anio_max):
            continue
        if year < int(anio_min):
            continue
        if km is not None and km < km_min:
            continue
        if km_max is not None and km is not None and km > km_max:
            continue
        if not price:
            continue
        href = m.group("href")
        comps.append(
            {
                "portal": "autocosmos",
                "title": m.group("title")[:140],
                "price": price,
                "year": year,
                "km": km,
                "currency": "CLP",
                "location": "",
                "image_url": m.group("img"),
                "url": _abs_url("https://www.autocosmos.cl", href),
                "external_id": href.rstrip("/").split("/")[-1],
            }
        )

    # Fallback looser parse for financed ads without "precio $"
    if len(comps) < 3:
        loose = re.compile(
            r'<a\s+itemprop="url"\s+href="(?P<href>/auto/usado/[^"]+)"\s+title="(?P<title>[^"]+)"'
            r'.{0,500}?<img[^>]+src="(?P<img>https://[^"]+)"'
            r'.{0,500}?itemprop="modelDate"[^>]*>(?P<year>\d{4})<'
            r'.{0,200}?itemprop="mileageFromOdometer"[^>]*>(?P<km>[\d\.\s]+)\s*km',
            re.I | re.S,
        )
        for m in loose.finditer(html):
            title = m.group("title")
            pm = re.search(r"\$\s*([\d\.]+)", title)
            if not pm:
                continue
            price = _parse_price(pm.group(1))
            year = int(m.group("year"))
            km = _parse_km(m.group("km"))
            if year < int(anio_min) or (anio_max and year > int(anio_max)):
                continue
            if not price:
                continue
            href = m.group("href")
            if any(c.get("url", "").endswith(href) for c in comps):
                continue
            comps.append(
                {
                    "portal": "autocosmos",
                    "title": title[:140],
                    "price": price,
                    "year": year,
                    "km": km,
                    "currency": "CLP",
                    "location": "",
                    "image_url": m.group("img"),
                    "url": _abs_url("https://www.autocosmos.cl", href),
                    "external_id": href.rstrip("/").split("/")[-1],
                }
            )

    return {
        "portal": "autocosmos",
        "ok": bool(comps),
        "error": None if comps else "Sin avisos parseables",
        "search_url": url,
        "comps": comps[:24],
        "count": len(comps),
    }


def fetch_mercadolibre_comps(
    *,
    marca: str,
    modelo: str,
    anio_min: int,
    anio_max: int | None = None,
    km_min: int = 0,
    km_max: int | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    q = f"{marca} {modelo}".strip()
    api = "https://api.mercadolibre.com/sites/MLC/search"
    params: dict[str, Any] = {
        "category": "MLC1744",
        "q": q,
        "limit": 20,
    }
    # year filter attribute if supported
    if anio_min:
        params["VEHICLE_YEAR"] = f"{int(anio_min)}-{int(anio_max or date.today().year)}"
    search_url = build_search_urls(
        marca=marca, modelo=modelo, anio_min=anio_min, anio_max=anio_max, km_min=km_min, km_max=km_max
    )["mercadolibre"]
    try:
        with httpx.Client(timeout=timeout_s, headers={"User-Agent": UA, "Accept": "application/json"}, follow_redirects=True) as client:
            r = client.get(api, params=params)
            if r.status_code >= 400:
                return {
                    "portal": "mercadolibre",
                    "ok": False,
                    "error": f"HTTP {r.status_code}",
                    "search_url": search_url,
                    "comps": [],
                }
            payload = r.json()
    except Exception as exc:
        return {"portal": "mercadolibre", "ok": False, "error": str(exc), "search_url": search_url, "comps": []}

    comps: list[dict[str, Any]] = []
    for it in payload.get("results") or []:
        attrs = {a.get("id"): a.get("value_name") for a in (it.get("attributes") or []) if isinstance(a, dict)}
        year = None
        try:
            year = int(str(attrs.get("VEHICLE_YEAR") or "0")[:4])
        except Exception:
            year = None
        km = _parse_km(attrs.get("KILOMETERS"))
        price = _parse_price(it.get("price"))
        if year and year < int(anio_min):
            continue
        if anio_max and year and year > int(anio_max):
            continue
        if km is not None and km < km_min:
            continue
        if km_max is not None and km is not None and km > km_max:
            continue
        if not price:
            continue
        comps.append(
            {
                "portal": "mercadolibre",
                "title": str(it.get("title") or "")[:140],
                "price": price,
                "year": year,
                "km": km,
                "currency": str(it.get("currency_id") or "CLP"),
                "location": ((it.get("address") or {}) if isinstance(it.get("address"), dict) else {}).get("city_name")
                or "",
                "image_url": str(it.get("thumbnail") or it.get("secure_thumbnail") or "").replace("http://", "https://"),
                "url": str(it.get("permalink") or search_url),
                "external_id": str(it.get("id") or ""),
            }
        )
    return {
        "portal": "mercadolibre",
        "ok": bool(comps),
        "error": None if comps else "Sin avisos o API bloqueada",
        "search_url": search_url,
        "comps": comps[:24],
        "count": len(comps),
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _trim_mean(values: list[float], trim_pct: float = 0.15) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    n = len(xs)
    k = int(n * trim_pct)
    core = xs[k : n - k] if n > 4 else xs
    return float(sum(core) / len(core)) if core else float(xs[n // 2])


def estimar_residual_con_mercado(
    *,
    marca: str,
    modelo: str,
    valor_bien: float,
    plazo_meses: int,
    km_anual: float,
    km_inicial: float = 0,
    anio_vehiculo: int | None = None,
    tipo_uso: str = "INTERURBANO",
    haircut_mercado_pct: float = 5.0,
) -> dict[str, Any]:
    """
    Estima residual futuro buscando hoy vehículos con edad/km similares al término del arriendo.
    """
    anio_hoy = date.today().year
    anio_v = int(anio_vehiculo or anio_hoy)
    anios = max(plazo_meses, 1) / 12.0
    edad_fin = max((anio_hoy - anio_v) + anios, 0)
    km_fin = float(km_inicial or 0) + float(km_anual or 0) * anios
    anio_comparable = max(anio_hoy - int(round(edad_fin)), 1995)
    # Ventana de años ±1 alrededor del año comparable
    anio_min = max(anio_comparable - 1, 1995)
    anio_max = min(anio_comparable + 1, anio_hoy)
    km_min = max(int(km_fin * 0.75), 0)
    km_max = int(km_fin * 1.35) if km_fin > 0 else None

    search_urls = build_search_urls(
        marca=marca,
        modelo=modelo,
        anio_min=anio_min,
        anio_max=anio_max,
        km_min=km_min,
        km_max=km_max,
    )

    sources = [
        fetch_chileautos_comps(
            marca=marca, modelo=modelo, anio_min=anio_min, anio_max=anio_max, km_min=km_min, km_max=km_max
        ),
        fetch_autocosmos_comps(
            marca=marca, modelo=modelo, anio_min=anio_min, anio_max=anio_max, km_min=km_min, km_max=km_max
        ),
        fetch_mercadolibre_comps(
            marca=marca, modelo=modelo, anio_min=anio_min, anio_max=anio_max, km_min=km_min, km_max=km_max
        ),
    ]

    all_comps: list[dict[str, Any]] = []
    for src in sources:
        all_comps.extend(src.get("comps") or [])

    # Prefer comps close in km; keep all as evidence
    scored: list[tuple[float, dict[str, Any]]] = []
    for c in all_comps:
        price = float(c.get("price") or 0)
        if price <= 0:
            continue
        km = c.get("km")
        score = abs(float(km) - km_fin) if km is not None else 25000.0
        scored.append((score, c))
    scored.sort(key=lambda x: x[0])
    top = [c for _, c in scored[:18]]
    prices = [float(c["price"]) for c in top]
    mediana = _median(prices)
    media_rec = _trim_mean(prices)

    uso = str(tipo_uso or "INTERURBANO").upper()
    uso_hair = {"URBANO": 0.0, "INTERURBANO": 0.01, "MIXTO": 0.02, "FAENA": 0.04, "MINERO": 0.06}.get(uso, 0.01)
    hair = max(float(haircut_mercado_pct), 0) / 100.0 + uso_hair

    if mediana and mediana > 0:
        sugerido = mediana * (1.0 - hair)
        fuente = "mercado_portales"
        metodo = "mediana_comparables"
    else:
        # Curva de retención calibrada a mercado CL (pickups/livianos): ~70-75% a 3 años
        ret = max(0.38, 0.92 - 0.07 * edad_fin - 0.0000009 * max(km_fin - 15000 * max(edad_fin, 0.5), 0))
        if uso in {"FAENA", "MINERO"}:
            ret *= 0.92 if uso == "FAENA" else 0.88
        sugerido = float(valor_bien) * ret * (1.0 - hair)
        fuente = "curva_mercado_calibrada"
        metodo = "retencion_edad_km"

    sugerido = max(min(sugerido, float(valor_bien) * 0.95), 0)
    capital = max(float(valor_bien) - sugerido, 0)

    return {
        "fuente": fuente,
        "metodo": metodo,
        "consultado_en": datetime.now(timezone.utc).isoformat(),
        "marca": marca,
        "modelo": modelo,
        "tipo_uso": uso,
        "plazo_meses": int(plazo_meses),
        "anios_contrato": round(anios, 2),
        "edad_fin_anios": round(edad_fin, 2),
        "km_fin_estimado": round(km_fin, 0),
        "anio_comparable": anio_comparable,
        "filtro": {
            "anio_min": anio_min,
            "anio_max": anio_max,
            "km_min": km_min,
            "km_max": km_max,
        },
        "search_urls": search_urls,
        "portales": [
            {
                "portal": s.get("portal"),
                "ok": bool(s.get("ok")),
                "error": s.get("error"),
                "search_url": s.get("search_url"),
                "count": int(s.get("count") or len(s.get("comps") or [])),
            }
            for s in sources
        ],
        "comparables": top[:12],
        "stats": {
            "n": len(prices),
            "mediana": mediana,
            "media_recortada": media_rec,
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
            "haircut_pct": round(hair * 100, 2),
        },
        "valor_bien": float(valor_bien),
        "valor_residual_sugerido": round(sugerido, 0),
        "capital_amortizable_sugerido": round(capital, 0),
        "pct_residual_sugerido": round(sugerido / float(valor_bien) * 100, 2) if valor_bien else 0,
        "nota": (
            "Residual estimado con avisos actuales de vehículos equivalentes en edad/km al término del arriendo "
            "(Chileautos, Autocosmos y Mercado Libre). Se aplica haircut comercial por tipo de uso."
            if fuente == "mercado_portales"
            else "Portales sin respuesta completa; se usó curva de retención calibrada a mercado chileno. "
            "Revise los links de búsqueda adjuntos."
        ),
    }
