"""Resultados de búsqueda agrupados por ferretería, con orden elegible y sin doble registro al reordenar."""

from busqueda.models import Busqueda

LAT, LON = -33.4290, -70.6040
KM = 0.009  # ~1 km de latitud
PARAMS = {"q": "llave", "radio": 3, "lat": str(LAT), "lon": str(LON)}


def _escenario(crear):
    """Cerca: caro y sin stock confirmado; medio: barato con stock; lejos: dos productos, uno con stock."""
    cerca, medio, lejos = (crear.comercio(lat=LAT + k * KM) for k in (0.3, 1, 2))
    crear.producto(cerca, "Llave A", stock=0, precio_referencial=9000)
    crear.producto(medio, "Llave B", precio_referencial=500)
    crear.producto(lejos, "Llave C", precio_referencial=3000)
    crear.producto(lejos, "Llave D", stock=0, precio_referencial=2000)
    return cerca, medio, lejos


def _ids(r):
    return [g["comercio"].pk for g in r.context["grupos"]]


def test_una_tarjeta_por_ferreteria_con_sus_productos_mas_baratos_primero(crear, client):
    cerca, medio, lejos = _escenario(crear)
    r = client.get("/", PARAMS)
    assert _ids(r) == [cerca.pk, medio.pk, lejos.pk]
    assert [p.nombre for p in r.context["grupos"][2]["productos"]] == ["Llave D", "Llave C"]
    # Pin numerado = posición de la tarjeta; un marcador por ferretería, no por producto.
    assert [(m["n"], m["nombre"]) for m in r.context["marcadores"]] == [
        (1, cerca.nombre), (2, medio.nombre), (3, lejos.nombre)
    ]
    html = r.content.decode()
    assert html.count('class="tarjeta-ferreteria"') == 3 and 'id="ferreteria-3"' in html


def test_orden_por_precio_y_por_stock(crear, client):
    cerca, medio, lejos = _escenario(crear)
    assert _ids(client.get("/", {**PARAMS, "orden": "precio"})) == [medio.pk, lejos.pk, cerca.pk]
    assert _ids(client.get("/", {**PARAMS, "orden": "stock"})) == [medio.pk, lejos.pk, cerca.pk]
    r = client.get("/", {**PARAMS, "orden": "stock"})
    assert r.context["orden"] == "stock" and '<option value="stock" selected>' in r.content.decode()


def test_orden_invalido_se_ignora_y_queda_mas_cerca(crear, client):
    cerca, medio, lejos = _escenario(crear)
    for orden in ("distancia; DROP", "", "__class__"):
        r = client.get("/", {**PARAMS, "orden": orden})
        assert r.status_code == 200 and r.context["orden"] == "cerca"
        assert _ids(r) == [cerca.pk, medio.pk, lejos.pk]


def test_reordenar_no_registra_otra_busqueda(crear, client):
    _escenario(crear)
    client.get("/", PARAMS)
    client.get("/", {**PARAMS, "orden": "precio", "reordenar": "1"})
    assert Busqueda.objects.count() == 1


def test_sin_resultados_muestra_aviso_y_ningun_pin(db, client):
    r = client.get("/", PARAMS)
    assert r.context["grupos"] == [] and r.context["marcadores"] == []
    assert "No encontramos" in r.content.decode()
