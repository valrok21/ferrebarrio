"""Caché caída: la búsqueda sigue (freno anti-abuso, falla abierto); el ingreso no (falla cerrado)."""

from unittest import mock

import pytest

from conftest import CLAVE


class CacheCaida(Exception):
    pass


def test_busqueda_sigue_si_cae_la_cache(crear, client):
    crear.producto(crear.comercio(), nombre="Llave inglesa")
    with mock.patch("busqueda.views.cache") as cache:
        cache.add.side_effect = CacheCaida("redis caído")
        r = client.get("/", {"q": "llave", "radio": 1, "lat": "-33.42905", "lon": "-70.60412"})
    assert r.status_code == 200 and len(r.context["resultados"]) == 1


def test_busqueda_limitada_con_cache_sana(db, client, settings):
    settings.BUSQUEDA_POR_MINUTO = 1
    for _ in range(2):
        r = client.get("/", {"q": "llave", "radio": 1, "comuna": "Providencia"})
    assert r.context["form"].non_field_errors()


def test_ingreso_falla_cerrado_si_cae_la_cache(crear, client):
    usuario = crear.usuario()
    with mock.patch("cuentas.forms.cache") as cache:
        cache.get.side_effect = CacheCaida("redis caído")
        with pytest.raises(CacheCaida):
            client.post("/cuentas/ingresar/", {"username": usuario.email, "password": CLAVE})
    assert "_auth_user_id" not in client.session
