import pytest
from django.core.exceptions import ValidationError

from comercios.models import Comercio
from comercios.rut import digito_verificador, normalizar_rut
from reservas.models import Aviso


def test_modulo_11_valido_normaliza_formato():
    assert normalizar_rut("12.345.678-5") == "12345678-5"
    assert normalizar_rut("123456785") == "12345678-5"


@pytest.mark.parametrize("rut", ["12345678-4", "12345678", "abc", "", "999999-9"])
def test_modulo_11_invalido(rut):
    with pytest.raises(ValidationError):
        normalizar_rut(rut)


def test_modulo_11_digito_k_y_cero():
    cuerpo_k = next(c for c in range(10_000_000, 10_001_000) if digito_verificador(c) == "K")
    assert normalizar_rut(f"{cuerpo_k}-k") == f"{cuerpo_k}-K"
    cuerpo_0 = next(c for c in range(10_000_000, 10_001_000) if digito_verificador(c) == "0")
    assert normalizar_rut(f"{cuerpo_0}0") == f"{cuerpo_0}-0"


def _ficha(**extra):
    return {
        "nombre": "Ferretería Prueba",
        "rut": "12.345.678-5",
        "direccion": "Av. Siempre Viva 742",
        "comuna": "Providencia",
        "telefono": "+56 2 2345 6789",
        "horario": "9 a 18",
        "acepto_terminos": "on",
        **extra,
    }


def test_registro_comercio_con_marcador_queda_pendiente(crear, ingresar):
    usuario = crear.usuario("comerciante")
    r = ingresar(usuario).post("/panel/ficha/", _ficha(lat="-33.43", lon="-70.61", marcador_movido="True"))
    assert r.status_code == 302
    comercio = Comercio.objects.get(propietario=usuario)
    assert (comercio.estado, comercio.origen_ubicacion, comercio.rut) == ("pendiente", "manual", "12345678-5")


def test_registro_sin_geocodificar_pide_marcar_en_mapa(crear, ingresar):
    r = ingresar(crear.usuario("comerciante")).post("/panel/ficha/", _ficha())
    assert r.status_code == 200 and r.context["sin_ubicacion"]
    assert not Comercio.objects.exists()


def test_registro_rechaza_marcador_fuera_de_chile_y_rut_repetido(crear, ingresar):
    Comercio.objects.filter(pk=crear.comercio().pk).update(rut="12345678-5")
    r = ingresar(crear.usuario("comerciante")).post(
        "/panel/ficha/", _ficha(lat="40", lon="-3", marcador_movido="True")
    )
    assert "rut" in r.context["form"].errors and r.context["form"].non_field_errors()


def test_verificar_aprobar_avisa_y_observar_exige_motivo(crear, ingresar):
    comercio = crear.comercio(estado="pendiente")
    admin = ingresar(crear.usuario("admin"))
    r = admin.post(f"/administracion/comercios/{comercio.pk}/", {"accion": "observar", "motivo": " "})
    assert r.status_code == 200 and "motivo" in r.context["form"].errors
    admin.post(f"/administracion/comercios/{comercio.pk}/", {"accion": "aprobar"})
    comercio.refresh_from_db()
    assert comercio.estado == "aprobada" and comercio.verificado_por.rol == "admin"
    assert Aviso.objects.filter(destinatario=comercio.propietario.email, tipo="verificacion").exists()


def test_ficha_publica_solo_aprobados(crear, client):
    assert client.get(f"/comercios/{crear.comercio().pk}/").status_code == 200
    assert client.get(f"/comercios/{crear.comercio(estado='pendiente').pk}/").status_code == 404


def test_bandeja_de_solicitudes_solo_admin(crear, ingresar):
    crear.comercio(estado="pendiente")
    assert ingresar(crear.usuario("comerciante")).get("/administracion/comercios/").status_code == 403
    r = ingresar(crear.usuario("admin")).get("/administracion/comercios/")
    assert r.status_code == 200 and len(r.context["pendientes"]) == 1
