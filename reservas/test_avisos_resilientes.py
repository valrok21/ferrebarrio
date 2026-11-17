"""Reserva visible y avisos que sobreviven a la caída del broker (FERREBARRIO-20261116, punto 1)."""

from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError

from reservas import avisos, servicios
from reservas.models import Aviso, Reserva


@pytest.fixture
def escena(crear):
    comercio = crear.comercio()
    return comercio, crear.producto(comercio, stock=5), crear.usuario()


def _broker_caido():
    return mock.patch("reservas.tasks.enviar_aviso_tarea.delay", side_effect=OperationalError("redis caído"))


def test_reserva_se_crea_aunque_el_broker_este_caido(escena, ingresar, django_capture_on_commit_callbacks):
    _, producto, cliente = escena
    with _broker_caido(), django_capture_on_commit_callbacks(execute=True):
        respuesta = ingresar(cliente).post(f"/reservar/{producto.pk}/", {"cantidad": 1})
    reserva = Reserva.objects.get()
    assert respuesta.status_code == 302 and respuesta.url == f"/mis-reservas/{reserva.pk}/"
    assert set(Aviso.objects.values_list("estado", "intentos")) == {("pendiente", 0)}
    assert mail.outbox == []


def test_redespacho_envia_los_pendientes_perdidos(escena, django_capture_on_commit_callbacks):
    _, producto, cliente = escena
    with _broker_caido(), django_capture_on_commit_callbacks(execute=True):
        servicios.crear_reserva(cliente, producto.pk, 1)
    assert avisos.redespachar_pendientes() == 0  # recién creados: todavía en ventana de despacho normal
    Aviso.objects.update(creado_en=timezone.now() - timedelta(minutes=3))
    assert avisos.redespachar_pendientes() == 2
    assert set(Aviso.objects.values_list("estado", flat=True)) == {"enviado"} and len(mail.outbox) == 2
    assert avisos.redespachar_pendientes() == 0


def _aviso(creado_hace, despachado_hace=None, **campos):
    ahora = timezone.now()
    aviso = Aviso.objects.create(destinatario="a@prueba.cl", tipo="x", asunto="a", cuerpo=".", **campos)
    Aviso.objects.filter(pk=aviso.pk).update(
        creado_en=ahora - creado_hace, despachado_en=despachado_hace and ahora - despachado_hace
    )
    return aviso


def test_redespacho_no_toca_encolados_recientes_ni_viejos(crear):
    _aviso(timedelta(minutes=30), timedelta(minutes=9))  # en cola con el worker caído: no se acumulan copias
    _aviso(timedelta(minutes=3), timedelta(minutes=1), intentos=1)  # reintento de Celery en curso
    _aviso(timedelta(days=2))  # fuera de la ventana de un día
    _aviso(timedelta(minutes=30), timedelta(minutes=20), intentos=3)  # agotado
    assert avisos.redespachar_pendientes() == 0 and mail.outbox == []


@pytest.mark.parametrize("intentos", [0, 2])
def test_redespacho_retoma_encolado_que_no_termino(crear, intentos):
    """Worker caído o reintento que no se publicó: tras 10 min el aviso vuelve a la cola y se envía."""
    aviso = _aviso(timedelta(minutes=30), timedelta(minutes=11), intentos=intentos)
    assert avisos.redespachar_pendientes() == 1
    aviso.refresh_from_db()
    assert aviso.estado == "enviado" and len(mail.outbox) == 1


def test_despachar_marca_el_encolado_solo_si_el_broker_lo_acepta(crear):
    aviso = Aviso.objects.create(destinatario="a@prueba.cl", tipo="x", asunto="a", cuerpo=".")
    with _broker_caido():
        avisos.despachar(aviso.pk)
    aviso.refresh_from_db()
    assert aviso.despachado_en is None
    with mock.patch("reservas.tasks.enviar_aviso_tarea.delay"):
        avisos.despachar(aviso.pk)
    aviso.refresh_from_db()
    assert aviso.despachado_en is not None


def test_redespacho_con_broker_aun_caido_no_lanza(crear):
    aviso = Aviso.objects.create(destinatario="a@prueba.cl", tipo="x", asunto="a", cuerpo=".")
    Aviso.objects.filter(pk=aviso.pk).update(creado_en=timezone.now() - timedelta(minutes=3))
    with _broker_caido():
        assert avisos.redespachar_pendientes() == 1
    aviso.refresh_from_db()
    assert (aviso.estado, aviso.intentos) == ("pendiente", 0)


def test_despacho_duplicado_envia_una_sola_vez(crear):
    aviso = Aviso.objects.create(destinatario="a@prueba.cl", tipo="x", asunto="a", cuerpo=".")
    avisos.enviar_aviso(aviso.pk)
    avisos.enviar_aviso(aviso.pk)
    aviso.refresh_from_db()
    assert len(mail.outbox) == 1 and aviso.intentos == 1


def test_fallo_de_envio_guarda_el_intento_antes_de_reintentar(crear):
    aviso = Aviso.objects.create(destinatario="a@prueba.cl", tipo="x", asunto="a", cuerpo=".")
    with mock.patch("reservas.avisos.send_mail", side_effect=ConnectionError("SMTP caído")):
        with pytest.raises(ConnectionError):
            avisos.enviar_aviso(aviso.pk)
    aviso.refresh_from_db()
    assert (aviso.estado, aviso.intentos) == ("pendiente", 1) and "SMTP caído" in aviso.error


def test_sin_atencion_avisa_tambien_al_comercio(escena):
    comercio, producto, cliente = escena
    reserva = servicios.crear_reserva(cliente, producto.pk, 1)
    Reserva.objects.filter(pk=reserva.pk).update(creada_en=timezone.now() - timedelta(minutes=31))
    assert servicios.avisar_sin_atencion() == 1
    aviso = Aviso.objects.get(tipo="reserva_sin_atencion_comercio")
    assert aviso.destinatario == comercio.propietario.email and reserva.codigo in aviso.asunto
    assert servicios.avisar_sin_atencion() == 0
    assert Aviso.objects.filter(tipo="reserva_sin_atencion_comercio").count() == 1


def test_contador_de_pendientes_en_navbar_y_json(escena, crear, ingresar):
    comercio, producto, cliente = escena
    panel = ingresar(comercio.propietario)
    assert panel.get("/panel/pendientes.json").json() == {"pendientes": 0, "ultima": None}
    reserva = servicios.crear_reserva(cliente, producto.pk, 1)
    assert panel.get("/panel/pendientes.json").json() == {"pendientes": 1, "ultima": reserva.pk}
    assert panel.get(reverse("catalogo:lista")).context["reservas_pendientes"] == 1
    servicios.atender_reserva(reserva.pk, comercio.propietario)
    assert panel.get("/panel/pendientes.json").json()["pendientes"] == 0


def test_panel_sondea_cada_10_s_y_al_volver_a_la_pestana(escena, ingresar):
    comercio, _, _ = escena
    html = ingresar(comercio.propietario).get("/panel/").content.decode()
    assert "setInterval(revisar, 10000)" in html and "'visibilitychange'" in html


def test_json_de_pendientes_aislado_por_comercio(escena, crear, ingresar):
    _, producto, cliente = escena
    servicios.crear_reserva(cliente, producto.pk, 1)
    otro = crear.comercio()
    assert ingresar(otro.propietario).get("/panel/pendientes.json").json()["pendientes"] == 0


@pytest.mark.parametrize("rol", ["cliente", "admin"])
def test_json_de_pendientes_solo_comerciante(crear, ingresar, rol):
    respuesta = ingresar(crear.usuario(rol)).get("/panel/pendientes.json")
    assert respuesta.status_code == 403
    assert "reservas_pendientes" not in ingresar(crear.usuario(rol)).get("/").context


def test_reservar_muestra_el_local_destacado(escena, ingresar):
    comercio, producto, cliente = escena
    html = ingresar(cliente).get(f"/reservar/{producto.pk}/").content.decode()
    assert "Reservas en" in html and f"Confirmar reserva en {comercio.nombre}" in html


def test_panel_cuenta_desactualizados_en_bd(escena, ingresar):
    comercio, producto, _ = escena
    type(producto).objects.filter(pk=producto.pk).update(actualizado_en=timezone.now() - timedelta(hours=73))
    assert ingresar(comercio.propietario).get("/panel/").context["desactualizados"] == 1
