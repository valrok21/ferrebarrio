"""Sección «Datos» del panel del administrador: reemplaza al admin de Django (/django-admin/ ya no existe)."""

import pytest

from catalogo.models import CargaCatalogo, Categoria
from comercios.models import Comercio
from cuentas.models import RegistroAuditoria

pytestmark = pytest.mark.django_db

TABLAS = [
    "usuarios",
    "comercios",
    "productos",
    "categorias",
    "reservas",
    "avisos",
    "cargas",
    "auditoria",
    "valoraciones",
]
NAV = 'id="fb-menu-boton"'  # botón del menú de base.html: prueba que la página usa la plantilla del sitio


@pytest.fixture
def admin(crear):
    return crear.usuario("admin")


@pytest.fixture
def como_admin(admin, ingresar):
    return ingresar(admin)


@pytest.mark.parametrize("tabla", TABLAS)
def test_cada_tabla_solo_para_el_admin(crear, client, ingresar, tabla):
    url = f"/administracion/datos/{tabla}/"
    crear.producto(crear.comercio())  # al menos una fila en usuarios, comercios, productos y categorías
    r = client.get(url)
    assert r.status_code == 302 and r.url.startswith("/cuentas/ingresar/")
    for rol in ["cliente", "comerciante"]:
        assert ingresar(crear.usuario(rol)).get(url).status_code == 403
    r = ingresar(crear.usuario("admin")).get(url)
    assert r.status_code == 200 and NAV in r.content.decode()


def test_indice_enlaza_cada_tabla_y_desconocida_da_404(como_admin):
    html = como_admin.get("/administracion/datos/").content.decode()
    assert NAV in html
    for tabla in TABLAS:
        assert f'href="/administracion/datos/{tabla}/"' in html
    assert como_admin.get("/administracion/datos/grupos/").status_code == 404


def test_panel_enlaza_datos_y_menu_sin_admin_tecnico(como_admin):
    html = como_admin.get("/administracion/").content.decode()
    assert html.count('href="/administracion/datos/"') == 2  # menú y panel
    assert "Admin técnico" not in html and "/django-admin/" not in html


def test_admin_de_django_ya_no_existe(como_admin):
    assert como_admin.get("/django-admin/").status_code == 404
    assert como_admin.get("/django-admin/login/").status_code == 404


def test_busqueda_filtra(crear, como_admin):
    comercio = crear.comercio()
    crear.producto(comercio, "Martillo carpintero")
    crear.producto(comercio, "Taladro percutor")
    html = como_admin.get("/administracion/datos/productos/", {"q": "martillo"}).content.decode()
    assert "Martillo carpintero" in html and "Taladro percutor" not in html


def test_busqueda_no_distingue_tildes(crear, como_admin):
    comercio = crear.comercio()  # «Ferretería N»
    CargaCatalogo.objects.create(comercio=comercio, archivo="catálogo.csv")
    for q in ["Ferreteria", "FERRETERÍA", "catalogo"]:
        html = como_admin.get("/administracion/datos/cargas/", {"q": q}).content.decode()
        assert "1 registro" in html and comercio.nombre in html, q
    html = como_admin.get("/administracion/datos/cargas/", {"q": "Ferreterio"}).content.decode()
    assert "0 registros" in html


def test_filtro_por_estado_filtra_y_valor_ajeno_se_ignora(crear, como_admin):
    Comercio.objects.filter(pk=crear.comercio(estado="pendiente").pk).update(nombre="Alfa pendiente")
    Comercio.objects.filter(pk=crear.comercio().pk).update(nombre="Beta aprobada")
    url = "/administracion/datos/comercios/"
    html = como_admin.get(url, {"estado": "pendiente"}).content.decode()
    assert "Alfa pendiente" in html and "Beta aprobada" not in html
    html = como_admin.get(url, {"estado": "inventado"}).content.decode()
    assert "Alfa pendiente" in html and "Beta aprobada" in html


def test_pagina_de_50_filas(como_admin):
    Categoria.objects.bulk_create(Categoria(nombre=f"Zz-cat-{i:02}") for i in range(51))
    url = "/administracion/datos/categorias/"
    assert "Zz-cat-50" not in como_admin.get(url).content.decode()
    r = como_admin.get(url, {"pagina": 2})
    assert r.status_code == 200 and "Zz-cat-50" in r.content.decode()


def test_usuarios_sin_hash_de_contrasena(crear, como_admin):
    usuario = crear.usuario()
    html = como_admin.get("/administracion/datos/usuarios/").content.decode()
    assert usuario.email in html
    assert "pbkdf2" not in html and usuario.password not in html


def test_desactivar_usuario_queda_auditado(crear, admin, como_admin):
    usuario = crear.usuario()
    r = como_admin.post(f"/administracion/datos/usuarios/{usuario.pk}/activo/", {"activo": "0"})
    assert r.status_code == 302
    usuario.refresh_from_db()
    assert not usuario.is_active
    registro = RegistroAuditoria.objects.get(accion="desactivar_usuario")
    assert (registro.usuario, registro.entidad_id) == (admin, str(usuario.pk))
    assert (registro.antes, registro.despues) == ({"is_active": True}, {"is_active": False})
    como_admin.post(f"/administracion/datos/usuarios/{usuario.pk}/activo/", {"activo": "1"})
    usuario.refresh_from_db()
    assert usuario.is_active and RegistroAuditoria.objects.filter(accion="activar_usuario").exists()


def test_admin_no_se_desactiva_a_si_mismo(admin, como_admin):
    r = como_admin.post(f"/administracion/datos/usuarios/{admin.pk}/activo/", {"activo": "0"}, follow=True)
    admin.refresh_from_db()
    assert admin.is_active and not RegistroAuditoria.objects.exists()
    assert "No puedes desactivar tu propia cuenta" in r.content.decode()


def test_activo_solo_admin_y_solo_post(crear, ingresar):
    usuario = crear.usuario()
    url = f"/administracion/datos/usuarios/{usuario.pk}/activo/"
    assert ingresar(crear.usuario()).post(url, {"activo": "0"}).status_code == 403
    assert ingresar(crear.usuario("admin")).get(url).status_code == 405
    usuario.refresh_from_db()
    assert usuario.is_active and not RegistroAuditoria.objects.exists()


def test_crear_y_renombrar_categoria(admin, como_admin):
    r = como_admin.post("/administracion/datos/categorias/nueva/", {"nombre": "Jardinería"})
    assert r.status_code == 302
    categoria = Categoria.objects.get(nombre="Jardinería")
    como_admin.post(f"/administracion/datos/categorias/{categoria.pk}/", {"nombre": "Jardín y riego"})
    categoria.refresh_from_db()
    assert categoria.nombre == "Jardín y riego"
    acciones = set(RegistroAuditoria.objects.filter(usuario=admin).values_list("accion", flat=True))
    assert acciones == {"crear_categoria", "renombrar_categoria"}


@pytest.mark.parametrize("nombre", ["Jardinería", " jardineria "])
def test_categoria_duplicada_no_se_crea(como_admin, nombre):
    Categoria.objects.create(nombre="Jardinería")
    r = como_admin.post("/administracion/datos/categorias/nueva/", {"nombre": nombre})
    assert r.status_code == 200 and "nombre" in r.context["form"].errors
    assert Categoria.objects.filter(nombre__icontains="jardin").count() == 1


def test_renombrar_a_su_mismo_nombre_no_es_duplicado(como_admin):
    categoria = Categoria.objects.create(nombre="Jardinería")
    r = como_admin.post(f"/administracion/datos/categorias/{categoria.pk}/", {"nombre": "Jardinería "})
    assert r.status_code == 302


def test_categorias_solo_admin(crear, ingresar):
    comerciante = ingresar(crear.usuario("comerciante"))
    r = comerciante.post("/administracion/datos/categorias/nueva/", {"nombre": "X"})
    assert r.status_code == 403 and not Categoria.objects.filter(nombre="X").exists()


# Revisión de seguridad: B1 valor de «activo», B2 cambio y auditoría atómicos, B3 nunca sin admins.
def test_activo_ausente_o_invalido_no_cambia_nada(crear, como_admin):
    usuario = crear.usuario()
    url = f"/administracion/datos/usuarios/{usuario.pk}/activo/"
    assert como_admin.post(url).status_code == 400
    assert como_admin.post(url, {"activo": "no"}).status_code == 400
    usuario.refresh_from_db()
    assert usuario.is_active and not RegistroAuditoria.objects.exists()


def test_si_la_auditoria_falla_el_cambio_se_revierte(crear, como_admin, monkeypatch):
    from reportes import datos

    def falla(*a, **k):
        raise RuntimeError("bitácora caída")

    monkeypatch.setattr(datos, "auditar", falla)
    usuario = crear.usuario()
    como_admin.raise_request_exception = False
    r = como_admin.post(f"/administracion/datos/usuarios/{usuario.pk}/activo/", {"activo": "0"})
    assert r.status_code == 500
    usuario.refresh_from_db()
    assert usuario.is_active


def test_admin_desactiva_a_otro_admin(crear, como_admin):
    otro = crear.usuario("admin")
    como_admin.post(f"/administracion/datos/usuarios/{otro.pk}/activo/", {"activo": "0"})
    otro.refresh_from_db()
    assert not otro.is_active


def test_admin_ya_desactivado_no_desactiva_al_ultimo_admin(crear, admin, rf):
    """Dos admins se desactivan a la vez: el segundo request llega con el actor ya inactivo y se rechaza."""
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.core.exceptions import PermissionDenied

    from reportes import datos

    actor = crear.usuario("admin")
    type(actor).objects.filter(pk=actor.pk).update(is_active=False)  # lo desactivó el otro admin
    request = rf.post("/", {"activo": "0"})
    request.user, request.session = actor, {}
    request._messages = FallbackStorage(request)
    with pytest.raises(PermissionDenied):
        datos.usuario_activo(request, pk=admin.pk)
    admin.refresh_from_db()
    assert admin.is_active


def test_usuario_desactivado_pierde_la_sesion(crear, como_admin):
    from django.test import Client

    usuario = crear.usuario()
    sesion = Client()
    sesion.force_login(usuario)
    assert sesion.get("/mis-reservas/").status_code == 200
    como_admin.post(f"/administracion/datos/usuarios/{usuario.pk}/activo/", {"activo": "0"})
    assert sesion.get("/mis-reservas/").status_code == 302


def test_anonimo_no_escribe(crear, client):
    usuario = crear.usuario()
    client.post(f"/administracion/datos/usuarios/{usuario.pk}/activo/", {"activo": "0"})
    client.post("/administracion/datos/categorias/nueva/", {"nombre": "Intrusa"})
    usuario.refresh_from_db()
    assert usuario.is_active and not Categoria.objects.filter(nombre="Intrusa").exists()


def test_nombre_con_html_se_escapa(crear, como_admin):
    usuario = crear.usuario()
    type(usuario).objects.filter(pk=usuario.pk).update(nombre="<script>x</script>")
    html = como_admin.get("/administracion/datos/usuarios/").content.decode()
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
