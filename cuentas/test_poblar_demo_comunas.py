"""poblar_demo deja al menos 5 ferreterías aprobadas con catálogo por cada comuna del piloto."""

import math

import pytest
from django.core.management import call_command

from catalogo.models import Producto
from comercios.models import COMUNAS, Comercio
from comercios.rut import normalizar_rut
from cuentas.models import Usuario


def _km(lat1, lon1, lat2, lon2):
    """Distancia haversine en km (independiente de PostGIS, para no probar con lo mismo que se usa)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


@pytest.fixture
def demo(db, settings):
    settings.DEBUG = True
    call_command("poblar_demo")


def test_cada_comuna_tiene_cinco_ferreterias_aprobadas_con_catalogo(demo):
    aprobados = Comercio.objects.filter(estado=Comercio.Estado.APROBADA)
    for comuna, (lat, lon) in COMUNAS.items():
        de_la_comuna = [c for c in aprobados if c.comuna == comuna]
        assert len(de_la_comuna) >= 5, comuna
        for comercio in de_la_comuna:
            activos = comercio.productos.filter(activo=True)
            assert activos.count() >= 20, comercio.nombre
            assert not activos.filter(nombre_normalizado="").exists(), comercio.nombre
            assert _km(lat, lon, comercio.ubicacion.y, comercio.ubicacion.x) <= 2, comercio.nombre


def test_rut_unicos_y_con_digito_verificador_correcto(demo):
    ruts = list(Comercio.objects.values_list("rut", flat=True))
    assert len(ruts) == len(set(ruts)) >= 40
    # normalizar_rut lanza ValidationError si el dígito verificador no corresponde.
    assert all(normalizar_rut(rut) == rut for rut in ruts)


def test_catalogo_amplio_y_nombres_distintos(demo):
    nombres = set(Producto.objects.values_list("nombre", flat=True))
    assert len(nombres) >= 60
    # Los nombres normalizados guardados coinciden con los que calcularía Producto.save().
    from catalogo.texto import normalizar_texto

    for nombre, normalizado in Producto.objects.values_list("nombre", "nombre_normalizado").distinct():
        assert normalizado == normalizar_texto(nombre)[:120]


def test_propietarios_de_demo_son_comerciantes_con_clave_publica(demo):
    from cuentas.management.commands.poblar_demo import CLAVE, DOMINIO

    for comercio in Comercio.objects.select_related("propietario"):
        dueno = comercio.propietario
        assert dueno.email.endswith(f"@{DOMINIO}")
        assert dueno.rol == Usuario.Rol.COMERCIANTE
        assert dueno.check_password(CLAVE), dueno.email
        comercio.full_clean()  # teléfono, comuna y largo de campos según el modelo


def test_segunda_ejecucion_no_cambia_los_conteos(demo):
    antes = (Usuario.objects.count(), Comercio.objects.count(), Producto.objects.count())
    call_command("poblar_demo")
    assert (Usuario.objects.count(), Comercio.objects.count(), Producto.objects.count()) == antes


def test_amplia_una_base_ya_poblada_con_la_version_anterior(db, settings):
    """La base de desarrollo ya tiene la demo vieja (4 comercios): correr de nuevo debe completarla."""
    settings.DEBUG = True
    call_command("poblar_demo")
    nuevos = Comercio.objects.exclude(
        propietario__email__in=[
            f"{c}@demo.ferrebarrio.cl" for c in ("sanpablo", "eltornillo", "donluis", "losaromos")
        ]
    )
    # El propietario está protegido (PROTECT): primero los comercios (sus productos caen en cascada).
    propietarios = list(nuevos.values_list("propietario", flat=True))
    nuevos.delete()
    Usuario.objects.filter(pk__in=propietarios).delete()
    assert Comercio.objects.count() == 4
    productos_originales = Producto.objects.count()
    call_command("poblar_demo")
    assert Comercio.objects.filter(estado=Comercio.Estado.APROBADA).count() >= 40
    # Los productos extra de los comercios originales no se duplican al completar.
    assert Producto.objects.filter(comercio__propietario__email__startswith="sanpablo@").count() == (
        Producto.objects.filter(comercio__propietario__email__startswith="sanpablo@")
        .values("nombre_normalizado")
        .distinct()
        .count()
    )
    assert Producto.objects.count() > productos_originales
