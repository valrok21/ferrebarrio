"""Revisión de seguridad (2026-11-03): un test por hallazgo, con el camino que sigue igual."""

import zipfile
from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.utils import timezone
from openpyxl import Workbook

from catalogo.models import Categoria, Producto
from catalogo.planilla import COLUMNAS, MAX_ENTERO, PlanillaInvalida, cargar, entero
from conftest import CLAVE
from cuentas.models import Usuario
from cuentas.servicios import eliminar_cuenta
from reservas import servicios
from reservas.models import Aviso, Reserva


def _registro(email):
    return {
        "nombre": "Ana", "email": email, "telefono": "+56 9 8765 4321", "rol": "cliente",
        "password1": CLAVE, "password2": CLAVE, "acepto_privacidad": "on",
    }  # fmt: skip


def test_registro_rechaza_el_dominio_de_cuentas_eliminadas(db, client):
    r = client.post("/cuentas/registro/", _registro("eliminado-7@ferrebarrio.invalid"))
    assert "email" in r.context["form"].errors and not Usuario.objects.exists()
    assert client.post("/cuentas/registro/", _registro("ana@prueba.cl")).status_code == 302


def test_eliminar_cuenta_borra_sus_datos_de_los_avisos(crear):
    producto = crear.producto(crear.comercio(), stock=3)
    cliente, otro = crear.usuario(), crear.usuario()
    Usuario.objects.filter(pk=cliente.pk).update(nombre="Ana")
    Usuario.objects.filter(pk=otro.pk).update(nombre="Anabel Soto")
    cliente.refresh_from_db()
    otro.refresh_from_db()
    servicios.crear_reserva(cliente, producto.pk, 1)
    servicios.crear_reserva(otro, producto.pk, 1)
    email = cliente.email
    eliminar_cuenta(cliente)
    assert not Aviso.objects.filter(destinatario=email).exists()
    for aviso in Aviso.objects.filter(reserva__cliente=cliente):
        assert email not in aviso.cuerpo and "Ana " not in aviso.cuerpo
    assert any("Usuario eliminado anuló" in a.cuerpo for a in Aviso.objects.filter(reserva__cliente=cliente))
    # El aviso de otra persona cuyo nombre contiene «Ana» queda intacto.
    assert Aviso.objects.filter(reserva__cliente=otro, cuerpo__contains="Anabel Soto").exists()


def test_admin_tecnico_bloquea_tras_5_fallos(crear, client):
    staff = crear.usuario("admin", is_staff=True, is_superuser=True)
    for _ in range(5):
        client.post("/django-admin/login/", {"username": staff.email, "password": "mala"})
    r = client.post("/django-admin/login/", {"username": staff.email, "password": CLAVE})
    assert r.status_code == 200 and "Demasiados intentos" in r.content.decode()


def test_admin_tecnico_deja_entrar_al_staff_y_no_a_un_cliente(crear, client):
    staff = crear.usuario("admin", is_staff=True, is_superuser=True)
    r = client.post(
        "/django-admin/login/?next=/django-admin/", {"username": crear.usuario().email, "password": CLAVE}
    )
    assert r.status_code == 200 and "_auth_user_id" not in client.session
    r = client.post("/django-admin/login/?next=/django-admin/", {"username": staff.email, "password": CLAVE})
    assert r.status_code == 302 and client.session["_auth_user_id"] == str(staff.pk)


def test_poblar_demo_no_corre_sin_debug(db, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("poblar_demo")
    assert not Usuario.objects.exists()


def _xlsx(filas, extra=None):
    libro = Workbook()
    libro.active.append(COLUMNAS)
    for fila in filas:
        libro.active.append(fila)
    salida = BytesIO()
    libro.save(salida)
    if extra:
        with zipfile.ZipFile(salida, "a", zipfile.ZIP_DEFLATED) as z:
            z.writestr("xl/relleno.bin", extra)
    return SimpleUploadedFile("catalogo.xlsx", salida.getvalue())


def test_planilla_rechaza_bomba_de_descompresion(crear):
    archivo = _xlsx([], extra=b"\0" * (21 * 1024 * 1024))
    assert archivo.size < 2 * 1024 * 1024
    with pytest.raises(PlanillaInvalida, match="demasiado grande"):
        cargar(archivo, crear.comercio(), crear.usuario("comerciante"))


@pytest.mark.parametrize(
    "valor, esperado",
    [(MAX_ENTERO, MAX_ENTERO), (MAX_ENTERO + 1, None), (10**12, None), (1e300, None),
     ("100.000.000", MAX_ENTERO), ("9" * 400, None)],
)  # fmt: skip
def test_entero_con_tope(valor, esperado):
    assert entero(valor) == esperado


def test_planilla_con_valores_extremos_informa_por_fila_sin_caer(crear):
    comercio = crear.comercio()
    nombre_largo = "㎏" * 120  # NFKD: 240 caracteres normalizados
    archivo = _xlsx(
        [
            ["Precio enorme", "Fijaciones", "unidad", 10**12, 1],
            ["Stock enorme", "Fijaciones", "unidad", 1, 1e300],
            [nombre_largo, "Fijaciones", "unidad", 100, 2],
        ]
    )
    Categoria.objects.get_or_create(nombre="Fijaciones")
    carga = cargar(archivo, comercio, comercio.propietario)
    assert carga.ok == 1 and [e["fila"] for e in carga.errores] == [2, 3]
    assert len(Producto.objects.get(comercio=comercio, nombre=nombre_largo).nombre_normalizado) == 120


def test_limite_de_reservas_por_dia(crear, settings):
    settings.RESERVA_MAX_POR_DIA = 3
    producto = crear.producto(crear.comercio(), stock=20)
    cliente = crear.usuario()
    for _ in range(3):
        reserva = servicios.crear_reserva(cliente, producto.pk, 1)
        servicios.anular_reserva(reserva.pk, cliente)
    with pytest.raises(servicios.ReservaError, match="24 horas"):
        servicios.crear_reserva(cliente, producto.pk, 1)
    Reserva.objects.filter(cliente=cliente).update(creada_en=timezone.now() - timedelta(days=1, minutes=1))
    assert servicios.crear_reserva(cliente, producto.pk, 1)
