from datetime import timedelta

from django.utils import timezone

from busqueda.models import Busqueda
from busqueda.views import buscar

LAT, LON = -33.4290, -70.6040
KM = 0.009  # ~1 km de latitud


def test_buscar_respeta_radio_orden_y_excluye_no_aprobados(crear):
    cerca = crear.producto(crear.comercio(lat=LAT + 0.5 * KM), 'Llave francesa 8"')
    medio = crear.producto(crear.comercio(lat=LAT + 2 * KM), 'Llave francesa 10"')
    crear.producto(crear.comercio(lat=LAT + 5 * KM), 'Llave francesa 12"')  # fuera de 3 km
    crear.producto(crear.comercio(lat=LAT, estado="pendiente"), 'Llave francesa 6"')  # no aprobado
    crear.producto(crear.comercio(lat=LAT), 'Llave francesa 9"', activo=False)  # dado de baja
    crear.producto(crear.comercio(lat=LAT), "Martillo")  # no coincide

    assert buscar("LLAVE  frAncesa", LAT, LON, 3) == [cerca, medio]
    assert buscar("llave", LAT, LON, 1) == [cerca]


def test_buscar_filtra_por_categoria(crear):
    producto = crear.producto(crear.comercio())
    assert buscar("llave", LAT, LON, 3, producto.categoria) == [producto]
    otra = producto.categoria.__class__.objects.exclude(pk=producto.categoria_id).first()
    assert buscar("llave", LAT, LON, 3, otra) == []


def test_marca_por_confirmar_pasadas_72_horas(crear):
    comercio = crear.comercio()
    viejo = crear.producto(comercio, "A", stock=4, actualizado_en=timezone.now() - timedelta(hours=73))
    justo = crear.producto(comercio, "B", stock=4, actualizado_en=timezone.now() - timedelta(hours=71))
    agotado = crear.producto(comercio, "C", stock=0)
    assert viejo.marca[0] == "confirmar"
    assert justo.marca == ("stock", "STOCK 4")
    assert agotado.marca == ("sin", "SIN STOCK")


def test_vista_registra_busqueda_anonima(crear, client):
    crear.producto(crear.comercio(), stock=0)
    r = client.get("/", {"q": "llave", "radio": 3, "lat": "-33.42905", "lon": "-70.60412"})
    assert r.status_code == 200 and len(r.context["resultados"]) == 1
    b = Busqueda.objects.get()
    assert (b.termino, b.n_resultados, b.n_con_stock, b.radio_km) == ("llave", 1, 0, 3)
    assert (b.ubicacion_aprox.y, b.ubicacion_aprox.x) == (-33.429, -70.604)


def test_vista_por_comuna_y_sin_ubicacion(crear, client):
    r = client.get("/", {"q": "llave", "radio": 2, "comuna": "Providencia"})
    assert r.status_code == 200 and r.context["resultados"] == []
    r = client.get("/", {"q": "llave", "radio": 2})
    assert (
        r.context["form"].non_field_errors() and not Busqueda.objects.filter(radio_km=2, comuna="").exists()
    )


def test_vista_rechaza_radio_mayor_a_3_y_termino_con_simbolos(db, client):
    assert (
        "radio"
        in client.get("/", {"q": "llave", "radio": 10, "comuna": "Providencia"}).context["form"].errors
    )
    assert (
        "q" in client.get("/", {"q": "<script>", "radio": 1, "comuna": "Providencia"}).context["form"].errors
    )
    assert not Busqueda.objects.exists()


def test_limite_de_busquedas_por_minuto(db, client, settings):
    settings.BUSQUEDA_POR_MINUTO = 2
    for _ in range(3):
        r = client.get("/", {"q": "llave", "radio": 1, "comuna": "Providencia"})
    assert "muchas búsquedas" in str(r.context["form"].non_field_errors())
    assert Busqueda.objects.count() == 2


def test_politica_referer_permite_teselas_de_osm_sin_filtrar_la_busqueda(client, db):
    # OSM bloquea teselas sin Referer; con "same-origin" el mapa sale en blanco.
    respuesta = client.get("/?q=tornillo")
    assert respuesta["Referrer-Policy"] == "strict-origin-when-cross-origin"
