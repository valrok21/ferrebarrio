"""La búsqueda refresca la marca de stock sin recargar: /stock.json con los productos que ya muestra."""

from comercios.models import Comercio
from reservas import servicios


def _stock(client, *productos, ids=None):
    return client.get("/stock.json", {"ids": ids or ",".join(str(p.pk) for p in productos)}).json()


def test_stock_refleja_reserva_y_anulacion(crear, client):
    producto = crear.producto(crear.comercio(), stock=1)
    assert _stock(client, producto) == {
        str(producto.pk): {"clave": "stock", "texto": "STOCK 1", "reservable": True}
    }
    reserva = servicios.crear_reserva(crear.usuario(), producto.pk, 1)
    assert _stock(client, producto)[str(producto.pk)] == {
        "clave": "sin",
        "texto": "SIN STOCK",
        "reservable": False,
    }
    servicios.anular_reserva(reserva.pk, reserva.comercio.propietario, por_cliente=False)
    assert _stock(client, producto)[str(producto.pk)]["texto"] == "STOCK 1"


def test_stock_solo_de_productos_publicos(crear, client):
    visible = crear.producto(crear.comercio())
    inactivo = crear.producto(crear.comercio(), activo=False)
    pendiente = crear.producto(crear.comercio(estado=Comercio.Estado.PENDIENTE))
    assert list(_stock(client, visible, inactivo, pendiente)) == [str(visible.pk)]


def test_ids_invalidos_se_ignoran_y_se_limitan(crear, client):
    producto = crear.producto(crear.comercio())
    assert _stock(client, ids=f"x,-1,,{producto.pk}") == {
        str(producto.pk): {"clave": "stock", "texto": "STOCK 5", "reservable": True}
    }
    assert _stock(client, ids="") == {}
    assert (
        _stock(client, ids=",".join(["0"] * 50 + [str(producto.pk)])) == {}
    )  # más allá de 50 no se consulta


def test_resultados_traen_id_y_reservar_oculto_sin_stock(crear, client):
    comercio = crear.comercio()
    sin = crear.producto(comercio, "Martillo carpintero", stock=0)
    con = crear.producto(comercio, "Martillo de goma", stock=3)
    html = client.get(
        "/", {"q": "martillo", "radio": 2, "lat": "-33.4290", "lon": "-70.6040"}
    ).content.decode()
    assert f'data-producto="{sin.pk}"' in html and f'data-producto="{con.pk}"' in html
    assert f'href="/reservar/{sin.pk}/"' in html and html.split(f'href="/reservar/{sin.pk}/"')[1].split(">")[
        0
    ].endswith("hidden")
    assert not html.split(f'href="/reservar/{con.pk}/"')[1].split(">")[0].endswith("hidden")
