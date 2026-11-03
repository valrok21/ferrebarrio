import pytest
from django.core.management import call_command

from conftest import CLAVE
from cuentas.models import RegistroAuditoria, Usuario
from reservas import servicios


def _registro(**extra):
    return {
        "nombre": "Ana Pérez",
        "email": "Ana@Prueba.cl",
        "telefono": "+56 9 8765 4321",
        "rol": "cliente",
        "password1": CLAVE,
        "password2": CLAVE,
        "acepto_privacidad": "on",
        **extra,
    }


def test_registro_de_cliente_inicia_sesion(db, client):
    r = client.post("/cuentas/registro/", _registro())
    assert r.status_code == 302 and r.url == "/"
    usuario = Usuario.objects.get()
    assert (usuario.email, usuario.rol) == ("ana@prueba.cl", "cliente") and usuario.acepto_privacidad_en


@pytest.mark.parametrize(
    "extra, campo",
    [
        ({"rol": "admin"}, "rol"),
        ({"acepto_privacidad": ""}, "acepto_privacidad"),
        ({"password2": "otra-cosa-123"}, "password2"),
        ({"password1": "123", "password2": "123"}, "password1"),
    ],
)
def test_registro_rechaza(db, client, extra, campo):
    r = client.post("/cuentas/registro/", _registro(**extra))
    assert campo in r.context["form"].errors and not Usuario.objects.exists()


def test_registro_correo_repetido(crear, client):
    existente = crear.usuario()
    r = client.post("/cuentas/registro/", _registro(email=existente.email.upper()))
    assert "email" in r.context["form"].errors


def test_ingreso_redirige_por_rol(crear, client):
    comerciante = crear.usuario("comerciante")
    r = client.post("/cuentas/ingresar/", {"username": comerciante.email, "password": CLAVE})
    assert r.status_code == 302 and r.url == "/panel/"


def test_bloqueo_tras_5_fallos(crear, client):
    usuario = crear.usuario()
    for _ in range(5):
        client.post("/cuentas/ingresar/", {"username": usuario.email, "password": "mala"})
    r = client.post("/cuentas/ingresar/", {"username": f" {usuario.email.upper()} ", "password": CLAVE})
    assert r.status_code == 200 and "Demasiados intentos" in r.content.decode()
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize(
    "rol, url, esperado",
    [
        ("cliente", "/panel/", 403),
        ("cliente", "/panel/catalogo/", 403),
        ("cliente", "/administracion/", 403),
        ("comerciante", "/mis-reservas/", 403),
        ("comerciante", "/administracion/valoraciones/", 403),
        ("comerciante", "/cuentas/eliminar/", 403),
        ("admin", "/panel/reportes/", 403),
        ("admin", "/reservar/1/", 403),
        ("cliente", "/administracion/comercios/", 403),
    ],
)
def test_cada_rol_bloqueado_fuera_de_lo_suyo(crear, ingresar, rol, url, esperado):
    assert ingresar(crear.usuario(rol)).get(url).status_code == esperado


@pytest.mark.parametrize("url", ["/panel/", "/mis-reservas/", "/administracion/", "/cuentas/mi-cuenta/"])
def test_anonimo_va_al_login(db, client, url):
    r = client.get(url)
    assert r.status_code == 302 and r.url.startswith("/cuentas/ingresar/")


def test_mi_cuenta_actualiza_telefono(crear, ingresar):
    usuario = crear.usuario()
    ingresar(usuario).post("/cuentas/mi-cuenta/", {"nombre": "Nuevo", "telefono": "+56 9 1111 2222"})
    usuario.refresh_from_db()
    assert (usuario.nombre, usuario.telefono) == ("Nuevo", "+56 9 1111 2222")


def test_eliminar_cuenta_anonimiza_y_libera_stock(crear, ingresar):
    producto = crear.producto(crear.comercio(), stock=3)
    cliente = crear.usuario()
    servicios.crear_reserva(cliente, producto.pk, 2)
    navegador = ingresar(cliente)
    assert navegador.post("/cuentas/eliminar/", {"password": "mala"}).status_code == 200
    navegador.post("/cuentas/eliminar/", {"password": CLAVE})
    cliente.refresh_from_db()
    producto.refresh_from_db()
    assert (cliente.nombre, cliente.telefono, cliente.is_active) == ("Usuario eliminado", "", False)
    assert cliente.email.endswith(".invalid") and not cliente.has_usable_password()
    assert (producto.stock_disponible, producto.stock_reservado) == (3, 0)
    assert RegistroAuditoria.objects.filter(accion="eliminar_cuenta").exists()


def test_salud(db, client):
    assert client.get("/salud/").content == b"ok"


def test_poblar_demo_es_idempotente(db, settings):
    settings.DEBUG = True
    call_command("poblar_demo")
    conteo = Usuario.objects.count()
    call_command("poblar_demo")
    assert conteo == Usuario.objects.count() >= 6
    assert Usuario.objects.filter(rol="admin").exists()
