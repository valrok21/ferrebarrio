from django.contrib.gis.geos import Point

from busqueda.models import Busqueda
from reservas import servicios
from reservas.models import Aviso


def _busqueda(termino, lat, con_stock, lon=-70.6040):
    return Busqueda.objects.create(
        termino=termino,
        ubicacion_aprox=Point(lon, lat, srid=4326),
        radio_km=2,
        n_resultados=1,
        n_con_stock=con_stock,
    )


def test_reportes_del_comerciante(crear, ingresar):
    comercio = crear.comercio()
    producto = crear.producto(comercio, stock=2)
    crear.producto(comercio, "Agotado", stock=0)
    for termino, con_stock in [("llave", 1), ("llave", 0), ("taladro", 0)]:
        _busqueda(termino, -33.4290, con_stock)
    _busqueda("lejos", -33.60, 0)  # a ~19 km: fuera de la zona
    cliente = crear.usuario()
    servicios.confirmar_retiro(servicios.crear_reserva(cliente, producto.pk, 1).pk, comercio.propietario)
    servicios.anular_reserva(servicios.crear_reserva(cliente, producto.pk, 1).pk, cliente)
    ctx = ingresar(comercio.propietario).get("/panel/reportes/").context
    assert [(b["termino"], b["n"]) for b in ctx["mas_buscados"]] == [("llave", 2), ("taladro", 1)]
    assert [(b["termino"], b["n"]) for b in ctx["sin_stock"]] == [("llave", 1), ("taladro", 1)]
    assert ctx["tasa_retiro"] == 50
    assert [p.nombre for p in ctx["quiebres"]] == ["Agotado"]


def test_reportes_del_comerciante_no_mezclan_comercios(crear, ingresar):
    otro = crear.comercio()
    servicios.crear_reserva(crear.usuario(), crear.producto(otro).pk, 1)
    ctx = ingresar(crear.comercio().propietario).get("/panel/reportes/").context
    assert list(ctx["por_estado"]) == [] and ctx["tasa_retiro"] is None


def test_indicadores_del_administrador(crear, ingresar):
    crear.producto(crear.comercio())
    crear.comercio(estado="pendiente")
    _busqueda("llave", -33.4290, 1)
    Busqueda.objects.create(
        termino="nada",
        ubicacion_aprox=Point(-70.6, -33.4, srid=4326),
        radio_km=1,
        n_resultados=0,
        n_con_stock=0,
    )
    Aviso.objects.create(destinatario="x@prueba.cl", tipo="t", asunto="a", cuerpo="c", estado="fallido")
    ctx = ingresar(crear.usuario("admin")).get("/administracion/").context
    assert ctx["oe1"] == {"aprobados": 1, "con_catalogo": 1}
    assert ctx["oe2"] == {"total": 2, "con_resultados": 1, "pct": 50}
    assert ctx["solicitudes"] == 1 and len(ctx["fallidos"]) == 1 and ctx["diferencias"] == []
