from datetime import timedelta

from django.contrib.gis.geos import Point
from django.utils import timezone

from busqueda.models import Busqueda
from catalogo.models import Producto
from reservas import servicios
from reservas.models import Aviso, Reserva
from valoraciones.models import Valoracion


def _busqueda(termino, lat, con_stock, lon=-70.6040):
    return Busqueda.objects.create(
        termino=termino,
        ubicacion_aprox=Point(lon, lat, srid=4326),
        radio_km=2,
        n_resultados=1,
        n_con_stock=con_stock,
    )


def test_zona_frente_al_catalogo_pone_primero_las_oportunidades(crear, ingresar):
    comercio = crear.comercio()
    crear.producto(comercio, 'Teflón 1/2"', stock=0)
    crear.producto(comercio, 'Llave francesa 8"', stock=2)
    crear.producto(comercio, "Llave de paso", stock=1)
    broca = crear.producto(comercio, "Broca madera 10 mm", stock=4)
    Producto.objects.filter(pk=broca.pk).update(actualizado_en=timezone.now() - timedelta(days=5))
    crear.producto(crear.comercio(), "Taladro percutor", stock=9)  # de otro comercio: no cuenta como tuyo
    for termino, con_stock in [("llave", 1), ("llave", 0), ("teflon", 0), ("taladro", 0), ("broca", 1)]:
        _busqueda(termino, -33.4290, con_stock)
    _busqueda("lejos", -33.60, 0)  # a ~19 km: fuera de la zona

    ctx = ingresar(comercio.propietario).get("/panel/reportes/").context
    assert [(t["termino"], t["n"], t["sin_stock"], t["situacion"]) for t in ctx["demanda"]] == [
        ("teflon", 1, 1, "Lo tienes sin stock"),
        ("taladro", 1, 1, "No lo vendes"),
        ("broca", 1, 0, "Por confirmar"),
        ("llave", 2, 1, "Con stock (3)"),
    ]
    assert [(p.nombre, p.buscado) for p in ctx["reponer"]] == [("Broca madera 10 mm", 1), ('Teflón 1/2"', 1)]


def test_reponer_ordena_por_busquedas_mas_reservas(crear, ingresar):
    comercio = crear.comercio()
    reservado = crear.producto(comercio, "Cinta aislante", stock=1)
    crear.producto(comercio, "Silicona", stock=0)
    crear.producto(comercio, "Huincha", stock=0)
    servicios.crear_reserva(crear.usuario(), reservado.pk, 1)  # deja el stock en 0
    _busqueda("silicona", -33.4290, 0)
    ctx = ingresar(comercio.propietario).get("/panel/reportes/").context
    assert [(p.nombre, p.buscado, p.reservado) for p in ctx["reponer"]] == [
        ("Cinta aislante", 0, 1),
        ("Silicona", 1, 0),
        ("Huincha", 0, 0),
    ]


def test_resumen_y_productos_mas_reservados(crear, ingresar):
    comercio = crear.comercio()
    llave = crear.producto(comercio, stock=20, precio_referencial=1000)
    broca = crear.producto(comercio, "Broca", stock=20, precio_referencial=500)
    ahora = timezone.now()
    retirada = servicios.crear_reserva(crear.usuario(), llave.pk, 2)
    Reserva.objects.filter(pk=retirada.pk).update(creada_en=ahora - timedelta(minutes=20))
    servicios.atender_reserva(retirada.pk, comercio.propietario)
    servicios.confirmar_retiro(retirada.pk, comercio.propietario)
    anulada = servicios.crear_reserva(crear.usuario(), llave.pk, 1)
    servicios.anular_reserva(anulada.pk, comercio.propietario, por_cliente=False)
    vencida = servicios.crear_reserva(crear.usuario(), broca.pk, 3)
    Reserva.objects.filter(pk=vencida.pk).update(estado="expirada", cerrada_en=ahora)
    Valoracion.objects.create(
        reserva=retirada, comercio=comercio, cliente=retirada.cliente, puntaje=4, estado="aprobada"
    )

    ctx = ingresar(comercio.propietario).get("/panel/reportes/").context
    r = ctx["resumen"]
    assert (r["total"], r["retiradas"], r["retirado"]) == (3, 1, 2000)
    assert (r["perdidas"], r["perdido"], r["sin_atender"]) == (2, 2500, 1)
    assert r["tasa_retiro"] == 33 and r["atencion_min"] == 20
    assert (r["nota"], r["valoraciones"]) == (4, 1)
    assert [
        (p["producto__nombre"], p["n"], p["unidades"], p["retiradas"], p["perdidas"], p["retirado"])
        for p in ctx["mas_reservados"]
    ] == [('Llave francesa 8"', 2, 3, 1, 1, 2000), ("Broca", 1, 3, 0, 1, 0)]


def test_reportes_del_comerciante_no_mezclan_comercios(crear, ingresar):
    otro = crear.comercio()
    servicios.crear_reserva(crear.usuario(), crear.producto(otro).pk, 1)
    _busqueda("llave", -33.4290, 1)
    comercio = crear.comercio()
    ctx = ingresar(comercio.propietario).get("/panel/reportes/").context
    assert ctx["resumen"]["total"] == 0 and ctx["resumen"]["tasa_retiro"] is None
    assert ctx["resumen"]["atencion_min"] is None and ctx["resumen"]["valoraciones"] == 0
    assert list(ctx["mas_reservados"]) == [] and ctx["demanda"][0]["situacion"] == "No lo vendes"


def test_comercio_sin_ubicacion_no_ve_demanda_de_zona(crear, ingresar):
    comercio = crear.comercio()
    comercio.ubicacion = None
    comercio.save()
    crear.producto(comercio, stock=0)
    _busqueda("llave", -33.4290, 0)
    ctx = ingresar(comercio.propietario).get("/panel/reportes/").context
    assert ctx["demanda"] == [] and [(p.buscado, p.reservado) for p in ctx["reponer"]] == [(0, 0)]


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
