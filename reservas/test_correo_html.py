"""Correos de aviso en HTML con detalle de la reserva y botón de acción (FERREBARRIO-20261116, punto 5)."""

import pytest
from django.core import mail
from django.test import override_settings
from django.utils.html import escape

from reservas import avisos, servicios
from reservas.models import Aviso

pytestmark = pytest.mark.django_db


@override_settings(SITIO_URL="http://sitio.test")
def test_reserva_nueva_manda_html_con_detalle_y_boton_por_destinatario(
    crear, django_capture_on_commit_callbacks
):
    comercio = crear.comercio()
    producto = crear.producto(comercio, stock=5)
    cliente = crear.usuario()
    with django_capture_on_commit_callbacks(execute=True):
        reserva = servicios.crear_reserva(cliente, producto.pk, 2)
    correos = {m.to[0]: m for m in mail.outbox}
    al_cliente, al_comercio = correos[cliente.email], correos[comercio.propietario.email]
    for correo in (al_cliente, al_comercio):
        html, tipo = correo.alternatives[0]
        assert tipo == "text/html" and reserva.codigo in html and escape(producto.nombre) in html
        assert correo.body and "<" not in correo.body  # el texto plano se mantiene
    assert f'href="http://sitio.test/mis-reservas/{reserva.pk}/"' in al_cliente.alternatives[0][0]
    assert 'href="http://sitio.test/panel/"' in al_comercio.alternatives[0][0]


def test_html_escapa_contenido_y_sin_reserva_usa_ruta_del_tipo():
    aviso = Aviso.objects.create(
        destinatario="x@prueba.cl",
        tipo="catalogo_desactualizado",
        asunto="Hola",
        cuerpo="<script>x</script>\nfin",
    )
    avisos.enviar_aviso(aviso.pk)
    html = mail.outbox[0].alternatives[0][0]
    assert "<script>" not in html and "&lt;script&gt;" in html and "<br>" in html
    assert "/panel/catalogo/" in html


def test_tipo_sin_ruta_no_muestra_boton():
    aviso = Aviso.objects.create(destinatario="x@prueba.cl", tipo="conciliacion", asunto="A", cuerpo="b")
    avisos.enviar_aviso(aviso.pk)
    assert "Abrir FerreBarrio" not in mail.outbox[0].alternatives[0][0]
