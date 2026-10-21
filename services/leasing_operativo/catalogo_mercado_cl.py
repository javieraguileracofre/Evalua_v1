# services/leasing_operativo/catalogo_mercado_cl.py
# -*- coding: utf-8 -*-
"""Catálogo marca → modelos orientado al mercado chileno (flota / leasing operativo).

Fuente de referencia (oferta y liquidez secundaria CL, no exhaustivo):
- Rankings ANAC / Autocosmos 2024–2025 (pasajeros, SUV, pick-ups, comerciales).
- Líneas vigentes de importadores en Chile (Hyundai, Toyota, Kia, etc.).
- Segmentos de camión y maquinaria con red de postventa local.

Se priorizan modelos con rotación real en Chileautos / Autocosmos / ML para residuales.
"""
from __future__ import annotations

from typing import Any

# Segmentos internos del catálogo (no son códigos de BD).
SEG_LIVIANO = "LIVIANO"
SEG_GERENCIAL = "GERENCIAL"
SEG_CAMIONETA = "CAMIONETA"
SEG_FURGON = "FURGON"
SEG_PESADO = "PESADO"
SEG_MAQUINARIA = "MAQUINARIA"

# Códigos leasing_op_tipo_activo → segmento de catálogo.
TIPO_A_SEGMENTO: dict[str, str] = {
    "VEHICULO_LIVIANO": SEG_LIVIANO,
    "VEHICULO_GERENCIAL": SEG_GERENCIAL,
    "CAMIONETA": SEG_CAMIONETA,
    "FURGON": SEG_FURGON,
    "VEHICULO_PESADO": SEG_PESADO,
    "GRUA": SEG_MAQUINARIA,
    "MAQUINARIA": SEG_MAQUINARIA,
    "EQUIPO_IT": SEG_LIVIANO,
}

_OTRO = "Otro"

# Marca → modelos por segmento. Orden: liquidez / relevancia comercial Chile.
_CATALOGO: dict[str, dict[str, list[str]]] = {
    SEG_LIVIANO: {
        "Toyota": [
            "Yaris",
            "Yaris Cross",
            "Raize",
            "Corolla",
            "Corolla Cross",
            "RAV4",
            "C-HR",
        ],
        "Hyundai": [
            "Grand i10 HB",
            "Grand i10 Sedán",
            "i20",
            "Accent",
            "Venue",
            "Creta",
            "Creta Grand",
            "Kona",
            "Tucson",
            "Santa Fe",
            "Palisade",
            "IONIQ 5",
        ],
        "Kia": [
            "Morning",
            "Soluto",
            "Rio",
            "Sonet",
            "Seltos",
            "Sportage",
            "Sorento",
            "EV6",
        ],
        "Chevrolet": [
            "Sail",
            "Onix",
            "Groove",
            "Tracker",
            "Captiva",
            "Equinox",
            "Traverse",
        ],
        "Suzuki": [
            "S-Presso",
            "Celerio",
            "Swift",
            "Baleno",
            "Fronx",
            "Vitara",
            "Jimny",
            "Grand Vitara",
        ],
        "Nissan": ["Versa", "March", "Kicks", "X-Trail", "Qashqai", "Pathfinder"],
        "Mitsubishi": ["ASX", "Outlander", "Eclipse Cross", "Montero Sport"],
        "Ford": ["Territory", "Escape", "Explorer", "Bronco Sport"],
        "Mazda": ["Mazda2", "Mazda3", "CX-3", "CX-5", "CX-30", "CX-50", "CX-60"],
        "MG": ["MG3", "ZS", "ZX", "HS", "RX5", "Marvel R"],
        "Chery": ["Arrizo 5", "Tiggo 2", "Tiggo 3 Pro", "Tiggo 4 Pro", "Tiggo 7 Pro", "Tiggo 8 Pro"],
        "GWM": ["Haval Jolion", "Haval H6", "Ora 03"],
        "Peugeot": ["208", "2008", "3008", "5008"],
        "Volkswagen": ["Polo", "Virtus", "T-Cross", "Taos", "Tiguan", "ID.4"],
        "Subaru": ["Impreza", "Crosstrek", "Forester", "Outback"],
        "Changan": ["Alsvin", "CS35 Plus", "X7 Plus", "UNI-T"],
        "Geely": ["Coolray", "Azkarra", "Okavango", "Geometry C"],
        "Omoda": ["C5", "E5"],
        "Citroën": ["C3", "C4 Cactus", "C5 Aircross"],
        "Opel": ["Corsa", "Mokka", "Crossland"],
        "Honda": ["City", "HR-V", "CR-V", "ZR-V"],
        "BMW": ["Serie 1", "Serie 3", "X1", "X3", "X5", "iX1", "iX3"],
        "Mercedes-Benz": ["Clase A", "Clase C", "GLA", "GLB", "GLC", "EQA", "EQB"],
        "Audi": ["A3", "A4", "Q3", "Q5", "Q7", "Q8 e-tron"],
        "Volvo": ["XC40", "XC60", "XC90", "EX30", "EX40"],
        _OTRO: [_OTRO],
    },
    SEG_GERENCIAL: {
        "Toyota": ["Corolla", "Corolla Cross", "Camry", "RAV4", "Highlander", "Land Cruiser Prado"],
        "Hyundai": ["Tucson", "Santa Fe", "Palisade", "IONIQ 5", "IONIQ 6"],
        "Kia": ["Sportage", "Sorento", "Carnival", "EV6", "EV9"],
        "Mazda": ["Mazda3", "CX-5", "CX-50", "CX-60", "CX-90"],
        "BMW": ["Serie 3", "Serie 5", "X3", "X5", "X7", "i4", "iX"],
        "Mercedes-Benz": ["Clase C", "Clase E", "GLC", "GLE", "EQE", "EQS"],
        "Audi": ["A4", "A6", "Q5", "Q7", "Q8", "e-tron GT"],
        "Volvo": ["S60", "XC60", "XC90", "EX90"],
        "Volkswagen": ["Passat", "Tiguan", "Touareg", "ID.4", "ID.7"],
        "Subaru": ["Outback", "Forester", "Crosstrek"],
        "Ford": ["Explorer", "Edge", "Mustang Mach-E"],
        "Chevrolet": ["Equinox", "Traverse", "Blazer EV"],
        "Lexus": ["UX", "NX", "RX", "ES"],
        "Jeep": ["Compass", "Grand Cherokee", "Wrangler"],
        "Land Rover": ["Discovery Sport", "Defender", "Range Rover Evoque", "Range Rover Sport"],
        _OTRO: [_OTRO],
    },
    SEG_CAMIONETA: {
        "Toyota": ["Hilux", "Tacoma", "Land Cruiser"],
        "Mitsubishi": ["L200", "Triton"],
        "Ford": ["Ranger", "Maverick", "F-150", "Ranger Raptor"],
        "Chevrolet": ["Colorado", "Silverado", "Montana", "S10"],
        "GWM": ["Poer", "Poer Cabina Simple", "Wingle 7", "Cannon"],
        "Nissan": ["Navara", "Frontier"],
        "Mazda": ["BT-50"],
        "Maxus": ["T60", "T90"],
        "RAM": ["700", "1500", "Rampage"],
        "Volkswagen": ["Amarok", "Saveiro"],
        "Isuzu": ["D-Max"],
        "JMC": ["Grand Avenue", "Vigus", "Vigus Pro"],
        "Changan": ["Hunter", "F70"],
        "Foton": ["G7", "Tunland"],
        "KGM": ["Grand Musso", "Musso Sports"],
        "Jac": ["T8", "T9"],
        "Peugeot": ["Landtrek"],
        _OTRO: [_OTRO],
    },
    SEG_FURGON: {
        "Peugeot": ["Partner", "Rifter", "Expert", "Boxer"],
        "Citroën": ["Berlingo", "Jumpy", "Jumper"],
        "Hyundai": ["Porter", "Staria", "Staria Furgón", "H100"],
        "Kia": ["Frontier", "K2700", "K2500"],
        "Ford": ["Transit", "Transit Custom", "Ranger Cabina Simple"],
        "Mercedes-Benz": ["Sprinter", "Vito", "Citan"],
        "Chevrolet": ["N400 Max", "N300", "Tornado"],
        "Foton": ["TM3", "TM5", "Midi", "Toano"],
        "Maxus": ["Deliver 9", "G10", "V80", "eDeliver 9"],
        "Volkswagen": ["Caddy", "Transporter", "Crafter"],
        "Opel": ["Combo", "Vivaro", "Movano"],
        "Jac": ["Sunray", "X200", "X200 Chasis"],
        "Changan": ["MD201", "MD301", "Kaicene"],
        "Toyota": ["Hiace", "Proace City"],
        "Nissan": ["NV350", "Urvan"],
        "Iveco": ["Daily"],
        "Renault": ["Kangoo", "Master", "Trafic"],
        "Dongfeng": ["DF212", "Rich"],
        _OTRO: [_OTRO],
    },
    SEG_PESADO: {
        "Mercedes-Benz": [
            "Actros",
            "Arocs",
            "Atego",
            "Accelo",
            "eActros 300",
            "eActros 400",
            "eActros 600",
        ],
        "Volvo": ["FH", "FM", "FMX", "FE", "FL", "VNL"],
        "Scania": ["R450", "R500", "G410", "G450", "P320", "P360", "S500"],
        "Isuzu": ["NPR", "NQR", "FTR", "FVR", "FYH", "GXZ"],
        "Foton": [
            "Miler 314",
            "Miler 513",
            "S614",
            "S915",
            "S1016L",
            "Aumark",
            "Auman",
            "Auman Galaxy",
            "E Aumark 1135",
            "E Auman 1851",
        ],
        "Jac": ["NSeries", "HFC", "Lander 3430", "Lander 3550", "Sunray Chasis"],
        "Freightliner": ["Cascadia", "M2", "Coronado"],
        "Kenworth": ["T680", "T880", "W900"],
        "International": ["LT", "HV", "HX"],
        "MAN": ["TGX", "TGS", "TGM"],
        "Iveco": ["S-Way", "T-Way", "Eurocargo", "Daily Chasis"],
        "Hino": ["500", "700", "XZU"],
        "Dongfeng": ["KL", "KX", "Captain"],
        "Sinotruk": ["Howo", "Howo T7H"],
        "Shacman": ["X3000", "X5000", "F3000"],
        "Hyundai": ["HD65", "HD78", "HD120", "Xcient"],
        "Mitsubishi Fuso": ["Canter", "Fighter", "Super Great"],
        _OTRO: [_OTRO],
    },
    SEG_MAQUINARIA: {
        "Caterpillar": [
            "320",
            "320D",
            "323",
            "336",
            "950",
            "966",
            "D6",
            "D8",
            "140",
            "CS11",
        ],
        "Komatsu": ["PC200", "PC210", "PC300", "WA380", "WA470", "D65", "D85", "HM400"],
        "JCB": ["3CX", "4CX", "JS130", "JS200", "530", "540"],
        "Volvo": ["EC210", "EC300", "L120", "L150", "A30", "A40"],
        "Liebherr": ["R920", "R946", "L550", "L566", "PR736"],
        "Hitachi": ["ZX200", "ZX210", "ZX350", "ZW220", "ZW310"],
        "John Deere": ["310L", "544", "624", "670G", "850L"],
        "Case": ["580N", "590SN", "CX210", "CX350", "621G"],
        "Doosan": ["DX225", "DX300", "DL200", "DL300"],
        "Sany": ["SY215", "SY365", "SW405", "STR130"],
        "XCMG": ["XE215", "XE370", "LW500", "GR215"],
        "LiuGong": ["922E", "936E", "856H", "4180D"],
        "Bobcat": ["S650", "S770", "T770", "E85", "E165"],
        "Manitou": ["MT1440", "MT1840", "MHT"],
        "Genie": ["S-65", "S-85", "ZX-135"],
        "JLG": ["600S", "800S", "1250AJP"],
        "Grove": ["RT530E", "RT765E", "GMK4100"],
        "Terex": ["RT555", "RT780"],
        "Zoomlion": ["ZE215E", "ZE370E", "QY25V"],
        _OTRO: [_OTRO],
    },
}


def segmento_para_tipo(codigo_tipo: str | None) -> str:
    cod = (codigo_tipo or "").strip().upper()
    return TIPO_A_SEGMENTO.get(cod, SEG_LIVIANO)


def _catalogo_segmento(segmento: str) -> dict[str, list[str]]:
    return _CATALOGO.get(segmento) or _CATALOGO[SEG_LIVIANO]


def marcas_para_tipo(codigo_tipo: str | None = None) -> list[str]:
    """Lista ordenada de marcas disponibles para el tipo de activo."""
    cat = _catalogo_segmento(segmento_para_tipo(codigo_tipo))
    marcas = [m for m in cat.keys() if m != _OTRO]
    marcas.sort(key=lambda x: x.casefold())
    marcas.append(_OTRO)
    return marcas


def modelos_para_marca(marca: str, codigo_tipo: str | None = None) -> list[str]:
    """Modelos de la marca en el segmento del tipo; si no hay match, busca en otros segmentos."""
    marca_n = (marca or "").strip() or _OTRO
    seg = segmento_para_tipo(codigo_tipo)
    cat = _catalogo_segmento(seg)
    if marca_n in cat:
        return list(cat[marca_n])
    # Fallback: misma marca en otro segmento (p. ej. Toyota en liviano vs camioneta).
    for other in _CATALOGO.values():
        if marca_n in other:
            return list(other[marca_n])
    return [_OTRO]


def catalogo_boot(tipos: list[Any] | None = None) -> dict[str, Any]:
    """Payload para el simulador UI: catálogo por código de tipo + helpers planos.

    `tipos` puede ser ORM o dicts con `.codigo` / `codigo`.
    """
    por_tipo: dict[str, dict[str, list[str]]] = {}
    codigos: list[str] = []
    if tipos:
        for t in tipos:
            cod = str(getattr(t, "codigo", None) or (t.get("codigo") if isinstance(t, dict) else "") or "").upper()
            if not cod:
                continue
            codigos.append(cod)
            seg = segmento_para_tipo(cod)
            por_tipo[cod] = {m: list(mods) for m, mods in _catalogo_segmento(seg).items()}

    # Asegurar segmentos base aunque no haya tipos en BD aún.
    for cod, seg in TIPO_A_SEGMENTO.items():
        if cod not in por_tipo:
            por_tipo[cod] = {m: list(mods) for m, mods in _catalogo_segmento(seg).items()}

    marcas_default = marcas_para_tipo("VEHICULO_LIVIANO")
    modelos_default = modelos_para_marca(marcas_default[0] if marcas_default else _OTRO, "VEHICULO_LIVIANO")
    return {
        "fuente": "Mercado Chile (ANAC / oferta local 2024-2025)",
        "por_tipo": por_tipo,
        "marcas": marcas_default,
        "modelos": modelos_default,
        "segmento_por_tipo": dict(TIPO_A_SEGMENTO),
    }


def normalizar_marca_modelo(
    marca: str | None,
    modelo: str | None,
    codigo_tipo: str | None = None,
) -> tuple[str, str]:
    """Ajusta marca/modelo a valores del catálogo si es posible; conserva texto libre vía Otro."""
    marcas = marcas_para_tipo(codigo_tipo)
    marca_n = (marca or "").strip()
    if not marca_n:
        marca_n = marcas[0] if marcas else _OTRO
    elif marca_n not in marcas:
        # Match case-insensitive
        found = next((m for m in marcas if m.casefold() == marca_n.casefold()), None)
        marca_n = found or marca_n

    modelos = modelos_para_marca(marca_n, codigo_tipo)
    modelo_n = (modelo or "").strip()
    if not modelo_n:
        modelo_n = modelos[0] if modelos else _OTRO
    elif modelo_n not in modelos:
        found = next((m for m in modelos if m.casefold() == modelo_n.casefold()), None)
        if found:
            modelo_n = found
        # Si el usuario escribió un modelo libre, se conserva (compat. con cotizaciones antiguas).
    return marca_n, modelo_n
