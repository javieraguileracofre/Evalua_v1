# -*- coding: utf-8 -*-
from services.leasing_operativo.catalogo_mercado_cl import (
    catalogo_boot,
    marcas_para_tipo,
    modelos_para_marca,
    normalizar_marca_modelo,
    segmento_para_tipo,
)


def test_hyundai_liviano_no_mezcla_otras_marcas():
    modelos = modelos_para_marca("Hyundai", "VEHICULO_LIVIANO")
    assert "Tucson" in modelos
    assert "Creta" in modelos
    assert "Accent" in modelos
    assert "Hilux" not in modelos
    assert "Ranger" not in modelos
    assert "Actros" not in modelos
    assert "PC200" not in modelos


def test_toyota_camioneta_hilux():
    modelos = modelos_para_marca("Toyota", "CAMIONETA")
    assert modelos[0] == "Hilux"
    assert "RAV4" not in modelos


def test_marcas_por_segmento():
    liv = marcas_para_tipo("VEHICULO_LIVIANO")
    pes = marcas_para_tipo("VEHICULO_PESADO")
    assert "Hyundai" in liv
    assert "Caterpillar" not in liv
    assert "Volvo" in pes
    assert "Scania" in pes
    assert liv[-1] == "Otro"


def test_furgon_partner_porter():
    assert "Partner" in modelos_para_marca("Peugeot", "FURGON")
    assert "Porter" in modelos_para_marca("Hyundai", "FURGON")


def test_maquinaria_cat_komatsu():
    assert "320D" in modelos_para_marca("Caterpillar", "MAQUINARIA")
    assert "PC200" in modelos_para_marca("Komatsu", "GRUA")


def test_segmento_mapping():
    assert segmento_para_tipo("VEHICULO_GERENCIAL") == "GERENCIAL"
    assert segmento_para_tipo("desconocido") == "LIVIANO"


def test_catalogo_boot_incluye_por_tipo():
    boot = catalogo_boot([{"codigo": "VEHICULO_LIVIANO"}, {"codigo": "CAMIONETA"}])
    assert "fuente" in boot
    assert "Tucson" in boot["por_tipo"]["VEHICULO_LIVIANO"]["Hyundai"]
    assert "Hilux" in boot["por_tipo"]["CAMIONETA"]["Toyota"]
    assert boot["marcas"]
    assert boot["modelos"]


def test_normalizar_marca_modelo():
    marca, modelo = normalizar_marca_modelo("hyundai", "tucson", "VEHICULO_LIVIANO")
    assert marca == "Hyundai"
    assert modelo == "Tucson"
    marca2, modelo2 = normalizar_marca_modelo("Hyundai", "ModeloLibreXYZ", "VEHICULO_LIVIANO")
    assert marca2 == "Hyundai"
    assert modelo2 == "ModeloLibreXYZ"
