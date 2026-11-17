"""Mapa con todas las ferreterías aprobadas: pines grises, sin repetir las numeradas de los resultados."""

PROVIDENCIA = {"q": "broca", "radio": 2, "lat": "-33.4290", "lon": "-70.6040"}


def _nombres(respuesta):
    return {c["nombre"] for c in respuesta.context["todas"]}


def test_portada_muestra_solo_aprobadas_con_ubicacion(crear, client):
    aprobada = crear.comercio()
    pendiente = crear.comercio(estado="pendiente")
    sin_ubicacion = crear.comercio()
    sin_ubicacion.ubicacion = None
    sin_ubicacion.save()
    r = client.get("/")
    assert _nombres(r) == {aprobada.nombre}
    assert pendiente.nombre not in r.content.decode() and 'id="mapa"' in r.content.decode()


def test_resultado_numerado_no_se_repite_en_gris_y_las_lejanas_siguen(crear, client):
    cerca = crear.comercio()
    crear.producto(cerca, nombre="Broca 6 mm")
    lejos = crear.comercio(lat=-33.60, lon=-70.75)  # fuera del radio de 2 km
    crear.producto(lejos, nombre="Broca 6 mm")
    r = client.get("/", PROVIDENCIA)
    assert [m["nombre"] for m in r.context["marcadores"]] == [cerca.nombre]
    assert _nombres(r) == {lejos.nombre}


def test_nombre_del_comerciante_no_llega_como_html_a_leaflet(crear, client):
    # Leaflet inserta como HTML el string que recibe en bindTooltip/bindPopup; el nombre lo escribe el
    # comerciante (XSS persistente). La prueba de ejecución se hizo en Chrome; esto evita
    # la regresión. El nombre solo va en el popup, como nodo DOM (enlace).
    crear.comercio()
    html = client.get("/").content.decode()
    assert "bindTooltip(c.nombre)" not in html and "bindPopup(c.nombre)" not in html
    assert "bindPopup(enlace(c))" in html
