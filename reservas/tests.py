import threading
from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.db import connection
from django.http import Http404
from django.utils import timezone

from reservas import servicios
from reservas.models import Aviso, Reserva
from reservas.servicios import ReservaError
from reservas.tasks import conciliar_stock, enviar_aviso_tarea


def _stock(producto):
    producto.refresh_from_db()
    return producto.stock_disponible, producto.stock_reservado


@pytest.fixture
def escena(crear):
    comercio = crear.comercio()
    return comercio, crear.producto(comercio, stock=5), crear.usuario()


def test_reservar_aparta_stock_y_programa_avisos(escena):
    comercio, producto, cliente = escena
    reserva = servicios.crear_reserva(cliente, producto.pk, 2)
    assert _stock(producto) == (3, 2)
    assert reserva.estado == "pendiente" and reserva.total == 2000 and reserva.codigo.startswith("FB-")
    assert reserva.vence_en - reserva.creada_en == timedelta(hours=4)
    assert set(Aviso.objects.values_list("destinatario", flat=True)) == {
        cliente.email,
        comercio.propietario.email,
    }


@pytest.mark.parametrize("cantidad", [0, 21])
def test_reservar_cantidad_fuera_de_rango(escena, cantidad):
    with pytest.raises(ReservaError, match="cantidad"):
        servicios.crear_reserva(escena[2], escena[1].pk, cantidad)


def test_reservar_requiere_cliente_con_telefono_y_stock(escena, crear):
    _, producto, _ = escena
    with pytest.raises(ReservaError, match="clientes"):
        servicios.crear_reserva(crear.usuario("comerciante"), producto.pk, 1)
    with pytest.raises(ReservaError, match="teléfono"):
        servicios.crear_reserva(crear.usuario(telefono=""), producto.pk, 1)
    with pytest.raises(ReservaError, match="unidades"):
        servicios.crear_reserva(crear.usuario(), producto.pk, 6)
    assert _stock(producto) == (5, 0)


def test_no_se_reserva_en_comercio_no_aprobado(crear):
    producto = crear.producto(crear.comercio(estado="pendiente"))
    with pytest.raises(Http404):
        servicios.crear_reserva(crear.usuario(), producto.pk, 1)


def test_limite_de_3_reservas_activas(escena):
    _, producto, cliente = escena
    primeras = [servicios.crear_reserva(cliente, producto.pk, 1) for _ in range(3)]
    with pytest.raises(ReservaError, match="3 reservas activas"):
        servicios.crear_reserva(cliente, producto.pk, 1)
    servicios.anular_reserva(primeras[0].pk, cliente)
    servicios.crear_reserva(cliente, producto.pk, 1)  # al liberar una, vuelve a poder


@pytest.mark.django_db(transaction=True)
def test_concurrencia_dos_clientes_por_la_ultima_unidad(crear):
    producto = crear.producto(crear.comercio(), stock=1)
    clientes = [crear.usuario(), crear.usuario()]
    barrera, resultados = threading.Barrier(2), []

    def reservar(cliente):
        try:
            barrera.wait()
            resultados.append(servicios.crear_reserva(cliente, producto.pk, 1))
        except ReservaError as e:
            resultados.append(e)
        finally:
            connection.close()

    hilos = [threading.Thread(target=reservar, args=(c,)) for c in clientes]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(type(r).__name__ for r in resultados) == ["Reserva", "ReservaError"]
    assert _stock(producto) == (0, 1)


def test_flujo_atender_y_retirar_descuenta_reservado(escena, ingresar):
    comercio, producto, cliente = escena
    reserva = servicios.crear_reserva(cliente, producto.pk, 2)
    panel = ingresar(comercio.propietario)
    panel.post(f"/panel/reservas/{reserva.pk}/atender/")
    reserva.refresh_from_db()
    assert reserva.estado == "atendida" and reserva.atendida_en
    panel.post(f"/panel/reservas/{reserva.pk}/entregar/")
    reserva.refresh_from_db()
    assert reserva.estado == "retirada" and _stock(producto) == (3, 0)
    with pytest.raises(ReservaError):
        servicios.confirmar_retiro(reserva.pk, comercio.propietario)
    assert panel.post(f"/panel/reservas/{reserva.pk}/inventada/").status_code == 302


def test_anular_devuelve_stock_por_cliente_y_por_comercio(escena, ingresar):
    comercio, producto, cliente = escena
    a, b = (servicios.crear_reserva(cliente, producto.pk, 1) for _ in range(2))
    ingresar(cliente).post(f"/mis-reservas/{a.pk}/anular/")
    servicios.anular_reserva(b.pk, comercio.propietario, por_cliente=False)
    assert set(Reserva.objects.values_list("estado", flat=True)) == {"anulada"}
    assert _stock(producto) == (5, 0)


def test_aislamiento_reservas_ajenas_dan_404(escena, crear, ingresar):
    comercio, producto, cliente = escena
    reserva = servicios.crear_reserva(cliente, producto.pk, 1)
    otro_comercio = crear.comercio().propietario
    for accion in ("atender", "entregar", "anular"):
        assert ingresar(otro_comercio).post(f"/panel/reservas/{reserva.pk}/{accion}/").status_code == 404
    otro_cliente = ingresar(crear.usuario())
    assert otro_cliente.get(f"/mis-reservas/{reserva.pk}/").status_code == 404
    assert otro_cliente.post(f"/mis-reservas/{reserva.pk}/anular/").status_code == 404
    with pytest.raises(Http404):
        servicios.anular_reserva(reserva.pk, comercio.propietario, por_cliente=True)
    reserva.refresh_from_db()
    assert reserva.estado == "pendiente"
    assert reserva.codigo not in ingresar(otro_comercio).get("/panel/").content.decode()


def test_vista_reservar_y_ver_detalle(escena, ingresar):
    _, producto, cliente = escena
    navegador = ingresar(cliente)
    r = navegador.post(f"/reservar/{producto.pk}/", {"cantidad": 2})
    reserva = Reserva.objects.get()
    assert r.url == f"/mis-reservas/{reserva.pk}/"
    assert reserva.codigo in navegador.get("/mis-reservas/").content.decode()
    r = navegador.post(f"/reservar/{producto.pk}/", {"cantidad": 4})
    assert "unidades" in str(r.context["form"].non_field_errors())


def test_expiracion_libera_stock_de_pendientes_y_atendidas(escena):
    comercio, producto, cliente = escena
    pendiente = servicios.crear_reserva(cliente, producto.pk, 1)
    atendida = servicios.atender_reserva(
        servicios.crear_reserva(cliente, producto.pk, 2).pk, comercio.propietario
    )
    vigente = servicios.crear_reserva(cliente, producto.pk, 1)
    Reserva.objects.filter(pk__in=[pendiente.pk, atendida.pk]).update(
        vence_en=timezone.now() - timedelta(minutes=1)
    )
    assert servicios.expirar_vencidas() == 2
    assert dict(Reserva.objects.values_list("pk", "estado")) == {
        pendiente.pk: "expirada",
        atendida.pk: "expirada",
        vigente.pk: "pendiente",
    }
    assert _stock(producto) == (4, 1)
    assert servicios.expirar_vencidas() == 0


def test_aviso_sin_atencion_una_sola_vez(escena):
    _, producto, cliente = escena
    reserva = servicios.crear_reserva(cliente, producto.pk, 1)
    assert servicios.avisar_sin_atencion() == 0
    Reserva.objects.filter(pk=reserva.pk).update(creada_en=timezone.now() - timedelta(minutes=31))
    assert servicios.avisar_sin_atencion() == 1
    assert servicios.avisar_sin_atencion() == 0
    assert Aviso.objects.filter(tipo="reserva_sin_atencion", destinatario=cliente.email).count() == 1


def test_conciliacion_detecta_diferencia_y_avisa_a_admins(escena, crear):
    _, producto, cliente = escena
    admin = crear.usuario("admin")
    servicios.crear_reserva(cliente, producto.pk, 2)
    assert servicios.diferencias_stock() == [] and conciliar_stock() == 0
    producto.__class__.objects.filter(pk=producto.pk).update(stock_reservado=5)
    assert [p.pk for p in servicios.diferencias_stock()] == [producto.pk]
    assert conciliar_stock() == 1
    assert Aviso.objects.filter(tipo="conciliacion", destinatario=admin.email).exists()


def _send_mail_caido(*args, fail_silently=False, **kwargs):
    if not fail_silently:
        raise ConnectionError("SMTP caído")
    return 1


def test_aviso_fallido_tras_3_intentos_escala_a_admins(crear):
    admin = crear.usuario("admin")
    aviso = Aviso.objects.create(destinatario="c@prueba.cl", tipo="x", asunto="Hola", cuerpo="...")
    with mock.patch("reservas.avisos.send_mail", side_effect=_send_mail_caido) as envio:
        enviar_aviso_tarea.apply(args=[aviso.pk])
    aviso.refresh_from_db()
    assert (aviso.estado, aviso.intentos) == ("fallido", 3) and "SMTP caído" in aviso.error
    escalado = envio.call_args_list[-1]
    assert escalado.args[3] == [admin.email] and escalado.kwargs["fail_silently"]


def test_aviso_enviado_y_alerta_de_cuota_al_80(crear, settings):
    settings.AVISOS_CUOTA_DIARIA = 1
    admin = crear.usuario("admin")
    aviso = Aviso.objects.create(destinatario="c@prueba.cl", tipo="x", asunto="Hola", cuerpo="...")
    enviar_aviso_tarea.apply(args=[aviso.pk])
    aviso.refresh_from_db()
    assert aviso.estado == "enviado" and aviso.enviado_en
    assert [m.to for m in mail.outbox] == [["c@prueba.cl"], [admin.email]]
    enviar_aviso_tarea.apply(args=[aviso.pk])  # ya enviado: no se repite
    assert len(mail.outbox) == 2


def test_avisos_se_despachan_solo_al_confirmar(escena, django_capture_on_commit_callbacks):
    _, producto, cliente = escena
    with django_capture_on_commit_callbacks(execute=True):
        servicios.crear_reserva(cliente, producto.pk, 1)
    assert len(mail.outbox) == 2 and set(Aviso.objects.values_list("estado", flat=True)) == {"enviado"}
