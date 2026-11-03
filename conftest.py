import itertools
from types import SimpleNamespace

import pytest
from django.contrib.gis.geos import Point

CLAVE = "Clave-de-prueba-123"
_n = itertools.count(1)


@pytest.fixture(autouse=True)
def _entorno(settings):
    settings.NOMINATIM_URL = ""  # geocodificar() devuelve None sin salir a internet
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.CELERY_TASK_ALWAYS_EAGER = True  # Celery lee los ajustes de Django en vivo (namespace CELERY)
    from django.core.cache import cache

    # La LocMemCache es global al proceso: los contadores de bloqueo no pasan de un test a otro.
    cache.clear()


def _usuario(rol="cliente", **extra):
    from cuentas.models import Usuario

    n = next(_n)
    extra.setdefault("telefono", "+56 9 1234 5678")
    return Usuario.objects.create_user(f"u{n}@prueba.cl", CLAVE, nombre=f"Usuario {n}", rol=rol, **extra)


def _comercio(propietario=None, lat=-33.4290, lon=-70.6040, estado="aprobada"):
    from comercios.models import Comercio
    from comercios.rut import digito_verificador

    n = next(_n)
    cuerpo = 10_000_000 + n
    return Comercio.objects.create(
        propietario=propietario or _usuario("comerciante"),
        rut=f"{cuerpo}-{digito_verificador(cuerpo)}",
        nombre=f"Ferretería {n}",
        direccion="Calle 1",
        comuna="Providencia",
        ubicacion=Point(lon, lat, srid=4326),
        horario="9 a 18",
        telefono="+56 2 2345 6789",
        estado=estado,
    )


def _producto(comercio, nombre='Llave francesa 8"', stock=5, **extra):
    from catalogo.models import Categoria, Producto

    extra.setdefault("categoria", Categoria.objects.get_or_create(nombre="Herramientas manuales")[0])
    return Producto.objects.create(
        comercio=comercio, nombre=nombre, precio_referencial=1000, stock_disponible=stock, **extra
    )


@pytest.fixture
def crear(db):
    return SimpleNamespace(usuario=_usuario, comercio=_comercio, producto=_producto)


@pytest.fixture
def ingresar(client):
    def _ingresar(usuario):
        client.force_login(usuario)
        return client

    return _ingresar
