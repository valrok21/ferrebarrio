import pytest

from reservas import servicios
from valoraciones.models import Valoracion


@pytest.fixture
def retirada(crear):
    comercio = crear.comercio()
    cliente = crear.usuario()
    reserva = servicios.crear_reserva(cliente, crear.producto(comercio).pk, 1)
    return servicios.confirmar_retiro(reserva.pk, comercio.propietario)


def test_valorar_retirada_propia_una_sola_vez(retirada, ingresar):
    navegador = ingresar(retirada.cliente)
    url = f"/mis-reservas/{retirada.pk}/valorar/"
    assert navegador.post(url, {"puntaje": 5, "comentario": "  "}).status_code == 302
    v = Valoracion.objects.get()
    assert (v.estado, v.puntaje, v.comercio_id) == ("aprobada", 5, retirada.comercio_id)
    navegador.post(url, {"puntaje": 1, "comentario": "otra"})
    assert Valoracion.objects.count() == 1


def test_comentario_queda_pendiente_y_admin_lo_aprueba(retirada, ingresar, crear, client):
    ingresar(retirada.cliente).post(
        f"/mis-reservas/{retirada.pk}/valorar/", {"puntaje": 4, "comentario": "Buena"}
    )
    v = Valoracion.objects.get()
    assert v.estado == "pendiente"
    assert "Buena" not in client.get(f"/comercios/{retirada.comercio_id}/").content.decode()
    assert (
        ingresar(retirada.cliente)
        .post(f"/administracion/valoraciones/{v.pk}/", {"accion": "aprobar"})
        .status_code
        == 403
    )
    ingresar(crear.usuario("admin")).post(f"/administracion/valoraciones/{v.pk}/", {"accion": "aprobar"})
    v.refresh_from_db()
    assert v.estado == "aprobada" and v.moderada_por.rol == "admin"


def test_no_se_valora_reserva_ajena_ni_no_retirada(retirada, crear, ingresar):
    assert (
        ingresar(crear.usuario()).post(f"/mis-reservas/{retirada.pk}/valorar/", {"puntaje": 1}).status_code
        == 404
    )
    pendiente = servicios.crear_reserva(retirada.cliente, retirada.producto_id, 1)
    assert (
        ingresar(retirada.cliente).post(f"/mis-reservas/{pendiente.pk}/valorar/", {"puntaje": 1}).status_code
        == 404
    )
    assert not Valoracion.objects.exists()


def test_puntaje_fuera_de_rango(retirada, ingresar):
    r = ingresar(retirada.cliente).post(f"/mis-reservas/{retirada.pk}/valorar/", {"puntaje": 6})
    assert "puntaje" in r.context["form"].errors and not Valoracion.objects.exists()
