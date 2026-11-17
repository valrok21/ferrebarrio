from datetime import timedelta

from django.utils import timezone

from catalogo.models import Producto
from reservas import servicios
from reservas.models import Reserva


def _reserva(crear, producto, cantidad=1, **campos):
    reserva = servicios.crear_reserva(crear.usuario(), producto.pk, cantidad)
    Reserva.objects.filter(pk=reserva.pk).update(**campos)
    return reserva


def test_panel_ordena_por_vencimiento_y_resume_lo_urgente(crear, ingresar):
    comercio = crear.comercio()
    producto = crear.producto(comercio, stock=20, precio_referencial=1500)
    ahora = timezone.now()
    tarde = _reserva(crear, producto, 2, vence_en=ahora + timedelta(hours=3))
    urgente = _reserva(
        crear, producto, 1, creada_en=ahora - timedelta(minutes=40), vence_en=ahora + timedelta(minutes=30)
    )
    lista = _reserva(crear, producto, 3, vence_en=ahora + timedelta(hours=2))
    servicios.atender_reserva(lista.pk, comercio.propietario)
    servicios.confirmar_retiro(_reserva(crear, producto, 4).pk, comercio.propietario)
    servicios.crear_reserva(crear.usuario(), crear.producto(crear.comercio()).pk, 5)  # de otro comercio

    respuesta = ingresar(comercio.propietario).get("/panel/")
    ctx = respuesta.context
    assert [r.codigo for r in ctx["pendientes"]] == [urgente.codigo, tarde.codigo]
    assert [r.codigo for r in ctx["atendidas"]] == [lista.codigo]
    assert ctx["pendientes"][0].urgente and ctx["pendientes"][0].espera_larga
    assert not ctx["pendientes"][1].urgente and not ctx["pendientes"][1].espera_larga
    cifras = ctx["cifras"]
    assert cifras["espera_larga"] == 1 and cifras["vencen_pronto"] == 1
    assert cifras["comprometido"] == (2 + 1 + 3) * 1500
    assert (cifras["retiradas_hoy"], cifras["retirado_hoy"]) == (1, 4 * 1500)
    html = respuesta.content.decode()
    assert 'id="fb-panel"' in html
    assert html.count("data-vence=") == 3 and html.count("data-desde=") == 2


def test_panel_sin_reservas_muestra_ceros(crear, ingresar):
    ctx = ingresar(crear.comercio().propietario).get("/panel/").context
    assert ctx["cifras"]["comprometido"] == 0 and ctx["cifras"]["retirado_hoy"] == 0
    assert ctx["semana"] == {"retiradas": 0, "retirado": 0, "perdidas": 0, "perdido": 0, "sin_atender": 0}


def test_cerradas_de_la_semana_con_montos_y_vencidas_sin_atender(crear, ingresar):
    comercio = crear.comercio()
    producto = crear.producto(comercio, stock=20, precio_referencial=1000)
    ahora = timezone.now()
    servicios.confirmar_retiro(_reserva(crear, producto, 2).pk, comercio.propietario)
    servicios.anular_reserva(_reserva(crear, producto, 3).pk, comercio.propietario, por_cliente=False)
    minuto = timedelta(minutes=1)
    _reserva(crear, producto, 4, estado="expirada", cerrada_en=ahora + minuto)  # nunca la atendieron
    _reserva(crear, producto, 5, estado="expirada", cerrada_en=ahora + 2 * minuto, atendida_en=ahora)
    _reserva(
        crear, producto, 6, estado="retirada", cerrada_en=ahora - timedelta(days=8)
    )  # fuera de la semana

    ctx = ingresar(comercio.propietario).get("/panel/").context
    assert ctx["semana"] == {
        "retiradas": 1,
        "retirado": 2000,
        "perdidas": 3,
        "perdido": 12000,
        "sin_atender": 1,
    }
    assert [r.resultado[1] for r in ctx["cerradas"]] == [
        "Venció sin retirar",
        "Venció sin atender",
        "Anulada por ti",
        "Retirada",
    ]


def test_cerradas_distingue_la_anulacion_del_cliente(crear, ingresar):
    comercio = crear.comercio()
    reserva = servicios.crear_reserva(crear.usuario(), crear.producto(comercio).pk, 1)
    servicios.anular_reserva(reserva.pk, reserva.cliente)
    ctx = ingresar(comercio.propietario).get("/panel/").context
    assert [r.resultado for r in ctx["cerradas"]] == [("neutra", "Anulada por el cliente")]


def test_panel_lista_los_cinco_productos_mas_atrasados_del_comercio(crear, ingresar):
    comercio = crear.comercio()
    viejo = timezone.now() - timedelta(days=10)
    for i in range(6):
        p = crear.producto(comercio, f"Producto {i}")
        Producto.objects.filter(pk=p.pk).update(actualizado_en=viejo + timedelta(hours=i))
    crear.producto(comercio, "Al día")
    ajeno = crear.producto(crear.comercio(), "Ajeno")
    Producto.objects.filter(pk=ajeno.pk).update(actualizado_en=viejo - timedelta(days=1))

    ctx = ingresar(comercio.propietario).get("/panel/").context
    assert ctx["desactualizados"] == 6
    assert [p.nombre for p in ctx["mas_atrasados"]] == [f"Producto {i}" for i in range(5)]
