"""Origen de la búsqueda: la comuna elegida manda sobre la ubicación que dejó «Usar mi ubicación»."""

from busqueda.forms import BusquedaForm
from comercios.models import COMUNAS

UBICACION = {"lat": "-33.4260", "lon": "-70.6100"}  # Providencia
BASE = {"q": "broca", "radio": 2}


def _punto(datos):
    f = BusquedaForm(datos)
    assert f.is_valid(), f.errors
    return f.cleaned_data["punto"]


def test_comuna_elegida_manda_sobre_la_ubicacion_que_quedo_en_la_pagina():
    assert _punto({**BASE, **UBICACION, "comuna": "Ñuñoa"}) == COMUNAS["Ñuñoa"]


def test_sin_comuna_usa_la_ubicacion_del_navegador():
    assert _punto({**BASE, **UBICACION, "comuna": ""}) == (-33.426, -70.61)


def test_ubicacion_fuera_de_chile_sin_comuna_se_rechaza():
    f = BusquedaForm({**BASE, "lat": "40.4", "lon": "-3.7"})
    assert not f.is_valid() and f.non_field_errors()


def test_resultados_dicen_desde_donde_se_mide(db, client):
    html = client.get("/", {**BASE, **UBICACION, "comuna": "Ñuñoa"}).content.decode()
    # Con comuna no hay punto azul: no es la ubicación de la persona (el círculo marca el centro).
    assert "km del centro de Ñuñoa." in html and "bindTooltip('Tu ubicación')" not in html
    html = client.get("/", {**BASE, **UBICACION}).content.decode()
    assert "km de tu ubicación." in html and "bindTooltip('Tu ubicación')" in html
